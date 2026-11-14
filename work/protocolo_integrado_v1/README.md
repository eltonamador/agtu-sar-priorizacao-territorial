# Protocolo integrado prospectivo v1

Implementação candidata prospectiva, separada do caso URBE-01 congelado. O
URBE-01 não foi alterado nem reprocessado por este protocolo.

## Escopo

- `LOC`: agrega resultados congelados do PERFIL V3 e preserva o ranking de setores dentro de cada candidato; não produz ranking global entre candidatos.
- `URG`: prioridade de revisão operacional por regras explícitas, sem probabilidade clínica.
- `DET`: avaliação por setor e modalidade, sem escore agregado.
- eventos de busca: registros imutáveis; um resultado negativo nunca elimina setor nem altera LOC na V1.

## Comandos

```bash
python3 integrated_protocol.py freeze-case rascunho.json caso_congelado.json --frozen-at 2026-10-21T10:00:00-03:00
# Para revisão > 1, acrescente: --parent-case caso_anterior_congelado.json
python3 integrated_protocol.py compile-case caso_congelado.json resultado.json
python3 integrated_protocol.py compile-case caso_congelado.json resultado_verificado.json --artifact-root pacote/ --artifact-map mapa_artefatos.json
python3 integrated_protocol.py build-loc-envelope caso_congelado.json loc_congelado.json \
  --profile-input cand_1_entrada.json --profile-result cand_1_saida.json \
  --profile-input cand_2_entrada.json --profile-result cand_2_saida.json
python3 visual_spatial_binding.py extract-manifest --case caso_congelado.json \
  --artifact-root pacote/ --artifact-map mapa_artefatos.json \
  --output manifesto_metadados_visuais.json
python3 visual_spatial_binding.py build-binding --case caso_congelado.json \
  --loc-result loc_congelado.json --manifest manifesto_metadados_visuais.json \
  --output vinculo_visual_setores.json
python3 integrated_protocol.py compile-case caso_congelado.json resultado_com_visual.json \
  --artifact-root pacote/ --artifact-map mapa_artefatos.json \
  --visual-metadata-manifest manifesto_metadados_visuais.json \
  --visual-sector-binding vinculo_visual_setores.json
python3 integrated_protocol.py freeze-event evento_rascunho.json evento_congelado.json --frozen-at 2026-10-21T11:20:00-03:00
# Para sequência > 1: --previous-event evento_anterior.json
# Para novo ponto: acrescente também --source-event evento_positivo_de_origem.json
python3 integrated_protocol.py compile-event evento_congelado.json resultado_evento.json --artifact-root pacote/ --artifact-map mapa_evento.json
python3 build_release.py
```

O congelamento usa JSON canônico estrito (sem `NaN`/infinito), SHA-256 e fuso horário obrigatório. A entrada não contém resposta real, fotografias com alvo nem dados pós-revelação. Evidências futuras, não autorizadas ou sem procedência não dirigem o processamento. Quando tempo transcorrido e tempo máximo plausível de deslocamento estiverem disponíveis, o segundo não pode superar o primeiro. Sem `--artifact-root` e `--artifact-map`, hashes externos permanecem corretamente identificados como declarados e não verificados.

O manifesto de metadados pode conter coordenadas e horários precisos da câmera. Por isso, deve permanecer na área restrita de processamento; versões destinadas à dissertação, aos slides ou à circulação externa devem expor apenas o necessário e omitir dados pessoais ou operacionais que não contribuam para a análise.

O arquivo LOC precisa seguir `loc_result_v1.schema.json` para que seu conteúdo seja validado. No contrato v1.1, cada item de `profile_runs` contém o par inseparável `profile_input` + `profile_result` do mesmo candidato. A entrada congelada deve declarar `source_loc_input_sha256`, calculado sobre a projeção LOC do caso, e `source_case_revision`; isso impede reaproveitar uma execução depois de alterar ponto, tempo, ambiente ou revisão. O integrador reexecuta o PERFIL V3 autorizado sobre a entrada incorporada e exige igualdade integral com a saída declarada. Código e configuração são conferidos contra `loc_engine_lock_v1.json`, além dos hashes constantes no envelope. O contrato exige `ground_truth_used=false`, `blind_processing=true` e `cross_candidate_ranking=false`, verifica o `output_sha256` e deriva os setores válidos exclusivamente de `operational_rows`. Os identificadores de candidato e de setor devem ser únicos. O PERFIL V3 ranqueia setores dentro de cada candidato e admite empates por competição, por exemplo 1, 1, 3; ranks de candidatos diferentes não são comparáveis. Um arquivo com SHA-256 correto, mas sem esse contrato, comprova somente a integridade dos bytes e mantém `review_required=true`. O campo histórico `profile_v2_compiled_sha256` identifica o artefato compilado de entrada, produzido na etapa anterior e consumido pelo PERFIL V3; ele não classifica o resultado atual como Versão 2.

Os hashes de perfil, território, manifesto de revisões espaciais e manifesto visual demonstram identidade e integridade dos arquivos fornecidos. O manifesto espacial do caso identifica o conjunto; cada execução PERFIL V3 pode apontar para sua revisão espacial específica. Como os demais artefatos externos ainda não compartilham um contrato semântico integral com o envelope, seus conteúdos não são automaticamente atestados. Da mesma forma, o cegamento indicado no contrato LOC é uma declaração verificável quanto à forma e às vinculações, mas não uma prova criptográfica de que nenhum agente externo consultou a referência reservada. Por isso, o resultado LOC permanece sujeito à revisão humana até existir atestação confiável de execução controlada.

DET verifica requisitos por setor e modalidade. Imagens precisam de anotação compatível com cada dimensão e verificação dos bytes; camada pública registra potencial, não observação favorável. Sem o subprocesso opcional de metadados e vínculo espacial, a mídia recebe apenas validação estrutural do contêiner (`CONTAINER_STRUCTURE_ONLY`). Quando acionado sobre o arquivo original, o subprocesso preserva sua identidade por SHA-256, usa ImageIO para decodificar pixels e conferir dimensões e extrai somente EXIF, GPS e propriedades DJI/XMP autorizadas. Os valores extraídos e os informados pelo operador permanecem lado a lado, com proveniência própria; um nunca sobrescreve o outro, e conflito relevante bloqueia o footprint.

GPS altitude representa altitude referida pelo metadado, tratada como MSL; `RelativeAltitude` da DJI é relativa ao ponto de decolagem. Nenhuma delas se torna altura AGL sem regra explícita e documentada. Fotografias de solo ou oblíquas permanecem contexto direcional. Somente um footprint conservador, auditável e ligado ao mesmo cenário, revisão, imagem e setores LOC pode qualificar o vínculo imagem-setor. `APROXIMADO_METADADOS` limita DET a `APTO_COM_RESTRICOES`; `VERIFICADO_CALIBRADO` fica reservado a dados calibrados futuros; `CONTEXTUAL_INSUFICIENTE` não qualifica a evidência. `numeric_model_input=false` refere-se aos valores dos pixels e à entrada LOC: metadados técnicos validados podem alimentar exclusivamente a construção geométrica do vínculo DET. Em qualquer estado, imagens não afetam LOC, não consultam ground truth e não são submetidas a visão computacional. O horário de captura registra precisão (`EXATA`, `APROXIMADA` ou `NAO_DISPONIVEL`) e origem (`METADADO_ARQUIVO`, `REGISTRO_OPERADOR`, `ESTIMATIVA_OPERADOR` ou `NAO_DISPONIVEL`). Uma imagem sem horário pode ser arquivada, mas não sustenta DET. `target_visible=false` confirma apenas que a vítima-alvo não integra o Conjunto A; `incidental_people_present` registra separadamente outras pessoas visíveis para fins de privacidade. Ambos são preenchidos por conferência humana, não por visão computacional.

Códigos estruturados de risco do perfil são reconciliados com URG e qualquer incompatibilidade força revisão humana. O modo operacional de deslocamento também não pode contradizer um fato estruturado e elegível de mobilidade. Se fatos elegíveis apontarem dois ou mais modos específicos diferentes, a entrada deve ser reconciliada: `MISTO` só é aceitável quando a combinação é sustentada pela evidência; caso contrário, use `DESCONHECIDO` e revise as fontes, sem escolher arbitrariamente um dos modos. Eventos posteriores preservam separadamente o predecessor imediato (`previous_event_sha256`) e o evento positivo de origem (`source_event_sha256`); a origem de um novo ponto precisa ser positiva, autorizada e georreferenciada. Revisões e eventos posteriores devem respeitar a ordem temporal e apresentar o artefato predecessor. Em revisão ou evento de ordem 3 ou superior, verificar apenas o elo imediato não comprova toda a cadeia; para encerrar LOC, a cadeia completa até a sequência 1 é obrigatória. Um evento de localização conhecida validado deve ser coerente com `person_location_status=CONHECIDA_OPERACIONALMENTE`; manter o status como `DESCONHECIDA` é uma inconsistência de entrada e não autoriza processamento LOC adicional até correção. Um registro negativo pode atingir completude documental/estrutural, mas ainda não é elegível como evidência negativa enquanto faltarem dois vínculos executáveis: cobertura com a geometria autenticada dos setores e proveniência temporal da trilha. Em qualquer estado, ele nunca altera LOC na V1.
