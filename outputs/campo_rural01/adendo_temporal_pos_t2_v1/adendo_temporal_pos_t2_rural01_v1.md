# Adendo temporal pós-congelamento — RURAL-01

## Correção registrada

O operador informou que o desaparecimento ocorreu **14 horas antes das fotografias**. O intervalo operacional correto passa a ser, portanto, **840 minutos**.

As sessões fotográficas foram declaradas para 22/10/2026 às 06:10 e às 06:22, no fuso America/Belém (UTC−03:00). Como não há associação individual de cada arquivo a uma dessas duas sessões, não se atribui um único horário ao desaparecimento. A derivação temporal válida é o intervalo entre **21/10/2026 às 16:10 e 16:22**.

O registro de 21/10/2026 às 14:20 permanece identificado como horário do ponto inicial ou do registro de ERB. Ele não deve ser interpretado como horário do desaparecimento.

## Efeito no processamento

- o pacote T2 congelado não foi alterado;
- a posição verdadeira continua ausente;
- o Top-3 espacial não foi recalculado nem modificado;
- a classificação de urgência permanece **REVISÃO PRIORITÁRIA**;
- o valor anterior de 1.333,42 minutos fica superado somente para interpretação temporal e deverá ser substituído por 840 minutos em futura revisão do perfil;
- o raio de 1.500 m foi recebido como raio final ajustado pela fonte. Por isso, as 14 horas não são aplicadas novamente ao buffer, evitando dupla contagem do efeito temporal.

## Divergência de metadados preservada

Os metadados embutidos nos arquivos indicam 21/10/2026, ao passo que as sessões foram declaradas pelo operador para 22/10/2026. O relato das 14 horas não permite determinar qual relógio ou associação de arquivos estava incorreto. A divergência permanece documentada para conferência, sem sobrescrita dos valores originais.

## Rastreabilidade

O adendo está vinculado ao manifesto do pacote T2 congelado, ao protocolo integrado, ao manifesto de metadados visuais e ao Top-3 espacial por seus respectivos hashes SHA-256. Os caminhos e hashes completos constam do arquivo JSON deste adendo.
