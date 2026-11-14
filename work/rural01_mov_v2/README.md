# RURAL-01 MOV-V v2

Extensão cega e não confirmatória que representa resistência relativa ao
deslocamento dentro do raio-fonte de 1.500 m. O pacote v1 permanece intacto.

## Execução

Use o Python empacotado pelo ambiente, que contém Pillow para leitura do ESA
WorldCover:

```bash
/Users/elton.amador/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  work/rural01_mov_v2/motor_movimento_v2.py
```

Testes unitários:

```bash
python3 -m unittest -v work/rural01_mov_v2/test_motor_movimento_v2.py
```

## Interpretação

- `cost_m_equivalent` é custo relativo acumulado, não tempo, distância real ou
  probabilidade de presença.
- As hipóteses `H_REDE_DISPONIVEL` e `H_FORA_REDE` são paralelas; nenhuma foi
  selecionada, pois o regime de uso da rede está desconhecido.
- Os perfis `SUAVE`, `BASE` e `FORTE` são sensibilidades não calibradas.
- O relevo BASE é simétrico entre subida e descida. A arquitetura conserva o
  gradiente assinado, mas anisotropia topográfica não foi ativada sem calibração.
  O custo total pode continuar dirigido porque usa a resistência da célula de
  destino.
- A vizinhança D8 gera distância octil, uma aproximação discreta com pequeno
  viés angular; não equivale a isotropia euclidiana contínua.
- O WorldCover é agregado por maioria de nove amostras de 10 m para cada célula
  de 30 m. A classe de dossel não comprova transitabilidade do sub-bosque.
- Vias, hidrografia e relevo públicos indicam resistência potencial, nunca veto
  absoluto ou condição atual comprovada. A hidrografia desta versão é uma proxy
  raster de proximidade/entrada em célula; não comprova cruzamento, ponte ou vau.
- Célula sem DEM ou WorldCover obrigatório invalida a execução; ausência de dado
  não recebe fator-padrão favorável.

## Saídas

As saídas são gravadas em
`outputs/campo_rural01/processamento_movimento_cego_v2/`:

- `grade_resistencia.csv`: fatores, custo, alcance e predecessor por célula;
- `superficie_custo_H_REDE_DISPONIVEL.geojson`;
- `superficie_custo_H_FORA_REDE.geojson`;
- `areas_alcancaveis_mov_v2.geojson`;
- `setores_mov_v2.csv`: agregação e ranking físico por setor e cenário;
- `corredores_mov_v2.geojson`: 24 caminhos diagnósticos por hipótese BASE;
- `resultado_mov_v2.json`;
- `relatorio_qa_mov_v2.json`;
- `manifesto_mov_v2.json`.

Os corredores terminam no ponto representativo congelado de cada um dos 24
setores v1. Eles não são trajetórias previstas nem rotas de emprego.

As listas “Top-3” são classificações de acessibilidade física relativa em cada
hipótese. Todos os setores com posto compartilhado menor ou igual a 3 são
mantidos; a lista pode, portanto, conter mais de três linhas. Elas não representam
probabilidade de presença nem localização prevista.
