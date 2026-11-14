# MATA-01 — processamento territorial cego v1

Este invólucro reutiliza, sem alterar, o motor `EXT-ESP-SET-v1.1`. O raio de 5 km e recebido diretamente como dominio operacional informado pelo pesquisador; o buffer adaptativo nao e executado e nenhuma qualidade de deteccao e presumida.

Execucao:

```bash
python3 work/mata01_processamento_cego_v1/run_mata01_blind.py
```

Testes:

```bash
python3 -m unittest work/mata01_processamento_cego_v1/test_mata01_blind.py
```

Saida padrao: `outputs/campo_mata01/processamento_cego_v1`.

Como a base OSM possui zero feicoes hidrográficas no dominio de 5 km, o BASE original fica abstido e nao gera Top-3. O pacote tambem gera `BASE-DISPONIVEIS`, analise diagnostica separada que renormaliza somente GEO-02, GEO-04 e GEO-05. Ela nao equivale ao BASE completo.

Relevo e cobertura usam 3.600 amostras deterministicas por setor, com suporte areal aproximado de 900 m2 por amostra (escala linear nominal de cerca de 30 m). Fotografias, perfil, pistas comportamentais, urgencia, detectabilidade e qualquer posicao declarada do alvo simulado permanecem fora do calculo desta etapa.
