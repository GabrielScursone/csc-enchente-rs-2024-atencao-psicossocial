"""Produção dos CAPS (SIA/SUS, RAAS psicossocial) por município de residência × mês de atendimento.

PLANO_ANALISE.md, seção 11 (Emenda 1). Uma linha do arquivo PS é um procedimento de uma RAAS
(um usuário em um CAPS num mês). Medidas:
  caps_usuarios            Σ QTDPCN: usuários atendidos (uma RAAS por usuário por CAPS por mês;
                           "quantidade de pacientes" do TabNet)
  caps_novos               usuários cujo acompanhamento começou no próprio mês (DT_INICIO)
  caps_usuarios_ad/_estresse/_fem/_masc/_0_17   recortes de usuários (CID F10–F19, F40–F48, sexo, 0–17)
  caps_usuarios_branca/_negra/_raca_ign   raça/cor (preta + parda = negra); sem informação até 2023
  caps_proced              Σ PA_QTDPRO: procedimentos produzidos; e por tipo (crise, individual etc.)
Também: oferta (CAPS com produção, pelo município onde o CAPS fica) e completude por atraso
(mês de atendimento → mês de processamento).

Entradas: dados/brutos/sia_ps_rs_AAAA.zip. Saídas em dados/processados/:
  painel_caps_municipio_mes.parquet, oferta_caps_municipio_mes.parquet,
  producao_caps_estabelecimento_mes.parquet (CAPS × mês, para as margens extensiva e intensiva),
  completude_caps_por_atraso.csv, qualidade_caps.json
"""
from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import BRUTOS, FIM_ESTUDO, INICIO_ESTUDO, INTERMED, PROCESSADOS, ler_dbf  # noqa: E402

COLS = ["UFMUN", "CNES_EXEC", "DT_PROCESS", "DT_ATEND", "TPIDADEPAC", "IDADEPAC", "SEXOPAC", "MUNPAC",
        "CIDPRI", "DT_INICIO", "PA_PROC_ID", "PA_QTDPRO", "QTDPCN", "RACACOR"]
PROCEDIMENTOS = {  # SIGTAP, grupo 03.01.08
    "caps_crise": ["0301080291"],                      # atenção às situações de crise
    "caps_individual": ["0301080208"],                 # atendimento individual em CAPS
    "caps_grupo": ["0301080216"],                      # atendimento em grupo em CAPS
    "caps_familiar": ["0301080224"],                   # atendimento familiar em CAPS
    "caps_domiciliar": ["0301080240"],                 # atendimento domiciliar (usuários e/ou familiares)
    "caps_acolhimento": ["0301080194", "0301080020", "0301080038"],  # acolhimento diurno, noturno, 3º turno
}


def ler_ps(zp: Path, membro: str) -> pd.DataFrame:
    import readdbc

    with zipfile.ZipFile(zp) as z, tempfile.TemporaryDirectory(dir=INTERMED) as tmp:
        dbc = Path(tmp) / membro
        dbc.write_bytes(z.read(membro))
        dbf = dbc.with_suffix(".dbf")
        readdbc.dbc2dbf(str(dbc), str(dbf))
        return ler_dbf(dbf, COLS)


def indicadores(df: pd.DataFrame) -> pd.DataFrame:
    usu = pd.to_numeric(df.QTDPCN, errors="coerce").fillna(0).to_numpy()
    qtd = pd.to_numeric(df.PA_QTDPRO, errors="coerce").fillna(0).to_numpy()
    cid3 = df.CIDPRI.str[:3]
    idade = pd.to_numeric(df.IDADEPAC, errors="coerce").where(df.TPIDADEPAC == "4", 0)
    idade = idade.where(df.TPIDADEPAC != "5", idade + 100)
    novo = (df.DT_INICIO.str[:6] == df.DT_ATEND).to_numpy()
    out = {
        "caps_usuarios": usu,
        "caps_novos": usu * novo,
        "caps_usuarios_ad": usu * cid3.between("F10", "F19").to_numpy(),
        "caps_usuarios_estresse": usu * cid3.between("F40", "F48").to_numpy(),
        "caps_usuarios_fem": usu * (df.SEXOPAC == "F").to_numpy(),
        "caps_usuarios_masc": usu * (df.SEXOPAC == "M").to_numpy(),
        # raça/cor (01 branca, 02 preta, 03 parda; 99 = sem informação, 30% em 2015 e 0% a partir de 2024)
        "caps_usuarios_branca": usu * (df.RACACOR == "01").to_numpy(),
        "caps_usuarios_negra": usu * df.RACACOR.isin(["02", "03"]).to_numpy(),
        "caps_usuarios_raca_ign": usu * ~df.RACACOR.isin(["01", "02", "03", "04", "05"]).to_numpy(),
        "caps_usuarios_0_17": usu * (idade < 18).to_numpy(),
        "caps_proced": qtd,
    }
    for nome, cods in PROCEDIMENTOS.items():
        out[nome] = qtd * df.PA_PROC_ID.isin(cods).to_numpy()
    return pd.DataFrame(out, index=df.index)


def main() -> None:
    zips = sorted(BRUTOS.glob("sia_ps_rs_20??.zip"))
    if not zips:
        raise SystemExit("sem sia_ps_rs_AAAA.zip: rode 01_baixar_dados.py --so ps")
    partes, oferta, atraso = [], [], []
    q = {"arquivos": 0, "registros": 0, "registros_nao_residentes_rs": 0}
    for zp in zips:
        with zipfile.ZipFile(zp) as z:
            membros = sorted(m for m in z.namelist() if m.upper().endswith(".DBC"))
        for m in membros:
            df = ler_ps(zp, m)
            q["arquivos"] += 1
            q["registros"] += len(df)
            oferta.append(df.assign(usu=pd.to_numeric(df.QTDPCN, errors="coerce").fillna(0))
                          .groupby(["UFMUN", "DT_ATEND", "CNES_EXEC"]).usu.sum().reset_index())
            res = df.MUNPAC.str[:2] == "43"
            q["registros_nao_residentes_rs"] += int((~res).sum())
            df = df[res]
            ind = indicadores(df)
            ind["mun_res"] = pd.to_numeric(df.MUNPAC, errors="coerce")
            ind["dt_atend"] = df.DT_ATEND.values
            partes.append(ind.groupby(["mun_res", "dt_atend"]).sum())
            atraso.append(pd.DataFrame({"dt_atend": df.DT_ATEND.values, "dt_process": df.DT_PROCESS.values,
                                        "usu": ind.caps_usuarios.values}).groupby(["dt_atend", "dt_process"]).usu.sum())
        print(f"{zp.name}: ok", flush=True)

    p = pd.concat(partes).groupby(level=[0, 1]).sum().reset_index()
    p["mes"] = pd.to_datetime(p.dt_atend, format="%Y%m", errors="coerce")
    q["usuarios_mes_invalido"] = int(p.loc[p.mes.isna(), "caps_usuarios"].sum())
    fora = ~p.mes.between(INICIO_ESTUDO, FIM_ESTUDO)
    q["usuarios_fora_da_janela"] = int(p.loc[fora, "caps_usuarios"].sum())
    p = p[~fora].drop(columns="dt_atend")
    pop = pd.read_csv(PROCESSADOS / "populacao_municipio_ano.csv")
    validos = set(pop.mun_res)
    q["usuarios_municipio_invalido"] = int(p.loc[~p.mun_res.isin(validos), "caps_usuarios"].sum())
    p = p[p.mun_res.isin(validos)]
    meses = pd.date_range(INICIO_ESTUDO, FIM_ESTUDO, freq="MS")
    idx = pd.MultiIndex.from_product([sorted(validos), meses], names=["mun_res", "mes"])
    p = p.groupby(["mun_res", "mes"]).sum().reindex(idx, fill_value=0).reset_index()
    p.to_parquet(PROCESSADOS / "painel_caps_municipio_mes.parquet", index=False)

    of = pd.concat(oferta).groupby(["UFMUN", "DT_ATEND", "CNES_EXEC"]).usu.sum().reset_index()
    of["mes"] = pd.to_datetime(of.DT_ATEND, format="%Y%m", errors="coerce")
    of = of[of.mes.between(INICIO_ESTUDO, FIM_ESTUDO)]
    # Produção por CAPS × mês (todos os usuários, residentes ou não), para margens extensiva/intensiva
    of.assign(mun_local=pd.to_numeric(of.UFMUN), cnes=of.CNES_EXEC)[["cnes", "mun_local", "mes", "usu"]] \
        .rename(columns={"usu": "usuarios"}).to_parquet(PROCESSADOS / "producao_caps_estabelecimento_mes.parquet",
                                                         index=False)
    of = of.groupby([pd.to_numeric(of.UFMUN).rename("mun_local"), "mes"]).CNES_EXEC.nunique() \
        .rename("caps_ativos").reset_index()
    of.to_parquet(PROCESSADOS / "oferta_caps_municipio_mes.parquet", index=False)

    a = pd.concat(atraso).groupby(level=[0, 1]).sum().reset_index()
    a = a[a.dt_atend.str.match(r"^\d{6}$") & a.dt_process.str.match(r"^\d{6}$")]
    meses_atraso = (a.dt_process.str[:4].astype(int) * 12 + a.dt_process.str[4:].astype(int)) - \
                   (a.dt_atend.str[:4].astype(int) * 12 + a.dt_atend.str[4:].astype(int))
    a["ano"] = a.dt_atend.str[:4].astype(int)
    t = a.assign(atraso=meses_atraso.clip(lower=0, upper=13)).pivot_table(index="ano", columns="atraso",
                                                                          values="usu", aggfunc="sum").fillna(0)
    t = (t.cumsum(axis=1).div(t.sum(axis=1), axis=0) * 100).round(2).loc[2016:2023]
    t.to_csv(PROCESSADOS / "completude_caps_por_atraso.csv")

    est = p.drop(columns="mun_res").groupby("mes").sum()
    q |= {"municipios": int(p.mun_res.nunique()), "meses": len(meses),
          "municipios_com_algum_usuario": int((p.groupby("mun_res").caps_usuarios.sum() > 0).sum()),
          "usuarios_por_ano": est.caps_usuarios.groupby(est.index.year).sum().astype(int).to_dict(),
          "novos_por_ano": est.caps_novos.groupby(est.index.year).sum().astype(int).to_dict(),
          "caps_ativos_por_ano_media_mensal": of.groupby(of.mes.dt.year).caps_ativos.sum()
          .div(of.groupby(of.mes.dt.year).mes.nunique()).round(0).astype(int).to_dict(),
          "completude_media_2016_2023_pct_por_atraso": t.mean().round(2).to_dict()}
    (PROCESSADOS / "qualidade_caps.json").write_text(json.dumps(q, ensure_ascii=False, indent=1, default=str),
                                                     encoding="utf-8")
    print(json.dumps(q, ensure_ascii=False, indent=1, default=str))
    print(t.to_string())


if __name__ == "__main__":
    main()
