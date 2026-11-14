# Guia curto para os próximos casos

## Antes do processamento

Preencha uma revisão por cenário. Se uma informação não existe, use o estado de indisponibilidade previsto; não estime nem complete por conveniência.

### 1. Identificação

- código do cenário;
- código do operador;
- data e hora com fuso `-03:00`;
- revisão 1 sem hash pai; revisões seguintes com o hash e o arquivo congelado da anterior, para conferência do elo imediato;
- em revisão 3 ou superior, mantenha também os ancestrais acessíveis: verificar apenas a revisão anterior não comprova automaticamente toda a cadeia.

### 2. Ponto que inicia o planejamento

- diga se é UPV, UPC, ponto de planejamento ou estimativa aerotransportada;
- registre latitude e longitude em WGS 84;
- registre o horário se existir;
- mantenha separadas a precisão horizontal e o raio de incerteza;
- não marque que a pessoa permanece no ponto.
- use somente ponto cuja fonte esteja identificada e autorizada e cujo horário não seja posterior à avaliação.
- mantenha coerência entre papel e origem: UPV vem de observação direta, UPC de registro operacional e estimativa aerotransportada do respectivo sistema.

### 3. Perfil e pistas

Registre apenas o que foi informado ou observado, sempre com fonte, natureza, horário e confiança. Não use na decisão evidência futura, não autorizada ou sem procedência. Roupa, calçado, equipamentos, água, alimento, abrigo, sinalização e comunicação devem ficar explícitos, inclusive quando indisponíveis. Se um código estruturado do perfil indicar risco, confira se a observação URG do mesmo domínio é compatível; divergência não deve ser resolvida por suposição.

No LOC atual, somente direção observada e destino/lugar familiar espacializado podem alterar o ranking de setores por meio do PERFIL V3. O motor é executado por candidato e não compara candidatos entre si. Os `profile_facts` registrados no caso são descritivos; não entram diretamente no cálculo LOC. Para LOC, use apenas as hipóteses estruturadas e congeladas em cada `profile_input`. Os demais fatos alimentam URG, DET ou revisão humana.

### 4. Ambiente

Registre o instante e a origem de cada observação relevante: clima, iluminação, relevo, vegetação, hidrografia, vias/trilhas, barreiras, acesso, solo e risco ambiental. Não trate observação visual como medição instrumental.

`environment_type`, `travel_mode` e o tempo máximo plausível são classificações assumidas pelo operador da revisão. Não os apresente como inferência automática. O modo de deslocamento não pode contradizer um fato estruturado e elegível de mobilidade. Se duas fontes elegíveis indicarem modos específicos diferentes, não escolha um deles por conveniência: use `MISTO` somente quando a combinação estiver documentada; se a divergência não puder ser resolvida, use `DESCONHECIDO` e encaminhe para revisão.

Se estiverem disponíveis tanto o tempo transcorrido quanto o tempo máximo plausível de deslocamento, o segundo não pode superar o primeiro. Corrija a cronologia ou marque o valor realmente desconhecido como indisponível; não aumente o número apenas para ampliar a área.

### 5. Imagens sem alvo

Para cada arquivo, registre:

- hash;
- formato;
- horário, sua precisão e sua origem;
- solo ou drone;
- posição da câmera em relação ao ponto;
- direção da lente;
- altura acima do solo e sua origem, quando realmente conhecida;
- anotações visuais objetivas.

Quando também houver azimute, confira se ele corresponde à direção da lente. Exemplo: lente apontada para o norte não pode ser registrada com azimute de 180°.

Use para o horário `EXATA`, `APROXIMADA` ou `NAO_DISPONIVEL` e informe se sua origem é `METADADO_ARQUIVO`, `REGISTRO_OPERADOR`, `ESTIMATIVA_OPERADOR` ou `NAO_DISPONIVEL`. Nas fotografias cujo horário foi lembrado apenas aproximadamente pelo operador, preencha `APROXIMADA` e `ESTIMATIVA_OPERADOR`; não atribua esse horário ao metadado do arquivo. Para a altura AGL, registre `TELEMETRIA`, `INFORMADO_PELO_OPERADOR`, `ESTIMATIVA_OPERADOR` ou `NAO_DISPONIVEL`.

Os valores dos pixels permanecem contextuais e não entram numericamente em LOC ou DET. Metadados técnicos validados podem ser usados somente para construir o vínculo geométrico do DET. Uma imagem sem horário pode ser arquivada, mas não sustenta DET. Cada arquivo precisa estar autorizado, anotado, ter captura não posterior à avaliação, ser preservado pelo SHA-256 e possuir anotação do domínio correspondente à dimensão analisada. O fluxo básico confirma apenas hash e estrutura mínima do contêiner (`CONTAINER_STRUCTURE_ONLY`). O subprocesso opcional ImageIO pode decodificar pixels, conferir dimensões e extrair EXIF, GPS e propriedades DJI/XMP permitidas, sem interpretar o conteúdo da imagem. Não reutilize, por exemplo, `TERRENO=PLANO` para concluir visibilidade, compatibilidade do recurso ou qualidade da imagem. Camada pública indica potencial; nunca registre `FAVORAVEL_OBSERVADO` com essa origem. Preencha `target_visible=false` somente quando a vítima-alvo não integrar o Conjunto A. Registre separadamente `incidental_people_present=true`, `false` ou `null` para informar presença de outras pessoas e revisão de privacidade. Esses campos são conferências humanas; esta versão não usa visão computacional.

Nunca corrija um metadado utilizando a anotação do operador, nem altere a anotação para fazê-la coincidir com o arquivo. Preserve os dois valores e suas origens. Se houver conflito de horário, posição, direção ou altura, marque para revisão e não gere footprint automático. Altitude GPS é MSL; `RelativeAltitude` da DJI é relativa à decolagem. Nenhuma delas deve ser registrada como AGL sem regra explícita e documentada.

Fotografia de solo ou oblíqua permanece contexto direcional: posição e direção não demonstram, sozinhas, até onde a câmera enxergou. Somente footprint conservador, ligado por hash à imagem, ao cenário, à revisão e aos setores LOC, pode estabelecer o vínculo imagem-setor. Classifique-o como `APROXIMADO_METADADOS`, `VERIFICADO_CALIBRADO` ou `CONTEXTUAL_INSUFICIENTE`. A primeira classe limita DET a `APTO_COM_RESTRICOES`; a segunda fica reservada a dados calibrados futuros; a terceira não qualifica a evidência. Não preencha vínculo espacial que não foi efetivamente documentado.

Esse subprocesso nunca utiliza a posição verdadeira da vítima, não recebe fotografias com alvo antes da revelação, não altera LOC e não executa visão computacional.

Como o manifesto pode registrar coordenadas e horários exatos da câmera, mantenha o original na pasta restrita de processamento. Para publicação ou apresentação, gere uma versão minimizada, contendo somente os campos necessários para demonstrar o método e o resultado.

### 6. Saídas separadas

- LOC: ranking de setores dentro de cada candidato, com empates permitidos; não existe ranking global entre candidatos;
- URG: prioridade de revisão da ocorrência;
- DET: condição de observação/acesso por setor e modalidade. O setor precisa constar do resultado LOC validado da mesma revisão. Sem vínculo espacial válido, mantenha `REVISAR`; com `APROXIMADO_METADADOS`, o máximo é `APTO_COM_RESTRICOES`.

Não combine as três saídas em um único número.

### 7. Congelamento e revelação

Confirme que a pasta de processamento não contém posição reservada nem imagem com alvo. Congele a entrada e todas as saídas. Somente depois abra o pacote reservado para avaliação.

## Depois de uma busca

Crie um novo evento. Não edite o anterior. Na sequência 1, `previous_event_sha256` fica nulo; nas seguintes, registre o predecessor imediato e forneça seu arquivo para verificação. Preserve em `source_event_sha256` o evento positivo que originou a pista ou o novo ponto.

O evento precisa ter sido registrado antes da avaliação da revisão que o incorpora e congelado antes do congelamento dessa revisão. Para evento 3 ou superior, a conferência isolada do predecessor comprova apenas o elo imediato; mantenha os eventos ancestrais disponíveis para validação da cadeia completa.

O campo `profile_v2_compiled_sha256` é o hash do artefato compilado anterior que serve de entrada ao PERFIL V3. O nome histórico do campo não rebaixa nem renomeia a saída atual. Os hashes de perfil, território, revisão espacial e manifesto visual comprovam os bytes entregues, mas não substituem a conferência semântica dos documentos. `spatial_review_manifest_sha256` identifica o manifesto global no caso; `source_spatial_review_sha256` identifica a revisão específica de cada candidato e deve coincidir entre sua entrada e sua saída.

No contrato LOC v1.1, cada item de `profile_runs` deve conter o par `profile_input` congelada + `profile_result` do mesmo candidato. Antes de executar o PERFIL V3, grave na entrada `source_loc_input_sha256`, calculado sobre a projeção LOC do caso, e `source_case_revision`. A saída deve repetir ambos. Criação e congelamento dessa entrada não podem ocorrer depois do corte temporal do caso. O protocolo confere a trava `loc_engine_lock_v1.json`, os hashes físicos do motor e da configuração, reexecuta o PERFIL V3 e aceita o par somente se a saída reproduzida for exatamente igual à declarada. Mantenha os candidatos em ordem determinística, não crie ranking entre eles, aceite empates de setores pelo método de competição e derive setores válidos somente de `operational_rows`. Não repita identificadores de candidato ou setor. O contrato declara o cegamento; até existir atestação controlada do executor, a revisão humana permanece obrigatória.

Um resultado sem localização mantém o ranking LOC. Duração positiva, cobertura maior que zero, geometria GeoJSON válida, trilha GeoJSON/GPX válida, setores, modalidade, esforço, visibilidade, limitações, autorização e arquivos verificados podem completar o **registro documental/estrutural**. A execução anterior precisa anteceder a busca e os setores percorridos precisam existir em `operational_rows` do LOC validado dessa execução. Contudo, a versão atual ainda não autentica o vínculo entre a cobertura e a geometria dos setores nem a proveniência temporal da trilha. Portanto, o registro negativo ainda não se torna evidência negativa semanticamente elegível e nunca altera LOC.

Se surgir pista positiva, autorizada e com coordenada validada, registre um novo ponto conhecido e execute uma nova revisão ligada por hash à anterior. Para encerrar LOC, forneça a cadeia completa dos eventos desde a sequência 1 e altere `person_location_status` para `CONHECIDA_OPERACIONALMENTE`. Evento conhecido validado com status ainda `DESCONHECIDA` é uma inconsistência: corrija a revisão antes de prosseguir. Pista não autorizada ou cadeia incompleta pode ser arquivada para conferência, mas não pode desligar o processamento LOC.

