"""Robustez — synthetic difference-in-differences (PLANO_ANALISE.md, seção 8.1).

Tratados: municípios com ≥10% da população em área afetada. Controles: <1%. O estrato
1–<10% fica fora. Unidade de tempo: trimestres alinhados a maio/2024 (o mesmo k do estudo de
eventos). O trimestre incompleto de jan/2015 sai. Desfecho: taxa mensal média por 100 mil
habitantes no trimestre. O efeito relativo é ATT / contrafactual dos tratados no pós-período.
O IC é ATT ± 1,96 × EP jackknife (pesos fixos), como no pacote synthdid.

Saída: resultados/03_robustez/sdid.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import INICIO_ENCHENTE, RESULTADOS, carregar_painel  # noqa: E402
from sdid import estimar  # noqa: E402

SAIDA = RESULTADOS / "03_robustez"
DESFECHOS = {"f_total": "pop_total", "f_spa": "pop_total", "f_humor": "pop_total",
             "f_psicoticos": "pop_total", "ctrl_parto": "pop_fem", "nao_f": "pop_total",
             "caps_usuarios": "pop_total", "caps_novos": "pop_total", "caps_crise": "pop_total"}
POS = {"agudo": [0], "subagudo": [1, 2, 3], "tardio": [4, 5, 6, 7], "todo o pós": list(range(8))}


def matriz(p: pd.DataFrame, y: str, pop: str) -> tuple[pd.DataFrame, int]:
    meses = (p.mes.dt.year - INICIO_ENCHENTE.year) * 12 + p.mes.dt.month - INICIO_ENCHENTE.month
    p = p.assign(k=np.floor_divide(meses, 3))
    p = p[p.k >= -37]
    g = p.groupby(["mun_res", "k"])[[y, pop]].sum()
    taxa = (1e5 * g[y] / g[pop]).unstack("k")
    trat = p.groupby("mun_res").exposicao_cat.first()
    ctrl, tr = taxa[trat.reindex(taxa.index) == "<1%"], taxa[trat.reindex(taxa.index) == ">=10%"]
    return pd.concat([ctrl, tr]), len(ctrl)


def margens_caps() -> pd.DataFrame:
    """CAPS × mês (pelo município onde o CAPS fica), CAPS com registro em todo o 1º trimestre de 2024.
    Extensiva: P(mês sem registro), modelo linear com EF de CAPS e de mês.
    Intensiva: usuários nos meses com registro, Poisson com EF de CAPS e de mês.
    Exposição = % da população do município do CAPS em área afetada / 10, por período."""
    import warnings
    import pyfixest as pf
    from comum import PROCESSADOS

    of = pd.read_parquet(PROCESSADOS / "producao_caps_estabelecimento_mes.parquet")
    exp = pd.read_csv(PROCESSADOS / "exposicao_municipio.csv")[["mun_res", "pct_pop_afetada"]]
    grade = of.pivot_table(index=["cnes", "mun_local"], columns="mes", values="usuarios", aggfunc="sum").fillna(0)
    ref = [c for c in grade.columns if pd.Timestamp("2024-01-01") <= c <= pd.Timestamp("2024-03-01")]
    grade = grade[(grade[ref] > 0).all(axis=1)]
    d = grade.stack().rename("usuarios").reset_index()
    d = d[d.mes >= "2022-05-01"].merge(exp.rename(columns={"mun_res": "mun_local"}), on="mun_local", how="left")
    d["x"] = d.pct_pop_afetada.fillna(0) / 10
    d["sem_registro"] = (d.usuarios == 0).astype(float)
    d["periodo"] = "pre"
    for nome, a, b in [("agudo", "2024-05-01", "2024-07-31"), ("subagudo", "2024-08-01", "2025-04-30"),
                       ("tardio", "2025-05-01", "2026-12-31")]:
        d.loc[d.mes.between(a, b), "periodo"] = nome
    d["abril_2024"] = (d.mes == "2024-04-01").astype(float)
    d.loc[d.mes == "2024-04-01", "periodo"] = "abr_2024"
    d["mes_s"] = d.mes.dt.strftime("%Y-%m")
    linhas = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ext = pf.feols("sem_registro ~ i(periodo, x, ref='pre') | cnes + mes_s", data=d, vcov={"CRV1": "cnes"})
        inten = pf.fepois("usuarios ~ i(periodo, x, ref='pre') | cnes + mes_s", data=d[d.usuarios > 0],
                          vcov={"CRV1": "cnes"})
    for nome, fit, escala in [("extensiva: P(mês sem registro), diferença por 10 p.p.", ext, "dif"),
                              ("intensiva: usuários por CAPS com registro, RT por 10 p.p.", inten, "rt")]:
        t = fit.tidy().reset_index()
        for _, r in t.iterrows():
            est, lo, hi = r.Estimate, r.Estimate - 1.96 * r["Std. Error"], r.Estimate + 1.96 * r["Std. Error"]
            if escala == "rt":
                est, lo, hi = np.exp(est), np.exp(lo), np.exp(hi)
            linhas.append({"margem": nome, "termo": r.Coefficient.split("::")[1].split(":")[0],
                           "estimativa": est, "ic_inf": lo, "ic_sup": hi, "p": r["Pr(>|t|)"],
                           "caps": d.cnes.nunique(), "n_obs": fit._N})
    base = d[d.periodo == "pre"].sem_registro.mean()
    print(f"CAPS na análise: {d.cnes.nunique()}; proporção de meses sem registro no pré (05/22–03/24): {base:.3f}")
    return pd.DataFrame(linhas)


def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    p = carregar_painel()
    linhas = []
    for y, pop in DESFECHOS.items():
        Y, N0 = matriz(p, y, pop)
        pre = [c for c in Y.columns if c < 0]
        for nome, ks in POS.items():
            pos = [k for k in ks if k in Y.columns]
            if not pos:
                continue
            cols = pre + pos
            r = estimar(Y[cols].to_numpy(float), N0, len(pre))
            rel = r["att"] / r["contrafactual_tratados_pos"]
            linhas.append({"desfecho": y, "periodo": nome, "n_controles": N0, "n_tratados": len(Y) - N0,
                           "trimestres_pre": len(pre), "att_taxa_100mil_mes": r["att"], "ep": r["ep"],
                           "att_ic_inf": r["att"] - 1.96 * r["ep"], "att_ic_sup": r["att"] + 1.96 * r["ep"],
                           "tratados_pos": r["media_tratados_pos"],
                           "contrafactual_pos": r["contrafactual_tratados_pos"],
                           "efeito_relativo_pct": 100 * rel,
                           "efeito_rel_ic_inf_pct": 100 * (r["att"] - 1.96 * r["ep"]) / r["contrafactual_tratados_pos"],
                           "efeito_rel_ic_sup_pct": 100 * (r["att"] + 1.96 * r["ep"]) / r["contrafactual_tratados_pos"],
                           "controles_com_peso": int((r["omega"] > 0).sum()),
                           "trimestres_pre_com_peso": int((r["lambda"] > 0).sum())})
        print(f"{y}: ok", flush=True)
    t = pd.DataFrame(linhas)
    t.to_csv(SAIDA / "sdid.csv", index=False)
    mg = margens_caps()
    mg.to_csv(SAIDA / "caps_margens_extensiva_intensiva.csv", index=False)
    print(mg.round(4).to_string())
    pd.set_option("display.width", 220)
    print(t[["desfecho", "periodo", "att_taxa_100mil_mes", "ep", "efeito_relativo_pct",
             "efeito_rel_ic_inf_pct", "efeito_rel_ic_sup_pct", "controles_com_peso"]].round(2).to_string())


if __name__ == "__main__":
    main()
