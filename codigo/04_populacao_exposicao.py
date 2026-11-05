"""População (SVS) por município × mês e exposição à enchente (IBGE, mancha v3) por município.

Saídas em dados/processados/:
- populacao_municipio_ano.csv: população por município de residência (6 dígitos, como no SIH),
  ano, sexo e faixa etária. 2026 repete 2025 (última estimativa publicada).
- populacao_municipio_mes.parquet: interpolação linear entre os meios de ano (1º de julho);
  antes do primeiro e depois do último meio de ano, fica constante.
- exposicao_municipio.csv: % da população na área afetada, estabelecimentos de saúde
  afetados e categorias definidas no PLANO_ANALISE.md (<1%, 1–<10%, ≥10%).
"""
from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import BRUTOS, FIM_ESTUDO, INICIO_ESTUDO, INTERMED, PROCESSADOS, ler_dbf  # noqa: E402

FAIXAS = {"0_17": (0, 17), "18_39": (18, 39), "40_59": (40, 59), "60m": (60, 200)}
XLSX_IBGE = (BRUTOS / "exposicao_ibge_areas_afetadas" /
             "Dados_Agregados_para_as_Areas_Afetadas_Municipios_do_RS_GTCasaCivil_26jun24.xlsx")


def populacao_anual() -> pd.DataFrame:
    linhas = []
    for z in sorted((BRUTOS / "populacao_svs").glob("POPSBR??.zip")):
        with zipfile.ZipFile(z) as zf, tempfile.TemporaryDirectory(dir=INTERMED) as tmp:
            nomes = [n for n in zf.namelist() if n.lower().endswith(".dbf")]
            if len(nomes) != 1:
                raise SystemExit(f"{z.name}: esperado 1 DBF, há {nomes}")
            zf.extract(nomes[0], tmp)
            df = ler_dbf(Path(tmp) / nomes[0])
        df.columns = df.columns.str.upper()  # 2025 vem em minúsculas
        df = df[df.COD_MUN.str[:2] == "43"].copy()
        df["idade"] = pd.to_numeric(df.IDADE)
        df["pop"] = pd.to_numeric(df.POP)
        df["mun_res"] = df.COD_MUN.str[:6].astype(int)
        df["ano"] = df.ANO.astype(int)
        g = df.groupby(["mun_res", "ano"])
        out = g["pop"].sum().rename("pop_total").to_frame()
        out["pop_masc"] = df[df.SEXO == "1"].groupby(["mun_res", "ano"])["pop"].sum()
        out["pop_fem"] = df[df.SEXO == "2"].groupby(["mun_res", "ano"])["pop"].sum()
        for k, (a, b) in FAIXAS.items():
            out[f"pop_{k}"] = df[df.idade.between(a, b)].groupby(["mun_res", "ano"])["pop"].sum()
        linhas.append(out.fillna(0).reset_index())
        print(f"{z.name}: {out.shape[0]} municípios do RS, pop {int(out.pop_total.sum()):,}")
    pop = pd.concat(linhas, ignore_index=True)
    ult = pop[pop.ano == pop.ano.max()].copy()
    for ano in range(pop.ano.max() + 1, FIM_ESTUDO.year + 1):
        pop = pd.concat([pop, ult.assign(ano=ano)], ignore_index=True)
    soma = pop.filter(like="pop_").drop(columns="pop_total")
    assert np.allclose(soma[["pop_masc", "pop_fem"]].sum(axis=1), pop.pop_total)
    assert np.allclose(soma[[f"pop_{k}" for k in FAIXAS]].sum(axis=1), pop.pop_total)
    return pop.sort_values(["mun_res", "ano"]).reset_index(drop=True)


def populacao_mensal(pop: pd.DataFrame) -> pd.DataFrame:
    meses = pd.date_range(INICIO_ESTUDO, FIM_ESTUDO, freq="MS")
    cols = [c for c in pop.columns if c.startswith("pop_")]
    partes = []
    for mun, d in pop.groupby("mun_res"):
        x_ano = pd.to_datetime(d.ano.astype(str) + "-07-01").values.astype("int64")
        x_mes = meses.values.astype("int64")
        m = pd.DataFrame({"mun_res": mun, "mes": meses})
        for c in cols:
            m[c] = np.interp(x_mes, x_ano, d[c].values.astype(float))
        partes.append(m)
    return pd.concat(partes, ignore_index=True)


def exposicao(municipios: pd.Index) -> pd.DataFrame:
    df = pd.read_excel(XLSX_IBGE, sheet_name=0, header=None, skiprows=2).iloc[:, [0, 1, 2, 3, 8, 11, 12, 17]]
    df.columns = ["mun7", "nome", "pop_afetada", "dom_afetados", "estab_saude_afetados",
                  "pop_censo2022", "dom_censo2022", "estab_saude_censo2022"]
    df = df[pd.to_numeric(df.mun7, errors="coerce").notna()].copy()
    for c in df.columns.drop("nome"):
        df[c] = pd.to_numeric(df[c])
    df["mun_res"] = (df.mun7 // 10).astype(int)
    total = int(df.pop_afetada.sum())
    if total != 876564:
        raise SystemExit(f"soma da população afetada {total} difere da versão conferida (876.564)")
    e = pd.DataFrame({"mun_res": municipios}).merge(df, on="mun_res", how="left")
    e["na_base_ibge"] = e.mun7.notna()
    for c in ["pop_afetada", "dom_afetados", "estab_saude_afetados"]:
        e[c] = e[c].fillna(0)
    e["pct_pop_afetada"] = 100 * e.pop_afetada / e.pop_censo2022
    e.loc[~e.na_base_ibge, "pct_pop_afetada"] = 0.0
    e["estab_saude_af_10mil"] = 1e4 * e.estab_saude_afetados / e.pop_censo2022
    e.loc[~e.na_base_ibge, "estab_saude_af_10mil"] = 0.0
    e["exposicao_cat"] = pd.cut(e.pct_pop_afetada, [-np.inf, 1, 10, np.inf], right=False,
                                labels=["<1%", "1-<10%", ">=10%"])
    return e


def regioes_saude() -> pd.DataFrame | None:
    """Regiões e macrorregiões de saúde da base territorial do DATASUS (None se não baixada)."""
    zp = BRUTOS / "territorio_datasus" / "base_territorial_out25.zip"
    if not zp.exists():
        return None
    raise NotImplementedError("ler a base territorial do DATASUS (formato a conferir)")


def territorio() -> pd.DataFrame:
    """Nome e área (malha IBGE 2022), regiões geográficas (IBGE 2017) e regiões de saúde (DATASUS)."""
    with zipfile.ZipFile(BRUTOS / "malha_ibge_2022" / "RS_Municipios_2022.zip") as zf, \
            tempfile.TemporaryDirectory(dir=INTERMED) as tmp:
        zf.extract("RS_Municipios_2022.dbf", tmp)
        m = ler_dbf(Path(tmp) / "RS_Municipios_2022.dbf", codificacao="utf-8")
    m = m[~m.CD_MUN.isin(["4300001", "4300002"])]  # Lagoa Mirim e Lagoa dos Patos (corpos d'água)
    t = pd.DataFrame({"mun7": m.CD_MUN.astype(int), "nome": m.NM_MUN,
                      "area_km2": pd.to_numeric(m.AREA_KM2)})
    t["mun_res"] = t.mun7 // 10
    r = pd.read_excel(BRUTOS / "regioes_ibge" / "regioes_geograficas_composicao_por_municipios_2017_20180911.xlsx")
    r = r[r.CD_GEOCODI.astype(str).str.startswith("43")]
    t = t.merge(r.rename(columns={"CD_GEOCODI": "mun7", "nome_rgi": "regiao_imediata",
                                  "nome_rgint": "regiao_intermediaria"})[
        ["mun7", "regiao_imediata", "regiao_intermediaria"]], on="mun7", how="left", validate="one_to_one")
    rs = regioes_saude()
    if rs is not None:
        t = t.merge(rs, on="mun_res", how="left", validate="one_to_one")
        t["fonte_macrorregiao"] = "DATASUS (macrorregião de saúde)"
    else:  # base territorial do DATASUS indisponível: regiões do IBGE
        t["regiao_saude"], t["macrorregiao"] = t.regiao_imediata, t.regiao_intermediaria
        t["fonte_macrorregiao"] = "IBGE (região geográfica intermediária)"
    faltam = t[t[["regiao_intermediaria", "regiao_saude", "macrorregiao"]].isna().any(axis=1)]
    if len(t) != 497 or len(faltam):
        raise SystemExit(f"território: {len(t)} municípios; sem região: {faltam.nome.tolist()}")
    return t


def main() -> None:
    terr = territorio()
    terr.to_csv(PROCESSADOS / "territorio_municipios.csv", index=False)
    print(f"território: {len(terr)} municípios, {terr.regiao_saude.nunique()} regiões de saúde, "
          f"{terr.macrorregiao.nunique()} macrorregiões")
    pop = populacao_anual()
    pop.to_csv(PROCESSADOS / "populacao_municipio_ano.csv", index=False)
    popm = populacao_mensal(pop)
    popm.to_parquet(PROCESSADOS / "populacao_municipio_mes.parquet", index=False)

    painel = pd.read_parquet(PROCESSADOS / "painel_municipio_mes.parquet", columns=["mun_res"])
    sem_pop = sorted(set(painel.mun_res.unique()) - set(pop.mun_res.unique()))
    print("códigos SIH sem população SVS (ignorados/antigos):", sem_pop)
    exp = exposicao(pd.Index(sorted(pop.mun_res.unique())))
    exp["nome"] = exp.mun_res.map(terr.set_index("mun_res").nome)  # nomes dos 497 (malha IBGE)
    exp.to_csv(PROCESSADOS / "exposicao_municipio.csv", index=False)
    print(exp.exposicao_cat.value_counts().sort_index().to_string())
    print("população 2024 por categoria:",
          pop[pop.ano == 2024].merge(exp, on="mun_res").groupby("exposicao_cat", observed=True)
          .pop_total.sum().astype(int).to_dict())


if __name__ == "__main__":
    main()
