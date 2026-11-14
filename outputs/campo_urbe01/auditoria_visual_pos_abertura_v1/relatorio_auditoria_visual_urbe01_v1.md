# Auditoria visual retrospectiva do URBE-01

## Finalidade e limite de uso

Esta auditoria foi executada após a abertura da posição de referência. Por isso, sua classificação é **retrospectiva, descritiva e não confirmatória**. O subprocesso visual não consultou a posição revelada, não recalculou setores, pesos ou rankings e não alterou as saídas LOC, URG ou DET anteriormente congeladas.

## Integridade e extração

- fotografias conferidas: **10 de 10**;
- fotografias decodificadas com dimensões válidas: **10 de 10**;
- imagens espacialmente qualificadas: **A05**;
- imagens mantidas apenas como contexto: **A00, A02, A03, A04, A06, A07, A08, A09, A10**;
- distância das câmeras ao ponto inicial: entre **11,32 m** e **54,74 m**.

Os metadados completos contêm geotags e permanecem na subpasta `restrito`. Cópias destinadas à dissertação, à qualificação ou à circulação externa devem ser sanitizadas.

## Vínculo espacial obtido

Apenas a fotografia A05, registrada como tomada vertical do drone, permitiu calcular footprint conservador. O vínculo recebeu a classe `APROXIMADO_METADADOS` e raio de **25,238859 m**. O círculo intersectou os oito setores do anel interno:

`URBE-01::URBE-01-E0::R01::E, URBE-01::URBE-01-E0::R01::N, URBE-01::URBE-01-E0::R01::NE, URBE-01::URBE-01-E0::R01::NW, URBE-01::URBE-01-E0::R01::S, URBE-01::URBE-01-E0::R01::SE, URBE-01::URBE-01-E0::R01::SW, URBE-01::URBE-01-E0::R01::W`.

Como a imagem cobre todas as direções de R01, ela demonstra aquisição e contexto visual nas proximidades do ponto inicial, mas **não diferencia uma hipótese direcional**, não sustenta R02 ou R03 e não melhora o ranking LOC.

## Registros que exigem cautela

As declarações cardinais e os metadados de direção ou posição precisam de revisão em: **A02, A03, A04, A07**. O rumo de voo DJI não comprova, por si, o eixo óptico, e o campo de inclinação do gimbal permaneceu 0° tanto em imagens verticais quanto oblíquas. Por isso, as imagens de solo e as tomadas oblíquas não receberam footprint automático.

Há pessoas incidentais, placas e identificadores de imóveis em parte do conjunto. A afirmação metodologicamente correta é que o alvo não foi incluído por desenho; isso não equivale a afirmar que nenhuma pessoa aparece nas fotografias.

## Conclusão

O Conjunto A validou identidade dos arquivos, custódia, decodificação, extração de metadados e uma vinculação espacial limitada ao entorno imediato do ponto inicial. Seu benefício nesta rodada é documental e metodológico. Ele não altera o resultado negativo já obtido na avaliação pós-abertura e não deve ser apresentado como cobertura dos candidatos, do corredor de deslocamento ou da posição encontrada.
