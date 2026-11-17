# -*- coding: utf-8 -*-
"""
Análises acrescentadas na revisão do manuscrito (novembro de 2026).

Todas partem apenas dos arquivos públicos da entrega:
  5_dados_agregados/        (painel município x mês, população, exposição, oferta de CAPS)
  6_resultados_completos/   (saídas dos modelos originais: contrafactual e validação)

Uso:
  python 14_analises_revisao.py <pasta_da_entrega_ou_raiz_do_repositorio> <pasta_de_saida>

Saídas (CSV, separador vírgula, ponto decimal):
  R1_dose_resposta_abril.csv        RT por 10 p.p. com abril/2024 separado e sem abril/2024
  R2_estudo_eventos_referencia.csv  estudo de eventos com referências alternativas
  R3_sem_vizinhos.csv               RT sem os municípios <1% da mesma região imediata dos >=10%
  R4_controle_negativo.csv          razão entre RT (CAPS ou internações F) e RT dos controles
  R5_contrafactual_treino_marco.csv quase-Poisson e SARIMA treinados até mar/2024 x abr/2024
  R6_oe_corrigida_placebo.csv       O/E dividida por (1 + erro médio nos cortes fictícios)
  R7_oe_mensal.csv                  O/E mês a mês (combinação dos modelos originais)
  R8_caps_sem_registro.csv          CAPS regularmente ativos sem registro, por categoria
  R9_distribuicao_exposicao.csv     distribuição dos usuários por raça/cor e sexo segundo a exposição
  R10_proporcao_f40_f48.csv         proporção de usuários com CID F40-F48 por quadrimestre

Pacotes: pandas, numpy, scipy, statsmodels 0.15, pyfixest 0.60.
"""
import sys, os, warnings
import numpy as np
import pandas as pd
import pyfixest as pf
import statsmodels.api as sm
from scipy import stats
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings("ignore")

ENT = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2] if len(sys.argv) > 2 else "saida_revisao"
os.makedirs(OUT, exist_ok=True)
# aceita a pasta da entrega (5_dados_agregados/, 6_resultados_completos/) ou a raiz do repositório (dados_agregados/, resultados/)
_DA, _RC = os.path.join(ENT, "5_dados_agregados"), os.path.join(ENT, "6_resultados_completos")
DA = _DA if os.path.isdir(_DA) else os.path.join(ENT, "dados_agregados")
RC = _RC if os.path.isdir(_RC) else os.path.join(ENT, "resultados")
INI_POS = pd.Timestamp("2024-05-01")


# ---------------------------------------------------------------- dados
def pop_mensal(pop, col):
    """População anual em 1º de julho, interpolada mês a mês; 2026 repete 2025."""
    p = pop.pivot(index="mun_res", columns="ano", values=col)
    p[2026] = p[2025]
    meses = pd.date_range("2015-01-01", "2026-03-01", freq="MS")
    xa = pd.to_datetime([f"{a}-07-01" for a in p.columns]).values.astype("datetime64[D]").astype(float)
    xm = meses.values.astype("datetime64[D]").astype(float)
    arr = np.vstack([np.interp(xm, xa, row) for row in p.values])
    out = pd.DataFrame(arr, index=p.index, columns=meses).stack().reset_index()
    out.columns = ["mun_res", "mes", col]
    return out


def periodo(m):
    if m < INI_POS:
        return "pre"
    if m <= pd.Timestamp("2024-07-01"):
        return "agudo"
    if m <= pd.Timestamp("2025-04-01"):
        return "subagudo"
    return "tardio"


def montar_painel():
    pm = pd.read_csv(os.path.join(DA, "painel_municipio_mes.csv"), parse_dates=["mes"])
    pc = pd.read_csv(os.path.join(DA, "painel_caps_municipio_mes.csv"), parse_dates=["mes"])
    ex = pd.read_csv(os.path.join(DA, "exposicao_municipio.csv"))
    pop = pd.read_csv(os.path.join(DA, "populacao_municipio_ano.csv"))
    te = pd.read_csv(os.path.join(DA, "territorio_municipios.csv"))
    df = pm.merge(pc, on=["mun_res", "mes"], how="left")
    for c in ["pop_total", "pop_0_17"]:
        df = df.merge(pop_mensal(pop, c), on=["mun_res", "mes"], how="left")
    df = df.merge(ex[["mun_res", "pct_pop_afetada", "exposicao_cat"]], on="mun_res", how="left")
    df = df.merge(te[["mun_res", "regiao_imediata"]], on="mun_res", how="left")
    df["x10"] = df.pct_pop_afetada / 10.0
    df["periodo"] = df.mes.map(periodo)
    df["t"] = (df.mes.dt.year - 2015) * 12 + df.mes.dt.month - 1
    df["lpop"] = np.log(df.pop_total)
    df["mes_s"] = df.mes.dt.strftime("%Y-%m")
    for p in ["agudo", "subagudo", "tardio"]:
        df[f"x_{p}"] = df.x10 * (df.periodo == p)
    df["x_abr24"] = df.x10 * (df.mes == "2024-04-01")
    t0 = (2024 - 2015) * 12 + 4
    k = np.floor((df.t - t0) / 3).astype(int)
    df["k"] = k.where(k >= -9, -9)
    return df, ex


def rt_tab(fit, termos):
    tb = fit.tidy()
    out = {}
    for t in termos:
        if t in tb.index:
            r = tb.loc[t]
            out[t] = (np.exp(r["Estimate"]), np.exp(r["2.5%"]), np.exp(r["97.5%"]), r["Pr(>|t|)"])
    return out


def fepois(df, y, termos, offset="lpop"):
    return pf.fepois(f"{y} ~ " + " + ".join(termos) + " | mun_res + mes_s",
                     data=df, offset=offset, vcov={"CRV1": "mun_res"})


# ---------------------------------------------------------------- R1 e R3
def r1_r3(df):
    linhas = []
    desf = ["caps_usuarios", "caps_usuarios_estresse", "caps_usuarios_ad", "caps_novos",
            "f_total", "f_psicoticos", "f_spa", "ctrl_parto", "nao_f"]
    per = ["x_agudo", "x_subagudo", "x_tardio"]
    reg_exp = set(df.loc[df.exposicao_cat == ">=10%", "regiao_imediata"])
    viz = df.groupby("mun_res").agg(cat=("exposicao_cat", "first"), reg=("regiao_imediata", "first"))
    excl = viz[(viz.cat == "<1%") & (viz.reg.isin(reg_exp))].index
    specs = {
        "principal": (df, per),
        "abril_2024_separado": (df, ["x_abr24"] + per),
        "sem_abril_2024": (df[df.mes != "2024-04-01"], per),
        "sem_vizinhos_<1%": (df[~df.mun_res.isin(excl)], per),
    }
    for y in desf:
        for nome, (d, termos) in specs.items():
            r = rt_tab(fepois(d, y, termos), termos)
            for t, v in r.items():
                linhas.append(dict(desfecho=y, especificacao=nome, termo=t.replace("x_", ""),
                                   rt=v[0], ic_inf=v[1], ic_sup=v[2], p=v[3]))
    R = pd.DataFrame(linhas)
    R[R.especificacao != "sem_vizinhos_<1%"].to_csv(os.path.join(OUT, "R1_dose_resposta_abril.csv"), index=False)
    R3 = R[R.especificacao.isin(["principal", "sem_vizinhos_<1%"])].copy()
    R3["municipios_excluidos"] = np.where(R3.especificacao == "sem_vizinhos_<1%", len(excl), 0)
    R3.to_csv(os.path.join(OUT, "R3_sem_vizinhos.csv"), index=False)
    return R


# ---------------------------------------------------------------- R2
def estudo_eventos(df, y, meses_ref, meses_proprios=None):
    d = df.copy()
    d["kk"] = d.k.astype(str)
    if meses_proprios:
        d.loc[d.mes.isin(pd.to_datetime(meses_proprios)), "kk"] = "proprio"
    d.loc[d.mes.isin(pd.to_datetime(meses_ref)), "kk"] = "ref"
    termos = []
    for kk in sorted(d.kk.unique()):
        if kk == "ref":
            continue
        nm = "xk_" + kk.replace("-", "m")
        d[nm] = d.x10 * (d.kk == kk)
        termos.append(nm)
    fit = fepois(d, y, termos)
    cf = fit.coef()
    nomes = list(cf.index)
    pre = [t for t in termos if t.startswith("xk_m") and int(t[4:]) >= 2]
    idx = [nomes.index(t) for t in pre]
    b = cf[pre].values
    V = fit._vcov[np.ix_(idx, idx)]
    W = float(b @ np.linalg.solve(V, b))
    p_pre = 1 - stats.chi2.cdf(W, len(pre))
    return rt_tab(fit, termos), p_pre


def r2(df):
    specs = {
        "principal (ref. fev-abr/2024)": (["2024-02-01", "2024-03-01", "2024-04-01"], None),
        "ref. fev-mar/2024, abril separado": (["2024-02-01", "2024-03-01"], ["2024-04-01"]),
        "ref. nov/2023-jan/2024": (["2023-11-01", "2023-12-01", "2024-01-01"], None),
    }
    linhas = []
    for y in ["caps_usuarios", "caps_usuarios_estresse", "f_total", "f_psicoticos", "ctrl_parto"]:
        for nome, (ref, prop) in specs.items():
            r, p_pre = estudo_eventos(df, y, ref, prop)
            for t in ["xk_0", "xk_1", "xk_4"]:
                v = r[t]
                linhas.append(dict(desfecho=y, referencia=nome, trimestre=int(t[3:]), rt=v[0],
                                   ic_inf=v[1], ic_sup=v[2], p_pretendencia=p_pre))
    pd.DataFrame(linhas).to_csv(os.path.join(OUT, "R2_estudo_eventos_referencia.csv"), index=False)


# ---------------------------------------------------------------- R4
def empilhado(df, y, ctrl, categorico=False):
    base = ["mun_res", "mes_s", "lpop", "x10", "periodo", "exposicao_cat"]
    manter = df.groupby("mun_res")[y].sum()
    manter = manter[manter > 0].index           # mesma amostra de municípios nos dois desfechos
    d1 = df.loc[df.mun_res.isin(manter), base + [y]].rename(columns={y: "y"}); d1["g"] = 1
    d2 = df.loc[df.mun_res.isin(manter), base + [ctrl]].rename(columns={ctrl: "y"}); d2["g"] = 0
    d = pd.concat([d1, d2], ignore_index=True)
    d["mun_g"] = d.mun_res.astype(str) + "_" + d.g.astype(str)
    d["mes_g"] = d.mes_s + "_" + d.g.astype(str)
    termos = []
    for p in ["agudo", "subagudo", "tardio"]:
        if categorico:
            for c, lab in [(">=10%", "c10"), ("1-<10%", "c1")]:
                d[f"{lab}_{p}"] = ((d.exposicao_cat == c) & (d.periodo == p)).astype(float)
                d[f"{lab}_{p}_g"] = d[f"{lab}_{p}"] * d.g
                termos += [f"{lab}_{p}", f"{lab}_{p}_g"]
        else:
            d[f"x_{p}"] = d.x10 * (d.periodo == p)
            d[f"x_{p}_g"] = d[f"x_{p}"] * d.g
            termos += [f"x_{p}", f"x_{p}_g"]
    fit = pf.fepois("y ~ " + "+".join(termos) + " | mun_g + mes_g", data=d,
                    offset="lpop", vcov={"CRV1": "mun_res"})
    return rt_tab(fit, termos)


def r4(df):
    linhas = []
    pares = [(y, c) for c in ["nao_f", "ctrl_parto"]
             for y in ["caps_usuarios", "caps_usuarios_estresse", "caps_usuarios_ad",
                       "f_total", "f_psicoticos", "f_spa"]]
    for y, c in pares:
        for cat in [False, True]:
            r = empilhado(df, y, c, cat)
            for t, v in r.items():
                if not t.endswith("_g"):
                    continue
                linhas.append(dict(desfecho=y, controle=c,
                                   exposicao=">=10% vs <1%" if t.startswith("c10") else ("1-<10% vs <1%" if t.startswith("c1") else "por 10 p.p."),
                                   periodo=t.split("_")[1], razao_rt=v[0], ic_inf=v[1], ic_sup=v[2], p=v[3]))
    pd.DataFrame(linhas).to_csv(os.path.join(OUT, "R4_controle_negativo.csv"), index=False)


# ---------------------------------------------------------------- R5
def ns_base(x, nos):
    k = np.asarray(nos, float); K = len(k)
    def d(j):
        return (np.clip(x - k[j], 0, None) ** 3 - np.clip(x - k[K - 1], 0, None) ** 3) / (k[K - 1] - k[j])
    return np.column_stack([x] + [d(j) - d(K - 2) for j in range(K - 2)])


def x_qp(s, nos):
    B = ns_base(s.t.values.astype(float), nos)
    M = pd.get_dummies(s.mes.dt.month, prefix="m", drop_first=True).astype(float).values
    cov = ((s.mes >= "2020-03-01") & (s.mes <= "2021-12-01")).astype(float).values[:, None]
    return np.column_stack([np.ones(len(s)), B, M, cov])


PER = {"agudo": ("2024-05-01", "2024-07-01"), "subagudo": ("2024-08-01", "2025-04-01"),
       "tardio": ("2025-05-01", "2026-03-01"), "23 meses": ("2024-05-01", "2026-03-01")}


def resumir(mes, obs, sims):
    res = {}
    for k, (a, b) in PER.items():
        i = ((mes >= a) & (mes <= b)).values
        o = obs[i].sum(); s = sims[i].sum(axis=0)
        res[k] = (o, s.mean(), o / s.mean(), o / np.percentile(s, 97.5), o / np.percentile(s, 2.5))
    return res


def qp(serie, fim_treino, nsim=2000, seed=1):
    s = serie.sort_values("mes").reset_index(drop=True).copy()
    s["t"] = np.arange(len(s))
    s["off"] = np.log(s["pop"] * s.mes.dt.days_in_month)
    tr = s[s.mes <= fim_treino]
    nos = np.quantile(tr.t, [0, 1 / 3, 2 / 3, 1])
    m = sm.GLM(tr.y.values, x_qp(tr, nos), family=sm.families.Poisson(),
               offset=tr.off.values).fit(scale="X2")
    po = s[s.mes >= INI_POS]
    rng = np.random.default_rng(seed)
    B = rng.multivariate_normal(m.params, m.cov_params(), size=nsim)
    mu = np.exp(x_qp(po, nos) @ B.T + po.off.values[:, None])
    phi = m.scale
    sims = rng.negative_binomial(mu / (phi - 1), (mu / (phi - 1)) / (mu / (phi - 1) + mu)) if phi > 1.0001 else rng.poisson(mu)
    return resumir(po.mes.reset_index(drop=True), po.y.values, sims)


def sarima(serie, fim_treino, ordem, nsim=2000, seed=2):
    np.random.seed(seed)
    s = serie.sort_values("mes").reset_index(drop=True).copy()
    s["z"] = np.log((s.y + 0.5) / s["pop"] * 1e5)
    s["cov"] = ((s.mes >= "2020-03-01") & (s.mes <= "2021-12-01")).astype(float)
    tr = s[s.mes <= fim_treino]
    p, q, P = ordem
    m = SARIMAX(tr.z.values, exog=tr[["cov"]].values, order=(p, 0, q),
                seasonal_order=(P, 1, 1, 12), trend="c").fit(disp=False)
    fut = s[s.mes > fim_treino].reset_index(drop=True)
    # rng com semente fixa: a simulação do statsmodels 0.15 não usa o gerador global do NumPy
    sim = np.asarray(m.simulate(nsimulations=len(fut), repetitions=nsim, anchor="end",
                                exog=fut[["cov"]].values, rng=seed)).reshape(len(fut), -1)
    sims = np.exp(sim) * fut["pop"].values[:, None] / 1e5 - 0.5
    keep = (fut.mes >= INI_POS).values
    return resumir(fut.mes[keep].reset_index(drop=True), fut.y.values[keep], sims[keep])


def r5(df):
    ordens = pd.read_csv(os.path.join(RC, "01_contrafactual", "ordens_sarima.csv"))
    linhas = []
    for y in ["caps_usuarios", "caps_usuarios_estresse"]:
        for est in ["estado", "<1%", "1-<10%", ">=10%"]:
            d = df if est == "estado" else df[df.exposicao_cat == est]
            serie = d.groupby("mes").agg(y=(y, "sum"), pop=("pop_total", "sum")).reset_index()
            od = ordens[(ordens.desfecho == y) & (ordens.estrato == est)]
            for fim in ["2024-04-01", "2024-03-01"]:
                modelos = {"quase-Poisson": qp(serie, fim)}
                if len(od):
                    o = od.iloc[0]
                    modelos["SARIMA"] = sarima(serie, fim, (int(o.p), int(o.q), int(o.P)))
                for nm, res in modelos.items():
                    for per, v in res.items():
                        linhas.append(dict(desfecho=y, estrato=est, modelo=nm, treino_ate=fim[:7],
                                           periodo=per, observado=v[0], esperado=v[1], oe=v[2],
                                           ic_inf=v[3], ic_sup=v[4]))
    pd.DataFrame(linhas).to_csv(os.path.join(OUT, "R5_contrafactual_treino_marco.csv"), index=False)


# ---------------------------------------------------------------- R6 e R7
def r6_r7():
    v = pd.read_csv(os.path.join(RC, "01_contrafactual", "validacao_placebo.csv"))
    r = pd.read_csv(os.path.join(RC, "01_contrafactual", "resumo_periodos.csv"))
    e = pd.read_csv(os.path.join(RC, "01_contrafactual", "esperado_mensal.csv"), parse_dates=["mes"])
    ve = v[v.modelo == "ensemble"].groupby(["desfecho", "estrato"]).agg(
        erro_medio_pct=("erro_pct_12m", "mean"), erro_min_pct=("erro_pct_12m", "min"),
        erro_max_pct=("erro_pct_12m", "max"), cortes_dentro_ic=("cobre_12m", "sum")).reset_index()
    re = r[r.modelo == "ensemble"].merge(ve, on=["desfecho", "estrato"], how="left")
    re["oe_corrigida"] = re.razao_oe / (1 + re.erro_medio_pct / 100)
    re[["desfecho", "estrato", "periodo", "observado", "esperado", "razao_oe", "razao_ic_inf",
        "razao_ic_sup", "excesso", "excesso_ic_inf", "excesso_ic_sup", "erro_medio_pct",
        "erro_min_pct", "erro_max_pct", "cortes_dentro_ic", "oe_corrigida"]].to_csv(
        os.path.join(OUT, "R6_oe_corrigida_placebo.csv"), index=False)
    x = e[(e.modelo == "ensemble") & e.desfecho.isin(["caps_usuarios", "caps_usuarios_estresse", "f_total"])].copy()
    x["oe"] = x.observado / x.esperado
    x["oe_ic_inf"] = x.observado / x.ic_sup
    x["oe_ic_sup"] = x.observado / x.ic_inf
    x[["desfecho", "estrato", "mes", "observado", "esperado", "oe", "oe_ic_inf", "oe_ic_sup"]].to_csv(
        os.path.join(OUT, "R7_oe_mensal.csv"), index=False)


# ---------------------------------------------------------------- R8, R9, R10
def r8_r10(df, ex):
    of = pd.read_csv(os.path.join(DA, "oferta_caps_municipio_mes.csv"), parse_dates=["mes"])
    cat = ex.set_index("mun_res")["exposicao_cat"]
    w = of.pivot_table(index="mun_local", columns="mes", values="caps_ativos", aggfunc="sum").fillna(0)
    q1 = w[pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"])].min(axis=1)
    linhas = []
    for m in pd.date_range("2024-04-01", "2024-08-01", freq="MS"):
        falta = (q1 - w[m]).clip(lower=0)
        g = pd.DataFrame({"q1": q1, "falta": falta, "cat": q1.index.map(cat)}).groupby("cat")[["q1", "falta"]].sum()
        for c, row in g.iterrows():
            linhas.append(dict(mes=m.strftime("%Y-%m"), categoria=c, caps_regulares=int(row.q1),
                               sem_registro=int(row.falta), pct=100 * row.falta / row.q1))
    pd.DataFrame(linhas).to_csv(os.path.join(OUT, "R8_caps_sem_registro.csv"), index=False)

    pre = df[(df.mes >= "2023-07-01") & (df.mes <= "2024-04-01")]
    g = pre.groupby("mun_res").agg(
        caps_negra=("caps_usuarios_negra", "sum"), caps_branca=("caps_usuarios_branca", "sum"),
        caps_fem=("caps_usuarios_fem", "sum"), caps_masc=("caps_usuarios_masc", "sum"),
        int_negra=("f_negra", "sum"), int_branca=("f_branca", "sum"),
        pct=("pct_pop_afetada", "first"))
    g["faixa"] = pd.cut(g.pct, [-0.1, 1, 10, 25, 101], right=False,
                        labels=["<1%", "1-<10%", "10-<25%", ">=25%"])
    linhas = []
    for c in ["caps_negra", "caps_branca", "caps_fem", "caps_masc", "int_negra", "int_branca"]:
        tot = g[c].sum()
        d = dict(grupo=c, n=int(tot), exposicao_media=(g[c] * g.pct).sum() / tot)
        for f in ["<1%", "1-<10%", "10-<25%", ">=25%"]:
            d[f"pct_{f}"] = 100 * g.loc[g.faixa == f, c].sum() / tot
        d["pct_>=10%"] = d["pct_10-<25%"] + d["pct_>=25%"]
        linhas.append(d)
    pd.DataFrame(linhas).to_csv(os.path.join(OUT, "R9_distribuicao_exposicao.csv"), index=False)

    d = df[df.mes.dt.year >= 2022].copy()
    d["quadrimestre"] = d.mes.dt.year.astype(str) + "-Q" + ((d.mes.dt.month - 1) // 4 + 1).astype(str)
    q = d.groupby(["quadrimestre", "exposicao_cat"])[["caps_usuarios_estresse", "caps_usuarios"]].sum().reset_index()
    q["pct_f40_f48"] = 100 * q.caps_usuarios_estresse / q.caps_usuarios
    q.to_csv(os.path.join(OUT, "R10_proporcao_f40_f48.csv"), index=False)


if __name__ == "__main__":
    df, ex = montar_painel()
    print("painel:", df.shape)
    r1_r3(df); print("R1/R3 ok")
    r2(df); print("R2 ok")
    r4(df); print("R4 ok")
    r5(df); print("R5 ok")
    r6_r7(); print("R6/R7 ok")
    r8_r10(df, ex); print("R8-R10 ok")
