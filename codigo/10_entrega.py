"""Monta a entrega simplificada para download: resultados/entrega_artigo/ e um ZIP.

Estrutura:
  LEIA-ME.txt                 o que é cada arquivo e os números principais
  1_figuras_artigo/           Figuras 1–4 (PNG 300 dpi + PDF vetorial)
  2_figuras_suplementares/    S1–S7
  3_tabelas/                  Resultados_principais.xlsx (abas legíveis) e as tabelas em CSV
  4_metodos/                  plano de análise (com registro de mudanças) e README
  5_dados_agregados/          painel município × mês, exposição, população, série estadual, dicionário
  6_resultados_completos/     saídas brutas dos modelos (para conferência)
Só lê o que as etapas 03–09 gravaram; não refaz cálculo. A pasta é recriada a cada execução.
Uso: python -I codigo/10_entrega.py
"""
from __future__ import annotations

import shutil
import sys
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import (DESFECHOS_CAPS, FIM_ESTUDO, PROCESSADOS, RAIZ, RESULTADOS, ROTULOS,  # noqa: E402
                   ROTULOS_ESTRATO, ROTULOS_MODELO)

ENTREGA = RESULTADOS / "entrega_artigo"
ZIP = RESULTADOS / f"entrega_artigo_enchente_{date.today().isoformat()}.zip"
FIG = RESULTADOS / "figuras"
CF, DR, RB = RESULTADOS / "01_contrafactual", RESULTADOS / "02_dose_resposta", RESULTADOS / "03_robustez"
PERIODOS_CF = ["agudo (mai-jul/24)", "subagudo (ago/24-abr/25)", "tardio (mai/25-mar/26)", "23 meses (mai/24-mar/26)"]
NOMES_PER = {"agudo": "Agudo (mai–jul/2024)", "subagudo": "Subagudo (ago/2024–abr/2025)",
             "tardio": "Tardio (mai/2025–mar/2026)"}
ESPEC = {"principal": "Principal", "sem_porto_alegre": "Sem Porto Alegre", "sem_vale_taquari": "Sem Vale do Taquari",
         "macro_x_ano": "Tendência por macrorregião × ano", "placebo_mai2023": "Data falsa (mai/2023)"}
# Figuras do manuscrito (as 3 usadas no texto) e figuras de trabalho que vão para o suplementar
FIGURAS = {
    "figura1_mapa_exposicao": "Figura1_mapa_exposicao",
    "artigo/Figura2_observado_esperado_internacoes_caps": "Figura2_observado_x_esperado_internacoes_CAPS",
    "artigo/Figura3_estudo_eventos": "Figura3_estudo_de_eventos",
}
FIGURAS_SUPLEMENTARES_EXTRAS = {
    "figura2_observado_esperado_f_total": "S12_observado_esperado_internacoes_por_exposicao",
    "figura3_estudo_eventos": "S13_estudo_eventos_grupos_diagnosticos",
    "figura4_floresta_periodos": "S14_dose_resposta_por_periodo",
    "figura5_caps_estudo_eventos": "S15_estudo_eventos_caps",
}
MANUSCRITO = RAIZ / "manuscrito"


def ic(v, lo, hi, casas=2) -> str:
    f = f"{{:.{casas}f}}"
    return f"{f.format(v)} ({f.format(lo)}–{f.format(hi)})".replace(".", ",")


def ic_a(v, lo, hi, casas=1) -> str:
    """Formato com "a" para intervalos que cruzam o zero: −12,3 (−26,4 a 1,8)."""
    f = lambda x: f"{x:.{casas}f}".replace(".", ",").replace("-", "−")  # noqa: E731
    return f"{f(v)} ({f(lo)} a {f(hi)})"


def ordem_desfecho(s: pd.Series) -> pd.Series:
    return s.map({k: i for i, k in enumerate(ROTULOS)})


# ------------------------------------------------------------------ tabelas legíveis
def t1() -> pd.DataFrame:
    t = pd.read_csv(RESULTADOS / "tabelas" / "tabela1_perfil_internacoes_F.csv", header=[0, 1], index_col=0)
    nomes = {"<1%": "Exposição <1%", "1-<10%": "Exposição 1–<10%", ">=10%": "Exposição ≥10%", "Total": "Total RS"}
    per = {"antes": "antes (mai/22–abr/24)", "depois": f"depois (mai/24–{FIM_ESTUDO:%m/%y})"}
    t.columns = [f"{nomes[a]} — {per[b]}" for a, b in t.columns]
    t.index.name = "Característica (internações com diagnóstico principal F00–F99)"
    decimais = t.index != "Internações (n)"  # nessa linha o ponto já é separador de milhar
    t.loc[decimais] = t.loc[decimais].apply(lambda col: col.astype(str).str.replace(".", ",", regex=False))
    return t


def t2() -> pd.DataFrame:
    r = pd.read_csv(CF / "resumo_periodos.csv")
    r = r[r.modelo == "ensemble"].copy()
    r["Desfecho"] = r.desfecho.map(ROTULOS)
    r["Estrato"] = r.estrato.map(ROTULOS_ESTRATO)
    linhas = []
    for (d, e), g in r.groupby(["desfecho", "estrato"], sort=False):
        lin = {"Desfecho": ROTULOS[d], "Estrato": ROTULOS_ESTRATO[e], "_o": ordem_desfecho(pd.Series([d]))[0],
               "_e": list(ROTULOS_ESTRATO).index(e)}
        for p in PERIODOS_CF:
            x = g[g.periodo == p].iloc[0]
            lin[f"{p} — observado"] = int(round(x.observado))
            lin[f"{p} — esperado"] = int(round(x.esperado))
            lin[f"{p} — O/E (IC 95%)"] = ic(x.razao_oe, x.razao_ic_inf, x.razao_ic_sup)
        linhas.append(lin)
    return pd.DataFrame(linhas).sort_values(["_o", "_e"]).drop(columns=["_o", "_e"])


def _periodo(termo: pd.Series) -> pd.Series:
    return termo.str.extract(r"::(\w+):")[0]


def t3() -> pd.DataFrame:
    c = pd.read_csv(DR / "coef_periodo.csv")
    c = c[(c.especificacao == "principal") & (c.exposicao == "continua_10pp")].copy()
    c["per"] = _periodo(c.termo)
    pre = pd.read_csv(DR / "pretendencia.csv")
    pre = pre[pre.especificacao == "principal"].set_index("desfecho").p_pretendencia
    linhas = []
    for d, g in c.groupby("desfecho"):
        lin = {"Desfecho": ROTULOS.get(d, d), "_o": ordem_desfecho(pd.Series([d]))[0]}
        for p, nome in NOMES_PER.items():
            x = g[g.per == p].iloc[0]
            lin[f"{nome} — RT por 10 p.p. (IC 95%)"] = ic(x.rr, x.rr_ic_inf, x.rr_ic_sup, 3)
            lin[f"{nome} — p"] = round(x.p, 3)
        lin["Teste de pré-tendência — p"] = round(pre.get(d, float("nan")), 3)
        linhas.append(lin)
    return pd.DataFrame(linhas).sort_values("_o").drop(columns="_o")


def t4_categorias() -> pd.DataFrame:
    c = pd.read_csv(DR / "coef_periodo.csv")
    c = c[(c.especificacao == "principal") & (c.exposicao == "categorias")].copy()
    c["per"] = _periodo(c.termo)
    c["cat"] = c.termo.str.extract(r":(e_\w+)$")[0].map({"e_1_10": "1–<10% vs <1%", "e_10": "≥10% vs <1%"})
    linhas = []
    for (d, k), g in c.groupby(["desfecho", "cat"]):
        lin = {"Desfecho": ROTULOS.get(d, d), "Comparação": k, "_o": ordem_desfecho(pd.Series([d]))[0]}
        for p, nome in NOMES_PER.items():
            x = g[g.per == p].iloc[0]
            lin[f"{nome} — RT (IC 95%)"] = ic(x.rr, x.rr_ic_inf, x.rr_ic_sup, 3)
        linhas.append(lin)
    return pd.DataFrame(linhas).sort_values(["_o", "Comparação"]).drop(columns="_o")


def t5_caps() -> pd.DataFrame:
    """Resumo dos CAPS (Emenda 1): observado/esperado, dose-resposta e SDID lado a lado."""
    r = pd.read_csv(CF / "resumo_periodos.csv")
    r = r[(r.modelo == "ensemble")].set_index(["desfecho", "estrato", "periodo"])
    c = pd.read_csv(DR / "coef_periodo.csv")
    c = c[(c.especificacao == "principal") & (c.exposicao == "continua_10pp")].copy()
    c["per"] = _periodo(c.termo)
    c = c.set_index(["desfecho", "per"])
    pre = pd.read_csv(DR / "pretendencia.csv")
    pre = pre[pre.especificacao == "principal"].set_index("desfecho").p_pretendencia
    sd = pd.read_csv(RB / "sdid.csv").set_index(["desfecho", "periodo"])
    caps = [d for d in ROTULOS if d.startswith("caps_") and (d, "agudo") in c.index]
    linhas = []
    for d in caps:
        lin = {"Desfecho": ROTULOS[d]}
        for est, per, nome in [("estado", PERIODOS_CF[0], "O/E estado, agudo"),
                               ("estado", PERIODOS_CF[3], "O/E estado, 23 meses"),
                               (">=10%", PERIODOS_CF[0], "O/E exposição ≥10%, agudo"),
                               (">=10%", PERIODOS_CF[3], "O/E exposição ≥10%, 23 meses")]:
            if (d, est, per) in r.index:
                x = r.loc[(d, est, per)]
                lin[f"{nome} (IC 95%)"] = ic(x.razao_oe, x.razao_ic_inf, x.razao_ic_sup)
        for per, nome in NOMES_PER.items():
            x = c.loc[(d, per)]
            lin[f"RT por 10 p.p., {nome} (IC 95%)"] = ic(x.rr, x.rr_ic_inf, x.rr_ic_sup, 3)
        lin["Pré-tendência — p"] = round(pre.get(d, float("nan")), 3)
        if (d, "todo o pós") in sd.index:
            x = sd.loc[(d, "todo o pós")]
            lin["SDID ≥10% × <1%, todo o pós: efeito % (IC 95%)"] = ic_a(
                x.efeito_relativo_pct, x.efeito_rel_ic_inf_pct, x.efeito_rel_ic_sup_pct)
        linhas.append(lin)
    return pd.DataFrame(linhas).fillna("—")


def s_sensibilidades() -> pd.DataFrame:
    c = pd.read_csv(DR / "coef_periodo.csv")
    c = c[(c.exposicao == "continua_10pp")].copy()
    c["per"] = _periodo(c.termo).replace({"placebo": "placebo (mai/2023–abr/2024)"})
    c["Desfecho"] = c.desfecho.map(ROTULOS)
    c["Especificação"] = c.especificacao.map(ESPEC)
    c["RT por 10 p.p. (IC 95%)"] = c.apply(lambda x: ic(x.rr, x.rr_ic_inf, x.rr_ic_sup, 3), axis=1)
    t = c.pivot_table(index=["desfecho", "Desfecho", "Especificação"], columns="per",
                      values="RT por 10 p.p. (IC 95%)", aggfunc="first").reset_index()
    t["_o"] = ordem_desfecho(t.desfecho)
    cols = [p for p in ["agudo", "subagudo", "tardio", "placebo (mai/2023–abr/2024)"] if p in t.columns]
    t = t.sort_values(["_o", "Especificação"]).rename(columns={k: NOMES_PER.get(k, k) for k in cols})
    return t[["Desfecho", "Especificação"] + [NOMES_PER.get(k, k) for k in cols]].fillna("—")


def s_sdid() -> pd.DataFrame:
    s = pd.read_csv(RB / "sdid.csv")
    return pd.DataFrame({
        "Desfecho": s.desfecho.map(ROTULOS), "Período": s.periodo,
        "Municípios tratados (≥10%)": s.n_tratados, "Municípios controle (<1%)": s.n_controles,
        "Efeito (internações por 100 mil hab./mês)": s.att_taxa_100mil_mes.round(2),
        "Efeito relativo % (IC 95%)": s.apply(lambda x: ic_a(x.efeito_relativo_pct, x.efeito_rel_ic_inf_pct,
                                                              x.efeito_rel_ic_sup_pct), axis=1),
    })


def s_caps_margens() -> pd.DataFrame:
    m = pd.read_csv(RB / "caps_margens_extensiva_intensiva.csv")
    nomes = {"abr_2024": "Abril/2024 (antes da enchente)", **NOMES_PER}
    return pd.DataFrame({
        "Margem": m.margem, "Período": m.termo.map(nomes).fillna(m.termo),
        "Estimativa (IC 95%)": m.apply(lambda x: ic_a(x.estimativa * (100 if x.margem.startswith("extensiva") else 1),
                                                      x.ic_inf * (100 if x.margem.startswith("extensiva") else 1),
                                                      x.ic_sup * (100 if x.margem.startswith("extensiva") else 1),
                                                      1 if x.margem.startswith("extensiva") else 3), axis=1),
        "p": m.p.round(3), "CAPS": m.caps, "Observações (CAPS-mês)": m.n_obs,
        "Unidade": m.margem.map(lambda t: "pontos percentuais por 10 p.p." if t.startswith("extensiva")
                                else "razão de taxas por 10 p.p."),
    })


def s_desigualdades() -> pd.DataFrame:
    t = pd.read_csv(RESULTADOS / "04_desigualdades" / "desigualdades_rt.csv")
    return pd.DataFrame({
        "Dimensão": t.dimensao, "Desfecho": t.desfecho, "Período": t.periodo.map(NOMES_PER),
        "Grupo de referência": t.grupo_ref,
        "RT por 10 p.p. (referência)": t.apply(lambda x: ic(x.rt_ref, x.rt_ref_inf, x.rt_ref_sup, 3), axis=1),
        "Grupo de comparação": t.grupo_comp,
        "RT por 10 p.p. (comparação)": t.apply(lambda x: ic(x.rt_comp, x.rt_comp_inf, x.rt_comp_sup, 3), axis=1),
        "Razão entre as RTs (IC 95%)": t.apply(lambda x: ic(x.razao_rt, x.razao_inf, x.razao_sup, 3), axis=1),
        "p da diferença": t.p_diferenca.round(3),
    })


def s_validacao() -> pd.DataFrame:
    v = pd.read_csv(CF / "validacao_placebo.csv")
    g = v.groupby(["desfecho", "estrato", "modelo"]).agg(
        erro=("erro_pct_12m", "mean"), cobre=("cobre_12m", "mean"),
        mae=("erro_abs_medio_mensal_pct", "mean"), cob=("cobertura_mensal", "mean"), n=("corte_placebo", "count")
    ).reset_index()
    g["_o"], g["_e"] = ordem_desfecho(g.desfecho), g.estrato.map({k: i for i, k in enumerate(ROTULOS_ESTRATO)})
    g = g.sort_values(["_o", "_e", "modelo"])
    return pd.DataFrame({
        "Desfecho": g.desfecho.map(ROTULOS), "Estrato": g.estrato.map(ROTULOS_ESTRATO),
        "Modelo": g.modelo.map(ROTULOS_MODELO), "Cortes-placebo": g.n,
        "Erro médio do total de 12 meses (%)": g.erro.round(1),
        "Proporção de placebos com total de 12 meses dentro do IC 95%": g.cobre.round(2),
        "Erro absoluto médio mensal (%)": g.mae.round(1),
        "Cobertura mensal do IC 95%": g.cob.round(2),
    })


def s_modelos() -> pd.DataFrame:
    r = pd.read_csv(CF / "resumo_periodos.csv")
    r["_o"], r["_e"] = ordem_desfecho(r.desfecho), r.estrato.map({k: i for i, k in enumerate(ROTULOS_ESTRATO)})
    r = r.sort_values(["_o", "_e", "periodo", "modelo"])
    return pd.DataFrame({
        "Desfecho": r.desfecho.map(ROTULOS), "Estrato": r.estrato.map(ROTULOS_ESTRATO), "Período": r.periodo,
        "Modelo": r.modelo.map(ROTULOS_MODELO), "Observado": r.observado.round(0).astype(int),
        "Esperado": r.esperado.round(0).astype(int),
        "O/E (IC 95%)": r.apply(lambda x: ic(x.razao_oe, x.razao_ic_inf, x.razao_ic_sup), axis=1),
        "Excesso (observado − esperado)": r.excesso.round(0).astype(int),
    })


def s_exposicao() -> pd.DataFrame:
    e = pd.read_csv(PROCESSADOS / "exposicao_municipio.csv")
    t = pd.read_csv(PROCESSADOS / "territorio_municipios.csv")[["mun_res", "regiao_imediata", "regiao_intermediaria"]]
    e = e.merge(t, on="mun_res", how="left").sort_values("pct_pop_afetada", ascending=False)
    return pd.DataFrame({
        "Código IBGE (6 dígitos, como no SIH)": e.mun_res, "Município": e.nome,
        "Região geográfica imediata": e.regiao_imediata, "Região geográfica intermediária": e.regiao_intermediaria,
        "População Censo 2022": e.pop_censo2022, "Pessoas na área afetada": e.pop_afetada.astype(int),
        "% da população na área afetada": e.pct_pop_afetada.round(2),
        "Estabelecimentos de saúde na área afetada": e.estab_saude_afetados.astype(int),
        "Categoria de exposição": e.exposicao_cat.map({"<1%": "<1%", "1-<10%": "1–<10%", ">=10%": "≥10%"}),
    })


ABAS = {
    "Leia-me": None,
    "T1 Perfil": (t1, "Perfil das internações psiquiátricas, 24 meses antes × depois da enchente, por exposição"),
    "T2 Observado x esperado": (t2, "Análise 1: observado e esperado sem a enchente (média dos 3 modelos), por período"),
    "T3 Dose-resposta": (t3, "Análise 2: razão de taxas por 10 p.p. da população em área afetada (Poisson, EF município e mês)"),
    "T4 Categorias": (t4_categorias, "Análise 2: razão de taxas por categoria de exposição (referência <1%)"),
    "T5 CAPS": (t5_caps, "CAPS (RAAS psicossocial, Emenda 1): observado/esperado, dose-resposta e SDID"),
    "S1 Sensibilidades": (s_sensibilidades, "Análise 2 sob especificações alternativas e data falsa (mai/2023)"),
    "S2 SDID": (s_sdid, "Robustez: synthetic difference-in-differences, municípios ≥10% × <1%"),
    "S3 Validação": (s_validacao, "Validação dos modelos de previsão em 4 cortes-placebo (12 meses)"),
    "S4 Modelos": (s_modelos, "Análise 1 por modelo (quase-Poisson, SARIMA, LightGBM e média)"),
    "S5 Exposição": (s_exposicao, "Exposição por município (IBGE, mancha v3 INPE/ANA × Censo 2022)"),
    "S6 CAPS margens": (s_caps_margens, "CAPS por estabelecimento: margem extensiva (mês sem registro) e intensiva "
                                        "(usuários por CAPS com registro), por 10 p.p. de exposição do município do CAPS"),
    "S7 Desigualdades": (s_desigualdades, "Efeito por sexo e raça/cor: RT por 10 p.p. em cada grupo e razão entre as RTs "
                                          "(raça/cor só de 07/2023 em diante, pela completude do registro)"),
}


def excel(destino: Path) -> dict[str, pd.DataFrame]:
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    tabelas = {nome: fn() for nome, (fn, _) in ((k, v) for k, v in ABAS.items() if v)}
    leia = pd.DataFrame({"Aba": list(tabelas), "Conteúdo": [ABAS[k][1] for k in tabelas]})
    with pd.ExcelWriter(destino, engine="openpyxl") as w:
        leia.to_excel(w, sheet_name="Leia-me", index=False)
        for nome, df in tabelas.items():
            df.to_excel(w, sheet_name=nome, index=(nome == "T1 Perfil"))
        for ws in w.book.worksheets:
            ws.freeze_panes = "B2" if ws.title == "T1 Perfil" else "A2"
            for cel in ws[1]:
                cel.font = Font(bold=True, color="FFFFFF")
                cel.fill = PatternFill("solid", fgColor="2A78D6")
                cel.alignment = Alignment(wrap_text=True, vertical="top")
            ws.row_dimensions[1].height = 48
            for i, col in enumerate(ws.columns, start=1):
                largura = max(len(str(c.value)) if c.value is not None else 0 for c in list(col)[1:] or [col[0]])
                ws.column_dimensions[get_column_letter(i)].width = min(max(12, largura + 2), 60)
    return tabelas


# ------------------------------------------------------------------ LEIA-ME
def numeros_principais() -> list[str]:
    r = pd.read_csv(CF / "resumo_periodos.csv")
    e = r[r.modelo == "ensemble"].set_index(["desfecho", "estrato", "periodo"])

    def oe(d, s, p):
        x = e.loc[(d, s, p)]
        return ic(x.razao_oe, x.razao_ic_inf, x.razao_ic_sup)

    c = pd.read_csv(DR / "coef_periodo.csv")
    c = c[(c.especificacao == "principal") & (c.exposicao == "continua_10pp")].copy()
    c["per"] = _periodo(c.termo)
    c = c.set_index(["desfecho", "per"])

    def rt(d, p):
        x = c.loc[(d, p)]
        return ic(x.rr, x.rr_ic_inf, x.rr_ic_sup)

    sd = pd.read_csv(RB / "sdid.csv").set_index(["desfecho", "periodo"])

    def sdid(d, p):
        x = sd.loc[(d, p)]
        pc = lambda v: f"{v:.0f}%".replace("-", "−")  # noqa: E731
        return f"{pc(x.efeito_relativo_pct)} (IC 95% {pc(x.efeito_rel_ic_inf_pct)} a {pc(x.efeito_rel_ic_sup_pct)})"

    pre = pd.read_csv(DR / "pretendencia.csv")
    pre = pre[pre.especificacao == "principal"].set_index("desfecho").p_pretendencia
    a, t = PERIODOS_CF[0], PERIODOS_CF[3]
    caps = []
    if ("caps_usuarios", "agudo") in c.index:
        caps = [
            "Atenção psicossocial nos CAPS (RAAS; Emenda 1 do plano):",
            f"   usuários atendidos, municípios com ≥10% atingido, O/E: agudo {oe('caps_usuarios', '>=10%', a)};"
            f"  23 meses {oe('caps_usuarios', '>=10%', t)}",
            f"   usuários atendidos, razão de taxas por 10 p.p.: agudo {rt('caps_usuarios', 'agudo')};"
            f"  tardio {rt('caps_usuarios', 'tardio')}",
            f"   usuários atendidos, synthetic DiD no agudo: {sdid('caps_usuarios', 'agudo')}",
            f"   usuários com CID F40–F48, O/E no agudo: ≥10% {oe('caps_usuarios_estresse', '>=10%', a)};"
            f"  <1% {oe('caps_usuarios_estresse', '<1%', a)}",
        ]
        if (RB / "caps_margens_extensiva_intensiva.csv").exists():
            mg = pd.read_csv(RB / "caps_margens_extensiva_intensiva.csv").set_index(["margem", "termo"])
            ki = [k for k in mg.index.get_level_values(0).unique() if k.startswith("intensiva")][0]
            ke = [k for k in mg.index.get_level_values(0).unique() if k.startswith("extensiva")][0]
            f = lambda k, t, esc, cs: ic_a(mg.loc[(k, t)].estimativa * esc, mg.loc[(k, t)].ic_inf * esc,  # noqa: E731
                                           mg.loc[(k, t)].ic_sup * esc, cs)
            dg = RESULTADOS / "04_desigualdades" / "desigualdades_rt.csv"
            if dg.exists():
                tg = pd.read_csv(dg)
                pmin = tg[~tg.dimensao.str.contains("out/2023")].p_diferenca.min()
                caps += [f"   sexo e raça/cor: razão entre as RTs dos grupos próxima de 1 em todos os períodos "
                         f"(menor p = {pmin:.2f})".replace("0.", "0,")]
            caps += [
                "   CAPS em funcionamento (por estabelecimento, por 10 p.p. de exposição do município do CAPS):",
                f"      usuários por CAPS com registro (RT): agudo {ic(mg.loc[(ki, 'agudo')].estimativa, mg.loc[(ki, 'agudo')].ic_inf, mg.loc[(ki, 'agudo')].ic_sup)};"
                f" tardio {ic(mg.loc[(ki, 'tardio')].estimativa, mg.loc[(ki, 'tardio')].ic_inf, mg.loc[(ki, 'tardio')].ic_sup)}",
                f"      chance de mês sem registro (+ p.p.): agudo {f(ke, 'agudo', 100, 1)}; tardio {f(ke, 'tardio', 100, 1)}",
            ]
    return [
        "Internações psiquiátricas (F00–F99), estado, observado/esperado sem a enchente (IC 95%):",
        f"   período agudo (mai–jul/2024): {oe('f_total', 'estado', a)};  23 meses: {oe('f_total', 'estado', t)}",
        "Razão de taxas por 10 p.p. da população em área afetada (dose-resposta, F00–F99):",
        f"   agudo {rt('f_total', 'agudo')};  subagudo {rt('f_total', 'subagudo')};  tardio {rt('f_total', 'tardio')}",
        f"   (teste de pré-tendência p = {pre['f_total']:.2f}; data falsa mai/2023 dá valor parecido → sem efeito no total)"
        .replace("0.", "0,"),
        "Mudança de perfil nos municípios com ≥10% da população atingida:",
        f"   esquizofrenia e psicóticos, O/E no agudo: {oe('f_psicoticos', '>=10%', a)}",
        f"   álcool e outras drogas, synthetic DiD no agudo: {sdid('f_spa', 'agudo')}",
        "Ruptura do atendimento hospitalar geral (controles):",
        f"   partos, razão de taxas por 10 p.p. no agudo: {rt('ctrl_parto', 'agudo')}",
        f"   demais causas, razão de taxas por 10 p.p. no tardio: {rt('nao_f', 'tardio')}",
    ] + caps


def leia_me(destino: Path) -> None:
    linhas = [
        "ENCHENTE DE 2024 E INTERNAÇÕES PSIQUIÁTRICAS NO SUS — RIO GRANDE DO SUL",
        f"Entrega gerada em {date.today():%d/%m/%Y} por codigo/10_entrega.py (refazer: rodar.py --etapas 10).",
        "",
        "COMO USAR",
        "  7_manuscrito/              Manuscrito_anonimo.docx (para a revista), Material_suplementar.docx (métodos",
        "                             detalhados, busca de literatura, Tabelas S1–S5, Figuras S1–S15) e Folha_de_rosto.docx",
        "                             (5 autores com ORCID e afiliações; falta preencher contribuições, financiamento,",
        "                             conflitos e endereço do autor correspondente). 5 ilustrações no meio do texto, logo",
        "                             após a 1ª citação: Tabelas 1–2 e Figuras 1–3. Trechos [INSERIR: ...] em amarelo,",
        "                             se houver, são pendências dos autores. Links anonimizados do repositório (/r/) e",
        "                             do painel (/w/) já estão no texto; painel: docs/ no repositório público.",
        "  1_figuras_artigo/          As Figuras 1–3 do manuscrito. PNG (300 dpi) e PDF vetorial para a revista.",
        "  2_figuras_suplementares/   S1–S5, S8–S9 e S12: observado × esperado; S6, S7, S11, S13 e S15: estudos de",
        "                             eventos; S10: oferta de CAPS; S14: dose-resposta por período (floresta).",
        "  3_tabelas/                 Resultados_principais.xlsx: uma aba por tabela, com rótulos em português.",
        "                             Abas T1–T5 = candidatas ao manuscrito (T5 = resumo dos CAPS);",
        "                             S1–S7 = material suplementar (S6 = CAPS por estabelecimento; S7 = sexo e raça/cor).",
        "                             CSVs com as mesmas tabelas T1–T5.",
        "  4_metodos/                 Plano de análise (pré-especificado, com registro de mudanças) e README técnico.",
        "  5_dados_agregados/         Dados agregados por município e mês (sem dados individuais) — para o dashboard",
        "                             e para a declaração de Ciência Aberta. Ver dicionario_variaveis.csv.",
        "  6_resultados_completos/    Saídas brutas dos modelos, para conferência.",
        "",
        "NÚMEROS PRINCIPAIS",
        *["  " + x for x in numeros_principais()],
        "",
        "LEITURA E CUIDADOS",
        "  - O volume total de internações psiquiátricas não mudou; mudou o perfil nos municípios mais atingidos",
        "    (mais psicoses, menos álcool e drogas no período agudo), enquanto o atendimento hospitalar geral caiu.",
        "  - Nos CAPS, o número de usuários atendidos caiu fortemente no período agudo onde a enchente foi maior",
        "    e se recuperou só em parte: nem o hospital nem o CAPS absorveram o aumento de sofrimento descrito",
        "    pelas coortes. Os usuários com transtornos relacionados ao estresse (F40–F48) cresceram nos municípios",
        "    menos atingidos e caíram nos mais atingidos. A queda nos CAPS é cerca de 3 vezes a dos partos,",
        "    logo não se explica só pelo deslocamento da população.",
        "  - Abril a junho de 2024: cerca de 1 em cada 5 CAPS ficou sem produção registrada no estado todo,",
        "    inclusive fora da área inundada (falha de registro; em 2022–2023 eram 2–7%). Por isso a queda",
        "    aguda dos CAPS foi decomposta por estabelecimento (aba S6): ela aparece também entre os CAPS que",
        "    registraram (menos usuários por CAPS) e persiste no período tardio, logo não é só falha de registro.",
        "  - Sexo e raça/cor (aba S7): o efeito por unidade de exposição não diferiu entre grupos, mas pessoas",
        "    pretas e pardas eram parcela maior dos usuários dos CAPS e das internações nos municípios mais",
        "    atingidos (19–20% contra 13–14% nos menos atingidos): a desigualdade está na distribuição do dano.",
        "  - CAPS, usuários novos: estimativas imprecisas (erro mensal de 26% na validação) e trimestre de",
        "    referência (fev–abr/2024) atipicamente alto na Figura 5. Atenção à crise e atendimento domiciliar",
        "    já caíam antes da enchente (pré-tendência p < 0,001): não atribuir à enchente.",
        "  - Urgência e internação em outros leitos parecem subir na tabela de dose-resposta, mas o estudo de",
        "    eventos (figura S6) mostra que já subiam antes da enchente: é tendência prévia, não efeito.",
        "  - Recortes com teste de pré-tendência p < 0,05 (coluna na aba T3) devem ser lidos com cautela.",
        "  - Partos e demais causas ficam acima do esperado no período tardio (aba T2): o contrafactual de 2 anos",
        "    tem incerteza crescente; compare sempre com os controles.",
        "  - Dados: SIH/SUS (AIH tipo 1, data de internação, residentes do RS) e SIA/SUS RAAS psicossocial",
        "    (CAPS; mês de atendimento, município de residência), jan/2015–mar/2026.",
        "    Exposição: IBGE, população na mancha de inundação v3 (INPE/ANA), Censo 2022.",
        "  - Dados públicos e agregados, sem identificação: dispensa de CEP (Resolução CNS 510/2016, art. 1º).",
    ]
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")


DICIONARIO = {
    "mun_res": "Código IBGE do município de residência, 6 dígitos (como no SIH)",
    "mes": "Mês da internação (data de internação, não competência)",
    "pop_total": "População estimada (SVS/MS), interpolada mês a mês",
    "pct_pop_afetada": "% da população do município (Censo 2022) residente na área afetada",
    "exposicao_cat": "Categoria de exposição: <1%, 1-<10%, >=10%",
}


def main() -> None:
    if ENTREGA.exists():
        shutil.rmtree(ENTREGA)
    pastas = {k: ENTREGA / k for k in ["1_figuras_artigo", "2_figuras_suplementares", "3_tabelas", "4_metodos",
                                         "5_dados_agregados", "6_resultados_completos", "7_manuscrito"]}
    for p in pastas.values():
        p.mkdir(parents=True)
    for orig, novo in FIGURAS.items():
        for ext in ("png", "pdf"):
            if (FIG / f"{orig}.{ext}").exists():
                shutil.copy2(FIG / f"{orig}.{ext}", pastas["1_figuras_artigo"] / f"{novo}.{ext}")
    for f in sorted((FIG / "suplementares").glob("S*")):
        shutil.copy2(f, pastas["2_figuras_suplementares"] / f.name)
    for orig, novo in FIGURAS_SUPLEMENTARES_EXTRAS.items():
        for ext in ("png", "pdf"):
            if (FIG / f"{orig}.{ext}").exists():
                shutil.copy2(FIG / f"{orig}.{ext}", pastas["2_figuras_suplementares"] / f"{novo}.{ext}")
    for f in ["Manuscrito_anonimo.docx", "Folha_de_rosto.docx", "Material_suplementar.docx"]:
        if (MANUSCRITO / "build" / f).exists():
            shutil.copy2(MANUSCRITO / "build" / f, pastas["7_manuscrito"] / f)
    for f, novo in [("manuscrito.txt", "texto_fonte_manuscrito.txt"), ("suplementar.txt", "texto_fonte_suplementar.txt")]:
        if (MANUSCRITO / f).exists():
            shutil.copy2(MANUSCRITO / f, pastas["7_manuscrito"] / novo)

    tabs = excel(pastas["3_tabelas"] / "Resultados_principais.xlsx")
    for nome, arq in [("T1 Perfil", "T1_perfil_internacoes.csv"), ("T2 Observado x esperado", "T2_observado_esperado.csv"),
                      ("T3 Dose-resposta", "T3_dose_resposta.csv"), ("T4 Categorias", "T4_dose_resposta_categorias.csv"),
                      ("T5 CAPS", "T5_caps_resumo.csv")]:
        tabs[nome].to_csv(pastas["3_tabelas"] / arq, index=(nome == "T1 Perfil"), encoding="utf-8-sig", sep=";",
                          decimal=",")

    shutil.copy2(RAIZ / "PLANO_ANALISE.md", pastas["4_metodos"] / "Plano_de_analise.md")
    shutil.copy2(RAIZ / "README.md", pastas["4_metodos"] / "README_analise.md")

    painel = pd.read_parquet(PROCESSADOS / "painel_municipio_mes.parquet")
    painel.to_csv(pastas["5_dados_agregados"] / "painel_municipio_mes.csv", index=False)
    for f in ["exposicao_municipio.csv", "serie_estado_mes.csv", "populacao_municipio_ano.csv",
              "completude_por_atraso.csv", "territorio_municipios.csv", "completude_caps_por_atraso.csv"]:
        if (PROCESSADOS / f).exists():
            shutil.copy2(PROCESSADOS / f, pastas["5_dados_agregados"] / f)
    for f in ["painel_caps_municipio_mes", "oferta_caps_municipio_mes"]:
        if (PROCESSADOS / f"{f}.parquet").exists():
            pd.read_parquet(PROCESSADOS / f"{f}.parquet").to_csv(pastas["5_dados_agregados"] / f"{f}.csv", index=False)
    dic = [{"variavel": k, "descricao": v} for k, v in DICIONARIO.items()]
    dic += [{"variavel": k, "descricao": f"Número de internações: {v}"} for k, v in ROTULOS.items() if k in painel.columns]
    dic += [{"variavel": k, "descricao": f"{v} (painel_caps_municipio_mes.csv; usuários = RAAS, procedimentos = PA_QTDPRO)"}
            for k, v in ROTULOS.items() if k.startswith("caps_")]
    dic += [{"variavel": "mun_local", "descricao": "Município onde o CAPS fica (oferta_caps_municipio_mes.csv)"},
            {"variavel": "caps_ativos", "descricao": "Número de CAPS com produção RAAS no mês (oferta)"}]
    pd.DataFrame(dic).to_csv(pastas["5_dados_agregados"] / "dicionario_variaveis.csv", index=False, encoding="utf-8-sig")

    for sub in (CF, DR, RB, RESULTADOS / "04_desigualdades"):
        destino = pastas["6_resultados_completos"] / sub.name
        destino.mkdir()
        for f in sub.glob("*.csv"):
            shutil.copy2(f, destino / f.name)

    leia_me(ENTREGA / "LEIA-ME.txt")
    for z in RESULTADOS.glob("entrega_artigo_enchente_*.zip"):
        z.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(ENTREGA.rglob("*")):
            if f.is_file():
                z.write(f, Path("entrega_artigo_enchente") / f.relative_to(ENTREGA))
    n = sum(1 for f in ENTREGA.rglob("*") if f.is_file())
    print(f"{n} arquivos em {ENTREGA}")
    print(f"ZIP: {ZIP} ({ZIP.stat().st_size / 1e6:.1f} MB)")
    print((ENTREGA / "LEIA-ME.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
