"""Converte cada RDRSAAMM.dbc em Parquet com as colunas de COLUNAS_RD (todos os registros).

Mantém todas as AIHs processadas no RS (residentes ou não); o filtro de residência fica
para 03_montar_base.py, que também registra quantas AIHs são de outros estados.
Saída: dados/intermediarios/rd/RDRSAAMM.parquet. Arquivos já convertidos a partir do
mesmo ZIP (mesmo tamanho e data) não são refeitos.

Uso: python -I codigo/02_extrair_rd.py [--refazer] [--processos N]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import zipfile
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import BRUTOS, COLUNAS_RD, INTERMED, ler_dbf  # noqa: E402

SAIDA = INTERMED / "rd"


def converter(zip_path: str, membro: str, refazer: bool) -> dict:
    import readdbc  # importado no processo filho

    zp = Path(zip_path)
    destino = SAIDA / membro.replace(".dbc", ".parquet")
    marca = {"zip": zp.name, "zip_bytes": zp.stat().st_size, "zip_mtime": int(zp.stat().st_mtime)}
    meta = destino.with_suffix(".json")
    if not refazer and destino.exists() and meta.exists() and \
            {k: json.loads(meta.read_text())[k] for k in marca} == marca:
        return {"arquivo": membro, "status": "já convertido", **json.loads(meta.read_text())}
    t0 = time.time()
    with tempfile.TemporaryDirectory(dir=INTERMED) as tmp:
        dbc = Path(tmp) / membro
        with zipfile.ZipFile(zp) as z:
            dbc.write_bytes(z.read(membro))
        dbf = dbc.with_suffix(".dbf")
        readdbc.dbc2dbf(str(dbc), str(dbf))
        df = ler_dbf(dbf, COLUNAS_RD)
    df = df[COLUNAS_RD]
    tmp_pq = destino.with_suffix(".parquet.parcial")
    df.to_parquet(tmp_pq, index=False, compression="zstd")
    tmp_pq.replace(destino)
    info = {**marca, "registros": len(df), "residentes_rs": int((df.MUNIC_RES.str[:2] == "43").sum()),
            "cmpt": sorted(set(df.ANO_CMPT + df.MES_CMPT)), "segundos": round(time.time() - t0, 1)}
    meta.write_text(json.dumps(info, ensure_ascii=False))
    return {"arquivo": membro, "status": "convertido", **info}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refazer", action="store_true")
    ap.add_argument("--processos", type=int, default=3)
    a = ap.parse_args()
    SAIDA.mkdir(parents=True, exist_ok=True)
    tarefas = []
    for z in sorted(BRUTOS.glob("sih_sus_rs_20??.zip")):
        with zipfile.ZipFile(z) as zf:
            tarefas += [(str(z), m, a.refazer) for m in sorted(zf.namelist()) if m.upper().endswith(".DBC")]
    print(f"{len(tarefas)} arquivos mensais em {len({t[0] for t in tarefas})} ZIPs", flush=True)
    res = []
    with ProcessPoolExecutor(max_workers=a.processos, mp_context=mp.get_context("fork")) as ex:
        for r in ex.map(converter, *zip(*tarefas)):
            res.append(r)
            print(f"{r['arquivo']}: {r['status']}, {r['registros']} registros, cmpt {r['cmpt']}", flush=True)
    tab = pd.DataFrame(res)
    tab.to_csv(SAIDA / "_conversao.csv", index=False)
    esperado = {t[1][4:8] for t in tarefas}
    obtido = {c[2:] for cs in tab.cmpt for c in cs}
    if esperado != obtido:
        raise SystemExit(f"competências divergentes: arquivo sem dado {sorted(esperado - obtido)}, "
                         f"dado sem arquivo {sorted(obtido - esperado)}")
    print(f"ok: {tab.registros.sum():,} registros; {tab.residentes_rs.sum():,} de residentes do RS")


if __name__ == "__main__":
    main()
