# The 2024 flood, psychosocial care and psychiatric admissions in Rio Grande do Sul, Brazil

Code, analysis plan, full results and aggregated data for the article submitted to the thematic call
"Atenção Psicossocial em Desastres Socioambientais" (Psychosocial Care in Socio-environmental Disasters) of
the journal *Ciência & Saúde Coletiva*.

**Question.** Did the flood of April and May 2024 change care in Psychosocial Care Centers (CAPS) and
psychiatric admissions in the Brazilian Unified Health System (SUS) for residents of Rio Grande do Sul? Was
the change larger in municipalities where a larger share of the population was affected?

**Design.** Ecological time-series study of the 497 municipalities of the state, from January 2015 to
March 2026, with two analyses and a set of robustness checks:

1. **Counterfactual:** the number expected without the flood, from the average of three models trained up
   to April 2024 (quasi-Poisson regression, SARIMA and LightGBM) and tested on four fictitious flood dates.
2. **Dose-response:** Poisson regression with municipality and month fixed effects, and an event study. The
   exposure is the share of each municipality's population living in the area hit by the flood.
3. **Robustness:** synthetic difference-in-differences (SDID), CAPS records by establishment, and
   differences by sex and race/skin color.

**Main findings.** In the 55 most affected municipalities (10% or more of the population affected), CAPS
had 36% fewer users than expected from May to July 2024 (observed/expected ratio 0.64; 95%CI 0.54-0.72). The
larger the share of the population affected, the larger the drop. Some CAPS stopped working, CAPS that stayed
open saw fewer users, and part of the care was not recorded. From August 2024, the number of CAPS users was
close to expected. Psychiatric admissions did not increase.

**Interactive dashboard.** All results, by outcome, exposure group and municipality, can be explored in the
dashboard in `docs/`, published with GitHub Pages from this repository. The dashboard opens in English and
has a button to switch to Portuguese. It is a static page: it only reads the files in `docs/dados/`, made by
step 13, and collects no data from visitors.

**Analysis plan.** The plan, with hypotheses, outcomes and a dated record of every change, is in
[PLANO_ANALISE.md](PLANO_ANALISE.md). It was registered in Portuguese and is kept in its original language.
Four checks were added after the main results were known (April 2024 analyzed separately, exclusion of the
less affected municipalities that border the most affected ones, rate ratio relative to the comparison
outcomes and correction for the error of the models on the fictitious dates). They are recorded in the plan
as post hoc analyses (November 8, 2026), and their outputs are in `resultados/revisao/`.

**Language.** The manuscript, this README, the figures and the dashboard are in English. Folder names, file
names, variable names and code comments are in Portuguese, the language in which the analysis was written.
The tables below explain each folder and step.

## Repository structure

| Folder or file | Content |
|---|---|
| `PLANO_ANALISE.md` | Analysis plan and dated record of changes (in Portuguese) |
| `rodar.py` | Runs all steps in order |
| `docs/` | Interactive dashboard (HTML and D3), published with GitHub Pages |
| `codigo/` | One script per step (table below) |
| `dados_agregados/` | Municipality × month panels (admissions, CAPS, population, exposure), a variable dictionary and the location map of Figure 1A |
| `resultados/01_contrafactual/` | Observed, expected and O/E ratio by outcome, exposure group and period; model validation |
| `resultados/02_dose_resposta/` | Rate ratios, event studies, pre-trend tests and sensitivity analyses |
| `resultados/03_robustez/` | SDID and CAPS records by establishment (extensive and intensive margins) |
| `resultados/04_desigualdades/` | Effect by sex and race/skin color |
| `resultados/revisao/` | Checks added during the revision (R1 to R10) |
| `resultados/figuras/manuscrito/` | Figures 1 to 4 of the manuscript, made up of panels, in color (`_color`) and grayscale (`_gray`); 15 cm wide, 9 pt serif text; PNG (300 dpi) and PDF (step 15 also writes JPEG and editable SVG files for the journal, kept out of the repository) |
| `resultados/figuras/` | Working figures (PNG 300 dpi and PDF), used in the dashboard and to check the results |
| `resultados/resultados_enchente_sihsus_rs.xlsx` | All tables in one spreadsheet |

Main terms used in file and variable names: *internações* (hospital admissions), *usuários* (CAPS users),
*esperado* (expected), *observado* (observed), *razão de taxas* or *RT* (rate ratio), *exposição* (exposure,
share of the population affected), *agudo*, *subagudo* and *tardio* (acute, May to July 2024;
subacute, August 2024 to April 2025; late, May 2025 to March 2026), *partos* (childbirth), *demais
internações* (all other admissions), *raça/cor* (race/skin color), *pretos ou pardos* (Black people).

## How to reproduce

Tested with Python 3.14.2 on Linux. Step 01 downloads the public data from DATASUS and IBGE (about 2 GB).
The DATASUS FTP server blocks the IP address when it receives simultaneous connections, so the download
uses a single connection.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python rodar.py                      # everything, about 40 minutes
.venv/bin/python rodar.py --etapas 05,06,07    # selected steps only
.venv/bin/python rodar.py --etapas 15 --idioma pt   # manuscript figures in Portuguese
```

| Step | Script (`codigo/`) | What it does |
|---|---|---|
| 01 | `01_baixar_dados.py` | Downloads the RD files (SIH/SUS) and PS files (SIA/SUS, psychosocial RAAS), populations, municipal boundaries and exposure; records SHA-256 checksums |
| 02 | `02_extrair_rd.py` | Converts each `.dbc` file to Parquet |
| 03 | `03_montar_base.py` | Admissions by date of admission; municipality × month panel |
| 03b | `03b_montar_caps.py` | CAPS records by municipality of residence × month of care |
| 04 | `04_populacao_exposicao.py` | Monthly population, exposure by municipality, regions |
| 05 | `05_contrafactual.py` | Analysis 1: expected without the flood |
| 06 | `06_dose_resposta.py` | Analysis 2: Poisson regression with fixed effects, event study, sensitivity analyses |
| 09 | `09_robustez_sdid.py` | SDID (own implementation, validated on the Proposition 99 example: -15.60) and CAPS by establishment |
| 12 | `12_desigualdades.py` | Effect by sex and race/skin color |
| 13 | `13_painel.py` | Data for the interactive dashboard (`painel/`, published as `docs/`) |
| 07 | `07_figuras.py` | Working figures |
| 08 | `08_tabelas.py` | Tables and spreadsheet |
| 14 | `14_analises_revisao.py` | Checks added during the revision (R1 to R10), using only aggregated data and results |
| 14b | `14b_conferir_caps_sem_registro.py` | Checks, by establishment, the counts of CAPS without records cited in the text |
| 15a | `15a_mapa_localizacao.py` | Optional: rebuilds the location map of Figure 1A from Natural Earth (the file is already in `dados_agregados/`) |
| 15 | `15_figuras_artigo.py` | Figures 1 to 4 of the manuscript, in color and grayscale, in English (default) or Portuguese; the maps have a north arrow, a scale bar and a legend |
| 16 and 18 | `16_gerar_docx_revisado.py`, `18_folha_de_rosto_revisada.py` | Word files of the manuscript (each figure right after its first citation) and of the title page (they need the private `manuscrito/` folder) |
| 10 | `10_entrega.py` | Delivery folder with a read-me file and a ZIP |

The Word files always come from steps 16 and 18, which keep the format required by the journal. Step 11
calls both. The article has no supplementary material: the full results of all analyses are in the
`resultados/` folders of this repository and in the dashboard. The `manuscrito/` folder, with the text, the
template and the authors' data, is kept out of this repository during peer review.

## Data

All data are public and aggregated, with no individual identification. For this reason, the study is
exempt from ethics committee review (National Health Council Resolution 510/2016, article 1).

- **SIH/SUS:** reduced hospital admission records (RD files) of Rio Grande do Sul, January 2015 to August
  2026. Type 1 records of state residents were used, dated by the date of admission.
- **SIA/SUS:** psychosocial RAAS records (PS files) of Rio Grande do Sul, January 2015 to August 2026. Each
  RAAS corresponds to one person followed by a CAPS in the month.
- **Population:** Ministry of Health estimates by municipality, sex and age (2015 to 2025).
- **Exposure:** population living in the area hit by the floods and landslides of 2024 (area mapped by
  INPE and ANA, version 3), calculated by IBGE with the addresses of the 2022 Census.
- **Territory:** IBGE municipal boundaries and geographic regions.
- **Location map:** country and state boundaries from Natural Earth 1:50m (public domain), simplified, to show
  where Rio Grande do Sul is in Brazil (Figure 1A).

The raw data are not in the repository: step 01 downloads them from the official sources. The panels in
`dados_agregados/` allow the series to be checked and reused without downloading the raw data again.

## License

Code under the MIT license (`LICENSE` file). Aggregated data, tables and figures under CC BY 4.0.

## How to cite

The full reference will be added after peer review.

## Resumo em português

Código, plano de análise, resultados completos e dados agregados do artigo submetido à chamada temática
"Atenção Psicossocial em Desastres Socioambientais" da *Ciência & Saúde Coletiva*. O estudo analisa o
cuidado nos Centros de Atenção Psicossocial (CAPS) e as internações psiquiátricas pelo SUS nos 497
municípios do Rio Grande do Sul após a enchente de 2024, de janeiro de 2015 a março de 2026. O painel
interativo, em `docs/`, abre em inglês e tem um botão para mudar para o português. O plano de análise, com o
registro datado de cada mudança, está em [PLANO_ANALISE.md](PLANO_ANALISE.md). Para refazer tudo, use
`rodar.py` (instruções acima); `--idioma pt` gera as figuras do manuscrito em português.
