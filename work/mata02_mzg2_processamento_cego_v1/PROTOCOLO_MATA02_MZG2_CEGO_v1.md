# Protocolo cego MATA-02/MZG2 — versão 1.0

## 1. Finalidade e classificação

Este protocolo congela a entrada e as regras do ensaio MATA-02/MZG2 antes de qualquer processamento e sem coordenada de alvo. O ensaio é classificado como **cenário controlado semissintético em território real**: o território, a coordenada inicial e as fotografias são reais; a ocorrência de desaparecimento e o intervalo de 17 horas pertencem somente ao cenário hipotético.

O ensaio não representa uma ocorrência real de pessoa desaparecida e não pode, isoladamente, comprovar eficácia operacional ou probabilidade de localização.

## 2. Entrada espacial congelada

- Cenário: `MATA-02`.
- Local de campo: `MZG2`.
- Referência de planejamento: `MATA-02-E0`.
- Latitude: `-0.1591666667`.
- Longitude: `-51.395`.
- Sistema de referência: `EPSG:4326`.
- Raio informado: `6000 m`.
- Método do raio: domínio operacional direto, sem buffer adaptativo nesta execução.
- Origem da coordenada: captura da bússola do iPhone.
- Acurácia horizontal: não disponível.
- Data da captura da tela: não disponível.
- Horário exibido na tela: `15:59`; esse horário não é horário de desaparecimento.

O ponto `MATA-02-E0` é um ponto inicial de planejamento. Ele não é coordenada do alvo nem coordenada de encontro.

## 3. Separação temporal obrigatória

Os horários presentes na captura da bússola e nos metadados ou sobreposições das fotografias descrevem capturas reais de campo. O intervalo de `17 h` é exclusivamente uma condição hipotética do cenário.

É proibido:

1. inferir o horário do desaparecimento a partir do horário das fotografias;
2. tratar a diferença entre capturas como tempo real de deslocamento de uma pessoa;
3. apresentar as 17 horas como fato observado em campo.

O horário real do evento permanece nulo, porque não houve ocorrência real. Para organizar exclusivamente o cenário hipotético, foram declarados `2026-10-22 15:30` como último registro simulado e `2026-10-23 08:30` como momento de avaliação simulada, ambos em `America/Belem`; esses valores não foram inferidos das fotografias e não entram no ranking BASE.

## 4. Fronteira do BASE

O processamento BASE pode consumir somente:

1. `MATA-02-E0`;
2. raio informado de `6000 m`;
3. GEO-02 — vias;
4. GEO-03 — hidrografia;
5. GEO-04 — declividade;
6. GEO-05 — cobertura do solo;
7. setorização congelada em três anéis e oito direções;
8. pesos fixos `0,30 / 0,25 / 0,20 / 0,25`;
9. 3.600 amostras determinísticas por setor.

O BASE não pode consumir fotografias, coordenadas de câmera do drone, perfil, saúde, vestuário, pistas comportamentais ou direcionais, intervalo hipotético de 17 horas, coordenada do alvo ou referência posterior de encontro.

As coordenadas registradas nas imagens do drone são posições da câmera no instante da captura. Elas não substituem `MATA-02-E0` e não representam o alvo.

## 5. Setorização, amostragem e pesos

O domínio circular é dividido em 24 setores: três anéis de área equivalente e oito direções. Não há preferência direcional, penalidade por anel ou pista aplicada ao ranking BASE.

Cada setor recebe 60 estratos radiais por 60 estratos angulares, totalizando 3.600 amostras. Para o raio de 6 km, a área nominal de cada setor é `4.712.388,980385 m²`; a área nominal por amostra é `1.308,996939 m²`, correspondente a suporte linear aproximado de `36,180061 m`. Esses valores decorrem apenas da geometria e não mudam os pesos ou as regras do motor.

Os pesos permanecem congelados:

| Componente | Peso |
|---|---:|
| GEO-02 | 0,30 |
| GEO-03 | 0,25 |
| GEO-04 | 0,20 |
| GEO-05 | 0,25 |

## 6. Regra de hidrografia

A condição da hidrografia será determinada durante a execução; este protocolo não presume que ela esteja presente ou ausente.

### Ramo H1 — fonte carregada com feições no domínio

Se GEO-03 for carregada com sucesso e houver pelo menos uma feição que intercepte o domínio, o BASE completo é executado com os quatro pesos originais. Essa é a saída principal do ensaio.

### Ramo H2 — fonte carregada sem feições no domínio

Se GEO-03 for carregada com sucesso, mas nenhuma feição interceptar o domínio, o BASE original fica **ABSTIDO**, com o motivo `GEO03_SEM_FEICOES_INTERSECTANTES`. Pode ser emitido um ranking separado sobre módulos disponíveis, claramente identificado como diagnóstico e não equivalente ao BASE.

### Ramo H3 — fonte indisponível ou com erro

Se GEO-03 não puder ser carregada, estiver ausente ou produzir erro, o BASE original fica **ABSTIDO**, com o motivo `GEO03_FONTE_INDISPONIVEL`. Essa condição não pode ser interpretada como ausência física de água. Um diagnóstico sobre módulos disponíveis pode ser gerado separadamente.

Quando utilizado, o diagnóstico de módulos disponíveis usa `GEO02=0,40`, `GEO03=0`, `GEO04=0,26666666666666666` e `GEO05=0,3333333333333333`. Ele nunca substitui nem recebe o rótulo de BASE completo.

## 7. Cegamento e referência do alvo

Não há coordenada de alvo fornecida nesta versão. O motor, a configuração e qualquer futuro invólucro não podem imputar uma coordenada.

Se uma referência de alvo vier a ser declarada posteriormente, ela deve ser registrada em artefato separado, com data de abertura. A entrada congelada, os arquivos de configuração e as saídas originais não podem ser reescritos.

## 8. Saídas mínimas previstas

Uma execução futura deve registrar, no mínimo:

- configuração efetivamente utilizada e seu hash;
- fontes geográficas, datas ou versões e hashes quando aplicável;
- ramo hidrológico acionado e evidência da decisão;
- 24 setores com componentes, escore e ordem quando houver ranking;
- status do BASE: executado ou abstido;
- código de motivo de abstenção, quando aplicável;
- eventual diagnóstico de módulos disponíveis em arquivo separado;
- mapa e tabela com o mesmo identificador de execução;
- declaração de que fotografias, perfil, pistas e coordenada do alvo não foram consumidos.

## 9. Estado desta versão

Esta versão contém somente entrada, partição de evidências, configuração e protocolo. Não registra execução, resultado, mapa, ranking, teste ou validação. O motor e o invólucro não foram modificados por este protocolo.
