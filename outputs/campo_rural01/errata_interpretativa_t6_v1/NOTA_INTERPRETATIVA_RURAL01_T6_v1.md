# Nota interpretativa versionada — RURAL-01 T6

## Finalidade

Esta nota corrige duas expressões semânticas do relatório automático T6 sem substituir, editar ou recalcular o pacote original. O protocolo, o domínio de 1.500 m, as superfícies de custo, os setores, os candidatos, os corredores e as duas hipóteses coprimárias permanecem exatamente como foram congelados antes da abertura da referência.

## Resultado preservado

A posição declarada do alvo simulado foi transcrita da imagem `KM14.png` como `0°9′12″ N, 51°8′56″ O`, equivalente a `0.15333333333333332, -51.14888888888889`. A distância calculada ao ponto inicial do RURAL-01 foi de **3.992,141 m**, com azimute inicial de **169,298°**. A posição encontra-se, portanto, **2.492,141 m além** do raio analítico congelado de 1.500 m.

O resultado correto da dimensão de cobertura é:

> **FORA_ESCOPO_DOMINIO**.

Por pré-especificação, nenhuma célula, setor, custo acumulado, posto, corredor ou hipótese pode ser atribuído a uma referência exterior. Não foi realizado encaixe forçado, extrapolação ou ajuste retrospectivo.

## Errata 1 — associação à grade

O relatório automático registrou `SEM_CELULA_NO_SUPORTE_DISCRETO`. Como a grade não foi aplicada fora do domínio, a forma semanticamente correta, já prevista no protocolo, é:

> **NAO_AVALIAVEL_GRADE**.

Isso não altera qualquer coordenada, distância ou resultado numérico.

## Errata 2 — seis cenários de sensibilidade

O texto automático informou `0/6` para orçamento e `0/6` para associação Top-3. Os próprios dados estruturados registram `missing_budget_count = 6` e `missing_ranking_count = 6`. Assim, não houve seis resultados negativos; houve **seis cenários não avaliáveis**, pois a posição estava fora do domínio.

A redação correta é:

> Nos seis cenários de sensibilidade, orçamento de movimento e associação a setor Top-3 foram não avaliáveis. Nenhum valor ausente foi contado como erro ou acerto.

## Interpretação científica autorizada

O RURAL-01 produziu um resultado negativo específico para a **cobertura espacial do domínio de entrada de 1.500 m**. O caso não avalia o desempenho dos custos, rankings e corredores internos e, por isso, não demonstra falha desses componentes. Também não autoriza aumentar retrospectivamente o buffer para incluir a posição declarada.

O achado sustenta uma melhoria prospectiva do modelo: definir o raio de busca de forma adaptativa e previamente parametrizada pelo tempo decorrido, mobilidade, condição clínica, contexto territorial e confiabilidade do último ponto conhecido. Essa melhoria deverá ser avaliada em novos casos, sem recalibrar o RURAL-01.

## Proveniência e integridade

- Manifesto T6 original: SHA-256 `05bba785481fa094aafa8e99971824c8d178fd72cd8e31970c6520475b30d7a2`.
- Resultado JSON original: SHA-256 `044e4a9219bee3c4667a2b84ce579feb443aa1000784bb3fa99fcd9d7b651705`.
- Relatório automático original: SHA-256 `ca1ce8f6657263658133583ffd4a2d893e64f9ba6f7c346c1131078071103273`.
- Registro T5: SHA-256 `f7aaa204e24c48ed343c769e924f01883f6405d05cb740cc82fe64841e491a15`.
- Imagem `KM14.png`: SHA-256 `dc7c8e19eeb85dd0ebdba9f2189ca38622b8bea7cef4698301ace3b956c43761`.
- O pacote T6 original permanece preservado e não foi sobrescrito.

Esta nota tem natureza exclusivamente interpretativa. Ela não constitui nova execução confirmatória nem modificação pós-revelação das regras do modelo.
