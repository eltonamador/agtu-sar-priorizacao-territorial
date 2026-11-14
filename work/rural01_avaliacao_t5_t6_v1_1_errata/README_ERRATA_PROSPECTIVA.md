# Avaliador v1.1 — correção prospectiva de semântica

Esta cópia foi criada **depois** da abertura da posição declarada no RURAL-01. Por isso, não substitui o avaliador v1.0 congelado nem o pacote T6 original desse caso.

Seu escopo é estritamente corretivo para execuções futuras:

1. quando a referência estiver fora do domínio e a grade não for aplicada, emitir `NAO_AVALIAVEL_GRADE`;
2. distinguir seis cenários pré-especificados de zero cenários efetivamente avaliáveis;
3. impedir que valores ausentes sejam narrados como `0/6` resultados favoráveis.
4. quando a referência estiver fora do domínio, emitir `NAO_AVALIAVEL_SETOR` em vez de `SEM_SETOR`;
5. manter cabeçalho estável no CSV de corredores, mesmo quando não houver métricas avaliáveis.

Não foram alterados domínio, tolerâncias, custos, bandas, setores, candidatos, corredores, rankings, hipóteses ou regras de seleção. Para o RURAL-01 já aberto, a interpretação autorizada está no pacote separado `outputs/campo_rural01/errata_interpretativa_t6_v1`.
