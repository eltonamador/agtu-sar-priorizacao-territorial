# Relatório de integração do módulo PERFIL V3

## Veredito

O núcleo quantitativo e o adaptador de proveniência estão **aptos para a montagem de um pacote integrado cego**, mas permanecem como candidatos a congelamento. Não houve aplicação aos novos casos nesta rodada.

## O que o adaptador passou a controlar

1. recalcula o SHA-256 dos bytes reais do compilado V2, do manifesto TERRITORIAL, do ranking, dos polígonos, dos buffers e da revisão espacial;
2. verifica o `compiled_sha256` interno do V2 e exige origem `CONGELADO`, congelamento `VERIFIED`, firewall aprovado e ausência declarada de *ground truth*;
3. vincula ranking e polígonos aos hashes registrados no manifesto, sem depender exclusivamente de caminhos absolutos;
4. cruza cenário, candidato, setor, protocolo, escore, azimutes, classificação, `source_row_hash` e hash da geometria entre CSV, GeoJSON e buffer autoritativo;
5. rejeita setores ausentes, duplicados ou diferentes entre fontes e exige a quantidade declarada no manifesto;
6. aceita somente polígonos simples, fechados, sem buracos, com área positiva e sem auto-interseção;
7. exclui por padrão toda direção ou destino sem revisão espacial congelada;
8. impede que a revisão altere coordenadas, natureza, confiança, azimute ou tolerância do V2;
9. deriva `evidence_group_id` exclusivamente de `source_clue_id`;
10. exige igualdade numérica entre a origem observada de uma direção e o centro autoritativo do candidato;
11. incorpora à entrada V3 o hash dos bytes da revisão espacial usada;
12. recusa pacote não confirmatório, salvo autorização explícita para ensaio diagnóstico, registrada no relatório.

## Estado dos artefatos reais

O workspace contém o compilador e o esquema do PERFIL V2, mas não contém um **compilado V2 real e congelado** dos novos cenários. O pacote TERRITORIAL v1.1 localizado corresponde ao desenvolvimento anterior de 90 buffers e está classificado como não confirmatório. Ele foi utilizado apenas para compreender o contrato dos arquivos, não para produzir resultado dos casos atuais.

Também não foram utilizados os arquivos de avaliação do URBE-01 produzidos após a abertura da referência verdadeira.

## Bloqueadores antes da aplicação

1. produzir o compilado V2 congelado de cada novo cenário sem acesso à posição verdadeira;
2. produzir a revisão espacial lateral, com decisão explícita para cada direção ou destino, e congelá-la;
3. gerar ou selecionar o pacote TERRITORIAL prospectivo correspondente aos candidatos do cenário;
4. executar o adaptador e auditar o relatório de integração;
5. somente então alterar administrativamente o conjunto aprovado para `CONGELADO` e processar o V3;
6. liberar o *ground truth* apenas depois do congelamento das saídas.

## Preservação do foco amazônico

O adaptador não introduz pesos, distâncias ou probabilidades externos. Perfil, ambiente e território permanecem separados. Informações internacionais podem apoiar governança, abstenção e testes, mas não definem o rumo nem os parâmetros espaciais do módulo. Mata, hidrografia, sazonalidade, ramais, trilhas, comunidades, acesso e detectabilidade devem vir do caso e das camadas territoriais da área amazônica analisada.
