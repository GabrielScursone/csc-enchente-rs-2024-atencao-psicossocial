# Plano de análise — Enchente de 2024 e internações psiquiátricas no SUS (RS)

Versão 1, 04/11/2026. Redigido antes de ajustar qualquer modelo. Antes disso, houve
uma única olhada descritiva nos dados brutos (contagens mensais de 2022–2024 em 25 municípios
atingidos × o restante do estado), registrada na seção 10 para transparência. Mudanças
posteriores entram na seção 12, com data e motivo.

## 1. Pergunta

A enchente de abril–maio de 2024 no Rio Grande do Sul alterou o volume, o perfil e o local das
internações por transtornos mentais e comportamentais financiadas pelo SUS? O efeito cresce com a
intensidade da exposição do município? Ele se distribui de forma desigual entre grupos
(sexo, idade, raça/cor) e entre tipos de cuidado (leito psiquiátrico × leito de saúde mental em
hospital geral)?

## 2. Hipóteses

- **H1 (estado):** de maio/2024 a março/2026, as internações com diagnóstico principal do
  capítulo F de residentes do RS diferem do esperado sem a enchente. O teste é bicaudal. Há dois
  mecanismos plausíveis e opostos: (a) mais sofrimento psíquico e mais uso de álcool e drogas, o
  que aumenta a demanda; (b) ruptura da rede e do acesso (hospitais, CAPS e transporte atingidos),
  o que reduz as internações.
- **H2 (dose-resposta):** o desvio em relação ao esperado varia monotonicamente com a proporção da
  população municipal residente em área inundada.
- **H3 (heterogeneidade, exploratória):** o desvio difere por grupo diagnóstico (álcool e outras
  drogas F10–F19; humor F30–F39; neuróticos e relacionados ao estresse F40–F48; psicóticos
  F20–F29), sexo, faixa etária e raça/cor.
- **H4 (fluxos, secundária):** nos municípios mais expostos, cresce a proporção de internações fora
  do município de residência e muda a composição por tipo de leito.

## 3. Dados

- **SIH/SUS, AIH reduzida (RD), RS**, competências de 01/2015 a 08/2026 (DATASUS, FTP público).
  Ficam as AIHs tipo 1 (IDENT=1) de residentes do RS. As AIHs de longa permanência (IDENT=5)
  continuam internações já contadas. As internações são datadas por `DT_INTER` (data de
  internação), não pela competência. Uma AIH repetida conta uma vez.
- **Janela:** internações de 01/2015 a 03/2026. Março/2026 tem 5 meses de processamento. Em
  2016–2023, 5 meses capturaram 99,88–99,98% das AIHs e 4 meses, 99,12–99,87% (ver
  `completude_por_atraso.csv`).
- **Exposição:** IBGE, "Dados agregados para as áreas afetadas – municípios do RS" (26/06/2024).
  São pessoas e estabelecimentos do Censo 2022/CNEFE dentro da mancha de inundação e
  deslizamentos v3, delimitada pelo grupo INPE/ANA. Há 345 municípios com área afetada. Os demais
  152 têm exposição 0.
- **População:** estimativas da SVS/MS por município, sexo e idade (2015–2025). 2026 repete 2025.
  Para raça/cor, o denominador é o Censo 2022.

## 4. Exposição

- **Principal:** % da população do município (Censo 2022) residente na área afetada, em uso
  contínuo (efeito por 10 pontos percentuais).
- **Categorias definidas a priori:** <1% (referência), 1–<10%, ≥10%. Na base do IBGE, 55
  municípios ficam em ≥10%.
- **Secundária:** número de estabelecimentos de saúde dentro da área afetada por 10 mil
  habitantes, como marcador de ruptura da oferta.
- **Tempo:** o primeiro mês exposto é maio/2024. Os períodos pós são: agudo (mai–jul/2024),
  subagudo (ago/2024–abr/2025) e tardio (mai/2025–mar/2026).

## 5. Desfechos

- **Primário:** internações com diagnóstico principal F00–F99 por 100 mil habitantes, por mês.
- **Secundários:** grupos F (F00–F09, F10–F19, F20–F29, F30–F39, F40–F48, demais), F10 e F43
  isolados, lesão autoprovocada (X60–X84 como diagnóstico secundário), óbito hospitalar com
  diagnóstico principal F e dias de permanência. Para H4: proporção de internações fora do
  município de residência e por tipo de leito (especialidade 05 = psiquiatria, 87 = saúde mental
  em hospital geral, demais).
- **Controles negativos:** partos (O80–O84) e apendicite (K35–K37). Eles medem a ruptura do acesso
  hospitalar sem relação com o sofrimento psíquico. Internações não F (todas as outras causas)
  indicam o efeito geral sobre o sistema.

## 6. Análise 1 — Contrafactual (esperado sem enchente)

- Os modelos são treinados com 01/2015–04/2024 e projetam 05/2024–03/2026 para o estado e para
  cada estrato de exposição.
  1. **Quase-Poisson** (antes previsto: binomial negativo; ver seção 12): tendência (spline natural,
     3 g.l.), mês do ano, indicador da pandemia (03/2020–12/2021) e offset log(população × dias no mês).
  2. **SARIMA** na taxa logarítmica, com ordem escolhida pelo AIC e indicador da pandemia como
     regressor.
  3. **LightGBM global** treinado no painel de municípios (objetivo Poisson). O offset é
     log(população) mais a taxa média do município antes do corte. As variáveis são calendário,
     tendência, indicador da pandemia, população, desvio da taxa dos 24 meses anteriores ao corte
     em relação à média e tendência do município. Nenhuma variável usa dado posterior ao corte. As previsões
     municipais somadas dão o esperado do estado e de cada estrato.
- **Validação:** cortes-placebo em 05/2018, 05/2019, 05/2022 e 05/2023, cada um com previsão de
  12 meses. Medidas: erro absoluto médio, viés e cobertura do intervalo de 95%.
- **Estimativa:** razão observado/esperado e excesso (observado − esperado) por período, com
  intervalo de 95%. O intervalo vem de simulação para o quase-Poisson, do próprio modelo para o SARIMA e de
  intervalos conformes derivados dos erros nos cortes-placebo para o LightGBM. O resultado
  principal é a média simples dos três modelos. Os modelos individuais vão para o suplementar.

## 7. Análise 2 — Dose-resposta (painel municipal)

- **Modelo:** Poisson com efeitos fixos de município e de mês-calendário (estudo de eventos) e
  offset log(população):
  `log E[Y_mt] = α_m + γ_t + Σ_k β_k · (exposição_m × 1[t ∈ trimestre k]) + log(pop_mt)`.
  Os trimestres são contados em relação a maio/2024, de −8 a +7. A referência é o trimestre
  fev–abr/2024. Os erros-padrão são agrupados por município.
- **Pré-tendência:** teste conjunto de β_k = 0 para k ≤ −2.
- **Resumo:** razão de taxas por 10 p.p. de exposição nos períodos agudo, subagudo e tardio.
  Também a mesma especificação com as três categorias de exposição.

## 8. Robustez e sensibilidade

1. Synthetic difference-in-differences: municípios com ≥10% × municípios com <1%.
2. Retirar Porto Alegre e, à parte, os municípios do Vale do Taquari atingidos em set/2023. Esses
   municípios tiveram exposição prévia e podem contaminar o período pré. Definição: regiões
   geográficas imediatas Lajeado e Encantado (IBGE, 2017).
3. Treinar o contrafactual sem 2020–2021.
4. Corte-placebo de exposição: maio/2023 como data falsa.
5. Desfechos-controle (seção 5).
6. Município de internação em vez de residência, para H4.
7. Tendência específica por macrorregião de saúde × ano.

## 9. Heterogeneidade (exploratória)

- Estudo de eventos por sexo, faixa etária (0–17, 18–39, 40–59, 60+), raça/cor (branca; preta +
  parda; indígena somente descritiva) e grupo diagnóstico.
- A raça/cor ignorada caiu de 19% (2015) para 0% (2024). Por isso, as análises por raça/cor usam
  só comparações no mesmo período entre municípios (efeito fixo de mês absorve a melhora geral) e
  repetem-se restritas a 05/2022–03/2026.
- Se houver tempo: causal forest sobre a razão observado/esperado municipal, com cobertura de
  CAPS, leitos de saúde mental, renda (Censo 2022) e porte. Os resultados serão apresentados como
  geradores de hipótese.

## 10. O que já foi visto antes deste plano

Contagens brutas por mês de internação (IDENT=1): no estado, 2024/média 2022–23 ficou entre 0,96
e 1,14 de janeiro a outubro. Em 25 municípios escolhidos como muito atingidos, maio–setembro/2024
ficou cerca de 3% abaixo da média de 2022–23, e o restante do estado ficou cerca de 2% acima. A
proporção de internações fora do município de residência nesses 25 municípios passou de 11–13%
(2023) para 14–15% (abr–set/2024). Nenhum modelo foi ajustado.

## 11. Emenda 1 — produção dos CAPS (04/11/2026)

**Quando e por quê.** Esta emenda foi escrita depois de conhecer os resultados das internações
(seções 6–8), mas antes de baixar ou olhar os dados dos CAPS. As internações totais não mudaram
com a enchente. A pergunta complementar, central para a chamada, é se a atenção psicossocial
ambulatorial absorveu a demanda. Todas as análises desta emenda são secundárias.

**Hipóteses.**
- H5: nos municípios mais expostos, o número de usuários atendidos nos CAPS e, sobretudo, o de
  usuários novos aumentou após a enchente, em relação ao esperado e de forma dose-dependente.
- H6: as ações de atenção à crise e o atendimento domiciliar aumentaram nos municípios mais
  expostos.
- H7, alternativa: a produção caiu no período agudo por interrupção dos serviços. Essa hipótese é
  avaliada pelo número de CAPS com produção no município.

**Dados.** SIA/SUS, RAAS psicossocial (arquivos PSRSAAMM.dbc), competências 01/2015–08/2026, por
município de residência (`MUNPAC`) e mês de atendimento (`DT_ATEND`), na mesma janela das
internações (até 03/2026). Se a completude por atraso de apresentação for menor que 99%, a janela
dos CAPS é encurtada, e isso fica registrado.

**Desfechos.**
- **Usuários atendidos:** soma de `QTDPCN`, uma RAAS por usuário por CAPS por mês. É a medida
  "quantidade de pacientes" do TabNet.
- **Usuários novos:** RAAS cujo início do acompanhamento (`DT_INICIO`) cai no mês de atendimento.
- **Usuários com CID principal F10–F19** e **usuários com CID principal F40–F48**.
- **Procedimentos produzidos** (`PA_QTDPRO`): total e por tipo:
  - atenção à crise (03.01.08.029-1);
  - atendimento individual (020-8), em grupo (021-6), familiar (022-4) e domiciliar (024-0);
  - acolhimento diurno, noturno ou em terceiro turno (019-4, 002-0, 003-8).
- **Oferta:** número de CAPS (`CNES_EXEC`) com produção no mês, pelo município onde o CAPS fica
  (`UFMUN`).

**Análises.** As mesmas das seções 6, 7 e 8.1: contrafactual com os três modelos e o ensemble,
dose-resposta por estudo de eventos e por período, e SDID. Os desfechos principais desta emenda
são usuários atendidos e usuários novos.

**Limitações conhecidas.** As ações coletivas dos CAPS registradas em BPA (matriciamento,
articulação de redes) não estão na RAAS. As mudanças de registro e a expansão da rede de CAPS ao
longo da década entram como tendência nos modelos.

## 12. Registro de mudanças

- **04/11/2026: fim da janela em 03/2026** (antes, 04/2026). A tabela de completude mostrou
  que 4 meses de processamento capturam 99,1–99,9% das AIHs, não ≥99,9% como estimado. Com
  5 meses, a captura chega a 99,88–99,98%.
- **04/11/2026: intervalos do LightGBM.** Em vez de intervalos conformes, o LightGBM usa
  bootstrap de municípios (20 reamostras) mais ruído de Poisson. Quatro janelas-placebo são
  poucas para quantis conformes estáveis. A cobertura obtida nos placebos fica registrada em
  `validacao_placebo.csv`. O resultado principal continua sendo o ensemble.
- **04/11/2026: olhada não planejada.** No teste de código do script 05, feito com
  competências só até 12/2024 e com pós-período de 05–08/2024, apareceram razões
  observado/esperado preliminares. Para F00–F99: estado 0,97; estrato ≥10% 0,95; estrato
  <1% 0,98. Para partos: estrato ≥10% 0,97. Essa olhada não alterou nenhuma escolha deste
  plano.
- **04/11/2026: definições territoriais.** O Vale do Taquari passa a ser definido pelas regiões
  geográficas imediatas Lajeado e Encantado do IBGE. A macrorregião usada na tendência
  específica é a macrorregião de saúde do DATASUS. Se a base territorial do DATASUS não puder
  ser baixada, usa-se a região geográfica intermediária do IBGE. A fonte usada fica registrada
  em `territorio_municipios.csv`. As duas decisões foram tomadas antes de ajustar os modelos
  com os dados completos.
- **04/11/2026: competência 08/2026 parcial.** O arquivo RDRS2608 publicado tem 34.801 registros,
  contra cerca de 75 mil nos meses vizinhos. Ele foi conferido duas vezes, pelo FTP e pelo
  portal de transferência, com o mesmo tamanho. A janela de internações continua terminando em
  03/2026, que tem 4 meses completos de processamento (99,1–99,9% em 2016–2023) mais o mês
  parcial.
- **04/11/2026: dias no mês no offset.** No binomial negativo, os dias do mês entraram no offset
  (log de pessoa-dias), e não mais como covariável. Como covariável, eles eram quase colineares
  com os indicadores de mês (só fevereiro bissexto difere), o que gerava erros-padrão instáveis.
  As previsões pontuais praticamente não mudam. Para séries em que o binomial negativo não
  converge com covariância utilizável (superdispersão próxima de zero), o ajuste usa quase-Poisson.
  Os casos ficam registrados no log da etapa 05.
- **04/11/2026: quase-Poisson no lugar do binomial negativo.** Mesmo com os dias no offset, o
  binomial negativo não convergiu com covariância utilizável em 68 de 180 combinações de série e
  corte. A superdispersão ficou próxima de zero nesses casos. A regressão quase-Poisson, com
  dispersão de Pearson, tem a mesma estrutura de média, é padrão em estudos de excesso de eventos
  e converge em todas as séries. A preditiva é simulada com variância φμ. Uma série muito esparsa
  sem ajuste utilizável fica sem esse modelo, e o ensemble usa os demais.
- **04/11/2026: offset do LightGBM.** A taxa média de cada município antes do corte passou a fazer
  parte do offset, e não mais das variáveis. Com ela como variável, o objetivo Poisson do
  LightGBM superestimava desfechos de taxa alta. Em "demais causas", o total de treino saiu
  1,8 vez o observado, e o contrafactual saiu cerca de 500 vezes maior. Com o offset, o total de
  treino bate com o observado em todos os desfechos (diferença <0,1%). O perfil sazonal
  municipal, previsto na v1, não foi usado: o mês do ano é variável do modelo global.
- **04/11/2026: CAPS, falha de registro e margens (análise acrescentada depois de ver os dados).**
  - O número de CAPS com produção caiu em abril/2024, antes da enchente, inclusive nos municípios
    não atingidos. Dos 155 CAPS que registravam produção em todo o 1º trimestre de 2024, 32 a 36 não
    registraram nada em abril, maio ou junho. Em 2022–2023, esse número ficava entre 3 e 12 por mês.
    A maioria voltou a registrar até dezembro. É provável que parte da produção desse período nunca
    tenha sido lançada (falha de registro).
  - Para separar falha de registro de interrupção do cuidado, foi acrescentada uma análise
    exploratória por estabelecimento, nos 155 CAPS, entre 05/2022 e 03/2026:
    - margem extensiva: probabilidade de um CAPS ficar sem registro no mês (modelo linear com EF de
      CAPS e de mês);
    - margem intensiva: usuários por CAPS nos meses com registro (Poisson com EF de CAPS e de mês);
    - nas duas, a exposição é a do município onde o CAPS fica.
  - A queda de abril/2024 não depende da exposição. As duas margens pioram com a exposição nos
    períodos agudo e tardio. Os resultados estão em `resultados/03_robustez/caps_margens_extensiva_intensiva.csv`.
- **04/11/2026: desigualdades por sexo e raça/cor (seção 9, exploratória).**
  - O efeito foi estimado por modelo de Poisson empilhado, com um par de grupos por vez (mulheres ×
    homens; pretos ou pardos × brancos), efeitos fixos de município × grupo e de mês × grupo. A
    medida é a razão entre as RTs dos dois grupos.
  - Raça/cor sem informação: na RAAS, 30% em 2015, 16% em 2022 e ≤3,4% só a partir de 07/2023; no
    SIH, 0% a partir de 04/2023.
  - Por isso, raça/cor usa a janela 07/2023–03/2026, com sensibilidade a partir de 10/2023, e não
    05/2022–03/2026 como previsto na v1. Sexo usa a série inteira.
  - A raça/cor dos usuários dos CAPS foi acrescentada ao painel nesta data.
