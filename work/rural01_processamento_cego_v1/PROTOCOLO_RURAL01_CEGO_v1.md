# Protocolo congelado — RURAL-01 territorial cego v1.0

## Finalidade

Produzir, antes da abertura da posição de avaliação, uma partição espacial e uma ordenação territorial reprodutível para o cenário RURAL-01. O procedimento usa um único ponto inicial, o raio de 1.500 m informado pela fonte e as camadas públicas GEO já consolidadas no projeto.

## Entradas autorizadas

- cenário: `RURAL-01`;
- candidato inicial: `RURAL-01-E0`;
- latitude: `0.188611`;
- longitude: `-51.155556`;
- raio direto informado pela fonte: `1.500 m`;
- GEO-02: vias e trilhas;
- GEO-03: hidrografia;
- GEO-04: relevo;
- GEO-05: cobertura e uso do solo.

O raio é aceito como parâmetro diagnóstico final ajustado pela fonte (`r0_semantics: source_adjusted_final`). Ele não é apresentado como resultado do motor de buffer adaptativo, e o motor não acrescenta fatores (`additional_factors_applied_by_engine: false`). A distância de 850 m entre o último registro de ERB e o ponto inicial é mantida apenas como relato contextual: esta execução não reproduz uma derivação matemática de 850 m para 1.500 m. Por isso, o raio permanece com situação `REVISAR`.

## Regras congeladas

1. O círculo é dividido em três anéis de área equivalente e oito direções, totalizando 24 setores.
2. Cada setor recebe os atributos territoriais do motor `EXT-ESP-SET-v1.1`.
3. O ranking principal é o conjunto `BASE`: GEO-02 30%, GEO-03 25%, GEO-04 20% e GEO-05 25%.
4. A direção provável Norte não entra no cálculo, pois não foi espacializada com azimute, tolerância e proveniência suficientes.
5. Perfil, fotografias, posição de avaliação e qualquer informação dela derivada não alteram setorização, extração ou ranking.
6. AP1, AP2 e AP3 são áreas analíticas. Não são probabilidades, detecções ou ordens operacionais.
7. Empates preservam o posto compartilhado; a ordem de apresentação pelo identificador não constitui preferência substantiva.
8. Todos os resultados permanecem com situação `REVISAR` por dependerem de fontes públicas e de confirmação humana em campo.

## Condição de uso

O pacote é diagnóstico e não confirmatório. A comparação posterior com a posição de avaliação deve ocorrer somente sobre os artefatos congelados e fora deste processamento.
