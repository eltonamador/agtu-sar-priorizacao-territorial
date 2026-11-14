# Relatorio de execucao — MATA-01 territorial cego v1.0

## Resultado

- classificacao: diagnostica e nao confirmatoria;
- situacao: revisar;
- ponto processado: MATA-01-E0;
- dominio circular recebido: 5.000 m;
- origem do dominio: informado pelo pesquisador sob incerteza alta;
- buffer adaptativo: nao executado por ausencia de qualidade de deteccao;
- imputacao de qualidade: nao;
- setores produzidos: 24;
- perfil, pista ao Norte e habito de buscar agua: nao aplicados ao ranking territorial v1;
- fotografias: nao aplicadas ao ranking quantitativo;
- posicao declarada do alvo simulado usada no processamento: nao.

- GEO-03: indisponivel (zero feicoes OSM no dominio);
- BASE original: abstido, sem Top-3;
- grade raster: 3.600 amostras por setor, suporte nominal aproximado de 30 m;

## Top 3 territorial — BASE-DISPONIVEIS (diagnostico separado)

| Area | Setor | Posto | Escore | Direcao | Anel | GEO-02 | GEO-03 | GEO-04 | GEO-05 |
|---|---|---:|---:|---|---|---:|---:|---:|---:|
| AP1 | MATA-01::MATA-01-E0::R01::S | 1 | 0.531415944 | S | R01 | 0.551161 | — | 0.668221 | 0.398278 |
| AP2 | MATA-01::MATA-01-E0::R02::SW | 2 | 0.508058394 | SW | R02 | 0.527237 | — | 0.655249 | 0.367292 |
| AP3 | MATA-01::MATA-01-E0::R01::E | 3 | 0.505515616 | E | R01 | 0.469477 | — | 0.684819 | 0.405319 |

## Reprodutibilidade e QA

- duas execucoes independentes: **PASS**;
- arquivos cientificos identicos: True;
- gates de QA: **24/24 (PASS)**.

## Interpretacao e limites

AP1, AP2 e AP3 pertencem somente ao BASE-DISPONIVEIS, cujo peso foi renormalizado para GEO-02 0,40, GEO-04 0,26666666666666666 e GEO-05 0,3333333333333333. Essa analise nao equivale ao BASE completo. Os escores nao representam probabilidade de presenca, precisao de localizacao, deteccao ou comando operacional. A diferenca temporal entre OSM, WorldCover, SRTM e o ensaio exige confirmacao em campo. Em especial, cobertura aerea e relevo regional nao revelam por si so vegetacao emaranhada, solo encharcado, barrancos estreitos, quedas de arvores ou passagem efetiva sob o dossel.

## Sintese de cobertura WorldCover no dominio amostrado

- celulas/amostras validas: 86400;
- classe 80 (agua): 317 (0.367%);
- classe 90 (area umida): 9895 (11.453%);
- essas classes pertencem a GEO-05 e nao preenchem artificialmente GEO-03.
