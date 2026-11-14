# Mapa RURAL-01 — resistência e corredores MOV-V v2

## Produto

- `Mapa_RURAL01_Resistencia_Corredores_MOV_V_v2.png`: figura multipainel em 4961 × 3508 px, 300 dpi;
- `Mapa_RURAL01_Resistencia_Corredores_MOV_V_v2.pdf`: versão A3 em paisagem para leitura e impressão, gerada separadamente;
- `gerar_mapa_mov_v2.py`: script reprodutível da figura;
- `manifesto_cartografico_mov_v2.json`: proveniência, hashes e controles cartográficos.

## Leitura dos painéis

1. **A — Resistência territorial:** resistência relativa por célula no perfil BASE. Os fatores são hipóteses de desenvolvimento, não medidas diretas de velocidade.
2. **B — Rede disponível:** custo acumulado quando vias e trilhas podem reduzir o esforço relativo. Top-3: R01-W, R01-E, R01-NE.
3. **C — Fora da rede:** custo acumulado sem desconto da rede. Top-3: R01-W, R01-N, R01-NE.
4. **D — Comparação:** classificação territorial v1 e classificações Top-3 MOV-V das duas hipóteses, sem seleção automática do regime.

Os painéis B e C usam a mesma escala cromática, de 0 a 4.500 metros equivalentes de esforço. O contorno interno marca o orçamento heurístico de 1.500 m equivalentes; não é uma isócrona em horas. Foram gerados 48 corredores, dos quais 6 aparecem na figura: três por hipótese BASE.

## Semântica espacial

- A vizinhança **D8** é uma aproximação octil entre células ortogonais e diagonais da grade; não reconstrói uma trilha observada em campo.
- A hidrografia OSM entra como **proxy raster de proximidade/entrada** na célula. O processamento não executa interseção geométrica que comprove travessia, vau, ponte, margem intransponível ou curso efetivamente cruzado.
- Os corredores são trajetos diagnósticos de menor custo na grade, e não rotas previstas para a pessoa desaparecida.

## Salvaguardas

- A posição verdadeira não foi consultada, utilizada nem representada.
- `cost_m_equivalent` não é tempo, probabilidade de presença nem distância euclidiana.
- As 14 horas desde o desaparecimento aparecem somente como contexto; não foram convertidas automaticamente em alcance.
- A composição orbital é o mosaico anual Sentinel-2/ESA WorldCover de 2021; não constitui observação do terreno em 2026.
- WorldCover descreve cobertura vista do alto e não comprova transitabilidade do sub-bosque.
- SRTM em resolução nominal de aproximadamente 30 m pode suavizar ravinas, barrancos e feições estreitas.
- OSM pode estar incompleto ou desatualizado.
- Nenhum obstáculo de campo foi espacializado nesta execução; a saída permanece em estado `REVISAR`.
- A v1 e os resultados numéricos MOV-V v2 não foram alterados por este script.

## Fontes cartográficas

- Composição anual Sentinel-2/ESA WorldCover 2021 em cores naturais.
- ESA WorldCover 2021 v200, resolução nominal de 10 m.
- SRTM N00W052, resolução nominal de aproximadamente 30 m.
- OpenStreetMap, recorte local congelado no projeto.

Nota de uso acadêmico: composição cartográfica a partir de fontes públicas e resultados do processamento cego; não é levantamento de campo nem mapa operacional validado.
