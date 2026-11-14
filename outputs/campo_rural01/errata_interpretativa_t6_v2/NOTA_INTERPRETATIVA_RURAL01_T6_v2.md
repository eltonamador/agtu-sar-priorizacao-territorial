# Nota interpretativa consolidada — RURAL-01 T6 v2

## Finalidade

Esta nota consolida a interpretação pública do resultado T6 e substitui a nota v1 apenas para fins de apresentação. O pacote computacional original permanece preservado, sem edição ou reexecução. Não foram modificados o ponto inicial, a posição declarada, o raio de 1.500 m, as superfícies de custo, os setores, os candidatos, os corredores, os rankings ou as duas hipóteses coprimárias.

## Resultado espacial preservado

A posição declarada do alvo simulado foi transcrita da imagem `KM14.png` como `0°9′12″ N, 51°8′56″ O`, equivalente a `0.15333333333333332, -51.14888888888889`. A distância calculada ao ponto inicial foi de **3.992,141 m**, no azimute inicial de **169,298°**. A referência situou-se, portanto, **2.492,141 m além** do domínio analítico congelado de 1.500 m.

O resultado da dimensão de cobertura é:

> **FORA_ESCOPO_DOMINIO**.

Como a posição estava fora do domínio, o protocolo não aplicou a grade nem a associação setorial e não calculou custos, rankings ou proximidade a corredores para a referência. Não houve encaixe forçado, extrapolação espacial ou ajuste retrospectivo.

## Correções semânticas de publicação

### 1. Associação à grade

O JSON original registrou `SEM_CELULA_NO_SUPORTE_DISCRETO`. Como a grade não foi aplicada fora do domínio, a forma pública correta é:

> **NAO_AVALIAVEL_GRADE**.

### 2. Associação setorial

O campo bruto `sector_assignment.classification` registrou `SEM_SETOR`, acompanhado de `method = NOT_APPLIED_OUTSIDE_DOMAIN`. Esse valor não representa uma tentativa negativa de associação. A forma pública correta é:

> **NAO_AVALIAVEL_SETOR**.

### 3. Seis cenários de sensibilidade

O relatório automático apresentou contagens `0/6`, embora os dados estruturados registrem seis ausências de orçamento e seis ausências de ranking. O denominador correto é:

> **6 cenários pré-especificados; 0 cenários avaliáveis; 6 cenários não avaliáveis**.

Nenhum valor ausente deve ser contabilizado como erro ou acerto. Por isso, não se publicam taxas de sucesso, fracasso, Top-3 ou orçamento para este caso.

### 4. Corredores

Como a posição estava fora do domínio, as métricas de corredores também ficaram não avaliáveis. O CSV original vazio não representa distância zero nem inexistência territorial de corredores; significa apenas que nenhuma métrica poderia ser calculada para a referência exterior.

## Interpretação científica

O RURAL-01 produziu resultado negativo específico para a **cobertura espacial da configuração de entrada de 1.500 m**. O caso demonstra que esse raio fixo não abrangeu a posição declarada. Ele não testa a qualidade relativa das superfícies de custo, dos rankings setoriais ou dos corredores internos e, portanto, não autoriza concluir que esses componentes acertaram ou falharam.

A preservação desse resultado delimita de forma verificável a fronteira de validade da configuração inicial e evita que o sistema forneça uma indicação territorial sem suporte. O achado sustenta uma evolução prospectiva: parametrizar e congelar, antes de novos testes, um **buffer adaptativo** que considere tempo decorrido, mobilidade, condição clínica, contexto territorial e confiabilidade do último ponto conhecido. Essa nova regra deve ser avaliada em casos posteriores, sem recalibrar o RURAL-01.

## Proveniência

- Manifesto T6 original: SHA-256 `05bba785481fa094aafa8e99971824c8d178fd72cd8e31970c6520475b30d7a2`.
- Resultado JSON original: SHA-256 `044e4a9219bee3c4667a2b84ce579feb443aa1000784bb3fa99fcd9d7b651705`.
- Relatório automático original: SHA-256 `ca1ce8f6657263658133583ffd4a2d893e64f9ba6f7c346c1131078071103273`.
- Registro T5: SHA-256 `f7aaa204e24c48ed343c769e924f01883f6405d05cb740cc82fe64841e491a15`.
- Imagem `KM14.png`: SHA-256 `dc7c8e19eeb85dd0ebdba9f2189ca38622b8bea7cef4698301ace3b956c43761`.
- Nota interpretativa v1 preservada: SHA-256 `084f99a7a327d5dd9e2dcf59db3a73b9c21fbea13e782753b7f2222a44661063`.

Esta nota é uma camada interpretativa versionada. Ela não constitui nova execução confirmatória nem alteração pós-revelação das regras do modelo.
