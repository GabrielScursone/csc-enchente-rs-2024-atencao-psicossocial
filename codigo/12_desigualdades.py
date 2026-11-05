"""Desigualdades por sexo e raça/cor no efeito da enchente (PLANO_ANALISE.md, seção 9; exploratório).

Modelo empilhado (Poisson, pyfixest), dois grupos por vez:
  y ~ i(periodo, x, ref="pre") + i(periodo, x_comp, ref="pre") | município^grupo + mês^grupo
x = % da população em área afetada / 10; x_comp = x no grupo de comparação. exp(coef de x) é a RT por
10 p.p. no grupo de referência; exp(coef de x_comp) é a RAZÃO entre as RTs (comparação ÷ referência),
que testa se o efeito difere entre os grupos. Erros-padrão agrupados por município.

Sexo: janela inteira (01/2015–03/2026), offset população do sexo.
Raça/cor: só 07/2023–03/2026 (sem informação ≤3,4% nos CAPS e 0% nas internações), offset população
total; sensibilidade começando em 10/2023. Preta + parda = negra; referência = branca.

Saídas em resultados/04_desigualdades/: desigualdades_rt.csv, desigualdades_descritivo.csv
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import FIM_ESTUDO, INICIO_ENCHENTE, INICIO_ESTUDO, RESULTADOS, carregar_painel  # noqa: E402

SAIDA = RESULTADOS / "04_desigualdades"
PERIODOS = [("agudo", "2024-05-01", "2024-07-31"), ("subagudo", "2024-08-01", "2025-04-30"),
            ("tardio", "2025-05-01", "2026-12-31")]
ANALISES = [
    # (dimensão, desfecho, coluna referência, coluna comparação, offset ref, offset comp, início da janela)
    ("sexo", "Internações F00–F99", "f_masc", "f_fem", "pop_masc", "pop_fem", INICIO_ESTUDO),
    ("sexo", "Usuários dos CAPS", "caps_usuarios_masc", "caps_usuarios_fem", "pop_masc", "pop_fem", INICIO_ESTUDO),
    ("raça/cor", "Internações F00–F99", "f_branca", "f_negra", "pop_total", "pop_total", pd.Timestamp("2023-07-01")),
    ("raça/cor", "Usuários dos CAPS", "caps_usuarios_branca", "caps_usuarios_negra", "pop_total", "pop_total",
     pd.Timestamp("2023-07-01")),
    ("raça/cor (desde out/2023)", "Internações F00–F99", "f_branca", "f_negra", "pop_total", "pop_total",
     pd.Timestamp("2023-10-01")),
    ("raça/cor (desde out/2023)", "Usuários dos CAPS", "caps_usuarios_branca", "caps_usuarios_negra", "pop_total",
     "pop_total", pd.Timestamp("2023-10-01")),
]
NOMES = {"f_masc": "homens", "f_fem": "mulheres", "caps_usuarios_masc": "homens", "caps_usuarios_fem": "mulheres",
         "f_branca": "brancos", "f_negra": "pretos ou pardos", "caps_usuarios_branca": "brancos",
         "caps_usuarios_negra": "pretos ou pardos"}


def empilhar(p: pd.DataFrame, ref, comp, off_ref, off_comp, inicio) -> pd.DataFrame:
    d = p[(p.mes >= inicio) & (p.mes <= FIM_ESTUDO)]
    base = d[["mun_res", "mes", "pct_pop_afetada"]]
    a = base.assign(y=d[ref].values, pop=d[off_ref].values, grupo="ref")
    b = base.assign(y=d[comp].values, pop=d[off_comp].values, grupo="comp")
    s = pd.concat([a, b], ignore_index=True)
    s = s[s["pop"] > 0].copy()
    s["log_pop"] = np.log(s["pop"])
    s["x"] = s.pct_pop_afetada / 10
    s["x_comp"] = s.x * (s.grupo == "comp")
    s["periodo"] = "pre"
    for nome, i, f in PERIODOS:
        s.loc[s.mes.between(i, f), "periodo"] = nome
    s["mes_s"] = s.mes.dt.strftime("%Y-%m")
    return s


def ajustar(s: pd.DataFrame):
    import pyfixest as pf
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pf.fepois("y ~ i(periodo, x, ref='pre') + i(periodo, x_comp, ref='pre') | mun_res^grupo + mes_s^grupo",
                         data=s, offset="log_pop", vcov={"CRV1": "mun_res"}, store_data=False, copy_data=False)


def resultados(fit, dim, desf, ref, comp) -> list[dict]:
    nomes = list(fit._coefnames)
    b, V = np.asarray(fit.coef()), np.asarray(fit._vcov)
    linhas = []
    for per, *_ in PERIODOS:
        i = nomes.index(f"periodo::{per}:x")
        j = nomes.index(f"periodo::{per}:x_comp")
        ep_ref = np.sqrt(V[i, i])
        b_comp, ep_comp = b[i] + b[j], np.sqrt(V[i, i] + V[j, j] + 2 * V[i, j])
        ep_int = np.sqrt(V[j, j])
        from scipy import stats
        linhas.append({
            "dimensao": dim, "desfecho": desf, "periodo": per,
            "grupo_ref": NOMES[ref], "rt_ref": np.exp(b[i]), "rt_ref_inf": np.exp(b[i] - 1.96 * ep_ref),
            "rt_ref_sup": np.exp(b[i] + 1.96 * ep_ref),
            "grupo_comp": NOMES[comp], "rt_comp": np.exp(b_comp), "rt_comp_inf": np.exp(b_comp - 1.96 * ep_comp),
            "rt_comp_sup": np.exp(b_comp + 1.96 * ep_comp),
            "razao_rt": np.exp(b[j]), "razao_inf": np.exp(b[j] - 1.96 * ep_int), "razao_sup": np.exp(b[j] + 1.96 * ep_int),
            "p_diferenca": 2 * (1 - stats.norm.cdf(abs(b[j] / ep_int))),
        })
    return linhas


def descritivo(p: pd.DataFrame) -> pd.DataFrame:
    """Composição antes da enchente (07/2023–04/2024), por categoria de exposição."""
    d = p[(p.mes >= "2023-07-01") & (p.mes < INICIO_ENCHENTE)]
    g = d.groupby("exposicao_cat", observed=True)[["f_total", "f_negra", "f_fem", "caps_usuarios",
                                                   "caps_usuarios_negra", "caps_usuarios_fem"]].sum()
    return pd.DataFrame({
        "internações F: % pretos ou pardos": 100 * g.f_negra / g.f_total,
        "internações F: % mulheres": 100 * g.f_fem / g.f_total,
        "CAPS: % usuários pretos ou pardos": 100 * g.caps_usuarios_negra / g.caps_usuarios,
        "CAPS: % usuárias mulheres": 100 * g.caps_usuarios_fem / g.caps_usuarios,
    }).round(1)


def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    p = carregar_painel()
    linhas = []
    for dim, desf, ref, comp, oref, ocomp, inicio in ANALISES:
        s = empilhar(p, ref, comp, oref, ocomp, inicio)
        linhas += resultados(ajustar(s), dim, desf, ref, comp)
        print(f"{dim} | {desf}: ok", flush=True)
    t = pd.DataFrame(linhas)
    t.to_csv(SAIDA / "desigualdades_rt.csv", index=False)
    desc = descritivo(p)
    desc.to_csv(SAIDA / "desigualdades_descritivo.csv")
    pd.set_option("display.width", 250)
    print(t.round(3).to_string())
    print(desc.to_string())


if __name__ == "__main__":
    main()
