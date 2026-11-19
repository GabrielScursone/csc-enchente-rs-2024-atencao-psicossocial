"""Roda a análise inteira em ordem: download → extração → base → população/exposição →
contrafactual → dose-resposta → robustez (SDID) → desigualdades → painel → figuras → tabelas →
verificações da revisão → figuras do manuscrito → Word (manuscrito e folha de rosto) → entrega (ZIP).
Etapas podem ser escolhidas com --etapas.

Uso:
  .venv/bin/python <pasta da análise>/rodar.py
  .venv/bin/python <pasta da análise>/rodar.py --etapas 05,06,07
  .venv/bin/python <pasta da análise>/rodar.py --etapas 15,16,18,10    # refazer figuras, Word e entrega
  .venv/bin/python <pasta da análise>/rodar.py --etapas 15,16,18 --idioma pt   # versão em português

O manuscrito submetido é em inglês, e esse é o idioma padrão das etapas 15, 16 e 18 (--idioma en).
A etapa 15 faz as Figuras 1 a 4 do manuscrito, compostas por painéis, em cores e em tons de cinza, com 15 cm
de largura e texto serifado de 9 pt (resultados/figuras/manuscrito/; Figure*_color e Figure*_gray em inglês,
Figura*_cor e Figura*_cinza em português). A etapa 15a, opcional e fora da ordem padrão, refaz a partir do Natural
Earth o mapa de localização da Figura 1A, que já está em dados_agregados/. Os arquivos Word saem sempre das etapas 16 (manuscrito) e 18 (folha
de rosto). A etapa 16 coloca cada figura e a Tabela 1 logo depois do parágrafo que as cita, nos pontos marcados
no texto com @figura e @tabela. O artigo não tem material suplementar: os resultados completos ficam neste
repositório. A etapa 11 chama as etapas 16 e 18. O gerador antigo (preparar_manuscrito.py + gerar_docx.js)
ficou como 11antigo e só serve para refazer o molde se as tabelas mudarem.

Em inglês, as etapas 16 e 18 usam manuscrito/manuscript_en.txt e manuscrito/title_page_data_en.json e gravam em
manuscrito/build_en/ (Manuscript_anonymous.docx, Manuscript_anonymous_grayscale.docx e Title_page.docx). Em
português, usam manuscrito/manuscrito.txt e manuscrito/folha_de_rosto_dados.json e gravam em
manuscrito/build_revisado/, com versão marcada em relação a manuscrito/anterior/, se existir. As duas usam
manuscrito/molde_2026-11-06/ (Word entregue em 06/11/2026, base de formatação e da Tabela 1). A pasta
manuscrito/ não está no repositório público, e essas etapas são puladas quando ela não existe.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
MANUSCRITO = RAIZ / "manuscrito"
MOLDE = MANUSCRITO / "molde_2026-11-06"
SAIDA_WORD = MANUSCRITO / "build_revisado"
SAIDA_EN = MANUSCRITO / "build_en"
REVISAO = RAIZ / "resultados" / "revisao"
FIGURAS_MANUSCRITO = RAIZ / "resultados" / "figuras" / "manuscrito"
ANTERIOR = MANUSCRITO / "anterior"

ETAPAS = {
    "01": "01_baixar_dados.py", "02": "02_extrair_rd.py", "03": "03_montar_base.py", "03b": "03b_montar_caps.py",
    "04": "04_populacao_exposicao.py", "05": "05_contrafactual.py", "06": "06_dose_resposta.py",
    "07": "07_figuras.py", "08": "08_tabelas.py", "09": "09_robustez_sdid.py", "10": "10_entrega.py",
    "11": "Word pelas etapas 16 e 18", "11antigo": "manuscrito (preparar_manuscrito.py + gerar_docx.js)",
    "12": "12_desigualdades.py", "13": "13_painel.py",
    "14": "14_analises_revisao.py", "14b": "14b_conferir_caps_sem_registro.py", "15a": "15a_mapa_localizacao.py",
    "15": "15_figuras_artigo.py",
    "16": "16_gerar_docx_revisado.py", "18": "18_folha_de_rosto_revisada.py",
}
PADRAO = "01,02,03,04,03b,05,06,09,12,13,07,08,10,14,14b,15,16,18,10"
WORD = {"16", "18", "11antigo"}


def base_publica() -> Path:
    """Pasta com os dados agregados e os resultados no formato público: a raiz (repositório público, com
    dados_agregados/) ou a pasta de entrega montada pela etapa 10 (5_dados_agregados/, 6_resultados_completos/)."""
    if (RAIZ / "dados_agregados").exists():
        return RAIZ
    entrega = RAIZ / "resultados" / "entrega_artigo"
    if not entrega.exists():
        raise SystemExit("etapas 14 e 15: rode antes a etapa 10, que monta os dados agregados da entrega")
    return entrega


def argumentos(e: str, idioma: str) -> list[str]:
    if e == "14":
        return [str(base_publica()), str(REVISAO)]
    if e == "15a":
        return [str(RAIZ)]
    if e == "15":
        return [str(base_publica()), str(FIGURAS_MANUSCRITO), idioma]
    if e == "16" and idioma == "en":
        a = [MOLDE / "Manuscrito_anonimo.docx", "-", MANUSCRITO / "manuscript_en.txt", FIGURAS_MANUSCRITO, SAIDA_EN]
        return [str(x) for x in a]
    if e == "18" and idioma == "en":
        a = [MOLDE / "Folha_de_rosto.docx", SAIDA_EN, SAIDA_EN / "Manuscript_anonymous.docx",
             MANUSCRITO / "title_page_data_en.json"]
        return [str(x) for x in a]
    if e == "16":
        # versão marcada: compara com o texto da entrega anterior (manuscrito/anterior/) ou com o molde
        anterior = ANTERIOR / "manuscrito.txt" if (ANTERIOR / "manuscrito.txt").exists() else MOLDE / "texto_fonte_manuscrito.txt"
        a = [MOLDE / "Manuscrito_anonimo.docx", anterior, MANUSCRITO / "manuscrito.txt", FIGURAS_MANUSCRITO, SAIDA_WORD]
        comentarios = MANUSCRITO / "comentarios_revisao.tsv"  # opcional: comentários na versão marcada
        return [str(x) for x in a + ([comentarios] if comentarios.exists() else [])]
    if e == "18":
        a = [MOLDE / "Folha_de_rosto.docx", SAIDA_WORD, SAIDA_WORD / "Manuscrito_anonimo_revisado.docx",
             MANUSCRITO / "folha_de_rosto_dados.json"]
        folha_anterior = ANTERIOR / "Folha_de_rosto_revisada.docx"  # opcional: base da versão marcada
        return [str(x) for x in a + ([folha_anterior] if folha_anterior.exists() else [])]
    return []


def pular(e: str, idioma: str) -> str | None:
    """Motivo para pular a etapa, ou None."""
    if e in WORD and not MANUSCRITO.exists():
        return "sem a pasta manuscrito/ (repositório público)"
    if e in {"16", "18"} and not MOLDE.exists():
        return f"sem o molde em {MOLDE.relative_to(RAIZ)}/ (copie para lá os Word e o texto entregues em 06/11/2026)"
    texto = "manuscript_en.txt" if idioma == "en" else "manuscrito.txt"
    if e == "16" and not (MANUSCRITO / texto).exists():
        return f"sem manuscrito/{texto}"
    dados = "title_page_data_en.json" if idioma == "en" else "folha_de_rosto_dados.json"
    if e == "18" and not (MANUSCRITO / dados).exists():
        return f"sem manuscrito/{dados} (autores e declarações)"
    if e == "14b" and not (RAIZ / "dados" / "processados" / "producao_caps_estabelecimento_mes.parquet").exists():
        return "sem dados/processados/producao_caps_estabelecimento_mes.parquet (rode a etapa 03b)"
    return None


def rodar(e: str, idioma: str = "en") -> None:
    motivo = pular(e, idioma)
    if motivo:
        print(f"\n===== {e} pulada: {motivo}", flush=True)
        return
    t = time.time()
    print(f"\n===== {e} {ETAPAS[e]}", flush=True)
    if e == "11antigo":  # gerador antigo: texto + tabelas (Python) e Word (Node; requer npm install em manuscrito/)
        r = subprocess.run([sys.executable, "-I", str(MANUSCRITO / "preparar_manuscrito.py")], cwd=RAIZ)
        if not r.returncode:
            r = subprocess.run(["node", "gerar_docx.js"], cwd=MANUSCRITO)
    else:
        r = subprocess.run([sys.executable, "-I", str(RAIZ / "codigo" / ETAPAS[e]), *argumentos(e, idioma)], cwd=RAIZ)
    if r.returncode:
        raise SystemExit(f"etapa {e} falhou (código {r.returncode})")
    print(f"===== {e} concluída em {time.time() - t:.0f} s", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--etapas", default=PADRAO,
                    help="ordem de execução; 03b (CAPS) usa a população de 04; 09 roda antes de 07 e 08; "
                         "10 roda antes de 14 e 15 (monta os dados agregados) e de novo no fim (empacota os Word)")
    ap.add_argument("--idioma", default="en", choices=["en", "pt"],
                    help="idioma das figuras do manuscrito e dos Word (etapas 15, 16 e 18); padrão: en")
    a = ap.parse_args()
    for e in a.etapas.split(","):
        if e == "11":  # o Word sai sempre das etapas 16 e 18
            print("\n===== 11: os arquivos Word agora saem das etapas 16 e 18", flush=True)
            for w in ("16", "18"):
                rodar(w, a.idioma)
            continue
        rodar(e, a.idioma)


if __name__ == "__main__":
    main()
