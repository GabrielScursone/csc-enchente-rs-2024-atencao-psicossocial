# Enchente de 2024, atenção nos CAPS e internações psiquiátricas no Rio Grande do Sul

Código, plano de análise, resultados e dados agregados do artigo submetido à chamada temática
"Atenção Psicossocial em Desastres Socioambientais" da revista *Ciência & Saúde Coletiva*.

**Pergunta.** A enchente de abril e maio de 2024 mudou as internações psiquiátricas pelo SUS e a
atenção nos Centros de Atenção Psicossocial (CAPS) dos residentes do Rio Grande do Sul? O efeito foi
maior nos municípios com maior parcela da população atingida?

**Desenho.** Estudo ecológico com séries temporais de 497 municípios, de janeiro de 2015 a março de 2026,
com duas análises e uma checagem de robustez:

1. **Contrafactual:** o que seria esperado sem a enchente, por média de três modelos treinados até abril de
   2024 (regressão quase-Poisson, SARIMA e LightGBM), validados em quatro cortes fictícios.
2. **Dose-resposta:** regressão de Poisson com efeitos fixos de município e mês e estudo de eventos. A
   exposição é a proporção da população residente na área atingida.
3. **Robustez:** controle sintético de diferenças em diferenças (SDID), produção dos CAPS por
   estabelecimento e desigualdades por sexo e raça/cor.

O plano de análise, com hipóteses, desfechos e registro datado de cada alteração, está em
[PLANO_ANALISE.md](PLANO_ANALISE.md).

## Estrutura

| Pasta ou arquivo | Conteúdo |
|---|---|
| `PLANO_ANALISE.md` | Plano de análise e registro de mudanças |
| `rodar.py` | Roda todas as etapas em ordem |
| `codigo/` | Uma etapa por script (tabela abaixo) |
| `dados_agregados/` | Painéis por município × mês (internações, CAPS, população, exposição) e dicionário de variáveis |
| `resultados/01_contrafactual/` | Observado, esperado e razão O/E por desfecho, categoria de exposição e período; validação |
| `resultados/02_dose_resposta/` | Razões de taxas, estudos de eventos, testes de tendência prévia e sensibilidades |
| `resultados/03_robustez/` | SDID e margens extensiva e intensiva dos CAPS |
| `resultados/04_desigualdades/` | Efeito por sexo e raça/cor |
| `resultados/figuras/` | Figuras do artigo e suplementares (PNG 300 dpi e PDF) |
| `resultados/resultados_enchente_sihsus_rs.xlsx` | Todas as tabelas numa planilha |

## Reproduzir

Ambiente testado: Python 3.14.2 em Linux. A etapa 01 baixa os dados públicos do DATASUS e do IBGE
(cerca de 2 GB). O FTP do DATASUS bloqueia o IP quando recebe conexões simultâneas, por isso o download
usa uma conexão só.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python rodar.py                      # tudo, cerca de 40 min
.venv/bin/python rodar.py --etapas 05,06,07    # só algumas etapas
```

| Etapa | Script (`codigo/`) | O que faz |
|---|---|---|
| 01 | `01_baixar_dados.py` | Baixa os arquivos RD (SIH/SUS) e PS (SIA/SUS, RAAS psicossocial), as populações, a malha e a exposição; grava somas SHA-256 |
| 02 | `02_extrair_rd.py` | Converte cada `.dbc` em Parquet |
| 03 | `03_montar_base.py` | Internações por data de internação; painel município × mês |
| 03b | `03b_montar_caps.py` | Produção dos CAPS por município de residência × mês de atendimento |
| 04 | `04_populacao_exposicao.py` | População mensal, exposição por município, regiões |
| 05 | `05_contrafactual.py` | Análise 1: esperado sem a enchente |
| 06 | `06_dose_resposta.py` | Análise 2: Poisson com efeitos fixos, estudo de eventos, sensibilidades |
| 09 | `09_robustez_sdid.py` | SDID (implementação própria, validada no exemplo da Proposição 99: −15,60) e CAPS por estabelecimento |
| 12 | `12_desigualdades.py` | Efeito por sexo e raça/cor |
| 07 | `07_figuras.py` | Figuras |
| 08 | `08_tabelas.py` | Tabelas e planilha |
| 10 | `10_entrega.py` | Pasta de entrega com LEIA-ME e ZIP |

## Dados

Todos os dados são públicos e agregados, sem identificação individual. Por isso, o estudo dispensa
apreciação por Comitê de Ética (Resolução CNS 510/2016, art. 1º).

- **SIH/SUS:** AIH reduzida (arquivos RD) do RS, competências 01/2015–08/2026. Foram usadas as AIH
  tipo 1 de residentes, datadas pela data de internação.
- **SIA/SUS:** RAAS psicossocial (arquivos PS) do RS, 01/2015–08/2026.
- **População:** estimativas por município, sexo e idade do Ministério da Saúde (2015–2025).
- **Exposição:** população residente na área atingida por inundações e deslizamentos de 2024 (mancha
  INPE/ANA, versão 3), calculada pelo IBGE com os endereços do Censo 2022.
- **Território:** malha municipal e regiões geográficas do IBGE.

Os dados brutos não estão no repositório: a etapa 01 os baixa das fontes oficiais. Os painéis em
`dados_agregados/` permitem conferir e reutilizar as séries sem refazer o download.

## Licença

Código sob licença MIT (arquivo `LICENSE`). Dados agregados, tabelas e figuras sob CC BY 4.0.

## Como citar

A referência completa será incluída após a avaliação por pares.
