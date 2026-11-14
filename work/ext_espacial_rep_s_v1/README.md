# Preparação REP-S — validação independente do buffer adaptativo

Este diretório contém a preparação técnica e metodológica da primeira validação
independente do protocolo `EXT-ESP-BUF-v1.0`. Nenhum dado de campo foi criado,
preenchido ou inferido.

## Objetivo

Separar, de modo auditável, três momentos:

1. registro e congelamento da entrada cega;
2. execução e congelamento das saídas do motor;
3. abertura posterior do ground truth e avaliação.

O arquivo Excel é uma área de preparação. Ele **não constitui, sozinho, uma
barreira de acesso**, porque contém abas para os dois conjuntos. Antes de uma
execução válida, `export_rep_s_firewall.py` deve gerar arquivos separados. O
arquivo de ground truth deve permanecer reservado até que o manifesto registre
o congelamento da saída.

## Arquivos planejados

- `Kit_REP_S_Validacao_Independente_v1.xlsx`: preenchimento orientado, plano de
  sites, entrada cega, ground truth reservado, gates e registro de congelamento;
- `Protocolo_REP_S_Validacao_Independente_Buffer_v1.docx`: protocolo legível e
  checklist de execução;
- `protocolo_rep_s_v1.json`: especificação legível por máquina;
- `export_rep_s_firewall.py`: validação e exportação dos conjuntos separados;
- `test_export_rep_s_firewall.py`: testes de integridade e de não vazamento.

## Regra de independência

Um site já observado durante ajuste, desenvolvimento ou inspeção dos resultados
não pode ser reclassificado como REP-S. Ele pode permanecer documentado como
DEV-S ou legado. A partição é feita por `site_id`, antes de consultar qualquer
resultado, e todos os candidatos do mesmo site ficam na mesma fase.

## Dados ausentes

Timestamp, precisão horizontal, equipamento, fotografia, ambiente e demais
metadados opcionais permanecem vazios quando não existirem. A exportação rejeita
somente a ausência de campos definidos como obrigatórios e nunca completa dados
por suposição.

## Execução futura

Após preencher o kit:

```text
python export_rep_s_firewall.py prepare Kit_REP_S_Validacao_Independente_v1.xlsx pacote_rep_s
python export_rep_s_firewall.py freeze-output saida_modelo pacote_rep_s/manifesto_preparacao_rep_s.json --config config_buffer_v1.json --engine motor_buffer_adaptativo.py --test-evidence resultado_testes_rep_s_v1.json --repeat-output saida_modelo_repetida --engine-manifest saida_modelo/manifest_execucao.json --repeat-engine-manifest saida_modelo_repetida/manifest_execucao.json
```

O exportador deve produzir arquivos separados, relatório de validação e
manifesto com hashes. O motor recebe apenas a entrada cega. A abertura do ground
truth e o cálculo das métricas ocorrem em etapa posterior. A segunda ordem só
autoriza essa abertura quando a configuração, o motor e os testes têm hashes
registrados, a suíte está aprovada e as duas execuções produzem **resultados
científicos idênticos**. Manifestos e logs podem conter timestamps e outros
metadados distintos entre as execuções; por isso são congelados e resumidos por
hash como evidência, mas não entram na comparação de determinismo.

Cada `--engine-manifest` deve ser o manifesto JSON realmente emitido pelo motor.
O firewall confere três compromissos antes de autorizar a abertura do ground
truth: `role=input` deve corresponder ao `rep_s_input_blind.csv` preparado;
`role=config` e `role=engine` devem corresponder exatamente aos arquivos
fornecidos nas opções `--config` e `--engine`. O manifesto e qualquer saída que
contenha `ground_truth_used` só são aceitos quando o valor é o booleano `false`
(ou `false` textual na coluna CSV).

Em `data_origin`, usar somente a origem compatível com a modalidade: no
`REP-S-FIELD-PILOT`, `GERADOR_CONGELADO`, `GERADOR_PRE_ESPECIFICADO` ou
`SIMULACAO_CONGELADA`; no `REP-S-OP`, `SISTEMA_AEROTRANSPORTADO`,
`SISTEMA_AEROTRANSPORTADO_OPERACIONAL` ou
`FONTE_OPERACIONAL_AEROTRANSPORTADA`.
