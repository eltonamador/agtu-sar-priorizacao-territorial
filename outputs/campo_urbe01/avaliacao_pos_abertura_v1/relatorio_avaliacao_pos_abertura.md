# Avaliação pós-abertura — URBE-01

## Controle temporal e metodológico

- referência registrada em: `2026-10-21T14:07:14-03:00` (`America/Belem`);
- origem: coordenada declarada pelo usuário após o congelamento;
- verificação GNSS/EXIF independente: não disponível;
- precisão horizontal da referência: não informada;
- rankings, pesos e setores recalculados: não;
- métodos independentes de identificação do setor: concordantes.

## Posição da referência

- latitude: `0.0024809355844815323`;
- longitude: `-51.07092698392779`;
- distância ao ponto inicial E0: **1518.618 m**;
- azimute a partir de E0: **192.135°**;
- setor: **URBE-01::URBE-01-E0::R02::S**.
- distância à borda setorial mais próxima: **75.4 m**.

A pertença a R02-S é válida para a coordenada declarada. Como a precisão horizontal não foi informada, não é possível excluir mudança de setor caso o erro real da referência exceda 75,4 m.

## Resultado contra os rankings congelados

| Ranking | Posto do setor verdadeiro | Top-1 | Top-3 | Resultado |
|---|---:|---|---|---|
| BASE | 18º | não | não | não coberto |
| PERFIL | 19º | não | não | não coberto |

O ranking PERFIL deslocou o setor verdadeiro do 18º para o 19º posto. Portanto, neste caso, a inclusão do perfil tal como congelada não produziu ganho de ranking.

No setor real, os escores territoriais congelados foram: vias/trilhas **0.946**, hidrografia **0.035**, terreno **0.811** e cobertura do solo **0.794**. O setor recebeu o alerta `BARREIRA_HIDRICA_POTENCIAL_ALTA` e contribuição comportamental ligada à água `Awater = 0.032`. Assim, a boa acessibilidade viária coexistiu com forte penalização hidrográfica, e o perfil congelado não compensou essa combinação.

As três áreas do Top-3 abrangem aproximadamente **2.454 km²**, equivalentes a **12.5%** da área setorizada, mas não contiveram a referência. O setor priorizado mais próximo foi `URBE-01::URBE-01-E0::R02::SW`, a aproximadamente **273.2 m** da referência; proximidade não é contabilizada como acerto Top-3.

## Interpretação

O resultado é negativo para Top-1 e Top-3 nos dois rankings. Ele deve ser preservado integralmente, pois informa que as regras territoriais e o componente comportamental atuais não distinguiram adequadamente o setor real neste cenário urbano. Um caso não permite estimar eficácia geral, mas fornece evidência útil para revisar prospectivamente o módulo comportamental em versões futuras, sem modificar esta rodada.
