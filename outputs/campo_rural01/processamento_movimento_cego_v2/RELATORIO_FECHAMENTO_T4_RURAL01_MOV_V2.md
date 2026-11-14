# Relatório de fechamento T4 — RURAL-01 MOV-V v2

## Resultado do fechamento

O módulo `MOV-V v2` foi congelado antes da revelação da posição verdadeira. A execução representa a resistência territorial ao deslocamento a partir do ponto inicial do RURAL-01 e mantém separadas duas hipóteses: uso possível da rede de vias/trilhas e deslocamento sem desconto da rede. Nenhuma das hipóteses foi escolhida automaticamente.

O congelamento significa que entradas, regras, código e saídas não poderão ser ajustados depois de conhecida a posição verdadeira. Ele não significa que os multiplicadores heurísticos estejam validados para emprego operacional.

## O que passou a influenciar o processamento

- cobertura e uso do solo, com a ressalva de que o WorldCover não mede o sub-bosque;
- relevo e variação de declividade derivados do SRTM;
- vias e trilhas mapeadas, em hipótese própria;
- hidrografia mapeada como proxy raster de proximidade ou entrada em célula;
- obstáculos de campo, quando existirem registros georreferenciados válidos. Nesta execução, nenhum obstáculo de campo foi espacializado.

O cálculo deixa de tratar todas as direções como igualmente fáceis. A distância continua relevante, mas cada percurso passa a acumular maior ou menor esforço conforme as células atravessadas. O produto mostra trajetos diagnósticos de menor custo na grade, e não rotas realmente percorridas ou ordens para equipes.

## Controles metodológicos

- posição verdadeira não consultada nem representada;
- 14 horas mantidas somente como contexto, sem conversão para distância, duração de marcha ou isócrona;
- `MOV-V` separado da acessibilidade das equipes (`MOV-E`) e da detectabilidade (`DET`);
- deduplicação entre hidrografia OSM e classes aquáticas/úmidas do WorldCover;
- duas hipóteses BASE processadas em paralelo;
- 21 testes automatizados aprovados;
- 37 portas de qualidade aprovadas;
- 8 arquivos centrais reproduzidos de forma idêntica em execução independente;
- 29 arquivos selados da versão v1 preservados.

## Leitura dos resultados

Na hipótese `H_REDE_DISPONIVEL`, os três primeiros postos de acessibilidade física relativa foram `R01-W`, `R01-E` e `R01-NE`. Na hipótese `H_FORA_REDE`, foram `R01-W`, `R01-N` e `R01-NE`.

Esses postos não são probabilidades de presença nem candidatos que “adivinham” onde a pessoa está. Eles indicam setores que, dentro da modelagem e de cada hipótese, acumulam menor resistência relativa a partir do ponto inicial. A permanência de `R01-W` e `R01-NE` nas duas leituras demonstra convergência parcial; a alternância entre `R01-E` e `R01-N` evidencia que o regime de uso da rede altera a interpretação e deve permanecer visível ao decisor.

## Limites conservados

O mapa permanece com estado `REVISAR` porque não há observação sistemática do sub-bosque, a rede OSM pode estar incompleta, o SRTM de aproximadamente 30 m pode suavizar barrancos e grotas e a hidrografia é uma aproximação raster, não um teste geométrico de travessia. A classificação de cobertura também não prova transitabilidade sob o dossel.

Esses limites não anulam o módulo. Eles delimitam sua contribuição atual: tornar explícito, reproduzível e auditável o efeito dos obstáculos e da conectividade sobre o deslocamento plausível, evitando que um círculo homogêneo seja interpretado como se todas as direções oferecessem a mesma dificuldade.

## Próxima etapa autorizada

Com o ledger T4 validado, a posição verdadeira poderá ser aberta e aplicada somente às métricas pré-especificadas: custo da célula de avaliação, percentil e banda de custo, setor correspondente, distância aos corredores congelados, comparação com a v1 e estabilidade entre hipóteses e sensibilidades. É vedado reajustar parâmetros após a revelação.
