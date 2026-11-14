# Plano da interface de entrada e segregação do ground truth — PERFIL V2

## Registro da decisão

Fica registrada como requisito do modelo a construção de uma interface guiada para entrada conjunta do ponto inicial, contexto da ocorrência, perfil operacional e pistas da pessoa procurada. A interface ainda não está implementada. O contrato de dados e o leitor qualitativo devem ser estabilizados antes da camada visual, para evitar que a tela cristalize campos ou regras ainda em revisão.

## Objetivo de uso

A interface deverá permitir que um único operador registre o caso sem editar JSON e sem precisar conhecer os nomes técnicos internos. O produto final deverá gerar um pacote compatível com `perfil_vitima_v2.schema.json`, apresentá-lo para conferência em linguagem comum e somente então permitir o congelamento.

## Fluxo mínimo

### Tela 1 — Ocorrência e ponto inicial

- código pseudonimizado do cenário;
- tipo, coordenada, data, hora, fuso e origem do ponto;
- raio ou precisão e sua fonte;
- tempo transcorrido;
- ambiente e meio de deslocamento.

### Tela 2 — Perfil e pistas

- mobilidade e limitações relevantes;
- condição cognitiva, sem converter suspeita em diagnóstico;
- experiência e familiaridade com a área;
- destino, lugar familiar, direção observada, hábito e outras pistas;
- procedência, natureza e confiança de cada informação;
- localização associada somente quando a pista tiver referência espacial real.

Para simplificar o trabalho, a tela poderá herdar uma procedência padrão em vários itens, gerar identificadores automaticamente e recolher os detalhes avançados. “Não disponível” deverá ser uma opção visível e distinta de “não”.

### Tela 3 — Revisão e congelamento

- resumo legível do que entrará no modelo;
- relação de informações que não produzirão efeito espacial;
- alertas de inconsistência ou de dado ausente;
- versão do protocolo e do esquema;
- confirmação da sanitização dos textos;
- geração automática do JSON, manifesto e hash;
- comando de congelamento da entrada.

## Separação obrigatória do ground truth

O *ground truth* não fará parte das três telas. Será mantido em módulo, esquema, arquivo e permissão separados. A sequência operacional será:

1. cadastrar somente a entrada operacional;
2. gerar e conferir o manifesto dos arquivos acessíveis ao processamento;
3. validar o pacote com o firewall;
4. congelar entrada, configuração, código e saída;
5. registrar os candidatos e o ranking produzidos;
6. somente depois liberar a referência verdadeira para avaliação.

O firewall identifica chaves e rótulos proibidos, mas não consegue distinguir uma coordenada verdadeira sem identificação de uma coordenada legítima de pista. Por isso, a segregação por pasta e permissão é o controle principal; a varredura automática é uma proteção adicional.

## Controles que a interface deverá aplicar

- impedir o congelamento se houver contradição entre valor, fonte, natureza e confiança;
- impedir data do ponto posterior à coleta ou congelamento anterior à coleta;
- recalcular o hash do conteúdo canônico, em vez de aceitar um hash digitado;
- rejeitar campos ou rótulos de posição verdadeira;
- alertar para nomes, telefones, documentos e outros dados pessoais em texto livre;
- registrar o operador sem incluir identificação pessoal da vítima;
- permitir abstenção quando não houver evidência suficiente;
- manter registro de versão e trilha de auditoria.

## Situação

- contrato estruturado de entrada: criado;
- leitor qualitativo e firewall: implementados;
- desenho funcional da interface: registrado neste documento;
- interface gráfica: pendente;
- integração quantitativa com o ranking espacial: pendente de formalização e congelamento;
- uso nos três novos casos: somente após o congelamento da V2.

