"""Roda a análise inteira em ordem: download → extração → base → população/exposição →
contrafactual → dose-resposta → robustez (SDID) → figuras → tabelas → manuscrito (Word) → entrega (ZIP). Etapas podem ser escolhidas com --etapas.

Uso:
  .venv/bin/python <pasta da análise>/rodar.py
  .venv/bin/python <pasta da análise>/rodar.py --etapas 05,06,07
A etapa 11 (manuscrito) é pulada quando a pasta manuscrito/ não existe (repositório público).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ETAPAS = {
    "01": "01_baixar_dados.py", "02": "02_extrair_rd.py", "03": "03_montar_base.py", "03b": "03b_montar_caps.py",
    "04": "04_populacao_exposicao.py", "05": "05_contrafactual.py", "06": "06_dose_resposta.py",
    "07": "07_figuras.py", "08": "08_tabelas.py", "09": "09_robustez_sdid.py", "10": "10_entrega.py",
    "11": "manuscrito (preparar_manuscrito.py + gerar_docx.js)", "12": "12_desigualdades.py",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--etapas", default="01,02,03,04,03b,05,06,09,12,07,08,11,10",
                    help="ordem de execução; 03b (CAPS) usa a população de 04; 09 roda antes de 07 e 08")
    a = ap.parse_args()
    for e in a.etapas.split(","):
        if e == "11" and not (RAIZ / "manuscrito").exists():
            print("\n===== 11 pulada: sem a pasta manuscrito/", flush=True)
            continue
        t = time.time()
        print(f"\n===== {e} {ETAPAS[e]}", flush=True)
        if e == "11":  # manuscrito: texto + tabelas (Python) e Word (Node; requer npm install em manuscrito/)
            r = subprocess.run([sys.executable, "-I", str(RAIZ / "manuscrito" / "preparar_manuscrito.py")], cwd=RAIZ)
            if not r.returncode:
                r = subprocess.run(["node", "gerar_docx.js"], cwd=RAIZ / "manuscrito")
        else:
            r = subprocess.run([sys.executable, "-I", str(RAIZ / "codigo" / ETAPAS[e])], cwd=RAIZ)
        if r.returncode:
            raise SystemExit(f"etapa {e} falhou (código {r.returncode})")
        print(f"===== {e} concluída em {time.time() - t:.0f} s", flush=True)


if __name__ == "__main__":
    main()
