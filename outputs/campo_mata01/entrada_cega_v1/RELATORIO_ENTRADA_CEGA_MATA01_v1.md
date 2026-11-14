# Relatório de entrada cega — MATA-01 v1

## Situação

A entrada do cenário MATA-01 foi preservada e congelada sem posição de alvo. O conjunto autorizado contém uma fotografia de solo e três fotografias aéreas RGB. Os arquivos originais foram copiados sem alteração e conferidos por SHA-256.

## Ponto e domínio espacial

- ponto inicial informado: `-0.172222, -51.430278`;
- papel operacional: **Ponto Inicial de Planejamento**;
- horário de referência do evento: 21/10/2026 às 14h20 UTC−03;
- horário de captura posterior da coordenada pelo iPhone: 22/10/2026 às 16h39min08s UTC−03;
- raio operacional informado: **5.000 m**;
- área circular correspondente: aproximadamente **78,54 km²**;
- precisão horizontal da coordenada inicial: não disponível;
- presença atual da pessoa no ponto: não afirmada.

O raio foi aceito como domínio de planejamento informado pelo pesquisador. Ele não é resultado do motor de buffer adaptativo, pois não existe qualidade de detecção celular ou aerotransportada para este caso. Preencher essa variável artificialmente introduziria um dado inexistente.

## Revisões temporais

### Revisão 1 — contexto de campo

- corte: 22/10/2026 às 16h40 UTC−03;
- tempo transcorrido: 26 h 20 min;
- finalidade: produzir o LOC principal e registrar o conjunto visual disponível até o corte.

As três fotografias aéreas foram capturadas entre 16h21min56s e 16h22min39s, aproximadamente 26 h 02 min após o horário inicial. O horário de 16h28 permanece apenas como anotação aproximada da sessão, não como horário desses arquivos.

### Revisão 2 — atualização operacional

- corte: 23/10/2026 às 15h41 UTC−03;
- tempo transcorrido: 49 h 21 min;
- efeito: LOC inalterado na ausência de nova pista espacial; atualização apenas de urgência, atualidade das evidências e estado operacional.

O tempo transcorrido não amplia automaticamente o raio nem cria nova direção.

## Metadados visuais verificados

| Arquivo | Aquisição | Posição da câmera/aeronave | Orientação útil | Uso permitido |
|---|---|---|---|---|
| `MZG1Solo_0442.HEIC` | iPhone 16; 22/10 às 16h39min08s | `-0.172270, -51.430175`; erro horizontal 4,75 m | 81,64° verdadeiro | contexto direcional; sem footprint |
| `...0001_V.JPG` | DJI M3T RGB; 16h21min56s | aprox. `-0.172111, -51.430561` | nadiral; pitch −89,9° | vínculo espacial apenas aproximado por metadados |
| `...0006_V.JPG` | DJI M3T RGB; 16h22min23s | aprox. `-0.172110, -51.430563` | oblíqua para oeste | contexto visual; sem alcance defensável |
| `...0011_V.JPG` | DJI M3T RGB; 16h22min39s | aprox. `-0.172112, -51.430562` | oblíqua para sudeste | contexto visual; sem alcance defensável |

As altitudes do drone foram preservadas como metadados brutos. Não foram interpretadas como elevação do terreno ou altura AGL. Os arquivos são RGB; não foi utilizado canal térmico. O telêmetro não registrou um alvo: distância e coordenadas LRF estão zeradas.

## Leitura visual defensável

O conjunto mostra mosaico de mata fechada, áreas abertas, bordas de vegetação, superfícies visualmente compatíveis com umidade e, na fotografia nadiral, uma edificação e uma via não pavimentada. O conjunto não permite concluir a passabilidade do sub-bosque, a profundidade da água, a resistência real do solo ou a ausência de uma pessoa sob o dossel.

A redação correta é **“nenhuma figura humana é discernível nas imagens”**. Isso não equivale a afirmar que não havia pessoa no terreno. A frase “não aparecem estradas nem construções” somente poderia se referir à fotografia de solo; ela é incorreta para o conjunto aéreo.

## Pistas e limites do ajuste por perfil

A única pista espacial autorizada para teste no PERFIL V3 é o relato de marcas de botas saindo do roçado em direção ao Norte. Ela foi codificada de modo conservador como direção `0° ± 22,5°`, natureza `RELATADO` e confiança `MEDIA`.

Os demais elementos permanecem contextuais ou pertencem a URG/DET:

- familiaridade e experiência do agricultor;
- ferramentas e almoço deixados na roça;
- costume de acompanhar bordas ou buscar água;
- vestuário laranja;
- possível esgotamento da água, cansaço e desidratação;
- fumaça distante sem localização ou vínculo comprovado.

O igarapé habitual não recebe peso espacial até que um trecho específico seja identificado. A fumaça não orienta o ranking sem georreferenciamento e relação comprovada.

## Resultado da auditoria

- 4/4 arquivos preservados e com hashes conferidos;
- 13/13 verificações de entrada aprovadas;
- duas revisões temporais encadeadas;
- posição de alvo ausente;
- imagens excluídas do cálculo numérico de LOC;
- entrada pronta para setorização territorial e, depois, ajuste limitado do PERFIL V3.

