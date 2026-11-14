# URBE-01 — avaliação pós-abertura v1

Esta etapa compara a referência declarada após o processamento cego com os
setores e rankings já congelados. O programa não recalcula setores, pesos,
escores nem posições.

## Referência avaliada

- latitude: `0.0024809355844815323`
- longitude: `-51.07092698392779`
- condição documental: declarada pelo usuário; precisão horizontal e
  verificação GNSS/EXIF independentes não disponíveis.

## Execução

Requisitos: Python 3.11 ou superior, Pillow e ReportLab.

```bash
python3 work/urbe01_avaliacao_pos_abertura_v1/evaluate_urbe01_reference.py
python3 -m unittest work/urbe01_avaliacao_pos_abertura_v1/test_evaluate_urbe01_reference.py
```

As saídas são gravadas em
`outputs/campo_urbe01/avaliacao_pos_abertura_v1`. Na primeira execução, o
programa registra o horário local de abertura em `America/Belem`; execuções
posteriores preservam esse registro. Uma referência diferente exige nova pasta
versionada.

## Controles

- fotografia criptográfica do pacote cego antes e depois da avaliação;
- dois métodos de identificação setorial: ponto-no-polígono e
  distância/azimute;
- regra de borda conservadora documentada;
- duas execuções e comparação SHA-256 de nove saídas científicas;
- manifesto final com hashes de entradas congeladas, referência e saídas.

