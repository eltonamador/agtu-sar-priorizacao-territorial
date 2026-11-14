# Protocolo metodológico cego — RURAL-01 MOV-V v2.0 (congelado antes da revelação)

## 1. Situação e finalidade

Este documento especifica uma evolução prospectiva do processamento territorial do cenário `RURAL-01`. A versão proposta acrescenta uma superfície de resistência ao deslocamento e calcula custo acumulado a partir do ponto inicial, sem consultar a posição verdadeira da pessoa-alvo.

O objetivo não é prever uma trajetória única. O objetivo é representar, de modo reproduzível, que duas posições igualmente distantes em linha reta podem demandar esforços muito diferentes quando separadas por relevo, hidrografia, cobertura do solo, vias ou obstáculos conhecidos.

Esta versão tem situação `CONGELADO_ANTES_DA_REVELACAO`. O congelamento foi autorizado somente após a aprovação da suíte de testes, das portas de qualidade, da repetição integral determinística, da preservação da v1 e da selagem dos artefatos em ledger T4. O pacote territorial v1 permanece intacto e constitui a linha de base circular/setorial para comparação. O congelamento não transforma os parâmetros heurísticos em parâmetros validados e não autoriza interpretação confirmatória.

Identificador proposto: `RURAL01-BLIND-MOV-V-v2.0`.

## 2. Pergunta analítica

> Partindo do ponto inicial autorizado e sem conhecer a posição de avaliação, quais porções do território apresentam menor ou maior resistência relativa ao deslocamento plausível da pessoa, sob hipóteses explícitas sobre uso de vias e travessia de barreiras?

A resposta é expressa como custo de movimento relativo ou `cost_m_equivalent`. Esse valor:

- não é distância realmente percorrida;
- não é duração em minutos;
- não é probabilidade de presença;
- não é detecção da pessoa;
- não constitui ordem automática de emprego operacional.

## 3. Invariantes metodológicos

1. A posição verdadeira, fotografias com alvo e qualquer informação posterior à revelação são proibidas na entrada, configuração, código, testes e resultados pré-congelamento.
2. O ponto inicial é referência de planejamento; ele não afirma que a pessoa permaneceu no local.
3. O raio de `1.500 m` é mantido como domínio comparável ao processamento v1 e como orçamento primário de custo métrico equivalente. O motor v2 não afirma ter derivado esse raio das 14 horas.
4. O intervalo declarado de 14 horas permanece contexto temporal e de urgência. Não será convertido automaticamente em distância ou tempo ativo de marcha, pois faltam velocidade calibrada, períodos de parada, horário da última alimentação/medicação e regra validada para a progressão clínica.
5. Dados ausentes permanecem ausentes. Nenhuma barreira, travessia, ponte, trilha, condição de sub-bosque ou velocidade será inventada.
6. Cartografia pública pode indicar obstáculo potencial, mas não estabelecer veto absoluto nem comprovar transitabilidade atual.
7. Evidência de campo só vale para a geometria, o instante e o domínio efetivamente observados.
8. Toda alteração de parâmetro exige novo identificador de configuração, nova execução integral, novo relatório de QA e novo congelamento anterior à revelação.

## 4. Separação obrigatória das três perguntas

O processamento mantém três produtos distintos:

### 4.1 MOV-V — movimento plausível da pessoa

Representa a resistência relativa encontrada pela pessoa desaparecida. É o único produto calculado neste motor.

### 4.2 MOV-E — acessibilidade da equipe

Representará, em artefato separado, por onde equipes e recursos podem chegar. Uma estrada pode ser muito favorável para MOV-E sem tornar automaticamente a mesma área mais provável para MOV-V.

### 4.3 DET — detectabilidade

Representa a possibilidade de observação por busca terrestre, câmera RGB, sensor térmico ou outro recurso em determinado instante. Dossel denso pode reduzir DET sem reduzir a plausibilidade MOV-V.

É proibido somar MOV-V, MOV-E e DET em um único escore. Uma área pode ter alta plausibilidade de deslocamento, baixa acessibilidade da equipe e baixa detectabilidade aérea. Nesse caso, o sistema deve conservar as três informações e exigir decisão humana.

## 5. Entradas cegas autorizadas para o RURAL-01

### 5.1 Referência espacial

- cenário: `RURAL-01`;
- ponto de planejamento: latitude `0.188611`, longitude `-51.155556`;
- raio comparável: `1.500 m`;
- sistema de origem: WGS 84 (`EPSG:4326`);
- classificação do ponto: ponto inicial de planejamento, com origem declarada pelo pesquisador;
- posição verdadeira: ausente e proibida.

### 5.2 Contexto temporal

- fotografias declaradas em duas sessões: 22/10/2026, aproximadamente 06:10 e 06:22, UTC−03:00;
- desaparecimento declarado 14 horas antes das fotografias;
- intervalo interpretativo: `840 min`;
- horário do registro de ERB/ponto: 21/10/2026 às 14:20, UTC−03:00;
- divergência temporal: o horário do ponto antecede a janela inferida do desaparecimento e não deve ser silenciosamente tratado como o mesmo evento;
- efeito no MOV-V: contexto e alerta de revisão, sem conversão automática em orçamento temporal.

### 5.3 Perfil elegível

O perfil pode definir hipóteses operacionais previamente estruturadas, mas não produzir ajuste livre após observar o resultado. Para esta rodada, são elegíveis apenas:

- deslocamento a pé;
- experiência local declarada;
- possibilidade de seguir cercas, linhas de transmissão ou cursos d'água;
- risco de redução de mobilidade por hipoglicemia, desidratação ou lesão;
- pista declarada de direção Norte e pegadas próximas a cerca rompida.

Esses fatos não autorizam, nesta versão, velocidade numérica, corredor obrigatório nem mudança automática de direção. Cercas e linhas de transmissão só poderão atuar espacialmente se houver geometria identificada, anterior ao corte e com proveniência registrada.

### 5.4 Camadas territoriais permitidas

- relevo: SRTMGL1, aproximadamente 30 m, como fonte primária compatível com o processamento v1;
- cobertura do solo: ESA WorldCover 2021 v200, 10 m, agregada à grade de análise;
- vias e trilhas: recorte OpenStreetMap já empregado pelo projeto, com data de captura registrada no manifesto;
- hidrografia: recorte OpenStreetMap já empregado pelo projeto, com data de captura registrada no manifesto;
- fotografias do Conjunto A: somente como contexto documentado; não comprovam transitabilidade sob o dossel e não entram numericamente sem vínculo espacial e regra congelada;
- observações de campo de obstáculo: não disponíveis para esta primeira execução, salvo se forem formalizadas e congeladas antes do corte.

Camadas opcionais de conferência, como Copernicus DEM GLO-30, MapBiomas ou hidrografia oficial, pertencem à análise de sensibilidade e não podem ser substituídas silenciosamente na execução principal.

## 6. Qualidade e confiança das fontes

Cada célula ou feição deve conservar `source_id`, data/versão, resolução nominal, data de obtenção, transformação aplicada e classe de confiança:

| Classe | Evidência | Efeito permitido |
|---|---|---|
| `CAMPO_VERIFICADO` | observação direta, georreferenciada, autorizada e temporalmente válida | pode elevar resistência local; veto apenas com regra específica e evidência inequívoca |
| `OPERACIONAL_DOCUMENTADO` | registro oficial/operacional com geometria e data | pode condicionar regime ou travessia conforme semântica documentada |
| `CARTOGRAFIA_PUBLICA` | DEM, cobertura, OSM ou base oficial | indica resistência potencial; não comprova condição atual |
| `IMAGEM_CONTEXTUAL` | fotografia aérea ou terrestre sem calibração/footprint suficiente | contextualiza; não altera automaticamente MOV-V |
| `NAO_DISPONIVEL` | ausência ou procedência insuficiente | não pode ser interpretado como favorável |

Conflitos entre fontes são preservados. A fonte mais recente não substitui automaticamente a fonte de maior adequação sem regra pré-especificada.

## 7. Grade comum e pré-processamento

1. Projetar o domínio em sistema métrico local documentado no manifesto. A implementação pode usar AEQD local centrada no ponto inicial, desde que a definição PROJ completa e o eixo `x,y` sejam congelados.
2. Adotar célula de `30 m`, compatível com o DEM primário, sem alegar precisão de obstáculo menor que a resolução efetiva.
3. Recortar o domínio ao círculo comparável de 1.500 m, incluindo borda técnica máxima de uma célula somente para cálculo de vizinhança.
4. Usar alinhamento único de origem, extensão, resolução e máscara para todas as camadas.
5. Agregar a cobertura de 10 m à célula de 30 m por regra determinística registrada; não selecionar apenas o pixel central.
6. Rasterizar vias, trilhas e hidrografia com tolerância explícita. A tolerância não pode ser descrita como largura física real da feição.
7. Tratar a hidrografia rasterizada como proxy de proximidade ou entrada em célula influenciada pela feição. Nesta versão, ela não comprova que uma aresta cruzou geometricamente um curso d'água, nem identifica ponte, vau ou deslocamento paralelo à margem.
8. Preencher lacuna somente quando houver regra autorizada. Lacuna de DEM, cobertura ou proveniência obrigatória invalida a célula e interrompe a execução principal; não recebe fator-padrão favorável.

## 8. Resistência ao deslocamento

### 8.1 Estrutura da aresta

O grafo usa vizinhança D8. Para cada movimento dirigido da célula `i` para a célula vizinha `j`:

```text
C(i→j) = d(i,j) × R_cobertura(j) × R_hidro(i→j)
         × R_relevo(i→j) × R_rede(i→j) × R_campo(i→j)
```

onde `d(i,j)` é 30 m em movimentos ortogonais e `30√2 m` em movimentos diagonais. Todos os fatores são positivos. O custo acumulado é a soma das arestas do caminho de menor custo a partir do ponto inicial. Essa geometria produz distância octil, uma aproximação discreta da distância euclidiana que conserva pequeno viés angular da grade e não deve ser descrita como isotropia contínua perfeita.

A multiplicação evita compensações indevidas entre barreiras. Entretanto, os multiplicadores da primeira rodada são hipóteses de desenvolvimento e devem ser avaliados pelos perfis `SUAVE`, `BASE` e `FORTE`. Há uma exceção obrigatória: quando uma célula com hidrografia OSM já pertence às classes aquáticas ou úmidas 80, 90 ou 95 do WorldCover, o fator hidrográfico permanece igual a 1,0 e a resistência superficial do WorldCover é conservada. Isso impede que duas proxies do mesmo obstáculo sejam multiplicadas automaticamente.

### 8.2 Relevo e anisotropia

O DEM é usado para calcular diferença de altitude, gradiente dirigido e declividade local. Altitude absoluta, isoladamente, não é tratada como obstáculo.

A arquitetura deve registrar separadamente:

- `grade_signed = (z_j - z_i) / d(i,j)`;
- componente de subida: `max(grade_signed, 0)`;
- componente de descida: `max(-grade_signed, 0)`;
- coeficientes de subida e descida;
- limite máximo do fator;
- indicadores diagnósticos de declividade superior a 20° e 35°.

Uma fórmula com `abs(grade_signed)` e coeficientes iguais nos dois sentidos é simétrica quanto ao componente de relevo. Nesse caso, a execução deve declarar `directional_anisotropy_effective=false` apenas para a assimetria calibrada entre subida e descida, e não pode ser descrita como calibrada para essa diferença. O custo total de `i→j` ainda pode diferir de `j→i` porque os fatores de cobertura, rede, água ou campo pertencem à célula de destino. A estrutura dirigida permanece preparada para anisotropia topográfica, mas uma função distinta de subida e descida somente poderá integrar a execução principal quando houver fundamento bibliográfico ou calibração de campo congelados antes da revelação.

Declividades extremas derivadas de DEM de 30 m indicam resistência potencial. Não comprovam, sozinhas, barranco, grota ou passagem impossível.

### 8.3 Cobertura e vegetação

As classes do ESA WorldCover recebem fatores de resistência versionados. Esses fatores representam hipótese geral de cobertura, não densidade de sub-bosque.

Consequentemente:

- `tree cover` não equivale automaticamente a mata intransponível;
- imagem aérea do dossel não comprova passagem livre nem emaranhada no interior;
- vegetação adensada observada em solo só pode modificar células vinculadas à observação;
- o resultado deve incluir `understory_observability=NAO_DISPONIVEL` quando não houver levantamento terrestre válido.

### 8.4 Hidrografia

A hidrografia aumenta o custo quando o movimento entra em célula marcada pela rasterização de uma feição mapeada. Como a marcação usa proximidade do centro da célula à linha OSM, trata-se de proxy de proximidade/entrada, não de teste geométrico de cruzamento. O fator depende da severidade/cartografia, mas não declara impossibilidade.

- ponte, vau ou travessia só reduz resistência quando documentado;
- ausência de ponte no mapa não comprova ausência no terreno;
- feição pública sem confirmação recebe custo potencial, não veto;
- cenário de sensibilidade deve testar resistência hídrica suave, base e forte;
- deslocamento paralelo à margem pode receber penalidade nesta aproximação; essa limitação deve permanecer explícita até eventual versão que teste interseção aresta–linha e travessias documentadas.
- a regra anterior, que multiplicava hidrografia OSM por classe aquática/úmida, será mantida apenas como contrafactual `COM_DUPLICACAO_HIDRO_COBERTURA`; ela não integra a configuração principal.

### 8.5 Vias e trilhas

Vias e trilhas não recebem importância fixa independente do contexto. O motor executa hipóteses paralelas:

| Hipótese | Regra |
|---|---|
| `H_REDE_DISPONIVEL` | vias e trilhas reduzem resistência para a pessoa, sem tornar o corredor obrigatório |
| `H_FORA_REDE` | nenhum desconto de rede é aplicado ao MOV-V; vias continuam disponíveis ao MOV-E |

Quando houver evidência de permanência em via, a primeira hipótese ganha plausibilidade interpretativa. Quando houver saída confirmada, o ponto de saída deverá originar nova revisão e `H_FORA_REDE` será a hipótese principal a partir dele. Sem evidência conclusiva, os resultados permanecem separados. É proibido fazer média silenciosa entre as hipóteses.

Uma futura tipologia operacional deve admitir:

- `NA_VIA`;
- `SAIDA_CONFIRMADA`;
- `FORA_DA_REDE`;
- `DESCONHECIDA`.

No RURAL-01 corrente, o regime permanece `DESCONHECIDA` até que o último ponto e a pista da cerca rompida tenham geometria e procedência suficientes.

### 8.6 Obstáculos observados em campo

Cada registro de campo deverá conter:

- identificador e tipo do obstáculo;
- geometria ou trecho observado;
- data e hora com fuso;
- posição e método de obtenção;
- classe `PASSAGEM_LIVRE`, `DIFICIL`, `MUITO_DIFICIL` ou `SEM_PASSAGEM_OBSERVADA`;
- direção provável de desvio, se efetivamente observada;
- fotografia ou anotação vinculada por hash;
- autor e nível de confiança;
- validade temporal.

`SEM_PASSAGEM_OBSERVADA` não é sinônimo universal de barreira absoluta. Veto exige regra específica e revisão humana.

## 9. Tratamento do tempo de 14 horas

O valor de 14 horas será conservado em `elapsed_hours_context=14`. Nesta versão, o orçamento principal continuará sendo `1.500 cost-m-equivalent`, dentro do mesmo domínio do v1.

A conversão para isócronas em minutos permanece bloqueada porque exigiria, no mínimo:

- função de velocidade por declividade, direção e cobertura;
- parcela de tempo efetivamente caminhado;
- pausas, sono e comportamento de permanência;
- efeito temporal documentado de condição clínica e disponibilidade de alimento/medicação;
- calibração ou fonte transferível ao contexto amazônico.

Se esses elementos forem futuramente aprovados, a conversão deverá aparecer como nova versão, nunca como correção silenciosa da v2.

## 10. Produtos obrigatórios do MOV-V

Para cada hipótese e perfil de sensibilidade, o motor deverá gerar:

1. grade de resistência por componente e resistência combinada;
2. superfície de custo acumulado desde o ponto inicial;
3. predecessor/direção do caminho de menor custo;
4. bandas de custo dentro do orçamento comparável;
5. corredores de menor custo, com largura/tolerância explícita;
6. resumo por setor v1 para comparação, sem substituir a superfície contínua;
7. contribuição de cada componente para interpretação;
8. mapa com ponto inicial, domínio de 1.500 m, resistência, corredores e Top-3 setorial anterior;
9. avisos de fonte, lacuna e extrapolação;
10. manifesto com hashes de entradas, código, configuração e saídas.

Os produtos devem usar rótulos como `MENOR_CUSTO_RELATIVO`, `CUSTO_INTERMEDIARIO` e `MAIOR_CUSTO_RELATIVO`. É proibido usar “provável localização”, “chance” ou percentuais de presença sem modelo probabilístico validado.

### 10.1 Regra congelável para corredores

Para impedir a seleção visual posterior de rotas favoráveis, os corredores serão gerados por uma regra exaustiva: em cada uma das duas hipóteses principais e no perfil `BASE`, reconstruir o caminho Dijkstra entre o ponto inicial e o ponto representativo já congelado de cada um dos 24 setores v1. A saída conterá, portanto, 48 linhas. O campo `v1_top3_member` poderá identificar AP1, AP2 e AP3 apenas para comparação; ele não participa do cálculo.

Cada linha deverá registrar hipótese, setor, célula inicial, célula final, custo acumulado, comprimento geométrico, número de células, algoritmo e hash da configuração. O caminho é uma trajetória de menor custo no modelo, não reconstrução do deslocamento real.

### 10.2 Regra congelável para resumo setorial

Para cada setor e hipótese, agregar todas as células válidas e registrar:

- custo mínimo, mediano, percentil 90 e máximo;
- fração de células com custo acumulado menor ou igual a `1.500 cost-m-equivalent`;
- índice diagnóstico `I_mov = média[exp(−célula_cost/1500)]`;
- cobertura de dados válidos e avisos.

O ranking diagnóstico MOV-V será ordenado por `I_mov` decrescente, depois pela fração dentro do orçamento e, por último, por `sector_id` apenas para apresentação determinística. Empates de valores arredondados compartilham a mesma posição. Quando for exibido “Top-3”, serão incluídos todos os setores com posto compartilhado menor ou igual a 3, ainda que isso produza mais de três linhas. `I_mov` é uma transformação monotônica de custo para facilitar a leitura; não é probabilidade de presença, confiança, acurácia nem frequência esperada. A denominação correta é classificação de acessibilidade física relativa sob determinada hipótese.

## 11. Relação com o ranking territorial v1

O MOV-V v2 não sobrescreve AP1, AP2 e AP3. Ele produz uma segunda leitura espacial, baseada em conectividade e custo do caminho entre o ponto inicial e cada célula.

A comparação pré-especificada deverá mostrar:

- classificação v1 do setor;
- custo mínimo, mediano e percentil de custo das células do setor;
- proporção do setor dentro do orçamento primário;
- presença de corredor de menor custo;
- concordância ou divergência entre v1 e v2;
- hipótese/regime responsável pela divergência.

Uma divergência não significa automaticamente erro. Ela indica que a favorabilidade média do setor e o esforço necessário para alcançá-lo respondem a perguntas diferentes. Como o MOV-V reutiliza vias, hidrografia, relevo e cobertura, ele constitui representação alternativa baseada em caminho. É proibido somá-lo ao GEO-02–GEO-05 como quinto fator, o que duplicaria evidências territoriais.

## 12. Sensibilidade obrigatória

O resultado principal deve ser acompanhado, no mínimo, por:

- hipóteses `H_REDE_DISPONIVEL` e `H_FORA_REDE`;
- resistências `SUAVE`, `BASE` e `FORTE` para cobertura, hidrografia e relevo;
- execução sem hidrografia;
- execução sem cobertura;
- execução sem relevo;
- execução sem desconto de vias;
- contrafactual com a duplicação hidrográfica anterior, identificado como não promovido;
- rotação/alteração do ponto inicial dentro da precisão disponível, somente se essa precisão for documentada;
- fonte altimétrica alternativa, caso disponível e congelada.

Devem ser reportados estabilidade espacial dos corredores, mudança das bandas de custo e concordância de setores. Um resultado que dependa fortemente de uma única hipótese permanece `REVISAR`.

## 13. Controles de qualidade

### 13.1 Dados e geometria

- CRS métrico e ordem das coordenadas verificados;
- raio geodésico e máscara comparados ao v1;
- grade alinhada e sem células duplicadas;
- DEM, cobertura, hidrografia e rede com proveniência e hash;
- cobertura espacial de cada fonte reportada;
- valores ausentes não convertidos em baixa resistência;
- ponto inicial inserido em célula válida e de forma determinística.

### 13.2 Algoritmo

- todos os custos finitos, positivos e reprodutíveis;
- diagonais corrigidas por `√2`;
- custo acumulado do ponto inicial igual a zero;
- custo nunca diminui ao longo da árvore de predecessores;
- caminho reconstruído termina no ponto inicial e não contém ciclos;
- obstáculo mais resistente não reduz o custo da travessia;
- desconto de rede não produz custo zero;
- perfil `FORTE` não gera menor custo que `SUAVE` sob os mesmos dados;
- execuções repetidas geram os mesmos bytes ou o mesmo conteúdo canônico;
- o recibo da suíte registra comando, ambiente, quantidade de testes, aprovações, falhas e hashes dos arquivos verificados;
- o manifesto é validado por existência, tamanho, SHA-256 e hash canônico;
- diferenças de relevo só são denominadas anisotropia topográfica calibrada quando os coeficientes de subida e descida efetivamente diferirem.

### 13.3 Testes sintéticos sem ground truth

Construir superfícies artificiais independentes do RURAL-01:

1. terreno uniforme: custo proporcional à distância;
2. barreira transversal com abertura: corredor deve desviar pela abertura;
3. encosta orientada: a função direcional, quando ativada, deve distinguir subida e descida;
4. rede viária: `H_REDE_DISPONIVEL` deve preferir o corredor, e `H_FORA_REDE` não;
5. rio sem travessia confirmada: custo deve aumentar sem veto absoluto;
6. lacuna de DEM ou WorldCover: execução deve falhar ou invalidar a célula, nunca aplicar resistência favorável;
7. firewall: aliases proibidos em chaves, valores textuais e caminhos devem abortar a execução;
8. empate no corte Top-3: todos os setores com posto menor ou igual a 3 devem ser conservados;
9. manifesto: arquivo ausente, tamanho divergente ou SHA-256 inválido deve reprovar o controle.

### 13.4 Firewall cego

- varredura recursiva de chaves e textos proibidos;
- `ground_truth_used` exatamente `false`;
- ausência de coordenadas reservadas, setor correto, distância à verdade ou fotografia com alvo;
- abertura da referência apenas depois do hash final do pacote;
- qualquer violação aborta a execução.

## 14. Validação antes da revelação

Antes de conhecer a posição verdadeira, somente são permitidas:

- validação estrutural e determinística;
- testes sintéticos de comportamento;
- inspeção de coerência das camadas;
- análise de sensibilidade e ablação;
- comparação metodológica com o buffer/setores v1;
- apreciação cega por especialista sobre plausibilidade operacional, sem acesso à referência.

O especialista poderá verificar se as barreiras e corredores são coerentes com as fontes apresentadas. Não poderá ajustar pesos ou selecionar a hipótese que mais se aproxima de uma posição ainda reservada.

## 15. Avaliação posterior, sem reajuste

Somente depois do congelamento será permitido abrir a posição de avaliação. As métricas já devem estar definidas:

- custo acumulado e percentil de custo da célula de avaliação em cada hipótese;
- banda de custo que contém a posição;
- setor v1 e posição setorial v2 correspondente;
- presença da posição no corredor/banda pré-especificados;
- distância da posição ao corredor mais próximo;
- área abrangida pelas bandas em comparação ao círculo de 1.500 m;
- mudança do posto do setor correto em relação ao v1;
- estabilidade da conclusão nas sensibilidades;
- comparação cega v1 versus v2, sem recalibrar os parâmetros.

Um único cenário constitui estudo de caso diagnóstico. Mesmo que a posição esteja em uma banda favorável, não comprova eficácia geral. Se estiver fora, o resultado é igualmente informativo e deverá ser preservado.

## 16. Congelamento

O congelamento seguirá esta ordem:

1. `T0 — entrada`: congelar ponto, raio, contexto temporal, hipóteses e fontes autorizadas;
2. `T1 — motor`: congelar código, dependências e `config_mov_v2.json` por SHA-256;
3. `T2 — execução`: executar duas vezes em ambiente limpo e comprovar determinismo;
4. `T3 — QA`: concluir todos os testes e registrar falhas/avisos;
5. `T4 — saída`: congelar cada saída e o manifesto final;
6. `T5 — abertura`: registrar data, hora e responsável pela abertura da posição reservada;
7. `T6 — avaliação`: calcular somente as métricas pré-especificadas, sem alterar T0–T4.

O pacote só recebe o status `CONGELADO_ANTES_DA_REVELACAO` quando todas as portas críticas estiverem aprovadas. Avisos não críticos permanecem no manifesto e impedem linguagem confirmatória.

## 17. Portas de aceitação

### Obrigatórias para congelar

- firewall cego aprovado;
- configuração válida e sem parâmetros implícitos;
- fontes e transformações com hashes;
- determinismo aprovado;
- testes sintéticos aprovados;
- outputs completos para as duas hipóteses principais;
- MOV-V separado de MOV-E e DET;
- custo descrito como relativo, não como tempo/probabilidade;
- limitações de sub-bosque e de cartografia pública expostas.

### Impedimentos

- acesso à posição verdadeira antes de T4;
- parâmetro alterado após inspeção do resultado;
- conversão não validada das 14 horas em distância;
- barreira absoluta inferida apenas de cartografia pública;
- uso de fotografia aérea como prova de transitabilidade sob o dossel;
- mistura de acessibilidade da equipe com plausibilidade da pessoa;
- ausência de proveniência ou lacunas tratadas como terreno favorável.

## 18. Limitações assumidas nesta rodada

- não há observação sistemática do sub-bosque;
- cercas, linhas de transmissão, barrancos, grotões, pontes e vaus não estão integralmente mapeados;
- OSM pode estar incompleto ou desatualizado;
- o SRTM de aproximadamente 30 m suaviza feições estreitas;
- o WorldCover classifica cobertura e não transitabilidade;
- as fotografias mostram condições visuais localizadas e não toda a área;
- o estado hídrico do terreno no dia pode divergir da cartografia;
- os multiplicadores de resistência são hipóteses de desenvolvimento;
- as 14 horas não equivalem a 14 horas contínuas de marcha;
- a condição clínica não foi convertida em velocidade.

Essas limitações não impedem o estudo comparativo. Elas determinam o alcance correto da conclusão: o MOV-V v2 testa se a incorporação explícita da resistência territorial produz uma representação mais coerente e auditável do deslocamento plausível do que o círculo homogêneo, sem afirmar localização autônoma da pessoa.
