# Protocolo congelado — MATA-01 territorial cego v1.0

## Finalidade

Produzir uma particao espacial e uma ordenacao territorial reprodutivel para o cenario MATA-01 sem usar qualquer posicao declarada do alvo simulado. O procedimento recebe o ponto inicial de planejamento, o dominio de 5 km informado pelo pesquisador e as camadas geograficas locais ja consolidadas no projeto.

## Entradas autorizadas

- cenario: `MATA-01`;
- candidato inicial: `MATA-01-E0`;
- latitude: `-0.172222`;
- longitude: `-51.430278`;
- dominio circular informado: `5.000 m`;
- GEO-02: vias e trilhas do OpenStreetMap;
- GEO-03: hidrografia do OpenStreetMap;
- GEO-04: relevo derivado de SRTM HGT;
- GEO-05: cobertura e uso do solo do ESA WorldCover 2021 v200.

O ponto e tratado como ponto inicial de planejamento registrado apos o evento, e nao como prova de um ultimo ponto visto contemporaneo. O raio de 5 km representa um dominio operacional declarado sob incerteza alta. Ele nao foi calculado pelo motor de buffer adaptativo porque a qualidade da deteccao nao foi fornecida e nenhum valor foi inventado. O campo `adaptive_radius_m` aparece apenas para compatibilidade com o contrato tecnico do motor setorial; semanticamente, continua sendo um dominio direto da fonte.

## Regras congeladas

1. O circulo e dividido em tres aneis de area equivalente e oito direcoes, totalizando 24 setores.
2. Cada setor recebe atributos territoriais do motor `EXT-ESP-SET-v1.1`, importado sem alteracao.
3. A consulta espacial mostrou zero feicoes OSM de hidrografia interceptando o dominio. Ausencia de mapeamento nao e interpretada como ausencia de agua ou como condicao favoravel. GEO-03 fica `NAO_DISPONIVEL`, a completude maxima e 0,75 e o `BASE` original fica formalmente `ABSTIDO`, sem Top-3.
4. Uma segunda saida, independente e apenas diagnostica, usa o protocolo `MATA01-BLIND-SET-AVAILABLE-v1.0` (`BASE-DISPONIVEIS`). Os pesos originais dos modulos observaveis sao renormalizados exatamente para GEO-02 0,40, GEO-04 0,26666666666666666 e GEO-05 0,3333333333333333. Essa saida nao e equivalente ao BASE completo.
5. Relevo e cobertura sao amostrados em grade polar estratificada deterministica de area equivalente, com 60 estratos radiais por 60 angulares: 3.600 amostras por setor. Cada amostra representa aproximadamente 909 m2, suporte linear nominal de 30,15 m. O metodo e uma aproximacao de grade de 30 m, nao um censo de pixels.
6. Perfil, pista direcional ao Norte, habito de buscar agua, fotografias e observacoes de campo nao alteram este ranking territorial inicial.
7. AP1, AP2 e AP3 existem somente para `BASE-DISPONIVEIS` e sao areas analiticas para revisao humana; nao sao probabilidades de presenca, deteccoes, rotas determinadas ou ordens operacionais.
8. Empates preservam o posto compartilhado. A ordenacao pelo identificador serve apenas para apresentacao deterministica.
9. A posicao declarada do alvo simulado, caso exista, permanece fora de todas as etapas desta execucao.
10. Todos os resultados permanecem em `REVISAR`, pois dependem de cartografia publica, amostragem raster e confirmacao humana em campo.

## Limites temporais e territoriais

- OpenStreetMap: instantaneo local com base em `2026-08-17T17:01:35Z`; cobertura voluntaria possivelmente incompleta.
- ESA WorldCover: produto de 2021; nao descreve necessariamente alteracoes ocorridas ate 2026.
- SRTM: modelo de elevacao adequado para relevo regional; nao representa vegetacao emaranhada, troncos caidos, barrancos estreitos, solo encharcado ou transitabilidade sob o dossel.
- A amostragem de 3.600 pontos por setor e substancialmente mais densa que o padrao do motor, mas ainda nao e censo de pixels e nao converte as camadas em probabilidades.
- O WorldCover indica classes de agua/area umida no dominio, mas essa evidencia permanece em GEO-05; ela nao preenche artificialmente o modulo GEO-03 ausente e nao comprova curso d'agua transitavel ou barreira atual.

## Condicao de uso

O pacote e diagnostico, nao confirmatorio e destinado a apoio a decisao supervisionado. O BASE original esta abstido. O Top-3 de BASE-DISPONIVEIS deve ser lido apenas como triagem territorial provisoria baseada nos tres modulos disponiveis. O resultado deve ser combinado posteriormente com perfil, pistas, atualizacoes da equipe e confirmacao de campo, mantendo separadas localizacao analitica, urgencia e detectabilidade.
