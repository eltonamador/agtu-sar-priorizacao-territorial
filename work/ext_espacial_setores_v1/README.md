# EXT-ESP-SET-v1.0 — setorização e priorização espacial DEV-S

Este diretório especifica a primeira implementação de desenvolvimento da
setorização radial e da priorização espacial sobre os buffers produzidos pelo
motor `EXT-ESP-BUF-v1.0`.

O protocolo está **congelado para desenvolvimento (DEV-S)**. Ele não constitui
execução confirmatória, validação operacional, localização da vítima nem ordem
de emprego de equipes. Nenhum dado de ground truth integra a geometria, os
atributos, os escores ou os rankings.

## Estado da implementação

O motor foi implementado e executado sobre os 90 buffers diagnósticos do DEV.
A execução produziu 2.160 setores, 90 decisões intrabuffer, quatro módulos GEO
completos em todos os setores e manifesto de proveniência. A suíte de contrato
aprovou 25/25 testes e uma segunda execução integral reproduziu exatamente os
seis arquivos científicos da primeira execução.

Resultados principais:

- `results/sector_polygons_dev.geojson`;
- `results/sector_features_dev.csv`;
- `results/sector_ranking_dev.csv`;
- `results/buffer_decisions_dev.csv`;
- `results/sector_results_dev.json`;
- `results/manifest_setorizacao_dev.json`;
- `results/determinism_report.json`;
- `results/RESUMO_EXECUCAO_DEV_S.md`.

## Finalidade

O componente transforma cada buffer adaptativo em unidades espaciais
comparáveis e produz uma prioridade relativa, rastreável e reproduzível entre
os setores do próprio buffer. Ele implementa a passagem da Camada 2, expansão
espacial, para a Camada 4, priorização multicritério, mantendo a Camada 3 e o
ranking de candidatos como produtos distintos.

O protocolo não cria ranking conjunto entre candidatos. Cada buffer é uma
unidade independente e recebe seu próprio ranking de 1 a 24. Essa delimitação
evita tratar setores sobrepostos de candidatos diferentes como se formassem
uma única partição territorial, problema que exige protocolo próprio.

## Geometria principal

Cada buffer circular é dividido em 24 setores:

- três anéis de área igual;
- oito direções de 45 graus, centradas em N, NE, E, SE, S, SW, W e NW;
- azimute contado no sentido horário a partir do norte verdadeiro;
- área teórica de cada setor igual a `pi × R² / 24`.

Os limites radiais são calculados por:

```text
r_i = R × sqrt(i / 3), para i = 0, 1, 2 e 3
```

Assim, os limites correspondem aproximadamente a `0`, `0,57735 R`,
`0,81650 R` e `R`. Os identificadores seguem o padrão:

```text
{scenario_id}::{candidate_id}::R{anel}::{direção}
```

As geometrias de sensibilidade previstas são 12 setores, 36 setores e rotação
de meia largura angular. Elas servem para avaliar dependência da resolução e da
orientação e não podem ser escolhidas depois de conhecer a referência.

## Módulos GEO e pesos

A taxonomia adotada é a dos artefatos reprodutíveis já existentes:

| Módulo | Conteúdo | Campo de escore |
|---|---|---|
| GEO-02 | Vias e trilhas | `road_trail_access_score` |
| GEO-03 | Hidrografia | `hydro_access_score` |
| GEO-04 | Relevo e declividade | `terrain_access_score` |
| GEO-05 | Cobertura e uso do solo | `landcover_access_score` |
| GEO-06 | Síntese territorial | combinação dos quatro anteriores |

O escore usa combinação linear ponderada de valores entre 0 e 1, orientados
para que valores maiores indiquem maior adequação analítica:

```text
P_j = M_j × soma(w_k × x_jk) × produto(1 - p_jm)
```

No DEV-S v1, `M_j` vale 1. Mapas públicos não autorizam veto absoluto sem
evidência operacional independente e regra previamente registrada. Também não
há penalização adicional de barreira, porque GEO-03 e GEO-05 já incorporam esse
efeito em seus escores; uma segunda penalização produziria dupla contagem.

### Conjuntos de pesos

| Conjunto | Vias/trilhas | Hidrografia | Relevo | Cobertura | Uso |
|---|---:|---:|---:|---:|---|
| BASE | 0,30 | 0,25 | 0,20 | 0,25 | Principal no DEV-S |
| IGUAIS | 0,25 | 0,25 | 0,25 | 0,25 | Sensibilidade |
| SEM_BARREIRAS | 0,60 | 0,00 | 0,40 | 0,00 | Ablação |
| APENAS_ACESSO | 1,00 | 0,00 | 0,00 | 0,00 | Ablação |
| ENFASE_BARREIRAS | 0,20 | 0,35 | 0,15 | 0,30 | Sensibilidade |

Esses pesos foram herdados do protocolo GEO06-v1. Eles são hipóteses de
desenvolvimento aplicadas anteriormente a candidatos pontuais e **não são pesos
setoriais validados**.

## Ranking, margem e estabilidade

O ranking principal é calculado apenas entre os 24 setores do mesmo buffer. A
ordenação usa escore decrescente. O identificador do setor é usado somente para
serialização determinística de empates; não representa preferência substantiva.

- margem: diferença entre o primeiro e o segundo escores BASE;
- margem abaixo de `0,05`: `REVISAR`;
- estabilidade Top-1: número de conjuntos de pesos nos quais o setor vence,
  dividido por cinco;
- estabilidade mínima: `0,80`, equivalente a vitória em pelo menos quatro dos
  cinco conjuntos;
- empate, instabilidade, ausência de setor viável ou conflito forte:
  `REVISAR`.

Os parâmetros `0,05` e `0,80` são herdados para diagnóstico. Devem permanecer
submetidos à análise de sensibilidade antes de uma futura REP-S.

## Dados ausentes

Nenhum valor ausente pode ser inventado ou tratado como favorável. Quando um
dos quatro escores GEO obrigatórios estiver ausente, inválido ou incompleto:

1. o escore de prioridade e o ranking ficam vazios;
2. o setor recebe `REVISAR`;
3. o evento é registrado por código de alerta;
4. os pesos não são renormalizados sobre os campos disponíveis.

Atributos GEO pontuais ou calculados em janelas antigas não podem ser apenas
copiados para os setores. Eles precisam ser extraídos novamente sobre cada
polígono setorial, com fonte, resolução, método e limitações registrados.

## Firewall do ground truth

O motor rejeita campos associados à posição verdadeira, setor correto,
distância à referência ou pertencimento da referência. O único campo de
controle admitido é `ground_truth_used`, obrigatoriamente com valor booleano
`false`.

O ground truth permanece fechado durante:

1. geração das geometrias;
2. extração dos atributos GEO;
3. cálculo dos cinco conjuntos de escores;
4. ranking e decisão de revisão;
5. repetição determinística;
6. congelamento de saídas, logs e manifestos.

Sua abertura futura somente poderá ocorrer depois da aprovação dos gates do
protocolo REP-S aplicável. Se a referência estiver fora do buffer, o evento
deverá ser contado como falha de cobertura; o buffer e os setores não poderão
ser alterados retrospectivamente.

## Entradas previstas

- resultados tabulares do motor de buffer;
- polígonos GeoJSON dos buffers;
- atributos GEO recalculados por setor;
- configuração JSON desta versão.

Chaves mínimas:

```text
buffer: scenario_id + candidate_id
setor:  scenario_id + candidate_id + sector_id
```

## Saídas previstas

- `sector_polygons.geojson`: 24 polígonos por buffer;
- `sector_features.csv`: atributos GEO por setor;
- `sector_ranking.csv`: critérios, contribuições, cinco escores, rankings,
  margem, estabilidade, alertas e status;
- `sector_results.json`: saída científica estruturada;
- `manifest_execucao_setores.json`: hashes de entradas, configuração, motor e
  saídas.

Todas as saídas devem ter ordem determinística e `ground_truth_used=false`.

## Reprodução

Usar o Python empacotado no ambiente de trabalho, com Pillow disponível:

```text
python3 motor_setorizacao_priorizacao.py \
  --config config_setorizacao_priorizacao_v1.json \
  --buffer-json ../ext_espacial_buffer_v1/results/buffer_results_dev.json \
  --buffer-geojson ../ext_espacial_buffer_v1/results/buffer_polygons_dev.geojson \
  --buffer-manifest ../ext_espacial_buffer_v1/results/manifest_execucao_dev.json \
  --roads ../../outputs/sprint2_s2_06_geo05_v33/osm_highways_raw.json \
  --hydro ../../outputs/sprint2_s2_06_geo05_v33/osm_hydrography_raw.json \
  --dem-dir ../../outputs/sprint2_s2_06_geo05_v33 \
  --worldcover-dir ../../outputs/sprint2_s2_06_geo05_v33/worldcover_tiles \
  --output-dir results
```

Os dados brutos GEO não são duplicados neste diretório. Seus caminhos e hashes
SHA-256 constam do manifesto da execução.

## Critérios mínimos de aceite

- JSON de configuração válido;
- cinco conjuntos de pesos somando 1;
- exatamente 24 setores para cada buffer válido;
- polígonos fechados, válidos e dentro dos limites geográficos;
- áreas iguais dentro da tolerância de 1%;
- união dos setores compatível com o buffer de origem;
- ausência de sobreposição interna além das fronteiras compartilhadas;
- escores GEO entre 0 e 1;
- firewall sem vazamento de ground truth;
- duas execuções com resultados científicos idênticos;
- hashes registrados no manifesto;
- ranking restrito ao próprio buffer.

## Limitações obrigatórias de interpretação

- Setores radiais são unidades analíticas regulares, não zonas operacionais
  comprovadas em campo.
- OSM, hidrografia, relevo e cobertura pública não confirmam transitabilidade
  atual, largura de obstáculos ou condição observada no local.
- Os pesos são hipóteses DEV-S e não foram validados para setores.
- O protocolo não consolida buffers sobrepostos e não produz ranking global
  entre candidatos.
- A prioridade indica adequação relativa segundo os critérios disponíveis; não
  determina onde a vítima está e não substitui o comandante da missão SAR.
- Resultados obtidos com os buffers legados permanecem diagnósticos de
  engenharia e não devem ser apresentados como evidência confirmatória.

## Arquivos de origem relacionados

- `../ext_espacial_buffer_v1/config_buffer_v1.json`;
- `../ext_espacial_buffer_v1/motor_buffer_adaptativo.py`;
- `../../outputs/sprint2_s2_06_geo05_v33/build_geo05_v33.mjs`;
- `../../outputs/sprint2_s2_07_geo06_v34/build_geo06_v34.mjs`;
- `../ext_espacial_rep_s_v1/protocolo_rep_s_v1.json`.

