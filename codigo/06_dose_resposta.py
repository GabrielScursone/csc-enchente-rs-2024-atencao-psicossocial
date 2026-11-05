"""Análise 2 — dose-resposta no painel de municípios (PLANO_ANALISE.md, seção 7).

Poisson com efeitos fixos de município e de mês-calendário, offset log(população do grupo),
erros-padrão agrupados por município (pyfixest.fepois):
  evento     y ~ i(k, x, ref=-1)            k = trimestre relativo a mai/2024 (−9 agrupa ≤ −9)
  periodo    y ~ i(periodo, x, ref="pre")   agudo, subagudo, tardio × pré (jan/2015–abr/2024)
x é a exposição: % da população em área afetada / 10 (razão de taxas por 10 p.p.), ou
indicadores das categorias 1–<10% e ≥10% (referência <1%).

Sensibilidades (seção 8): sem Porto Alegre; sem as regiões de saúde do Vale do Taquari (enchentes
de set e nov/2023); efeito fixo de macrorregião de saúde × ano; data-placebo mai/2023 (só dados
anteriores a mai/2024).

Saídas em resultados/02_dose_resposta/: coef_evento.csv, coef_periodo.csv, pretendencia.csv.
Uso: python -I codigo/06_dose_resposta.py [--desfechos f_total,f_spa] [--rapido]
"""
from __future__ import annotations

import argparse
import gc
import resource
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import INICIO_ENCHENTE, PROCESSADOS, RESULTADOS, carregar_painel  # noqa: E402

SAIDA = RESULTADOS / "02_dose_resposta"
# desfecho → coluna de população usada como offset
DESFECHOS = {
    "f_total": "pop_total", "f_spa": "pop_total", "f_alcool": "pop_total", "f_humor": "pop_total",
    "f_neuroticos": "pop_total", "f_estresse": "pop_total", "f_psicoticos": "pop_total",
    "f_organicos": "pop_total", "autolesao": "pop_total", "f_obito": "pop_total",
    "f_masc": "pop_masc", "f_fem": "pop_fem", "f_spa_masc": "pop_masc", "f_spa_fem": "pop_fem",
    "f_0_17": "pop_0_17", "f_18_39": "pop_18_39", "f_40_59": "pop_40_59", "f_60m": "pop_60m",
    "f_branca": "pop_total", "f_negra": "pop_total",
    "f_leito_psiq": "pop_total", "f_leito_sm_hg": "pop_total", "f_leito_outro": "pop_total",
    "f_urgencia": "pop_total", "f_eletiva": "pop_total", "f_fora_mun": "pop_total",
    "nao_f": "pop_total", "ctrl_parto": "pop_fem", "ctrl_apendicite": "pop_total",
    # CAPS (Emenda 1)
    "caps_usuarios": "pop_total", "caps_novos": "pop_total", "caps_usuarios_ad": "pop_total",
    "caps_usuarios_estresse": "pop_total", "caps_usuarios_fem": "pop_fem", "caps_usuarios_0_17": "pop_0_17",
    "caps_proced": "pop_total", "caps_crise": "pop_total", "caps_individual": "pop_total",
    "caps_grupo": "pop_total", "caps_familiar": "pop_total", "caps_domiciliar": "pop_total",
    "caps_acolhimento": "pop_total",
}
PORTO_ALEGRE = 431490
# Vale do Taquari (enchentes de set e nov/2023): regiões geográficas imediatas do IBGE
REGIOES_TAQUARI = {"Lajeado", "Encantado"}
PERIODOS = [("agudo", "2024-05-01", "2024-07-31"), ("subagudo", "2024-08-01", "2025-04-30"),
            ("tardio", "2025-05-01", "2026-12-31")]


def preparar(p: pd.DataFrame) -> pd.DataFrame:
    p = p.copy()
    meses = (p.mes.dt.year - INICIO_ENCHENTE.year) * 12 + p.mes.dt.month - INICIO_ENCHENTE.month
    p["k"] = np.maximum(np.floor_divide(meses, 3), -9).astype(int)
    p["periodo"] = "pre"
    for nome, a, b in PERIODOS:
        p.loc[p.mes.between(a, b), "periodo"] = nome
    p["x"] = p.pct_pop_afetada / 10
    p["e_1_10"] = (p.exposicao_cat == "1-<10%").astype(float)
    p["e_10"] = (p.exposicao_cat == ">=10%").astype(float)
    p["ano"] = p.mes.dt.year
    p["mes_s"] = p.mes.dt.strftime("%Y-%m")
    return p


COLS_MODELO = ["mun_res", "mes_s", "ano", "macrorregiao", "k", "periodo", "x", "e_1_10", "e_10"]


def ajustar(dados: pd.DataFrame, y: str, pop: str, rhs: str, fe: str):
    """Só as colunas do modelo e sem guardar os dados no objeto ajustado: o painel inteiro
    copiado em centenas de ajustes estourava o limite de memória do processo."""
    import pyfixest as pf

    cols = [c for c in COLS_MODELO if c in dados.columns] + (["placebo"] if "placebo" in dados.columns else [])
    d = dados.loc[dados[pop] > 0, cols + [y]].copy()
    d["log_pop"] = np.log(dados.loc[dados[pop] > 0, pop])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pf.fepois(f"{y} ~ {rhs} | {fe}", data=d, offset="log_pop",
                         vcov={"CRV1": "mun_res"}, store_data=False, copy_data=False)


def tabela(fit, **info) -> pd.DataFrame:
    t = fit.tidy().reset_index().rename(columns={"Coefficient": "termo", "Estimate": "coef",
                                                 "Std. Error": "ep", "Pr(>|t|)": "p"})
    t["rr"] = np.exp(t.coef)
    t["rr_ic_inf"] = np.exp(t.coef - 1.96 * t.ep)
    t["rr_ic_sup"] = np.exp(t.coef + 1.96 * t.ep)
    for k, v in info.items():
        t.insert(0, k, v)
    t["n_obs"] = fit._N
    return t[[*info, "termo", "coef", "ep", "p", "rr", "rr_ic_inf", "rr_ic_sup", "n_obs"]]


def wald_pre(fit, prefixo: str) -> tuple[float, int]:
    """Teste conjunto de β_k = 0 para k ≤ −2 (inclui o bloco agrupado −9)."""
    nomes = list(fit._coefnames)
    idx = [i for i, n in enumerate(nomes) if n.startswith(prefixo) and _k(n) <= -2]
    if not idx:
        return np.nan, 0
    b = np.asarray(fit.coef())[idx]
    V = np.asarray(fit._vcov)[np.ix_(idx, idx)]
    w = float(b @ np.linalg.solve(V, b))
    return 1 - stats.chi2.cdf(w, len(idx)), len(idx)


def _k(nome: str) -> int:
    # nomes do pyfixest: "k::-3:x"
    return int(nome.split("::")[1].split(":")[0])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--desfechos", default=",".join(DESFECHOS))
    ap.add_argument("--rapido", action="store_true", help="só a especificação principal")
    ap.add_argument("--anexar", action="store_true",
                    help="mantém nos CSVs os desfechos já estimados e substitui só os desta execução")
    a = ap.parse_args()
    SAIDA.mkdir(parents=True, exist_ok=True)
    p = preparar(carregar_painel())
    terr = pd.read_csv(PROCESSADOS / "territorio_municipios.csv")
    p = p.merge(terr[["mun_res", "macrorregiao"]], on="mun_res", how="left")
    taquari = set(terr.loc[terr.regiao_imediata.isin(REGIOES_TAQUARI), "mun_res"])
    print(f"{p.mun_res.nunique()} municípios; Vale do Taquari (sensibilidade): {len(taquari)}; "
          f"macrorregiões: {terr.fonte_macrorregiao.iloc[0]}", flush=True)

    specs = {"principal": (p, "mun_res + mes_s")}
    if not a.rapido:
        specs |= {
            "sem_porto_alegre": (p[p.mun_res != PORTO_ALEGRE], "mun_res + mes_s"),
            "sem_vale_taquari": (p[~p.mun_res.isin(taquari)], "mun_res + mes_s"),
            "macro_x_ano": (p, "mun_res + mes_s + macrorregiao^ano"),
        }
    ev, per, pre = [], [], []
    for y in a.desfechos.split(","):
        pop = DESFECHOS[y]
        for nome, (d, fe) in specs.items():
            f1 = ajustar(d, y, pop, "i(k, x, ref=-1)", fe)
            ev.append(tabela(f1, desfecho=y, especificacao=nome, exposicao="continua_10pp"))
            pv, gl = wald_pre(f1, "k::")
            pre.append({"desfecho": y, "especificacao": nome, "exposicao": "continua_10pp",
                        "p_pretendencia": pv, "gl": gl})
            f2 = ajustar(d, y, pop, "i(periodo, x, ref='pre')", fe)
            per.append(tabela(f2, desfecho=y, especificacao=nome, exposicao="continua_10pp"))
            if nome == "principal":
                f3 = ajustar(d, y, pop, "i(k, e_1_10, ref=-1) + i(k, e_10, ref=-1)", fe)
                ev.append(tabela(f3, desfecho=y, especificacao=nome, exposicao="categorias"))
                f4 = ajustar(d, y, pop, "i(periodo, e_1_10, ref='pre') + i(periodo, e_10, ref='pre')", fe)
                per.append(tabela(f4, desfecho=y, especificacao=nome, exposicao="categorias"))
                # data-placebo: mai/2023, só com dados anteriores à enchente
                dp = d[d.mes < INICIO_ENCHENTE].assign(
                    placebo=lambda z: np.where(z.mes >= "2023-05-01", "placebo", "pre"))
                f5 = ajustar(dp, y, pop, "i(placebo, x, ref='pre')", fe)
                per.append(tabela(f5, desfecho=y, especificacao="placebo_mai2023",
                                  exposicao="continua_10pp"))
        gc.collect()
        print(f"{y}: ok (memória máx. {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6:.2f} GB)", flush=True)
    ev, per, pre = pd.concat(ev), pd.concat(per), pd.DataFrame(pre)
    feitos = set(a.desfechos.split(","))
    for df, nome in [(ev, "coef_evento.csv"), (per, "coef_periodo.csv"), (pre, "pretendencia.csv")]:
        if a.anexar and (SAIDA / nome).exists():
            antigo = pd.read_csv(SAIDA / nome)
            df = pd.concat([antigo[~antigo.desfecho.isin(feitos)], df], ignore_index=True)
        df.to_csv(SAIDA / nome, index=False)
    pd.set_option("display.width", 250)
    pr = per[per.exposicao == "continua_10pp"]
    print(pr[["desfecho", "especificacao", "termo", "rr", "rr_ic_inf", "rr_ic_sup", "p"]].round(3).to_string())
    print(pre.round(3).to_string())


if __name__ == "__main__":
    main()
