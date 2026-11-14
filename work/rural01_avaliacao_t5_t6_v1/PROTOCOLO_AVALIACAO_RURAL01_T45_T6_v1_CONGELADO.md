# Protocolo de avaliação pós-abertura — RURAL-01 T4.5–T6 v1.0

## 1. Identificação e situação

- **Protocolo:** `RURAL01-EVAL-T45-T6-v1.0`
- **Cenário:** `RURAL-01`
- **Situação:** `CONGELADO_ANTES_DA_REVELACAO`
- **Linha de base territorial:** `RURAL01-BLIND-SET-v1.0`
- **Módulo de movimento:** `RURAL01-BLIND-MOV-V-v2.0`
- **Finalidade:** aplicar uma posição de referência somente depois de congelados o método, o código, a configuração, os testes e as saídas T0–T4.

Este protocolo fecha a lacuna entre o congelamento T4 e a abertura T5. Ele especifica, antes de conhecer a posição de avaliação, como associá-la ao domínio, à grade, aos setores, às superfícies de custo e aos corredores já congelados. Nenhuma regra poderá ser escolhida ou reajustada depois da abertura.

O protocolo não contém a coordenada reservada. O arquivo `MODELO_REGISTRO_T5_SEM_COORDENADA.json` registra apenas que a revelação ainda não ocorreu. Data, hora, precisão, equipamento, método de obtenção e autoria que não tenham sido fornecidos permanecerão ausentes; não serão inferidos de fotografias, nomes de arquivo ou contexto narrativo.

## 2. Pergunta de avaliação

> Depois de revelar a posição declarada do alvo simulado, em que medida essa posição é abrangida pelas priorizações territoriais e pelos caminhos de menor custo previamente congelados, e quão estável é essa leitura entre as duas hipóteses e os três perfis de sensibilidade?

A avaliação é diagnóstica e multidimensional. Ela não transforma custo em probabilidade, não reconstrói a trajetória real, não demonstra eficácia geral e não produz uma decisão global de aprovação ou reprovação do modelo. Recibos técnicos podem usar `PASS/FAIL` exclusivamente para informar se esquema, hashes, testes e portas de execução foram satisfeitos; esse estado de QA não é resultado empírico nem julgamento de eficácia.

## 3. Invariantes

1. Os artefatos T0–T4 são somente leitura e devem ser conferidos por SHA-256 antes de qualquer cálculo.
2. A referência só pode ser aberta depois do congelamento deste avaliador, de seus testes e de seu manifesto.
3. É proibido alterar raio, grade, pesos, fatores, rankings, setores, corredores, hipóteses, perfis ou limiares depois da abertura.
4. As hipóteses `H_REDE_DISPONIVEL` e `H_FORA_REDE` permanecem paralelas. Não haverá média, seleção retrospectiva ou promoção da hipótese que produzir o resultado mais favorável.
5. O custo em `cost_m_equivalent` não é tempo, distância percorrida, probabilidade de presença ou nível de confiança.
6. O corredor é uma linha discreta de menor custo na grade. A tolerância definida neste protocolo representa apenas o suporte espacial de uma célula de 30 m; não é largura física de trilha, faixa de busca ou corredor real.
7. O perfil da vítima, inclusive o PERFIL V3, não poderá modificar os resultados territoriais congelados durante T5–T6.
8. Resultado desfavorável, divergente ou não avaliável será preservado e classificado pela taxonomia deste protocolo; não será ocultado, rebatizado como acerto nem usado para recalibração.

## 4. Cadeia temporal

| Marco | Conteúdo | Regra |
|---|---|---|
| T4 | saídas cegas e manifesto MOV-V congelados | concluído e imutável |
| T4.5 | avaliador, configuração, esquema, testes e manifesto congelados | obrigatório antes da abertura |
| T5 | recebimento e abertura controlada da posição | registrar somente dados efetivamente fornecidos |
| T6 | execução das métricas pré-especificadas | sem alterar T0–T4.5 |

O registro T5 em estado `REVELADO_CONGELADO` deverá conter instante real de abertura com fuso, responsável, proveniência, papel da referência e coordenada em WGS 84. Caso a posição seja definida pelo pesquisador para um alvo simulado e não aferida independentemente por GNSS, a denominação será **posição declarada do alvo simulado**, e não “verdade absoluta” nem “coordenada GNSS”.

## 5. Integridade dos insumos congelados

Antes de T6, o avaliador verificará pelo menos:

- `grade_resistencia.csv`;
- `setores_mov_v2.csv`;
- `corredores_mov_v2.geojson`;
- `resultado_mov_v2.json`;
- `setores_rural01.geojson` da v1;
- `ranking_base_rural01.csv` da v1;
- `top3_rural01.json` da v1;
- `config_mov_v2.json`;
- `ledger_congelamento_T4_mov_v2.json`.

Ausência, divergência de hash, duplicidade de identificador ou incompatibilidade de cenário impede o cálculo das métricas dependentes. O avaliador deve registrar `NAO_AVALIAVEL_INTEGRIDADE`, e nunca reconstruir, corrigir ou substituir silenciosamente um insumo.

## 6. Referencial geométrico e tolerâncias

### 6.1 Projeção

Todos os testes métricos serão realizados na projeção azimutal equidistante local já congelada:

```text
+proj=aeqd +lat_0=0.188611 +lon_0=-51.155556 +R=6371008.8 +units=m +no_defs
```

A entrada da referência permanece em `EPSG:4326`, com ordem explícita `longitude, latitude` na transformação. Distâncias e tolerâncias não serão calculadas em graus.

### 6.2 Domínio circular

O raio analítico é `1.500,00 m`. A tolerância numérica é `0,05 m` e não amplia o alcance substantivo do modelo:

- `INTERIOR`: distância radial menor que `1.499,95 m`;
- `BORDA_DOMINIO`: distância radial entre `1.499,95 m` e `1.500,05 m`, inclusive;
- `EXTERIOR_DOMINIO`: distância radial maior que `1.500,05 m`.

A borda é incluída apenas para neutralizar arredondamento e transformação numérica. Uma referência em `EXTERIOR_DOMINIO` recebe distância radial e classificação de cobertura, mas não será extrapolada para uma célula, setor ou custo fora do domínio.

### 6.3 Bordas setoriais

A distância de até `0,05 m` de uma fronteira radial ou angular congelada caracteriza `BORDA_SETORIAL`. Todos os setores adjacentes serão registrados. Para evitar benefício arbitrário, a avaliação utiliza, em cada ranking, o **pior posto numérico** entre os setores adjacentes. Se houver empate no pior posto, o `sector_id` em ordem lexicográfica crescente é usado somente como identificador determinístico; a lista completa de setores limítrofes continua na saída.

Essa regra é aplicada separadamente ao ranking v1 e a cada cenário MOV-V, pois os postos podem diferir entre cenários. A borda não autoriza escolher o setor com melhor resultado.

### 6.4 Associação à grade

A referência elegível no domínio será associada ao centro da célula válida mais próxima por distância euclidiana em AEQD. Empates serão resolvidos, nesta ordem, por menor distância quadrática, menor `row` e menor `col`.

A metade da diagonal da célula de 30 m é:

```text
30 × √2 / 2 = 21,2132034356 m
```

Esse é o limiar substantivo do suporte espacial do *snap*. A tolerância numérica de `0,05 m` é aplicada somente à comparação, sem alterar a interpretação nominal de meia diagonal. Se o centro válido mais próximo exceder `21,2132034356 m + 0,05 m`, a associação será classificada `NAO_AVALIAVEL_SEM_CELULA_ASSOCIAVEL`; o avaliador não buscará uma célula mais distante para fabricar cobertura.

## 7. Custo, percentil e bandas

### 7.1 Universo do percentil

O percentil será calculado separadamente para cada cenário de custo congelado, usando todas as células válidas do domínio que possuam custo finito naquele cenário. Para o custo `c*` da célula associada, será usada a função de distribuição empírica inclusiva:

```text
percentil_custo(c*) = 100 × N(custo ≤ c*) / N(custos finitos e válidos)
```

Percentil menor representa posição relativamente menos custosa. A regra inclusiva conserva os empates. O percentil não é probabilidade de presença, porcentagem de acerto nem confiança.

### 7.2 Bandas em terços do orçamento

O orçamento congelado é `1.500 cost-m-equivalent`. As bandas são:

| Código | Intervalo | Interpretação permitida |
|---|---:|---|
| `B1_ATE_UM_TERCO` | `0 ≤ custo ≤ 500` | primeiro terço do orçamento |
| `B2_ENTRE_UM_E_DOIS_TERCOS` | `500 < custo ≤ 1.000` | segundo terço do orçamento |
| `B3_ENTRE_DOIS_TERCOS_E_ORCAMENTO` | `1.000 < custo ≤ 1.500` | terceiro terço, ainda dentro do orçamento |
| `B4_ACIMA_DO_ORCAMENTO` | `custo > 1.500` | fora do orçamento congelado |
| `NAO_DISPONIVEL` | ausente, inválido ou não finito | não avaliável; não equivale a baixo custo |

Os limites superiores são inclusivos. O custo zero só é admissível na célula-fonte congelada.

### 7.3 Área das bandas

A área será estimada pela contagem de centros de células por banda multiplicada por `900 m²`. A saída também informará:

- a proporção sobre todas as células válidas do domínio;
- a proporção aproximada sobre a área teórica `π × 1.500²`;
- a quantidade e a área estimada de células sem custo válido.

Trata-se de aproximação raster, não de medição cadastral ou área vetorial exata.

## 8. Setor e ranking

### 8.1 Linha de base v1

Serão registrados o conjunto de setores que contém ou toca a referência, o posto conservador conforme a regra de borda, e os indicadores `top1_v1` e `top3_v1`. “Top-3” significa posto congelado menor ou igual a 3, conservando empates se existirem.

### 8.2 MOV-V

Para cada cenário de custo, será recuperado o posto do setor correspondente em `setores_mov_v2.csv`. As duas leituras principais são:

- `H_REDE_DISPONIVEL__BASE`;
- `H_FORA_REDE__BASE`.

Ambas têm o mesmo estatuto. A saída apresentará, lado a lado, custo, percentil, banda, condição dentro/fora do orçamento, posto setorial e participação no Top-3. Uma coluna de diferença `posto_MOV-V − posto_v1` poderá ser exibida apenas como comparação descritiva; valor negativo não prova melhoria causal.

## 9. Corredores congelados

### 9.1 Conjunto principal: Top-3 MOV-V BASE

Para cada hipótese BASE, o conjunto principal contém os corredores que levam aos setores com `mobility_rank_within_buffer ≤ 3` no cenário BASE da própria hipótese, conforme `setores_mov_v2.csv`. A seleção é feita pela junção determinística de `hypothesis_id` e `sector_id` com `corredores_mov_v2.geojson`. Empates de posto no corte são preservados, mesmo que produzam mais de três corredores. Serão calculados:

- distância a cada corredor do Top-3 MOV-V da hipótese;
- distância ao corredor Top-3 MOV-V mais próximo;
- identificador do corredor mais próximo, com desempate lexicográfico;
- indicador de suporte discreto.

A referência é considerada dentro do suporte discreto de um corredor quando a distância à linha for menor ou igual ao limiar substantivo de `21,2132034356 m`, com `0,05 m` usados somente como tolerância de comparação numérica. O indicador significa proximidade compatível com o suporte de uma célula de 30 m. Não significa que a pessoa percorreu a linha, que existe uma trilha física ou que o corredor tenha 42,43 m de largura.

### 9.2 Conjunto secundário comparativo: Top-3 v1

Para cada hipótese BASE, o conjunto secundário contém os três corredores rotulados `v1_top3_member=true`. Ele permite comparar a priorização setorial anterior com a saída principal MOV-V, mas não substitui o conjunto Top-3 MOV-V e não pode ser promovido retrospectivamente quando for mais favorável.

### 9.3 Conjunto diagnóstico: qualquer um dos 24 corredores

A distância ao corredor mais próximo entre os 24 setores de cada hipótese será calculada como diagnóstico terciário. Como há um caminho para cada setor, a proximidade a qualquer uma dessas 24 linhas não constitui acerto de priorização e não poderá substituir os resultados dos conjuntos Top-3 MOV-V e Top-3 v1.

## 10. Sensibilidade, ablações e PERFIL V3

### 10.1 Seis cenários de sensibilidade

A robustez será verificada nos seis cenários formados por:

- duas hipóteses: `H_REDE_DISPONIVEL` e `H_FORA_REDE`;
- três perfis: `SUAVE`, `BASE` e `FORTE`.

Para cada cenário serão informados custo, ECDF inclusiva, banda, orçamento, posto e Top-3. A síntese de estabilidade conservará:

- concordância de orçamento entre os três perfis de cada hipótese;
- concordância de Top-3 entre os três perfis de cada hipótese;
- posto mínimo, máximo e amplitude por hipótese;
- concordância ou divergência entre as hipóteses BASE;
- contagem, de zero a seis, de cenários em que a referência ficou dentro do orçamento;
- contagem, de zero a seis, de cenários em que o setor ficou no Top-3.

Não haverá média dos seis custos, escolha retrospectiva de perfil ou rótulo global de sucesso.

### 10.2 Ablações

`SEM_HIDRO`, `SEM_COBERTURA`, `SEM_RELEVO` e `SEM_DESCONTO_REDE` serão calculadas como análises secundárias. Elas podem indicar sensibilidade a componentes, mas não integram a conclusão principal, não substituem as duas hipóteses BASE e não autorizam novo peso.

O contrafactual `COM_DUPLICACAO_HIDRO_COBERTURA` permanece não promovido e, se exibido, será claramente separado das ablações e dos resultados principais.

### 10.3 Abstenção do PERFIL V3

O PERFIL V3 só poderá ser citado se houver artefato íntegro, compatível com o mesmo cenário e congelado antes da revelação. Se estiver ausente, incompatível, não discriminante ou com `operational_status=ABSTENCAO_PERFIL`, a saída registrará a abstenção e preservará exatamente a leitura territorial. Não será inferida direção comportamental nem aplicada compensação ao resultado espacial.

Mesmo quando elegível, o PERFIL V3 é contexto complementar e prioridade para revisão humana; não altera retrospectivamente custos, bandas, setores, corredores ou a classificação T6.

## 11. Taxonomia de resultados, inclusive negativos

Não existe `PASS/FAIL` global para o resultado empírico. Cada dimensão recebe um estado próprio:

| Dimensão | Estado favorável descritivo | Resultado negativo preservado | Não avaliável |
|---|---|---|---|
| cobertura do domínio | `DENTRO_DOMINIO` ou `BORDA_DOMINIO` | `FORA_ESCOPO_DOMINIO` | `NAO_AVALIAVEL_GEOMETRIA` |
| associação à grade | `CELULA_ASSOCIADA` | `SEM_CELULA_NO_SUPORTE_DISCRETO` | `NAO_AVALIAVEL_GRADE` |
| orçamento MOV-V | `DENTRO_ORCAMENTO` | `NEGATIVO_ALCANCABILIDADE_ACIMA_ORCAMENTO` | `NAO_AVALIAVEL_CUSTO` |
| priorização v1/MOV-V | `SETOR_TOP3` | `NEGATIVO_PRIORIZACAO_FORA_TOP3` | `NAO_AVALIAVEL_SETOR` |
| corredor Top-3 MOV-V | `DENTRO_SUPORTE_DISCRETO_TOP3_MOVV` | `NEGATIVO_CORREDOR_TOP3_MOVV_FORA_SUPORTE` | `NAO_AVALIAVEL_CORREDOR` |
| sensibilidade | `ESTAVEL_NO_CRITERIO` | `NEGATIVO_ROBUSTEZ_INSTAVEL` | `NAO_AVALIAVEL_SENSIBILIDADE` |
| hipóteses | `CONCORDANTES_NO_CRITERIO` | `DIVERGENTES_ENTRE_HIPOTESES` | `NAO_AVALIAVEL_HIPOTESES` |
| integridade | `INSUMOS_VERIFICADOS` | não se aplica | `NAO_AVALIAVEL_INTEGRIDADE` |

Um resultado pode ser favorável em uma dimensão e negativo em outra. Por exemplo, a referência pode estar dentro do orçamento, mas fora do Top-3. A saída deve conservar essa combinação sem criar um escore agregado.

A expressão “resultado negativo” significa apenas que um critério pré-especificado não foi atendido. Ela não autoriza concluir, a partir de um único caso, que o modelo inteiro é inútil, nem permite transformar o critério depois de observado o resultado.

## 12. Dados ausentes e divergências

- Campo ausente será `null` ou `NAO_DISPONIVEL`, conforme o contrato.
- Precisão horizontal ausente não será derivada do modelo do aparelho.
- Horário de abertura será o horário real do ato; não será confundido com o horário da coordenada, da fotografia, do desaparecimento ou do registro de ERB.
- Método e equipamento somente serão preenchidos quando documentados.
- Divergência entre fontes será registrada, não resolvida por conveniência.
- Referência sem proveniência mínima pode ser armazenada, mas recebe `NAO_AVALIAVEL_PROVENIENCIA` para alegações que dependam dessa procedência.

## 13. Produtos T6 obrigatórios

1. registro T5 congelado e seu SHA-256;
2. relatório JSON completo, com resultados por dimensão e por cenário;
3. tabela CSV de métricas das seis sensibilidades e das ablações secundárias;
4. resumo narrativo que mantenha hipóteses separadas e declare os limites;
5. manifesto de execução com hashes de entrada, código, configuração e saídas;
6. recibo dos testes e da verificação de integridade.

A geração do mapa pós-abertura fica explicitamente adiada. Nesta rodada, `map_generated=false`; nenhum mapa da posição reservada integra o pacote obrigatório T6. Uma figura futura somente poderá representar os resultados já calculados e congelados, sem modificar métricas ou seleção de hipóteses.

O relatório não pode usar “posição prevista”, “trajetória encontrada”, “probabilidade de presença” ou “acurácia geral” para descrever estas métricas.

## 14. Portas de execução

### 14.1 Antes de T5

- configuração, esquema, código e testes do avaliador congelados;
- hashes dos insumos T0–T4 verificados;
- modelo T5 sem coordenada validado no estado pré-revelação;
- ausência da posição reservada no pacote T4.5 confirmada.

### 14.2 Antes de T6

- registro T5 no estado `REVELADO_CONGELADO` e válido contra o esquema;
- instante real de abertura posterior ao congelamento T4.5;
- cenário e papel da referência compatíveis;
- SHA-256 do registro T5 calculado;
- nenhuma modificação nos artefatos T0–T4.5.

Se uma porta falhar, o avaliador emitirá estado não avaliável e diagnóstico. Ele não reparará automaticamente o pacote.

## 15. Alcance das conclusões

O RURAL-01 é um estudo de caso prospectivo diagnóstico. A avaliação poderá demonstrar se o caso declarado é ou não abrangido por critérios congelados, como esses critérios divergem entre hipóteses e quanto dependem dos perfis de resistência. Ela não estima sensibilidade populacional, taxa de acerto, generalização para outras áreas ou benefício operacional causal.

O valor científico deste protocolo está em impedir ajuste pós-revelação, preservar também os resultados negativos e tornar auditável a comparação entre uma setorização territorial e uma representação baseada em custo de movimento.
