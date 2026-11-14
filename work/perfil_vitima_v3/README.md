# PERFIL V3 — rankeador quantitativo prospectivo

Implementação separada do V1 e do compilador qualitativo V2. Somente direção observada estruturada e destino/lugar explicitamente georreferenciado podem alterar o ranking territorial.

## Arquivos

- `profile_ranker.py`: valida, congela e processa a entrada;
- `profile_integration.py`: verifica e integra V2, manifesto TERRITORIAL, buffers, setores e revisão espacial;
- `test_profile_ranker.py`: testes unitários;
- `test_profile_integration.py`: testes de proveniência, topologia e integração;
- `../../outputs/modulo_perfil_vitima_v3/perfil_quantitativo_v3.input.schema.json`: contrato da entrada;
- `../../outputs/modulo_perfil_vitima_v3/config_perfil_quantitativo_v3.json`: configuração candidata a congelamento;
- `../../outputs/modulo_perfil_vitima_v3/Especificacao_PERFIL_V3_Quantitativo.md`: justificativa e limites.
- `../../outputs/modulo_perfil_vitima_v3/Matriz_Hierarquia_Transferibilidade_Fontes_v3.md`: regras de admissão e transferibilidade das fontes;
- `../../outputs/modulo_perfil_vitima_v3/manifesto_candidato_perfil_v3.json`: hashes do pacote candidato.
- `../../outputs/modulo_perfil_vitima_v3/perfil_v3_revisao_espacial.schema.json`: contrato da revisão espacial lateral.
- `../../outputs/modulo_perfil_vitima_v3/Relatorio_Integracao_PERFIL_V3.md`: estado e bloqueadores de aplicação.

## Fluxo

1. montar um rascunho compatível com o esquema;
2. congelar em arquivo diferente;
3. processar somente o pacote congelado;
4. congelar as saídas;
5. somente depois liberar o *ground truth* para avaliação.

### Congelar

```bash
python3 profile_ranker.py \
  --input entrada_rascunho.json \
  --prepare-freeze \
  --frozen-at 2026-10-21T12:00:00-03:00 \
  --output entrada_congelada.json
```

### Processar

```bash
python3 profile_ranker.py \
  --input entrada_congelada.json \
  --output resultado_perfil_v3.json
```

## Fórmula

`lambda_eff = lambda × max(q_f)`

`S_j = (1 - lambda_eff) × T_j + lambda_eff × C_j`

O teto principal é `lambda=0,10`. `lambda=0,15` existe somente como estresse. Em abstenção, `S_j=T_j` exatamente em todas as sensibilidades.

Direções devem informar `origin_candidate_id` igual ao `candidate_id` da entrada. Destinos usam o círculo definido por coordenada e `location_uncertainty_m`: a compatibilidade é binária quando o ponto está no setor ou o círculo alcança sua borda. O cálculo usa projeção equiretangular local e trata o antimeridiano; não transforma incerteza em peso ou probabilidade.

`lambda_results` e `primary_rows` são saídas diagnósticas. Se o Top-1 divergir entre `lambda=0,05` e `lambda=0,10`, `operational_rows` volta exatamente ao TERRITORIAL e `operational_status` solicita revisão.

## O que não recebe peso

- idade, sexo ou personalidade;
- cognição sem pista espacial;
- mobilidade sem regra de alcance validada;
- urgência clínica;
- pesca, água ou isolamento sem lugar concreto;
- estatísticas externas transformadas diretamente em peso ou distância.

## Validação

```bash
python3 -m unittest discover -s work/perfil_vitima_v3 -p 'test_*.py' -v
python3 -m py_compile work/perfil_vitima_v3/profile_ranker.py work/perfil_vitima_v3/profile_integration.py
jq empty outputs/modulo_perfil_vitima_v3/*.json
```

O validador do motor aplica as mesmas restrições essenciais do esquema, rejeita campos extras, valida identificadores, vincula a direção ao candidato e rejeita setores angulares nulos ou polígonos de área nula. Também fixa os campos decisórios do ranking; uma configuração adulterada é recusada. O adaptador confere os bytes reais, a topologia simples dos polígonos, os identificadores e a coerência entre CSV, GeoJSON e buffer autoritativo. O JSON Schema permanece como contrato para futura interface; um validador JSON Schema genérico não é exigido em tempo de execução.

## Integração auditável

Uma pista espacial somente é incluída quando o compilado V2 está congelado, o pacote TERRITORIAL está íntegro e existe revisão espacial congelada vinculada pelos hashes exatos dessas duas fontes. O sidecar não pode modificar coordenadas, natureza, confiança, azimute ou tolerância. Ele apenas registra a decisão de inclusão/exclusão, identifica a origem da direção ou informa incerteza e procedência do destino.

Sem sidecar, direções e destinos são excluídos e o V3 preserva o TERRITORIAL. A origem de uma direção deve possuir coordenadas numericamente idênticas ao centro autoritativo do candidato. Nenhuma tolerância espacial é criada pelo adaptador. A entrada V3 registra `source_spatial_review_sha256`, vinculando criptograficamente a revisão que influenciou a decisão.

```bash
python3 profile_integration.py freeze-review \
  --input revisao_espacial_rascunho.json \
  --frozen-at 2026-10-21T12:00:00-03:00 \
  --output revisao_espacial_congelada.json

python3 profile_integration.py build \
  --profile perfil_v2_compilado.json \
  --territorial-manifest manifest_setorizacao.json \
  --ranking sector_ranking.csv \
  --polygons sector_polygons.geojson \
  --buffers buffer_results.json \
  --spatial-review revisao_espacial_congelada.json \
  --scenario-id CENARIO-001 --candidate-id CENARIO-001-C1 \
  --created-at 2026-10-21T12:05:00-03:00 \
  --frozen-at 2026-10-21T12:06:00-03:00 \
  --output entrada_v3_congelada.json --report relatorio_integracao.json
```

Pacote territorial não confirmatório é recusado por padrão. `--allow-nonconfirmatory` existe somente para ensaio diagnóstico e essa condição fica explícita no relatório.

## Estado

Motor e adaptador implementados como **candidatos a congelamento**. O núcleo está apto à integração, mas não há compilado V2 real no workspace para executar a cadeia ponta a ponta. Não aplicar aos novos casos antes de produzir o V2 congelado, preencher/congelar a revisão espacial sem acesso ao *ground truth* e concluir a auditoria do pacote integrado.

