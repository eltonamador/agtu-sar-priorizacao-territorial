# EXT-ESPACIAL — motor de buffer adaptativo v1

Este diretório contém a implementação reprodutível do protocolo `EXT-ESP-BUF-v1.0`. O componente transforma a incerteza espacial inicial de cada hipótese candidata em um raio adaptativo, limitado entre 250 m e 7.500 m, sem usar a posição verdadeira da vítima durante o cálculo.

O protocolo foi congelado para desenvolvimento em 14 de outubro de 2026. A configuração normativa está em `config_buffer_v1.json`. Qualquer mudança de parâmetro, fórmula, política de ausência ou regra de elegibilidade exige um novo identificador de versão e a repetição integral dos testes.

## Finalidade e posição no projeto

O motor pertence à extensão espacial do modelo de apoio à decisão. Ele não localiza autonomamente a vítima, não substitui o sistema aerotransportado e não comanda a operação de busca. Sua função é qualificar espacialmente as hipóteses já recebidas, produzindo uma área de incerteza rastreável para cada candidato.

A execução sobre a base DEV legada é exclusivamente diagnóstica. Nessa base, o raio inicial foi produzido pelo gerador semissintético e pode depender do erro em relação à referência, além de apresentar correlação com a idade da informação. Portanto, esse ensaio verifica o funcionamento técnico do motor, mas **não** demonstra cobertura confirmatória, ganho causal ou eficácia operacional.

## Fórmula congelada

O raio adaptativo é calculado por:

`r_a = min(r_max, max(r_min, r0 × f_q(Qdet) × f_e(Amb) × f_s(σ_pos) × f_t(I_dado)))`

Parâmetros principais:

- raio mínimo: 250 m;
- raio máximo: 7.500 m;
- baseline fixo de comparação: 2.000 m;
- raio médio da Terra para a geometria esférica: 6.371.008,8 m;
- polígono circular: 72 vértices, além do fechamento do anel;
- sistema de referência de entrada e saída: EPSG:4326.

Os fatores são contínuos e determinísticos:

- qualidade: `f_q = 1 + 0,5 × (1 − q)`, com `q` obrigatório no intervalo fechado de 0 a 1;
- ambiente: multiplicador categórico definido na configuração;
- dispersão posicional: `f_s = 1 + 0,5 × min(σ_pos / 50, 1)`;
- idade da informação: `f_t = 1 + 0,5 × min(I_dado / 180, 1)`.

Quando dispersão posicional ou idade não estiverem disponíveis, o respectivo fator assume 1,0 e o motor registra uma advertência. A ausência do ambiente aplica o fator 1,15 e força revisão. A classe explícita `DESCONHECIDO` também usa 1,15 e permanece identificada para revisão. Se dois ou mais campos opcionais estiverem ausentes, o resultado recebe o status `REVISAR`.

## Semântica obrigatória do raio inicial

Cada linha deve declarar `r0_semantics` com um dos três valores:

| Valor | Uso | Elegibilidade confirmatória |
|---|---|---|
| `nominal_base` | raio nominal congelado pelo protocolo; espera-se 2.000 m | sim, se congelado antes da abertura da referência |
| `source_adjusted` | raio fornecido ou calculado pela fonte operacional, sem utilizar o ground truth; exige declarar em `factors_applied` quais ajustes já estão embutidos | sim, com proveniência documentada |
| `diagnostic_legacy` | raio do gerador semissintético legado | não |

O valor `diagnostic_legacy` sempre gera a advertência de entrelaçamento com o gerador e impede que a execução seja classificada como confirmatória.

## Entradas

O arquivo de entrada deve estar em CSV UTF-8. Campos obrigatórios:

- `scenario_id`: identificador do cenário;
- `candidate_id`: identificador do candidato;
- `estimated_lat`: latitude estimada em graus decimais;
- `estimated_lon`: longitude estimada em graus decimais;
- `base_radius_m`: raio inicial `r0`, em metros;
- `r0_semantics`: semântica do raio inicial;
- `detection_quality`: qualidade da detecção, de 0 a 1.

Campos opcionais:

- `environment_class`;
- `position_dispersion_m`;
- `information_age_min`;
- `factors_applied`, obrigatório apenas quando `r0_semantics=source_adjusted`;
- `r0_provenance`;
- `data_origin`;
- `source_row_hash`;
- `execution_phase`.

São aceitas as classes ambientais `RURAL/ABERTO`, `MISTO`, `URBANO`, `MATA`, `ÁREA ALAGADA` e `DESCONHECIDO`. Valores não reconhecidos são rejeitados, porque a conversão automática de uma categoria ambígua poderia alterar o raio sem justificativa.

### Firewall de ground truth

O motor interrompe a execução quando encontra campos que revelem ou derivem da posição real, incluindo latitude ou longitude de referência, distância ao ground truth e indicação do candidato relevante. Essa barreira impede que a resposta conhecida influencie o cálculo.

## Execução

Consulte primeiro os argumentos disponíveis:

```bash
python3 motor_buffer_adaptativo.py --help
```

Execução canônica do ensaio de desenvolvimento:

```bash
python3 motor_buffer_adaptativo.py \
  --input input_dev_blind.csv \
  --config config_buffer_v1.json \
  --output-csv results/buffer_results_dev.csv \
  --output-json results/buffer_results_dev.json \
  --output-geojson results/buffer_polygons_dev.geojson \
  --manifest results/manifest_execucao_dev.json
```

Em seguida, execute a suíte de testes:

```bash
python3 test_motor_buffer_adaptativo.py -v \
  --json-report results/test_results.json
```

Uma execução somente pode ser aceita quando todos os testes passarem, os raios permanecerem nos limites, os anéis GeoJSON estiverem fechados, a repetição determinística produzir o mesmo conteúdo e o manifesto registrar os hashes SHA-256.

## Saídas

O pacote gera:

- CSV e JSON tabulares com fatores, raio bruto, raio limitado, status e advertências;
- GeoJSON com um polígono de incerteza por candidato;
- manifesto de execução com versão do protocolo, classificação do ensaio e hashes dos artefatos;
- relatório de testes, quando solicitado pela rotina correspondente.

As saídas não contêm ground truth. A comparação com a posição verdadeira pertence a uma etapa posterior e separada, executada somente depois do congelamento dos resultados do motor.

## Leitura dos resultados

O raio adaptativo representa uma área de investigação coerente com os sinais informados na entrada. Um raio maior não significa pior desempenho por si só; significa que o protocolo reconheceu mais incerteza. O limite superior evita expansão sem controle e o limite inferior evita precisão artificial.

O baseline fixo de 2.000 m é uma referência comparativa, não um valor substitutivo para `r0`. Na validação independente, a análise deverá comparar cobertura, área e comportamento de revisão entre o buffer adaptativo e esse baseline, após a abertura controlada do ground truth.

## Fotografias e dados de campo

Fotografias aéreas e terrestres não entram numericamente no motor v1. Elas podem documentar o contexto ambiental, apoiar a interpretação dos casos e fortalecer uma validação externa futura, mas sua ausência não impede o teste lógico do cálculo. Metadados de campo devem ser preservados como evidência de proveniência, sem serem convertidos em fatores não previstos no protocolo.

## Requisitos para validação independente

Uma futura execução `REP_S_INDEPENDENTE` deve cumprir cumulativamente:

1. utilizar `r0` nominal ou oriundo do sistema-fonte, nunca derivado da posição verdadeira;
2. congelar configuração, entradas e plano de análise antes de abrir a referência;
3. manter separados o arquivo cego de entrada e o arquivo protegido de ground truth;
4. registrar origem dos dados, versões e hashes;
5. congelar as saídas antes de calcular cobertura ou distância à referência;
6. relatar ausências, revisões e saturações sem exclusão oportunista de casos.

Enquanto esses requisitos não forem cumpridos, resultados obtidos com `diagnostic_legacy` devem ser apresentados apenas como evidência de implementação e teste de engenharia.

## Limites do módulo v1

- O modelo geométrico usa esfera com o raio médio WGS84. Isso é adequado aos raios locais previstos pelo protocolo, mas não substitui um processamento geodésico de maior precisão quando o estudo exigir essa precisão.
- A dispersão posicional é opcional; sua ausência produz fator neutro e advertência, não um valor inventado.
- A idade ausente também produz fator neutro e advertência.
- O ambiente ausente recebe fator conservador definido e revisão obrigatória.
- A base DEV legada não é apropriada para estimar desempenho confirmatório, porque seu `r0` não é independente da referência.
- O motor gera áreas candidatas; ele não comprova que a vítima esteja dentro delas sem uma avaliação posterior e protegida.

## Controle de mudanças

`config_buffer_v1.json` é a fonte normativa da versão 1.0. Correções meramente documentais podem ser registradas sem mudar a fórmula. Qualquer modificação que altere resultados — inclusive parâmetros, classes, fatores, políticas de ausência, limites, método geométrico ou critérios de revisão — exige uma nova versão do protocolo, nova assinatura de hashes e nova execução integral da suíte de testes.
