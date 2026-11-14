# RURAL-01 — processamento territorial cego v1

Este diretório contém o invólucro reproduzível do núcleo territorial do cenário `RURAL-01`. Ele reutiliza, sem modificar, o motor `EXT-ESP-SET-v1.1` e processa diretamente o raio de 1.500 m informado pela fonte.

Execução:

```bash
python3 work/rural01_processamento_cego_v1/run_rural01_blind.py
```

Testes:

```bash
python3 -m unittest work/rural01_processamento_cego_v1/test_rural01_blind.py
```

Saída padrão: `outputs/campo_rural01/processamento_cego_v1`.

O núcleo não lê fotografias, não usa direção comportamental e não acessa posição de avaliação. Esses insumos permanecem segregados para módulos próprios e para avaliação posterior.

## PERFIL V2/V3, LOC integrado, URG e DET

Depois de fixar o ranking territorial e gerar o manifesto visual de controle,
execute o pacote complementar com um instante RFC 3339 real e dotado de fuso:

```bash
python3 work/rural01_processamento_cego_v1/build_profile_protocol.py \
  --created-at AAAA-MM-DDTHH:MM:SS-03:00
```

Entradas padrão:

- `outputs/campo_rural01/processamento_cego_v1/ranking_base_rural01.csv`;
- `outputs/campo_rural01/processamento_cego_v1/setores_rural01.geojson`;
- `outputs/campo_rural01/entrada_cega_v1/manifesto_metadados_visuais.json`.

Saída padrão: `outputs/campo_rural01/perfil_v2_v3`.

O manifesto visual é ligado apenas pelo SHA-256. As fotografias não entram como
evidência LOC/DET, e o procedimento não cria horário de captura nem footprint.
Sem hipótese espacial quantitativa elegível, o PERFIL V3 se abstém e preserva
integralmente o ranking territorial. O `loc_result_v1.json` fecha o contrato LOC
com os setores já produzidos, sem misturar urgência ou detectabilidade ao ranking.

Teste de integração e determinismo:

```bash
python3 -m unittest \
  work/rural01_processamento_cego_v1/test_build_profile_protocol.py
```

## Congelamento T2 pré-revelação

Somente depois de produzir e validar os artefatos anteriores, congele o pacote
que antecede o recebimento da posição real usada na avaliação:

```bash
python3 work/rural01_processamento_cego_v1/freeze_t2_package.py
```

Saída padrão: `outputs/campo_rural01/t2_congelado_final`.

O congelamento calcula hashes dos artefatos críticos, confere a segregação da
posição real, a ausência de efeito numérico das fotografias no LOC, a
preservação do Top-3 territorial e a separação entre LOC, URG e DET. A posição
real somente pode ser recebida e usada para avaliação depois que o manifesto
T2 estiver com o estado `CONGELADO_PASS`. O instante é obtido diretamente do
relógio do sistema em `America/Belem`, e o diretório final não pode ser
sobrescrito por outra execução.
