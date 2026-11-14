# Realinhamento local para a banca — 14/11/2026

**Conclusão.** A estrutura de consulta e os recibos de verificação foram preparados com base no corpo da dissertação entregue às 16h21. Os sete identificadores do Apêndice C coincidem, e os testes executados com a custódia autorizada têm os mesmos nomes, ordem e resultados antes e depois da organização. Nenhum dos cinco casos foi reprocessado. A preparação local não equivale a publicação no GitHub.

## O que mudou e onde conferir

| Entrega | Evidência |
|---|---|
| Distribuição separada da raiz privada, com seleção explícita em vez de copiar a pasta de pesquisa inteira | [Guia, glossário e mapa entre texto e arquivos](../README.md). Para cada caso indica o ponto de entrada, a saída principal e os limites de reprodução. O arquivo de 14/11 às 16h21 prevalece sobre a V11. |
| Motores, configurações, dados e saídas preservados, inclusive nomenclatura histórica | [Inventário arquivo a arquivo](integridade_distribuicao.csv): **530 arquivos** em work/ e outputs/, com tamanho e SHA idênticos aos da origem, inclusive o ZIP histórico fechado de setorização. [143 entradas de manifestos](lista_evidencia_manifestos.csv); entradas repetidas entre manifestos não são novos arquivos. [Sete identificadores do Apêndice C](hashes_apos_realinhamento.txt). |
| Leitura dos caminhos antigos em outro computador | [Adaptador da verificação](../scripts/verificar_dev_local.py): substitui somente a resolução de caminhos absolutos históricos, em memória. Uma primeira tentativa de verificação após a cópia fez 15/16 porque ainda consultava o caminho do Mac de origem. Com a leitura local, **16/16**. Nenhum manifesto nem rotina de cálculo foi editado. |
| Verificação do parecer e dos dados | [Confere/não confere](verificacao_parecer_V12_2026-11-14.md), [entradas e trechos do código dos testes de PRIORIZADO](evidencia_regras_V12.md), [postos, Top-3 e exemplo numérico](evidencia_casos_V12.md). |
| Avaliação profissional | [Instrumento](../avaliacao/instrumento.md), [agregados da Tabela 7](../avaliacao/frequencias.csv), vídeo demonstrativo localizado. Nenhuma resposta individual, inclusive aberta, nem horário de envio incluído. |
| Fotografias organizadas sem alterar metadados | [Inventário resumido, figuras e triagem](acervo_fotografico.md); cinco guias em casos/. Originais e índices completos, inclusive coordenadas e sinalização por arquivo, ficam locais e ignorados. |

## Execução e comparação

| Verificação | Antes (custódia) | Depois (custódia) | Cópia dos arquivos versionáveis, sem custódia |
|---|---:|---:|---:|
| Seis diretórios dos módulos da Tabela 8 | 272 passaram | 272 passaram | 272 passaram |
| Agrupamento histórico integrado, com sobreposição; **não somar** | 178 passaram | 178 passaram | 178 passaram |
| Suítes complementares e históricas, fora da Tabela 8 | 208 passaram | 208 passaram | 205 passaram; 3 dependem de arquivos privados |
| Verificações independentes DEV-S | 16/16 | 16/16 | 16/16 |

**Recibos completos:** [antes](reexecucao_testes_2026-11-14.txt), [depois](testes_apos_realinhamento.txt) e [modo sem dados privados](testes_modo_publico.txt). Python 3.12.14, ambiente temporário novo por rodada; versões do sistema, Swift e dependências registradas nas próprias saídas. Nos recibos distribuídos foram substituídos apenas os prefixos pessoais e os caminhos temporários; os logs originais permanecem privados. Os três testes extras do URBE-01 conferem a revisão fotográfica (divergência direcional, isolamento da referência e determinismo). Não houve falha registrada nas três rodadas finais. Não apresentar as três execuções somadas como testes diferentes.

**Leitura da Tabela 8:** 329 é a soma das linhas históricas, não a contagem de testes atuais sem repetição. Os diretórios atuais contêm 28 + 34 + 21 + 11 + 58 + 120 = **272**. A linha histórica de perfil traz 57 e a integração de 178 inclui os 58 de perfil. Documentar a diferença é mais fiel do que ajustar o código ou o relatório para produzir 329. Nos testes de setorização, dois métodos exigem expressamente PRIORIZADO e outros três o produzem ao testar propriedades diferentes. Nenhum dos cinco casos recebeu esse estado.

## Inventário, exclusões e terminologia

O inventário local da raiz de trabalho contém 273 itens ou grupos com caminho, tamanho e motivo da seleção (`_arquivo/historico/inventario_raiz_V12.csv`). O inventário científico versionado acima identifica os arquivos efetivamente incluídos; não confundir uma proposta histórica de inclusão com a distribuição. O material privado não foi transferido em bloco, nem apagado.

| Destino | Exemplos e motivo |
|---|---|
| Arquivo local ignorado, `_arquivo/historico/` | Formulário A/B superado, síntese intermediária dos cinco casos, README proposto, inventário de triagem e registro exploratório de dependências. Preservados para memória, não para orientar o leitor da V12. |
| Arquivo local ignorado, `_arquivo/` | Índice fotográfico global, levantamento de termos na origem e recibos brutos, inclusive a tentativa intermediária de relocalização. |
| Permanece apenas na origem de pesquisa ou em custódia privada | Versões da dissertação, parecer do orientador, documentos editoriais, fontes sincronizadas, históricos pessoais, saídas intermediárias não necessárias, dados individuais e arquivos de coleta. Não se moveram os originais: esta distribuição nasceu separada, sem histórico Git a limpar. |
| Mantido apesar do nome histórico | Perfil anterior ao V3 do URBE-01, testes de versões anteriores usados na conferência, erratas e documentos internos provenientes dos pacotes. Os relatórios de engenharia são evidência contemporânea de suas versões, **não** documentação normativa da V12. |

[Índice das denominações históricas](termos_historicos.csv): distingue código, documentação histórica e dados/manifestos; registra caminhos e primeiras ocorrências por termo. O levantamento procurou também títulos numerados nos textos, sem presumir que toda ocorrência de “Tabela” seja uma referência à dissertação. Na origem, a busca contemplou os arquivos de texto selecionados de work/ e outputs/ de até 8 MiB e até as primeiras 12 mil linhas; não é varredura de binários ou OCR. A leitura vigente usa o README e os relatórios desta entrega. Abertura em modo de leitura e cópia em outra plataforma não devem normalizar terminadores de linha de objetos congelados.

## Estado Git e o que falta para acesso externo

A pasta histórica informada pelo pesquisador não era um clone Git. A consulta somente de leitura ao endereço indicado não devolveu referências de branches/tags; por isso não havia commit anterior demonstrável para citar ou substituir. Criou-se distribuição em separado no branch **realinhamento-v12**, com origin apontando para o endereço da Seção 2.12. O primeiro commit é local. Para identificar sem ambiguidade o próprio commit que contém este relatório: `git rev-parse HEAD`; para alterações e branch: `git status --short --branch`; para commits sem correspondente entre as referências locais do remoto: `git rev-list --count HEAD --not --remotes=origin`. Não houve push.

**Antes de tornar público:** decidir sobre as imagens sinalizadas (incluindo coordenadas e placas), as camadas cartográficas e os direitos sobre o vídeo e sua narração. Alguns registros científicos preservam caminhos pessoais antigos e geolocalização; se a divulgação não for autorizada, restringir o objeto ou produzir um derivado identificado por outro hash, sem editar o original para fazê-lo parecer idêntico. Confirmar o vídeo efetivamente apresentado. Somente depois da publicação e de testar o acesso sem credenciais será possível afirmar à banca que o endereço permite baixar esta revisão.
