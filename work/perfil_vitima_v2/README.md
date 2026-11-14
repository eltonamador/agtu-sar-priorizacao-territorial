# Compilador qualitativo do perfil da vítima V2

Esta implementação é a primeira etapa prospectiva do módulo PERFIL V2 e lê o
contrato `PERFIL-V2-DRAFT.2`. Ela:

- valida a entrada conforme `outputs/modulo_perfil_vitima_v2/perfil_vitima_v2.schema.json`;
- rejeita chaves de *ground truth* em qualquer nível;
- preserva natureza, fonte e confiança de cada evidência;
- valida identificadores estáveis e metadados condicionais de congelamento;
- recalcula e verifica o hash do pacote congelado;
- rejeita contradições entre valor, fonte, confiança e autorização de uso;
- verifica a ordem temporal ponto inicial → coleta → congelamento;
- preserva direção estruturada com origem, azimute ou rumo cardinal, tolerância e método;
- converte apenas informações autorizadas em hipóteses qualitativas explícitas;
- marca informações ainda não espacializáveis;
- não calcula pesos, escores, probabilidades ou rankings.

## Uso

```bash
python3 compile_profile.py --input entrada.json --output perfil_compilado.json
```

Sem `--output`, o JSON compilado é emitido na saída padrão.

### Congelamento seguro

Um rascunho validado pode ser convertido em pacote congelado sem sobrescrever a
entrada original:

```bash
python3 compile_profile.py \
  --input entrada_rascunho.json \
  --prepare-freeze \
  --frozen-at 2026-10-21T09:00:00-03:00 \
  --output entrada_congelada.json
```

O algoritmo `PERFIL-V2-FREEZE-PROJECTION-v1` cria uma cópia do pacote com
`record_status=CONGELADO` e todos os metadados de congelamento. Para evitar
autorreferência, remove **somente** `freeze_metadata.payload_sha256`, serializa
o restante em JSON UTF-8 com chaves ordenadas, separadores compactos, Unicode
preservado e nova linha final, e calcula SHA-256 hexadecimal em minúsculas.
Qualquer modificação posterior em outro campo invalida o pacote.

Um pacote já marcado como `CONGELADO` só é aceito pelo compilador quando o hash
declarado coincide com o hash recalculado. A função pública
`prepare_frozen_payload(...)` oferece o mesmo fluxo para integração futura com
a interface.

### Coerências mínimas

- valor não disponível não pode ser autorizado para produzir efeito nem ter
  confiança alta;
- valor conhecido e autorizado não pode usar fonte `NAO_DISPONIVEL`;
- o horário do ponto de planejamento não pode ser posterior à coleta;
- a coleta não pode ser posterior ao congelamento;
- quando `elapsed_status=CALCULADO`, `elapsed_minutes` deve coincidir, com
  tolerância técnica de um segundo, com o intervalo entre o ponto e a coleta.
- quando o tempo é `INFORMADO` e o horário do ponto é `EXATA`, admite-se até
  um minuto de diferença, correspondente à unidade de registro do campo.

Tempos aproximados, ou informados a partir de um horário também aproximado,
mantêm sua natureza declarada e não são artificialmente forçados a uma
igualdade exata sem margem de incerteza temporal formalizada.

## Testes

```bash
python3 -m unittest test_compile_profile.py
```

Os testes cobrem o firewall estrutural e textual, o tratamento de desconhecidos,
pistas genéricas não direcionais, destino georreferenciado, direção observada
estruturada, preservação de suspeita, identificadores, congelamento verificável,
detecção de alteração, coerência de evidências, ordem temporal, tempo calculado
e determinismo.

## Limite desta versão

Uma hipótese compilada não altera ranking. Antes disso será necessário formalizar e congelar regras quantitativas independentes dos três novos casos de campo.
