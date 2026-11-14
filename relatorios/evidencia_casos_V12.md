# Casos e integridade — evidência da conferência de 14/11/2026

O confronto desta entrega usa a V12 recebida em 14/11 às 16h21. A versão enviada em 13/11 serve apenas para verificar continuidade dos trechos. Os caminhos abaixo são relativos à raiz que contém `work/` e `outputs/`; não atestam publicação. Foi feita leitura das saídas, **não** nova execução dos cinco casos. Não se usou o desfecho para alterar nenhuma saída.

## Versões e escopo

| Documento de Downloads | SHA-256 do DOCX |
|---|---|
| Dissertacao_AGTU_Francielton_Amador_v98_2026-11-13_1615_final.docx (V11 anterior) | `3f1f5b485edef3a73ff15f2bf42dcdd09adac49ca2c73b68b2db672d55e37be6` |
| Dissertacao_AGTU_Francielton_Amador_v98_2026-11-14_1621.docx (V12 de referência) | `9a18f83d381484172d35637e4ca7e3d253ec4b28f9d6ce952affb896bca114bd` |

Na extração de texto, coincidem as linhas de dados das Tabelas 3 e 5, o parágrafo numérico do §2.9.1 e o parágrafo com os hashes abreviados do Apêndice C. Não se afirma equivalência integral dos documentos.

## Confere — sete identificadores do Apêndice C

| Identificador | SHA-256 recalculado | Objeto e localização |
|---|---|---|
| URBE-01 | `490663d2459b1aa5fac151b425ff474c0dacdb44891ee8530b2dd9960dbdcb23` | Conjunto de 15 arquivos; `outputs/campo_urbe01/processamento_cego_v1/manifesto_processamento_cego.json`, campo `scientific_projection_sha256`. |
| RURAL-01 | `d51dd9e3252f50bd1d756b4b9ee914aca0b7300eda6e2b2f751e5f6fa587301e` | Conjunto de 12 arquivos; `outputs/campo_rural01/processamento_cego_v1/manifesto_processamento_cego.json`, mesmo campo. |
| MATA-01 | `7ba1186d90aaf5ef6b92dd7095727e151c948880163b3c81d0c4cd7ff02df29b` | Conjunto de 13 arquivos; `outputs/campo_mata01/processamento_cego_v1/manifesto_processamento_cego.json`, mesmo campo. |
| MATA-02 | `8236e5244a8f6fef501d4aea9492c56bf75d34a87109eecfc94da03e681f31fb` | Bytes de `outputs/campo_mata02_mzg2/ensaio_complementar_v2_249/ranking_BASE_completo.json`. |
| MATA-03 | `1ba965b3d69f07e06607771036d8246dc6023886929d2a6ca3c6340d5094e11a` | Bytes de `outputs/campo_mata03_km21/ranking_BASE.json`. |
| Setorização v1.1 — projeção científica | `bff2deb9cf329096d7191b86381d5570c2df6905ba51499242d51c07531053dc` | 2.160 registros do campo `results` de `outputs/ext_espacial_s3_setorizacao_priorizacao_v1_1/results/sector_results_dev.json`. Registrado em `manifest_setorizacao_dev.json` na mesma pasta. |
| Setorização v1.1 — conjunto científico | `0d90933c35117cf6abc62346ec790e38328c65fa9af9f94752a8554286cbc837` | Seis saídas na mesma pasta, campo `scientific_bundle_sha256` do mesmo manifesto. |

**Como reproduzir a verificação:** para cada um dos três primeiros casos, a listagem completa está na constante `SCIENTIFIC_FILES` do arquivo `work/urbe01_processamento_cego_v1/run_urbe01_blind.py`, `work/rural01_processamento_cego_v1/run_rural01_blind.py` ou `work/mata01_processamento_cego_v1/run_mata01_blind.py`. A partir dessa lista, calculou-se SHA-256 dos bytes atuais de cada arquivo da pasta do manifesto, conferiu-se cada digest individual e calculou-se o SHA-256 do mapa `{nome: digest}` serializado em UTF-8 com `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))`. As 40 comparações individuais e as três agregadas conferiram. Não se deve aplicar SHA-256 aos bytes do próprio manifesto e esperar o identificador agregado. Para MATA-02 e MATA-03, basta `shasum -a 256` aplicado ao JSON indicado.

No módulo, `work/ext_espacial_setores_v1_1/motor_setorizacao_priorizacao.py:1549` define a projeção por linha, preservando ordem: ID do setor, escore BASE, posto, estado do domínio, seleção e estabilidade. A linha 1579 define o mapa canônico com os digests de `sector_polygons_dev.geojson`, `sector_features_dev.csv`, `sector_ranking_dev.csv`, `buffer_decisions_dev.csv`, `sector_results_dev.json` e `warnings_dev.log`. Ambos foram reconstruídos de seus conteúdos, sem rodar o motor. **Não confere** interpretar `bff2de…53dc` como hash do código-fonte nem `0d9093…c837` como hash do ZIP: os hashes dos bytes de `work/ext_espacial_setores_v1_1/motor_setorizacao_priorizacao.py` e `outputs/ext_espacial_s3_setorizacao_priorizacao_v1_1.zip` são, respectivamente, `938f98a0cf52751aeaa9f17369ef86c4d7afd96965d574f79898cebd3799c519` e `4d36dc86a89bd3ab1043a5e8a22c1eaa5a8dbeab647a6c23931ba78cf64c0c4e`.

## Confere — Tabelas 3 e 5

| Caso | Estado BASE; ordenação 1º → 3º | Referência para comparação |
|---|---|---|
| URBE-01 | REVISAR; R03-N → R02-SW → R01-NW | R02-S, 18º/24 no BASE (19º no perfil legado). |
| RURAL-01 | REVISAR; R01-E → R03-SE → R03-E | A 3.992,141 m de E0, fora do domínio de 1.500 m. Sem posto; não conta como último. |
| MATA-01 | ABSTIDO no BASE completo, **sem Top-3**; só no diagnóstico separado: R01-S → R02-SW → R01-E | Sem posto de referência; abstenção por GEO-03 indisponível. |
| MATA-02 | REVISAR; R01-SW → R03-SW → R03-E | R02-W, 22º/24 no BASE; 12º a 21º nas nove variantes de perfil elegíveis. Controle sem confiança avaliada abstido, conserva 22º. |
| MATA-03 | REVISAR; R01-E → R03-NE → R01-SE | Ponto A (comparação posterior), R03-NE, 2º/24 no BASE. Perfil abstido. |

Fontes das linhas (cada ordenação consultada contém 24 registros, inclusive o diagnóstico do MATA-01):

- URBE-01: `outputs/campo_urbe01/processamento_cego_v1/ranking_base_original.csv` e `outputs/campo_urbe01/avaliacao_pos_abertura_v1/avaliacao_rankings.csv`.
- RURAL-01: `outputs/campo_rural01/processamento_cego_v1/ranking_base_rural01.csv` e `outputs/campo_rural01/avaliacao_pos_abertura_v1/resultado_avaliacao_t5_t6.json`.
- MATA-01: `outputs/campo_mata01/processamento_cego_v1/resultado_mata01_cego.json` (campos `base_original.status = ABSTIDO_GEO03_INDISPONIVEL`, `top3_generated = false`); `ranking_base_disponiveis_mata01.csv` e `top3_base_disponiveis_mata01.json` na mesma pasta. O campo geral `review_status = REVISAR` não é a decisão de emitir o BASE completo desse caso.
- MATA-02: JSON do ranking na tabela dos hashes e `outputs/campo_mata02_mzg2/conferencia_referencia_declarada_v1_20261030/COMPARACAO_RESULTADOS.json` e `COMPARACAO_PERFIL.csv` na mesma pasta.
- MATA-03: JSON do ranking na tabela dos hashes e `outputs/campo_mata03_km21/comparacao_referencia_A_20261103/comparacao_referencia_A.json`.

**Não confere — apenas entre duas representações do MATA-03:** em `outputs/campo_mata03_km21/resultado_BASE.json`, `top3 = []`; o ranking primário de 24 setores, de hash confirmado, e o registro de comparação de A contêm os três setores publicados. A inconsistência do resumo não é uma divergência da Tabela 5 com a ordenação. Já estava consignada na consolidação histórica dos cinco casos. Não corrigir retroativamente a saída; indicar o ranking autoritativo no README.

## Confere — exemplo numérico, §2.9.1

Linha `RURAL-01::RURAL-01-E0::R01::E` do ranking CSV acima: GEO-02 a GEO-05 = 0,748831198; 0,671086362; 0,640838520; 0,550000000. A soma decimal com os pesos BASE 0,30; 0,25; 0,20; 0,25 dá **0,65808865390**, ou **0,658088654** a nove casas, igual ao `score_base` gravado. A seis casas, **0,658089**, como na V12. Repetir a conta com os quatro componentes já arredondados no texto dá 0,65808860: mesma apresentação final a seis casas. Não é um ajuste de pesos.

Esta conferência demonstra compatibilidade documental e integridade dos objetos locais examinados, não comprovação de eficácia operacional, autoria, data de criação ou publicação em GitHub.
