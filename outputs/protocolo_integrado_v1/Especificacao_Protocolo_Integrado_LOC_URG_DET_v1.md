# Especificação do Protocolo Integrado Prospectivo LOC/URG/DET v1

## 1. Finalidade

Esta versão transforma as melhorias discutidas após a leitura do material de busca em áreas remotas em um contrato executável para os próximos casos de campo. O protocolo é prospectivo: ele será usado antes de revelar a posição reservada da pessoa-alvo e não modifica o processamento já congelado do URBE-01.

O protocolo organiza três perguntas diferentes:

1. **LOC — Onde concentrar a busca?** Mantém, para cada candidato, o ranking dos setores produzido pelos módulos TERRITORIAL e PERFIL V3, sem ordenar candidatos entre si.
2. **URG — Com que prioridade a ocorrência precisa ser revista?** Expõe fatores de risco e vulnerabilidade por regras de precedência, sem gerar probabilidade clínica.
3. **DET — Quão observável e operacionalmente pesquisável é cada setor por determinada modalidade?** Avalia setor, meio de busca e instante, sem alterar a plausibilidade espacial.

Não existe um escore agregado LOC + URG + DET. A separação evita que uma vítima vulnerável eleve artificialmente a plausibilidade de um setor ou que vegetação densa faça o setor parecer menos provável apenas porque dificulta a observação aérea.

## 2. Base documental e limite de uso

O material `AREAS REMOTAS CSTER.pdf` reforça três elementos aproveitados nesta versão:

- distinção operacional entre UPV, UPC e ponto inicial de busca (p. 31);
- emprego do raio como referência de planejamento, sem confundi-lo com a trajetória efetivamente percorrida (p. 8);
- atualização da área de busca a partir de pistas e vestígios associados a UPV/UPC (p. 38).

O material é útil como referência didático-operacional, mas não apresenta bibliografia final suficiente para transformar suas porcentagens, distâncias ou velocidades em parâmetros quantitativos do modelo. Por isso, esses números não foram incorporados como pesos, limiares ou probabilidades.

A hierarquia de transferência adotada é:

1. dados do próprio protocolo e evidências de campo documentadas;
2. doutrina nacional e regional compatível com o contexto amazônico;
3. referências internacionais apenas como complemento técnico, sem impor perfis, distâncias ou comportamentos de outras regiões.

## 3. Contrato de entrada

O arquivo `entrada_integrada_v1.schema.json` exige:

- identificação pseudonimizada do cenário;
- modo `PROSPECTIVO_CEGO`;
- declaração de ausência de ground truth;
- revisão imutável, com hash da revisão anterior quando aplicável;
- ponto de planejamento com tipologia canônica;
- precisão horizontal separada do raio de incerteza;
- contexto temporal e ambiental;
- fatos do perfil com procedência;
- fotografias do Conjunto A sem pessoa-alvo;
- observações de urgência;
- avaliações de detectabilidade por setor e modalidade;
- referências por SHA-256 aos artefatos dos motores já existentes;
- congelamento canônico por SHA-256.

O hash declarado não é tratado como prova de integridade por si só. Na execução completa, um mapa externo associa cada declaração a um caminho relativo dentro de uma raiz autorizada. O motor lê os bytes, recalcula o SHA-256, bloqueia fuga da raiz e só então registra `VERIFIED`. Sem essa etapa, a saída permanece marcada como `DECLARADO_NAO_VERIFICADO` e exige revisão.

Para os artefatos de perfil, território, revisão espacial e manifesto visual, essa conferência comprova a identidade e a integridade dos bytes, mas o envelope integrado não interpreta automaticamente o conteúdo de contratos externos que ainda não foram formalizados de modo comum. `spatial_review_manifest_sha256`, no caso, identifica o manifesto global do conjunto de revisões; `source_spatial_review_sha256`, em cada entrada PERFIL V3, identifica a revisão espacial específica daquele candidato e pode, legitimamente, ser diferente entre candidatos. Esse vínculo deve ser repetido pela saída correspondente. O campo `profile_v2_compiled_sha256` conserva, por compatibilidade e rastreabilidade, o nome do artefato compilado de entrada produzido na etapa anterior. Esse arquivo é consumido pelo PERFIL V3 e não significa que o resultado corrente seja classificado como Versão 2.

No caso particular do resultado LOC, a integridade dos bytes não comprova, sozinha, que o arquivo foi produzido sem consultar a referência reservada. O contrato `loc_result_v1.schema.json`, na versão `LOC-RESULT-v1.1`, acrescenta uma segunda verificação: versão do contrato, cenário, revisão do caso, hash da projeção de entrada LOC, hashes do código e do arquivo de configuração autorizados do PERFIL V3, declaração de processamento cego e execuções efetivamente produzidas pelo rankeador. A projeção de entrada exclui o próprio hash do resultado e os campos URG/DET; assim, evita dependência circular e preserva a separação entre os módulos. Os `profile_facts` do caso permanecem descritivos e podem apoiar URG ou revisão; eles não entram diretamente no cálculo LOC. Para LOC, o conteúdo autoritativo é o conjunto de hipóteses estruturadas e congeladas em cada `profile_input`.

Cada item de `profile_runs` contém exatamente `candidate_id`, `profile_input` congelada e `profile_result` correspondente. A entrada declara `source_loc_input_sha256`, que precisa coincidir com a projeção LOC do caso, e `source_case_revision`, que precisa coincidir com a revisão corrente. A saída repete esses vínculos. A criação e o congelamento da entrada PERFIL V3 não podem ultrapassar o corte temporal do caso. Essas guardas impedem que uma execução antiga seja reutilizada depois de alterar ponto, tempo, ambiente ou revisão.

O protocolo confere `loc_engine_lock_v1.json`, compara os hashes físicos de `profile_ranker.py` e da configuração autorizada, recalcula o hash canônico da configuração, reexecuta o PERFIL V3 com a entrada incorporada e só aceita o par quando a saída reproduzida é exatamente igual à declarada. Também verifica o `output_sha256` interno e os hashes das fontes vinculadas. A finalidade do envelope não é criar um novo escore: `cross_candidate_ranking=false` é obrigatório. Cada execução ordena apenas os setores pertencentes ao respectivo candidato. Empates seguem a classificação por competição adotada pelo motor, podendo formar sequências como 1, 1, 3. Portanto, ranks iguais são válidos e um rank atribuído em um candidato não pode ser comparado ao rank de outro. Os setores reconhecidos pelo protocolo são derivados exclusivamente de `operational_rows`; `primary_rows`, listas auxiliares ou declarações soltas não ampliam esse conjunto. Para que a referência de um setor seja inequívoca em DET e nos eventos, os identificadores de candidato e de setor devem ser globalmente únicos no envelope.

Arquivo binário ou JSON legado com hash correto é identificado apenas como `INTEGRITY_ONLY`, exige revisão e não fornece setores válidos ao DET. Resultado de revisão anterior, contrato incompleto, configuração divergente, hash interno inválido, setor duplicado ou conteúdo contaminado por ground truth é rejeitado. Ainda assim, `blind_processing=true` é uma declaração contratual, e não prova criptográfica do comportamento de um executor externo. Até a implantação de atestação confiável em ambiente controlado, o protocolo mantém `review_required=true` mesmo quando o contrato LOC declarado cego é formalmente válido.

O contrato também recusa números não finitos (`NaN` e infinitos), estruturas no lugar de valores escalares e padrões textuais típicos de dados pessoais ou coordenadas livres. Esta varredura é uma barreira sintática adicional; a pseudonimização continua dependendo de conferência humana antes do congelamento.

### 3.1 Tipologia do ponto

São mantidos os códigos já empregados pelo PERFIL V2:

| Conceito | Código |
|---|---|
| Último Ponto Visto | `ULTIMO_PONTO_VISTO` |
| Último Ponto Conhecido | `ULTIMO_PONTO_CONHECIDO` |
| Ponto Inicial de Planejamento | `PONTO_INICIAL_PLANEJAMENTO` |
| Estimativa do sistema aerotransportado | `ESTIMATIVA_SISTEMA_AEROTRANSPORTADO` |

O campo `current_presence_assertion` é sempre falso. O ponto informa onde o planejamento começa ou onde existe uma referência anterior; ele não afirma que a pessoa permanece naquele lugar.

Para orientar o processamento, a evidência do ponto precisa estar autorizada, identificada, possuir natureza suficiente e ser anterior ou igual ao instante da avaliação. Uma coordenada futura, uma fonte não autorizada ou uma declaração sem procedência pode ser arquivada fora do envelope cego, mas não pode dirigir o planejamento.

O papel, a semântica e a origem da coordenada formam uma matriz coerente: UPV exige observação direta; UPC exige registro operacional; estimativa aerotransportada exige origem no sistema aerotransportado. Quando o horário é declarado exato para UPV ou UPC, o instante do ponto e o instante da evidência devem coincidir. Códigos de fonte passam pela mesma barreira contra coordenadas livres aplicada aos demais textos.

### 3.2 Precisão e incerteza

O contrato impede a confusão entre:

- `horizontal_accuracy_m`: precisão do sensor ou da coordenada, quando informada por fonte identificável;
- `uncertainty_radius_m`: raio operacional de incerteza utilizado para o planejamento.

Valores indisponíveis permanecem nulos. Zero não é usado como substituto de dado ausente.

Quando `elapsed_minutes` e `maximum_plausible_travel_minutes` estão ambos disponíveis, o tempo máximo plausível de deslocamento não pode exceder o tempo transcorrido. Essa guarda evita transformar um valor fisicamente incompatível com a cronologia conhecida em parâmetro espacial.

Os escalares `environment_type`, `travel_mode` e `maximum_plausible_travel_minutes` são classificações operacionais assumidas pelo operador responsável pela revisão, não medições inferidas automaticamente. Quando existe fato estruturado e elegível de mobilidade, um modo específico contraditório é recusado. Se duas ou mais evidências elegíveis indicarem modos específicos diferentes, o protocolo não permite selecionar silenciosamente apenas um deles: as fontes devem ser reconciliadas. `MISTO` só deve ser empregado quando a combinação de modos estiver sustentada pela evidência; se o conflito permanecer sem solução, o modo operacional deve ficar `DESCONHECIDO` e seguir para revisão.

## 4. Imagens do Conjunto A

Na V1, as fotografias entram como evidência contextual anotada manualmente. Podem documentar terreno, vegetação, obstrução visual, vias, acessos, barreiras e iluminação.

Guardas aplicadas:

- `target_visible=false`, indicando apenas que a vítima-alvo não integra o Conjunto A;
- `incidental_people_present=true`, `false` ou `null`, para registrar separadamente outras pessoas e a revisão de privacidade;
- `numeric_model_input=false`;
- não há visão computacional;
- posição da câmera e direção da lente são conceitos distintos;
- quando direção cardinal e azimute são informados conjuntamente, eles devem ser coerentes (tolerância de 22,5° em torno do rumo cardinal);
- a imagem contextual não altera silenciosamente o LOC;
- fotografias com alvo permanecem no pacote reservado pós-revelação.

O horário da imagem é acompanhado por dois campos distintos: precisão temporal (`EXATA`, `APROXIMADA` ou `NAO_DISPONIVEL`) e origem (`METADADO_ARQUIVO`, `REGISTRO_OPERADOR`, `ESTIMATIVA_OPERADOR` ou `NAO_DISPONIVEL`). Se o horário provém apenas da lembrança ou anotação aproximada do operador, o registro correto é `APROXIMADA` com `ESTIMATIVA_OPERADOR`; não se deve atribuir falsamente o valor ao EXIF ou a outro metadado do arquivo. A altura acima do solo (`altitude_agl_m`) também recebe uma origem: `TELEMETRIA`, `INFORMADO_PELO_OPERADOR`, `ESTIMATIVA_OPERADOR` ou `NAO_DISPONIVEL`.

Uma imagem com horário indisponível pode permanecer no acervo contextual, mas não sustenta conclusão DET. Além disso, `target_visible=false` registra uma conferência humana de que a vítima-alvo não integra o Conjunto A; não afirma ausência de outras pessoas. A presença incidental é declarada separadamente em `incidental_people_present`. Como não há visão computacional nesta versão, esses campos não constituem conclusões automáticas sobre o conteúdo da imagem.

Para participar da revisão DET, não basta a presença do arquivo: a imagem precisa estar autorizada para contexto, ter captura anterior ou igual ao instante avaliado, conter anotação objetiva **compatível com a dimensão avaliada** e ter seu SHA-256 conferido contra os bytes do arquivo. No fluxo básico, a validação permanece limitada a hash e estrutura mínima do contêiner (`CONTAINER_STRUCTURE_ONLY`). O subprocesso opcional descrito a seguir acrescenta decodificação e metadados, mas não interpreta semanticamente os pixels e não constitui visão computacional.

### 4.1 Subprocesso opcional de metadados e vínculo espacial

O subprocesso atua somente sobre o arquivo original preservado por SHA-256. O backend ImageIO decodifica os pixels para conferir a abertura do arquivo e as dimensões declaradas e extrai um conjunto permitido de propriedades EXIF, GPS e DJI/XMP. XML bruto, número de série, nome do proprietário e outros metadados não necessários não são incorporados. A saída registra o identificador e a versão do extrator, o hash do arquivo, a condição de decodificação e a proveniência de cada valor.

Metadados do arquivo e informações do operador são fontes independentes. Ambos são preservados, mesmo quando divergem; o sistema não substitui silenciosamente um pelo outro. Divergência de horário, posição, direção, altura ou identificação bloqueia a geração automática do footprint e encaminha o registro para revisão. A orientação EXIF da matriz não é interpretada como azimute da lente.

As grandezas verticais também permanecem separadas. A altitude GPS é tratada como altitude referida pelo metadado, em relação ao nível médio do mar (MSL). `RelativeAltitude`, quando presente em arquivo DJI, é relativa ao ponto de decolagem. Nenhum desses campos é convertido em altura acima do terreno (AGL) sem uma regra explícita, fonte territorial adequada e registro da transformação. Ausência de AGL não é completada por estimativa implícita.

Fotografias de solo e imagens oblíquas permanecem evidência contextual direcional; posição e rumo, isoladamente, não definem o alcance observado. O vínculo automático com um setor requer footprint conservador e auditável, calculado a partir de dados coerentes e ligado por hash ao mesmo cenário, revisão, arquivo visual e conjunto de setores LOC. Interseção espacial indica aplicabilidade da imagem, não probabilidade de presença da pessoa.

A qualidade do vínculo recebe uma das seguintes classes:

- `APROXIMADO_METADADOS`: footprint conservador derivado de metadados coerentes, porém não calibrados; pode, no máximo, permitir `APTO_COM_RESTRICOES` em DET;
- `VERIFICADO_CALIBRADO`: reservado a uma etapa futura com câmera, geometria e referências calibradas; não é atribuído por simples presença de EXIF/XMP;
- `CONTEXTUAL_INSUFICIENTE`: dados ausentes, conflitantes, de solo/oblíquos sem alcance defensável ou sem footprint auditável; não qualifica DET.

O subprocesso não altera LOC, não acessa ground truth, não processa fotografias com alvo antes da revelação e não realiza detecção ou classificação automática do conteúdo visual. Sua função é somente comprovar a identidade do arquivo, estruturar metadados permitidos e, quando possível, demonstrar a relação espacial entre uma imagem sem alvo e os setores que ela efetivamente representa.

A compatibilidade semântica é explícita e não pode ser inferida apenas do hash ou do tipo de arquivo:

| Domínio anotado ou observado | Dimensão DET que pode sustentar |
|---|---|
| vegetação | visibilidade, acessibilidade e condição ambiental |
| obstrução visual | visibilidade |
| vias e acessos | acessibilidade |
| barreiras | visibilidade e acessibilidade |
| iluminação | visibilidade e condição ambiental |
| terreno/relevo | acessibilidade e condição ambiental |
| recurso operacional | compatibilidade do recurso |
| qualidade da imagem ou atualidade da fonte | atualidade e qualidade |
| clima e risco ambiental | condição ambiental |
| hidrografia | acessibilidade e condição ambiental |

Assim, uma anotação `TERRENO=PLANO` pode contribuir para acessibilidade ou condição ambiental, mas não comprova, sozinha, visibilidade, compatibilidade do recurso ou qualidade/atualidade da evidência. Fatos de perfil e observações de urgência também não são convertidos automaticamente em evidência DET.

Sem um artefato válido produzido pelo subprocesso, imagens, fotografias de solo, observações de campo e registros operacionais apenas contextualizam a revisão e permanecem em `REVISAR`. Um vínculo `APROXIMADO_METADADOS` pode superar a ausência de vínculo espacial, mas impõe o teto `APTO_COM_RESTRICOES`; ele não comprova aptidão irrestrita. A classe `VERIFICADO_CALIBRADO` permanece reservada a dados calibrados futuros. Essa postura permite comparar, futuramente, uma saída T1 sem imagens com uma revisão T2 enriquecida pelo Conjunto A, sem afirmar benefício antes de medi-lo.

## 5. Saída URG

A URG V1 produz uma **prioridade de revisão operacional**, não diagnóstico clínico nem probabilidade de sobrevivência:

- `REVISAO_IMEDIATA`;
- `REVISAO_PRIORITARIA`;
- `REVISAO_PADRAO`;
- `INDETERMINADA`.

As regras são explícitas e versionadas em `catalogo_regras_urg_v1.json`. Informações duplicadas não se acumulam. Evidência vencida, não autorizada ou indisponível não aciona regra. Contradição força abstenção. A ausência de dados nunca é interpretada como baixa urgência.

Fatos do perfil não são transformados por interpretação livre em conclusão clínica. Entretanto, códigos estruturados e previamente definidos de risco, como `DESORIENTADO`, precisam ser reconciliados com a observação URG do mesmo domínio. Se um fato elegível indicar risco e URG o registrar como ausente ou com significado inferior, a saída passa a `INDETERMINADA` e exige revisão humana.

## 6. Saída DET

A unidade de análise é:

> setor × modalidade de busca × instante

Modalidades previstas:

- busca terrestre;
- observação aérea RGB;
- câmera térmica, quando realmente disponível;
- busca fluvial.

Dimensões avaliadas separadamente:

- visibilidade;
- acessibilidade;
- compatibilidade do recurso;
- condição ambiental;
- atualidade e qualidade da evidência.

Saídas operacionais:

- `APTO_A_PLANEJAMENTO`;
- `APTO_COM_RESTRICOES`;
- `REVISAR`;
- `NAO_AVALIADO`.

Uma camada pública, isolada ou combinada a outra fonte, registra apenas `POTENCIAL_CAMADA_PUBLICA`, `INDETERMINADO` ou `CONTRADITORIO`. Ela nunca recebe a categoria `FAVORAVEL_OBSERVADO`, não declara impossibilidade operacional e não modifica o ranking LOC. Evidência de campo ou registro operacional precisa estar autorizada, temporalmente válida, com procedência identificada e domínio compatível com a dimensão avaliada. Evidência visual só supera a condição contextual quando apresenta vínculo espacial válido conforme a Seção 4.1.

Além disso, o `sector_id` de cada avaliação DET deve existir em `operational_rows` de um resultado LOC cujo contrato cego foi semanticamente validado para a mesma revisão do caso. Integridade de bytes sem contrato, ausência do resultado LOC, setor ausente dessas linhas operacionais ou falta de vínculo espacial da evidência mantêm DET em `REVISAR`. Vínculo `APROXIMADO_METADADOS` estabelece o limite superior `APTO_COM_RESTRICOES`; somente `VERIFICADO_CALIBRADO`, quando futuramente implementado com dados calibrados, poderá remover esse teto.

## 7. Registro versionado de busca

O arquivo `evento_busca_v1.schema.json` registra buscas executadas, pistas, atualizações ambientais e novos pontos conhecidos. Todo evento congelado recebe SHA-256 e pode ser ligado à revisão seguinte do caso. O campo `previous_event_sha256` identifica o predecessor imediato (`null` apenas na sequência 1); `source_event_sha256` preserva, separadamente, o evento positivo que originou uma pista ou novo ponto. A saída conserva ambos os vínculos e não substitui o hash de origem pelo hash do evento corrente. Um evento ligado a uma revisão precisa ter sido registrado até o instante de avaliação e congelado até o congelamento daquela revisão. A nova revisão, por sua vez, deve ser cronologicamente posterior ao evento que incorpora.

Na V1:

- “não localizado” não comprova ausência;
- resultado negativo nunca elimina setor;
- resultado negativo nunca reduz escore ou posição no LOC;
- a documentação estrutural da cobertura, isoladamente, não qualifica evidência negativa;
- uma pista positiva, autorizada e georreferenciada pode originar novo ponto conhecido e nova execução;
- a nova execução não sobrescreve a anterior.

Uma busca negativa pode atingir **completude documental/estrutural** quando contém duração real positiva, cobertura maior que zero, geometria da cobertura, trilha, setores, modalidade, esforço, visibilidade, limitações e autorização. Além do hash dos bytes, a geometria deve ser um polígono GeoJSON minimamente válido, a trilha deve ser uma linha GeoJSON ou GPX com coordenadas válidas e a execução anterior precisa apresentar hash lógico íntegro, cenário coincidente e congelamento anterior ao início da busca. Os setores pesquisados devem pertencer aos setores LOC validados dessa execução anterior. O leitor de GPX preserva segmentos desconectados e a análise de cobertura respeita buracos de polígonos, evitando interseções artificiais.

Essa completude documental não é confundida com **elegibilidade semântica**. A versão atual ainda não possui geometria autenticada dos setores para comprovar o vínculo cobertura-setor nem proveniência temporal executável da trilha para comprovar que ela pertence à janela do evento. Por isso, mesmo quando `documentary_search_record_complete=true`, permanecem `search_artifacts_semantically_validated=false`, `search_record_complete=false` e `negative_evidence_eligible_for_human_review=false`. Uma sequência ou um SHA-256 apenas digitado também não comprova a cadeia. Em qualquer estado, o efeito automático em LOC permanece `NONE_V1`.

A verificação do predecessor comprova diretamente apenas o elo imediato. Na revisão 2 ou no evento 2, isso alcança a raiz conhecida. A partir da revisão 3 ou do evento 3, conferir somente o predecessor não prova, por si, todos os ancestrais. Nessa situação, a saída distingue o elo imediato de uma cadeia integralmente verificada e conserva a exigência de revisão humana enquanto os demais ancestrais não forem apresentados e validados. Excepcionalmente, um evento que pretenda encerrar LOC por novo ponto conhecido só é qualificado quando todos os eventos ancestrais necessários, desde a sequência 1, estão presentes e formam uma cadeia temporalmente contínua. Quando essa cadeia confirma uma localização conhecida, o caso deve declarar `person_location_status=CONHECIDA_OPERACIONALMENTE`. A combinação de evento conhecido verificado com status `DESCONHECIDA` é incoerente, bloqueia o encaminhamento automático e precisa ser corrigida antes de continuar ou encerrar LOC.

## 8. Reprodutibilidade e segregação

O motor aplica:

- datas e horas com fuso obrigatório;
- serialização JSON canônica;
- hash SHA-256 de congelamento;
- encadeamento de revisões;
- encadeamento de eventos por predecessor verificado e preservação do evento de origem;
- verificação dos bytes de geometria, trilha e demais artefatos antes de qualificá-los como comprovados;
- preservação dos segmentos GPX e dos buracos dos polígonos nas verificações espaciais;
- trava por hash do motor PERFIL V3 e de sua configuração;
- reexecução determinística de cada par entrada-saída PERFIL V3;
- varredura recursiva contra rótulos de ground truth;
- detecção de alterações após o congelamento;
- IDs únicos;
- saídas determinísticas para entradas iguais.

O firewall textual é complementar. A salvaguarda principal continua sendo a separação física e temporal do pacote de avaliação: a referência verdadeira, as fotografias com alvo e os dados pós-revelação não entram na pasta entregue ao processamento cego.

## 9. Situação desta entrega

Esta implementação é uma **candidata prospectiva v1**. Ela está tecnicamente preparada para receber os próximos casos após a validação da suíte e a revisão do pesquisador antes do primeiro congelamento real. O URBE-01 permanece intacto e não foi reprocessado.

Arquivos executáveis:

- `work/protocolo_integrado_v1/integrated_protocol.py`;
- `work/protocolo_integrado_v1/test_integrated_protocol.py`;
- `work/protocolo_integrado_v1/test_protocol_adversarial.py`;
- `work/protocolo_integrado_v1/test_protocol_cross_module_guards.py`;
- `work/protocolo_integrado_v1/test_schema_contracts.py`;
- `work/perfil_vitima_v3/profile_ranker.py`;
- `work/perfil_vitima_v3/profile_integration.py`.

Artefatos de contrato:

- `entrada_integrada_v1.schema.json`;
- `evento_busca_v1.schema.json`;
- `catalogo_regras_urg_v1.json`;
- `loc_result_v1.schema.json`;
- `loc_engine_lock_v1.json`;
- `config_perfil_quantitativo_v3.json`;
- `perfil_quantitativo_v3.input.schema.json`;
- `perfil_v3_revisao_espacial.schema.json`.

## 10. Critério para avanço

Antes de usar o protocolo nos três novos casos:

1. preencher apenas dados conhecidos e marcar ausências;
2. revisar a classificação de cada observação URG e resolver contradições explícitas;
3. concluir a setorização LOC por candidato, mantendo identificadores de setor globalmente únicos e sem criar ranking entre candidatos;
4. gerar e congelar cada `profile_input` já vinculada ao hash LOC e à revisão do caso, executar o motor autorizado e formar os pares de `profile_runs`;
5. registrar DET por setor e modalidade somente quando houver evidência, mantendo-o em revisão enquanto não existir vínculo espacial autenticado;
6. verificar as fontes, os horários e os arquivos; em revisões ou eventos posteriores, fornecer também o artefato predecessor;
7. congelar a entrada;
8. executar e arquivar a saída;
9. revelar a referência apenas depois de todas as saídas estarem congeladas.

