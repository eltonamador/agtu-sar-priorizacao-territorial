# URBE-01 — processamento cego v1

Pacote isolado para reproduzir a setorização e a priorização territorial do cenário URBE-01. O motor científico existente não é alterado: suas funções são importadas em tempo de execução.

## Execução

```bash
/Users/elton.amador/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  work/urbe01_processamento_cego_v1/run_urbe01_blind.py
```

O executor produz a primeira rodada na pasta final, repete integralmente o processamento em uma pasta temporária e compara os SHA-256 de 15 artefatos científicos. A publicação só é concluída se a repetição for idêntica e todos os gates de QA forem aprovados.

## Testes unitários

```bash
/Users/elton.amador/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest -v work/urbe01_processamento_cego_v1/test_urbe01_blind.py
```

## Saídas

As saídas são gravadas em `outputs/campo_urbe01/processamento_cego_v1` e incluem:

- entrada e geometria do raio informado pela fonte;
- configuração efetiva e protocolo congelado;
- atributos GEO dos 24 setores;
- ranking BASE original;
- ranking PERFIL URBE-01;
- Top 3 de ambos os rankings;
- polígonos setoriais em GeoJSON;
- resultado estruturado, avisos, relatórios de determinismo e QA;
- manifesto final com SHA-256 de entradas, motor, configurações, bases GEO e saídas.

Todos os resultados permanecem como `REVISAR`, são não confirmatórios e registram `ground_truth_used=false`.
