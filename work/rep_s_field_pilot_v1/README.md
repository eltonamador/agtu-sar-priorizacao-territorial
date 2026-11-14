# FIELD-CAND-v1.0

Gerador standalone e congelavel de candidatos semissinteticos para o piloto de
campo `REP-S-FIELD-PILOT`. O componente usa somente a biblioteca padrao do
Python e foi separado do motor de buffer, dos modulos GEO e do ranking.

## Escopo metodologico

O gerador recebe quatro posicoes protegidas de campo e produz tres candidatos
por site. A posicao protegida e usada exclusivamente para aplicar deslocamentos
semissinteticos. Ela nao aparece na saida cega e nao pode ser entregue ao
buffer, ao processamento GEO ou ao ranking.

Este protocolo evita a dependencia identificada no gerador legado:

- o raio-base e fixo em `2.000 m` para todos os candidatos;
- `r0_semantics=nominal_base`;
- `detection_quality` e `information_age_min` usam sorteios proprios e nao sao
  calculados a partir da distancia gerada;
- `position_dispersion_m` e `factors_applied` permanecem vazios;
- o ambiente vem apenas do estrato planejado antes da coleta.

Os candidatos continuam semissinteticos. Portanto, este componente permite
testar o fluxo de processamento em campo, mas nao transforma a entrada em uma
deteccao aerotransportada operacional independente.

## Arquivos

- `config_field_candidates_v1.json`: protocolo e parametros congelados;
- `generate_field_candidates.py`: gerador e firewall;
- `test_generate_field_candidates.py`: testes com coordenadas ficticias.

Nenhum arquivo com candidatos reais acompanha este diretorio.

## Entrada reservada

CSV UTF-8, delimitado por virgula, com exatamente quatro linhas e os campos:

```text
site_id,scenario_id,ground_truth_lat,ground_truth_lon,planned_environment
```

Use ponto como separador decimal. Os quatro estratos devem aparecer uma vez:

- `Urbano`;
- `Semirrural`;
- `Rural`;
- `Mata`.

O arquivo deve permanecer em local reservado. Nao o copie para a pasta de
entrada do buffer ou dos modulos GEO.

## Regra congelada de geracao

- protocolo: `FIELD-CAND-v1.0`;
- data de congelamento: `2026-10-15`;
- quatro sites, tres candidatos por site;
- seed material:
  `FIELD-CAND-v1.0|REP-S-FIELD-PILOT|AGTU|2026-10-15`;
- SHA-256 da seed:
  `f41da30635e383266f3739cf025e4b9f030a5e2db91fc14559cb30de847f1b5f`;
- estado inicial uint32: `4095582982`;
- PRNG: `xorshift32`;
- ordem dos sites: `scenario_id`, depois `site_id`;
- por site, duas chamadas permutam as faixas e quatro chamadas geram cada
  candidato: distancia, bearing, qualidade e idade;
- total esperado: 56 sorteios.

Cada site recebe exatamente um candidato em cada faixa:

| Faixa | Intervalo |
| --- | ---: |
| PROXIMO | 250 m <= d < 800 m |
| INTERMEDIARIO | 800 m <= d < 2.000 m |
| DISTANTE | 2.000 m <= d < 4.500 m |

As faixas sao permutadas entre os slots C1, C2 e C3 por Fisher-Yates. O bearing
e uniforme no intervalo `[0, 360)`. A qualidade e uniforme em `[0,35, 0,95)` e
a idade e uniforme discreta entre 5 e 180 minutos.

## Execucao futura

Depois da coleta e da consolidacao protegida das quatro referencias:

```bash
python3 work/rep_s_field_pilot_v1/generate_field_candidates.py \
  --input-gt /caminho/reservado/ground_truth_field.csv \
  --blind-output /caminho/cego/field_candidates_blind.csv \
  --secure-output /caminho/reservado/field_candidates_secure.csv \
  --manifest-output /caminho/auditoria/field_candidates_manifest.json
```

O programa recusa:

- a coincidencia entre os caminhos das saidas cega e segura;
- sobrescrever saidas sem `--overwrite`;
- quantidade diferente de quatro sites;
- IDs duplicados;
- estratos ausentes ou repetidos;
- configuracao ou seed divergente;
- colunas reservadas no schema cego;
- coordenadas invalidas.

## Saidas

1. **CSV cego**: unica entrada autorizada para buffer, GEO e ranking. Nao
   contem coordenada protegida, distancia gerada, bearing, faixa ou indicacao
   do candidato mais proximo. Inclui `site_id` e um `source_row_hash` calculado
   somente a partir do registro publico do candidato, sem hash da linha de
   ground truth.
2. **CSV seguro**: log reservado com a referencia e todos os parametros de
   geracao. Deve permanecer separado.
3. **Manifesto JSON**: protocolo, seed, contagens, estado final do PRNG, schemas
   e hashes SHA-256 da configuracao, entrada reservada e saidas. O hash do
   arquivo de ground truth permanece somente neste manifesto de auditoria.

O script contem o SHA-256 esperado da configuracao congelada. Qualquer edicao
do JSON e recusada antes da geracao. A checagem de caminhos tambem inclui o
proprio arquivo de configuracao, que nao pode ser usado como saida nem mesmo
com `--overwrite`.

O momento `T1` ocorre apos o congelamento do CSV cego e do manifesto. Somente
depois podem ser executados o buffer e os modulos GEO. A abertura da referencia
para avaliacao pertence ao momento `T3`, depois do congelamento das saidas do
modelo em `T2`.

## Testes

Os testes usam somente quatro coordenadas ficticias:

```bash
python3 -m unittest discover -s work/rep_s_field_pilot_v1 \
  -p 'test_*.py' -v
```

Eles verificam determinismo, cardinalidade, faixas, schema cego, independencia
estrutural dos sorteios de qualidade e idade, validade das coordenadas e
segregacao dos caminhos.
