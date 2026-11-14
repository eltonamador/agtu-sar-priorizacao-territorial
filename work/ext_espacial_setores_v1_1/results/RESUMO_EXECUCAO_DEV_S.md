# Resumo da execução DEV-S — EXT-ESP-SET-v1.1

## Resultado

O motor processou 90 buffers correspondentes a 30 cenários e três candidatos
por cenário. Cada buffer foi dividido em 24 setores, totalizando 2.160 unidades
espaciais com atributos GEO-02, GEO-03, GEO-04 e GEO-05 recalculados no próprio
setor. Todos os setores apresentaram completude GEO 4/4.

O ranking foi produzido exclusivamente dentro de cada buffer. Houve Top-1 BASE
único nos 90 buffers; isso identifica o primeiro colocado analítico, mas não
autoriza emprego operacional. Após os gates de margem, robustez e barreiras,
2 decisões receberam `PRIORIZADO` e 88 receberam `REVISAR`.

| Indicador | Resultado |
|---|---:|
| Cenários | 30 |
| Buffers/candidatos | 90 |
| Setores por buffer | 24 |
| Setores totais | 2.160 |
| Setores com GEO 4/4 | 2.160 |
| Top-1 BASE único | 90 |
| `PRIORIZADO` | 2 |
| `REVISAR` | 88 |
| Margem BASE média | 0,014874308 |
| Estabilidade fracionária média do Top-1 | 0,683611111 |

Os dois buffers que atenderam simultaneamente aos gates foram:

- `DV2-007 / DV2-007-C2`, setor `R01::E`, margem `0,052905367` e estabilidade `0,80`;
- `DV2-009 / DV2-009-C1`, setor `R03::E`, margem `0,050556703` e estabilidade `0,80`.

## Alertas de supervisão

Os alertas são cumulativos e não representam erro de processamento:

| Código | Buffers |
|---|---:|
| `LOW_MARGIN` | 85 |
| `POTENTIAL_BARRIER` | 59 |
| `RANKING_UNSTABLE` | 51 |
| `SENSITIVITY_TOP_TIE` | 15 |

Os 15 empates ocorreram em configurações de sensibilidade. Eles foram mantidos
como conjuntos de co-vencedores e contribuíram por suporte fracionário; nenhum
identificador técnico foi usado para escolher artificialmente um vencedor.
Não houve empate Top-1 na configuração BASE nesta execução.

## Integridade geométrica

Os setores foram construídos sobre o contorno GeoJSON autoritativo de cada
buffer, em projeção azimutal equidistante local, com anéis homotéticos. A
verificação independente registrou:

- erro relativo máximo de conservação da área-pai: `5,11 × 10⁻¹⁰`;
- erro relativo máximo de igualdade setorial: `6,4508 × 10⁻⁸`;
- setores com vértice fora do pai: `0`;
- pares com sobreposição interna relevante: `0`;
- arestas externas do pai não cobertas: `0`.

Em relação à linha de base v1.0, a correção do domínio geométrico alterou o
Top-1 de um único buffer (`DV2-018 / DV2-018-C3`, de `R02::NE` para
`R03::NE`). O balanço de estados permaneceu em 2 `PRIORIZADO` e 88 `REVISAR`.

## Qualidade e reprodutibilidade

- testes unitários e de contrato: **34/34 PASS**;
- verificações independentes: **16/16 PASS**;
- repetição integral: os seis arquivos científicos foram idênticos byte a byte;
- hash da projeção científica:
  `bff2deb9cf329096d7191b86381d5570c2df6905ba51499242d51c07531053dc`;
- hash do conjunto dos seis outputs:
  `0d90933c35117cf6abc62346ec790e38328c65fa9af9f94752a8554286cbc837`.

## Limite de interpretação

O escore expressa prioridade territorial relativa entre setores do mesmo
buffer. Ele não é probabilidade de presença, não afirma onde a vítima está e
não substitui decisão humana. O ground truth permaneceu fechado durante toda a
setorização, extração GEO, pontuação, repetição e verificação. A avaliação
confirmatória somente poderá ocorrer em etapa REP-S posterior ao congelamento
destas saídas.
