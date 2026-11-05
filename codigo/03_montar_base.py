"""Monta a base de internações pela data de internação e os painéis município × mês.

Regras (ver PLANO_ANALISE.md):
- Residentes do RS (MUNIC_RES começa com 43), AIH tipo 1 (IDENT=1). As AIHs de longa
  permanência (IDENT=5) continuam uma internação já contada e ficam fora.
- Data: DT_INTER (não a competência). Janela INICIO_ESTUDO–FIM_ESTUDO de comum.py.
- AIH repetida (mesmo N_AIH e IDENT=1 em mais de uma competência): fica a última apresentação.

Saídas em dados/processados/:
- internacoes_rs_aih.parquet: uma linha por internação (todas as causas), colunas compactas.
- painel_municipio_mes.parquet/.csv: contagens por município de residência × mês.
- serie_estado_mes.csv: as mesmas contagens somadas no estado.
- qualidade_base.json e completude_por_atraso.csv: números para o fluxograma e a nota de método.
"""
from __future__ import annotations

import gc
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import (AUTOLESAO, CONTROLES, FIM_ESTUDO, GRUPOS_F, INICIO_ESTUDO, INTERMED,  # noqa: E402
                   PROCESSADOS, ULTIMA_CMPT, entre)

COLS = ["ANO_CMPT", "MES_CMPT", "IDENT", "N_AIH", "MUNIC_RES", "MUNIC_MOV", "CNES", "DT_INTER",
        "DT_SAIDA", "DIAG_PRINC", "DIAGSEC1", "DIAGSEC2", "DIAGSEC3", "DIAGSEC4", "DIAGSEC5",
        "DIAGSEC6", "DIAGSEC7", "DIAGSEC8", "DIAGSEC9", "ESPEC", "CAR_INT", "SEXO", "NASC", "IDADE",
        "COD_IDADE", "RACA_COR", "DIAS_PERM", "MORTE", "VAL_TOT"]
SEC = [f"DIAGSEC{i}" for i in range(1, 10)]


def compactar(df: pd.DataFrame) -> pd.DataFrame:
    """Uma competência → colunas numéricas/categóricas, para caber em memória."""
    cid = df.DIAG_PRINC.str[:3]
    sec3 = df[SEC].apply(lambda s: s.str[:3])
    autoles = sec3.apply(lambda s: entre(s, AUTOLESAO)).any(axis=1) | entre(cid, AUTOLESAO)
    dt = pd.to_datetime(df.DT_INTER, format="%Y%m%d", errors="coerce")
    nasc = pd.to_datetime(df.NASC, format="%Y%m%d", errors="coerce")
    idade_nasc = np.floor((dt - nasc).dt.days / 365.25)
    idade_num = pd.to_numeric(df.IDADE, errors="coerce")
    idade_cod = np.select([df.COD_IDADE == "4", df.COD_IDADE == "5", df.COD_IDADE.isin(["2", "3"])],
                          [idade_num, idade_num + 100, 0], np.nan)
    idade = idade_nasc.where(idade_nasc.between(0, 120), idade_cod)
    return pd.DataFrame({
        "cmpt": (df.ANO_CMPT + df.MES_CMPT).astype("int32"),
        "ident": pd.to_numeric(df.IDENT, errors="coerce").astype("Int8"),
        "n_aih": pd.to_numeric(df.N_AIH, errors="coerce").astype("Int64"),
        "mun_res": pd.to_numeric(df.MUNIC_RES, errors="coerce").astype("Int32"),
        "mun_mov": pd.to_numeric(df.MUNIC_MOV, errors="coerce").astype("Int32"),
        "cnes": pd.to_numeric(df.CNES, errors="coerce").astype("Int32"),
        "dt_inter": dt,
        "dt_saida": pd.to_datetime(df.DT_SAIDA, format="%Y%m%d", errors="coerce"),
        "cid3": cid.astype("category"),
        "cid4": df.DIAG_PRINC.astype("category"),
        "autolesao": autoles.astype("int8"),
        "espec": df.ESPEC.astype("category"),
        "car_int": df.CAR_INT.astype("category"),
        "sexo": df.SEXO.map({"1": "M", "2": "F", "3": "F"}).astype("category"),
        "idade": idade.astype("float32"),
        "idade_divergente": ((idade_nasc - idade_cod).abs() > 1).astype("int8"),
        "raca": df.RACA_COR.map({"01": "branca", "02": "preta", "03": "parda", "04": "amarela",
                                 "05": "indigena"}).fillna("ignorada").astype("category"),
        "dias_perm": pd.to_numeric(df.DIAS_PERM, errors="coerce").astype("float32"),
        "morte": pd.to_numeric(df.MORTE, errors="coerce").fillna(0).astype("int8"),
        "val_tot": pd.to_numeric(df.VAL_TOT, errors="coerce").astype("float32"),
    })


def carregar() -> tuple[pd.DataFrame, dict]:
    arqs = sorted((INTERMED / "rd").glob("RDRS????.parquet"))
    partes, q = [], {"arquivos": len(arqs), "registros": 0, "nao_residentes_rs": 0}
    for a in arqs:
        df = pd.read_parquet(a, columns=COLS)
        q["registros"] += len(df)
        res = df.MUNIC_RES.str[:2] == "43"
        q["nao_residentes_rs"] += int((~res).sum())
        partes.append(compactar(df[res]))
    base = pd.concat(partes, ignore_index=True)
    for c in ["cid3", "cid4", "espec", "car_int", "sexo", "raca"]:
        base[c] = base[c].astype("category")
    q["primeira_cmpt"], q["ultima_cmpt"] = int(base.cmpt.min()), int(base.cmpt.max())
    if str(q["ultima_cmpt"]) != ULTIMA_CMPT:
        raise SystemExit(f"última competência {q['ultima_cmpt']} != {ULTIMA_CMPT} (rode 02_extrair_rd.py)")
    return base, q


def completude(base: pd.DataFrame) -> pd.DataFrame:
    """Distribuição do atraso internação → competência (AIH tipo 1), por ano de internação."""
    b = base[(base.ident == 1) & base.dt_inter.notna()]
    cm = (b.cmpt // 100) * 12 + b.cmpt % 100
    im = b.dt_inter.dt.year * 12 + b.dt_inter.dt.month
    atraso = (cm - im).clip(lower=0)
    t = pd.crosstab(b.dt_inter.dt.year, atraso.clip(upper=13))
    t = t.loc[2016:2023]  # anos com todas as competências posteriores observadas
    return (t.cumsum(axis=1).div(t.sum(axis=1), axis=0) * 100).round(2)


def na_categoria(s: pd.Series, cond) -> np.ndarray:
    """Aplica cond às categorias (não às 9 milhões de linhas) e devolve a máscara por linha."""
    cats = pd.Series(s.cat.categories.astype(str))
    m = np.append(np.asarray(cond(cats), dtype=bool), False)  # código −1 (ausente) → False
    return m[s.cat.codes.to_numpy()]


def eh_f(cid3: pd.Series) -> np.ndarray:
    return na_categoria(cid3, lambda c: c.str.match(r"^F\d\d$"))


def desfechos_gerais(b: pd.DataFrame) -> pd.DataFrame:
    """Indicadores calculados sobre todas as internações (contagens no painel)."""
    f = eh_f(b.cid3)
    d = {"todas_causas": np.ones(len(b), bool), "nao_f": ~f, "f_total": f,
         "autolesao": (b.autolesao == 1).to_numpy()}
    for k, faixa in CONTROLES.items():
        d[k] = na_categoria(b.cid3, lambda c, fx=faixa: entre(c, fx))
    return pd.DataFrame({k: v.astype("int8") for k, v in d.items()}, index=b.index)


def desfechos_f(b: pd.DataFrame) -> pd.DataFrame:
    """Recortes do capítulo F, calculados só sobre as internações com diagnóstico principal F."""
    cid3 = b.cid3.astype(str)
    d = {k: entre(cid3, faixa) for k, faixa in GRUPOS_F.items()}
    d["f_outros"] = ~np.logical_or.reduce([d[k] for k in GRUPOS_F])
    d["f_alcool"] = cid3 == "F10"
    d["f_estresse"] = cid3 == "F43"
    idade = b.idade
    d |= {
        "f_masc": b.sexo == "M", "f_fem": b.sexo == "F",
        "f_0_17": idade < 18, "f_18_39": idade.between(18, 39),
        "f_40_59": idade.between(40, 59), "f_60m": idade >= 60,
        "f_branca": b.raca == "branca", "f_negra": b.raca.isin(["preta", "parda"]),
        "f_indigena": b.raca == "indigena", "f_raca_ign": b.raca == "ignorada",
        "f_leito_psiq": b.espec == "05", "f_leito_sm_hg": b.espec == "87",
        "f_leito_outro": ~b.espec.isin(["05", "87"]),
        "f_urgencia": b.car_int != "01", "f_eletiva": b.car_int == "01",
        "f_fora_mun": (b.mun_mov != b.mun_res).fillna(False).astype(bool),
        "f_obito": b.morte == 1,
    }
    d["f_spa_masc"] = d["f_spa"] & (b.sexo == "M")
    d["f_spa_fem"] = d["f_spa"] & (b.sexo == "F")
    out = pd.DataFrame({k: np.asarray(v, dtype="int32") for k, v in d.items()}, index=b.index)
    out["f_dias_perm"] = b.dias_perm.fillna(0).astype("float64")
    return out


def main() -> None:
    PROCESSADOS.mkdir(parents=True, exist_ok=True)
    base, q = carregar()
    comp = completude(base)
    comp.to_csv(PROCESSADOS / "completude_por_atraso.csv")
    q["completude_media_2016_2023_pct_por_atraso_meses"] = comp.mean().round(2).to_dict()

    q["aih_tipo5_longa_permanencia"] = int((base.ident == 5).sum())
    b = base[base.ident == 1].copy()
    del base
    gc.collect()
    q["aih_tipo1"] = len(b)
    # AIH repetida: fica a última competência
    b = b.sort_values("cmpt")
    dup = b.duplicated("n_aih", keep="last")
    q["aih_tipo1_repetidas_removidas"] = int(dup.sum())
    b = b[~dup]
    q["dt_inter_invalida"] = int(b.dt_inter.isna().sum())
    fora = ~b.dt_inter.between(INICIO_ESTUDO, FIM_ESTUDO)
    q["fora_da_janela"] = int(fora.sum())
    b = b[~fora].copy()
    q["internacoes_na_janela"] = len(b)
    q["idade_ausente"] = int(b.idade.isna().sum())
    q["idade_nasc_vs_campo_idade_divergente"] = int(b.idade_divergente.sum())
    q["sexo_ausente"] = int(b.sexo.isna().sum())
    b["mes"] = b.dt_inter.dt.to_period("M").dt.to_timestamp()
    b = b.drop(columns=["idade_divergente"]).reset_index(drop=True)
    b.to_parquet(PROCESSADOS / "internacoes_rs_aih.parquet", index=False, compression="zstd")

    chave = [b.mun_res.to_numpy(), b.mes.to_numpy()]
    painel = desfechos_gerais(b).groupby(chave).sum()
    f = eh_f(b.cid3)
    bf = b[f]
    painel = painel.join(desfechos_f(bf).groupby([bf.mun_res.to_numpy(), bf.mes.to_numpy()]).sum(), how="left")
    painel.index.names = ["mun_res", "mes"]
    painel = painel.fillna(0)
    # Grade completa: municípios observados × todos os meses (zeros onde não houve internação)
    meses = pd.date_range(INICIO_ESTUDO, FIM_ESTUDO, freq="MS")
    idx = pd.MultiIndex.from_product([sorted(b.mun_res.dropna().unique()), meses], names=["mun_res", "mes"])
    painel = painel.reindex(idx, fill_value=0).reset_index()
    painel.to_parquet(PROCESSADOS / "painel_municipio_mes.parquet", index=False)
    painel.to_csv(PROCESSADOS / "painel_municipio_mes.csv", index=False)
    estado = painel.drop(columns="mun_res").groupby("mes").sum()
    estado.to_csv(PROCESSADOS / "serie_estado_mes.csv")

    q["municipios_no_painel"] = int(painel.mun_res.nunique())
    q["meses_no_painel"] = len(meses)
    q["f_total_janela"] = int(estado.f_total.sum())
    q["f_por_ano"] = estado.f_total.groupby(estado.index.year).sum().astype(int).to_dict()
    q["raca_ignorada_pct_F_por_ano"] = (
        bf.groupby(bf.mes.dt.year).raca
        .apply(lambda s: round(100 * (s == "ignorada").mean(), 1)).to_dict())
    (PROCESSADOS / "qualidade_base.json").write_text(
        json.dumps(q, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(q, ensure_ascii=False, indent=1, default=str))
    print(comp.to_string())


if __name__ == "__main__":
    main()
