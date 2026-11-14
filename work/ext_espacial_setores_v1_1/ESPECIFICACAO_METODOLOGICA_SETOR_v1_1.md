# ESPECIFICAÇÃO METODOLÓGICA SETOR-v1.1

## Setorização e priorização espacial sobre buffers adaptativos

**Identificador:** EXT-ESP-SET-v1.1  
**Versão:** 1.1  
**Data da especificação:** 14 de outubro de 2026  
**Fase:** DEV-S  
**Estado:** CONGELADO PARA DESENVOLVIMENTO; NÃO CONFIRMATÓRIO  
**Componente:** extensão espacial da arquitetura de apoio à decisão em busca e salvamento  
**Dependência direta:** EXT-ESP-BUF-v1.0  
**Regra de controle:** nenhum dado de ground truth pode ser consultado durante geração, caracterização, pontuação ou priorização dos setores.

---

## 1. Finalidade e escopo

O SETOR-v1.1 transforma cada polígono de buffer adaptativo em 24 unidades
espaciais menores, extrai atributos territoriais de cada unidade e produz um
ranking restrito aos setores do próprio buffer.

O componente entrega duas saídas metodologicamente distintas:

1. uma partição geométrica rastreável do buffer recebido;
2. uma prioridade territorial relativa, calculada com GEO-02 a GEO-05.

O escore representa **prioridade operacional territorial relativa** segundo os
critérios públicos disponíveis. Não representa probabilidade de presença da
vítima, não estima sua posição e não substitui a decisão humana no comando da
missão SAR.

A execução DEV-S serve para engenharia, reprodutibilidade e avaliação do
comportamento do artefato. Não altera a REP-C, não recalibra o motor de
confiabilidade e não converte pontos históricos em validação independente. A
avaliação confirmatória futura exige REP-S com locais novos, protocolo
pré-especificado e ground truth protegido até o congelamento das saídas.

## 2. Alterações controladas da v1.1

A v1.1 corrige quatro limitações identificadas na auditoria da v1.0:

1. **geometria autoritativa:** o motor reutiliza o contorno do buffer recebido
   no GeoJSON; não reconstrói um segundo círculo a partir de centro e raio;
2. **partição homotética:** os anéis internos são cópias escaladas do contorno
   autoritativo, preservando o domínio externo;
3. **empates substantivos:** o ranking é de competição, e `sector_id` serve
   somente à ordem determinística dos arquivos;
4. **ausência estrita:** um critério obrigatório ausente produz escore e rank
   nulos, sem redistribuição de pesos.

A v1.0 é preservada como linha de base de auditoria e não deve ser confundida
com a execução científica v1.1.

## 3. Artefatos de origem e precedência

A execução usa, nesta ordem:

1. o GeoJSON de buffers do EXT-ESP-BUF-v1.0, como domínio geométrico
   autoritativo;
2. o JSON tabular do buffer, para chaves, centro, raio, avisos e proveniência;
3. o manifesto do buffer, para cardinalidade e integridade por SHA-256;
4. os recortes versionados das fontes GEO;
5. `config_setorizacao_priorizacao_v1_1.json`;
6. o código versionado do motor.

O arquivo tabular não substitui a geometria. Em caso de divergência entre uma
aproximação circular derivada do raio e o contorno recebido, prevalece o
GeoJSON autoritativo, e a divergência deve ser registrada ou rejeitada conforme
o contrato.

Os atributos GEO de um ponto ou de uma janela anterior não podem ser copiados
e rotulados como atributos de setor. A extração é refeita no nível de cada
polígono setorial.

## 4. Unidade de análise e identificadores

A unidade de processamento é o **buffer de um candidato**, identificado por:

```text
scenario_id + candidate_id
```

A unidade elementar de saída é o setor, identificado por:

```text
{scenario_id}::{candidate_id}::R{ring_index_2d}::{direction_label}
```

Exemplo:

```text
RS-001::RS-001-C1::R02::SE
```

Regras do identificador:

- separador único `::`;
- componentes não vazios;
- componentes de origem não podem conter o separador;
- anéis `R01`, `R02` e `R03`;
- direções `N`, `NE`, `E`, `SE`, `S`, `SW`, `W` e `NW`.

O SETOR-v1.1 não cria `buffer_id` sintético nem replica `candidate_rank`. O
ranking de candidatos pertence a outro nível arquitetural. Setores de buffers
distintos não concorrem entre si, ainda que suas geometrias se sobreponham.

## 5. Construção geométrica autoritativa

### 5.1 Referência espacial e plano local

As entradas e saídas geográficas usam EPSG:4326, com coordenadas na ordem
longitude–latitude. Cálculos métricos não podem usar graus diretamente. Para
cada buffer, o motor cria um sistema métrico local centrado no ponto estimado
do candidato, usando o raio médio da Terra WGS84 registrado na configuração.

O manifesto deve registrar versões do interpretador, dependências relevantes,
sistema de referência e método de transformação.

### 5.2 Condições do polígono-pai

O polígono de entrada deve:

- ser `Polygon` com um anel externo fechado;
- possuir ao menos quatro vértices únicos;
- conter o ponto estimado do candidato;
- ser válido e não vazio;
- ser convexo em relação ao candidato e, portanto, estrelado nesse ponto, de
  modo que cada raio usado na partição encontre um único limite externo.

O não atendimento dessas condições aborta o buffer ou a execução segundo o
contrato. O motor não corrige silenciosamente o contorno e não cria uma nova
geometria circular para substituir o pai.

### 5.3 Anéis homotéticos

Seja $P$ o polígono-pai representado em coordenadas locais com o candidato na
origem. Para (t \in [0,1]), define-se a transformação homotética:

\[
H_t(x,y)=(tx,ty)
\]

Os limites dos três anéis usam:

\[
t_0=0,\qquad t_1=\sqrt{\frac{1}{3}},\qquad
t_2=\sqrt{\frac{2}{3}},\qquad t_3=1
\]

Como a área de $H_t(P)$ é $t^2A(P)$, cada faixa homotética contém um terço
da área do polígono-pai. O limite de `R03` reutiliza exatamente o contorno de
entrada; não há nova discretização do arco externo.

Os campos `inner_radius_m` e `outer_radius_m` preservam a semântica radial da
configuração e auxiliam a amostragem. A autoridade topológica, contudo, é o
polígono-pai e suas cópias homotéticas.

### 5.4 Direções e cunhas

Cada anel é dividido em oito cunhas de 45 graus centradas em:

| Direção | Centro angular |
|---|---:|
| N | 0° |
| NE | 45° |
| E | 90° |
| SE | 135° |
| S | 180° |
| SW | 225° |
| W | 270° |
| NW | 315° |

O azimute parte do norte verdadeiro e cresce no sentido horário. Os limites
ficam a 22,5 graus de cada centro. Cada polígono setorial reúne o trecho do
contorno externo entre os dois raios, os segmentos radiais e o trecho inverso
do limite interno homotético. No anel interno, o limite interno é o próprio
centro.

### 5.5 Área e topologia

A referência de área é a área planar do GeoJSON autoritativo no sistema local:

\[
A_{esperada} = \frac{A(P)}{24}
\]

Para cada buffer, devem ser verificados:

- exatamente 24 setores;
- polígonos fechados, válidos e não vazios;
- vértices contidos no polígono-pai;
- limite externo agregado coincidente com o contorno recebido;
- soma das áreas dos setores compatível com $A(P)$;
- ausência de sobreposição interna além das fronteiras compartilhadas;
- erro relativo de cada setor em relação a $A(P)/24$ menor ou igual a 1%;
- erro relativo de conservação da área-pai menor ou igual a $10^{-6}$.

A igualdade por setor é um gate de validação do buffer de origem e da partição,
não uma licença para substituir o contorno por um círculo idealizado.

## 6. Extração dos atributos GEO

### 6.1 Princípios comuns

Cada registro deve conservar fonte, versão ou data, resolução nominal, método,
cobertura válida, limitação e hash. A ausência de feição em base pública não
prova ausência no terreno.

Vetores são medidos em relação ao setor. Linhas são aproximadas por
subsegmentos determinísticos de 50 m cujo ponto médio é alocado a um setor. A
alocação é aproximação de desenvolvimento, não interseção vetorial exata.

Rasters usam nove amostras estratificadas de área por setor, em uma malha 3 ×
3 radial-angular. A v1.1 exige fração válida igual a 1, ou seja, nove amostras
válidas de nove esperadas. O motor registra contagem esperada, contagem válida
e cobertura para relevo e cobertura do solo.

### 6.2 GEO-02 — vias e trilhas

São calculados distância à rede, comprimentos aproximados no setor, densidade
linear e escore de acesso:

\[
P_{via}=e^{-d_{via}/2000}
\]

\[
P_{trilha}=e^{-d_{trilha}/1500}
\]

\[
D_{rede}=\min\left(1,\frac{densidade_{via}+densidade_{trilha}}{4}\right)
\]

\[
GEO02=0{,}50P_{via}+0{,}25P_{trilha}+0{,}25D_{rede}
\]

### 6.3 GEO-03 — hidrografia

São calculados distância à feição hidrográfica, densidade aproximada,
severidade e sinalização de barreira:

\[
P_h=e^{-d_h/1500}\times severidade
\]

\[
D_h=\min\left(1,\frac{densidade_h}{3}\right)
\]

\[
B_h=0{,}75P_h+0{,}25D_h
\]

\[
GEO03=\max(0,1-B_h)
\]

Barreiras públicas geram sinalização e transformação suave. Não produzem veto
automático, pois a fonte não confirma largura, ponte, navegabilidade ou estado
atual da travessia.

### 6.4 GEO-04 — relevo

Nove amostras estratificadas alimentam estatísticas de elevação, amplitude e
declividade Horn 3 × 3:

\[
P_{declive}=e^{-declividade_{media}/8}
\]

\[
P_{relevo}=e^{-amplitude/30}
\]

\[
GEO04=0{,}70P_{declive}+0{,}30P_{relevo}
\]

O modelo com resolução aproximada de 30 m não representa microrrelevo,
obstáculos sob dossel ou transitabilidade atual.

### 6.5 GEO-05 — cobertura e uso do solo

O ESA WorldCover 2021 v200 é consultado nas mesmas nove posições. Cada classe
possui o escore congelado na configuração, e o resultado é a média dos valores
válidos:

\[
GEO05=\frac{\sum_c n_cs_c}{\sum_c n_c}
\]

Água/área úmida, floresta/manguezal, ambiente aberto e área construída geram
sinais de contexto conforme os limiares congelados. O produto representa 2021
e não comprova a condição atual.

## 7. Síntese territorial

### 7.1 Configuração principal

\[
S_{BASE}=0{,}30GEO02+0{,}25GEO03+0{,}20GEO04+0{,}25GEO05
\]

Os pesos são hipóteses metodológicas herdadas do GEO-06 e transferidas para o
nível setorial. Não são parâmetros aprendidos nem validados em campo.

### 7.2 Sensibilidades e ablações

| Conjunto | GEO-02 | GEO-03 | GEO-04 | GEO-05 | Função |
|---|---:|---:|---:|---:|---|
| BASE | 0,30 | 0,25 | 0,20 | 0,25 | principal DEV-S |
| IGUAIS | 0,25 | 0,25 | 0,25 | 0,25 | controle sem preferência |
| SEM_BARREIRAS | 0,60 | 0,00 | 0,40 | 0,00 | ablação GEO-03/GEO-05 |
| APENAS_ACESSO | 1,00 | 0,00 | 0,00 | 0,00 | ablação apenas GEO-02 |
| ENFASE_BARREIRAS | 0,20 | 0,35 | 0,15 | 0,30 | sensibilidade |

Não há penalização adicional: GEO-03 e GEO-05 já incorporam custos potenciais,
e uma segunda penalização produziria dupla contagem.

## 8. Ranking de competição, margem e estabilidade

### 8.1 Comparação e rank

Os escores são quantizados em nove casas decimais antes da comparação. Em cada
conjunto de pesos e dentro de cada buffer:

\[
rank_i=1+\#\{j:S_j>S_i\}
\]

Esse ranking de competição gera, por exemplo, `1, 2, 2, 4`. Setores empatados
compartilham o mesmo rank. A ordenação física por `sector_id` é apenas um
recurso de serialização determinística e não cria preferência substantiva.

### 8.2 Top-1 BASE

O motor registra o conjunto completo de setores no rank 1. Se o Top-1 BASE
contiver mais de um setor:

- `top1_sector_id` fica nulo;
- `top1_sector_ids_base` preserva todos os co-vencedores;
- nenhum setor recebe `selected_sector=true`;
- a margem é zero;
- a decisão é `REVISAR`;
- são registrados `BASE_TOP_TIE` e `NO_UNIQUE_TOP1`.

### 8.3 Sensibilidade e suporte fracionário

Para cada conjunto de pesos $w$, seja $T_w$ o conjunto de setores no rank 1. O
suporte do setor $i$ é:

\[
stability_i=\frac{1}{|W|}\sum_{w\in W}
\frac{I(i\in T_w)}{|T_w|}
\]

Essa regra impede que um empate com muitos co-vencedores conte como vitória
integral para todos. Também são registrados:

- número de conjuntos em que o setor pertenceu ao Top-1;
- número de vitórias Top-1 únicas;
- pontos de suporte acumulados;
- quantidade de conjuntos com empate no Top-1;
- lista de co-vencedores por conjunto.

`SENSITIVITY_TOP_TIE` é informativo por si só. Ele leva a `REVISAR` quando
impede o atendimento simultâneo dos gates de estabilidade e de quatro vitórias
únicas.

### 8.4 Margem e robustez

A margem BASE é a diferença entre o maior e o segundo maior escore comparável:

\[
M=S_{(1)}-S_{(2)}
\]

Os gates são:

- margem (M \geq 0{,}05);
- estabilidade fracionária (geq 0{,}80);
- pelo menos quatro vitórias Top-1 únicas entre cinco conjuntos;
- Top-1 BASE único;
- completude e proveniência válidas.

## 9. Política estrita de ausência

Os estados de atributo são `DISPONIVEL`, `PARCIAL` e `NAO_DISPONIVEL`. Um
estado parcial pode ser útil à auditoria descritiva, mas não autoriza pontuação
agregada.

Se qualquer escore obrigatório estiver ausente ou se `geo_completeness < 1`:

1. todos os escores agregados do setor ficam nulos;
2. todos os ranks do setor ficam nulos;
3. os pesos permanecem inalterados e não são renormalizados;
4. o setor e seu buffer são marcados para revisão;
5. são registrados `INCOMPLETE_GEO` e `MISSING_REQUIRED_GEO_SCORE`;
6. se nenhum setor completo existir, nenhum Top-1 é selecionado e
   `NO_COMPLETE_SECTOR` é registrado.

O mesmo princípio vale para proveniência obrigatória: sua ausência não é
silenciosa e produz `MISSING_SOURCE_PROVENANCE` e `REVISAR`.

Não são calculados `S_parcial`, `S_min` ou `S_max` na v1.1. Esses resultados
foram retirados para evitar que incompletude pareça evidência comparável.

## 10. Política de decisão

Os únicos estados persistidos são:

| Estado | Interpretação |
|---|---|
| `PRIORIZADO` | Top-1 BASE único; dados completos; margem e robustez aprovadas; sem alerta bloqueante |
| `REVISAR` | supervisão humana requerida por empate, baixa margem, instabilidade, incompletude, proveniência, barreira potencial ou revisão de origem |

Falha de esquema, geometria, integridade, faixa, firewall ou contrato aborta a
execução. `ERRO_DE_PROCESSAMENTO` não é gravado como decisão científica.

Os alertas válidos são:

```text
UPSTREAM_REVIEW_REQUIRED
INCOMPLETE_GEO
NO_COMPLETE_SECTOR
LOW_MARGIN
BASE_TOP_TIE
NO_UNIQUE_TOP1
SENSITIVITY_TOP_TIE
RANKING_UNSTABLE
POTENTIAL_BARRIER
MISSING_REQUIRED_GEO_SCORE
MISSING_SOURCE_PROVENANCE
```

Todos os resultados requerem supervisão humana. `PRIORIZADO` significa que os
gates analíticos intrabuffer foram atendidos; não significa autorização de
deslocamento ou comando operacional.

## 11. Firewall de ground truth

### 11.1 Escopo

O firewall examina recursivamente:

- JSON tabular e GeoJSON dos buffers;
- manifesto do buffer;
- entradas vetoriais OSM;
- estruturas intermediárias relevantes;
- CSV, JSON, GeoJSON e manifesto produzidos.

A correspondência é por fragmento normalizado de chave, sem distinção entre
maiúsculas e minúsculas. A lista configurada inclui termos de ground truth,
coordenada real, referência, alvo/vítima, distâncias ao gabarito, pertencimento
ao buffer e setor correto.

### 11.2 Exceção controlada

O único campo permitido é:

```text
ground_truth_used = false
```

O valor deve ser booleano estritamente falso. O campo não autoriza payload de
ground truth. Qualquer chave proibida ou valor verdadeiro aborta a execução.

### 11.3 Momento da abertura

A referência protegida só pode ser aberta após:

1. testes e verificação independente aprovados;
2. repetição determinística;
3. congelamento de geometria, configuração, saídas e hashes;
4. autorização do gate REP-S pertinente.

## 12. Saídas e serialização

Arquivos científicos:

1. `sector_polygons_dev.geojson`;
2. `sector_features_dev.csv`;
3. `sector_ranking_dev.csv`;
4. `buffer_decisions_dev.csv`;
5. `sector_results_dev.json`;
6. `warnings_dev.log`.

Controle:

7. `manifest_setorizacao_dev.json`.

A ordem canônica é:

```text
scenario_id, candidate_id, ring_index, direction_index
```

Os arquivos devem registrar protocolo, versão do motor, fase DEV-S,
classificação não confirmatória, método geométrico, escores, ranks, co-vencedores,
margem, estabilidade, alertas, proveniência e `ground_truth_used=false`.

O manifesto registra SHA-256 das entradas, configuração, motor e seis saídas
científicas. O hash científico agregado não inclui timestamp, caminho absoluto
ou o próprio manifesto.

## 13. Testes de aceitação

### 13.1 Contrato e geometria

- configuração válida e versão v1.1;
- chaves únicas e componentes de ID válidos;
- uma geometria autoritativa por buffer;
- 24 setores por buffer;
- reutilização do contorno externo recebido;
- anéis homotéticos nas escalas congeladas;
- áreas individuais dentro da tolerância;
- soma de áreas igual ao pai dentro de $10^{-6}$;
- vértices contidos no pai;
- ausência de sobreposição interna relevante;
- funcionamento próximo ao Equador e nos dois hemisférios.

### 13.2 Atributos e ausência

- escores GEO no intervalo `[0,1]`;
- nove amostras raster válidas de nove esperadas;
- ausência preservada como nula;
- nenhum peso renormalizado;
- rank nulo para setor incompleto;
- proveniência obrigatória presente;
- nenhum valor ausente tratado como zero favorável.

### 13.3 Ranking e empates

- ranking restrito a `scenario_id + candidate_id`;
- ranks de competição reproduzidos;
- ordem de entrada sem efeito no resultado;
- BASE empatado sem seleção;
- listas de co-vencedores completas;
- suporte fracionário correto;
- quatro vitórias únicas exigidas para robustez;
- serialização por ID sem efeito substantivo.

### 13.4 Segurança e reprodutibilidade

- bloqueio de chaves proibidas simples, compostas e com caixa alterada;
- `ground_truth_used=false` em todas as estruturas permitidas;
- duas execuções científicas idênticas;
- hashes completos no manifesto;
- verificador independente aprovado.

## 14. Métricas permitidas no DEV-S fechado

- número de buffers e setores;
- conservação de área e erro topológico;
- completude por módulo;
- distribuição dos escores;
- taxa de empates BASE e de sensibilidade;
- margem BASE;
- estabilidade e vitórias únicas;
- proporção `PRIORIZADO`/`REVISAR`;
- incidência de cada alerta;
- tempo de processamento;
- reprodutibilidade por hash.

Nenhuma dessas métricas exige ou permite o uso da posição verdadeira.

## 15. Avaliação posterior autorizada

Somente após o congelamento e a abertura controlada poderão ser calculadas
cobertura do buffer, Top-k de setor, Mean Reciprocal Rank, área acumulada até o
setor de referência e comparações com baselines pré-especificados.

Se a referência estiver fora do buffer, o caso será falha de cobertura. O
buffer não será ampliado retrospectivamente. Se a referência estiver em
fronteira setorial, serão preservados todos os setores intersectados e aplicado
o critério conservador pré-especificado.

## 16. Limites de interpretação

1. Setores radiais são unidades analíticas regulares, não zonas operacionais
   confirmadas em campo.
2. Os pesos são hipóteses DEV-S, não parâmetros aprendidos.
3. OSM possui cobertura colaborativa e desigual.
4. Hidrografia pública não confirma travessia ou risco atual.
5. O modelo de elevação não representa microrrelevo.
6. WorldCover representa 2021 e possui erro temático.
7. Nove pontos constituem amostragem, não censo raster.
8. A alocação de linhas por subsegmentos é aproximação determinística.
9. Buffers distintos podem se sobrepor; não há ranking global de setores.
10. Prioridade territorial relativa não é probabilidade de localização da
    vítima.
11. `PRIORIZADO` não é ordem operacional.
12. DEV-S não sustenta alegação confirmatória de eficácia em missão real.

## 17. Fluxo REP-S

1. preparar sítios, permissões, fontes e separação por local;
2. fechar e lacrar o ground truth;
3. congelar as entradas cegas e seus hashes;
4. verificar os motores de buffer e SETOR-v1.1;
5. executar sem acesso ao gabarito;
6. repetir e comparar os hashes científicos;
7. congelar buffers, setores, ranks, decisões, logs e manifestos;
8. abrir a referência somente após os gates;
9. calcular as métricas pré-especificadas sem alterar a configuração;
10. arquivar resultados positivos, negativos, empates, revisões e limitações.

## 18. Regra final de validade

O SETOR-v1.1 só poderá integrar uma avaliação confirmatória se geometria,
fontes, amostragem, ausência, pesos, empates, limiares, serialização, testes e
firewall estiverem congelados antes da REP-S. Qualquer alteração posterior
exige novo identificador de versão, justificativa, repetição integral dos
testes e novo congelamento. Resultados produzidos após conhecimento do ground
truth serão classificados como pós-hoc.
