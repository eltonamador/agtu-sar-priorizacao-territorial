# Mapa RURAL-01 — previsão/priorização cega v1

Arquivos:

- `Mapa_RURAL01_Previsao_Cega_BASE_PERFIL_v1.png`: figura em 4.000 × 2.550 px, 300 dpi;
- `Mapa_RURAL01_Previsao_Cega_BASE_PERFIL_v1.pdf`: exportação A3 horizontal;
- script reprodutível: `gerar_mapa_rural01_cego.py`.

## Leitura

- E0: ponto inicial recebido pelo sistema;
- AP1, AP2 e AP3: áreas priorizadas, na ordem do ranking;
- R01, R02 e R03: anéis interno, intermediário e externo;
- N, NE, E, SE, S, SW, W e NW: direções dos setores;
- o painel B repete o Top-3 porque o módulo de perfil se absteve de alterar o ranking sem pista espacial quantitativamente elegível;
- a posição verdadeira não foi lida nem representada.

## Correção temporal

O intervalo entre desaparecimento e fotografias foi corrigido para 14 h. Essa correção não altera o Top-3 porque o raio de 1.500 m foi recebido como raio final ajustado pela fonte e o tempo não participou numericamente do ranking espacial congelado.

## Contexto cartográfico

A figura usa camadas públicas do OpenStreetMap (© OpenStreetMap contributors, ODbL), SRTMGL1/Mapzen e ESA WorldCover 2021 v200. Não representa levantamento de campo. A pista Norte, o perfil e as fotografias não alteraram quantitativamente o ranking congelado. AP1–AP3 expressam prioridade analítica para revisão humana, não probabilidade de presença.
