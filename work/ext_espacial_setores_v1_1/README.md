# EXT-ESP-SET-v1.1 — setorização e priorização espacial DEV-S

Este diretório contém a versão 1.1 do componente que divide, caracteriza e
prioriza espacialmente os buffers produzidos pelo `EXT-ESP-BUF-v1.0`.

O protocolo está **congelado para desenvolvimento (DEV-S)**. Ele não constitui
validação confirmatória, localização da vítima, probabilidade de presença nem
ordem de emprego de equipes. Nenhum dado de ground truth participa da
geometria, da extração dos atributos, dos escores ou dos rankings.

## O que mudou na v1.1

A v1.1 substitui a execução diagnóstica v1.0 nos quatro pontos abaixo:

1. o contorno de cada buffer passa a ser o polígono recebido no GeoJSON, sem
   reconstrução circular independente;
2. os anéis internos são cópias homotéticas do contorno autoritativo, nas
   escalas `sqrt(1/3)` e `sqrt(2/3)`, e o limite externo é reutilizado
   exatamente;
3. o ranking usa competição, com Top-1 compartilhado em caso de igualdade e
   sem preferência substantiva pelo identificador do setor;
4. qualquer módulo GEO obrigatório ausente torna os escores e ranks daquele
   setor indisponíveis, sem renormalização dos pesos.

A versão 1.0 permanece apenas como linha de base de auditoria. O estado e os
hashes da execução v1.1 devem ser lidos nos arquivos da pasta `results/`, em
especial no manifesto e nos relatórios de verificação.

## Unidade de análise

Cada buffer de candidato é processado de forma independente. A chave do buffer
é:

```text
scenario_id + candidate_id
```

Cada setor é identificado por:

```text
{scenario_id}::{candidate_id}::R{anel com dois dígitos}::{direção}
```

Exemplo:

```text
RS-001::RS-001-C1::R02::SE
```

Não há `candidate_rank`, `buffer_id` inventado nem ranking global de setores.
O ranking do SETOR-v1.1 reinicia dentro de cada buffer e permanece separado do
ranking de candidatos produzido por outro componente da arquitetura.

## Geometria principal

O GeoJSON do `EXT-ESP-BUF-v1.0` é a geometria-pai autoritativa. O polígono deve
ser fechado, válido e convexo em relação ao ponto estimado do candidato
(portanto, também estrelado nesse ponto). Em
coordenadas métricas locais, cada raio que parte do candidato encontra o
contorno do polígono, e esse contorno é particionado em:

- três anéis definidos pelas escalas `0`, `sqrt(1/3)`, `sqrt(2/3)` e `1`;
- oito direções de 45 graus: N, NE, E, SE, S, SW, W e NW;
- 24 setores por buffer.

As transformações homotéticas preservam um terço da área do polígono-pai em
cada anel. As cunhas radiais completam a partição. A área esperada de cada
setor é:

```text
área planar do polígono autoritativo / 24
```

O contorno externo não é recalculado. A soma dos setores deve reproduzir a área
do polígono recebido dentro da tolerância relativa de `0,000001`, e a área de
cada setor deve respeitar a tolerância relativa de `0,01`.

As geometrias de sensibilidade previstas são 12 setores, 36 setores e rotação
de meia cunha. Elas não podem ser escolhidas após o conhecimento da referência.

## Módulos GEO e pesos

| Módulo | Conteúdo | Campo de escore |
|---|---|---|
| GEO-02 | Vias e trilhas | `road_trail_access_score` |
| GEO-03 | Hidrografia | `hydro_access_score` |
| GEO-04 | Relevo e declividade | `terrain_access_score` |
| GEO-05 | Cobertura e uso do solo | `landcover_access_score` |
| GEO-06 | Síntese territorial | combinação dos quatro anteriores |

Os quatro escores variam de 0 a 1 e são orientados para que valores maiores
indiquem maior favorabilidade territorial relativa. A configuração BASE é:

```text
P = 0,30 × GEO-02 + 0,25 × GEO-03 + 0,20 × GEO-04 + 0,25 × GEO-05
```

Também são calculados os conjuntos `IGUAIS`, `SEM_BARREIRAS`,
`APENAS_ACESSO` e `ENFASE_BARREIRAS`. Esses pesos são hipóteses de
desenvolvimento herdadas do GEO-06; não são pesos setoriais aprendidos ou
validados em campo.

Os rasters são avaliados por nove amostras estratificadas por setor. A v1.1
exige `9/9` amostras válidas para o módulo ser considerado disponível, e
registra contagem esperada, contagem válida e cobertura.

## Ranking de competição e empates

Os escores são comparados depois da quantização em nove casas decimais. O rank
é calculado por competição:

```text
rank_i = 1 + quantidade de setores com escore estritamente maior
```

Assim, uma sequência empatada pode assumir ranks `1, 2, 2, 4`. O
`sector_id` serve apenas para estabilizar a ordem física do arquivo; ele nunca
resolve um empate substantivo.

- empate no Top-1 da configuração BASE: nenhum setor é selecionado e a decisão
  fica `REVISAR`;
- empate em uma configuração de sensibilidade: todos os co-vencedores são
  registrados e recebem suporte fracionário;
- estabilidade: soma, entre os cinco conjuntos, de `1 / número de
  co-vencedores` quando o setor pertence ao conjunto Top-1, dividida por cinco;
- robustez: estabilidade de pelo menos `0,80` e quatro vitórias Top-1 únicas;
- margem BASE abaixo de `0,05`: `REVISAR`.

O resultado preserva as listas de co-vencedores por conjunto de pesos. Não se
transforma uma lista empatada em um falso Top-1 único.

## Dados ausentes

Nenhum valor ausente é convertido em zero, estimado ou tratado como evidência
favorável. Se qualquer um dos quatro escores GEO obrigatórios estiver ausente,
fora do intervalo permitido ou com cobertura inferior a 100%:

1. todos os escores agregados e ranks daquele setor ficam vazios;
2. os pesos não são renormalizados;
3. o buffer fica `REVISAR` e o motivo é registrado;
4. sem setor completo, nenhum setor é selecionado.

A ausência de uma feição no OpenStreetMap também não comprova ausência física.
Campos de proveniência obrigatórios ausentes produzem revisão explícita.

## Estados e alertas

Os únicos estados decisórios gravados são:

- `PRIORIZADO`: prioridade analítica única, completa e robusta dentro do
  buffer;
- `REVISAR`: exige supervisão humana antes de qualquer uso operacional.

Falhas de esquema, geometria, integridade, firewall ou proveniência que
impedem o processamento abortam a execução; não são gravadas como um terceiro
estado decisório.

Os códigos previstos incluem `UPSTREAM_REVIEW_REQUIRED`, `INCOMPLETE_GEO`,
`NO_COMPLETE_SECTOR`, `LOW_MARGIN`, `BASE_TOP_TIE`, `NO_UNIQUE_TOP1`,
`SENSITIVITY_TOP_TIE`, `RANKING_UNSTABLE`, `POTENTIAL_BARRIER`,
`MISSING_REQUIRED_GEO_SCORE` e `MISSING_SOURCE_PROVENANCE`.

## Firewall do ground truth

O firewall percorre recursivamente as chaves de todas as entradas e saídas,
sem diferenciar maiúsculas de minúsculas. A correspondência é por fragmento de
chave normalizado. Isso bloqueia tanto nomes diretos quanto variantes compostas
relacionadas à posição real, setor correto, distância à referência ou
pertencimento da referência.

A única exceção é o campo de controle `ground_truth_used`, que deve existir
somente com o valor booleano `false`. Qualquer violação aborta a execução.

O ground truth permanece fechado durante geometria, extração, pontuação,
ranking, repetição determinística e congelamento das saídas. Sua abertura só é
permitida no fluxo REP-S, depois da aprovação dos gates aplicáveis.

## Entradas

- JSON tabular do motor de buffer;
- GeoJSON autoritativo dos buffers;
- manifesto do motor de buffer;
- recortes OSM de vias/trilhas e hidrografia;
- quadrantes do modelo digital de elevação;
- quadrantes ESA WorldCover 2021;
- `config_setorizacao_priorizacao_v1_1.json`.

## Saídas científicas

- `sector_polygons_dev.geojson`;
- `sector_features_dev.csv`;
- `sector_ranking_dev.csv`;
- `buffer_decisions_dev.csv`;
- `sector_results_dev.json`;
- `warnings_dev.log`;
- `manifest_setorizacao_dev.json`.

Os relatórios de testes, verificação e determinismo complementam o pacote de
auditoria. A planilha de leitura é
`Sintese_Setorizacao_Priorizacao_DEV_S_v1_1.xlsx`.

Todas as saídas têm ordem determinística e preservam
`ground_truth_used=false`.

## Reprodução

```text
python3 motor_setorizacao_priorizacao.py \
  --config config_setorizacao_priorizacao_v1_1.json \
  --buffer-json ../ext_espacial_buffer_v1/results/buffer_results_dev.json \
  --buffer-geojson ../ext_espacial_buffer_v1/results/buffer_polygons_dev.geojson \
  --buffer-manifest ../ext_espacial_buffer_v1/results/manifest_execucao_dev.json \
  --roads ../../outputs/sprint2_s2_06_geo05_v33/osm_highways_raw.json \
  --hydro ../../outputs/sprint2_s2_06_geo05_v33/osm_hydrography_raw.json \
  --dem-dir ../../outputs/sprint2_s2_06_geo05_v33 \
  --worldcover-dir ../../outputs/sprint2_s2_06_geo05_v33/worldcover_tiles \
  --output-dir results
```

Os dados brutos GEO não são duplicados neste diretório. Caminhos e hashes
SHA-256 devem constar do manifesto.

## Gates mínimos

- configuração JSON válida e cinco conjuntos de pesos somando 1;
- 24 setores por buffer válido;
- contorno externo coincidente com o GeoJSON autoritativo;
- conservação da área-pai e ausência de sobreposição interna relevante;
- vértices setoriais contidos no polígono-pai;
- escores GEO no intervalo `[0,1]` ou explicitamente ausentes;
- ranking de competição restrito ao buffer;
- empates preservados sem seleção artificial;
- ausência estrita sem renormalização;
- firewall recursivo aprovado;
- duas execuções com resultados científicos idênticos;
- hashes de entradas, configuração, motor e saídas no manifesto.

## Limites de interpretação

- Setores radiais são unidades analíticas reprodutíveis, não zonas
  operacionais comprovadas em campo.
- Dados públicos não confirmam transitabilidade, largura de obstáculos nem
  condição territorial atual.
- O protocolo não consolida buffers sobrepostos e não cria ranking global
  entre candidatos.
- O escore expressa **prioridade operacional territorial relativa**. Ele não é
  probabilidade de presença, não afirma onde a vítima está e não substitui a
  decisão do comando SAR.
- Resultados DEV-S são evidência de engenharia do artefato, não evidência
  confirmatória de eficácia em missão real.

## Arquivos relacionados

- `ESPECIFICACAO_METODOLOGICA_SETOR_v1_1.md`;
- `../ext_espacial_buffer_v1/config_buffer_v1.json`;
- `../ext_espacial_buffer_v1/motor_buffer_adaptativo.py`;
- `../../outputs/sprint2_s2_06_geo05_v33/build_geo05_v33.mjs`;
- `../../outputs/sprint2_s2_07_geo06_v34/build_geo06_v34.mjs`;
- `../ext_espacial_rep_s_v1/protocolo_rep_s_v1.json`.
