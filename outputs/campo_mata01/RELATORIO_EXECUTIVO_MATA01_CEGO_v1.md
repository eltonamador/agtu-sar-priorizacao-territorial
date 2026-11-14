# Relatório executivo — processamento cego MATA-01 v1

## 1. Síntese do resultado

O cenário MATA-01 foi processado sem acesso a qualquer posição declarada do alvo. A execução foi organizada em quatro etapas independentes e rastreáveis: entrada e metadados, triagem territorial, modelagem relativa do custo de deslocamento e ajuste limitado pelo perfil da pessoa desaparecida.

O modelo territorial completo não produziu prioridade, porque a camada hidrográfica do OpenStreetMap não contém feições dentro do domínio de 5 km. Essa ausência foi tratada como falta de informação, e não como ausência de água ou facilidade de passagem. Uma análise separada, denominada BASE-DISPONÍVEIS, foi executada apenas com os módulos efetivamente disponíveis: vias e trilhas, relevo e cobertura do solo. Essa análise é diagnóstica, não equivale ao BASE completo e permanece sob revisão humana.

O Top-3 territorial diagnóstico foi:

1. R01-S, anel interno ao Sul, escore 0,531416;
2. R02-SW, anel intermediário a Sudoeste, escore 0,508058;
3. R01-E, anel interno a Leste, escore 0,505516.

Esses escores expressam prioridade analítica relativa entre setores. Eles não são probabilidades de presença, estimativas de precisão, detecções nem ordens operacionais.

## 2. Entradas congeladas

- ponto inicial de planejamento: -0,172222, -51,430278;
- referência temporal do evento: 21/10/2026, 14h20, UTC−03;
- domínio circular informado: 5.000 m, equivalente a aproximadamente 78,54 km²;
- origem do raio: informado pelo pesquisador sob incerteza alta;
- buffer adaptativo: não executado, pois não existe qualidade de detecção celular ou aerotransportada para o caso;
- posição declarada do alvo: ausente e não utilizada;
- fotografia de solo: 22/10/2026, 16h39min08s, UTC−03;
- fotografias DJI M3T: 22/10/2026, entre 16h21min56s e 16h22min39s, UTC−03.

O ponto foi classificado como Ponto Inicial de Planejamento registrado após o evento. Ele não foi apresentado como último ponto visto contemporâneo nem como prova de que a pessoa ainda estivesse ali.

## 3. Leitura das imagens

As imagens mostram um mosaico de mata fechada, áreas abertas, bordas de vegetação, superfícies visualmente compatíveis com umidade, uma edificação e uma via não pavimentada na fotografia nadiral. Nenhuma figura humana é discernível. Essa afirmação não significa que não havia pessoa sob o dossel ou fora do pequeno campo de visão das fotografias.

As fotografias foram usadas como evidência contextual. Não foram empregadas como ortomosaico, não cobrem o domínio de 5 km e não entraram numericamente no ranking. Imagens RGB aéreas não permitem inferir, isoladamente, a passabilidade do sub-bosque, a profundidade da água, a resistência do solo ou a presença de obstáculos estreitos.

## 4. Base territorial e motivo das áreas diagnósticas

No domínio amostrado, o ESA WorldCover 2021 indicou aproximadamente 80,1% de cobertura arbórea, 11,5% de área úmida herbácea, 8,0% de vegetação herbácea e 0,4% de água permanente. O SRTM representou o relevo regional, mas não barrancos estreitos, árvores caídas ou emaranhados de vegetação. O OpenStreetMap forneceu vias, mas nenhuma feição hidrográfica dentro do domínio.

A análise BASE-DISPONÍVEIS renormalizou os pesos para:

- GEO-02, vias e trilhas: 0,40;
- GEO-04, relevo: 0,2666667;
- GEO-05, cobertura do solo: 0,3333333.

Os três setores destacados resultaram da combinação desses fatores:

| Área | Setor | GEO-02 | GEO-04 | GEO-05 | Interpretação resumida |
|---|---|---:|---:|---:|---|
| AP1 | R01-S | 0,551 | 0,668 | 0,398 | melhor composição relativa entre acesso mapeado, relevo e cobertura no anel interno |
| AP2 | R02-SW | 0,527 | 0,655 | 0,367 | composição favorável no anel intermediário, apesar da maior distância |
| AP3 | R01-E | 0,469 | 0,685 | 0,405 | relevo relativamente mais favorável e cobertura compatível com a triagem |

A diferença entre AP1 e AP2 é pequena, cerca de 0,0234. Por isso, a saída permanece em REVISAR e não sustenta a interpretação de um único setor certo.

## 5. Obstáculos e custo relativo de deslocamento

O módulo de movimento avaliou 87.253 células de aproximadamente 30 m em seis cenários: deslocamento com rede viária disponível e fora da rede, cada um sob resistências suave, base e forte. Foram gerados 48 corredores diagnósticos predefinidos.

A camada viária alcançou 1.013 células. Classes de água e área úmida do WorldCover apareceram em 10.265 células, mas foram tratadas somente como proxy hídrica ou úmida potencial. Elas não foram transformadas em igarapé confirmado e não substituíram a hidrografia ausente.

Os obstáculos descritos em campo ainda não têm geometria espacial suficiente. Consequentemente, o fator de obstáculo de campo permaneceu neutro, igual a 1. Isso significa “sem ajuste por falta de localização”, e não “passagem livre”. Os tempos transcorridos de 26 h e 49 h permaneceram como contexto: não foram convertidos em distância, raio ou isócrona sem uma função calibrada.

## 6. Efeito do perfil e da pista ao Norte

A única pista comportamental usada quantitativamente foi o relato de marcas de botas saindo do roçado em direção ao Norte. Ela foi codificada como 0° ±22,5°, natureza RELATADA, confiança MÉDIA e fator de qualidade q=2/3.

Com λ nominal de 0,05 e 0,10, os pesos efetivos foram 0,033333 e 0,066667. O Top-3 permaneceu R01-S, R02-SW e R01-E. Entretanto, os setores Norte subiram de forma consistente:

- R01-N: posto 22 no territorial, 17 com λ=0,05 e 14 com λ=0,10;
- R02-N: posto 24, depois 22 e 18;
- R03-N: posto 23, depois 21 e 16.

Esse comportamento é coerente com o desenho do módulo: a pista influenciou apenas os setores angularmente compatíveis, mas não recebeu força suficiente para forçar uma troca do vencedor. A anamnese entrou como evidência adicional e auditável, sem apagar os sinais territoriais.

O hábito de buscar água, a fumaça distante, a familiaridade com a área, a roupa, as fotografias e o tempo de desaparecimento não receberam peso em LOC. O hábito relacionado ao igarapé poderá ser espacializado somente quando houver um trecho específico e georreferenciado. Urgência e detectabilidade permanecem módulos separados.

## 7. Conclusão metodológica

MATA-01 demonstra uma função relevante do artefato: organizar evidências incompletas, explicitar ausências de dados, separar hipóteses e produzir áreas para revisão sem transformar incerteza em certeza. O resultado mais defensável não é afirmar onde a pessoa estaria, mas mostrar por que certos setores merecem atenção, quanto cada evidência alterou a ordenação e em que pontos o sistema deve se abster.

Para eventual operação real, AP1–AP3 devem ser tratados como triagem inicial; os setores Norte devem permanecer visíveis por causa da pista; e a equipe deve atualizar o modelo com confirmação de trilhas, drenagens, áreas encharcadas, barreiras e novas pistas de campo. A saída continua diagnóstica, não confirmatória e sujeita à decisão do comandante da busca.

## 8. Verificação e rastreabilidade

- entrada: 13/13 verificações aprovadas;
- territorial: 24/24 verificações aprovadas, 86.400 amostras raster e repetição determinística;
- movimento: 11/11 testes e 19/19 verificações aprovadas;
- perfil: 20/20 verificações, 2/2 testes do construtor e 58/58 testes do motor original aprovados;
- posição de alvo usada: não;
- consulta externa para obter imagem de satélite: não;
- situação final: REVISAR, diagnóstico não confirmatório.

## 9. Artefatos principais

- entrada congelada: `entrada_cega_v1/`;
- processamento territorial: `processamento_cego_v1/`;
- processamento de movimento: `processamento_movimento_cego_v1/`;
- ajuste por perfil: `perfil_cego_v3/`;
- figura multipainel inicial: `figura_multipainel_cega_v1/`;
- figura multipainel consolidada com o PERFIL V3: `figura_multipainel_cega_v2/`.
