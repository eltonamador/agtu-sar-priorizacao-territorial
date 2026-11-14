# Auditoria independente dos parâmetros e das sobreposições — RURAL-01 MOV-V v2

> **Adendo de fechamento.** Esta auditoria registrou o problema existente na primeira execução. Antes do congelamento T4, a configuração principal foi corrigida para neutralizar a penalidade OSM quando a célula já pertence às classes aquáticas ou úmidas 80, 90 ou 95 do WorldCover. A regra multiplicativa anterior foi preservada somente como contrafactual não promovido. Na execução final, 132 células sobrepostas foram desduplicadas; a suíte, o QA e a repetição integral devem ser consultados no ledger T4 para verificar a versão congelada.

## 1. Finalidade e limites

Esta auditoria examina a fundamentação, a rastreabilidade e o comportamento dos parâmetros empregados na superfície de resistência ao deslocamento da pessoa no cenário `RURAL-01`, protocolo `RURAL01-BLIND-MOV-V-v2.0`.

O trabalho foi realizado exclusivamente com arquivos locais do projeto, saídas cegas já produzidas e documentos operacionais constantes do acervo CBMAP. A posição verdadeira da pessoa, fotografias com alvo e qualquer referência posterior à revelação não foram consultadas. Nenhum arquivo do motor, da configuração ou das saídas foi alterado.

O exame distingue três níveis:

1. variáveis e regras com fundamento documental local;
2. escolhas técnicas ou multiplicadores heurísticos, ainda não calibrados;
3. comportamento quantitativo observado na execução cega, sem avaliação de acerto.

## 2. Veredito executivo

O MOV-V v2 possui fundamento documental suficiente para incluir relevo, cobertura vegetal, hidrografia, vias, trilhas e obstáculos na representação da resistência relativa ao deslocamento. Também é metodologicamente adequada a separação entre movimento da pessoa (`MOV-V`), acesso das equipes (`MOV-E`) e detectabilidade (`DET`), bem como a decisão de não converter automaticamente as 14 horas em distância, velocidade ou isócrona.

Entretanto, os valores numéricos de resistência, desconto, severidade e sensibilidade não possuem calibração local documentada. Eles devem continuar identificados como heurísticas de desenvolvimento. A execução é útil para comparação de hipóteses e avaliação de estabilidade, mas não autoriza interpretar `cost-m-equivalent` como tempo, distância realmente percorrida, probabilidade de presença ou alcance fisiológico.

O principal problema quantitativo encontrado é a dupla penalização de hidrografia: 65,7% das células marcadas pela hidrografia OSM também já são classificadas como água ou área úmida pelo ESA WorldCover. Em 131 células, a regra atual combina os fatores `12 × 6 = 72`.

## 3. Fontes examinadas

### 3.1 Arquitetura, protocolo e configuração

- `work/rural01_mov_v2/PROTOCOLO_RURAL01_MOVIMENTO_CEGO_v2_CONGELADO.md`;
- `work/rural01_mov_v2/config_mov_v2.json`;
- `work/rural01_mov_v2/motor_movimento_v2.py`, somente leitura;
- `work/rural01_mov_v2/INVENTARIO_FONTES_RURAL01_MOB_v2.md`.

### 3.2 Linha de base GEO-02–05

- `work/ext_espacial_setores_v1_1/ESPECIFICACAO_METODOLOGICA_SETOR_v1_1.md`;
- `work/ext_espacial_setores_v1_1/config_setorizacao_priorizacao_v1_1.json`;
- `work/ext_espacial_setores_v1_1/motor_setorizacao_priorizacao.py`, somente leitura;
- `outputs/campo_rural01/processamento_cego_v1/atributos_geo_setores.csv`.

### 3.3 Governança do perfil

- `outputs/modulo_perfil_vitima_v3/Especificacao_PERFIL_V3_Quantitativo.md`;
- `outputs/modulo_perfil_vitima_v3/Matriz_Hierarquia_Transferibilidade_Fontes_v3.md`;
- `outputs/modulo_perfil_vitima_v3/Relatorio_Revisao_Amazonia_Mata_v3.md`.

### 3.4 Saídas cegas auditadas

- `outputs/campo_rural01/processamento_movimento_cego_v2/grade_resistencia.csv`;
- `outputs/campo_rural01/processamento_movimento_cego_v2/setores_mov_v2.csv`;
- `outputs/campo_rural01/processamento_movimento_cego_v2/resultado_mov_v2.json`;
- `outputs/campo_rural01/processamento_movimento_cego_v2/relatorio_qa_mov_v2.json`.

### 3.5 Documentos operacionais locais

- Corpo de Bombeiros Militar do Amapá, `BG 072/2022`, p. 5, SHA-256 `57694e9b5ce7fdef01fa4c1ceb68fae76f96b9c1d20728b3467d0aa73a9377d3`;
- Corpo de Bombeiros Militar do Amapá, `BG 209/2023`, pp. 10, 13, 39–40, SHA-256 `f05825dde8dc8a2370457eb5027606d194baefeda8c8ffba3c0e86c8a2538779`;
- `tmp/pdfs/cster/areas_remotas_cster.txt`, extração local do material didático fornecido ao projeto.

## 4. Parâmetros e regras com fundamento documental local

| Elemento | Fundamento encontrado | Uso metodologicamente permitido | Limite |
|---|---|---|---|
| Relevo, vegetação, hidrografia, vias, trilhas e obstáculos | Contexto operacional do projeto, doutrina CBMAP e inventário territorial | Integrar essas variáveis à superfície de resistência | A documentação sustenta a variável e a direção geral do efeito, não o multiplicador numérico |
| Distinção entre circulação acessível e progressão difícil | `BG 209/2023`, p. 40, diferencia busca primária em caminhos, estradas, trilhas e margens de rios de busca avançada em mata fechada e terreno acidentado | Sustentar hipóteses separadas com e sem influência da rede | A classificação refere-se ao planejamento de busca, não à probabilidade de a pessoa usar uma rota |
| Coleta de trilhas, cursos d'água, acessos, tempo, último local e características da vítima | `BG 209/2023`, pp. 10, 13 e 39 | Sustentar campos de entrada, proveniência e revisão humana | Não fornece pesos, velocidades ou probabilidades |
| Aumento de esforço em relevo acentuado, vegetação e locais de difícil acesso | `BG 072/2022`, p. 5, estabelece para instrução de equipes ciclos de 50 min de deslocamento e 10 min de descanso em local plano e sem vegetação, e 40 min de deslocamento e 15 min de descanso em terreno acentuado, vegetado, florestal ou de difícil acesso | Sustentar a direção qualitativa do efeito e um cenário de sensibilidade claramente rotulado | Regra para instrução e segurança de equipes; não pode calibrar diretamente a mobilidade da pessoa desaparecida |
| Grade de aproximadamente 30 m | Resolução efetiva do SRTMGL1 utilizado | Definir a resolução comum e impedir alegação de precisão inferior à grade | Não representa microrrelevo, barrancos, grotas, valas ou taludes estreitos |
| Agregação do WorldCover de 10 m para 30 m | Compatibilização técnica entre a cobertura e o DEM | Aplicar regra determinística ou composição proporcional | A classe não mede transitabilidade do sub-bosque |
| Hipóteses `H_REDE_DISPONIVEL` e `H_FORA_REDE` | Doutrina sobre caminhos e acessos, combinada com a incerteza do regime de rota no caso | Executar separadamente as duas hipóteses | Não fazer média silenciosa nem selecionar uma delas depois de observar a referência verdadeira |
| Não conversão das 14 horas | Política do PERFIL V3 e ausência de função validada de velocidade, marcha ativa, repouso e condição clínica | Preservar o tempo como contexto e urgência | Não derivar distância, custo ou isócrona temporal |
| Ausência de veto absoluto pela cartografia pública | Limitações documentadas do SRTM, WorldCover e OSM | Produzir resistência potencial e alerta | Feição mapeada não comprova condição atual; feição ausente não comprova passagem livre |
| Separação entre `MOV-V`, `MOV-E` e `DET` | Arquitetura consolidada do projeto | Manter saídas independentes | Acessibilidade da equipe ou baixa detectabilidade não devem diminuir automaticamente a plausibilidade de presença |

O raio de `1.500 m` possui fundamento como entrada do cenário, domínio espacial e referência comparável ao processamento v1. Ele não possui, nos documentos auditados, fundamento como distância que a pessoa percorreria em 14 horas.

## 5. Parâmetros heurísticos e provisórios

Os parâmetros abaixo são escolhas transparentes de engenharia, mas não foram calibrados para mobilidade de pessoa perdida no Amapá ou em mata amazônica:

### 5.1 Cobertura do solo

- fatores WorldCover por código: `2,8; 2,4; 1,2; 1,3; 1,1; 1,05; 4; 12; 5; 8; 2`;
- fator-padrão `3,0`;
- expoentes `0,75`, `1,0` e `1,25` dos perfis SUAVE, BASE e FORTE;
- uso da classe majoritária como resistência integral da célula de 30 m.

Os fatores da v2 se aproximam, em várias classes, do inverso dos escores de favorabilidade do GEO-05 v1. Exemplos: cobertura arbórea `1/0,35 = 2,857`, comparada ao fator v2 `2,8`; vegetação herbácea `1/0,80 = 1,25`, comparada a `1,2`; agricultura `1/0,75 = 1,333`, comparada a `1,3`; área úmida `1/0,20 = 5`, igual ao fator v2 `5`. Isso assegura continuidade interna, mas não constitui validação independente.

### 5.2 Rede viária e trilhas

- fator de estrada `0,45`;
- fator de trilha `0,65`;
- tolerância de rasterização `22 m`;
- regra de multiplicação do desconto pela classe WorldCover da mesma célula.

### 5.3 Hidrografia

- severidades `0,35`, `0,65` e `1,0` por classe OSM;
- fatores máximos `4`, `6` e `9`;
- fórmula `1 + severidade × (fator_máximo - 1)`;
- uso da mesma tolerância de `22 m` definida para a rede;
- aplicação do fator à célula próxima da linha, em vez de identificar geometricamente a travessia da aresta.

### 5.4 Relevo

- fórmula `1 + a × |grade| + b × grade²`;
- coeficientes `a`, `b` e limites dos perfis SUAVE, BASE e FORTE;
- tratamento simétrico de subida e descida;
- limiares diagnósticos de `20°` e `35°`.

### 5.5 Agregação e saída

- combinação multiplicativa de cobertura, hidrografia, relevo, rede e campo;
- orçamento de `1.500 cost-m-equivalent`;
- índice setorial `média[exp(-custo acumulado/1500)]`;
- denominação de células abaixo desse orçamento como `reachable` ou “alcançáveis”.

O termo “alcançável” deve ser sempre acompanhado de “sob orçamento heurístico de custo”, pois não representa alcance fisiológico nem distância percorrida em 14 horas.

## 6. Valores do material CSTER que não devem calibrar o RURAL-01

O material didático local contém valores numéricos, porém sem transferibilidade suficiente para o caso:

- a afirmação de que 57% seguem o caminho de menor resistência encontra-se no perfil de crianças de 0 a 3 anos;
- a indicação de localização a 50 m de trilha refere-se a pessoas com demência;
- a divisão de 50% descendo, 20% na mesma elevação e 30% subindo, com distância de 1 a 2,6 km, não apresenta na extração local população, amostra e procedência suficientes;
- o “modelo de mobilidade” é descrito conceitualmente, sem função transferível ao contexto do RURAL-01.

Esses elementos podem apoiar discussão ou formulação de hipóteses, mas não devem entrar na configuração principal nem ser apresentados como base empírica amazônica.

## 7. Achados quantitativos da execução cega

### 7.1 Universo analisado

- células válidas: `7.845`;
- arestas D8 examinadas na auditoria: `61.792`;
- setores: `24`;
- células com fator de cobertura maior que 1: `7.845`;
- obstáculos de campo aplicados: `0`;
- fator de campo: `1` em todo o domínio.

### 7.2 Cobertura do solo

| Código WorldCover | Classe | Células | Proporção |
|---:|---|---:|---:|
| 10 | Cobertura arbórea | 5.857 | 74,66% |
| 30 | Vegetação herbácea | 1.391 | 17,73% |
| 60 | Solo exposto/vegetação esparsa | 6 | 0,08% |
| 80 | Água permanente | 180 | 2,29% |
| 90 | Área úmida herbácea | 411 | 5,24% |

### 7.3 Relevo

As declividades por célula apresentaram:

- mínimo: `0,013°`;
- mediana: `3,324°`;
- percentil 90: `7,006°`;
- percentil 95: `8,251°`;
- percentil 99: `10,362°`;
- máximo: `13,087°`.

Nenhuma célula alcançou os limiares diagnósticos de 20° ou 35°. Apesar disso, a fórmula contínua de relevo gerou multiplicador maior que 1 em aproximadamente `99,165%` das arestas. A mediana do multiplicador de declividade foi aproximadamente `1,150`, e o máximo, `2,941`.

### 7.4 Rede

- células de estrada: `156`, ou `1,99%` do domínio;
- células de trilha: `0`;
- estrada sobre cobertura arbórea: `87` células, ou `55,8%` das células viárias;
- estrada sobre vegetação herbácea: `67` células;
- estrada sobre solo exposto: `2` células.

Na configuração BASE, a combinação da classe arbórea com estrada resulta em `2,8 × 0,45 = 1,26`. A via reduz a resistência relativa à floresta sem via, porém a célula ainda permanece mais resistente que a referência unitária. Isso pode representar uma via degradada ou encoberta, mas também pode ser efeito de escala: uma linha estreita é inserida em célula classificada como árvore.

### 7.5 Hidrografia e sobreposição com cobertura

- células com hidrografia OSM: `201`, ou `2,56%` do domínio;
- todas foram classificadas como `Rio`, severidade `1,0`;
- células hidrográficas também classificadas como água ou área úmida: `132`, ou `65,7%` das células hidrográficas;
- células OSM-rio + WorldCover água: `131`;
- células OSM-rio + WorldCover área úmida: `1`;
- células OSM-rio + WorldCover árvore: `69`.

Consequências na configuração BASE:

- 131 células recebem `12 × 6 = 72` antes do componente de relevo;
- uma célula recebe `5 × 6 = 30`;
- 69 células recebem `2,8 × 6 = 16,8`;
- `1.028` arestas, ou `1,664%`, combinam simultaneamente relevo, hidrografia OSM e classe aquática/úmida.

Não houve célula simultaneamente hidrográfica e viária nesta execução.

### 7.6 Sobreposição setorial com GEO-02–05

Nos 24 setores v1:

- 3 apresentam simultaneamente hidrografia OSM e proporção de água/área úmida;
- 9 apresentam hidrografia e floresta;
- 8 apresentam rede e floresta;
- a correlação de Pearson entre GEO-03 e GEO-05 foi `r = 0,581`.

A correlação não prova duplicação por si só, mas confirma que os componentes não são independentes no cenário.

## 8. Resultado das ablações

As comparações abaixo usam como referência `H_REDE_DISPONIVEL__BASE` e permanecem cegas:

| Ablação | Jaccard do Top-3 | Deslocamento médio de posições | Interpretação |
|---|---:|---:|---|
| Sem cobertura | 0,50 | 1,917 | Componente de maior influência observada sobre o ranking |
| Sem desconto de rede | 0,50 | 1,750 | Influência material da hipótese viária |
| Sem hidrografia | 1,00 | 1,000 | Preserva integrantes do Top-3, embora altere posições internas |
| Sem relevo | 1,00 | 0,417 | Preserva integrantes do Top-3 e produz menor deslocamento médio |

O primeiro colocado permaneceu estável nas ablações examinadas. Essa estabilidade é evidência de robustez interna limitada à configuração e ao caso, não validação operacional ou comprovação de localização correta.

## 9. Riscos de dupla contagem

### 9.1 Hidrografia OSM × WorldCover — risco alto e materializado

O mesmo fenômeno territorial é representado pela linha hidrográfica OSM e pelas classes 80/90 do WorldCover. A multiplicação produz fatores 72 e 30, muito superiores aos demais fatores da grade. Esse é o principal risco identificado.

Além disso, o protocolo declara que a hidrografia deve aumentar o custo quando a aresta cruza ou entra em uma feição. O motor atual rasteriza qualquer célula cujo centro esteja até 22 m da linha e aplica o fator à célula de destino. Consequentemente, deslocamento paralelo à margem também pode ser penalizado, mesmo sem travessia.

### 9.2 Rede × cobertura — risco médio e materializado

A rede reduz o fator da célula, mas permanece multiplicada pela cobertura dominante. Isso pode ser correto quando a via realmente atravessa ambiente difícil, porém pode duplicar a resistência quando o pixel arbóreo apenas encobre cartograficamente uma estrada estreita.

### 9.3 Relevo × cobertura — risco médio de correlação de fonte

Em área florestal, o SRTM pode incorporar parte da resposta do dossel, enquanto o WorldCover aplica nova penalização pela cobertura arbórea. O risco é menor que o hídrico, mas exige cautela na interpretação de pequenas variações de declividade.

### 9.4 MOV-V × GEO-02–05 — risco alto em eventual fusão

O MOV-V utiliza novamente os quatro grupos que já estruturam o ranking territorial v1:

- GEO-02: vias e trilhas;
- GEO-03: hidrografia;
- GEO-04: relevo e declividade;
- GEO-05: cobertura e uso do solo.

Portanto, o resultado MOV-V não deve ser somado ao escore territorial v1 como um quinto componente. As alternativas metodologicamente seguras são:

1. tratá-lo como representação alternativa baseada em conectividade e caminho;
2. substituir, em versão futura explicitamente congelada, o bloco de mobilidade GEO-02–05;
3. apresentar os dois resultados em paralelo, explicando convergências e divergências;
4. desenvolver composição residual que retire previamente dos dois produtos os efeitos duplicados.

## 10. Recomendações de sensibilidade

### 10.1 Controle neutro obrigatório

Executar cenário em que todos os fatores sejam iguais a 1. O custo acumulado deve reproduzir a distância de grade, observada a aproximação D8. Esse controle separa o efeito do algoritmo do efeito dos parâmetros.

### 10.2 Desduplicação hidrografia–cobertura

Comparar, no mínimo:

1. `PRODUTO_ATUAL`: multiplicação de WorldCover e OSM;
2. `MAXIMO`: `max(fator_cobertura, fator_hidro)`;
3. `EXCLUSIVO`: WorldCover representa superfície aquática e OSM atua somente onde não existe classe aquática/úmida;
4. `ARESTAS_DE_TRAVESSIA`: penalidade OSM apenas quando a aresta cruza a geometria hídrica.

Recomenda-se registrar uma ablação específica `SEM_DUPLICACAO_HIDRO_COBERTURA`.

### 10.3 Cobertura

Testar expoentes `0`, `0,5`, `1,0` e `1,5`, além de perturbação individual de ±25% e ±50% nas classes predominantes do caso. Deve-se comparar também classe majoritária com resistência proporcional à composição dos pixels de 10 m.

### 10.4 Rede

Testar os seguintes pares estrada/trilha:

- `1,00/1,00`: sem efeito;
- `0,75/0,85`: desconto fraco;
- `0,45/0,65`: configuração atual, provisória;
- `0,30/0,50`: desconto forte.

Adicionar cenário em que a rede substitui parcialmente a resistência superficial dentro da célula viária, em vez de apenas multiplicá-la.

### 10.5 Hidrografia

Testar fatores máximos `1`, `2`, `4`, `6` e `9`. A tolerância hídrica deve ser independente da tolerância de vias e testada em `15`, `22`, `30` e `45 m`. Nenhuma dessas tolerâncias deve ser apresentada como largura física real do rio.

### 10.6 Relevo

Testar `0×`, `0,5×`, `1×` e `2×` os coeficientes atuais. Os limiares de 20° e 35° devem permanecer apenas diagnósticos, pois nenhuma célula do cenário os alcançou. Uma função direcional distinta para subida e descida somente deve entrar em nova versão após fundamento bibliográfico transferível ou calibração independente.

### 10.7 Métricas de estabilidade

Para cada configuração, relatar:

- estabilidade do Top-1;
- Jaccard do Top-3;
- correlação de Spearman ou Kendall do ranking completo;
- variação média e máxima de posições;
- sobreposição espacial dos corredores;
- área e fração de células dentro do orçamento;
- proporção de células que muda de banda de custo;
- contribuição marginal de cada componente;
- proporção de células sujeitas a sobreposição de fatores.

Mudança do Top-1 entre hipóteses, baixa sobreposição do Top-3, alteração importante causada pela retirada de um único componente ou forte dependência de uma única regra devem conservar o resultado em `REVISAR`. Qualquer limiar numérico de estabilidade deverá ser pré-especificado e rotulado como regra de governança, não como limiar validado.

## 11. Recomendações para congelamento e relato acadêmico

1. Preservar a execução atual como cenário `MULTIPLICATIVO_ORIGINAL`, sem descartá-la.
2. Corrigir ou testar explicitamente a dupla penalização de hidrografia antes de denominar qualquer configuração como principal.
3. Separar a tolerância de rasterização hídrica da tolerância de rede.
4. Manter todos os multiplicadores com o rótulo `HEURISTICA_DESENVOLVIMENTO_NAO_CALIBRADA`.
5. Evitar o termo “área alcançável” sem o complemento “sob orçamento heurístico de custo”.
6. Não selecionar parâmetros com base no desempenho após abertura da posição verdadeira.
7. Não fundir aditivamente MOV-V e GEO-02–05.
8. Manter `MOV-V`, `MOV-E` e `DET` como produtos separados.
9. Preservar a ausência de obstáculos de campo como `NAO_DISPONIVEL`, e não como passagem livre.
10. Apresentar na dissertação a análise de sensibilidade como parte do resultado metodológico, deixando claro que estabilidade interna não equivale a validação operacional.

## 12. Conclusão

A arquitetura do MOV-V v2 representa avanço metodológico relevante porque troca uma favorabilidade média setorial por conectividade e custo acumulado espacialmente explícitos. O modelo também documenta fontes, limitações, hipóteses paralelas, ablações e separação de produtos operacionais.

Sua validade atual é diagnóstica. Os dados locais sustentam quais componentes devem ser considerados, mas não fornecem calibração empírica suficiente para os multiplicadores. A principal providência antes do congelamento é resolver ou tornar explícita a sobreposição hidrografia–cobertura. Em seguida, a robustez deve ser demonstrada por sensibilidade pré-especificada, sem qualquer ajuste orientado pela posição verdadeira.
