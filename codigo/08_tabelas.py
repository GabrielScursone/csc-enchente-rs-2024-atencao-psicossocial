"""Tabelas do artigo e planilha única com todos os resultados.

Tabela 1  perfil das internações F00–F99: 24 meses antes (05/2022–04/2024) × depois
          (05/2024–03/2026), por categoria de exposição.
Tabela 2  razões observado/esperado (ensemble) e razões de taxas por 10 p.p., por período.
Saídas em resultados/tabelas/ (CSV) e resultados/resultados_enchente_sihsus_rs.xlsx.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import FIM_ESTUDO, GRUPOS_F, INICIO_ENCHENTE, PROCESSADOS, RESULTADOS, entre  # noqa: E402

SAIDA = RESULTADOS / "tabelas"
ANTES = (pd.Timestamp("2022-05-01"), INICIO_ENCHENTE - pd.Timedelta(days=1))
DEPOIS = (INICIO_ENCHENTE, FIM_ESTUDO)
NOMES_F = {"f_organicos": "F00–F09 orgânicos", "f_spa": "F10–F19 álcool e outras drogas",
           "f_psicoticos": "F20–F29 esquizofrenia e psicóticos", "f_humor": "F30–F39 humor",
           "f_neuroticos": "F40–F48 neuróticos e relacionados ao estresse"}


def pct(s: pd.Series) -> str:
    return f"{100 * s.mean():.1f}"


def perfil(d: pd.DataFrame, pessoa_anos: float) -> dict:
    cid3 = d.cid3.astype(str)
    lin = {
        "Internações (n)": f"{len(d):,}".replace(",", "."),
        "Taxa por 100 mil hab./ano": f"{1e5 * len(d) / pessoa_anos:.1f}",
        "Mulheres (%)": pct(d.sexo == "F"),
        "Idade, mediana (IIQ)": f"{d.idade.median():.0f} ({d.idade.quantile(.25):.0f}–{d.idade.quantile(.75):.0f})",
        "0–17 anos (%)": pct(d.idade < 18), "18–39 anos (%)": pct(d.idade.between(18, 39)),
        "40–59 anos (%)": pct(d.idade.between(40, 59)), "60+ anos (%)": pct(d.idade >= 60),
        "Branca (%)": pct(d.raca == "branca"), "Preta ou parda (%)": pct(d.raca.isin(["preta", "parda"])),
        "Indígena (%)": pct(d.raca == "indigena"), "Raça/cor ignorada (%)": pct(d.raca == "ignorada"),
    }
    for k, nome in NOMES_F.items():
        lin[f"{nome} (%)"] = pct(entre(cid3, GRUPOS_F[k]))
    lin |= {
        "Leito psiquiátrico (%)": pct(d.espec == "05"),
        "Leito de saúde mental em hospital geral (%)": pct(d.espec == "87"),
        "Caráter de urgência (%)": pct(d.car_int != "01"),
        "Internação fora do município de residência (%)": pct((d.mun_mov != d.mun_res).fillna(False)),
        "Permanência em dias, mediana (IIQ)": f"{d.dias_perm.median():.0f} ({d.dias_perm.quantile(.25):.0f}–{d.dias_perm.quantile(.75):.0f})",
        "Óbito hospitalar (%)": f"{100 * d.morte.mean():.2f}",
    }
    return lin


def tabela1() -> pd.DataFrame:
    b = pd.read_parquet(PROCESSADOS / "internacoes_rs_aih.parquet")
    b = b[b.cid3.astype(str).str.match(r"^F\d\d$")]
    exp = pd.read_csv(PROCESSADOS / "exposicao_municipio.csv")[["mun_res", "exposicao_cat"]]
    b = b.merge(exp, on="mun_res", how="left")
    pop = pd.read_parquet(PROCESSADOS / "populacao_municipio_mes.parquet", columns=["mun_res", "mes", "pop_total"])
    pop = pop.merge(exp, on="mun_res")
    cols = {}
    for cat in ["<1%", "1-<10%", ">=10%", "Total"]:
        for nome, (a, z) in [("antes", ANTES), ("depois", DEPOIS)]:
            sel = b.dt_inter.between(a, z) & ((b.exposicao_cat == cat) if cat != "Total" else True)
            ps = pop[pop.mes.between(a, z) & ((pop.exposicao_cat == cat) if cat != "Total" else True)]
            cols[(cat, nome)] = perfil(b[sel], ps.pop_total.sum() / 12)
    t = pd.DataFrame(cols)
    t.columns = pd.MultiIndex.from_tuples(t.columns, names=["exposição", "período"])
    return t


def tabela2() -> tuple[pd.DataFrame, pd.DataFrame]:
    cf = pd.read_csv(RESULTADOS / "01_contrafactual" / "resumo_periodos.csv")
    cf = cf[cf.modelo == "ensemble"]
    cf["O/E (IC 95%)"] = cf.apply(lambda r: f"{r.razao_oe:.2f} ({r.razao_ic_inf:.2f}–{r.razao_ic_sup:.2f})", axis=1)
    a = cf.pivot_table(index=["desfecho", "estrato"], columns="periodo", values="O/E (IC 95%)", aggfunc="first")
    dr = pd.read_csv(RESULTADOS / "02_dose_resposta" / "coef_periodo.csv")
    dr = dr[(dr.especificacao == "principal") & (dr.exposicao == "continua_10pp")].copy()
    dr["periodo"] = dr.termo.str.extract(r"periodo::(\w+):")
    dr["RT por 10 p.p. (IC 95%)"] = dr.apply(lambda r: f"{r.rr:.3f} ({r.rr_ic_inf:.3f}–{r.rr_ic_sup:.3f})", axis=1)
    b = dr.pivot_table(index="desfecho", columns="periodo", values="RT por 10 p.p. (IC 95%)", aggfunc="first")
    return a, b


def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    t1 = tabela1()
    t1.to_csv(SAIDA / "tabela1_perfil_internacoes_F.csv")
    print(t1.to_string())
    folhas = {"Tabela1_perfil": t1}
    try:
        oe, rt = tabela2()
        oe.to_csv(SAIDA / "tabela2a_observado_esperado.csv")
        rt.to_csv(SAIDA / "tabela2b_razao_taxas_10pp.csv")
        folhas |= {"Tabela2a_O_E": oe, "Tabela2b_RT_10pp": rt}
    except FileNotFoundError as e:
        print("tabela 2 pulada:", e)
    extras = {
        "contrafactual_periodos": RESULTADOS / "01_contrafactual" / "resumo_periodos.csv",
        "contrafactual_validacao": RESULTADOS / "01_contrafactual" / "validacao_placebo.csv",
        "contrafactual_mensal": RESULTADOS / "01_contrafactual" / "esperado_mensal.csv",
        "dose_resposta_periodo": RESULTADOS / "02_dose_resposta" / "coef_periodo.csv",
        "dose_resposta_evento": RESULTADOS / "02_dose_resposta" / "coef_evento.csv",
        "pretendencia": RESULTADOS / "02_dose_resposta" / "pretendencia.csv",
        "exposicao_municipios": PROCESSADOS / "exposicao_municipio.csv",
        "completude_atraso": PROCESSADOS / "completude_por_atraso.csv",
    }
    for nome, p in extras.items():
        if p.exists():
            folhas[nome] = pd.read_csv(p)
    with pd.ExcelWriter(RESULTADOS / "resultados_enchente_sihsus_rs.xlsx") as w:
        for nome, df in folhas.items():
            df.to_excel(w, sheet_name=nome[:31])
    print("planilha:", RESULTADOS / "resultados_enchente_sihsus_rs.xlsx")


if __name__ == "__main__":
    main()
