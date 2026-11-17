# -*- coding: utf-8 -*-
"""
Confere, com o arquivo por estabelecimento, as contagens de CAPS sem registro citadas no manuscrito.

Usa a mesma definição da etapa 09 (margens dos CAPS): CAPS (CNES) com usuários registrados nos três
meses do primeiro trimestre de 2024, classificados pela exposição do município onde o CAPS fica.
Conta, para cada mês de abril a agosto de 2024, quantos desses CAPS ficaram sem nenhum registro, e
compara com os números do texto (aproximação municipal do R8). Também mostra o mínimo e o máximo
mensal em 2022 e 2023, para a frase "ante 3 a 12 por mês em 2022 e 2023". Grava
resultados/revisao/R8b_caps_sem_registro_estabelecimento.csv, no mesmo formato do R8.

Uso (na raiz do repositório, com dados/ presente):
  python codigo/14b_conferir_caps_sem_registro.py
  python codigo/14b_conferir_caps_sem_registro.py <producao_caps_estabelecimento_mes.parquet ou .csv> <exposicao_municipio.csv>
"""
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
ARQ_PROD = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "dados" / "processados" / "producao_caps_estabelecimento_mes.parquet"
ARQ_EXP = Path(sys.argv[2]) if len(sys.argv) > 2 else RAIZ / "dados_agregados" / "exposicao_municipio.csv"
if not ARQ_EXP.exists():
    ARQ_EXP = RAIZ / "dados" / "processados" / "exposicao_municipio.csv"

# números do manuscrito revisado (R8, aproximação pela oferta de CAPS por município)
TEXTO = {
    "2024-04": {"<1%": 19, "1-<10%": 4, ">=10%": 8},
    "2024-05": {"<1%": 16, "1-<10%": 1, ">=10%": 19},
}
TEXTO_TOTAL_ABR_JUN = (30, 36)     # "30 a 36 deixaram de registrar produção a cada mês entre abril e junho"
TEXTO_2022_2023 = (3, 12)          # "ante 3 a 12 por mês em 2022 e 2023"
TEXTO_DENOMINADORES = {"<1%": 77, "1-<10%": 23, ">=10%": 55}


def main() -> None:
    of = pd.read_csv(ARQ_PROD) if ARQ_PROD.suffix == ".csv" else pd.read_parquet(ARQ_PROD)
    of["mes"] = pd.to_datetime(of["mes"])
    exp = pd.read_csv(ARQ_EXP)[["mun_res", "exposicao_cat"]].rename(columns={"mun_res": "mun_local"})
    grade = of.pivot_table(index=["cnes", "mun_local"], columns="mes", values="usuarios", aggfunc="sum").fillna(0)
    ref = [c for c in grade.columns if pd.Timestamp("2024-01-01") <= c <= pd.Timestamp("2024-03-01")]
    grade = grade[(grade[ref] > 0).all(axis=1)]
    cat = grade.reset_index()[["cnes", "mun_local"]].merge(exp, on="mun_local", how="left")
    cat["exposicao_cat"] = cat["exposicao_cat"].fillna("<1%")
    cat = cat.set_index(["cnes", "mun_local"])["exposicao_cat"]
    print(f"CAPS com registro em jan, fev e mar de 2024: {len(grade)} (texto: 155)")
    den = cat.value_counts()
    print("Por categoria do município do CAPS:", {k: int(den.get(k, 0)) for k in TEXTO_DENOMINADORES},
          "| texto:", TEXTO_DENOMINADORES)

    sem = (grade == 0)
    linhas = []
    for m in pd.date_range("2024-04-01", "2024-08-01", freq="MS"):
        if m not in sem.columns:
            continue
        s = sem[m].groupby(cat).sum()
        linhas.append({"mes": m.strftime("%Y-%m"), **{k: int(s.get(k, 0)) for k in ["<1%", "1-<10%", ">=10%"]},
                       "total": int(sem[m].sum())})
    t = pd.DataFrame(linhas).set_index("mes")
    print("\nCAPS sem registro, por exposição do município do CAPS")
    print(t.to_string())
    # mesmo formato do R8 (aproximação municipal), agora com a contagem por estabelecimento
    saida = RAIZ / "resultados" / "revisao" / "R8b_caps_sem_registro_estabelecimento.csv"
    saida.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"mes": m, "categoria": k, "caps_regulares": int(den.get(k, 0)), "sem_registro": int(t.loc[m, k]),
                   "pct": 100 * t.loc[m, k] / den.get(k, 1)} for m in t.index for k in ["1-<10%", "<1%", ">=10%"]]
                 ).to_csv(saida, index=False)
    print("gravado:", saida)

    ok = True
    for mes, esperado in TEXTO.items():
        for k, v in esperado.items():
            obs = int(t.loc[mes, k])
            if obs != v:
                ok = False
                print(f"DIFERENTE do texto: {mes}, {k}: arquivo {obs}, texto {v}")
    abr_jun = t.loc[["2024-04", "2024-05", "2024-06"], "total"]
    print(f"\nTotal por mês entre abril e junho de 2024: {abr_jun.min()} a {abr_jun.max()} (texto: "
          f"{TEXTO_TOTAL_ABR_JUN[0]} a {TEXTO_TOTAL_ABR_JUN[1]})")
    if (abr_jun.min(), abr_jun.max()) != TEXTO_TOTAL_ABR_JUN:
        ok = False
        print("DIFERENTE do texto: total de abril a junho")
    antes = sem[[c for c in sem.columns if pd.Timestamp("2022-01-01") <= c <= pd.Timestamp("2023-12-01")]].sum()
    antes = antes[antes.index >= pd.Timestamp("2022-05-01")]  # mesma janela das margens (05/2022 em diante)
    print(f"Por mês em 2022 e 2023 (05/2022 a 12/2023): {int(antes.min())} a {int(antes.max())} "
          f"(texto: {TEXTO_2022_2023[0]} a {TEXTO_2022_2023[1]})")
    if (int(antes.min()), int(antes.max())) != TEXTO_2022_2023:
        ok = False
        print("DIFERENTE do texto: faixa de 2022 e 2023")
    print("\nResultado:", "os números do texto conferem." if ok else "há diferenças; corrigir o texto (manuscrito/manuscrito.txt).")


if __name__ == "__main__":
    main()
