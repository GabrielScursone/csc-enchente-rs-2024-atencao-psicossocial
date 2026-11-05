"""Figuras do artigo (PNG 300 dpi + PDF vetorial) a partir das saídas de 04, 05 e 06.

Figura 1  mapa da exposição (% da população em área afetada)
Figura 2  observado × esperado (ensemble), estado e estratos de exposição
Figura 3  estudo de eventos: razão de taxas por 10 p.p. de exposição, por trimestre
Figura 4  razão de taxas por 10 p.p. por período, desfechos e grupos
Cores: paleta de referência validada (skill dataviz) — categórica azul/laranja; rampa azul
sequencial para a exposição.
Uso: python -I codigo/07_figuras.py [--so 1,2]
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402
from matplotlib.collections import PatchCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Polygon  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import BRUTOS, INICIO_ENCHENTE, INTERMED, PROCESSADOS, RESULTADOS, ROTULOS  # noqa: E402

SAIDA = RESULTADOS / "figuras"
TXT1, TXT2, GRADE, FUNDO = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
AZUL, LARANJA = "#2a78d6", "#eb6834"
RAMPA5 = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
RAMPA3 = ["#86b6ef", "#2a78d6", "#104281"]
NOMES_ESTRATO = {"estado": "Rio Grande do Sul", "<1%": "Exposição <1%",
                 "1-<10%": "Exposição 1–<10%", ">=10%": "Exposição ≥10%"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRADE, "axes.linewidth": 0.8,
    "axes.labelcolor": TXT2, "xtick.color": TXT2, "ytick.color": TXT2, "axes.titlesize": 10,
    "axes.titleweight": "bold", "axes.titlecolor": TXT1, "axes.grid": True, "grid.color": GRADE,
    "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": "white", "axes.facecolor": "white", "lines.linewidth": 1.6,
    "legend.frameon": False,
})


def eixo_razao(ax, eixo: str = "y", marcas_possiveis=(0.25, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 3.0)) -> None:
    """Escala log com marcas legíveis e vírgula decimal (0,90 · 1,00 · 1,10)."""
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    getattr(ax, f"set_{eixo}scale")("log")
    a = getattr(ax, f"{eixo}axis")
    lo, hi = getattr(ax, f"get_{eixo}lim")()
    if hi / lo > 2.2:  # escala larga: marcas mais espaçadas para não colarem
        marcas_possiveis = tuple(m for m in marcas_possiveis if m in (0.25, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0)) or (1.0,)
    elif hi / lo < 1.3:  # escala curta: marcas a cada 0,05
        marcas_possiveis = (0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2)
    marcas = [m for m in marcas_possiveis if lo <= m <= hi] or [1.0]
    a.set_major_locator(FixedLocator(marcas))
    a.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.2f}".replace(".", ",")))
    a.set_minor_locator(NullLocator())


def salvar(fig, nome: str, pasta: Path | None = None) -> None:
    pasta = pasta or SAIDA
    pasta.mkdir(parents=True, exist_ok=True)
    fig.savefig(pasta / f"{nome}.png", dpi=300, bbox_inches="tight")
    fig.savefig(pasta / f"{nome}.pdf", bbox_inches="tight")
    plt.close(fig)
    print("figura:", nome)


# ------------------------------------------------------------------ Figura 1
def figura_mapa() -> None:
    import shapefile  # pyshp

    exp = pd.read_csv(PROCESSADOS / "exposicao_municipio.csv").set_index("mun_res")
    zp = BRUTOS / "malha_ibge_2022" / "RS_Municipios_2022.zip"
    tmp = INTERMED / "malha_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zp) as zf:
        zf.extractall(tmp)
    sf = shapefile.Reader(str(tmp / "RS_Municipios_2022.shp"), encoding="utf-8")
    cortes = [1, 5, 10, 25]
    rotulos = ["<1%", "1–<5%", "5–<10%", "10–<25%", "≥25%"]
    patches, cores = [], []
    for sr in sf.iterShapeRecords():
        cod = int(sr.record["CD_MUN"]) // 10
        if cod not in exp.index:  # Lagoa Mirim e Lagoa dos Patos
            cor = "#ffffff"
        else:
            cor = RAMPA5[int(np.searchsorted(cortes, exp.loc[cod, "pct_pop_afetada"], side="right"))]
        pts = np.asarray(sr.shape.points)
        partes = list(sr.shape.parts) + [len(pts)]
        for i in range(len(partes) - 1):
            patches.append(Polygon(pts[partes[i]:partes[i + 1]], closed=True))
            cores.append(cor)
    fig, ax = plt.subplots(figsize=(6.3, 5.6))
    ax.add_collection(PatchCollection(patches, facecolor=cores, edgecolor="#ffffff", linewidth=0.25))
    ax.autoscale_view()
    ax.set_aspect(1 / np.cos(np.deg2rad(30)))
    ax.axis("off")
    n = np.bincount(np.searchsorted(cortes, exp.pct_pop_afetada, side="right"), minlength=5)
    ax.legend([Patch(facecolor=c, edgecolor="#9a9994", linewidth=0.4) for c in RAMPA5],
              [f"{r} ({k} municípios)" for r, k in zip(rotulos, n)], loc="lower left",
              title="População em área afetada", title_fontsize=8.5, fontsize=8)
    salvar(fig, "figura1_mapa_exposicao")


# ------------------------------------------------------------------ Figura 2
def figura_observado_esperado(desfecho: str = "f_total", nome: str | None = None, titulo: str | None = None,
                              pasta: Path | None = None, rotulo_y: str = "Internações por 100 mil hab.") -> None:
    m = pd.read_csv(RESULTADOS / "01_contrafactual" / "esperado_mensal.csv", parse_dates=["mes"])
    m = m[(m.desfecho == desfecho) & (m.modelo == "ensemble")]
    arq = "painel_caps_municipio_mes.parquet" if desfecho.startswith("caps_") else "painel_municipio_mes.parquet"
    serie = pd.read_parquet(PROCESSADOS / arq, columns=["mun_res", "mes", desfecho])
    exp = pd.read_csv(PROCESSADOS / "exposicao_municipio.csv")[["mun_res", "exposicao_cat"]]
    pop = pd.read_parquet(PROCESSADOS / "populacao_municipio_mes.parquet", columns=["mun_res", "mes", "pop_total"])
    s = serie.merge(pop, on=["mun_res", "mes"]).merge(exp, on="mun_res")
    inicio = pd.Timestamp("2022-01-01")
    fig, axs = plt.subplots(2, 2, figsize=(7.2, 5.4), sharex=True)
    for ax, e in zip(axs.ravel(), NOMES_ESTRATO):
        d = s if e == "estado" else s[s.exposicao_cat == e]
        o = d[d.mes >= inicio].groupby("mes")[[desfecho, "pop_total"]].sum()
        taxa = 1e5 * o[desfecho] / o.pop_total
        f = m[m.estrato == e].set_index("mes")
        k = 1e5 / f["pop"]
        ax.fill_between(f.index, f.ic_inf * k, f.ic_sup * k, color=LARANJA, alpha=0.18, linewidth=0)
        ax.plot(f.index, f.esperado * k, color=LARANJA, linewidth=1.6)
        ax.plot(taxa.index, taxa.values, color=AZUL, linewidth=1.6)
        ax.axvline(INICIO_ENCHENTE, color=TXT2, linewidth=0.8)
        ax.set_title(NOMES_ESTRATO[e], loc="left")
        ax.grid(axis="x", visible=False)
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        lo, hi = min(taxa.min(), (f.ic_inf * k).min()), max(taxa.max(), (f.ic_sup * k).max())
        ax.set_ylim(lo - 0.15 * (hi - lo), hi + 0.25 * (hi - lo))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",")))
        if e == "estado":
            ax.text(INICIO_ENCHENTE, ax.get_ylim()[1], " maio/2024", va="top", ha="left",
                    color=TXT2, fontsize=7.5)
            ax.legend([Line2D([], [], color=AZUL, linewidth=1.6),
                       (Patch(facecolor=LARANJA, alpha=0.18, linewidth=0),
                        Line2D([], [], color=LARANJA, linewidth=1.6))],
                      ["Observado", "Esperado sem a enchente (IC 95%)"], loc="lower left", fontsize=7.5)
    for ax in axs[:, 0]:
        ax.set_ylabel(rotulo_y)
    if titulo:
        fig.suptitle(titulo, x=0.01, ha="left", fontsize=10.5, fontweight="bold", color=TXT1)
    fig.tight_layout()
    salvar(fig, nome or f"figura2_observado_esperado_{desfecho}", pasta)


# ------------------------------------------------------------------ Figura 3
def figura_evento(desfechos=("f_total", "f_spa", "f_humor", "ctrl_parto"), nome: str = "figura3_estudo_eventos",
                  pasta: Path | None = None, mesmo_y: bool = True, titulos: dict | None = None) -> None:
    rot = {**ROTULOS, **(titulos or {})}
    c = pd.read_csv(RESULTADOS / "02_dose_resposta" / "coef_evento.csv")
    c = c[(c.especificacao == "principal") & (c.exposicao == "continua_10pp")]
    c["k"] = c.termo.str.extract(r"k::(-?\d+)").astype(int)
    fig, axs = plt.subplots(2, 2, figsize=(7.2, 5.0), sharex=True, sharey=mesmo_y)
    for ax, y in zip(axs.ravel(), desfechos):
        d = pd.concat([c[c.desfecho == y], pd.DataFrame({"k": [-1], "rr": [1.0], "rr_ic_inf": [1.0],
                                                        "rr_ic_sup": [1.0]})]).sort_values("k")
        d = d[d.k >= -8]
        ax.axhline(1, color=TXT2, linewidth=0.8)
        ax.axvline(-0.5, color=GRADE, linewidth=0.8)
        ax.vlines(d.k, d.rr_ic_inf, d.rr_ic_sup, color=AZUL, linewidth=1.6)
        ax.plot(d.k, d.rr, "o", color=AZUL, markersize=4.5, markeredgecolor="white", markeredgewidth=1)
        ax.set_title(rot.get(y, y), loc="left", fontsize=9)
        ax.set_xticks(range(-8, 8, 2))
        ax.grid(axis="x", visible=False)
    for ax in axs.ravel():
        ax.set_yscale("log")
    for ax in axs.ravel():
        eixo_razao(ax, "y")
    for ax in axs[:, 0]:
        ax.set_ylabel("Razão de taxas por 10 p.p.")
    fig.supxlabel("Trimestres desde maio/2024 (referência: fev–abr/2024)", fontsize=9, color=TXT2)
    fig.tight_layout()
    salvar(fig, nome, pasta)


# ------------------------------------------------------------------ Figura 4
def figura_floresta() -> None:
    rot = {
        "f_total": "Total F00–F99", "f_spa": "F10–F19 álcool e drogas", "f_alcool": "F10 álcool",
        "f_humor": "F30–F39 humor", "f_neuroticos": "F40–F48 neuróticos/estresse",
        "f_psicoticos": "F20–F29 psicóticos", "f_masc": "Homens", "f_fem": "Mulheres",
        "f_0_17": "0–17 anos", "f_18_39": "18–39 anos", "f_40_59": "40–59 anos", "f_60m": "60+ anos",
        "f_branca": "Branca", "f_negra": "Preta ou parda", "f_leito_psiq": "Leito psiquiátrico",
        "f_leito_sm_hg": "Saúde mental em hospital geral", "f_fora_mun": "Fora do município",
        "ctrl_parto": "Partos (controle)", "ctrl_apendicite": "Apendicite (controle)",
        "nao_f": "Demais causas (controle)",
    }
    c = pd.read_csv(RESULTADOS / "02_dose_resposta" / "coef_periodo.csv")
    c = c[(c.especificacao == "principal") & (c.exposicao == "continua_10pp") & c.desfecho.isin(rot)]
    c["periodo"] = c.termo.str.extract(r"periodo::(\w+):")
    ordem = [k for k in rot if k in set(c.desfecho)]
    periodos = [("agudo", "Agudo\nmai–jul/2024"), ("subagudo", "Subagudo\nago/2024–abr/2025"),
                ("tardio", "Tardio\nmai/2025–mar/2026")]
    fig, axs = plt.subplots(1, 3, figsize=(7.2, 0.28 * len(ordem) + 1.2), sharey=True, sharex=True)
    y = np.arange(len(ordem))[::-1]
    for ax, (p, titulo) in zip(axs, periodos):
        d = c[c.periodo == p].set_index("desfecho").reindex(ordem)
        ax.axvline(1, color=TXT2, linewidth=0.8)
        ax.hlines(y, d.rr_ic_inf, d.rr_ic_sup, color=AZUL, linewidth=1.6)
        ax.plot(d.rr, y, "o", color=AZUL, markersize=4.5, markeredgecolor="white", markeredgewidth=1)
        ax.set_title(titulo, loc="left", fontsize=9)
        ax.set_xscale("log")
        ax.grid(axis="y", visible=False)
    for ax in axs:
        eixo_razao(ax, "x", (0.5, 0.8, 1.0, 1.25, 2.0))
    axs[0].set_yticks(y, [rot[k] for k in ordem])
    fig.supxlabel("Razão de taxas por 10 p.p. da população em área afetada (IC 95%)", fontsize=9, color=TXT2)
    fig.tight_layout()
    salvar(fig, "figura4_floresta_periodos")


def figura_caps() -> None:
    """Figura 5 (candidata): estudo de eventos da produção dos CAPS."""
    figura_evento(("caps_usuarios", "caps_novos", "caps_crise", "caps_domiciliar"), nome="figura5_caps_estudo_eventos")


def figura_oferta_caps(pasta: Path) -> None:
    """CAPS com produção no mês, pelo município onde o CAPS fica, por categoria de exposição."""
    of = pd.read_parquet(PROCESSADOS / "oferta_caps_municipio_mes.parquet")
    exp = pd.read_csv(PROCESSADOS / "exposicao_municipio.csv")[["mun_res", "exposicao_cat"]]
    of = of.merge(exp.rename(columns={"mun_res": "mun_local"}), on="mun_local", how="left")
    t = of.groupby(["mes", "exposicao_cat"]).caps_ativos.sum().unstack().reindex(columns=["<1%", "1-<10%", ">=10%"])
    t = t[t.index >= "2022-01-01"]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    for (cat, cor), rot in zip(zip(t.columns, RAMPA3), ["Exposição <1%", "Exposição 1–<10%", "Exposição ≥10%"]):
        ax.plot(t.index, t[cat], color=cor, linewidth=1.6)
        ax.annotate(rot, (t.index[-1], t[cat].iloc[-1]), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=8, color=TXT1)
    ax.axvline(INICIO_ENCHENTE, color=TXT2, linewidth=0.8)
    ax.text(INICIO_ENCHENTE, ax.get_ylim()[1], " maio/2024", va="top", ha="left", color=TXT2, fontsize=7.5)
    ax.set_ylabel("CAPS com produção no mês")
    ax.set_title("Oferta: CAPS com produção registrada (RAAS), pelo município do CAPS", loc="left")
    ax.grid(axis="x", visible=False)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_xlim(right=t.index[-1] + pd.Timedelta(days=200))
    fig.tight_layout()
    salvar(fig, "S10_oferta_caps", pasta)


def figuras_artigo() -> None:
    """Figuras 2 e 3 do manuscrito (internações + CAPS), em resultados/figuras/artigo/."""
    pasta = SAIDA / "artigo"
    m = pd.read_csv(RESULTADOS / "01_contrafactual" / "esperado_mensal.csv", parse_dates=["mes"])
    m = m[m.modelo == "ensemble"]
    exp = pd.read_csv(PROCESSADOS / "exposicao_municipio.csv")[["mun_res", "exposicao_cat"]]
    pop = pd.read_parquet(PROCESSADOS / "populacao_municipio_mes.parquet", columns=["mun_res", "mes", "pop_total"])
    inicio = pd.Timestamp("2022-01-01")
    linhas = [("f_total", "painel_municipio_mes.parquet", "Internações psiquiátricas (F00–F99)",
               "Internações por 100 mil hab."),
              ("caps_usuarios", "painel_caps_municipio_mes.parquet", "Usuários atendidos nos CAPS",
               "Usuários por 100 mil hab.")]
    NOMES_ESTRATO_FIG = {"estado": "Rio Grande do Sul", ">=10%": "Municípios com ≥10% da população atingida"}
    fig, axs = plt.subplots(2, 2, figsize=(7.2, 5.6), sharex=True)
    for i, (d, arq, nome_d, rot_y) in enumerate(linhas):
        serie = pd.read_parquet(PROCESSADOS / arq, columns=["mun_res", "mes", d]).merge(pop, on=["mun_res", "mes"]) \
            .merge(exp, on="mun_res")
        for j, e in enumerate(["estado", ">=10%"]):
            ax = axs[i, j]
            dd = serie if e == "estado" else serie[serie.exposicao_cat == e]
            o = dd[dd.mes >= inicio].groupby("mes")[[d, "pop_total"]].sum()
            taxa = 1e5 * o[d] / o.pop_total
            f = m[(m.desfecho == d) & (m.estrato == e)].set_index("mes")
            k = 1e5 / f["pop"]
            ax.fill_between(f.index, f.ic_inf * k, f.ic_sup * k, color=LARANJA, alpha=0.18, linewidth=0)
            ax.plot(f.index, f.esperado * k, color=LARANJA, linewidth=1.6)
            ax.plot(taxa.index, taxa.values, color=AZUL, linewidth=1.6)
            ax.axvline(INICIO_ENCHENTE, color=TXT2, linewidth=0.8)
            ax.set_title(f"{'ABCD'[2 * i + j]}. {nome_d}\n{NOMES_ESTRATO_FIG[e]}", loc="left", fontsize=8.5)
            ax.grid(axis="x", visible=False)
            ax.xaxis.set_major_locator(mdates.YearLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",")))
            lo, hi = min(taxa.min(), (f.ic_inf * k).min()), max(taxa.max(), (f.ic_sup * k).max())
            ax.set_ylim(lo - 0.15 * (hi - lo), hi + 0.25 * (hi - lo))
            if j == 0:
                ax.set_ylabel(rot_y)
            if i == 0 and j == 0:
                ax.legend([Line2D([], [], color=AZUL, linewidth=1.6),
                           (Patch(facecolor=LARANJA, alpha=0.18, linewidth=0), Line2D([], [], color=LARANJA, linewidth=1.6))],
                          ["Observado", "Esperado sem a enchente (IC 95%)"], loc="lower left", fontsize=7.5)
                ax.text(INICIO_ENCHENTE, ax.get_ylim()[1], " maio/2024", va="top", ha="left", color=TXT2, fontsize=7.5)
    fig.tight_layout()
    salvar(fig, "Figura2_observado_esperado_internacoes_caps", pasta)
    figura_evento(("f_total", "f_psicoticos", "caps_usuarios", "ctrl_parto"),
                  nome="Figura3_estudo_eventos", pasta=pasta, mesmo_y=False,
                  titulos={"f_total": "A. Internações psiquiátricas (F00–F99)",
                           "f_psicoticos": "B. Internações por psicoses (F20–F29)",
                           "caps_usuarios": "C. Usuários atendidos nos CAPS",
                           "ctrl_parto": "D. Partos (controle)"})


def figuras_suplementares() -> None:
    """S1–S6: observado × esperado dos desfechos secundários e estudos de eventos adicionais."""
    pasta = SAIDA / "suplementares"
    for i, d in enumerate(["f_spa", "f_humor", "f_psicoticos", "ctrl_parto", "nao_f"], start=1):
        figura_observado_esperado(d, nome=f"S{i}_observado_esperado_{d}", titulo=ROTULOS[d], pasta=pasta)
    figura_evento(("f_psicoticos", "f_urgencia", "f_leito_outro", "nao_f"),
                  nome="S6_estudo_eventos_outros_desfechos", pasta=pasta)
    figura_evento(("f_fora_mun", "f_negra", "f_fem", "ctrl_apendicite"),
                  nome="S7_estudo_eventos_fluxo_grupos", pasta=pasta)
    if (PROCESSADOS / "painel_caps_municipio_mes.parquet").exists():
        figura_observado_esperado("caps_usuarios", nome="S8_observado_esperado_caps_usuarios",
                                  titulo=ROTULOS["caps_usuarios"], pasta=pasta, rotulo_y="Usuários por 100 mil hab.")
        figura_observado_esperado("caps_novos", nome="S9_observado_esperado_caps_novos",
                                  titulo=ROTULOS["caps_novos"], pasta=pasta, rotulo_y="Usuários novos por 100 mil hab.")
        figura_oferta_caps(pasta)
        figura_evento(("caps_usuarios_ad", "caps_usuarios_estresse", "caps_individual", "caps_acolhimento"),
                      nome="S11_estudo_eventos_caps_recortes", pasta=pasta)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", default="1,2,3,4,5,S,A")
    a = ap.parse_args()
    fns = {"1": figura_mapa, "2": figura_observado_esperado, "3": figura_evento, "4": figura_floresta,
           "5": figura_caps, "S": figuras_suplementares, "A": figuras_artigo}
    for k in a.so.split(","):
        fns[k]()


if __name__ == "__main__":
    main()
