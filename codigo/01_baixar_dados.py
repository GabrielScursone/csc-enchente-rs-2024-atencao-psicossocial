"""Baixa (ou confere) os dados públicos usados no artigo e grava o manifesto com SHA-256.

- SIH/SUS RD do RS (DATASUS): competências de 2025 e 2026 que faltavam. As de 2015–2024 já
  estão em dados/brutos/sih_sus_rs_AAAA.zip (baixadas em 03/11/2026).
- SIA/SUS, RAAS psicossocial (PSRSAAMM.dbc, produção dos CAPS), 01/2015 em diante.
- Estimativas populacionais da SVS por município, sexo e idade (POPSVS, 2015–2025).
- DATASUS: base territorial (regiões e macrorregiões de saúde), versão out/2025 (opcional).
- IBGE: população, domicílios e estabelecimentos dentro da mancha de inundação v3 (INPE/ANA)
  por município (Censo 2022/CNEFE, 26/06/2024); malha municipal 2022; regiões geográficas 2017.

Caminhos de download do DATASUS, nesta ordem:
  1. FTP (ftp.datasus.gov.br), uma conexão só, comparando o tamanho com o do servidor;
  2. portal de transferência (datasus.saude.gov.br/wp-content/download.php), usado quando o FTP
     não responde: o servidor do portal busca o mesmo arquivo no FTP e devolve um ZIP.
     O servidor FTP bloqueia o IP por mais de uma hora quando recebe conexões simultâneas.
Todo arquivo é conferido: .dbc precisa descompactar com o número de registros do cabeçalho;
.zip precisa passar no teste de integridade.
Uso: python -I codigo/01_baixar_dados.py [--forcar-portal RDRS2608.dbc,...]
"""
from __future__ import annotations

import argparse
import ftplib
import json
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import BRUTOS, INTERMED, ULTIMA_CMPT, ler_dbf, sha256  # noqa: E402

FTP_HOST = "ftp.datasus.gov.br"
FTP_RD = "/dissemin/publicos/SIHSUS/200801_/Dados"
FTP_POP = "/dissemin/publicos/IBGE/POPSVS"
FTP_PS = "/dissemin/publicos/SIASUS/200801_/Dados"  # RAAS psicossocial (CAPS): PSRSAAMM.dbc
FTP_TERR = "/territorio/tabelas/2025/10-base_territorial_out25.zip"
PORTAL = "https://datasus.saude.gov.br/wp-content/download.php"
IBGE_RS = "https://ftp.ibge.gov.br/Informacoes_Gerais_e_Referencia/SINGED_Lab/apoio_rs/"
IBGE_ARQ = [
    "Leia_me.txt",
    "Dados_agregados_para_toda_a_area_afetada_v3_Governo_Federal/"
    "Dados_Agregados_para_as_Areas_Afetadas_Municipios_do_RS_GTCasaCivil_26jun24.xlsx",
    "Dados_agregados_para_toda_a_area_afetada_v3_Governo_Federal/"
    "Pres_Informacoes_Oficio_Dados_Agregados_para_as_Areas_Afetadas_Municipios_do_RS_GTCasaCivil_26jun24.pdf",
]
IBGE_GEO = {
    "malha_ibge_2022/RS_Municipios_2022.zip":
        "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/"
        "municipio_2022/UFs/RS/RS_Municipios_2022.zip",
    "regioes_ibge/regioes_geograficas_composicao_por_municipios_2017_20180911.xlsx":
        "https://geoftp.ibge.gov.br/organizacao_do_territorio/divisao_regional/divisao_regional_do_brasil/"
        "divisao_regional_do_brasil_em_regioes_geograficas_2017/tabelas/"
        "regioes_geograficas_composicao_por_municipios_2017_20180911.xlsx",
}


def competencias(inicio: str, fim: str) -> list[str]:
    a, m = int(inicio[:4]), int(inicio[4:])
    out = []
    while f"{a}{m:02d}" <= fim:
        out.append(f"{a}{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return out


def conferir(p: Path, tipo: str | None = None) -> str:
    """Levanta erro se o arquivo estiver corrompido ou cortado (tipo: extensão, se p for temporário)."""
    tipo = (tipo or p.suffix).lower()
    if tipo == ".dbc":
        import readdbc
        with tempfile.TemporaryDirectory(dir=INTERMED) as tmp:
            dbc, dbf = Path(tmp) / "x.dbc", Path(tmp) / "x.dbf"  # readdbc exige a extensão .dbc
            shutil.copy2(p, dbc)
            readdbc.dbc2dbf(str(dbc), str(dbf))
            n = len(ler_dbf(dbf, ["N_AIH"]))  # ler_dbf recusa DBF menor que o cabeçalho declara
        return f"{n} registros"
    if tipo == ".zip":
        with zipfile.ZipFile(p) as z:
            ruim = z.testzip()
            if ruim:
                raise OSError(f"{p.name}: membro corrompido {ruim}")
            return f"zip íntegro, {len(z.namelist())} arquivo(s)"
    raise ValueError(f"{p.name}: tipo sem conferência definida ({tipo})")


def ftp_disponivel() -> bool:
    try:
        with ftplib.FTP(FTP_HOST, timeout=30) as ftp:
            ftp.login()
        return True
    except (OSError, EOFError, ftplib.Error):
        return False


def baixar_ftp(remoto: str, destino: Path) -> str:
    with ftplib.FTP(FTP_HOST, timeout=90) as ftp:
        ftp.login()
        ftp.voidcmd("TYPE I")
        tam = ftp.size(remoto)
        if destino.exists() and destino.stat().st_size == tam:
            return f"já existia ({tam} bytes, igual ao servidor)"
        tmp = destino.with_suffix(destino.suffix + ".parcial")
        with open(tmp, "wb") as f:
            ftp.retrbinary(f"RETR {remoto}", f.write)
    if tmp.stat().st_size != tam:
        raise OSError(f"{remoto}: {tmp.stat().st_size} bytes baixados, servidor informa {tam}")
    tmp.replace(destino)
    return f"baixado do FTP ({tam} bytes)"


def baixar_portal(remoto: str, destino: Path, tentativas: int = 6) -> str:
    """O portal às vezes responde 503 sob carga: novas tentativas com espera crescente."""
    for t in range(tentativas):
        try:
            return _baixar_portal(remoto, destino)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            espera = 30 * 2 ** t
            print(f"  portal falhou em {destino.name} ({e}); nova tentativa em {espera} s", flush=True)
            time.sleep(espera)
    raise SystemExit(f"portal: não foi possível baixar {destino.name}")


def _baixar_portal(remoto: str, destino: Path) -> str:
    dados = urllib.parse.urlencode({"dados[0][arquivo]": destino.name,
                                    "dados[0][link]": f"ftp://{FTP_HOST}{remoto}"}).encode()
    with urllib.request.urlopen(urllib.request.Request(PORTAL, data=dados), timeout=600) as r:
        url = json.loads(r.read())[0][0]
    tmpzip = destino.with_suffix(destino.suffix + ".portal.zip")
    with urllib.request.urlopen(url, timeout=600) as r, open(tmpzip, "wb") as f:
        shutil.copyfileobj(r, f)
    with zipfile.ZipFile(tmpzip) as z:
        if z.namelist() != [destino.name]:
            raise OSError(f"ZIP do portal com conteúdo inesperado: {z.namelist()}")
        tmp = destino.with_suffix(destino.suffix + ".parcial")
        tmp.write_bytes(z.read(destino.name))
    tmpzip.unlink()
    info = conferir(tmp, destino.suffix)
    antes = destino.stat().st_size if destino.exists() else None
    tmp.replace(destino)
    extra = f"; versão anterior tinha {antes} bytes" if antes not in (None, destino.stat().st_size) else ""
    return f"baixado pelo portal ({destino.stat().st_size} bytes, {info}{extra})"


def baixar_lista(pares: list[tuple[str, Path]], forcar_portal: set[str] = frozenset()) -> None:
    usar_ftp = ftp_disponivel()
    print(f"FTP {'disponível' if usar_ftp else 'indisponível: usando o portal'}", flush=True)
    for remoto, destino in pares:
        if destino.name in forcar_portal:
            print(destino.name, baixar_portal(remoto, destino), flush=True)
        elif usar_ftp:
            print(destino.name, baixar_ftp(remoto, destino), flush=True)
        elif destino.exists():
            print(destino.name, f"já existia ({destino.stat().st_size} bytes; {conferir(destino)})", flush=True)
        else:
            print(destino.name, baixar_portal(remoto, destino), flush=True)
            time.sleep(2)  # gentileza com o portal


def rd_faltantes(forcar: set[str]) -> None:
    """Baixa os RDRS de 2025 em diante e os empacota em sih_sus_rs_AAAA.zip (sem recompressão)."""
    pasta = BRUTOS / "download_rd_2025_2026"
    pasta.mkdir(parents=True, exist_ok=True)
    cmpts = competencias("202501", ULTIMA_CMPT)
    baixar_lista([(f"{FTP_RD}/RDRS{c[2:]}.dbc", pasta / f"RDRS{c[2:]}.dbc") for c in cmpts], forcar)
    for ano in sorted({c[:4] for c in cmpts}):
        arqs = sorted(pasta.glob(f"RDRS{ano[2:]}??.dbc"))
        esperado = [f"RDRS{c[2:]}.dbc" for c in cmpts if c[:4] == ano]
        if [a.name for a in arqs] != esperado:
            raise SystemExit(f"{ano}: faltam {sorted(set(esperado) - {a.name for a in arqs})}")
        destino = BRUTOS / f"sih_sus_rs_{ano}.zip"
        with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_STORED) as z:
            for a in arqs:
                z.write(a, a.name)
        print(f"{destino.name}: {len(arqs)} competências")


def sia_ps(forcar: set[str]) -> None:
    """SIA/SUS, RAAS psicossocial (produção dos CAPS), RS, 01/2015 até ULTIMA_CMPT.
    Empacotado em sia_ps_rs_AAAA.zip (sem recompressão)."""
    pasta = BRUTOS / "download_sia_ps"
    pasta.mkdir(parents=True, exist_ok=True)
    cmpts = competencias("201501", ULTIMA_CMPT)
    baixar_lista([(f"{FTP_PS}/PSRS{c[2:]}.dbc", pasta / f"PSRS{c[2:]}.dbc") for c in cmpts], forcar)
    for ano in sorted({c[:4] for c in cmpts}):
        arqs = sorted(pasta.glob(f"PSRS{ano[2:]}??.dbc"))
        esperado = [f"PSRS{c[2:]}.dbc" for c in cmpts if c[:4] == ano]
        if [a.name for a in arqs] != esperado:
            raise SystemExit(f"PS {ano}: faltam {sorted(set(esperado) - {a.name for a in arqs})}")
        with zipfile.ZipFile(BRUTOS / f"sia_ps_rs_{ano}.zip", "w", compression=zipfile.ZIP_STORED) as z:
            for a in arqs:
                z.write(a, a.name)
        print(f"sia_ps_rs_{ano}.zip: {len(arqs)} competências")


def populacao(forcar: set[str]) -> None:
    pasta = BRUTOS / "populacao_svs"
    pasta.mkdir(parents=True, exist_ok=True)
    baixar_lista([(f"{FTP_POP}/POPSBR{a:02d}.zip", pasta / f"POPSBR{a:02d}.zip") for a in range(15, 26)], forcar)


def territorio(forcar: set[str]) -> None:
    pasta = BRUTOS / "territorio_datasus"
    pasta.mkdir(parents=True, exist_ok=True)
    try:  # opcional: sem ela, 04 usa as regiões geográficas do IBGE
        baixar_lista([(FTP_TERR, pasta / "base_territorial_out25.zip")], forcar)
    except (OSError, ValueError, KeyError, SystemExit) as e:
        print("AVISO: base territorial não baixada:", e)


def ibge() -> None:
    alvos = {f"exposicao_ibge_areas_afetadas/{Path(r).name}": IBGE_RS + urllib.parse.quote(r) for r in IBGE_ARQ}
    for rel, url in {**alvos, **IBGE_GEO}.items():
        destino = BRUTOS / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            print(destino.name, "já existia")
            continue
        with urllib.request.urlopen(url, timeout=300) as r, open(destino, "wb") as f:
            shutil.copyfileobj(r, f)
        print(destino.name, "baixado")


def manifesto() -> None:
    linhas = ["arquivo,bytes,sha256"]
    for p in sorted(BRUTOS.rglob("*")):
        if p.is_file() and not p.name.endswith((".parcial", ".portal.zip")) \
                and "download_rd_2025_2026" not in p.parts and "download_sia_ps" not in p.parts and p.name not in {"manifesto_arquivos.csv", "download.log"}:
            linhas.append(f"{p.relative_to(BRUTOS).as_posix()},{p.stat().st_size},{sha256(p)}")
    (BRUTOS / "manifesto_arquivos.csv").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"manifesto: {len(linhas) - 1} arquivos")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--forcar-portal", default="", help="nomes a baixar de novo pelo portal")
    ap.add_argument("--so", default="rd,ps,pop,terr,ibge", help="partes: rd, ps, pop, terr, ibge")
    a = ap.parse_args()
    forcar = set(filter(None, a.forcar_portal.split(",")))
    partes = set(a.so.split(","))
    INTERMED.mkdir(parents=True, exist_ok=True)
    if "rd" in partes:
        rd_faltantes(forcar)
    if "ps" in partes:
        sia_ps(forcar)
    if "pop" in partes:
        populacao(forcar)
    if "terr" in partes:
        territorio(forcar)
    if "ibge" in partes:
        ibge()
    manifesto()
