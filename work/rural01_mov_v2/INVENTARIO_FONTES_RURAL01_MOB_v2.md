# Inventário de fontes locais para o RURAL-01 — movimento e obstáculos v2

## 1. Finalidade e escopo

Este inventário registra as fontes geoespaciais e visuais que já estão
disponíveis localmente e podem apoiar a versão 2 do processamento cego do
cenário RURAL-01 sem nova transmissão de coordenadas nem novo download.

O levantamento distingue:

1. dados aptos a compor uma superfície **relativa** de resistência ao
   deslocamento;
2. dados que servem somente como contexto visual ou confirmação qualitativa;
3. informações inexistentes ou insuficientes, que devem permanecer marcadas
   como desconhecidas até obtenção de evidência de campo ou de nova fonte.

A posição verdadeira da vítima não foi consultada nem utilizada neste
inventário.

## 2. Síntese executiva

| Fonte local | Cobertura do RURAL-01 | Resolução ou escala | Uso admissível na v2 | Restrição principal |
|---|---|---:|---|---|
| SRTMGL1/Mapzen-Skadi | Integral | 1 segundo de arco, aproximadamente 30 m | Elevação, declividade, orientação, relevo local e custo relativo | Não representa barrancos, grotas ou microrrelevo abaixo da grade; não autoriza tempo absoluto |
| ESA WorldCover 2021 v200 | Integral | Nominal de 10 m | Resistência categórica, proporções de classes e cenários de sensibilidade | Não representa sub-bosque, cipós ou transitabilidade atual; referência de 2021 |
| OpenStreetMap — vias | Integral no recorte regional | Vetorial, precisão heterogênea | Corredores de menor custo e contexto de acesso | Completude desconhecida; não confirma condição da via ou existência de trilhas não mapeadas |
| OpenStreetMap — hidrografia | Integral no recorte regional | Vetorial, precisão heterogênea | Resistência hídrica suave e sinalização de barreira | Não confirma largura, nível, ponte, vau ou transitabilidade |
| Composição Sentinel-2/WorldCover TCC 2021 | Integral no enquadramento cartográfico | Informação nominal de 10 m, entregue como PNG 2.048 × 2.048 | Contexto visual e figura cartográfica | Não é cena de 2026 nem produto multiespectral analítico |
| Fotografias de solo e drone | Pontual, concentrada junto ao ponto inicial | Variável; RGB visível | Contexto qualitativo e eventual confirmação local explicitamente documentada | Não formam ortomosaico e não possuem pegada espacial confiável para rasterização |

Conclusão operacional: os dados locais são suficientes para construir uma
superfície de custo **relativo**, executar caminhos/corredores plausíveis e
comparar cenários. Eles não são suficientes para declarar tempo absoluto de
deslocamento, transitabilidade real da mata ou barreiras intransponíveis.

## 3. Modelo de elevação — SRTMGL1/Mapzen-Skadi

### 3.1 Arquivo e integridade

- Caminho: `outputs/sprint2_s2_06_geo05_v33/N00W052.hgt.gz`
- Produto registrado no projeto: Mapzen/Skadi-SRTMGL1.
- Tile: `N00W052`.
- Cobertura nominal: latitude 0° a 1° N; longitude 52° a 51° O.
- Grade descompactada: 3.601 × 3.601 amostras, inteiros de 16 bits em big-endian.
- Resolução: 1 segundo de arco; no centro do RURAL-01, aproximadamente
  30,7 m no sentido norte-sul e 30,9 m no sentido leste-oeste.
- Tamanho compactado: 10.237.499 bytes.
- Tamanho descompactado conferido: 25.934.402 bytes, exatamente o esperado
  para 3.601 × 3.601 × 2 bytes.
- SHA-256:
  `64fa9dce08cdba5a883b2811c1887c1e055fe878f54d53d0c3431c4bf48ecbeb`.
- Data interna do arquivo gzip: 27/04/2016 às 03:25:57.
- Registro da cópia local: 17/08/2026, aproximadamente 17:03 UTC.

### 3.2 Cobertura e qualidade no cenário

O buffer de 1.500 m encontra-se integralmente dentro do tile. A janela usada
no enquadramento cartográfico contém 115 × 115 células e não apresenta valor
`-32768`, usado como ausência de elevação no formato HGT.

Estatísticas no enquadramento:

- elevação mínima: -1 m;
- elevação média: 15,05 m;
- elevação máxima: 39 m.

Uma verificação independente da declividade Horn dentro do círculo de 1.500 m
produziu:

- mediana: 3,43°;
- percentil 90: 7,39°;
- percentil 95: 8,63°;
- percentil 99: 10,79°;
- máximo observado na grade: 14,41°;
- células com declividade igual ou superior a 10°: aproximadamente 2,07%;
- nenhuma célula com declividade igual ou superior a 15°.

Esses valores indicam que o SRTM não sinaliza encosta muito íngreme no buffer
do RURAL-01. Isso não demonstra ausência de barrancos, taludes, valas ou
microformas de relevo: tais feições podem ser menores do que a grade de cerca
de 30 m. Além disso, em floresta, a elevação radar pode conter influência do
dossel e não deve ser tratada automaticamente como modelo de terreno nu.

### 3.3 Uso admissível

O arquivo pode ser empregado, sem download, para derivar:

- elevação;
- declividade;
- orientação de vertente;
- amplitude e rugosidade em janelas locais;
- curvatura aproximada;
- custo relativo de subida, descida e travessia do terreno;
- caminhos e corredores de menor resistência.

Não existe no motor atual função de Tobler, calibração de velocidade nem
conversão validada de custo para minutos. O GEO-04 v1 utiliza a expressão de
favorabilidade setorial:

`0,70 × exp(-declividade_em_graus/8) + 0,30 × exp(-amplitude_em_metros/30)`.

Essa fórmula não é anisotrópica e não representa velocidade de caminhada. Na
v2, qualquer função de velocidade ou multiplicador de subida/descida deve ser
tratado como hipótese de sensibilidade até existir calibração independente.

### 3.4 Alerta de proveniência

O projeto conserva o nome da fonte e o hash do tile, mas não conserva, junto
ao arquivo HGT, URL de aquisição, licença e metadados completos do download
original. Essa lacuna deve ser sanada antes de publicação ou distribuição do
dado derivado. O hash permite preservar exatamente o insumo usado.

## 4. Cobertura e uso do solo — ESA WorldCover 2021 v200

### 4.1 Arquivo e integridade

- Caminho:
  `outputs/sprint2_s2_06_geo05_v33/worldcover_tiles/ESA_WorldCover_10m_2021_v200_N00W054_Map.tif`
- Tile: `N00W054`.
- Cobertura: latitude 0° a 3° N; longitude 54° a 51° O.
- CRS: EPSG:4326.
- Dimensões: 36.000 × 36.000 pixels.
- Passo da grade: 1/12.000 de grau, aproximadamente 9,2 m no local;
  resolução nominal publicada: 10 m.
- Período de referência: 01/01/2021 a 31/12/2021.
- Versão do algoritmo: 2.0.0.
- Data de criação embutida: 21/10/2022.
- Registro da cópia local: 17/08/2026, aproximadamente 17:01 UTC.
- Tamanho: 8.977.040 bytes.
- SHA-256:
  `fc4a381c1734a42e5b52ba797b3dea2da2b06ed0e095f1fa30fbc3ebfe893f16`.
- Licença embutida: Creative Commons Attribution 4.0 International.
- Atribuição embutida: `ESA WorldCover project 2021 / Contains modified
  Copernicus Sentinel data (2021) processed by ESA WorldCover consortium`.

### 4.2 Cobertura e classes no cenário

O recorte do enquadramento contém 379 × 379 pixels. Não foram encontrados
pixels de código zero no recorte. A composição dentro do buffer, já calculada
no pacote cartográfico, é:

- cobertura arbórea: 74,3997%;
- vegetação herbácea: 17,8164%;
- área úmida herbácea: 5,3546%;
- água permanente: 2,3505%;
- solo exposto ou vegetação esparsa: 0,0788%.

O motor v1 atribui os seguintes escores heurísticos de favorabilidade às
classes WorldCover:

| Código | Classe | Escore v1 |
|---:|---|---:|
| 10 | Cobertura arbórea | 0,35 |
| 20 | Arbustiva | 0,50 |
| 30 | Herbácea | 0,80 |
| 40 | Agricultura | 0,75 |
| 50 | Construída | 0,85 |
| 60 | Solo exposto/vegetação esparsa | 0,90 |
| 70 | Neve e gelo | 0,30 |
| 80 | Água permanente | 0,05 |
| 90 | Área úmida herbácea | 0,20 |
| 95 | Manguezal | 0,15 |
| 100 | Musgo e líquen | 0,45 |

Esses valores foram congelados para o desenvolvimento anterior, mas não são
velocidades nem coeficientes de resistência validados em ambiente amazônico.
Na v2, devem ser usados como ponto de partida para cenários de sensibilidade,
com identificação explícita de sua natureza heurística.

### 4.3 Limitações

O WorldCover distingue cobertura vista por sensoriamento remoto, não a
estrutura interna da vegetação. A classe “cobertura arbórea” não permite
concluir se o sub-bosque está limpo, fechado, alagado ou tomado por cipós. O
produto também antecede o campo de 2026 em cinco anos; queimadas, clareiras,
novas vias e regeneração podem não estar representadas.

## 5. OpenStreetMap — vias e trilhas

### 5.1 Arquivo e integridade

- Caminho: `outputs/sprint2_s2_06_geo05_v33/osm_highways_raw.json`.
- Consulta preservada:
  `way["highway"](-0.25,-51.95,0.45,-50.70)`.
- Envelope: latitude -0,25° a 0,45°; longitude -51,95° a -50,70°.
- Elementos no arquivo regional: 8.622 ways.
- Snapshot OSM informado pelo Overpass: `2026-08-17T17:01:35Z`.
- Tamanho: 6.198.892 bytes.
- SHA-256:
  `a57bff45b51175b7287a044ac8c57cdb457c3bbf7629a4d683ff94be989c4a20`.
- Licença/atribuição preservada: Open Database License; © OpenStreetMap
  contributors.

### 5.2 Feições próximas ao buffer

Foram identificadas três vias com vértices até aproximadamente 1.550 m do
ponto inicial:

- way 780553885: `highway=unclassified`, `surface=unpaved`, distância mínima
  aproximada de 60 m;
- way 1136309633: `highway=unclassified`, `surface=unpaved`, distância mínima
  aproximada de 979 m;
- way 1136309632: `highway=service`, distância mínima aproximada de 1.079 m.

Essas geometrias podem funcionar como corredores de menor custo. A ausência
de uma trilha no OSM não demonstra ausência física, e a presença cartográfica
não demonstra que a via estava transitável em 2026. O recorte atual também
não consulta cercas, porteiras, linhas de transmissão ou barreiras lineares.

## 6. OpenStreetMap — hidrografia

### 6.1 Arquivo e integridade

- Caminho: `outputs/sprint2_s2_06_geo05_v33/osm_hydrography_raw.json`.
- Consulta: rios, igarapés, canais, valas, drenagens, áreas de água, áreas
  úmidas, reservatórios e bacias dentro do mesmo envelope regional.
- Elementos no arquivo regional: 241.
- Snapshot OSM: `2026-08-17T17:01:35Z`.
- Tamanho: 5.748.363 bytes.
- SHA-256:
  `0e3b3732140ec3d0197224687e00173bd771e9ae2d2175c974d4b01d7fcc6346`.
- Licença/atribuição: Open Database License; © OpenStreetMap contributors.

### 6.2 Feição no cenário

No buffer foi identificada apenas a feição way 852706441, `Rio Matapi`,
`waterway=river`, com `source=Landsat`. A distância mínima aproximada entre
um vértice da geometria e o ponto inicial é 747 m.

O rio pode elevar o custo relativo de travessia e justificar alerta de
barreira. Não deve receber veto absoluto com base apenas no OSM, porque a
fonte não comprova largura local, nível d'água, pontes, vaus, embarcações ou
condição na data da ocorrência. Tributários e áreas encharcadas menores podem
estar ausentes da cartografia.

## 7. Composição visual Sentinel-2/WorldCover TCC 2021

### 7.1 Arquivo e integridade

- Imagem:
  `outputs/campo_rural01/mapa_real_vegetacao_v2/fontes/ESA_WorldCover_S2_TCC_2021_RURAL01.png`
- Metadados:
  `outputs/campo_rural01/mapa_real_vegetacao_v2/fontes/ESA_WorldCover_S2_TCC_2021_RURAL01.metadata.json`
- Serviço: Terrascope/VITO, OGC WMS.
- Camada: `esa-worldcover-s2rgbnir-10m-2021-v2_tcc`.
- Composição: TCC, cores naturais, derivada do período de 2021.
- Bounds: longitude -51,1712941916385 a -51,13981780836149;
  latitude 0,17287289363482058 a 0,20434910636517942.
- Dimensões do PNG: 2.048 × 2.048 pixels, RGB.
- Data de recuperação: `2026-10-22T17:02:47Z`.
- SHA-256 da imagem:
  `cb778a1dfbb189dfaa7a03027af9fd9042dd1388fcb3ccffafe9fea8ac372916`.
- SHA-256 dos metadados:
  `0e0bec26ce6db7c2d592ae048c13a7f208123a706a4fc6028c2fb3a8b3dd0515`.
- Licença: CC BY 4.0.

Embora o arquivo possua pixels menores do que 10 m após a requisição WMS, a
resolução informativa continua sendo a resolução nominal da fonte. O PNG é
uma imagem RGB pronta para visualização, não um conjunto multibanda. Ele não
deve ser usado para NDVI, estimativa de altura, densidade de sub-bosque,
classificação temporal de 2026 ou mensuração de velocidade de deslocamento.

## 8. Fotografias locais

### 8.1 Custódia e integridade

- Diretório: `outputs/campo_rural01/reservado_originais/`.
- Conteúdo autorizado: seis HEIC de solo e nove JPEG de drone.
- Manifesto de metadados:
  `outputs/campo_rural01/entrada_cega_v1/manifesto_metadados_visuais.json`.
- SHA-256 do manifesto de metadados:
  `41c7e443f6e89e402506f39736fcf39c328799bfa581cc55250182559d3924c7`.
- Manifesto de custódia:
  `outputs/campo_rural01/entrada_cega_v1/manifesto_sha256_conjunto_a.json`.
- SHA-256 do manifesto de custódia:
  `07bb784d56eac3ed30be65c82aa4e8adbdd8e549d553bd0782ba0f137bc2aaa8`.
- Todos os 15 hashes individuais conferem com os valores congelados.

As fotografias de solo possuem GPS e direção da imagem. As fotografias DJI
foram registradas praticamente na mesma posição, cerca de 17 m do ponto
inicial, com altitude relativa indicada entre aproximadamente 119 e 121 m.
Não há erro horizontal informado para as imagens do drone, e a orientação
óptica disponível não foi considerada suficiente para construir pegadas
automatizadas confiáveis.

### 8.2 Divergência temporal

Os metadados embutidos apontam para 21/10/2026, enquanto o operador declarou
sessões em 22/10/2026 às 06:10 e 06:22. O adendo registra que o desaparecimento
ocorreu 14 horas antes das fotografias, mas não resolve qual relógio ou
associação de arquivo estava incorreto.

- Adendo:
  `outputs/campo_rural01/adendo_temporal_pos_t2_v1/adendo_temporal_pos_t2_rural01_v1.json`.
- SHA-256:
  `c81daba64808028af91e6a4f805e5c8da17976a8e180d357b1e0301daf16f22d`.

As fotografias podem sustentar descrição qualitativa do entorno observado e
confirmação pontual documentada. Elas não devem ser convertidas em superfície
espacial de vegetação, obstáculo ou visibilidade sem ortomosaico, pontos de
controle e pegadas confiáveis.

## 9. Geometrias e saídas congeladas reutilizáveis

Os seguintes artefatos podem delimitar e auditar a nova execução:

| Artefato | Caminho | SHA-256 |
|---|---|---|
| Buffer de 1.500 m | `outputs/campo_rural01/processamento_cego_v1/entrada_raio_fonte.geojson` | `c4db552973f9128affe7525350a64e4c1e721b9b5582c749bc2714b927ffa0ab` |
| 24 setores v1 | `outputs/campo_rural01/processamento_cego_v1/setores_rural01.geojson` | `bfa023ec8899bb6f37487cf92a154cee21388fdf67e36ecb34224189a9e042fc` |
| Top-3 v1 | `outputs/campo_rural01/processamento_cego_v1/top3_rural01.json` | `887f427d095b4e0a050f813061c67a616e23525f228d8d30e1a1ecfecf4bd268` |

O Top-3 v1 deve permanecer como linha de base comparativa. Ele não deve ser
usado para calibrar os parâmetros da v2 antes da abertura do ground truth.

## 10. Dados não encontrados localmente

Não foram encontrados arquivos geoespaciais locais para:

- Copernicus DEM;
- TOPODATA;
- MapBiomas;
- ANA/SNIRH;
- LiDAR, ALOS ou outro modelo de terreno de maior resolução;
- cercas e porteiras;
- linhas de transmissão;
- trilhas levantadas em campo;
- barrancos, grotas, valas e taludes;
- densidade de sub-bosque, cipós ou vegetação emaranhada;
- pontes, vaus e locais de travessia confirmados;
- Sentinel-2 bruto ou multibanda contemporâneo ao campo;
- ortomosaico georreferenciado das fotografias do drone.

Ausência de dado deve ser representada como **desconhecida**, e não como
ausência de obstáculo ou passagem livre.

## 11. Recomendação de implementação sem download

### 11.1 Grade e projeção

Adotar grade comum de aproximadamente 30 m em projeção métrica local, como
AEQD centrada no ponto inicial ou UTM zona 22N. O SRTM define a resolução
efetiva do componente de relevo. O WorldCover de 10 m deve ser agregado dentro
de cada célula de 30 m por proporção ou classe dominante, em vez de usar
interpolação que produza falsa precisão do relevo.

### 11.2 Componentes de custo relativo

Construir componentes separados e auditáveis:

1. custo de relevo, incluindo declividade e direção de movimento;
2. custo de cobertura do solo, com mais de um conjunto de multiplicadores;
3. redução de custo sobre vias mapeadas;
4. aumento de custo na hidrografia e áreas úmidas;
5. máscara opcional de obstáculos confirmados em campo;
6. camada explícita de incerteza/proveniência.

As vias devem apoiar duas análises distintas: plausibilidade de deslocamento
da vítima e acessibilidade da equipe. Um local difícil para a equipe não deve
ser automaticamente excluído como hipótese para a vítima.

### 11.3 Interpretação permitida

A saída admissível é:

- custo acumulado relativo;
- corredores plausíveis de menor resistência;
- zonas de desvio ou retenção potencial;
- comparação entre cenários de resistência;
- estabilidade espacial das áreas priorizadas.

Sem calibração local de velocidade, resistência de vegetação e comportamento,
fica proibido interpretar o custo como minutos, afirmar que o indivíduo
alcançaria determinada célula em 14 horas ou apresentar a área acumulada como
probabilidade de presença.

### 11.4 Sensibilidade mínima

Executar ao menos três configurações pré-especificadas:

- resistência moderada de vegetação e hidrografia;
- resistência elevada de vegetação densa/área úmida;
- cenário com maior atração por vias e caminhos.

Se o Top-3 ou os corredores mudarem substancialmente entre configurações, a
saída deve permanecer em `REVISAR`. A estabilidade entre cenários é evidência
de robustez relativa, não validação operacional.

## 12. Alertas metodológicos finais

1. O motor v1 avalia setores por média de nove amostras raster; ele não calcula
   o custo do caminho entre o ponto inicial e cada setor.
2. O escore GEO-04 v1 não distingue subida de descida e não representa tempo.
3. A classificação WorldCover não mede o interior da mata.
4. O OSM pode omitir feições importantes e não confirma seu estado atual.
5. O SRTM de aproximadamente 30 m não identifica todos os obstáculos descritos
   pela experiência operacional.
6. A composição TCC 2021 é contextual e não deve ser chamada de imagem atual.
7. As fotografias disponíveis não formam cobertura espacial suficiente para
   substituir as camadas públicas.
8. Barreiras públicas devem produzir resistência ou alerta, não veto absoluto,
   salvo quando houver evidência independente e regra pré-especificada.
9. Qualquer função de Tobler, tabela de velocidades ou multiplicador de
   vegetação deve entrar como hipótese documentada e submetida à sensibilidade.
10. O ground truth deve permanecer fechado até a configuração, a execução e o
    congelamento das saídas da v2.
