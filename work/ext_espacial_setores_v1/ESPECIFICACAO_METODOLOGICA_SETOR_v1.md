# ESPECIFICAÇÃO METODOLÓGICA SETOR-v1

## Setorização e priorização espacial sobre buffers adaptativos

**Identificador:** EXT-ESP-SET-v1.0  
**Versão:** 1.0  
**Data da especificação:** 14 de outubro de 2026  
**Estado:** IMPLEMENTADO E EXECUTADO EM DEV-S; NÃO CONFIRMATÓRIO  
**Componente:** extensão espacial da arquitetura de apoio à decisão em busca e salvamento  
**Dependência direta:** EXT-ESP-BUF-v1.0  
**Regra de controle:** nenhum dado de ground truth pode ser consultado durante a geração, caracterização ou priorização dos setores.

**Evidência de execução:** 90 buffers, 2.160 setores, quatro módulos GEO
completos, 25/25 testes aprovados e repetição determinística com hash científico
`fd092f2db09448002346130d8cd7f809fe2b151ab21db415b98caec5e64085d7`.

---

## 1. Finalidade e escopo

O SETOR-v1 transforma cada buffer adaptativo produzido pelo EXT-ESP-BUF-v1.0 em unidades espaciais menores, comparáveis e ordenáveis. Sua finalidade é oferecer uma representação territorial operacionalmente compreensível para apoiar a alocação inicial de atenção e recursos em missões de busca e salvamento.

O componente produz duas saídas distintas:

1. a divisão geométrica reproduzível do buffer em setores;
2. a priorização territorial dos setores a partir de atributos geoespaciais calculados sem acesso à posição verdadeira da vítima.

O resultado não representa probabilidade de presença da vítima nem substitui a decisão do comando da operação. O escore deve ser interpretado como **favorabilidade operacional territorial**, composta por acessibilidade cartografada, pressão de barreiras, relevo e cobertura do solo.

Esta especificação não altera os resultados da REP-C, não recalibra o motor de confiabilidade e não converte os seis pontos históricos em validação independente. Esses pontos permanecem no conjunto de desenvolvimento espacial, DEV-S. A confirmação futura deverá utilizar a REP-S, com locais novos, separação por sítio e ground truth protegido.

## 2. Artefatos de origem e precedência

A implementação deverá usar, nesta ordem:

1. o arquivo GeoJSON de buffers produzido pelo EXT-ESP-BUF-v1.0, como domínio geométrico autoritativo;
2. o arquivo tabular de resultados do buffer, para identificadores, centro, raio, avisos e proveniência;
3. as fontes geoespaciais brutas ou seus recortes versionados;
4. a configuração congelada do SETOR-v1;
5. o código versionado do motor de setorização e priorização.

Os principais artefatos locais que fundamentam esta especificação são:

- `work/ext_espacial_buffer_v1/config_buffer_v1.json`;
- `work/ext_espacial_buffer_v1/results/buffer_polygons_dev.geojson`;
- `work/ext_espacial_buffer_v1/results/buffer_results_dev.csv`;
- `outputs/sprint2_s2_06_geo05_v33/osm_highways_raw.json`;
- `outputs/sprint2_s2_06_geo05_v33/osm_hydrography_raw.json`;
- os quadrantes SRTM/Mapzen e ESA WorldCover preservados no pacote GEO-05;
- `outputs/sprint2_s2_07_geo06_v34/Sprint_2_S2-07_GEO-06_Sintese_Territorial_v34.xlsx`.

Os escores pontuais já calculados para cada candidato não podem ser simplesmente repetidos em seus setores. A caracterização precisa ser refeita no nível de cada polígono, pois a finalidade da extensão é produzir diferenciação espacial interna ao buffer.

## 3. Unidade de análise e tratamento de múltiplos candidatos

A unidade elementar é o **setor contido no buffer de um candidato**. Cada registro deve preservar, no mínimo:

- `scenario_id`;
- `candidate_id`;
- `buffer_id`;
- `sector_id`;
- `ring_id`;
- `direction_id`.

Quando um cenário possuir mais de um candidato, o SETOR-v1 manterá dois níveis de decisão:

1. `candidate_rank`, oriundo do componente de ranking de candidatos já congelado;
2. `sector_rank_within_buffer`, calculado exclusivamente entre os setores do mesmo buffer.

O SETOR-v1 não combinará numericamente o escore do candidato com o escore do setor. Essa combinação exigiria novos pesos, poderia produzir dupla contagem dos componentes GEO e alteraria a arquitetura já avaliada. A saída operacional deverá exibir os dois níveis em conjunto, sem os confundir.

Os setores pertencentes a buffers diferentes podem se sobrepor. Por isso:

- não devem ser tratados como áreas territoriais independentes em métricas de área;
- a área total de busca deverá ser calculada pela união dissolvida dos polígonos;
- a versão 1 não produzirá um ranking territorial único entre setores de buffers diferentes;
- eventual partição não sobreposta da união dos buffers será tratada como versão metodológica posterior.

## 4. Construção geométrica dos setores

### 4.1 Projeção de trabalho

Cada buffer será processado em uma projeção azimutal equidistante local, centrada nas coordenadas do respectivo candidato. Essa escolha preserva as distâncias radiais e evita erros associados ao uso de graus como metros, à proximidade do Equador e à possível transição entre zonas UTM.

O resultado final será transformado para EPSG:4326. A configuração da projeção local, a versão da biblioteca cartográfica e o método de transformação deverão constar do manifesto de execução.

### 4.2 Estratégia principal

O método principal terá **24 setores de área equivalente**, formados por três anéis e oito direções.

Para um buffer de raio adaptativo \(R\), os limites radiais serão:

\[
r_0=0
\]

\[
r_1=R\sqrt{\frac{1}{3}}
\]

\[
r_2=R\sqrt{\frac{2}{3}}
\]

\[
r_3=R
\]

Essa regra faz com que cada faixa anular contenha um terço da área circular. A divisão de cada faixa em oito partes produz setores com área teórica:

\[
A_s=\frac{\pi R^2}{24}
\]

Três anéis de mesma espessura não serão usados, pois resultariam em setores com áreas distintas e tornariam a comparação operacional menos direta.

### 4.3 Orientação

As direções serão centradas nos rumos cardeais e intercardeais:

| Código | Centro angular |
|---|---:|
| N | 0° |
| NE | 45° |
| E | 90° |
| SE | 135° |
| S | 180° |
| SO | 225° |
| O | 270° |
| NO | 315° |

Os limites ocorrerão a \(\pm 22{,}5°\) do centro de cada direção, com azimute contado a partir do norte verdadeiro e em sentido horário. Essa orientação será fixada antes da avaliação e não poderá ser rotacionada para aproximar setores da referência.

### 4.4 Recorte e identificação

As cunhas teóricas serão intersectadas com o polígono do buffer GeoJSON de origem. O recorte assegurará correspondência exata entre o domínio setorizado e o domínio previamente congelado.

O identificador seguirá o padrão:

```text
<scenario_id>|<candidate_id>|A<anel>|<direcao>
```

Exemplo:

```text
RS-001|RS-001-C1|A2|SE
```

### 4.5 Regras topológicas

Para cada buffer, a implementação deverá garantir:

- exatamente 24 setores;
- polígonos válidos e não vazios;
- ausência de lacunas internas relevantes;
- ausência de sobreposição de área entre setores do mesmo buffer;
- união dos setores equivalente ao buffer de origem;
- anel e direção derivados exclusivamente da configuração congelada.

Tolerâncias técnicas recomendadas para os testes de engenharia:

- diferença simétrica entre união e buffer menor ou igual a \(10^{-6}\) da área do buffer;
- sobreposição interna acumulada menor ou igual a \(10^{-8}\) da área do buffer;
- diferença relativa entre a área de um setor e \(\pi R^2/24\) menor ou igual a 1%, admitindo-se o efeito da discretização do polígono de origem.

As tolerâncias deverão ser verificadas no DEV-S antes do congelamento definitivo e não poderão ser alteradas após a abertura da REP-S.

## 5. Extração dos atributos GEO por setor

### 5.1 Princípios comuns

Cada atributo será calculado sobre o polígono do setor. Todos os resultados deverão registrar:

- fonte;
- versão ou data do recorte;
- resolução nominal;
- sistema de referência;
- transformação executada;
- cobertura válida;
- limitação aplicável;
- hash do arquivo-fonte.

As feições vetoriais deverão ser recortadas ou medidas em relação ao setor. As fontes raster deverão ser submetidas a estatística zonal com regra de inclusão de pixels explicitamente congelada. Recomenda-se usar o centro do pixel como regra principal (`all_touched=false`) e avaliar `all_touched=true` apenas como sensibilidade, sem selecionar retrospectivamente o método mais favorável.

### 5.2 GEO-02 — vias e trilhas

Para cada setor serão obtidos:

- distância mínima do polígono à via mapeada mais próxima;
- distância mínima do polígono à trilha mapeada mais próxima;
- comprimento de vias dentro do setor;
- comprimento de trilhas dentro do setor;
- densidade linear em km/km².

Serão preservadas as transformações do GEO02-v1:

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

Se mais de uma feição estiver à mesma distância, o desempate técnico deverá usar, nesta ordem: classe funcional registrada, identificador da feição e ordem lexical estável. A ausência de uma feição no OpenStreetMap não comprova sua ausência física.

### 5.3 GEO-03 — hidrografia

Para cada setor serão calculados:

- distância mínima à feição hidrográfica mapeada;
- comprimento hidrográfico dentro do setor;
- densidade hidrográfica;
- categoria e fator de severidade da feição relevante;
- sinalização de barreira potencial.

Serão preservadas as regras do GEO03-v1:

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

O mapeamento de severidade continuará sendo o versionado no GEO03-v1. Uma barreira cartografada produzirá alerta e penalidade suave, não veto automático. A camada não informa largura atual, existência de ponte, navegabilidade nem transitabilidade real.

### 5.4 GEO-04 — relevo

O modelo digital de elevação será usado para calcular, por setor:

- número e proporção de células válidas;
- elevação mínima, média e máxima;
- amplitude do relevo;
- declividade média;
- percentis de declividade para auditoria;
- classe predominante de declividade.

Serão preservadas as escalas do GEO04-v1:

\[
P_{declive}=e^{-declividade_{media}/8}
\]

\[
P_{relevo}=e^{-amplitude/30}
\]

\[
GEO04=0{,}70P_{declive}+0{,}30P_{relevo}
\]

A declividade será derivada pelo método Horn 3 × 3. A resolução nominal próxima de 30 m não representa microrrelevo, obstáculos sob o dossel ou condições atuais de deslocamento. A proporção de células válidas deverá ser registrada; cobertura inferior a 80% será tratada como parcial na configuração inicial e submetida a sensibilidade de 70% e 90% no DEV-S.

### 5.5 GEO-05 — cobertura e uso do solo

Para cada setor serão calculadas as proporções das classes do ESA WorldCover 2021. O escore será a média ponderada dos pixels válidos, usando os valores já registrados:

| Classe | Código | Escore |
|---|---:|---:|
| Cobertura arbórea | 10 | 0,35 |
| Arbustos | 20 | 0,50 |
| Herbáceas/pastagem | 30 | 0,80 |
| Cultivo | 40 | 0,75 |
| Área construída | 50 | 0,85 |
| Solo exposto/vegetação esparsa | 60 | 0,90 |
| Neve/gelo | 70 | 0,30 |
| Água permanente | 80 | 0,05 |
| Área úmida herbácea | 90 | 0,20 |
| Manguezal | 95 | 0,15 |
| Musgo/líquen | 100 | 0,45 |

Assim:

\[
GEO05=\frac{\sum_c n_c s_c}{\sum_c n_c}
\]

onde \(n_c\) é o número de pixels válidos da classe \(c\), e \(s_c\) é seu escore congelado.

Serão mantidos os limiares de sinalização já documentados:

- água e área úmida iguais ou superiores a 25%: barreira hídrica potencial;
- árvores e manguezal iguais ou superiores a 70%: vegetação densa potencial;
- classes abertas iguais ou superiores a 60%: ambiente aberto;
- área construída igual ou superior a 25%: ambiente urbano.

O produto representa o ano de 2021 e não comprova a condição atual do terreno.

## 6. Síntese territorial e ranking

### 6.1 Configuração principal

O escore principal reutilizará os pesos congelados no GEO06-v1:

\[
S_{base}=0{,}30GEO02+0{,}25GEO03+0{,}20GEO04+0{,}25GEO05
\]

Os pesos serão tratados como hipóteses metodológicas transferidas para o nível setorial, não como parâmetros aprendidos ou validados em campo.

### 6.2 Configurações de sensibilidade

Serão calculadas conjuntamente:

| Configuração | GEO-02 | GEO-03 | GEO-04 | GEO-05 | Finalidade |
|---|---:|---:|---:|---:|---|
| BASE | 0,30 | 0,25 | 0,20 | 0,25 | especificação principal |
| IGUAIS | 0,25 | 0,25 | 0,25 | 0,25 | controle sem preferência |
| SEM_BARREIRAS | 0,60 | 0 | 0,40 | 0 | ablação |
| APENAS_ACESSO | 1,00 | 0 | 0 | 0 | ablação GEO-02 |
| ENFASE_BARREIRAS | 0,20 | 0,35 | 0,15 | 0,30 | sensibilidade |

Para cada configuração, o ranking será calculado dentro do mesmo buffer. Escores maiores indicam maior favorabilidade operacional.

### 6.3 Empates e ordenação determinística

O ranking seguirá a regra de competição:

\[
rank_i=1+\#\{j:S_j>S_i\}
\]

Setores com o mesmo escore terão o mesmo rank e serão marcados como empate. A ordenação física do arquivo usará `sector_id` como desempate técnico, mas essa ordenação não será interpretada como superioridade substantiva.

A comparação numérica será feita com precisão integral de cálculo. Arredondamentos ocorrerão apenas na serialização, segundo regra congelada. Recomenda-se:

- coordenadas: oito casas decimais;
- distâncias e áreas: três casas decimais;
- escores: nove casas decimais.

### 6.4 Margem e estabilidade

A margem principal será:

\[
M=S_{(1)}-S_{(2)}
\]

Margem inferior a 0,05 será considerada insuficiente para uma prioridade forte.

A estabilidade Top-1 será a proporção das cinco configurações em que o mesmo setor ocupa a primeira posição. O resultado será considerado robusto quando alcançar pelo menos 0,80, isto é, quatro das cinco configurações.

As classes territoriais do GEO06-v1 poderão ser mantidas apenas como descrição:

- favorável: \(S_{base}\geq0{,}67\);
- intermediária: \(0{,}34\leq S_{base}<0{,}67\);
- restritiva: \(S_{base}<0{,}34\).

Essas classes não substituem a análise da margem, da estabilidade, da completude ou das barreiras.

## 7. Política de ausência e incompletude

### 7.1 Estados de disponibilidade

Cada módulo, em cada setor, deverá assumir um dos estados:

- `DISPONIVEL`: cobertura e amostras válidas suficientes;
- `PARCIAL`: cobertura válida inferior ao limiar técnico;
- `NAO_DISPONIVEL`: fonte não cobre o setor ou não produz amostras válidas;
- `LIMITACAO_DA_FONTE`: cálculo disponível, mas sujeito a limitação temporal, temática ou colaborativa.

Ausência de dado não será codificada como zero. Ausência cartográfica de feição também não será apresentada como comprovação de ausência física.

### 7.2 Escore parcial e intervalo de incerteza

Se \(m_i=1\) quando o módulo está disponível e \(m_i=0\) quando está ausente, será calculado:

\[
S_{parcial}=\frac{\sum_i w_i x_i m_i}{\sum_i w_i m_i}
\]

Também serão apresentados limites conservadores:

\[
S_{min}=\sum_i w_i x_i m_i
\]

\[
S_{max}=S_{min}+\sum_i w_i(1-m_i)
\]

Esses limites representam os extremos possíveis para módulos ausentes no intervalo de 0 a 1. O escore parcial serve à inspeção, não autoriza automaticamente uma prioridade.

### 7.3 Regra de comparabilidade

O ranking principal será emitido apenas quando todos os setores do buffer tiverem os quatro módulos disponíveis. Se o mesmo módulo estiver ausente para todos os setores e pelo menos três módulos permanecerem disponíveis, poderá ser produzido ranking provisório pelo escore parcial, obrigatoriamente marcado para revisão.

O motor deverá se abster quando ocorrer pelo menos uma das condições:

- menos de três módulos disponíveis;
- padrões de ausência diferentes entre setores concorrentes;
- intervalo \([S_{min},S_{max}]\) do primeiro colocado sobreposto ao intervalo de outro setor;
- cobertura espacial incompatível com comparação justa;
- impossibilidade de distinguir falta de dado de resultado territorial adverso.

## 8. Política de decisão e supervisão humana

O resultado por buffer terá um dos seguintes estados:

| Estado | Condições mínimas |
|---|---|
| `PRIORIZACAO_EMITIDA` | geometria válida; quatro módulos completos; margem ≥ 0,05; estabilidade ≥ 0,80; sem empate; intervalos não conflitantes |
| `PRIORIZACAO_COM_REVISAO` | prioridade calculável, mas com barreira potencial ou limitação cartográfica relevante |
| `ABSTER_REVISAO_HUMANA` | incompletude, empate, margem baixa, instabilidade, conflito entre intervalos ou cobertura insuficiente |
| `ERRO_DE_PROCESSAMENTO` | falha de esquema, geometria, projeção, integridade ou proveniência |

Barreiras hidrográficas, vegetação densa, relevo desfavorável e áreas úmidas não gerarão veto automático. O mapa indica contexto potencial, não transitabilidade confirmada. A decisão operacional permanecerá sob responsabilidade humana.

A confiança do candidato não será usada para ordenar seus setores, pois é constante dentro do respectivo buffer. Ela poderá qualificar a apresentação, reforçar a necessidade de revisão e organizar o nível superior da decisão, sem alterar o escore territorial interno.

## 9. Firewall de ground truth e reprodutibilidade

### 9.1 Campos vedados

As entradas e saídas científicas não poderão conter nomes ou fragmentos relacionados a:

```text
ground_truth
reference_lat
reference_lon
true_lat
true_lon
base_lat
base_lon
distance_to_reference
generator_distance
relevant_candidate
```

O campo de controle `ground_truth_used` poderá existir somente com valor booleano estritamente `false`.

### 9.2 Integridade

O manifesto deverá registrar SHA-256 de:

- arquivo de buffers;
- resultados tabulares do motor de buffer;
- configuração SETOR-v1;
- código do motor;
- fontes GEO e respectivos recortes;
- arquivos científicos produzidos;
- evidências de teste.

O manifesto e os logs poderão conter data, hora e caminhos de execução. Esses metadados serão preservados como evidência, mas não integrarão a comparação de determinismo dos resultados científicos.

### 9.3 Dupla execução

Antes de autorizar a abertura do ground truth, o mesmo pacote de entrada deverá ser executado duas vezes, com ambiente e configuração equivalentes. Os hashes dos arquivos científicos deverão coincidir. Divergência bloqueará a avaliação.

### 9.4 Ordem canônica

Os registros serão serializados em ordem:

```text
scenario_id, candidate_id, ring_id, direction_id, sector_id
```

As chaves de propriedades GeoJSON também deverão seguir ordem estável. A versão do interpretador e das bibliotecas geoespaciais será registrada.

## 10. Produtos do motor

O SETOR-v1 deverá produzir:

1. `sector_polygons.geojson` — geometrias e identificadores;
2. `sector_features.csv` — atributos GEO setoriais e completude;
3. `sector_ranking.csv` — escores, ranks, margens e estabilidade;
4. `buffer_decisions.csv` — síntese e estado de decisão por buffer;
5. `manifest_setorizacao.json` — proveniência, versões e hashes;
6. `test_results_setorizacao.json` — evidência dos testes automatizados;
7. log técnico de execução.

Campos mínimos de `sector_ranking.csv`:

```text
protocol_id
engine_version
scenario_id
candidate_id
candidate_rank
buffer_id
sector_id
ring_id
direction_id
azimuth_start_deg
azimuth_end_deg
area_m2
geo02_score
geo03_score
geo04_score
geo05_score
geo_completeness
score_base
score_equal
score_without_barriers
score_access_only
score_barrier_focus
rank_base
top1_stability
margin_to_second
barrier_flags
decision_status
ground_truth_used
```

## 11. Testes de aceitação

### 11.1 Geometria

- geração de 24 setores para todo buffer válido;
- anéis com os limites matemáticos especificados;
- orientação fixa pelo norte verdadeiro;
- polígonos válidos e não vazios;
- união equivalente ao buffer;
- ausência de sobreposição interna relevante;
- áreas equivalentes dentro da tolerância;
- funcionamento nos dois hemisférios e próximo ao Equador;
- funcionamento no raio mínimo e no raio máximo do EXT-ESP-BUF-v1.0.

### 11.2 Escores

- pesos de cada configuração somando 1;
- componentes e escores restritos ao intervalo [0,1];
- reprodução exata das fórmulas congeladas;
- ranking invariável à ordem das linhas de entrada;
- empates identificados sem desempate substantivo artificial;
- margem e estabilidade calculadas corretamente;
- barreiras sinalizadas sem veto automático.

### 11.3 Ausência

- valor ausente nunca transformado silenciosamente em zero;
- cálculo correto do escore parcial e dos limites;
- abstenção com menos de três módulos;
- abstenção quando padrões de ausência forem incompatíveis;
- distinção entre ausência cartográfica, nodata e valor territorial baixo.

### 11.4 Segurança metodológica

- rejeição de campos proibidos;
- `ground_truth_used=false` em todos os resultados e manifestos;
- ausência de consulta ao arquivo protegido durante o processamento;
- hashes científicos idênticos em execução repetida;
- alteração de configuração exigindo novo identificador de versão.

## 12. Métricas anteriores à abertura do ground truth

As métricas de engenharia e comportamento permitidas na fase cega são:

- número de setores produzidos;
- conservação da área;
- erro topológico;
- completude por módulo e por setor;
- distribuição dos escores;
- margem entre primeiro e segundo;
- estabilidade Top-1 entre configurações;
- taxa de empates;
- taxa de abstenção;
- sensibilidade à resolução espacial;
- sensibilidade à rotação;
- tempo de processamento;
- reprodutibilidade por hash.

As análises de sensibilidade geométrica serão:

- 12 setores: três anéis por quatro direções;
- 36 setores: três anéis por doze direções;
- rotação de 22,5° da configuração principal.

A configuração principal permanecerá a de 24 setores. A análise de sensibilidade não poderá ser usada para selecionar retrospectivamente a geometria com melhor desempenho na REP-S.

## 13. Métricas posteriores à abertura controlada

Somente depois do congelamento das saídas e da autorização de abertura serão calculadas:

- cobertura do buffer e intervalo de Wilson;
- Top-1, Top-3 e Top-5 de setor;
- Mean Reciprocal Rank de setor;
- posição hierárquica candidato–setor;
- área acumulada até alcançar o setor de referência;
- proporção da área do buffer pesquisada até o acerto;
- arrependimento espacial;
- cobertura seletiva em função da abstenção;
- comparação com prioridade uniforme, aleatória com semente fixa, radial, apenas acesso e pesos iguais;
- robustez a resolução, rotação, pesos e dados ausentes.

Se a referência estiver fora do buffer, o caso será contado como falha de cobertura. O raio não será ampliado retrospectivamente.

Se a referência estiver exatamente sobre uma borda, todos os setores cobertos pela geometria serão registrados. Para cobertura, o caso contará como contido. Para ranking, será usado o critério conservador: a posição do setor de referência será a pior posição entre os setores que cobrem o ponto. Top-1 somente será atribuído se todos esses setores ocuparem a primeira posição.

Em cenários com buffers sobrepostos, as métricas territoriais usarão área dissolvida. A avaliação reportará separadamente o rank do candidato e o rank do setor dentro do buffer correspondente.

## 14. Baselines e ablações

A avaliação deverá incluir, no mínimo:

- setores sem priorização, considerados uniformes;
- ordenação aleatória com semente fixa;
- prioridade radial, com anel interno antes dos demais;
- apenas GEO-02;
- pesos iguais;
- sem barreiras;
- configuração SETOR-v1 completa.

O baseline radial não será incorporado à configuração principal, pois não existe, nesta etapa, distribuição de erro empiricamente calibrada que justifique transformar proximidade ao centro em probabilidade de presença.

## 15. Limites de interpretação

1. Os pesos GEO foram definidos no piloto e transferidos para o nível setorial; não foram aprendidos com dados de campo.
2. OSM possui cobertura colaborativa e desigual. Ausência na base não prova ausência física.
3. A hidrografia cartografada não informa, por si só, largura atual, ponte, travessia ou risco operacional.
4. O SRTM, com resolução aproximada de 30 m e possível influência do dossel, não representa microrrelevo.
5. O ESA WorldCover representa 2021 e está sujeito a erro temático e mudança de uso do solo.
6. A favorabilidade operacional não equivale à probabilidade de localização da vítima.
7. A divisão radial impõe orientação e resolução artificiais; por isso, rotação e número de setores integram a sensibilidade.
8. Buffers de candidatos diferentes podem se sobrepor; a versão 1 não resolve essa sobreposição por partição única.
9. Resultados do DEV-S servem para engenharia, ajuste documentado e teste de comportamento, não para alegação confirmatória.
10. Fotografias, inspeção de campo e imagens recentes poderão enriquecer a interpretação futura, mas não serão inseridas retrospectivamente como variáveis numéricas da configuração congelada.

## 16. Fluxo REP-S

O fluxo confirmatório seguirá os estados já definidos no pacote REP-S:

1. **T−1 — PREPARACAO:** verificar sítios, permissões, fontes GEO e separação por local;
2. **T0 — GROUND_TRUTH_FECHADO:** lacrar coordenadas reais e cadeia de custódia;
3. **T1 — ENTRADA_CEGA_CONGELADA:** congelar posições estimadas, atributos permitidos e hashes;
4. **T1.5 — MOTOR_VERIFICADO:** comprovar testes do buffer e do SETOR-v1;
5. executar o buffer adaptativo e a setorização sem acesso ao gabarito;
6. repetir a execução e comparar hashes científicos;
7. **T2 — SAIDA_DO_MODELO_CONGELADA:** bloquear buffers, setores, ranking, decisões, logs e manifestos;
8. **T3 — GROUND_TRUTH_ABERTO:** abrir a referência somente após aprovação dos gates de integridade e determinismo;
9. calcular as métricas pré-especificadas sem alterar geometria, pesos, fontes ou política de decisão;
10. **T4 — AVALIACAO_CONCLUIDA:** arquivar resultados positivos, negativos, abstenções e limitações.

Os seis pontos históricos poderão ser usados para demonstração e testes DEV-S. A REP-S deverá empregar locais novos e independentes, definidos antes dos desfechos e separados por sítio.

## 17. Próximos passos de implementação

1. criar `config_setorizacao_v1.json` com geometria, fórmulas, pesos, limiares, política de ausência e precisão de serialização;
2. implementar o gerador geométrico com projeção azimutal equidistante local;
3. implementar os extratores setoriais GEO-02 a GEO-05 a partir das fontes brutas;
4. implementar síntese, sensibilidade, ranking e abstenção;
5. criar fixtures integralmente sintéticos para testes unitários, inclusive nos dois hemisférios;
6. executar um dry run no DEV-S, sem alegação confirmatória;
7. produzir mapas de inspeção com buffer, anéis, direções, escores e alertas;
8. auditar completude, topologia, fórmulas, hashes e ausência de ground truth;
9. congelar a versão que atender aos gates;
10. aplicar a versão congelada uma única vez à REP-S independente.

## 18. Regra final de validade

O SETOR-v1 estará apto para avaliação confirmatória somente quando a geometria, os extratores, a política de ausência, os pesos, os limiares, os testes e a serialização estiverem congelados antes da abertura da REP-S. Qualquer alteração posterior deverá gerar novo identificador de versão e nova execução integral. Resultados obtidos após conhecimento do ground truth serão classificados como pós-hoc e não poderão substituir a análise confirmatória principal.
