# REP-S-SPATIAL-EVAL-v1.0

Pacote congelado antes da coleta para completar a ligação entre o
`FIELD-CAND-v1.0`, o buffer adaptativo `EXT-ESP-BUF-v1.0`, a setorização
`EXT-ESP-SET-v1.1` e a avaliação espacial posterior à abertura controlada do
ground truth.

Nenhum resultado anterior foi alterado. Este diretório acrescenta uma camada
de interface, custódia e avaliação. Ele não contém coordenadas reais, imagens
de campo ou resultados da futura REP-S.

## O que o pacote resolve

Antes desta versão, havia:

1. um gerador congelado de três candidatos cegos por site;
2. um motor de buffer adaptativo;
3. um motor de 24 setores e ranking intrabuffer;
4. um protocolo geral de segregação do ground truth.

Faltava um contrato executável que demonstrasse, sem decisões posteriores aos
dados, como essas partes seriam conectadas e como a saída setorial seria
avaliada depois de T3. O presente pacote fecha essa lacuna.

## Limite científico

A modalidade é `REP-S-FIELD-PILOT`: quatro posições reais de campo alimentam
somente o gerador pre-especificado de candidatos semissintéticos. A partir da
saída cega, buffer, GEO e ranking não recebem a posição verdadeira. Portanto,
o desenho avalia prospectivamente o componente espacial e o fluxo de
processamento, mas não valida uma detecção aerotransportada operacional nem a
eficácia de uma missão real.

O ranking continua restrito aos 24 setores de cada buffer. Setores de C1, C2 e
C3 não são colocados em uma lista global, porque o `EXT-ESP-SET-v1.1` não gera
escores comparáveis entre buffers.

## Arquivos

- `config_rep_s_spatial_eval_v1.json`: especificação normativa congelada,
  dependências com SHA-256, estados, regras de borda, métricas e limites de
  interpretação;
- `common.py`: validação de integridade, geometria local, hashes e estatística;
- `prepare_and_run_blind.py`: interface T1 e execução repetida T1.5–T2;
- `evaluate_post_t3.py`: abertura vinculada ao hash de T0 e avaliação T3–T4;
- `test_rep_s_spatial_eval.py`: testes com coordenadas exclusivamente
  fictícias;
- `resultado_testes_rep_s_spatial_v1.json`: evidência da suíte local e das
  suítes congeladas a montante;
- `manifesto_congelamento_pre_campo_v1.json`: inventário da versão pronta para
  receber os dados de campo.

## Cadeia temporal obrigatória

| Marco | Estado | O que pode ser visto pelo processamento |
|---|---|---|
| T-1 | Plano congelado | protocolo, estratos, regras e versões |
| T0 | Ground truth lacrado | somente seu SHA-256; coordenadas reservadas |
| T1 | Entrada cega congelada | 12 candidatos FIELD-CAND sem referência real |
| T1.5 | Motores verificados | entrada cega, configurações, código e testes |
| T2 | Saídas cegas congeladas | buffers, setores, rankings, logs e manifestos |
| T3 | Ground truth aberto | referência liberada apenas ao avaliador |
| T4 | Avaliação concluída | métricas pre-especificadas, sem retuning |

O avaliador recusa um arquivo de ground truth cujo SHA-256 seja diferente do
compromisso gravado pelo gerador em T0. As duas execuções cegas devem produzir
arquivos científicos idênticos byte a byte antes que T3 seja aceito.

## Regra de fronteira set-valued

Para cada buffer, seja `S*` o conjunto de setores fechados que contêm a
posição de referência. Uma tolerância de 0,25 m é usada somente para absorver
erro numérico da geometria, não como incerteza GNSS.

- no interior, `S*` normalmente tem um setor;
- em uma linha comum, pode ter dois;
- no encontro entre limite angular e anular, pode ter quatro;
- no caso degenerado do centro, pode ter os oito setores internos;
- fora do buffer, `S*` é vazio.

Nenhum `sector_id` escolhe artificialmente um lado da fronteira. São
registradas duas leituras:

- primária: `rank_min = min(rank(s), s em S*)`, Top-k por existência e
  `MRR = 1/rank_min`;
- conservadora: `rank_max = max(rank(s), s em S*)`, Top-k exigindo todos os
  membros de `S*` e `MRR = 1/rank_max`.

Quando `S*` é vazio, o rank fica ausente e o recíproco vale zero na métrica
incondicional.

## Área acumulada

A área primária até o acerto soma integralmente todos os setores com rank BASE
menor ou igual a `rank_min`. A área conservadora usa `rank_max`. Assim, todo o
grupo empatado no patamar de corte é incluído, sem inventar uma ordem dentro do
empate. Também é informada a fração da área total dos 24 setores.

Se o buffer não cobre a referência, a área até o acerto fica ausente. O
resultado registra separadamente que a área completa daquele buffer foi
insuficiente.

## Coberturas reportadas

O relatório separa:

- cobertura do ground truth por cada buffer adaptativo;
- cobertura pelo círculo fixo de 2.000 m;
- cobertura de ao menos um candidato por cenário;
- completude dos quatro módulos GEO em cada setor;
- buffers com 24/24 setores completos;
- resultados globais e por ambiente planejado.

As proporções incluem intervalo de Wilson de 95%. Top-k e MRR são apresentados
com denominador incondicional (todos os 12 buffers) e condicional (buffers que
cobrem a referência). Uma leitura adicional considera somente os buffers
cobertos cujo ranking está disponível.

## Uso depois da coleta

Use o mesmo ambiente Python configurado para o processamento geoespacial. Ele
deve incluir suporte de leitura TIFF pelo Pillow, exigido pelo ESA WorldCover.
O orquestrador reutiliza automaticamente o mesmo interpretador com que foi
iniciado.

### 1. Gerar os candidatos com o componente já congelado

```text
python3 work/rep_s_field_pilot_v1/generate_field_candidates.py \
  --input-gt /reservado/ground_truth_field.csv \
  --blind-output /cego/field_candidates_blind.csv \
  --secure-output /reservado/field_candidates_secure.csv \
  --manifest-output /auditoria/field_candidates_manifest.json
```

### 2. Congelar T1

```text
python3 work/rep_s_spatial_eval_v1/prepare_and_run_blind.py prepare-t1 \
  --blind-csv /cego/field_candidates_blind.csv \
  --field-cand-manifest /auditoria/field_candidates_manifest.json \
  --output-csv /cego/buffer_input_t1.csv \
  --output-manifest /auditoria/manifest_t1.json
```

O arquivo produzido para o buffer exclui `site_id` e colunas auxiliares. A
relação pública entre cenário, candidato e site permanece no manifesto T1 para
que a união posterior possa ocorrer sem revelar coordenadas.

### 3. Executar cegamente duas vezes e congelar T2

```text
python3 work/rep_s_spatial_eval_v1/prepare_and_run_blind.py run-blind \
  --buffer-input /cego/buffer_input_t1.csv \
  --t1-manifest /auditoria/manifest_t1.json \
  --roads /fontes/osm_highways_raw.json \
  --hydro /fontes/osm_hydrography_raw.json \
  --dem-dir /fontes/dem \
  --worldcover-dir /fontes/worldcover \
  --output-root /cego/rep_s_t2
```

O comando confere os hashes fixados, executa as três suítes a montante, roda
buffer e setores duas vezes, compara os arquivos científicos e grava
`manifest_t2_rep_s_spatial.json`. Os nomes internos `*_dev` emitidos pelo motor
setorial v1.1 são preservados para não reescrever resultados; a modalidade
prospectiva é registrada no manifesto externo.

### 4. Abrir T3 e calcular T4

Somente depois da aprovação e do congelamento de T2:

```text
python3 work/rep_s_spatial_eval_v1/evaluate_post_t3.py \
  --t2-manifest /cego/rep_s_t2/manifest_t2_rep_s_spatial.json \
  --ground-truth /reservado/ground_truth_field.csv \
  --output-dir /avaliacao/rep_s_t4
```

As saídas são:

- `candidate_sector_evaluation.csv`;
- `scenario_spatial_evaluation.csv`;
- `metrics_summary.json`;
- `manifest_t4_rep_s_spatial.json`.

As coordenadas verdadeiras não são repetidas nos CSVs analíticos. O manifesto
registra o caminho e o hash do arquivo reservado usado em T3.

## Testes

```text
python3 -m unittest -v test_rep_s_spatial_eval.py
```

Os testes verificam integridade do FIELD-CAND, ausência de vazamento,
cardinalidade, fronteira set-valued, leitura primária e conservadora, área
acumulada com empates, cobertura, Wilson, compromisso do ground truth e um
ensaio T3–T4 completo com quatro sites, 12 buffers e 288 setores fictícios.

## Política de mudança

Qualquer alteração de tolerância, Top-k, regra de borda, definição de área,
denominador, fonte GEO, dependência ou algoritmo exige novo identificador de
versão e nova execução integral. Os dados de campo não podem ser usados para
escolher ou ajustar essas regras retrospectivamente.
