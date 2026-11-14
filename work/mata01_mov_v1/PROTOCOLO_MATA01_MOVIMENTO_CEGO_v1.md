# Protocolo cego MATA-01 MOV-V v1.0

## Finalidade

Este módulo representa resistência relativa ao deslocamento dentro do domínio direto de 5 km declarado para o cenário `MATA-01`. Ele não localiza a pessoa, não estima probabilidade de presença e não reconstrói uma trajetória. A saída é uma superfície comparativa de custo físico e um conjunto exaustivo de corredores de menor custo para planejamento.

## Entradas autorizadas

- ponto inicial de planejamento: `-0.172222, -51.430278` em WGS 84;
- domínio circular: 5 km, entendido como área de incerteza alta recebida, não como distância percorrida;
- SRTM `S01W052`, aproximadamente 30 m;
- ESA WorldCover 2021 v200, mosaico `S03W054`, 10 m, agregado à grade de 30 m;
- recorte OSM já preservado no projeto, com data-base `2026-08-17T17:01:35Z`;
- contexto T26 e T49, sem conversão automática em velocidade, distância ou isócrona;
- pistas comportamentais registradas apenas para módulo posterior de priorização.

Nenhuma posição declarada do alvo entra na configuração, no código ou nas saídas.

## Grade e custo

A grade usa projeção métrica local AEQD, célula de 30 m e vizinhança D8. Para a aresta entre uma célula `i` e uma vizinha `j`:

```text
C(i→j) = distância(i,j)
         × fator_cobertura(j)
         × fator_declividade(i,j)
         × fator_rede(j)
         × fator_campo(j)
```

O custo acumulado resulta do algoritmo de Dijkstra. A unidade `cost_m_equivalent` é uma medida heurística relativa de esforço. Não corresponde a metros percorridos, minutos, probabilidade, confiança nem chance de localização.

## Cobertura e proxies hídricas

As classes 80 e 90 do WorldCover recebem resistência elevada somente como proxy potencial de água ou área úmida. Elas não confirmam igarapé, profundidade, vazão, solo encharcado ou impossibilidade de travessia. A hidrografia OSM não contém feições no domínio. Essa ausência cartográfica é classificada como dado não disponível no recorte e jamais como condição favorável.

## Rede de deslocamento

O motor executa duas hipóteses paralelas:

1. `H_REDE_DISPONIVEL`: aplica desconto se houver via ou trilha OSM rasterizada;
2. `H_FORA_REDE`: não aplica desconto de rede.

O recorte OSM disponível contém vias dentro dos 5 km. Por isso, `H_REDE_DISPONIVEL` e `H_FORA_REDE` devem permanecer separadas: a primeira testa o efeito do desconto sobre células tocadas pela rede, enquanto a segunda conserva apenas cobertura e relevo. A via mapeada não comprova transitabilidade atual, permanência da pessoa na rede nem prioridade de busca.

## Obstáculos de campo

As fotografias e a descrição indicam possíveis obstáculos, mas ainda não há geometrias de campo válidas para rasterização. Portanto:

- `field_obstacle.records_available=false`;
- `field_obstacle_factor=1` em todas as células;
- o valor 1 significa “sem ajuste espacial aplicável”, não “passagem livre”.

## Tempo

T26 e T49 são revisões temporais do mesmo caso. Sem novas camadas territoriais ou função de mobilidade calibrada, ambas compartilham a mesma superfície física. O motor proíbe transformar o tempo transcorrido em raio, orçamento de custo, distância ou isócrona.

## Corredores

O domínio é dividido apenas para síntese em três anéis iguais e oito direções. Para cada uma das 24 unidades e em cada hipótese BASE, reconstrói-se um caminho de menor custo até o ponto representativo do setor. São 48 linhas predefinidas. Elas são corredores diagnósticos, não rotas observadas, previstas ou recomendadas automaticamente.

O resumo apresenta dois ordenamentos distintos: o posto global combina distância radial e resistência; o posto direcional compara somente os oito setores do mesmo anel. Nenhum desses postos constitui priorização final de busca ou incorpora as pistas comportamentais.

## Limitações obrigatórias

- fatores de resistência ainda não calibrados para marcha humana amazônica;
- cobertura aérea não representa densidade do sub-bosque;
- SRTM não resolve micro-obstáculos;
- OSM incompleto não autoriza inferência de ausência;
- pistas ao Norte e hábito de seguir bordas/igarapés não alteram o MOV-V sem geometria e regra prospectiva;
- nenhum produto pode ser denominado trajetória, probabilidade, área provável ou acurácia.
