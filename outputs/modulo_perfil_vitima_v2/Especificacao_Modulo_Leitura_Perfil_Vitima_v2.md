# Especificação do módulo de leitura do perfil da vítima V2

## Decisão registrada

O modelo passará a receber, em conjunto com o último ponto visto, último ponto conhecido ou ponto inicial de planejamento, um perfil operacional estruturado da pessoa procurada. Esse perfil não será usado para adivinhar sua posição nem para reproduzir estereótipos. Sua função será transformar informações verificáveis sobre mobilidade, condição cognitiva, experiência, hábitos, intenção e destino em hipóteses espaciais explícitas, limitadas e auditáveis.

A posição verdadeira permanecerá fora da entrada. Ela será aberta somente depois do congelamento das saídas, em módulo separado, para avaliação do resultado.

Fica registrado o requisito de desenvolver uma interface simples para essa entrada. A interface deverá orientar uma única pessoa no preenchimento, aceitar informações desconhecidas, registrar a procedência de cada fato e impedir a inclusão do *ground truth* antes da execução.

## Situação do URBE-01

O processamento cego V1 do URBE-01 permanece congelado. A coordenada verdadeira revelada em 21 de outubro de 2026 serve exclusivamente para avaliar aquela saída já produzida. Ela não será usada para escolher regras, pesos, distâncias ou limiares da V2.

O resultado V1 mostrou que o setor verdadeiro ficou em 18º lugar no ranking BASE e em 19º no ranking PERFIL. Esse caso revelou uma deficiência concreta: a regra anterior registrava o perfil narrativo, mas não interpretava seus campos individualmente; além disso, tratava a água ao mesmo tempo como possível atrator e como barreira. A V2 foi projetada para enfrentar essa deficiência prospectivamente, sem reprocessar o URBE-01 como se ainda fosse um teste cego. A correção efetiva somente poderá ser afirmada após a avaliação dos novos casos.

Os três novos pontos deverão ser processados somente depois do congelamento desta V2 e antes da revelação de suas posições verdadeiras.

## Evidências utilizadas

| Fonte | Contribuição admitida | Uso que não será feito |
|---|---|---|
| Manual Operacional de Salvamento Terrestre do CBMMT, 1ª edição | Fundamentar a coleta de idade, tempo de desaparecimento, saúde, terreno, clima, direção e destino; apoiar o uso de vias, rios, referências e vestígios no planejamento | Extrair probabilidades ou pesos que o manual não apresenta |
| Diretriz Operacional nº 30 do CBMSC, 2021 | Estruturar a entrevista: motivação, história, destino, transporte, último avistamento, direção, saúde, comportamento, resistência e familiaridade | Transferir dados pessoais desnecessários para o motor analítico |
| Michels e Domingos, 2021 | Apoiar a seleção de variáveis e hipóteses discutidas no artigo, como ponto inicial, distância, direção, mobilidade, vias, trilhas e locais de encontro compatíveis com o perfil | Converter em probabilidades universais as frequências de 63 ocorrências atendidas por equipes caninas; tratar todas as variáveis da revisão conceitual como resultados empíricos da amostra |
| Marcondes, Souza e Alves, 2022 | Fornecer referência regional do Mato Grosso e categorias observadas em registros do CBMMT entre 2016 e 2022 | Fixar pesos antes da conferência integral das tabelas e da inconsistência entre os resumos em português e inglês |
| Material didático local associado no acervo ao 2º Curso de Busca Terrestre, 2021, com procedência institucional ainda a confirmar | Formular hipóteses operacionais por categoria, inclusive pescador e possível desorientação, e orientar perguntas de triagem | Tratar generalizações didáticas como regra causal, diagnóstico individual ou publicação oficial enquanto a proveniência não for comprovada |
| Formulário preliminar BTer e ARBUS-SAR do acervo local | Complementar os campos de entrevista, o registro do ponto de origem, a cronologia e o uso explícito de “não disponível” | Copiar dados pessoais ou exemplos reais contidos nos arquivos |
| Tabela de Bill Wade | Manter, em módulo separado, uma possível classificação de urgência da resposta | Usar urgência como escore de localização ou priorização espacial |

Fontes públicas consultadas:

- [Manual Operacional de Salvamento Terrestre do CBMMT](https://www.bombeiros.mt.gov.br/documents/18620746/19096055/CBMMT%2B-%2BManual%2Bde%2BSalvamento%2BTerrestre%2B-%2B1%C2%AA%2Bedi%C3%A7%C3%A3o.pdf/2c6f1a69-5572-8bc6-89cd-b0b4ba3a3f72?t=1681418747577)
- [Diretriz Operacional nº 30 do CBMSC e formulário de entrevista](https://documentoscbmsc.cbm.sc.gov.br/uploads/e522bac79c94c05c4818b7a7f8122186.pdf)
- [Michels e Domingos, 2021](https://vigiles.bombeiros.mg.gov.br/index.php/cbmmg/article/download/136/110)
- [Marcondes, Souza e Alves, 2022](https://revistascintilla.cbm.mt.gov.br/scintilla/article/view/7)

Os manuais e formulários institucionais consultados concentram-se em busca terrestre, mata e ambientes rurais ou com características rurais. Eles fundamentam os campos da entrevista, mas não validam automaticamente pesos comportamentais urbanos. O emprego em contexto urbano será tratado como adaptação de projeto e avaliado prospectivamente.

A separação entre atrator, acesso, travessia e barreira, os três rankings, a política de abstenção e o firewall constituem decisões de engenharia testáveis. Não serão apresentados como achados diretamente demonstrados pelas fontes.

## Princípio de funcionamento

O módulo seguirá esta cadeia:

```text
Ponto inicial e incerteza
        ↓
Tempo e capacidade de deslocamento
        ↓
Fatos do perfil com fonte e confiança
        ↓
Hipóteses comportamentais formalizadas
        ↓
Correspondência com elementos geoespaciais
        ↓
Ajuste limitado e explicável do ranking territorial
        ↓
Revisão humana e congelamento da saída
```

Um texto livre nunca será convertido diretamente em peso. Primeiro, o operador preserva a informação original. Depois, confirma sua classificação em um campo estruturado. Somente regras previamente formalizadas poderão afetar o ranking.

## Entradas obrigatórias

### Ponto e tempo

- código pseudonimizado do cenário;
- tipo do ponto: último ponto visto, último ponto conhecido, ponto inicial de planejamento ou estimativa do sistema aerotransportado;
- latitude e longitude em WGS 84;
- data, hora e fuso;
- origem da coordenada;
- precisão ou raio de incerteza, com unidade e fonte;
- tempo transcorrido até o processamento;
- ambiente predominante: urbano, periurbano, rural, mata ou misto.

### Mobilidade e vulnerabilidade

- forma de deslocamento;
- tempo plausível de deslocamento;
- mobilidade normal, reduzida, assistida ou desconhecida;
- limitações físicas ou sensoriais relevantes;
- condição cognitiva observada, relatada, suspeita ou desconhecida;
- uso relevante de medicamento e consequência conhecida de sua ausência, quando autorizado e necessário;
- experiência e familiaridade com a área.

### Intenção, hábitos e pistas

Essas informações serão registradas em uma única lista canônica de pistas, evitando duplicação entre o perfil e o relato:

- destino declarado;
- lugar familiar;
- atividade ou hábito relevante;
- direção efetivamente observada;
- histórico de desaparecimento, quando pertinente;
- tendência relatada de continuar deslocando-se, procurar abrigo, retornar, buscar isolamento ou aproximar-se de determinado elemento;
- local, coordenada ou feição geográfica associada à pista, se identificável.

Cada fato deverá registrar:

- natureza: confirmado, observado, relatado, suspeito, inferido ou não disponível;
- fonte: vítima, familiar, testemunha, registro, operador ou outra;
- data e hora da informação, exatas, aproximadas ou não disponíveis;
- confiança: alta, média, baixa ou não avaliada;
- autorização de uso no protocolo congelado.

## Transformação do perfil em hipóteses espaciais

### Regras admissíveis

1. **Restrição de alcance.** Mobilidade, tempo e obstáculos podem limitar a área plausível. A regra ajusta o alcance, não escolhe uma direção sem indício.
2. **Direção observada.** Só pode orientar um leque ou setor quando sustentada por testemunho, vestígio ou sequência de pontos. “Direção desconhecida” não produz preferência.
3. **Destino identificável.** Um destino declarado pode gerar hipótese espacial quando for possível ligá-lo a um lugar, área ou feição concreta.
4. **Lugar familiar.** Residência anterior, local de trabalho, ponto de pesca ou outro lugar conhecido pode ser considerado quando houver identificação espacial e procedência registrada.
5. **Locais compatíveis.** Estradas, trilhas, edificações, abrigos, margens, vegetação e outras feições podem receber compatibilidade adicional quando a literatura e os fatos do caso sustentarem a relação.
6. **Interação perfil-terreno.** Uma limitação física pode aumentar a relevância de acessos suaves; experiência em mata pode reduzir, sem eliminar, a penalização de áreas mais complexas. A interação deve ser explicitada.

### Regras não admissíveis

- atribuir direção com base apenas em idade, sexo ou diagnóstico;
- converter adjetivos como “difícil” ou “impaciente” diretamente em peso;
- considerar suspeita como diagnóstico confirmado;
- usar informação ausente como zero;
- aplicar uma categoria geral quando os fatos individuais contradizem essa categoria;
- aumentar a nota de uma área sem registrar qual fato e qual feição produziram o efeito;
- usar a posição verdadeira, mesmo indiretamente, para escolher regras ou parâmetros.

### Matriz de interpretação permitida

| Informação recebida | Interpretação admitida | Condição para produzir efeito espacial | Inferência proibida |
|---|---|---|---|
| tempo e mobilidade | restringir ou ampliar o alcance plausível | tempo confiável, modo de deslocamento e regra de alcance congelada | escolher uma direção apenas pela idade ou capacidade física |
| direção observada | formar leque ou preferência angular | origem, fonte, horário, rumo/azimute e tolerância registrados | transformar direção desconhecida em preferência |
| destino declarado | comparar candidatos com o destino | lugar ou feição identificável e acessível | tratar intenção vaga como coordenada certa |
| lugar familiar | testar proximidade e conectividade | local específico, procedência e vínculo documentados | presumir que toda pessoa retornará ao lugar |
| pesca, ilhas ou água | testar margens, acessos e travessias compatíveis | pista contextual e feição espacial concreta; preferência forte somente com destino identificado | favorecer indistintamente todo corpo d'água |
| desejo de isolamento | manter hipótese contextual | só se torna espacial com destino, área ou feição identificável | converter o traço narrativo diretamente em setor remoto |
| desorientação ou possível perda de memória | elevar incerteza, atenção a risco e necessidade de revisão | natureza da evidência preservada; suspeita continua sendo suspeita | atribuir rumo, distância ou padrão universal pelo diagnóstico |
| experiência no ambiente | modular o efeito de dificuldade do terreno | experiência e tipo de terreno correspondentes | tornar áreas difíceis automaticamente preferenciais |
| limitação física ou sensorial | considerar acessibilidade, declive, barreiras e ritmo | limitação funcional relevante e fonte registrada | usar a condição como estereótipo de localização |
| desaparecimentos anteriores | testar padrões documentados do próprio indivíduo | local, trajeto ou comportamento anterior verificável | substituir a ocorrência atual pelo padrão passado |
| medicamento ou gravidade clínica | alimentar avaliação de urgência | consequência conhecida e necessária à operação | usar urgência como probabilidade espacial |

Essa matriz permite que o módulo leia o perfil sem transformar toda informação humana em peso geográfico. Pistas que não satisfizerem a condição de espacialização permanecem no relatório operacional, mas não alteram o ranking.

## Tratamento específico da água

A V2 separará quatro conceitos que a V1 misturou:

1. **água como possível atrator**, por exemplo, destino de pesca declarado;
2. **acesso à margem**, por vias, trilhas, passagens ou terreno caminhável;
3. **travessia disponível**, por ponte, passarela, embarcação ou outro meio documentado;
4. **água como barreira**, quando o deslocamento exige cruzamento sem acesso conhecido.

A proximidade de um corpo d’água não bastará para elevar um setor. A pista deverá ser compatível com o perfil e, quando possível, com um acesso funcional. Da mesma forma, a presença de água não reduzirá automaticamente a hipótese de a pessoa estar na margem.

## Saídas obrigatórias

O sistema produzirá três rankings e uma comparação:

1. **BASE SIMPLIFICADA:** referência construída apenas com geometria, distância ou regra simples previamente declarada;
2. **TERRITORIAL:** resultado das camadas ambientais e de acessibilidade, sem comportamento;
3. **PERFIL:** o mesmo ranking territorial acrescido somente das regras de perfil efetivamente ativadas;
4. **COMPARAÇÃO:** relatório da mudança de posição e de escore de cada setor entre os três rankings.

O rótulo histórico `BASE` do URBE-01 V1 não será renomeado no pacote congelado. Na V2, os nomes acima evitam confundir a referência simplificada com o ranking territorial.

Para cada setor, a saída deverá mostrar:

- escore antes do perfil;
- regras ativadas;
- fatos que sustentaram cada regra;
- nível de confiança aplicado;
- feições espaciais correspondentes;
- contribuição positiva ou negativa;
- escore após o perfil;
- motivo de abstenção ou revisão, quando houver.

Se não houver informação suficiente, o módulo PERFIL deverá abster-se e preservar o ranking territorial, sem simular certeza.

## Requisito da interface

### REQ-INT-PERFIL-01 — Interface de entrada do perfil

Desenvolver interface simples e auditável para registrar o ponto inicial, o tempo, a mobilidade, as vulnerabilidades, a experiência, o comportamento provável, os destinos e as pistas da pessoa procurada, com identificação da fonte, natureza e confiança de cada informação. A interface deverá produzir entrada estruturada e versionada, permitir valores desconhecidos, preservar a procedência dos dados e impedir acesso ou inserção do *ground truth* antes do congelamento das saídas.

O fluxo funcional, os controles e a segregação operacional estão detalhados em `Plano_Interface_e_Segregacao_GT_V2.md`.

### Organização da interface

**Tela 1 — Ocorrência e ponto inicial**

Código, coordenada, tipo do ponto, data/hora/fuso, origem, precisão ou raio, tempo transcorrido, ambiente e meio de deslocamento.

**Tela 2 — Perfil e pistas**

Faixa etária, mobilidade, condição cognitiva, experiência, familiaridade, limitações e pistas repetíveis. Cada item recebe fonte, natureza, horário e confiança. Para reduzir o trabalho do operador, a interface poderá aplicar uma procedência padrão a vários itens e mostrar os detalhes em seção expansível; o JSON final, porém, armazenará a procedência completa de cada fato.

**Tela 3 — Revisão e congelamento**

Resumo do que entrará no cálculo, campos não disponíveis, pistas não espacializáveis, regras ativadas, versão do protocolo e botão “Validar e congelar entrada”. O sistema gera JSON, resumo legível, hash, data/hora e identificação do operador.

**Módulo restrito — Ground truth**

Fica separado das três telas anteriores. Só pode ser aberto depois do congelamento das saídas. A aplicação deverá rejeitar chaves como `ground_truth`, `true_location`, `victim_lat`, `victim_lon` e equivalentes no pacote de entrada.

A declaração `ground_truth_absent=true` não será considerada proteção suficiente. O exportador fará varredura recursiva de chaves proibidas e aliases, impedirá objetos livres dentro dos fatos, examinará campos de texto em busca de rótulos explícitos de referência e produzirá um manifesto do firewall. A separação principal continuará física e lógica: permissões, pasta e esquema próprios para a referência.

## Proteção de dados

O motor não precisa receber nome completo, CPF, endereço residencial, telefone, fotografia identificável ou diagnóstico nominal detalhado. O cenário usará código pseudonimizado. Informações sensíveis originais permanecerão em área restrita e somente os dados necessários ao cálculo serão exportados.

O protocolo definitivo deverá explicitar finalidade do tratamento, pessoas autorizadas, prazo de retenção, descarte e fundamento da autorização. Pseudonimização reduz a exposição, mas não equivale a anonimização.

## Critérios de aceitação da V2

- a desativação do perfil reproduz exatamente o ranking territorial de referência;
- um campo sem regra formalizada não altera o resultado;
- “não disponível” nunca é convertido em ausência confirmada;
- os parâmetros são lidos da configuração, não gravados como números fixos no código;
- água como atrator, acesso, travessia e barreira são variáveis separadas;
- todas as contribuições do perfil são rastreáveis até um fato, uma fonte e uma regra;
- a execução é determinística e reproduzível;
- a comparação BASE SIMPLIFICADA, TERRITORIAL e PERFIL permite isolar o ganho ou a perda do módulo;
- o pacote de entrada não contém a posição verdadeira;
- os valores principais usam vocabulários fechados, e cada fato ou pista possui identificador estável;
- data, hora, disponibilidade e procedência obedecem a regras condicionais de coerência;
- direção observada registra origem, azimute ou direção cardinal, tolerância e forma de observação quando usada espacialmente;
- o pacote congelado registra operador, data de congelamento, versão do esquema e hash;
- o exportador registra a varredura de dados pessoais em campos textuais e exige confirmação de sanitização;
- protocolo, configuração e esquema de entrada são congelados antes dos três novos casos;
- os três casos serão apresentados como validação prospectiva diagnóstica, sem alegação de eficácia geral.

## Sequência de implementação

1. conferir integralmente o artigo regional do CBMMT e concluir a matriz de evidências;
2. transformar as hipóteses admitidas em regras testáveis, sem calibrá-las pelo URBE-01;
3. definir limites conservadores e análise de sensibilidade do ajuste comportamental;
4. implementar o leitor do esquema de entrada e o firewall do *ground truth*;
5. implementar as funções de interação perfil-terreno;
6. produzir explicações e comparação por ablação;
7. executar testes unitários, determinismo e casos-limite;
8. congelar a V2;
9. cadastrar os três novos cenários sem revelar suas posições verdadeiras;
10. executar, congelar e somente depois abrir as referências para avaliação.

## Estado

- pesquisa documental inicial: concluída;
- auditoria do módulo V1: concluída;
- requisito da interface: registrado;
- esquema de entrada V2: criado em arquivo separado;
- leitor/compilador qualitativo do perfil: implementado;
- firewall recursivo do *ground truth*: implementado no leitor qualitativo;
- congelamento verificável: implementado com projeção canônica e validação do hash;
- coerência mínima entre valor, fonte, confiança, autorização e cronologia: implementada;
- testes do leitor qualitativo: 22 testes automatizados aprovados;
- regras quantitativas e parâmetros V2: pendentes de formalização e congelamento;
- interface gráfica: requisito e fluxo definidos; desenvolvimento visual pendente após o congelamento do contrato de entrada;
- aplicação aos três novos pontos: aguardando congelamento da V2.

### Limite do que já está implementado

O leitor atual valida o pacote, rejeita indícios de *ground truth*, preserva a qualidade e a procedência das evidências e converte somente fatos autorizados em hipóteses qualitativas. Ele ainda não altera escores nem rankings. Essa separação é deliberada: as regras quantitativas, seus limites e sua análise de sensibilidade deverão ser definidos antes do acesso aos três novos casos, para impedir ajuste retrospectivo aos resultados desejados.
