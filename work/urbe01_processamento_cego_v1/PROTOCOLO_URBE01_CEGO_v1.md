# Protocolo congelado URBE-01 — processamento cego v1.0

## Finalidade

Este protocolo executa a setorização e a priorização territorial do cenário URBE-01 antes da abertura de qualquer posição de referência. O resultado é diagnóstico, não confirmatório e sujeito à revisão humana.

## Entrada autorizada

- protocolo de origem: `URBE-SOURCE-RADIUS-v1.0`;
- ponto recebido: `URBE-01-E0`;
- latitude estimada: `0.015833`;
- longitude estimada: `-51.068056`;
- raio informado pela fonte: `2.500 m`;
- data e hora declaradas na Ficha 3: `20/10/2026, 18:17 GMT-3`;
- situação: `REVISAR`;
- elegibilidade confirmatória: `false`;
- controle obrigatório: `ground_truth_used=false`.

O raio é tratado como dado de origem. Ele não é recalculado nem ajustado a partir de uma posição conhecida posteriormente.

O registro de entrada deste pacote foi materializado a partir dos valores declarados pelo pesquisador na Ficha 3. Não foi importado diretamente de um sistema externo; por isso, a data e a hora permanecem identificadas como declaração ainda não verificada por metadados independentes.

## Setorização

O polígono circular do raio recebido é dividido em 24 setores: três anéis de áreas teóricas iguais e oito direções. A geometria é construída pelas funções científicas do motor `EXT-ESP-SET-v1.1`. Não se aplica preferência direcional nem penalidade por anel.

## Dados GEO

Os atributos territoriais são extraídos pelas rotinas do motor `EXT-ESP-SET-v1.1` a partir das bases públicas locais já incorporadas ao projeto:

- GEO-02: vias e trilhas do OpenStreetMap;
- GEO-03: hidrografia do OpenStreetMap;
- GEO-04: relevo SRTMGL1/Mapzen;
- GEO-05: cobertura e uso do solo ESA WorldCover 2021 v200.

As bases públicas apoiam a caracterização analítica, mas não comprovam a condição atual nem a transitabilidade observada em campo.

## Ranking BASE

O ranking BASE é produzido sem alterar a função `rank_sector_records` do motor científico existente. Pesos: GEO-02 = 0,30; GEO-03 = 0,25; GEO-04 = 0,20; GEO-05 = 0,25.

## Ranking PERFIL

O segundo ranking não é apenas o BASE acrescido de 10%. Primeiro, ele recalcula o componente territorial `baseperfil` com pesos próprios: GEO-02 = 0,35; GEO-03 = 0,20; GEO-04 = 0,25; GEO-05 = 0,20. Esse componente territorial representa 90% do escore final. Somente o componente contextual `C`, associado às pistas de pesca e isolamento, representa os 10% restantes:

```text
baseperfil = 0,35*GEO02 + 0,20*GEO03 + 0,25*GEO04 + 0,20*GEO05
Awater = exp(-dwater/750) * GEO03 * (1 - water_wetland_prop)
Aisolation = GEO02 * (1 - min(road_density/4, 1))
C = 0,60*Awater + 0,40*Aisolation
final = 0,90*baseperfil + 0,10*C
```

O componente contextual expressa somente coerência territorial com as pistas de pesca e isolamento. A limitação de 10% aplica-se a esse componente, não ao ranking PERFIL inteiro. O ranking também difere do BASE pelos pesos territoriais 35/20/25/20. Nenhuma dessas parcelas impõe direção, destino, proximidade de ilha ou preferência por anel.

## Interpretação e limites

As três primeiras áreas são rotuladas AP1, AP2 e AP3 para apresentação. São áreas de prioridade analítica e não constituem probabilidades, detecções, localizações da vítima ou comandos operacionais. Empates preservam o mesmo posto analítico; eventual ordenação alfanumérica é apenas técnica para serialização.

Qualquer comparação posterior com a posição de referência deve ocorrer somente depois do congelamento destas saídas e em etapa separada.
