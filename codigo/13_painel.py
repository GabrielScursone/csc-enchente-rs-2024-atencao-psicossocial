"""Etapa 13: dados do painel interativo (pasta painel/, publicada pelo GitHub Pages).

Junta num só JSON os resultados das etapas 05, 06, 09 e 12, as séries mensais por categoria de
exposição e as séries por município. O painel só lê esse arquivo; nenhum número é digitado à mão.

Saídas: painel/dados/painel.js, series_municipio.js e municipios.js (dados como scripts) e municipios.geojson
(malha simplificada, fonte do municipios.js).
A malha é feita uma vez com o mapshaper (Node), que simplifica sem abrir frestas entre vizinhos:
  npx mapshaper RS_Municipios_2022.shp encoding=utf8 -simplify 2% keep-shapes -filter-fields CD_MUN \
      -o format=geojson precision=0.0005 municipios.geojson
Se o arquivo já existir, é mantido.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import (BRUTOS, FIM_ESTUDO, INICIO_ESTUDO, PROCESSADOS, RAIZ, RESULTADOS, ROTULOS,  # noqa: E402
                   carregar_painel)

# painel/ neste projeto; docs/ no repositório público (pasta publicada pelo GitHub Pages)
SAIDA = (RAIZ / "docs" if (RAIZ / "docs").exists() and not (RAIZ / "painel").exists() else RAIZ / "painel") / "dados"
ESTRATOS = ["estado", "<1%", "1-<10%", ">=10%"]
# Desfechos com série por município no painel (os demais ficam só nos resultados agregados)
DESFECHOS_MUN = ["f_total", "f_spa", "f_humor", "f_psicoticos", "caps_usuarios", "caps_novos", "ctrl_parto"]
# Grupos de desfechos para os seletores (ordem de leitura do artigo)
GRUPOS = [
    ("Internações psiquiátricas", ["f_total", "f_spa", "f_alcool", "f_humor", "f_neuroticos", "f_estresse",
                                   "f_psicoticos", "f_organicos", "autolesao", "f_obito"]),
    ("Internações por perfil", ["f_masc", "f_fem", "f_spa_masc", "f_spa_fem", "f_0_17", "f_18_39", "f_40_59",
                                "f_60m", "f_branca", "f_negra"]),
    ("Internações por leito e caráter", ["f_leito_psiq", "f_leito_sm_hg", "f_leito_outro", "f_urgencia",
                                         "f_eletiva", "f_fora_mun"]),
    ("Atenção nos CAPS", ["caps_usuarios", "caps_novos", "caps_usuarios_ad", "caps_usuarios_estresse",
                          "caps_usuarios_fem", "caps_usuarios_0_17", "caps_proced", "caps_crise", "caps_individual",
                          "caps_grupo", "caps_familiar", "caps_domiciliar", "caps_acolhimento"]),
    ("Desfechos-controle", ["nao_f", "ctrl_parto", "ctrl_apendicite"]),
]


def r(x, n=3):
    """Arredonda para o JSON; NaN vira null."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), n)


def registros(df: pd.DataFrame, colunas: dict[str, str], casas: int = 4) -> list[dict]:
    out = []
    for _, l in df.iterrows():
        d = {}
        for novo, velho in colunas.items():
            v = l[velho]
            d[novo] = r(v, casas) if isinstance(v, (float, np.floating)) else (int(v) if isinstance(v, (np.integer,)) else v)
        out.append(d)
    return out


def series_estrato(p: pd.DataFrame, desfechos: list[str]) -> dict:
    """Observado mensal (contagem e população) no estado e em cada categoria de exposição."""
    out = {}
    est = p.groupby("mes")[desfechos + ["pop_total"]].sum()
    cat = p.groupby(["exposicao_cat", "mes"], observed=True)[desfechos + ["pop_total"]].sum()
    for d in desfechos:
        out[d] = {"estado": {"n": est[d].astype(int).tolist(), "pop": est.pop_total.round().astype(int).tolist()}}
        for c in ESTRATOS[1:]:
            s = cat.loc[c]
            out[d][c] = {"n": s[d].astype(int).tolist(), "pop": s.pop_total.round().astype(int).tolist()}
    return out


def esperado(meses: list[str]) -> dict:
    """Esperado sem a enchente (e IC95%) por desfecho, estrato e modelo, alinhado aos meses pós-enchente."""
    e = pd.read_csv(RESULTADOS / "01_contrafactual" / "esperado_mensal.csv")
    e["mes"] = pd.to_datetime(e.mes).dt.strftime("%Y-%m")
    out: dict = {}
    for (d, s, m), g in e.groupby(["desfecho", "estrato", "modelo"]):
        g = g.sort_values("mes")
        out.setdefault(d, {}).setdefault(s, {})[m] = {
            "inicio": meses.index(g.mes.iloc[0]),
            "esp": [r(v, 2) for v in g.esperado], "inf": [r(v, 2) for v in g.ic_inf], "sup": [r(v, 2) for v in g.ic_sup],
        }
    return out


def periodos_contrafactual() -> list[dict]:
    t = pd.read_csv(RESULTADOS / "01_contrafactual" / "resumo_periodos.csv")
    t["periodo"] = t.periodo.str.split(" ").str[0].replace({"23": "23 meses"})
    return registros(t, {"desfecho": "desfecho", "estrato": "estrato", "modelo": "modelo", "periodo": "periodo",
                         "obs": "observado", "esp": "esperado", "oe": "razao_oe", "inf": "razao_ic_inf",
                         "sup": "razao_ic_sup", "excesso": "excesso", "p": "p_bicaudal"})


def validacao() -> list[dict]:
    v = pd.read_csv(RESULTADOS / "01_contrafactual" / "validacao_placebo.csv")
    v = v[v.modelo == "ensemble"]
    g = v.groupby(["desfecho", "estrato"]).agg(erro=("erro_pct_12m", "mean"), erro_abs=("erro_abs_medio_mensal_pct", "mean"),
                                               cobre=("cobre_12m", "sum"), cortes=("cobre_12m", "size")).reset_index()
    return registros(g, {"desfecho": "desfecho", "estrato": "estrato", "erro": "erro", "erro_abs": "erro_abs",
                         "cobre": "cobre", "cortes": "cortes"}, 2)


def dose_resposta() -> dict:
    pasta = RESULTADOS / "02_dose_resposta"
    ev = pd.read_csv(pasta / "coef_evento.csv")
    ev = ev[ev.exposicao == "continua_10pp"].copy()
    ev["k"] = ev.termo.str.extract(r"k::(-?\d+):").astype(int)
    pe = pd.read_csv(pasta / "coef_periodo.csv")
    partes = pe.termo.str.extract(r"(?:periodo|placebo)::(\w+):(\w+)")
    pe["periodo"], pe["grupo"] = partes[0], partes[1].replace({"x": "10pp", "e_1_10": "1-<10%", "e_10": ">=10%"})
    pt = pd.read_csv(pasta / "pretendencia.csv")
    col = {"desfecho": "desfecho", "espec": "especificacao", "rr": "rr", "inf": "rr_ic_inf", "sup": "rr_ic_sup", "p": "p"}
    return {
        "evento": registros(ev, {**col, "k": "k"}),
        "periodo": registros(pe, {**col, "exposicao": "exposicao", "periodo": "periodo", "grupo": "grupo"}),
        "pretendencia": registros(pt, {"desfecho": "desfecho", "espec": "especificacao", "exposicao": "exposicao",
                                       "p": "p_pretendencia"}),
    }


def robustez() -> dict:
    s = pd.read_csv(RESULTADOS / "03_robustez" / "sdid.csv")
    m = pd.read_csv(RESULTADOS / "03_robustez" / "caps_margens_extensiva_intensiva.csv")
    m["margem"] = m.margem.str.split(":").str[0]
    return {
        "sdid": registros(s, {"desfecho": "desfecho", "periodo": "periodo", "att": "att_taxa_100mil_mes",
                              "att_inf": "att_ic_inf", "att_sup": "att_ic_sup", "rel": "efeito_relativo_pct",
                              "rel_inf": "efeito_rel_ic_inf_pct", "rel_sup": "efeito_rel_ic_sup_pct"}, 2),
        "margens": registros(m, {"margem": "margem", "periodo": "termo", "est": "estimativa", "inf": "ic_inf",
                                 "sup": "ic_sup", "p": "p", "caps": "caps"}),
    }


def desigualdades() -> dict:
    pasta = RESULTADOS / "04_desigualdades"
    t = pd.read_csv(pasta / "desigualdades_rt.csv")
    d = pd.read_csv(pasta / "desigualdades_descritivo.csv")
    return {
        "rt": registros(t, {c: c for c in t.columns}),
        "descritivo": registros(d.rename(columns={
            "internações F: % pretos ou pardos": "f_negra", "internações F: % mulheres": "f_fem",
            "CAPS: % usuários pretos ou pardos": "caps_negra", "CAPS: % usuárias mulheres": "caps_fem"}),
            {"cat": "exposicao_cat", "f_negra": "f_negra", "f_fem": "f_fem", "caps_negra": "caps_negra",
             "caps_fem": "caps_fem"}, 1),
    }


def municipios(p: pd.DataFrame) -> tuple[list[dict], dict]:
    exp = pd.read_csv(PROCESSADOS / "exposicao_municipio.csv", dtype={"mun_res": str})
    ter = pd.read_csv(PROCESSADOS / "territorio_municipios.csv", dtype={"mun_res": str, "mun7": str})
    m = exp.drop(columns="mun7").merge(ter[["mun_res", "mun7", "regiao_imediata", "regiao_intermediaria"]],
                                      on="mun_res", how="left", validate="one_to_one")
    # População estimada em maio de 2024, a mesma base dos totais citados no artigo
    pop24 = p[p.mes == "2024-05-01"].groupby("mun_res").pop_total.sum().round().astype(int)
    m["pop"] = m.mun_res.map(pop24.rename(index=str))
    m = m.sort_values("nome")
    lista = registros(m, {"cod": "mun_res", "cod7": "mun7", "nome": "nome", "reg_imediata": "regiao_imediata",
                          "reg_intermediaria": "regiao_intermediaria", "pct": "pct_pop_afetada",
                          "pop_afetada": "pop_afetada", "cat": "exposicao_cat", "pop": "pop",
                          "na_ibge": "na_base_ibge"}, 3)
    q = p.assign(mun_res=p.mun_res.astype(str)).sort_values(["mun_res", "mes"])
    series = {"pop": {c: g.pop_total.round().astype(int).tolist() for c, g in q.groupby("mun_res")}}
    for d in DESFECHOS_MUN:
        series[d] = {c: g[d].astype(int).tolist() for c, g in q.groupby("mun_res")}
    return lista, series


def orientar_para_d3(arquivo: Path) -> None:
    """O D3 quer o anel externo no sentido horário e os buracos no anti-horário (o inverso do
    GeoJSON RFC 7946, que o mapshaper grava). Com o sentido trocado, cada polígono cobre o globo."""
    g = json.loads(arquivo.read_text(encoding="utf-8"))

    def area(anel):  # > 0: anti-horário (x = longitude, y = latitude)
        return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(anel, anel[1:] + anel[:1])) / 2

    trocados = 0
    for f in g["features"]:
        geo = f["geometry"]
        for poligono in [geo["coordinates"]] if geo["type"] == "Polygon" else geo["coordinates"]:
            for i, anel in enumerate(poligono):
                if (area(anel) > 0) == (i == 0):
                    anel.reverse()
                    trocados += 1
    if trocados:
        arquivo.write_text(json.dumps(g, separators=(",", ":")), encoding="utf-8")
    print(f"malha: {trocados} anéis reorientados para o D3")


def malha(destino: Path) -> None:
    if destino.exists():
        orientar_para_d3(destino)
        return
    exe = shutil.which("mapshaper") or shutil.which("npx")
    if not exe:
        print("AVISO: sem mapshaper/npx; o mapa do painel ficará vazio. Veja o comando no início deste script.")
        return
    with tempfile.TemporaryDirectory() as tmp:
        zipfile.ZipFile(BRUTOS / "malha_ibge_2022" / "RS_Municipios_2022.zip").extractall(tmp)
        cmd = ([exe] if exe.endswith("mapshaper") else [exe, "--yes", "mapshaper@0.6.102"]) + [
            str(Path(tmp) / "RS_Municipios_2022.shp"), "encoding=utf8", "-simplify", "2%", "keep-shapes",
            "-filter-fields", "CD_MUN", "-o", "format=geojson", "precision=0.0005", str(destino)]
        subprocess.run(cmd, check=True)
    orientar_para_d3(destino)


def destaques(cf: list[dict], dr: dict, rob: dict, munis: list[dict]) -> dict:
    """Números da visão geral, lidos dos resultados (os mesmos citados no artigo)."""
    def oe(d, s, per):
        x = next(l for l in cf if l["desfecho"] == d and l["estrato"] == s and l["modelo"] == "ensemble" and l["periodo"] == per)
        return {k: x[k] for k in ("obs", "esp", "oe", "inf", "sup")}

    def rt(d, per, espec="principal"):
        x = next(l for l in dr["periodo"] if l["desfecho"] == d and l["espec"] == espec and l["exposicao"] == "continua_10pp"
                 and l["periodo"] == per)
        return {k: x[k] for k in ("rr", "inf", "sup", "p")}

    sd = next(l for l in rob["sdid"] if l["desfecho"] == "caps_usuarios" and l["periodo"] == "agudo")
    afet = [m for m in munis if m["na_ibge"]]  # municípios com área atingida na planilha do IBGE
    alto = [m for m in munis if m["cat"] == ">=10%"]
    return {
        "pop_afetada": int(sum(m["pop_afetada"] or 0 for m in munis)), "mun_afetados": len(afet),
        "mun_10": len(alto), "pop_10": int(sum(m["pop"] or 0 for m in alto)),
        "caps_oe_agudo_10": oe("caps_usuarios", ">=10%", "agudo"),
        "caps_oe_23_10": oe("caps_usuarios", ">=10%", "23 meses"),
        "caps_rt_agudo": rt("caps_usuarios", "agudo"),
        "caps_sdid_agudo": {"rel": sd["rel"], "inf": sd["rel_inf"], "sup": sd["rel_sup"]},
        "f_oe_23_estado": oe("f_total", "estado", "23 meses"),
        "f_rt_agudo": rt("f_total", "agudo"),
        "psic_oe_agudo_10": oe("f_psicoticos", ">=10%", "agudo"),
        "parto_rt_agudo": rt("ctrl_parto", "agudo"),
    }


def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    p = carregar_painel()
    p = p[(p.mes >= INICIO_ESTUDO) & (p.mes <= FIM_ESTUDO)]
    meses = sorted(p.mes.dt.strftime("%Y-%m").unique())
    cf_desf = sorted(pd.read_csv(RESULTADOS / "01_contrafactual" / "resumo_periodos.csv").desfecho.unique(),
                     key=lambda d: [x for _, g in GRUPOS for x in g].index(d))
    cf = periodos_contrafactual()
    dr = dose_resposta()
    rob = robustez()
    lista, smun = municipios(p)
    dados = {
        "gerado": date.today().isoformat(), "meses": meses, "inicio_enchente": "2024-05",
        "rotulos": {k: ROTULOS.get(k, k) for _, g in GRUPOS for k in g},
        "grupos": [{"nome": n, "desfechos": g} for n, g in GRUPOS],
        "desfechos_contrafactual": cf_desf, "desfechos_municipio": DESFECHOS_MUN,
        "contrafactual": {"observado": series_estrato(p, cf_desf), "esperado": esperado(meses),
                          "periodos": cf, "validacao": validacao()},
        "dose": dr, "robustez": rob, "desigualdades": desigualdades(),
        "municipios": lista,
        "destaques": destaques(cf, dr, rob, lista),
    }
    # Os dados vão como scripts (window.PAINEL_*), não como JSON lido por fetch: assim o painel abre
    # direto do arquivo (file://) e passa pelo proxy do anonymous.4open.science, que barra .json/.geojson.
    malha(SAIDA / "municipios.geojson")
    geo = json.loads((SAIDA / "municipios.geojson").read_text(encoding="utf-8"))
    for nome, var, obj in [("painel", "PAINEL_DADOS", dados), ("series_municipio", "PAINEL_SERIES", smun),
                           ("municipios", "PAINEL_GEO", geo)]:
        arq = SAIDA / f"{nome}.js"
        arq.write_text(f"window.{var}=" + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + ";\n",
                       encoding="utf-8")
        print(f"{arq.relative_to(RAIZ)}: {arq.stat().st_size / 1e6:.2f} MB")
    for velho in ("painel.json", "series_municipio.json"):  # formato antigo
        (SAIDA / velho).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
