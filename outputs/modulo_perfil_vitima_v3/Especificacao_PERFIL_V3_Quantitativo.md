# Especificação prospectiva do módulo PERFIL V3 quantitativo

## Estado

**Candidato a congelamento.** Esta versão foi implementada sem acesso às posições verdadeiras dos três novos casos. O URBE-01 não foi usado para escolher hipótese, peso, distância, limiar ou função.

O motor ainda não deve ser aplicado aos três casos até a conclusão da auditoria documental, dos testes e do congelamento conjunto de esquema, configuração, código e manifesto.

## Finalidade

O PERFIL V3 acrescenta ao ranking TERRITORIAL apenas informações comportamentais que já possuam representação espacial explícita. O escore produzido indica prioridade analítica para revisão humana; não é probabilidade de presença, previsão da posição verdadeira nem comando operacional.

## Delimitação quantitativa

Somente duas famílias podem alterar o ranking:

1. **DIREÇÃO:** rumo observado, com azimute, tolerância e candidato de origem documentados;
2. **DESTINO:** destino declarado ou lugar familiar com latitude, longitude, fonte espacial e raio de incerteza registrados.

Permanecem sem peso quantitativo:

- idade e sexo;
- condição cognitiva sem pista espacial própria;
- personalidade, impaciência ou desejo genérico de isolamento;
- histórico de pesca sem local identificável;
- mobilidade, tempo e limitações enquanto não existir regra de alcance externamente sustentada e independente;
- urgência clínica e uso de medicamento;
- qualquer estatística nacional ou internacional que não tenha sido validada para o contexto local.

Essas informações podem permanecer no relatório operacional e orientar a revisão humana, mas não alteram o escore nesta versão.

## Dependências

Para cada setor do mesmo buffer candidato, a entrada deve fornecer:

- identificador único;
- escore TERRITORIAL congelado em `[0,1]`;
- intervalo angular do setor;
- polígono WGS 84 fechado e com área não nula;
- manifesto territorial e compilação qualitativa identificados por SHA-256.

O V3 não recalcula GEO-02, GEO-03, GEO-04 ou GEO-05 e não modifica seus pesos. Também não compara candidatos distintos.

## Qualidade da evidência

A qualidade de cada hipótese é limitada pelo elo mais fraco entre natureza e confiança:

| Nível | Natureza | Confiança | Fator ordinal |
|---|---|---|---:|
| forte | confirmado ou observado | alta | 1 |
| intermediário | relatado | média | 2/3 |
| fraco | suspeito ou inferido | baixa | 1/3 |
| sem efeito | não disponível | não avaliada | 0 |

Formalmente:

`q = min(fator_natureza, fator_confiança)`

O tipo de fonte é preservado como proveniência, mas não recebe nota numérica. Os fatores são níveis ordinais transparentes de engenharia, não estimativas de confiabilidade estatística.

## Deduplicação

Cada informação original recebe `evidence_group_id`. Repetições do mesmo relato são unidas pelo máximo de compatibilidade, sem somar influência. Dentro de uma família, novas cópias da mesma evidência não elevam o peso.

Classificações divergentes de natureza ou confiança dentro do mesmo grupo invalidam a entrada.

Um mesmo `evidence_group_id` não pode aparecer em famílias distintas. Quando um único relato admitir mais de uma interpretação, o operador deve selecionar, antes do congelamento, a regra espacial canônica que melhor representa a evidência. Essa restrição impede que a mesma informação influencie o escore simultaneamente como direção e destino.

## Compatibilidade espacial

### Direção

A compatibilidade corresponde à fração angular do setor coberta pelo leque formado por azimute e tolerância. A regra trata corretamente a passagem por 0°/360° e não inventa decaimento ou distância.

Cada direção inclui `origin_candidate_id`, que deve coincidir exatamente com o `candidate_id` da entrada. Assim, o azimute é aplicado somente aos setores construídos a partir da mesma origem espacial. Setores com início e fim angulares equivalentes, inclusive 0°/360°, são rejeitados como nulos ou ambíguos; um círculo completo não é inferido silenciosamente.

Direções independentes incompatíveis geram alerta de revisão somente quando forem autorizadas, espacializadas e apresentarem `q > 0`. O motor mantém a união das áreas compatíveis e não escolhe silenciosamente uma testemunha.

### Destino ou lugar familiar

O destino é representado por um ponto e por seu raio de incerteza em metros. Para cada setor, o motor realiza uma projeção equiretangular local centrada no destino e atribui compatibilidade binária igual a 1 quando o ponto está dentro do polígono ou quando a distância mínima até sua borda é menor ou igual ao raio informado. Um círculo pode, portanto, ser compatível com mais de um setor. A incerteza não é transformada em peso, decaimento ou probabilidade.

A projeção utiliza raio terrestre médio de 6.371.008,8 m, coordenadas WGS 84 com latitude estritamente entre −90° e 90° e desembrulho sequencial de longitude em relação ao destino. Esse tratamento contempla polígonos locais que cruzem o antimeridiano. Trata-se de aproximação métrica adequada ao domínio de buffers locais da pesquisa amazônica, não de solução geodésica global. O raio terrestre é uma constante geométrica da projeção e não um peso, uma distância comportamental ou um parâmetro transferido de estatística estrangeira.

Se o círculo do destino estiver fora de todo o domínio analisado, ele é excluído com alerta. O sistema não projeta seu centro para a borda nem favorece artificialmente o setor mais próximo.

Se uma incerteza ampla alcançar todos os setores e produzir compatibilidade constante, a hipótese é excluída como não discriminante e o módulo se abstém quando não restar outra evidência elegível. Assim, um raio grande não se converte em vantagem artificial para qualquer setor.

## Agregação

Para cada família, hipóteses repetidas são agregadas sem empilhamento. Entre famílias, a compatibilidade é combinada segundo a qualidade da evidência.

Seja:

- `T_j`: escore TERRITORIAL do setor `j`;
- `C_j`: compatibilidade agregada do PERFIL em `[0,1]`;
- `q_max`: maior nível de evidência ativo;
- `lambda`: influência máxima configurada;
- `lambda_eff = lambda × q_max`.

O escore é:

`S_j = (1 - lambda_eff) × T_j + lambda_eff × C_j`

Assim, uma pista fraca não produz o mesmo efeito que uma observação forte.

## Teto e sensibilidade

- principal: `lambda = 0,10`;
- sensibilidade conservadora: `0,05`;
- ablação TERRITORIAL: `0`;
- estresse fora do teto operacional: `0,15`.

O valor `0,10` é um teto heurístico de engenharia mantido para continuidade prospectiva; não é peso empiricamente validado. O resultado de `0,15` nunca é a recomendação principal.

O método `COMPETITION_RANK`, a comparação em 12 casas decimais, o limiar diagnóstico de margem `0,05` e todas as regras de retorno ao TERRITORIAL por instabilidade são parâmetros de governança fixados na configuração. O motor rejeita qualquer alteração nesses campos, inclusive quando o arquivo continua sintaticamente válido.

## Abstenção

O módulo se abstém quando:

- não existe hipótese autorizada, espacializada e com `q > 0`;
- todos os destinos se encontram fora do domínio;
- a incerteza do destino torna sua compatibilidade constante entre os setores;
- a compatibilidade é constante e não distingue setores.

Em qualquer abstenção, para **todos** os valores de `lambda`:

`S_j = T_j` exatamente.

Não há preenchimento artificial, renormalização silenciosa nem desempate substantivo pelo identificador.

## Alertas de revisão

- destino fora do domínio;
- incerteza de destino não discriminante;
- direções independentes conflitantes;
- Top-1 instável entre `lambda=0,05` e `lambda=0,10`;
- ausência de Top-1 único;
- margem Top-1–Top-2 inferior a `0,05`, apenas como diagnóstico ainda não validado.

## Firewall e integridade

- varredura recursiva de chaves e rótulos de *ground truth* em português e inglês;
- `ground_truth_absent=true` obrigatório;
- entrada somente no estado `CONGELADO`;
- hash da entrada recalculado por projeção canônica;
- hashes das fontes qualitativa e territorial obrigatórios;
- hash da revisão espacial obrigatório quando alguma hipótese é incluída;
- hash da configuração e da saída registrado;
- campos extras rejeitados;
- identificadores validados no motor pelo mesmo padrão declarado no esquema;
- origem da direção vinculada ao candidato da entrada;
- setores com largura angular nula ou ambígua rejeitados;
- polígonos setoriais fechados com área nula rejeitados;
- execução determinística.

O controle principal continua sendo a segregação física e lógica da referência verdadeira. Um firewall textual não identifica uma coordenada secreta sem rótulo.

A configuração pode estar em `CANDIDATO_A_CONGELAMENTO` durante auditoria ou em `CONGELADO` depois da aprovação. O estado efetivamente carregado é registrado na saída.

## Saída diagnóstica e saída operacional

Os resultados de cada valor de `lambda`, inclusive `primary_rows` em `lambda=0,10`, permanecem disponíveis para diagnóstico. A recomendação operacional é registrada separadamente em `operational_rows`.

Se o conjunto Top-1 mudar entre `lambda=0,05` e `lambda=0,10`, o motor define `operational_effect_applied=false`, atribui `operational_status=REVISAR_INSTABILIDADE` e devolve em `operational_rows` exatamente o ranking TERRITORIAL. Portanto, uma inversão sensível ao peso heurístico não é promovida automaticamente a recomendação de campo.

## Sensibilidade e ablação complementares

Antes do uso nos três casos, o protocolo integrado deverá também executar:

- setorização S12, S24, S36 e rotação de meio setor;
- conjuntos de pesos territoriais já registrados no módulo espacial;
- direção isolada, destino isolado e retirada de cada família;
- estabilidade do Top-1, sobreposição do Top-3, margem e deslocamento de posições.

Essas variações pertencem aos módulos territoriais existentes; o V3 registra a dependência, mas não as recalcula internamente.

## Critérios de aceitação

- `lambda=0` reproduz o TERRITORIAL exatamente;
- ausência de pista ou incerteza que não discrimina setores não cria efeito;
- duplicação do mesmo grupo não altera o resultado;
- uma pista fraca produz influência menor que a mesma pista forte;
- famílias não autorizadas são rejeitadas;
- destino externo não é projetado para a borda;
- o raio de incerteza é tratado geometricamente e uma cobertura não discriminante leva à abstenção;
- direção com origem diferente do candidato é rejeitada;
- setor de largura angular nula é rejeitado;
- polígono setorial de área nula é rejeitado;
- alteração dos parâmetros decisórios do ranking é rejeitada;
- conflito direcional ignora hipóteses inelegíveis;
- instabilidade do Top-1 mantém resultados diagnósticos, mas restaura exatamente o TERRITORIAL na saída operacional;
- adulteração após congelamento é detectada;
- *ground truth* é rejeitado;
- repetições produzem bytes e hashes idênticos;
- configuração, esquema e motor permanecem separados do V1 e do V2.

## Limites de validade

- a aplicação permanece diagnóstica e prospectiva;
- três casos não demonstram eficácia geral;
- resultados estrangeiros não são assumidos como equivalentes à Amazônia, mata ou área urbana de Macapá;
- setores radiais não representam integralmente redes urbanas ou corredores reais de deslocamento;
- o módulo ranqueia setores dentro de um único buffer, não múltiplos candidatos globais;
- mudanças após a abertura das posições verdadeiras exigirão nova versão e conjunto independente de avaliação.

## Integração antes da aplicação

O adaptador V2 + TERRITORIAL → V3 foi implementado separadamente. Ele recalcula o SHA-256 dos arquivos reais, confere o hash canônico interno do compilado V2, verifica os arquivos contra o manifesto territorial e cruza CSV, GeoJSON e buffer autoritativo. Também rejeita polígonos com buracos, área nula, vértices não consecutivos repetidos ou auto-interseção.

Direções e destinos não recebem complementação automática. A inclusão exige revisão espacial estruturada e congelada, vinculada aos hashes exatos do V2 e do manifesto territorial. O `evidence_group_id` vem exclusivamente do `source_clue_id` do V2. Para direção, a coordenada de origem do V2 deve ser numericamente idêntica ao centro autoritativo do candidato; para destino, as coordenadas vêm do V2 e o sidecar fornece apenas incerteza e procedência. O SHA-256 do sidecar é incorporado ao pacote V3 congelado.

Não existe ainda, no workspace, um compilado V2 real dos novos casos. Portanto, o adaptador está validado por testes sintéticos, mas a cadeia real ainda aguarda a produção do compilado V2 e da revisão espacial cegos. Essa ausência é um bloqueador de aplicação, não uma falha do adaptador.
