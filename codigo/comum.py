"""Caminhos, leitura de DBF e definições comuns da análise SIH/SUS RS × enchente de 2024."""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
BRUTOS = RAIZ / "dados" / "brutos"
INTERMED = RAIZ / "dados" / "intermediarios"
PROCESSADOS = RAIZ / "dados" / "processados"
RESULTADOS = RAIZ / "resultados"

# Competências baixadas (AAAAMM). A última define até quando a data de internação é confiável.
PRIMEIRA_CMPT = "201501"
ULTIMA_CMPT = "202608"

# Janela analítica pela data de internação. Com a competência de 08/2026, internações até
# 03/2026 já têm 5 meses de processamento: em 2016–2023, 5 meses capturaram 99,88–99,98% das
# AIHs; 4 meses, 99,12–99,87% (completude_por_atraso.csv).
INICIO_ESTUDO = pd.Timestamp("2015-01-01")
FIM_ESTUDO = pd.Timestamp("2026-03-31")

# Enchente: chuvas a partir de 27/04/2024; pico em maio. Primeiro mês exposto = 05/2024.
INICIO_ENCHENTE = pd.Timestamp("2024-05-01")
# Enchente de set/2023 no Vale do Taquari (análise de sensibilidade).
ENCHENTE_2023 = pd.Timestamp("2023-09-01")
# Pandemia: tratada com indicador nos modelos (mar/2020 a dez/2021).
COVID_INICIO, COVID_FIM = pd.Timestamp("2020-03-01"), pd.Timestamp("2021-12-31")

COLUNAS_RD = [
    "ANO_CMPT", "MES_CMPT", "IDENT", "N_AIH", "SEQ_AIH5", "MUNIC_RES", "MUNIC_MOV", "CNES",
    "DT_INTER", "DT_SAIDA", "DIAG_PRINC", "DIAGSEC1", "DIAGSEC2", "DIAGSEC3", "DIAGSEC4",
    "DIAGSEC5", "DIAGSEC6", "DIAGSEC7", "DIAGSEC8", "DIAGSEC9", "CID_ASSO", "CID_MORTE",
    "ESPEC", "CAR_INT", "SEXO", "NASC", "IDADE", "COD_IDADE", "RACA_COR", "ETNIA", "INSTRU",
    "DIAS_PERM", "MORTE", "COBRANCA", "PROC_REA", "VAL_TOT", "COMPLEX", "GESTAO", "NATUREZA",
    "NAT_JUR",
]

# Grupos do capítulo F pelo diagnóstico principal (3 caracteres).
GRUPOS_F = {
    "f_organicos": ("F00", "F09"),
    "f_spa": ("F10", "F19"),          # álcool e outras drogas
    "f_psicoticos": ("F20", "F29"),
    "f_humor": ("F30", "F39"),
    "f_neuroticos": ("F40", "F48"),   # inclui reação a estresse grave (F43)
}
# Lesão autoprovocada intencional como causa externa (diagnóstico secundário).
AUTOLESAO = ("X60", "X84")
# Desfechos-controle: hospitalizações que dependem pouco do sofrimento psíquico.
CONTROLES = {
    "ctrl_parto": ("O80", "O84"),
    "ctrl_apendicite": ("K35", "K37"),
}


def sha256(path: Path, bloco: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(bloco):
            h.update(chunk)
    return h.hexdigest()


def ler_dbf(path: Path, colunas: list[str] | set[str] | None = None,
            codificacao: str = "latin-1") -> pd.DataFrame:
    """Lê um DBF (dBase III) como texto, só com as colunas pedidas.

    Mais rápido que simpledbf/dbfread para os RD: lê o arquivo de uma vez e fatia
    os campos de largura fixa com NumPy. Registros marcados como apagados ('*') saem.
    """
    buf = Path(path).read_bytes()
    n = struct.unpack("<I", buf[4:8])[0]
    hlen, rlen = struct.unpack("<HH", buf[8:12])
    campos, pos, off = [], 32, 1
    while buf[pos] != 0x0D:
        nome = buf[pos:pos + 11].split(b"\x00")[0].decode("latin-1").strip()
        tam = buf[pos + 16]
        campos.append((nome, off, tam))
        off += tam
        pos += 32
    if off != rlen:
        raise ValueError(f"{path}: soma das larguras {off} != tamanho do registro {rlen}")
    if hlen + n * rlen > len(buf):
        raise ValueError(f"{path}: arquivo menor que o declarado no cabeçalho (cortado?)")
    arr = np.frombuffer(buf, dtype=np.uint8, count=n * rlen, offset=hlen).reshape(n, rlen)
    vivos = arr[:, 0] != ord("*")
    pedidas = set(colunas) if colunas is not None else None
    out = {}
    for nome, off, tam in campos:
        if pedidas is None or nome in pedidas:
            col = np.ascontiguousarray(arr[vivos, off:off + tam]).view(f"S{tam}").ravel()
            out[nome] = pd.Series(col).str.decode(codificacao).str.strip()
    faltam = (pedidas or set()) - set(out)
    for nome in sorted(faltam):  # coluna inexistente nesse mês: fica vazia, mas registrada
        out[nome] = pd.Series([""] * int(vivos.sum()))
    return pd.DataFrame(out)


def entre(cid3: pd.Series, faixa: tuple[str, str]) -> pd.Series:
    """CID de 3 caracteres dentro da faixa fechada (comparação lexicográfica)."""
    return (cid3 >= faixa[0]) & (cid3 <= faixa[1])


def carregar_painel() -> pd.DataFrame:
    """Painel município × mês com contagens, população mensal e exposição (saídas de 03 e 04).

    Fica fora o código de município que não existe na população da SVS (ex.: '430000',
    município ignorado); quantas internações isso remove fica em qualidade_base.json.
    """
    p = pd.read_parquet(PROCESSADOS / "painel_municipio_mes.parquet")
    pop = pd.read_parquet(PROCESSADOS / "populacao_municipio_mes.parquet")
    exp = pd.read_csv(PROCESSADOS / "exposicao_municipio.csv")
    caps = PROCESSADOS / "painel_caps_municipio_mes.parquet"
    if caps.exists():  # produção dos CAPS (Emenda 1), mesma grade município × mês
        p = p.merge(pd.read_parquet(caps), on=["mun_res", "mes"], how="left")
        cols = [c for c in p.columns if c.startswith("caps_")]
        p[cols] = p[cols].fillna(0)
    p = p.merge(pop, on=["mun_res", "mes"], how="inner")
    p = p.merge(exp[["mun_res", "nome", "pct_pop_afetada", "estab_saude_af_10mil", "exposicao_cat"]],
                on="mun_res", how="left", validate="many_to_one")
    p["exposicao_cat"] = pd.Categorical(p.exposicao_cat, ["<1%", "1-<10%", ">=10%"])
    return p


# Rótulos em português para tabelas e figuras
ROTULOS = {
    "f_total": "Transtornos mentais (F00–F99)", "f_spa": "Álcool e outras drogas (F10–F19)",
    "f_alcool": "Álcool (F10)", "f_humor": "Transtornos do humor (F30–F39)",
    "f_neuroticos": "Neuróticos e relacionados ao estresse (F40–F48)", "f_estresse": "Reação ao estresse (F43)",
    "f_psicoticos": "Esquizofrenia e psicóticos (F20–F29)", "f_organicos": "Orgânicos (F00–F09)",
    "f_outros": "Demais F", "autolesao": "Lesão autoprovocada (X60–X84, diag. secundário)",
    "f_obito": "Óbito hospitalar (diag. principal F)", "f_masc": "F00–F99, homens", "f_fem": "F00–F99, mulheres",
    "f_spa_masc": "F10–F19, homens", "f_spa_fem": "F10–F19, mulheres",
    "f_0_17": "F00–F99, 0–17 anos", "f_18_39": "F00–F99, 18–39 anos", "f_40_59": "F00–F99, 40–59 anos",
    "f_60m": "F00–F99, 60+ anos", "f_branca": "F00–F99, raça/cor branca", "f_negra": "F00–F99, preta ou parda",
    "f_indigena": "F00–F99, indígena", "f_raca_ign": "F00–F99, raça/cor ignorada",
    "f_leito_psiq": "F00–F99, leito psiquiátrico", "f_leito_sm_hg": "F00–F99, saúde mental em hospital geral",
    "f_leito_outro": "F00–F99, outros leitos (clínicos etc.)", "f_urgencia": "F00–F99, caráter de urgência",
    "f_eletiva": "F00–F99, eletivas", "f_fora_mun": "F00–F99, fora do município de residência",
    "f_dias_perm": "F00–F99, dias de permanência", "todas_causas": "Todas as causas",
    "nao_f": "Demais causas, exceto F (controle)", "ctrl_parto": "Partos O80–O84 (controle)",
    "ctrl_apendicite": "Apendicite K35–K37 (controle)",
    "caps_usuarios": "CAPS: usuários atendidos", "caps_novos": "CAPS: usuários novos",
    "caps_usuarios_ad": "CAPS: usuários com CID F10–F19", "caps_usuarios_estresse": "CAPS: usuários com CID F40–F48",
    "caps_usuarios_fem": "CAPS: usuárias (mulheres)", "caps_usuarios_masc": "CAPS: usuários (homens)",
    "caps_usuarios_branca": "CAPS: usuários de raça/cor branca", "caps_usuarios_negra": "CAPS: usuários pretos ou pardos",
    "caps_usuarios_raca_ign": "CAPS: usuários com raça/cor sem informação",
    "caps_usuarios_0_17": "CAPS: usuários de 0–17 anos",
    "caps_proced": "CAPS: procedimentos (total)", "caps_crise": "CAPS: atenção às situações de crise",
    "caps_individual": "CAPS: atendimentos individuais", "caps_grupo": "CAPS: atendimentos em grupo",
    "caps_familiar": "CAPS: atendimentos familiares", "caps_domiciliar": "CAPS: atendimentos domiciliares",
    "caps_acolhimento": "CAPS: acolhimento (diurno, noturno, 3º turno)",
}
DESFECHOS_CAPS = ["caps_usuarios", "caps_novos", "caps_usuarios_ad", "caps_usuarios_estresse", "caps_crise",
                  "caps_domiciliar"]
ROTULOS_ESTRATO = {"estado": "Rio Grande do Sul", "<1%": "Exposição <1%", "1-<10%": "Exposição 1–<10%",
                   ">=10%": "Exposição ≥10%"}
ROTULOS_MODELO = {"ensemble": "Média dos 3 modelos", "qp": "Quase-Poisson", "sarima": "SARIMA",
                  "lgbm": "LightGBM"}
