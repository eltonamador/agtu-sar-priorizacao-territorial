# MATA-01 MOV-V v1

Implementação cega da superfície de resistência física e dos corredores de planejamento do cenário MATA-01.

## Execução

Use o Python empacotado no Codex, que contém Pillow e os leitores de TIFF:

```bash
PY=/Users/elton.amador/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
$PY work/mata01_mov_v1/run_tests_with_receipt.py
$PY work/mata01_mov_v1/motor_movimento_mata01_v1.py
```

As saídas são gravadas em `outputs/campo_mata01/processamento_movimento_cego_v1/`.

## Semântica

- custo = resistência relativa acumulada;
- corredor = caminho diagnóstico de menor custo até alvo setorial predefinido;
- nenhum resultado é probabilidade, trajetória observada, isócrona ou localização da pessoa;
- T26 e T49 permanecem contexto e não são convertidos em distância.
