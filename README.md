# AGTU — Priorização territorial em busca e salvamento

Repositório da dissertação 'Modelo de inteligência artificial explicável para priorização territorial em busca e salvamento por análise multicritério geoespacial e regras de conhecimento', de Francielton Araujo Amador (AGTU University, Mestrado em Inteligência Artificial, 2026).

Este pacote acompanha a versão para qualificação de 14/11/2026 (V12). **É uma prova de conceito, sem validação operacional.** A partir de uma referência inicial e de um raio informado, o modelo divide o domínio em 24 setores de igual área, atribui escores territoriais e indica se há condições para interpretar a ordenação. O escore não é probabilidade de encontrar a pessoa. Os cinco desaparecimentos são hipotéticos, em ambientes documentados em campo; a decisão de empregar equipes continua com o profissional. O repositório é público. A publicação não inclui os originais sob custódia nem concede licença geral de redistribuição.

## Como consultar

Os pesos do BASE (0,30; 0,25; 0,20; 0,25 para GEO-02 a GEO-05) são parâmetros de referência por julgamento operacional e literatura, não calibrados. IGUAIS, SEM_BARREIRAS, APENAS_ACESSO e ENFASE_BARREIRAS são alternativas de sensibilidade. Margem de 0,05 e estabilidade de 0,80 são critérios de projeto, não limites de segurança. A comparação posterior com a posição simulada é descritiva, não uma medida de acerto. Não se declara nível de maturidade tecnológica (TRL).

| Pasta | Para que serve |
|---|---|
| [work](work/) | Motores, parâmetros, testes e executores históricos dos casos. Há versões anteriores necessárias para interpretar resultados, especialmente o perfil usado no URBE-01. |
| [outputs](outputs/) | Insumos geoespaciais, configurações efetivas, atributos por setor, rankings, decisões, registros de comparação posterior e manifestos. **Estes arquivos são a evidência preservada: não gravar uma nova execução sobre eles.** |
| [casos](casos/) | Notas sobre as fotografias dos cinco casos. Os originais (cerca de 1,5 GB) não são publicados porque o acervo contém placas de veículos e fachadas identificáveis. Permanecem sob custódia do autor e podem ser disponibilizados ao orientador e à banca mediante solicitação. |
| [avaliacao](avaliacao/) | [Questionário sem respostas](avaliacao/instrumento.md), [frequências agregadas](avaliacao/frequencias.csv) e [vídeo demonstrativo](avaliacao/Apresentacao_narrada_especialistas_PTBR.mp4). A avaliação é de utilidade e clareza percebidas, não de eficácia. Nenhum registro individual ou horário de envio integra a tabela. |
| [scripts](scripts/) e [relatorios](relatorios/) | Conferência independente dos sete hashes, relação dos arquivos científicos e evidências para conferir testes, regras e resultados. |

O diretório local `_arquivo/` é excluído do versionamento. A dissertação, o parecer e os dados individuais dos profissionais não são materiais deste repositório. A ausência de um mapa, imagem, dado geográfico ou entrada de um manifesto na cópia de consulta **não comprova que ele nunca existiu**; consulte a fonte identificada e não reconstrua o dado ausente por suposição.

## Como verificar sem repetir uma busca

Na raiz, com Python 3.12 e Bash:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python scripts/verificar_hashes_apendice_c.py
```

Esse verificador lê os resultados; não executa os motores. Para URBE-01, RURAL-01 e MATA-01, o hash publicado é o de uma **projeção de vários arquivos**, não o hash do próprio manifesto. Para MATA-02 e MATA-03, é o SHA-256 dos bytes do ranking BASE em JSON. Os outros dois identificadores pertencem ao módulo de setorização. Há [explicação por identificador e por caso](relatorios/evidencia_casos_V12.md).

Para os testes, em macOS com Swift/ImageIO para leitura de metadados, use:

```sh
python -m pip install Pillow==13.0.0 openpyxl==3.1.5 et_xmlfile==2.0.0 reportlab==4.4.9 charset-normalizer==3.5.2
PYTHON="$PWD/.venv/bin/python" bash relatorios/reexecutar_tabela8.sh
```

Essas são as versões da conferência, não uma declaração sobre o ambiente original de desenvolvimento. Os testes dos seis diretórios principais funcionam num ambiente Python isolado; os pacotes extras são para as suítes complementares. O roteiro prepara uma cópia temporária, registra as versões e separa os resultados por suíte. Sem a custódia privada, não se executam os três testes complementares dependentes das fotografias urbanas. **Somente** quem dispõe dos originais autorizados no caminho `casos/URBE-01/fotos/originais/` deve usar:

```sh
COM_CUSTODIA=1 PYTHON="$PWD/.venv/bin/python" bash relatorios/reexecutar_tabela8.sh
```

O modo de custódia também requer o registro reservado do operador visual em `work/urbe01_auditoria_visual_v1/registro_operador_visual_urbe01_v1.json`. Ele não acompanha o checkout.

A Tabela 8 da V12 final conta **272 testes distintos**: 28 de domínio, 34 de setorização, 21 de movimento rural, 11 de movimento em mata, 58 de perfil e 120 do protocolo integrado. O pacote de 178 já inclui os 58 do perfil e não constitui um sétimo grupo.

Na [reexecução independente em Linux de 14/11/2026](relatorios/reexecucao_independente_linux_2026-11-14.txt), **271 passaram e um foi ignorado**, sem falhas na Tabela 8. O teste de leitura de imagem do protocolo integrado (`test_real_imageio_pixel_decode_returns_dimensions`) só roda com Swift/ImageIO do macOS e aparece como ignorado nos demais sistemas. As verificações DEV-S (16/16) são separadas da Tabela 8. Fora dela, a suíte complementar `urbe01_avaliacao_pos_abertura_v1` exige uma instalação completa do Pillow no Linux: nessa execução, a ausência da biblioteca nativa libtiff impediu a importação e explica o código de saída 1 do roteiro completo.

## Como ler e, quando autorizado, repetir um caso

**Rota de leitura:** entrada congelada → configuração efetiva → atributos GEO-02 a GEO-05 → ranking e avisos → comparação posterior. Não forneça ao motor as coordenadas de comparação. O mesmo setor pode liderar o BASE e ainda exigir revisão. Em particular, a revisão não significa necessariamente empate, e o diagnóstico de um caso abstido não substitui o BASE completo.

| Caso | Arquivo inicial para consulta | Como reproduzir em ambiente de trabalho separado |
|---|---|---|
| URBE-01 | [Processamento e ranking original](outputs/campo_urbe01/processamento_cego_v1/). A posição simulada ficou em 18º/24 no BASE; estado REVISAR. | `python work/urbe01_processamento_cego_v1/run_urbe01_blind.py --output-dir SAIDA_NOVA_URBE`. Usar o protocolo de perfil deste caso, não substituí-lo pelo PERFIL V3. |
| RURAL-01 | [Processamento e ranking por setor](outputs/campo_rural01/processamento_cego_v1/). A referência comparativa ficou fora do domínio; não recebeu posto. Estado REVISAR. | `python work/rural01_processamento_cego_v1/run_rural01_blind.py --output-dir SAIDA_NOVA_RURAL`. Consultar o movimento e a comparação posterior separadamente. |
| MATA-01 | [BASE abstido e diagnóstico de três componentes](outputs/campo_mata01/processamento_cego_v1/). Não há Top-3 do BASE completo. | `python work/mata01_processamento_cego_v1/run_mata01_blind.py --output-dir SAIDA_NOVA_MATA01`. A rotina de controle registra falta de hidrografia na fonte consultada; não a converte em ausência física de água. |
| MATA-02 | [Ranking BASE](outputs/campo_mata02_mzg2/ensaio_complementar_v2_249/) e [direção confirmada de 249°](outputs/campo_mata02_mzg2/direcao_249_confirmada_v2_20261030/). Referência em 22º/24 no BASE, REVISAR. | `python work/executar_mata02_complementar_v2.py` usa a entrada auditada v2 e grava em **caminho fixo**. Somente em cópia descartável com destino vazio. A pista direcional é comparada separadamente: não é um quinto peso do BASE. |
| MATA-03 | [Ranking BASE](outputs/campo_mata03_km21/ranking_BASE.json) e [comparação posterior do ponto A](outputs/campo_mata03_km21/comparacao_referencia_A_20261103/). Ponto A em 2º/24; estado REVISAR. | `python work/executar_mata03_km21.py` usa a configuração-base de MATA-02, grava em **caminho fixo** e encerra se encontrar a execução concluída. Preparar árvore descartável com destino ainda inexistente e acervo KM21 autorizado; verificar o caminho de leitura das fotos antes de executar. O ponto A não integra a entrada. |

Os comandos identificam os executores científicos, não são um convite a executá-los na árvore de custódia. Para replicar, comece numa cópia com os caminhos de entrada preservados, saídas novas e acesso aos insumos da versão pertinente: dados de vias e hidrografia do OpenStreetMap, arquivos de elevação e mosaicos ESA WorldCover do [lote geoespacial congelado](outputs/sprint2_s2_06_geo05_v33/). Usar dados atuais em vez desse lote seria **nova execução**, não reprodução da original. Alguns programas antigos de documentação e comparação usam caminhos locais e recursos externos; uma cópia sem esses insumos não é uma reprodução de ponta a ponta. As apresentações cartográficas não substituem o ranking nem servem para preencher lacunas de entrada.

## Correspondência com o corpo da V12

| Local na dissertação | O que verificar no pacote |
|---|---|
| §§2.4 e 2.7; Quadros 3–6 | Termos, quatro fases, entradas e componentes; [motor de domínio](work/ext_espacial_buffer_v1/) e [motor de setorização](work/ext_espacial_setores_v1_1/). Os cinco raios foram informados. |
| §§2.8–2.10.2; Quadros 7–9; §2.9.1 | [Evidência das regras](relatorios/evidencia_regras_V12.md); [exemplo RURAL R01-E](relatorios/evidencia_casos_V12.md). O empate no primeiro lugar BASE bloqueia; empate em uma configuração alternativa, sozinho, gera aviso e divide crédito. |
| Equação 2 — escore BASE | [Motor de setorização](work/ext_espacial_setores_v1_1/motor_setorizacao_priorizacao.py), função `_weighted_score` (linha 1140); a [configuração](work/ext_espacial_setores_v1_1/config_setorizacao_priorizacao_v1_1.json) define os pesos. A conferência aritmética de R01-E consta no relatório dos casos. |
| Equação 1 — razão de cobertura; Equação 3 — ajuste de perfil | [Comparação posterior do RURAL-01](outputs/campo_rural01/avaliacao_pos_abertura_v1/): a razão distância/raio é descritiva. [Módulo de perfil](work/perfil_vitima_v3/profile_ranker.py), linhas 880–885: aplicação do peso efetivo da pista; não é o perfil histórico do URBE-01. |
| §§6.1–6.7; Tabelas 2–6 | Entrada, estado, limites das camadas, ordenações, movimento e perfis por caso. Os três primeiros setores não são setores automaticamente atribuídos a equipes. |
| §§2.11, 2.13 e 6.8; Tabela 7; Apêndice B/Quadro 17 | Treze respostas por item; [instrumento e escalas](avaliacao/instrumento.md) e [tabela agregada](avaliacao/frequencias.csv). Sem comentários individuais. |
| §6.9, Tabela 8; §6.10, Quadro 13; Apêndice A/Quadro 16 | [Roteiro de reexecução](relatorios/reexecutar_tabela8.sh), triangulação das evidências e rastreabilidade por objetivo. A concordância dos hashes não transforma testes funcionais em validação operacional. |
| Apêndice C/Quadro 18 | [Verificador de integridade](scripts/verificar_hashes_apendice_c.py), [lista de arquivos e manifestos](relatorios/lista_evidencia_manifestos.csv) e separação entre entrada, saída e comparação. |
| Apêndice D/Quadro 19 | Componentes previstos mas **não utilizados nos cinco casos**: raio adaptativo, índice numérico de qualidade e verificações físico-temporais propostas. O módulo de raio tem testes próprios de engenharia; isso não demonstra seu acionamento em campo. |

## Glossário: como ler as denominações históricas

Os nomes de arquivos, chaves, códigos e horários originais foram preservados para não romper os hashes. As correspondências abaixo explicam a leitura; não constituem um mapa universal de substituição de todo identificador. Na falta de correspondência documentada, conservar o termo original e consultar a configuração ou o manifesto do caso.

| No arquivo histórico | Leitura em português nesta versão |
|---|---|
| ensaio; buffer; wrapper | Caso; domínio espacial; rotina de controle externa. “Domínio” designa a área analisada, não uma distância percorrida. |
| ANATEL; AP; API; CBM | Agência Nacional de Telecomunicações; Amapá; interface de programação de aplicações; Corpo de Bombeiros Militar. Em um identificador específico, interpretar segundo o contexto. |
| D8; DET; DSRM | Vizinhança de oito direções; diagnóstico de detectabilidade; metodologia de Design Science Research. |
| E0; ERB; UPV | Referência espacial inicial; estação rádio-base; último ponto visto. E0 não comprova que alguém foi visto naquele ponto. |
| EXT-ESP; EXT-ESP-BUF; EXT-ESP-SET | Família de extensões espaciais; módulo do domínio; módulo de setorização e priorização. |
| LOC; MCDA; MOV | Eixo de priorização territorial/localização; análise de decisão multicritério; diagnóstico de movimento. LOC não é localização confirmada. |
| OSM; SNIRH; URG | OpenStreetMap; Sistema Nacional de Informações sobre Recursos Hídricos; diagnóstico de urgência. |
| UTC | Tempo Universal Coordenado. “Horário de Brasília” designa o fuso local utilizado quando explicitado; não é sinônimo de UTC. Conservar o instante e o deslocamento originais; um fuso desconhecido continua desconhecido. |

| Termos mantidos no texto | Significado |
|---|---|
| AGTU; IA; DSR; SAR | American Global Tech University; inteligência artificial; Design Science Research; Search and Rescue (busca e salvamento). |
| AIR; AML; CASSAR | Solução aerotransportada de localização celular da Smith Myers; Advanced Mobile Location; Cellular Airborne Sensor for Search and Rescue. São referências de contexto, não equipamentos testados pelo motor. |
| ANA; IBGE; ESA; DJI | Agência Nacional de Águas e Saneamento Básico; Instituto Brasileiro de Geografia e Estatística; European Space Agency; Da-Jiang Innovations. |
| GNSS; RSSI; DEM; SRTM | Global Navigation Satellite System; Received Signal Strength Indicator; Digital Elevation Model; Shuttle Radar Topography Mission. |
| GEO; BASE; Top-3; PERFIL | Componente geoespacial; configuração territorial principal; três primeiros setores no produto especificado; módulo de pistas comportamentais espacializáveis. Os diagnósticos são identificados à parte. |
| GeoJSON; GeoPDF; KML; PDF; QGIS | Formato geoespacial baseado em JSON; documento PDF georreferenciado; Keyhole Markup Language; Portable Document Format; sistema de informação geográfica QGIS. Citar um formato não demonstra integração com um aplicativo. |
| POC; POD; POS | Probability of Containment; Probability of Detection; Probability of Success. Esses conceitos de busca **não são a unidade dos escores BASE**. |

## Fontes e citação

Para citar o trabalho em preparação: Amador, F. A. (2026). *Modelo de inteligência artificial explicável para priorização territorial em busca e salvamento por análise multicritério geoespacial e regras de conhecimento* [Dissertação de mestrado, versão para qualificação]. AGTU University. Ao citar um resultado computacional, acrescentar o **caso, configuração e SHA-256** correspondentes; indicar a revisão consultada do [repositório público](https://github.com/eltonamador/agtu-sar-priorizacao-territorial).

Referências selecionadas da dissertação: [Malczewski (2006), análise multicritério em SIG](https://doi.org/10.1080/13658810600661508); [Russell e Norvig (2020), inteligência artificial](https://aima.cs.berkeley.edu/); [OpenStreetMap contributors, dados cartográficos](https://www.openstreetmap.org/); [Zanaga et al. (2022), ESA WorldCover 2021 v200](https://doi.org/10.5281/zenodo.7254221). São créditos das fontes, não licença geral para redistribuir fotos, registros de campo, vídeo ou insumos de terceiros.
