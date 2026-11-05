"""Análise 1 — internações esperadas sem a enchente (PLANO_ANALISE.md, seção 6).

Três modelos treinados até o mês anterior ao corte e projetados para depois dele:
  qp       regressão quase-Poisson (spline natural da tendência, mês do ano, pandemia; offset
           log pessoa-dias = população × dias no mês), um por série (estado ou estrato);
  sarima   SARIMA na log-taxa, ordem escolhida pelo AIC no treino principal, um por série;
  lgbm     LightGBM global no painel de municípios (Poisson, offset log população), cujas
           previsões municipais são somadas no estado e em cada estrato.
Cada modelo gera N_SIM trajetórias de contagens futuras; o conjunto ("ensemble") junta as
trajetórias dos três em partes iguais. Cortes-placebo (12 meses) medem erro e cobertura.

Saídas em resultados/01_contrafactual/:
  esperado_mensal.csv      mês × desfecho × estrato × modelo: observado, esperado, IC 95%
  resumo_periodos.csv      razão observado/esperado e excesso por período, com IC 95%
  validacao_placebo.csv    erro, viés e cobertura por corte-placebo
  ordens_sarima.csv        ordem escolhida por série
Uso: python -I codigo/05_contrafactual.py [--desfechos f_total,f_spa] [--nsim 2000]
"""
from __future__ import annotations

import os

# Uma thread de BLAS por processo (definido antes de importar NumPy/SciPy): os ajustes usam
# matrizes pequenas e 4 processos × N threads disputando 4 núcleos ficam muito mais lentos.
# O LightGBM usa OpenMP com num_threads explícito e não é afetado.
for _v in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import itertools  # noqa: E402
import multiprocessing as mp  # noqa: E402
import sys  # noqa: E402
import warnings  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import (COVID_FIM, COVID_INICIO, DESFECHOS_CAPS, FIM_ESTUDO, INICIO_ENCHENTE,  # noqa: E402
                   RESULTADOS, carregar_painel)

SAIDA = RESULTADOS / "01_contrafactual"
DESFECHOS = ["f_total", "f_spa", "f_humor", "f_neuroticos", "f_psicoticos", "autolesao",
             "nao_f", "ctrl_parto", "ctrl_apendicite"] + DESFECHOS_CAPS
ESTRATOS = ["estado", "<1%", "1-<10%", ">=10%"]
PLACEBOS = [pd.Timestamp(d) for d in ["2018-05-01", "2019-05-01", "2022-05-01", "2023-05-01"]]
PERIODOS = {
    "agudo (mai-jul/24)": ("2024-05-01", "2024-07-01"),
    "subagudo (ago/24-abr/25)": ("2024-08-01", "2025-04-01"),
    "tardio (mai/25-mar/26)": ("2025-05-01", "2026-03-01"),
    "23 meses (mai/24-mar/26)": ("2024-05-01", "2026-03-01"),
}
LGBM_PARAMS = dict(objective="poisson", learning_rate=0.05, num_leaves=15, min_data_in_leaf=50,
                   feature_fraction=0.9, bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0,
                   verbose=-1, num_threads=4, seed=20261104)
LGBM_RODADAS = 300
LGBM_BOOT = 20
SEMENTE = 20261104


# ---------------------------------------------------------------- séries e utilidades
def series(painel: pd.DataFrame, desfecho: str) -> dict[str, pd.DataFrame]:
    """Contagem mensal e população do estado e de cada estrato de exposição."""
    out = {}
    for e in ESTRATOS:
        d = painel if e == "estado" else painel[painel.exposicao_cat == e]
        s = d.groupby("mes")[[desfecho, "pop_total"]].sum().rename(columns={desfecho: "y", "pop_total": "pop"})
        out[e] = s
    return out


def covid(idx: pd.DatetimeIndex) -> np.ndarray:
    return ((idx >= COVID_INICIO) & (idx <= COVID_FIM)).astype(float)


def spline_natural(x: np.ndarray, nos: np.ndarray) -> np.ndarray:
    """Base de spline cúbica natural (Hastie et al., ESL eq. 5.4–5.5): linear fora dos nós extremos."""
    x = np.asarray(x, float)
    K = len(nos)

    def d(k):
        return (np.clip(x - nos[k], 0, None) ** 3 - np.clip(x - nos[-1], 0, None) ** 3) / (nos[-1] - nos[k])

    return np.column_stack([x] + [d(k) - d(K - 2) for k in range(K - 2)])


def resumo_draws(obs: np.ndarray, draws: np.ndarray) -> dict:
    """obs: total observado; draws: totais esperados simulados (contagens)."""
    e = draws.mean()
    lo, hi = np.percentile(draws, [2.5, 97.5])
    razao = obs / draws
    return {"observado": obs, "esperado": e, "esperado_ic_inf": lo, "esperado_ic_sup": hi,
            "razao_oe": obs / e, "razao_ic_inf": np.percentile(razao, 2.5),
            "razao_ic_sup": np.percentile(razao, 97.5), "excesso": obs - e,
            "excesso_ic_inf": obs - hi, "excesso_ic_sup": obs - lo,
            "p_bicaudal": 2 * min((draws >= obs).mean(), (draws <= obs).mean())}


# ---------------------------------------------------------------- modelos por série
def _aceitavel(b, V, ep_max: float = 3.0) -> bool:
    """Ajuste utilizável: tudo finito, covariância positiva definida e EP plausíveis (escala log)."""
    if not (np.all(np.isfinite(b)) and np.all(np.isfinite(V))):
        return False
    V = (V + V.T) / 2
    return bool(np.all(np.linalg.eigvalsh(V) > 0) and np.sqrt(np.diag(V)).max() < ep_max)


def _ajuste_qp(y, X, off) -> tuple[np.ndarray, np.ndarray, float]:
    """Regressão quase-Poisson (dispersão φ de Pearson); devolve coeficientes, covariância e φ."""
    import statsmodels.api as sm

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g = sm.GLM(y, X, family=sm.families.Poisson(), offset=off).fit(scale="X2")
    b, V = np.asarray(g.params), np.asarray(g.cov_params())
    if not _aceitavel(b, V):
        raise RuntimeError("quase-Poisson sem ajuste utilizável (série esparsa demais)")
    return b, (V + V.T) / 2, float(g.scale)


def ajustar_qp(s: pd.DataFrame, corte: pd.Timestamp, fim: pd.Timestamp, nsim: int, rng,
               rotulo: str = "") -> np.ndarray:
    import statsmodels.api as sm

    tr, fu = s[s.index < corte], s[(s.index >= corte) & (s.index <= fim)]

    def X(idx, nos):
        t = (idx.year - 2015) + (idx.month - 1) / 12
        mes = pd.get_dummies(pd.Categorical(idx.month, categories=range(1, 13)), drop_first=True).values
        return np.column_stack([np.ones(len(idx)), spline_natural(t, nos), mes, covid(idx)]).astype(float)

    t_tr = (tr.index.year - 2015) + (tr.index.month - 1) / 12
    nos = np.quantile(t_tr, [0, 1 / 3, 2 / 3, 1])
    Xtr, Xfu = X(tr.index, nos), X(fu.index, nos)
    if covid(tr.index).sum() == 0:  # cortes antes da pandemia: coluna toda zero sai
        Xtr, Xfu = Xtr[:, :-1], Xfu[:, :-1]
    # Offset: pessoa-dias (população × dias no mês). Dias como covariável seriam quase colineares
    # com os indicadores de mês (só fevereiro bissexto difere).
    off_tr = np.log(tr["pop"].values * tr.index.days_in_month.values)
    off_fu = np.log(fu["pop"].values * fu.index.days_in_month.values)
    b, V, phi = _ajuste_qp(tr.y.values, Xtr, off_tr)
    B = rng.multivariate_normal(b, V, size=nsim)
    mu = np.exp(B @ Xfu.T + off_fu)  # nsim × h
    if not np.all(np.isfinite(mu)):
        raise RuntimeError(f"quase-Poisson [{rotulo}]: previsão não finita")
    if phi <= 1:
        return rng.poisson(mu).astype(float)
    # Preditiva com variância φμ: binomial negativa com n = μ/(φ−1) e p = 1/φ.
    return rng.negative_binomial(mu / (phi - 1), 1 / phi).astype(float)


def escolher_ordem_sarima(s: pd.DataFrame, corte: pd.Timestamp) -> tuple:
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    tr = s[s.index < corte]
    ylog = np.log((tr.y + 0.5) / tr["pop"] * 1e5)
    ex = covid(tr.index)[:, None] if covid(tr.index).sum() else None
    melhor = (np.inf, None)
    for p, q, P in itertools.product([0, 1, 2], [0, 1, 2], [0, 1]):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r = SARIMAX(ylog.values, exog=ex, order=(p, 0, q), seasonal_order=(P, 1, 1, 12),
                            trend="c").fit(disp=False, maxiter=200)
            if r.aic < melhor[0]:
                melhor = (r.aic, (p, q, P))
        except Exception:  # noqa: BLE001 — combinação que não converge fica de fora
            continue
    return melhor[1]


def ajustar_sarima(s: pd.DataFrame, corte, fim, nsim: int, rng, ordem: tuple) -> np.ndarray:
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    tr, fu = s[s.index < corte], s[(s.index >= corte) & (s.index <= fim)]
    ylog = np.log((tr.y + 0.5) / tr["pop"] * 1e5)
    usa_cov = covid(tr.index).sum() > 0
    ex = covid(tr.index)[:, None] if usa_cov else None
    exf = covid(fu.index)[:, None] if usa_cov else None
    for p, q, P in [ordem, (0, 0, 0)]:  # reserva: só a parte sazonal, se a ordem escolhida falhar
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r = SARIMAX(ylog.values, exog=ex, order=(p, 0, q), seasonal_order=(P, 1, 1, 12),
                            trend="c").fit(disp=False, maxiter=200)
                sim = r.simulate(nsimulations=len(fu), repetitions=nsim, anchor="end", exog=exf,
                                 rng=rng)
            break
        except (ValueError, np.linalg.LinAlgError) as e:
            print(f"  aviso SARIMA{(p, 0, q)}x{(P, 1, 1)}: {e}; usando ordem de reserva", flush=True)
    else:
        raise RuntimeError("SARIMA falhou também na ordem de reserva")
    sim = np.asarray(sim).reshape(len(fu), nsim).T  # nsim × h
    return np.clip(np.exp(sim) * fu["pop"].values / 1e5 - 0.5, 0, None)


def tarefa_serie(args) -> list[dict]:
    """Ajusta nb e sarima numa série e devolve os draws mensais (para o processo-pai resumir)."""
    desfecho, estrato, s, corte, fim, nsim, ordem, semente = args
    rng = np.random.default_rng(semente)
    out = []
    rotulo = f"{desfecho} | {estrato} | corte {corte.date()}"
    for nome, fn in [("qp", lambda: ajustar_qp(s, corte, fim, nsim, rng, rotulo)),
                     ("sarima", lambda: ajustar_sarima(s, corte, fim, nsim, rng, ordem))]:
        try:
            out.append({"desfecho": desfecho, "estrato": estrato, "corte": corte, "modelo": nome, "draws": fn()})
        except (RuntimeError, ValueError, np.linalg.LinAlgError) as e:
            print(f"  FALHA {nome} [{rotulo}]: {e} — série sem este modelo", flush=True)
    return out


# ---------------------------------------------------------------- LightGBM global (painel)
def lgbm_draws(painel: pd.DataFrame, desfecho: str, corte, fim, nsim: int, rng) -> dict[str, np.ndarray]:
    import lightgbm as lgb

    d = painel[painel.mes <= fim][["mun_res", "mes", desfecho, "pop_total", "exposicao_cat"]].copy()
    d = d.rename(columns={desfecho: "y"})
    pre = d[d.mes < corte]
    ult24 = pre[pre.mes >= corte - pd.DateOffset(months=24)]
    ant = pre[pre.mes < corte - pd.DateOffset(months=24)]

    def taxa(x):
        g = x.groupby("mun_res")
        return np.log((g.y.sum() + 0.5) / g.pop_total.sum() * 1e5)

    feats = pd.DataFrame({"taxa_24m": taxa(ult24), "taxa_toda": taxa(pre)})
    feats["tendencia"] = feats.taxa_24m - (taxa(ant) if len(ant) else feats.taxa_24m)
    feats["log_pop"] = np.log(pre.groupby("mun_res").pop_total.mean())
    d = d.join(feats, on="mun_res")
    d["mes_ano"] = d.mes.dt.month
    d["t"] = (d.mes.dt.year - 2015) * 12 + d.mes.dt.month - 1
    d["covid"] = covid(pd.DatetimeIndex(d.mes))
    # Offset = população + taxa média do município antes do corte: as árvores só aprendem desvios
    # (sazonalidade, tendência, pandemia). Sem isso, o objetivo Poisson do LightGBM fica viesado em
    # desfechos de taxa alta (o total de treino de "demais causas" saía 1,8× o observado).
    d["offset"] = np.log(d.pop_total / 1e5) + d.taxa_toda
    d["desvio_24m"] = d.taxa_24m - d.taxa_toda
    cols = ["mes_ano", "t", "covid", "desvio_24m", "tendencia", "log_pop"]
    tr, fu = d[d.mes < corte], d[d.mes >= corte]
    muns = tr.mun_res.unique()
    meses_fu = np.sort(fu.mes.unique())
    estr = {e: (fu.exposicao_cat == e).values if e != "estado" else np.ones(len(fu), bool) for e in ESTRATOS}
    out = {e: [] for e in ESTRATOS}
    por_boot = int(np.ceil(nsim / LGBM_BOOT))
    for b in range(LGBM_BOOT):
        amostra = rng.choice(muns, size=len(muns), replace=True)
        cont = pd.Series(amostra).value_counts()
        w = tr.mun_res.map(cont).fillna(0).values  # reamostragem de municípios via pesos
        ds = lgb.Dataset(tr[cols], label=tr.y, weight=w, init_score=tr.offset,
                         categorical_feature=["mes_ano"], free_raw_data=False)
        m = lgb.train({**LGBM_PARAMS, "seed": SEMENTE + b}, ds, num_boost_round=LGBM_RODADAS)
        mu = np.exp(m.predict(fu[cols], raw_score=True) + fu.offset.values)
        for e in ESTRATOS:
            soma = pd.Series(mu[estr[e]]).groupby(fu.mes.values[estr[e]]).sum().reindex(meses_fu).values
            out[e].append(rng.poisson(np.tile(soma, (por_boot, 1))).astype(float))
    return {e: np.vstack(v)[:nsim] for e, v in out.items()}


# ---------------------------------------------------------------- orquestração
def _uma_thread() -> None:
    """Cada processo usa 1 thread de BLAS/OpenMP; sem isso, 4 processos × 4 threads disputam
    4 núcleos e os ajustes com matrizes pequenas (SARIMA) ficam dezenas de vezes mais lentos."""
    import scipy.linalg  # noqa: F401  (carrega a OpenBLAS do SciPy antes de limitar)
    import statsmodels.api  # noqa: F401
    from threadpoolctl import threadpool_limits
    threadpool_limits(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--desfechos", default=",".join(DESFECHOS))
    ap.add_argument("--nsim", type=int, default=2000)
    ap.add_argument("--processos", type=int, default=4)
    ap.add_argument("--anexar", action="store_true",
                    help="mantém nos CSVs os desfechos já estimados e substitui só os desta execução")
    a = ap.parse_args()
    desfechos = a.desfechos.split(",")
    SAIDA.mkdir(parents=True, exist_ok=True)
    painel = carregar_painel()
    print(f"painel: {painel.mun_res.nunique()} municípios × {painel.mes.nunique()} meses", flush=True)

    cortes = [(INICIO_ENCHENTE, FIM_ESTUDO)] + [(c, c + pd.DateOffset(months=11)) for c in PLACEBOS]
    ser = {d: series(painel, d) for d in desfechos}
    ordens = {}
    with ProcessPoolExecutor(a.processos, mp_context=mp.get_context("fork"), initializer=_uma_thread) as ex:
        chaves = [(d, e) for d in desfechos for e in ESTRATOS]
        for (d, e), o in zip(chaves, ex.map(escolher_ordem_sarima, [ser[d][e] for d, e in chaves],
                                            [INICIO_ENCHENTE] * len(chaves))):
            ordens[(d, e)] = o
        ordens_df = pd.DataFrame([{"desfecho": d, "estrato": e, "p": o[0], "q": o[1], "P": o[2]}
                                  for (d, e), o in ordens.items()])
        if a.anexar and (SAIDA / "ordens_sarima.csv").exists():
            antigo = pd.read_csv(SAIDA / "ordens_sarima.csv")
            ordens_df = pd.concat([antigo[~antigo.desfecho.isin(desfechos)], ordens_df])
        ordens_df.to_csv(SAIDA / "ordens_sarima.csv", index=False)
        print("ordens SARIMA escolhidas", flush=True)
        tarefas = [(d, e, ser[d][e], c, f, a.nsim, ordens[(d, e)], SEMENTE + i)
                   for i, ((d, e), (c, f)) in enumerate(itertools.product(chaves, cortes))]
        draws = [r for lst in ex.map(tarefa_serie, tarefas) for r in lst]
    print("qp e sarima prontos", flush=True)
    rng = np.random.default_rng(SEMENTE)
    for d in desfechos:
        for c, f in cortes:
            for e, dr in lgbm_draws(painel, d, c, f, a.nsim, rng).items():
                draws.append({"desfecho": d, "estrato": e, "corte": c, "modelo": "lgbm", "draws": dr})
        print(f"lgbm {d} pronto", flush=True)

    # ensemble: partes iguais das trajetórias de cada modelo
    grupos = {}
    for r in draws:
        grupos.setdefault((r["desfecho"], r["estrato"], r["corte"]), []).append(r)
    for k, lst in grupos.items():
        n = min(len(r["draws"]) for r in lst) // len(lst)
        ens = np.vstack([r["draws"][rng.permutation(len(r["draws"]))[:n]] for r in lst])
        draws.append({"desfecho": k[0], "estrato": k[1], "corte": k[2], "modelo": "ensemble", "draws": ens})

    mensal, periodos, valid = [], [], []
    for r in draws:
        d, e, c = r["desfecho"], r["estrato"], r["corte"]
        f = FIM_ESTUDO if c == INICIO_ENCHENTE else c + pd.DateOffset(months=11)
        s = ser[d][e]
        fu = s[(s.index >= c) & (s.index <= f)]
        D = r["draws"]
        base = {"desfecho": d, "estrato": e, "modelo": r["modelo"]}
        if c == INICIO_ENCHENTE:
            for j, mes in enumerate(fu.index):
                lo, hi = np.percentile(D[:, j], [2.5, 97.5])
                mensal.append({**base, "mes": mes.strftime("%Y-%m-%d"), "observado": fu.y.iloc[j], "esperado": D[:, j].mean(),
                               "ic_inf": lo, "ic_sup": hi, "pop": fu["pop"].iloc[j]})
            for nome, (i0, i1) in PERIODOS.items():
                sel = (fu.index >= i0) & (fu.index <= i1)
                periodos.append({**base, "periodo": nome, "meses": int(sel.sum()),
                                 **resumo_draws(fu.y.values[sel].sum(), D[:, sel].sum(axis=1))})
        else:
            tot = resumo_draws(fu.y.values.sum(), D.sum(axis=1))
            lo, hi = np.percentile(D, [2.5, 97.5], axis=0)
            valid.append({**base, "corte_placebo": c.date(), "observado_12m": tot["observado"],
                          "esperado_12m": tot["esperado"], "erro_pct_12m": 100 * (tot["razao_oe"] - 1),
                          "cobre_12m": tot["esperado_ic_inf"] <= tot["observado"] <= tot["esperado_ic_sup"],
                          "erro_abs_medio_mensal_pct": 100 * np.mean(np.abs(fu.y.values - D.mean(0)) / D.mean(0)),
                          "cobertura_mensal": np.mean((fu.y.values >= lo) & (fu.y.values <= hi))})
    def gravar(df: pd.DataFrame, nome: str) -> pd.DataFrame:
        if a.anexar and (SAIDA / nome).exists():
            antigo = pd.read_csv(SAIDA / nome)
            df = pd.concat([antigo[~antigo.desfecho.isin(desfechos)], df], ignore_index=True)
        df.to_csv(SAIDA / nome, index=False)
        return df

    gravar(pd.DataFrame(mensal), "esperado_mensal.csv")
    per = gravar(pd.DataFrame(periodos), "resumo_periodos.csv")
    val = gravar(pd.DataFrame(valid), "validacao_placebo.csv")
    pd.set_option("display.width", 250)
    print("\n== Validação (média dos 4 cortes-placebo, 12 meses)")
    print(val.groupby(["desfecho", "estrato", "modelo"])[["erro_pct_12m", "cobre_12m", "erro_abs_medio_mensal_pct",
                                                          "cobertura_mensal"]].mean().round(2).to_string())
    print("\n== Razão observado/esperado (ensemble)")
    print(per[per.modelo == "ensemble"].pivot_table(index=["desfecho", "estrato"], columns="periodo",
                                                    values="razao_oe").round(3).to_string())


if __name__ == "__main__":
    main()
