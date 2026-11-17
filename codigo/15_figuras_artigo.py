# -*- coding: utf-8 -*-
"""
Figuras 1 a 4 do manuscrito (versão de 15/11/2026), em cores e em tons de cinza.

Normas da Ciência & Saúde Coletiva: no máximo cinco ilustrações por artigo, figuras com até 15 cm de largura
e 20 cm de altura, texto em Times New Roman 9 e gráficos em tons de cinza. As figuras são compostas (vários
painéis) para caberem no limite de ilustrações sem material suplementar. A versão em cores usa cores com
luminosidades bem diferentes, que continuam distinguíveis quando a revista converte a figura para cinza.
O texto usa Times New Roman quando instalada; senão Liberation Serif, que tem as mesmas medidas.

Figura 1  A: proporção da população na área atingida, por município (mapa);
          B: CAPS com atendimentos registrados no mês, por grupo de exposição do município do CAPS
Figura 2  usuários dos CAPS, observado e esperado: todos (A, C, E, G) e com F40-F48 (B, D, F, H),
          no estado e por grupo de exposição
Figura 3  A: razão de taxas por 10 p.p. por período (CAPS, internações, comparação, sexo e raça/cor);
          B: razão de taxas por trimestre (usuários dos CAPS, internações F00-F99 e partos)
Figura 4  internações, observado e esperado: F00-F99 (estado, <1% e >=10%), F20-F29, F10-F19, F30-F39,
          partos e demais internações (>=10%)

Uso: python 15_figuras_artigo.py <raiz do repositório ou pasta da entrega> <pasta de saída> [en|pt]
Saídas em inglês (padrão; o manuscrito é em inglês): FigureN_<nome>_color.{png,jpg,pdf} e FigureN_<nome>_gray.{...}
Saídas em português: FiguraN_<nome>_cor.{png,jpg,pdf} e FiguraN_<nome>_cinza.{png,jpg,pdf}. Todas com 15 cm de largura.
"""
import json
import os
import sys
import zipfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as md  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, PathPatch  # noqa: E402
from matplotlib.path import Path as MPath  # noqa: E402

ENT, OUT = sys.argv[1], sys.argv[2]
IDIOMA = sys.argv[3] if len(sys.argv) > 3 else "en"
if IDIOMA not in ("en", "pt"):
    raise SystemExit("idioma deve ser en ou pt")
os.makedirs(OUT, exist_ok=True)
# aceita a pasta da entrega (5_dados_agregados/, 6_resultados_completos/) ou a raiz do repositório
_DA, _RC = os.path.join(ENT, "5_dados_agregados"), os.path.join(ENT, "6_resultados_completos")
DA = _DA if os.path.isdir(_DA) else os.path.join(ENT, "dados_agregados")
RC = _RC if os.path.isdir(_RC) else os.path.join(ENT, "resultados")
# malha municipal: a completa do IBGE (dados/brutos, só na pasta da análise) ou a simplificada do painel (docs/dados),
# procuradas na pasta indicada e na raiz do repositório onde está este script
RAIZ_SCRIPT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def primeiro(*caminhos):
    return next((c for c in caminhos if os.path.exists(c)), caminhos[-1])


MALHA_IBGE = primeiro(*[os.path.join(r, "dados", "brutos", "malha_ibge_2022", "RS_Municipios_2022.zip") for r in (ENT, RAIZ_SCRIPT)])
MALHA_PAINEL = primeiro(*[os.path.join(r, "docs", "dados", "municipios.geojson") for r in (ENT, RAIZ_SCRIPT)])

FONTE = ("Times New Roman" if any("Times New Roman" in f.name for f in matplotlib.font_manager.fontManager.ttflist)
         else "Liberation Serif")
plt.rcParams.update({
    "font.family": "serif", "font.serif": [FONTE, "Liberation Serif", "DejaVu Serif"], "font.size": 9,
    "axes.titlesize": 9, "axes.labelsize": 9, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "legend.fontsize": 9, "legend.title_fontsize": 9, "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#555555", "axes.linewidth": 0.6, "xtick.color": "#333333", "ytick.color": "#333333",
    "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2.5, "ytick.major.size": 2.5,
    "pdf.fonttype": 42, "ps.fonttype": 42, "axes.titlepad": 3,
})
CM = 1 / 2.54
LARGURA = 15.0
MAIO24 = pd.Timestamp("2024-05-01")
INICIO, FIM = pd.Timestamp("2022-01-01"), pd.Timestamp("2026-03-01")

# Cores. Na versão em cores, observado (azul escuro), esperado (laranja) e faixa (pêssego claro) têm
# luminosidades de cerca de 28%, 47% e 88%, e o esperado é tracejado; no mapa, a rampa azul vai de 95% a 27%.
ESTILOS = {
    "cor": {
        "obs": "#1f4e8c", "esp": "#d95f02", "faixa": "#fbd9c4", "vline": "#4d4d4d", "grade": "#e6e6e6",
        "mapa": ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"], "borda_lagoa": "#7f9fbf",
        "oferta": {"<1%": ("#6baed6", "-", 1.3), "1-<10%": ("#3182bd", (0, (4, 2)), 1.3),
                   ">=10%": ("#08306b", "-", 1.8)},
        "grupo": {"caps": "#1f4e8c", "int": "#7b3294", "comp": "#6f6f6f"},
    },
    "cinza": {
        "obs": "#000000", "esp": "#555555", "faixa": "#d9d9d9", "vline": "#4d4d4d", "grade": "#e6e6e6",
        "mapa": ["#ececec", "#c4c4c4", "#969696", "#636363", "#252525"], "borda_lagoa": "#8a8a8a",
        "oferta": {"<1%": ("#8c8c8c", "-", 1.3), "1-<10%": ("#4d4d4d", (0, (4, 2)), 1.3),
                   ">=10%": ("#000000", "-", 1.8)},
        "grupo": {"caps": "#000000", "int": "#000000", "comp": "#555555"},
    },
}
GRUPOS_EXP = ["<1%", "1-<10%", ">=10%"]

# Textos das figuras em cada idioma
TEXTOS = {
    "pt": {
        "grupo": {"estado": "Rio Grande do Sul", "<1%": "<1% da população atingida",
                  "1-<10%": "1% a <10% da população atingida", ">=10%": "≥10% da população atingida"},
        "legenda": ["Observado", "Esperado sem a enchente", "IC95% do esperado"],
        "faixas_mapa": ["<1%", "1% a <5%", "5% a <10%", "10% a <25%", "≥25%"], "n_mun": "municípios",
        "titulo_legenda_mapa": "População na área atingida",
        "fig1a": "A. Proporção da população residente na área atingida, por município",
        "rot_oferta": {"<1%": "<1%", "1-<10%": "1% a <10%", ">=10%": "≥10%"}, "eixo_caps": "Número de CAPS",
        "fig1b": "B. CAPS com atendimentos registrados no mês, por grupo de municípios",
        "todos_usuarios": "Todos os usuários", "estresse": "Relacionados ao estresse (F40-F48)",
        "eixo_fig2": "Usuários por 100 mil habitantes",
        "fig4": ["Transtornos mentais (F00-F99)", "Esquizofrenia e psicoses (F20-F29)",
                 "Álcool e outras drogas (F10-F19)", "Transtornos do humor (F30-F39)", "Partos (O80-O84), comparação",
                 "Demais internações, comparação"],
        "eixo_fig4": "Internações por 100 mil habitantes",
        "cab": ["Usuários dos CAPS", "Internações psiquiátricas", "Internações de comparação"],
        "linhas_caps": ["Todos", "Usuários novos", "Álcool e drogas (F10-F19)", "Estresse (F40-F48)", "0 a 17 anos"],
        "linhas_int": ["Todas (F00-F99)", "Psicoses (F20-F29)", "Álcool e drogas (F10-F19)", "Humor (F30-F39)"],
        "linhas_comp": ["Partos (O80-O84)", "Apendicite (K35-K37)", "Demais internações"],
        "mulheres": "Mulheres", "homens": "Homens", "negras": "Pessoas negras", "brancas": "Pessoas brancas",
        "fig3a": "A. Por período após a enchente",
        "periodos": ["Agudo\nmai-jul/2024", "Subagudo\nago/2024-abr/2025", "Tardio\nmai/2025-mar/2026"],
        "eixo_fig3a": "Razão de taxas a cada 10 pontos percentuais\nde população atingida (IC95%)",
        "fig3b": "B. Por trimestre desde maio de 2024 (referência: fevereiro a abril de 2024)",
        "paineis_3b": ["Usuários dos CAPS", "Internações (F00-F99)", "Partos (comparação)"],
        "eixo_rt": "Razão de taxas", "eixo_trimestres": "Trimestres desde maio de 2024",
        "arquivos": {1: "Figura1_exposicao_e_caps", 2: "Figura2_caps_observado_esperado", 3: "Figura3_razao_de_taxas",
                     4: "Figura4_internacoes_observado_esperado"},
        "variantes": {"cor": "cor", "cinza": "cinza"}, "decimal": ",",
    },
    "en": {
        "grupo": {"estado": "Rio Grande do Sul", "<1%": "<1% of the population affected",
                  "1-<10%": "1% to <10% of the population affected", ">=10%": "≥10% of the population affected"},
        "legenda": ["Observed", "Expected without the flood", "95%CI of the expected"],
        "faixas_mapa": ["<1%", "1% to <5%", "5% to <10%", "10% to <25%", "≥25%"], "n_mun": "municipalities",
        "titulo_legenda_mapa": "Population in the affected area",
        "fig1a": "A. Share of the population living in the affected area, by municipality",
        "rot_oferta": {"<1%": "<1%", "1-<10%": "1% to <10%", ">=10%": "≥10%"}, "eixo_caps": "Number of CAPS",
        "fig1b": "B. CAPS with care recorded in the month, by group of municipalities",
        "todos_usuarios": "All users", "estresse": "Stress-related disorders (F40-F48)",
        "eixo_fig2": "Users per 100,000 inhabitants",
        "fig4": ["Mental disorders (F00-F99)", "Schizophrenia and psychoses (F20-F29)",
                 "Alcohol and other drugs (F10-F19)", "Mood disorders (F30-F39)", "Childbirth (O80-O84), comparison",
                 "All other admissions, comparison"],
        "eixo_fig4": "Admissions per 100,000 inhabitants",
        "cab": ["CAPS users", "Psychiatric admissions", "Comparison admissions"],
        "linhas_caps": ["All", "New users", "Alcohol and drugs (F10-F19)", "Stress (F40-F48)", "Aged 0-17 years"],
        "linhas_int": ["All (F00-F99)", "Psychoses (F20-F29)", "Alcohol and drugs (F10-F19)", "Mood (F30-F39)"],
        "linhas_comp": ["Childbirth (O80-O84)", "Appendicitis (K35-K37)", "All other admissions"],
        "mulheres": "Women", "homens": "Men", "negras": "Black people", "brancas": "White people",
        "fig3a": "A. By period after the flood",
        "periodos": ["Acute\nMay-Jul 2024", "Subacute\nAug 2024-Apr 2025", "Late\nMay 2025-Mar 2026"],
        "eixo_fig3a": "Rate ratio per 10 percentage points\nof the population affected (95%CI)",
        "fig3b": "B. By quarter since May 2024 (reference: February to April 2024)",
        "paineis_3b": ["CAPS users", "Admissions (F00-F99)", "Childbirth (comparison)"],
        "eixo_rt": "Rate ratio", "eixo_trimestres": "Quarters since May 2024",
        "arquivos": {1: "Figure1_exposure_and_CAPS", 2: "Figure2_CAPS_observed_expected", 3: "Figure3_rate_ratios",
                     4: "Figure4_admissions_observed_expected"},
        "variantes": {"cor": "color", "cinza": "gray"}, "decimal": ".",
    },
}
L = TEXTOS[IDIOMA]
NOME_GRUPO = L["grupo"]

fmt_num = mt.FuncFormatter(lambda v, p: f"{v:g}".replace(".", L["decimal"]))


def fmt_razao(v, p=None):
    return f"{v:.2f}".replace(".", L["decimal"])


def eixo(fig, x, y, w, h):
    """Eixo posicionado em centímetros (x, y = canto inferior esquerdo)."""
    W, H = fig.get_size_inches() / CM
    return fig.add_axes([x / W, y / H, w / W, h / H])


def salvar(fig, nome):
    for ext in ("png", "jpg", "pdf"):
        kw = {"dpi": 300} if ext != "pdf" else {}
        if ext == "jpg":
            kw["pil_kwargs"] = {"quality": 95}
        fig.savefig(os.path.join(OUT, f"{nome}.{ext}"), **kw)
    plt.close(fig)
    print("figura:", nome)


# ------------------------------------------------------------------ dados
def pop_mensal(pop):
    p = pop.pivot(index="mun_res", columns="ano", values="pop_total")
    if 2026 not in p.columns:
        p[2026] = p[2025]
    meses = pd.date_range("2015-01-01", "2026-03-01", freq="MS")
    xa = pd.to_datetime([f"{a}-07-01" for a in p.columns]).values.astype("datetime64[D]").astype(float)
    xm = meses.values.astype("datetime64[D]").astype(float)
    arr = np.vstack([np.interp(xm, xa, r) for r in p.values])
    o = pd.DataFrame(arr, index=p.index, columns=meses).stack().reset_index()
    o.columns = ["mun_res", "mes", "pop"]
    return o


ex = pd.read_csv(os.path.join(DA, "exposicao_municipio.csv"))
pm = pd.read_csv(os.path.join(DA, "painel_municipio_mes.csv"), parse_dates=["mes"])
pc = pd.read_csv(os.path.join(DA, "painel_caps_municipio_mes.csv"), parse_dates=["mes"])
pop = pop_mensal(pd.read_csv(os.path.join(DA, "populacao_municipio_ano.csv")))
base = (pm[["mun_res", "mes", "f_total", "f_psicoticos", "f_spa", "f_humor", "ctrl_parto", "nao_f"]]
        .merge(pc[["mun_res", "mes", "caps_usuarios", "caps_usuarios_estresse"]], on=["mun_res", "mes"], how="left")
        .merge(pop, on=["mun_res", "mes"]).merge(ex[["mun_res", "exposicao_cat"]], on="mun_res"))
esp = pd.read_csv(os.path.join(RC, "01_contrafactual", "esperado_mensal.csv"), parse_dates=["mes"])
esp = esp[esp.modelo == "ensemble"]


# ------------------------------------------------------------------ painéis observado x esperado
def painel_oe(ax, est, desfecho, estrato, titulo):
    d = base if estrato == "estado" else base[base.exposicao_cat == estrato]
    s = d.groupby("mes").agg(y=(desfecho, "sum"), pop=("pop", "sum")).reset_index()
    s = s[(s.mes >= INICIO) & (s.mes <= FIM)]
    e = esp[(esp.desfecho == desfecho) & (esp.estrato == estrato)].sort_values("mes")
    if e.empty:
        raise SystemExit(f"sem esperado para {desfecho} / {estrato}")
    k = 1e5 / e["pop"]
    ax.fill_between(e.mes, e.ic_inf * k, e.ic_sup * k, color=est["faixa"], lw=0, zorder=1)
    ax.plot(e.mes, e.esperado * k, color=est["esp"], lw=1.1, ls=(0, (4, 2)), zorder=2)
    ax.plot(s.mes, s.y / s["pop"] * 1e5, color=est["obs"], lw=1.2, zorder=3)
    ax.axvline(MAIO24, color=est["vline"], lw=0.6, zorder=0)
    ax.set_xlim(INICIO - pd.Timedelta(days=20), FIM + pd.Timedelta(days=20))
    ax.set_title(titulo, loc="left", fontweight="bold", linespacing=1.1)
    ax.xaxis.set_major_locator(md.YearLocator())
    ax.xaxis.set_major_formatter(md.DateFormatter("%Y"))
    ax.yaxis.set_major_locator(mt.MaxNLocator(4))
    ax.yaxis.set_major_formatter(fmt_num)
    ax.grid(axis="y", color=est["grade"], lw=0.5, zorder=0)


def grade_oe(nome, paineis, rotulo_y, est, variante):
    """4 linhas x 2 colunas de painéis observado x esperado, títulos de duas linhas e legenda embaixo."""
    H = 18.8
    fig = plt.figure(figsize=(LARGURA * CM, H * CM))
    x0, wcol, gap = 1.45, 6.05, 1.25
    alt, passo, topo = 3.15, 4.25, H - 0.95
    eixos = []
    for i, (desf, estr, tit) in enumerate(paineis):
        lin, col = divmod(i, 2)
        ax = eixo(fig, x0 + col * (wcol + gap), topo - alt - lin * passo, wcol, alt)
        painel_oe(ax, est, desf, estr, tit)
        if lin < 3:
            ax.tick_params(labelbottom=False)
        eixos.append(ax)
    fig.text(0.12 / LARGURA, 0.5 + 0.35 / H, rotulo_y, rotation=90, va="center", ha="left")
    alcas = [Line2D([], [], color=est["obs"], lw=1.2), Line2D([], [], color=est["esp"], lw=1.1, ls=(0, (4, 2))),
             Patch(facecolor=est["faixa"], lw=0)]
    fig.legend(alcas, L["legenda"], loc="lower center",
               ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.0), handlelength=2.2, columnspacing=1.6)
    salvar(fig, f"{nome}_{L['variantes'][variante]}")


# ------------------------------------------------------------------ Figura 1
def aneis_malha():
    """(código IBGE de 7 dígitos, lista de anéis). Malha completa do IBGE se existir; senão a do painel."""
    if os.path.exists(MALHA_IBGE):
        import shapefile  # pyshp
        tmp = os.path.join(OUT, "_malha_tmp")
        os.makedirs(tmp, exist_ok=True)
        with zipfile.ZipFile(MALHA_IBGE) as zf:
            zf.extractall(tmp)
        sf = shapefile.Reader(os.path.join(tmp, "RS_Municipios_2022.shp"), encoding="utf-8")
        for sr in sf.iterShapeRecords():
            pts = np.asarray(sr.shape.points)
            partes = list(sr.shape.parts) + [len(pts)]
            yield int(sr.record["CD_MUN"]), [pts[partes[i]:partes[i + 1]] for i in range(len(partes) - 1)]
        return
    print("AVISO: sem a malha completa do IBGE; usando a malha simplificada do painel:", MALHA_PAINEL)
    with open(MALHA_PAINEL, encoding="utf-8") as f:
        gj = json.load(f)
    for ft in gj["features"]:
        g = ft["geometry"]
        poligonos = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        yield int(ft["properties"]["CD_MUN"]), [np.asarray(anel) for pol in poligonos for anel in pol]


def figura1(est, variante):
    H = 18.9
    fig = plt.figure(figsize=(LARGURA * CM, H * CM))
    # A. mapa
    ax = eixo(fig, 0.0, 6.35, LARGURA, 12.45)
    expo = ex.set_index("mun_res")
    cortes = [1, 5, 10, 25]
    rotulos = L["faixas_mapa"]
    for cod, aneis in aneis_malha():
        cod6 = cod // 10
        lagoa = cod6 not in expo.index  # Lagoa Mirim e Lagoa dos Patos
        cor = "#ffffff" if lagoa else est["mapa"][int(np.searchsorted(cortes, expo.loc[cod6, "pct_pop_afetada"], side="right"))]
        verts = np.concatenate(aneis)
        codes = np.concatenate([[MPath.MOVETO] + [MPath.LINETO] * (len(a) - 2) + [MPath.CLOSEPOLY] for a in aneis])
        ax.add_patch(PathPatch(MPath(verts, codes), facecolor=cor, edgecolor=est["borda_lagoa"] if lagoa else "#ffffff",
                               linewidth=0.3 if lagoa else 0.15))
    ax.autoscale_view()
    ax.set_aspect(1 / np.cos(np.deg2rad(30)))
    ax.axis("off")
    n = np.bincount(np.searchsorted(cortes, ex.pct_pop_afetada, side="right"), minlength=5)
    ax.legend([Patch(facecolor=c, edgecolor="#6f6f6f", linewidth=0.4) for c in est["mapa"]],
              [f"{r} ({k} {L['n_mun']})" for r, k in zip(rotulos, n)], loc="lower left",
              title=L["titulo_legenda_mapa"], alignment="left", frameon=False, borderaxespad=0.2)
    fig.text(0.02 / LARGURA, 1 - 0.15 / H, L["fig1a"],
             fontweight="bold", va="top", ha="left")
    # B. CAPS com atendimentos registrados, pelo município onde o CAPS fica
    of = pd.read_csv(os.path.join(DA, "oferta_caps_municipio_mes.csv"), parse_dates=["mes"])
    of = of.merge(ex[["mun_res", "exposicao_cat"]].rename(columns={"mun_res": "mun_local"}), on="mun_local", how="left")
    of["exposicao_cat"] = of["exposicao_cat"].fillna("<1%")
    t = of.groupby(["mes", "exposicao_cat"]).caps_ativos.sum().unstack().reindex(columns=GRUPOS_EXP)
    t = t[(t.index >= INICIO) & (t.index <= FIM)]
    bx = eixo(fig, 1.45, 0.75, 11.35, 4.75)
    rot = L["rot_oferta"]
    for g in GRUPOS_EXP:
        cor, ls, lw = est["oferta"][g]
        bx.plot(t.index, t[g], color=cor, ls=ls, lw=lw)
        bx.annotate(rot[g], (t.index[-1], t[g].iloc[-1]), xytext=(5, 0), textcoords="offset points",
                    va="center", ha="left", annotation_clip=False)
    bx.axvline(MAIO24, color=est["vline"], lw=0.6)
    bx.set_xlim(INICIO - pd.Timedelta(days=20), FIM + pd.Timedelta(days=20))
    bx.set_ylim(0, max(100, t.max().max() * 1.08))
    bx.set_ylabel(L["eixo_caps"])
    bx.set_title(L["fig1b"], loc="left", fontweight="bold")
    bx.xaxis.set_major_locator(md.YearLocator())
    bx.xaxis.set_major_formatter(md.DateFormatter("%Y"))
    bx.yaxis.set_major_locator(mt.MultipleLocator(20))
    bx.grid(axis="y", color=est["grade"], lw=0.5)
    salvar(fig, f"{L['arquivos'][1]}_{L['variantes'][variante]}")


# ------------------------------------------------------------------ Figura 2
def figura2(est, variante):
    paineis = []
    letras = iter("ABCDEFGH")
    for estr in ["estado", "<1%", "1-<10%", ">=10%"]:
        paineis.append(("caps_usuarios", estr, f"{next(letras)}. {L['todos_usuarios']}\n{NOME_GRUPO[estr]}"))
        paineis.append(("caps_usuarios_estresse", estr, f"{next(letras)}. {L['estresse']}\n{NOME_GRUPO[estr]}"))
    grade_oe(L["arquivos"][2], paineis, L["eixo_fig2"], est, variante)


# ------------------------------------------------------------------ Figura 4
def figura4(est, variante):
    t = L["fig4"]
    g = NOME_GRUPO
    paineis = [
        ("f_total", "estado", f"A. {t[0]}\n{g['estado']}"),
        ("f_total", "<1%", f"B. {t[0]}\n{g['<1%']}"),
        ("f_total", ">=10%", f"C. {t[0]}\n{g['>=10%']}"),
        ("f_psicoticos", ">=10%", f"D. {t[1]}\n{g['>=10%']}"),
        ("f_spa", ">=10%", f"E. {t[2]}\n{g['>=10%']}"),
        ("f_humor", ">=10%", f"F. {t[3]}\n{g['>=10%']}"),
        ("ctrl_parto", ">=10%", f"G. {t[4]}\n{g['>=10%']}"),
        ("nao_f", ">=10%", f"H. {t[5]}\n{g['>=10%']}"),
    ]
    grade_oe(L["arquivos"][4], paineis, L["eixo_fig4"], est, variante)


# ------------------------------------------------------------------ Figura 3
def dados_floresta():
    cp = pd.read_csv(os.path.join(RC, "02_dose_resposta", "coef_periodo.csv"))
    cp = cp[(cp.especificacao == "principal") & (cp.exposicao == "continua_10pp")].copy()
    cp["periodo"] = cp.termo.str.extract(r"periodo::(\w+):")
    pt = pd.read_csv(os.path.join(RC, "02_dose_resposta", "pretendencia.csv"))
    pt = pt[(pt.especificacao == "principal") & (pt.exposicao == "continua_10pp")].set_index("desfecho").p_pretendencia
    dg = pd.read_csv(os.path.join(RC, "04_desigualdades", "desigualdades_rt.csv"))

    def de_coef(desf):
        d = cp[cp.desfecho == desf].set_index("periodo")
        return {p: (d.loc[p, "rr"], d.loc[p, "rr_ic_inf"], d.loc[p, "rr_ic_sup"]) for p in ("agudo", "subagudo", "tardio")}

    def de_desig(dim, desf_txt, grupo):
        d = dg[(dg.dimensao == dim) & (dg.desfecho == desf_txt)]
        out = {}
        for p in ("agudo", "subagudo", "tardio"):
            r = d[d.periodo == p].iloc[0]
            lado = "ref" if r.grupo_ref == grupo else "comp"
            if r[f"grupo_{lado}"] != grupo:
                raise SystemExit(f"grupo {grupo} não encontrado em {dim}/{desf_txt}")
            out[p] = (r[f"rt_{lado}"], r[f"rt_{lado}_inf"], r[f"rt_{lado}_sup"])
        return out

    def adaga(desf):
        return "†" if desf in pt.index and pt[desf] < 0.05 else ""

    caps_txt = [t for t in dg.desfecho.unique() if t.startswith("Usuários")][0]
    int_txt = [t for t in dg.desfecho.unique() if t.startswith("Internações")][0]
    linhas = [("cab", L["cab"][0], None, None)]
    for desf, rot in zip(["caps_usuarios", "caps_novos", "caps_usuarios_ad", "caps_usuarios_estresse",
                          "caps_usuarios_0_17"], L["linhas_caps"]):
        linhas.append(("lin", rot + adaga(desf), "caps", de_coef(desf)))
    linhas += [("lin", L["mulheres"] + adaga("caps_usuarios_fem"), "caps", de_desig("sexo", caps_txt, "mulheres")),
               ("lin", L["homens"], "caps", de_desig("sexo", caps_txt, "homens")),
               ("lin", L["negras"], "caps", de_desig("raça/cor", caps_txt, "pretos ou pardos")),
               ("lin", L["brancas"], "caps", de_desig("raça/cor", caps_txt, "brancos")),
               ("cab", L["cab"][1], None, None)]
    for desf, rot in zip(["f_total", "f_psicoticos", "f_spa", "f_humor"], L["linhas_int"]):
        linhas.append(("lin", rot + adaga(desf), "int", de_coef(desf)))
    linhas += [("lin", L["mulheres"] + adaga("f_fem"), "int", de_desig("sexo", int_txt, "mulheres")),
               ("lin", L["homens"] + adaga("f_masc"), "int", de_desig("sexo", int_txt, "homens")),
               ("lin", L["negras"], "int", de_desig("raça/cor", int_txt, "pretos ou pardos")),
               ("lin", L["brancas"], "int", de_desig("raça/cor", int_txt, "brancos")),
               ("cab", L["cab"][2], None, None)]
    for desf, rot in zip(["ctrl_parto", "ctrl_apendicite", "nao_f"], L["linhas_comp"]):
        linhas.append(("lin", rot + adaga(desf), "comp", de_coef(desf)))
    return linhas


def marcas_log(lo, hi, candidatas):
    m = [c for c in candidatas if lo <= c <= hi]
    return m if len(m) >= 2 else [c for c in candidatas if lo * 0.97 <= c <= hi * 1.03]


def figura3(est, variante):
    H = 19.2
    fig = plt.figure(figsize=(LARGURA * CM, H * CM))
    linhas = dados_floresta()
    n = len(linhas)
    y = np.arange(n)[::-1]
    topo, base_f = H - 1.45, 7.25
    alt = topo - base_f
    fig.text(0.02 / LARGURA, 1 - 0.12 / H, L["fig3a"], fontweight="bold", va="top", ha="left")
    # coluna de rótulos
    lx = eixo(fig, 0.0, base_f, 4.9, alt)
    lx.set_xlim(0, 1)
    lx.set_ylim(-0.6, n - 0.4)
    lx.axis("off")
    for yi, (tipo, rot, grp, _) in zip(y, linhas):
        if tipo == "cab":
            lx.text(0.0, yi, rot, va="center", ha="left", fontweight="bold")
        else:
            lx.text(0.05, yi, rot, va="center", ha="left")
    todos = [v for t, _, _, d in linhas if t == "lin" for p in d.values() for v in p[1:]]
    lo, hi = min(min(todos) * 0.96, 0.56), max(max(todos) * 1.04, 1.40)
    periodos = list(zip(["agudo", "subagudo", "tardio"], L["periodos"]))
    for j, (p, tit) in enumerate(periodos):
        ax = eixo(fig, 5.1 + j * 3.3, base_f, 2.85, alt)
        ax.axvline(1, color="#4d4d4d", lw=0.6, zorder=1)
        for yi, (tipo, rot, grp, d) in zip(y, linhas):
            if tipo == "cab":
                continue
            rr, li, ls_ = d[p]
            cor = est["grupo"][grp]
            ax.hlines(yi, li, ls_, color=cor, lw=1.1, zorder=2)
            ax.plot(rr, yi, "o", color=cor, ms=3.6, mec="white", mew=0.5, zorder=3)
        ax.set_xscale("log")
        ax.set_xlim(lo, hi)
        ax.set_ylim(-0.6, n - 0.4)
        ax.xaxis.set_major_locator(mt.FixedLocator(marcas_log(lo, hi, [0.6, 0.8, 1.0, 1.25])))
        ax.xaxis.set_major_formatter(mt.FuncFormatter(fmt_razao))
        ax.xaxis.set_minor_locator(mt.NullLocator())
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        for yi, (tipo, *_r) in zip(y, linhas):
            if tipo == "cab":
                ax.axhspan(yi - 0.5, yi + 0.5, color="#f2f2f2", lw=0, zorder=0)
        ax.set_title(tit, fontweight="bold", loc="center", linespacing=1.1)
    fig.text((5.1 + 1.5 * 3.3 - 0.225) / LARGURA, (base_f - 1.15) / H, L["eixo_fig3a"], ha="center", va="center",
             linespacing=1.1)
    # B. por trimestre
    ce = pd.read_csv(os.path.join(RC, "02_dose_resposta", "coef_evento.csv"))
    ce = ce[(ce.especificacao == "principal") & (ce.exposicao == "continua_10pp")].copy()
    ce["k"] = ce.termo.str.extract(r"k::(-?\d+):").astype(int)
    fig.text(0.02 / LARGURA, (base_f - 1.95) / H, L["fig3b"], fontweight="bold", va="top", ha="left")
    paineis = list(zip(["caps_usuarios", "f_total", "ctrl_parto"], L["paineis_3b"], ["caps", "int", "comp"]))
    b_alt, b_base = 3.55, 1.05
    for j, (desf, tit, grp) in enumerate(paineis):
        ax = eixo(fig, 1.35 + j * 4.65, b_base, 3.85, b_alt)
        c = ce[(ce.desfecho == desf) & (ce.k >= -8)].sort_values("k")
        c = pd.concat([c, pd.DataFrame({"k": [-1], "rr": [1.0], "rr_ic_inf": [1.0], "rr_ic_sup": [1.0]})]).sort_values("k")
        cor = est["grupo"][grp]
        ax.axhline(1, color="#4d4d4d", lw=0.6)
        ax.axvline(-0.5, color="#9a9a9a", lw=0.6, ls=(0, (2, 2)))
        ax.vlines(c.k, c.rr_ic_inf, c.rr_ic_sup, color=cor, lw=1.0)
        ax.plot(c.k, c.rr, "o", color=cor, ms=3.2, mec="white", mew=0.5)
        ax.set_yscale("log")
        lo_b, hi_b = c.rr_ic_inf.min() * 0.98, c.rr_ic_sup.max() * 1.02
        ax.set_ylim(lo_b, hi_b)
        cand = [0.7, 0.8, 0.9, 1.0, 1.1, 1.25] if hi_b / lo_b > 1.25 else [0.9, 0.95, 1.0, 1.05, 1.1]
        ax.yaxis.set_major_locator(mt.FixedLocator(marcas_log(lo_b, hi_b, cand)))
        ax.yaxis.set_major_formatter(mt.FuncFormatter(fmt_razao))
        ax.yaxis.set_minor_locator(mt.NullLocator())
        ax.set_xticks(range(-8, 8, 4))
        ax.xaxis.set_major_formatter(mt.FuncFormatter(lambda v, p: f"{int(v)}".replace("-", "−")))
        ax.set_xlim(-8.7, 7.7)
        ax.set_title(tit, loc="left", fontweight="bold")
        ax.grid(axis="y", color=est["grade"], lw=0.5)
        if j == 0:
            ax.set_ylabel(L["eixo_rt"])
    fig.text(0.5 + 0.4 / LARGURA, 0.12 / H, L["eixo_trimestres"], ha="center", va="bottom")
    salvar(fig, f"{L['arquivos'][3]}_{L['variantes'][variante]}")


if __name__ == "__main__":
    for variante, est in ESTILOS.items():
        figura1(est, variante)
        figura2(est, variante)
        figura3(est, variante)
        figura4(est, variante)
    print("fonte usada:", FONTE)
