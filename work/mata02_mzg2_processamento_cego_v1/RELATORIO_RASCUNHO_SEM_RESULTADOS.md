# Rascunho dos relatórios finais — MATA-02/MZG2 cego v1.0

> **Estado deste documento:** modelo de preenchimento anterior à execução. Os campos `[[PREENCHER APÓS EXECUÇÃO]]` não são resultados. Este rascunho não substitui o protocolo congelado, não registra Top-3, escore, ordem, estado decisório nem validação do modelo.

## 1. Fatos confirmados e fronteira de interpretação

- protocolo: `MATA02-MZG2-BLIND-SET-v1.0`;
- cenário/local: `MATA-02` / `MZG2`;
- ponto inicial de planejamento: `MATA-02-E0`;
- centro: latitude `-0.1591666667`, longitude `-51.395` (`EPSG:4326`);
- domínio circular informado: `6.000 m`;
- método do domínio: operacional direto, sem buffer adaptativo;
- classificação: cenário controlado semissintético em território real;
- território e coordenada inicial: reais;
- ocorrência, pessoa desaparecida e intervalo de 17 horas: hipotéticos;
- alvo/referência de encontro: indisponível e não utilizado;
- setorização: três anéis de área equivalente por oito direções, total de 24 setores;
- amostragem: 3.600 amostras determinísticas por setor;
- pesos do BASE: GEO-02 `0,30`, GEO-03 `0,25`, GEO-04 `0,20` e GEO-05 `0,25`;
- auditoria preparatória da hidrografia: 28 feições interceptantes no domínio;
- ramo hidrológico esperado: H1, com execução do BASE completo; a execução deve confirmar a fonte carregada e reproduzir essa contagem;
- fotografias, coordenadas de câmera do drone, perfil, vestuário, saúde, pistas e intervalo hipotético: excluídos do ranking BASE;
- preferência direcional e penalidade por anel: não aplicadas;
- significado do escore: prioridade analítica territorial ordinal, não probabilidade de presença;
- elegibilidade confirmatória: não; não há verdade-terreno para aferir acerto, eficácia ou precisão.

## 2. Modelo de `relatorio_execucao_mata02_mzg2.md`

### Relatório de execução — MATA-02/MZG2 territorial cego v1.0

#### 2.1 Identificação da execução

- identificador da execução: `[[PREENCHER APÓS EXECUÇÃO]]`;
- data e hora da execução: `[[PREENCHER APÓS EXECUÇÃO]]`;
- protocolo: `MATA02-MZG2-BLIND-SET-v1.0`;
- versão/hash do invólucro: `[[PREENCHER APÓS EXECUÇÃO]]`;
- versão/hash do motor: `[[PREENCHER APÓS EXECUÇÃO]]`;
- hash da configuração efetiva: `[[PREENCHER APÓS EXECUÇÃO]]`.

#### 2.2 Entrada e classificação

- classificação do ensaio: cenário controlado semissintético em território real;
- ponto processado: `MATA-02-E0`;
- centro processado: `-0.1591666667, -51.395`;
- domínio circular recebido: `6.000 m`;
- origem do domínio: informado pelo pesquisador;
- buffer adaptativo: não executado;
- qualidade de detecção disponível: não;
- imputação de qualidade: não;
- setores produzidos: `[[PREENCHER APÓS EXECUÇÃO; ESPERADO: 24]]`;
- amostras esperadas por setor: 3.600;
- alvo disponível ou usado: não;
- fotografias, perfil, pistas, coordenadas de câmera e intervalo hipotético usados no BASE: não.

#### 2.3 Decisão sobre a hidrografia e configuração do BASE

- fonte GEO-03 carregada: `[[PREENCHER APÓS EXECUÇÃO]]`;
- feições hidrográficas que interceptam o domínio: `[[PREENCHER APÓS EXECUÇÃO; AUDITORIA PRÉVIA: 28]]`;
- ramo acionado: `[[PREENCHER APÓS EXECUÇÃO; ESPERADO: H1]]`;
- evidência da decisão: `[[ARQUIVO, CAMPO E HASH A SEREM INDICADOS]]`;
- configuração executada: `[[PREENCHER APÓS EXECUÇÃO; ESPERADO: BASE COMPLETO]]`;
- pesos efetivamente usados: `[[PREENCHER APÓS EXECUÇÃO]]`;
- completude geoespacial: `[[PREENCHER APÓS EXECUÇÃO; ESPERADO: 1,00]]`;
- saída diagnóstica com pesos renormalizados: `[[PREENCHER APÓS EXECUÇÃO; ESPERADO NO RAMO H1: NÃO GERADA/NÃO APLICÁVEL]]`.

O texto final deve registrar a decisão observada, não apenas a esperada. Se a execução não reproduzir as 28 feições, o relatório deve interromper a interpretação do ranking, registrar a divergência e investigar fonte, recorte, versão e consulta espacial antes de qualquer conclusão.

#### 2.4 Resultado territorial

- status técnico da execução do BASE: `[[PREENCHER APÓS EXECUÇÃO]]`;
- estado decisório produzido pelo sistema, se houver: `[[PREENCHER APÓS EXECUÇÃO]]`;
- código(s) de motivo: `[[PREENCHER APÓS EXECUÇÃO]]`;
- número de linhas no ranking: `[[PREENCHER APÓS EXECUÇÃO; ESPERADO QUANDO HOUVER RANKING: 24]]`;
- margem entre o primeiro e o segundo setor: `[[PREENCHER APÓS EXECUÇÃO]]`;
- medida de estabilidade, se efetivamente calculada: `[[PREENCHER APÓS EXECUÇÃO OU DECLARAR NÃO CALCULADA]]`.

Não antecipar `PRIORIZADO`, `REVISAR`, `ABSTIDO`, Top-3 ou qualquer escore. O estado decisório só pode ser transcrito do artefato efetivamente produzido e deve ser acompanhado pela regra que o gerou.

#### 2.5 Áreas analíticas prioritárias — BASE completo

| Área | Setor | Posto | Escore | Direção | Anel | GEO-02 | GEO-03 | GEO-04 | GEO-05 |
|---|---|---:|---:|---|---|---:|---:|---:|---:|
| AP1 | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` |
| AP2 | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` |
| AP3 | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` | `[[PREENCHER]]` |

Esta tabela só deve permanecer no relatório final se houver ranking válido do BASE completo. Cada valor deve ser copiado automaticamente dos arquivos científicos, sem digitação ou arredondamento manual que altere a ordem.

#### 2.6 Reprodutibilidade e QA

- duas execuções independentes: `[[PASS/FAIL]]`;
- arquivos científicos equivalentes após exclusão apenas de campos voláteis documentados: `[[PREENCHER]]`;
- quantidade de gates: `[[PREENCHER]]`;
- gates aprovados: `[[PREENCHER]]`;
- status geral do QA: `[[PASS/FAIL]]`;
- divergências ou avisos: `[[PREENCHER; NÃO USAR “NENHUM” SEM VERIFICAÇÃO]]`.

Se houver qualquer gate essencial com falha, o relatório deve declarar a execução não liberada para interpretação. Não se deve calcular uma taxa de aprovação que esconda uma falha crítica.

#### 2.7 Síntese das camadas territoriais

**GEO-02 — vias**

- fonte/versão/hash: `[[PREENCHER]]`;
- feições no domínio: `[[PREENCHER]]`;
- observação de cobertura: `[[PREENCHER]]`.

**GEO-03 — hidrografia**

- fonte/versão/hash: `[[PREENCHER]]`;
- feições interceptantes: `[[PREENCHER; AUDITORIA PRÉVIA: 28]]`;
- estatística territorial pertinente: `[[PREENCHER]]`.

**GEO-04 — declividade**

- produto/arquivo/hash: `[[PREENCHER]]`;
- amostras válidas: `[[PREENCHER]]`;
- síntese de declividade: `[[PREENCHER; USAR SOMENTE ESTATÍSTICAS GERADAS]]`.

**GEO-05 — cobertura do solo**

- produto: ESA WorldCover 2021 v200;
- arquivo/hash: `[[PREENCHER]]`;
- amostras válidas: `[[PREENCHER; ESPERADO: 86.400]]`;
- distribuição por classes: `[[PREENCHER A PARTIR DA SAÍDA]]`.

As sínteses de camada caracterizam o domínio amostrado; não comprovam transitabilidade no interior da mata nem condições atuais de campo.

#### 2.8 Interpretação e limites

O ranking, se produzido e aprovado no QA, organiza setores do domínio recebido segundo os quatro componentes territoriais do BASE completo. O resultado não representa probabilidade de presença, acurácia de localização, detecção automática da pessoa, eficácia operacional nem ordem obrigatória para as equipes. A decisão permanece com o responsável pela operação e exige conferência de campo.

Este ensaio não possui coordenada de alvo. Consequentemente, não permite calcular distância ao alvo, posto do alvo, acerto do Top-3, sensibilidade, especificidade ou qualquer indicador de desempenho de localização. Sua contribuição é demonstrar o processamento territorial, a rastreabilidade, a separação de evidências e a produção de alternativas analíticas em um território amazônico real.

Fotografias e observações de campo podem documentar dossel, vegetação emaranhada, troncos caídos, áreas abertas e terrenos úmidos, mas permanecem fora do escore quantitativo desta execução. Imagens aéreas e bases regionais também não revelam, sozinhas, passagem efetiva sob o dossel, barrancos estreitos, solo encharcado, obstáculos temporários ou alterações posteriores às datas das fontes.

Deve ser verificada e documentada a cobertura espacial usada nas consultas de vizinhança. Se o recorte de busca por feições próximas não cobrir integralmente a distância necessária além da borda sul do domínio, o relatório final deve indicar os setores potencialmente afetados, quantificar o efeito máximo observado sobre seus componentes/escores e impedir que diferenças da mesma ordem sejam interpretadas como separação robusta.

## 3. Estrutura proposta para `relatorio_qa.json`

O arquivo final deve ser gerado pela execução. A estrutura mínima recomendada é:

```json
{
  "protocol_id": "MATA02-MZG2-BLIND-SET-v1.0",
  "execution_id": "[[PREENCHER APÓS EXECUÇÃO]]",
  "status": "[[PASS OU FAIL]]",
  "gate_count": "[[PREENCHER]]",
  "passed_gate_count": "[[PREENCHER]]",
  "critical_failed_gates": [],
  "ground_truth_available": false,
  "ground_truth_used": false,
  "hydrography": {
    "source_loaded": "[[true OU false]]",
    "intersecting_feature_count": "[[PREENCHER]]",
    "expected_pre_audit_count": 28,
    "branch": "[[H1, H2 OU H3]]",
    "base_configuration": "[[BASE_COMPLETO, ABSTIDO OU OUTRO ESTADO DOCUMENTADO]]"
  },
  "gates": {
    "protocol_id_matches": "[[true OU false]]",
    "declared_center_matches": "[[true OU false]]",
    "declared_radius_is_6000_m": "[[true OU false]]",
    "adaptive_buffer_not_used": "[[true OU false]]",
    "missing_detection_quality_not_imputed": "[[true OU false]]",
    "sector_count_is_24": "[[true OU false]]",
    "feature_count_is_24": "[[true OU false]]",
    "all_sectors_have_3600_expected_samples": "[[true OU false]]",
    "all_raster_sample_coverage_is_complete": "[[true OU false]]",
    "all_worldcover_class_counts_sum_to_3600": "[[true OU false]]",
    "expected_dem_source_available": "[[true OU false]]",
    "expected_worldcover_source_available": "[[true OU false]]",
    "geo03_source_loaded": "[[true OU false]]",
    "geo03_domain_segment_count_matches_audit": "[[true OU false]]",
    "hydrography_branch_is_h1": "[[true OU false]]",
    "all_geo03_values_are_present": "[[true OU false]]",
    "all_geo_completeness_is_1": "[[true OU false]]",
    "base_original_weights_match_protocol": "[[true OU false]]",
    "base_original_weights_sum_to_one": "[[true OU false]]",
    "base_complete_rank_row_count_is_24": "[[true OU false]]",
    "all_component_values_in_unit_interval": "[[true OU false]]",
    "all_base_scores_in_unit_interval": "[[true OU false]]",
    "ranks_are_unique_and_cover_1_to_24": "[[true OU false]]",
    "top3_count_is_3": "[[true OU false]]",
    "no_directional_preference": "[[true OU false]]",
    "no_ring_penalty": "[[true OU false]]",
    "all_excluded_context_flags_false": "[[true OU false]]",
    "target_coordinate_absent": "[[true OU false]]",
    "ground_truth_not_used": "[[true OU false]]",
    "deterministic_repeat_matches": "[[true OU false]]",
    "scientific_files_present": "[[true OU false]]",
    "map_table_execution_ids_match": "[[true OU false]]",
    "source_and_config_hashes_recorded": "[[true OU false]]",
    "no_stale_mata01_or_radius5000_labels": "[[true OU false]]"
  }
}
```

Os campos entre colchetes são marcadores do rascunho e não devem aparecer no JSON definitivo. O número total de gates deve ser calculado a partir do objeto final; não deve ser digitado separadamente sem conferência.

## 4. Checks essenciais de QA

### 4.1 Identidade e configuração

1. O `protocol_id`, cenário, local e candidato correspondem ao MATA-02/MZG2.
2. Centro exato: `-0.1591666667, -51.395`.
3. Raio exato: `6.000 m`, sem reaproveitamento do raio de 5 km do MATA-01.
4. Buffer adaptativo e imputação de qualidade permanecem desativados.
5. A setorização produz exatamente 24 setores, com IDs únicos e geometria válida.
6. Os pesos efetivos são `0,30 / 0,25 / 0,20 / 0,25` e somam 1.

### 4.2 Fronteira cega

7. Não existe coordenada de alvo na entrada, configuração efetiva ou processamento.
8. Fotografias, coordenadas de câmera, perfil, saúde, vestuário, pistas e 17 horas não são consumidos no BASE.
9. Não há preferência direcional nem penalidade por anel.
10. Os horários das fotografias e da bússola não são tratados como horário real de desaparecimento.

### 4.3 Hidrografia e completude

11. A fonte GEO-03 é carregada com sucesso e seu hash/versão fica registrado.
12. A consulta espacial reproduz as 28 feições interceptantes da auditoria; divergência bloqueia a interpretação até ser explicada.
13. O ramo efetivamente acionado é H1.
14. O BASE usa os quatro componentes originais, sem renormalização diagnóstica.
15. GEO-03 é preenchido para todos os 24 setores e a completude é 1,00.
16. Não é produzido nem rotulado como principal um ranking `BASE-DISPONÍVEIS`.

### 4.4 Amostragem e consistência matemática

17. Cada setor possui exatamente 3.600 amostras esperadas e válidas, ou registra explicitamente qualquer falta.
18. As contagens de classes WorldCover somam 3.600 em cada setor e 86.400 no domínio completo.
19. Componentes e escores respeitam o intervalo `[0,1]`.
20. O ranking, quando válido, contém 24 linhas, postos únicos de 1 a 24 e exatamente três linhas no Top-3.
21. A ordem do Top-3 confere com o ranking integral, inclusive no desempate definido pelo motor.
22. Tabela, GeoJSON, mapa e relatório usam os mesmos IDs, escores e identificador de execução.

### 4.5 Fontes e cobertura espacial

23. Arquivos DEM, WorldCover e vetores esperados existem e têm hashes registrados.
24. Datas/versões das fontes são registradas com a ressalva temporal pertinente.
25. O recorte usado para consultas de vizinhança cobre a distância necessária em todas as direções.
26. Se houver limitação no recorte sul, os setores afetados e o impacto numérico máximo são registrados; margens equivalentes não sustentam diferenciação robusta.

### 4.6 Reprodutibilidade e integridade

27. Duas execuções independentes, com a mesma configuração e fontes, geram arquivos científicos idênticos após tratamento documentado de campos voláteis.
28. Manifesto, configuração efetiva, hashes, avisos, ranking integral, Top-3, setores e relatórios estão presentes.
29. Não restam rótulos, caminhos ou valores herdados do MATA-01, inclusive `5.000 m`, `GEO-03 ausente`, `BASE-DISPONÍVEIS` ou abstenção copiada.
30. Nenhum resultado é digitado manualmente no relatório quando pode ser derivado dos artefatos científicos.

### 4.7 Interpretação científica

31. O relatório declara explicitamente que não há alvo nem verdade-terreno.
32. Não usa os termos acurácia, eficácia, validação operacional ou probabilidade de presença como resultado deste ensaio.
33. Diferencia demonstração do processamento de avaliação da qualidade da priorização.
34. Mantém a decisão operacional sob responsabilidade humana e exige confirmação em campo.

## 5. Lacunas que devem permanecer visíveis até a execução

1. **Resultado ainda inexistente:** não há Top-3, escores, margem, estabilidade ou estado decisório a relatar.
2. **Contagem hidrográfica a reproduzir:** as 28 feições vêm da auditoria preparatória; precisam constar da evidência gerada pela execução.
3. **Proveniência incompleta:** timestamps/versões e hashes das fontes OSM, DEM, WorldCover, configuração efetiva e código devem ser preenchidos.
4. **Cobertura de vizinhança:** deve-se confirmar que a consulta cobre todas as direções além da borda do domínio, especialmente ao sul, ou quantificar a limitação.
5. **Regra de estado decisório:** o relatório só pode usar um status se a implementação registrar a regra, o limiar e o código de motivo correspondente.
6. **Ausência de verdade-terreno:** o caso não mede acerto do ranking; essa limitação não será resolvida por fotos ou opinião retrospectiva.
7. **Obstáculos sob o dossel:** as bases e imagens não medem diretamente transitabilidade interna; observações de campo permanecem documentação contextual, não variáveis retroativamente inseridas.
8. **Atualidade das camadas:** OSM, WorldCover e SRTM têm datas distintas das fotografias e não comprovam a situação no dia do levantamento.

## 6. Critério de liberação dos relatórios finais

Os relatórios podem ser considerados finais somente quando:

1. a execução tiver produzido os artefatos científicos e a configuração efetiva;
2. a decisão hidrológica estiver sustentada por evidência verificável;
3. todos os gates essenciais estiverem aprovados, ou qualquer falha estiver claramente marcada como impeditiva;
4. a repetição determinística tiver sido verificada;
5. os campos deste rascunho tiverem sido preenchidos automaticamente ou conferidos contra as fontes;
6. nenhuma afirmação ultrapassar o que um cenário semissintético, sem alvo, permite concluir.
