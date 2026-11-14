# Relatório PERFIL V3 cego — MATA-01

## Resultado executivo

O PERFIL V3 foi executado sem posição de referência do alvo e usando exclusivamente a pista autorizada **marcas de botas rumo Norte (0° ±22,5°)**. A qualidade da evidência foi atenuada para `q=2/3` por ser **RELATADA** e de confiança **MÉDIA**. No λ principal de 0,10, o peso efetivo foi `0,0666667`.

A seleção de primeiro lugar foi **estável** entre λ=0,05 e λ=0,10. O Top-3 não mudou em relação ao ranking territorial diagnóstico. O resultado do motor foi `EFEITO_PERFIL_APLICADO`, mas seu uso permanece **diagnóstico, não confirmatório, sob status REVISAR**, porque a fonte territorial é `BASE_DISPONÍVEIS`, com GEO03 ausente, e não equivale ao BASE completo.

## Top-3 no λ principal

1. `MATA-01::MATA-01-E0::R01::S`
2. `MATA-01::MATA-01-E0::R02::SW`
3. `MATA-01::MATA-01-E0::R01::E`

- Margem Top-1/Top-2 territorial: 0.023358.
- Margem Top-1/Top-2 em λ=0,05: 0.022579.
- Margem Top-1/Top-2 em λ=0,10: 0.021800.
- Avisos do motor: `MARGEM_BAIXA_DIAGNOSTICA_REVISAR`.

## Efeito explicável da pista Norte

- `MATA-01::MATA-01-E0::R01::N`: posto territorial 22 → 17 em λ=0,05 → 14 em λ=0,10; ΔS(0,10)=0.044639.
- `MATA-01::MATA-01-E0::R02::N`: posto territorial 24 → 22 em λ=0,05 → 18 em λ=0,10; ΔS(0,10)=0.045566.
- `MATA-01::MATA-01-E0::R03::N`: posto territorial 23 → 21 em λ=0,05 → 16 em λ=0,10; ΔS(0,10)=0.044906.

A pista elevou apenas os três setores direcionais Norte, exatamente como previsto pela interseção angular. Ela não foi forte o bastante para superar os escores territoriais dos setores líderes. Isso é um resultado válido: o módulo ajustou o ranking de forma rastreável sem forçar uma mudança de vencedor.

## Entradas excluídas do LOC quantitativo

Não receberam peso: hábito de buscar água sem segmento georreferenciado, fumaça sem posição ou vínculo, familiaridade, roupa, tempo/cansaço/desidratação e fotografias. Urgência e detectabilidade permanecem separadas de LOC.

## Compatibilidade e limites

- O núcleo `PERFIL-V3-QUANT-RANKER-v1.1` foi usado sem alteração.
- O adaptador legado não foi usado porque exige compilado PERFIL V2 inexistente para MATA-01. A integração direta está declarada e vinculada por hashes em sidecars congelados.
- O motor mantém λ=0,15 no JSON bruto apenas como teste de estresse fora do teto. A decisão de estabilidade considera somente λ=0,05 e λ=0,10.
- A saída não representa probabilidade, acurácia de localização ou comando operacional.
- A base hidrográfica OSM vazia no domínio foi tratada como ausência de dado, não como condição favorável.

## Verificação

- QA: **PASS** (20/20 verificações).
- Firewall da posição reservada: **PASS**.
- Dependência de posição de referência: **não**.
- Situação para uso: **REVISAR — diagnóstico não confirmatório**.
