# MATA-02/MZG2 — pacote documental de processamento cego v1

Este diretório prepara o ensaio `MATA-02/MZG2` sem executar ou modificar o motor territorial. O cenário é controlado e semissintético em território real.

## Conteúdo

- `config_mata02_mzg2_blind_v1.json`: configuração congelada da entrada espacial, da setorização, dos pesos, da amostragem e dos ramos de hidrografia.
- `PROTOCOLO_MATA02_MZG2_CEGO_v1.md`: regras de cegamento, separação temporal, fronteira do BASE e saídas mínimas previstas.
- `../mata02_mzg2_entrada_cega_v1/FICHA_CANONICA_MATA02_MZG2_v1.json`: ficha canônica da entrada.
- `../mata02_mzg2_entrada_cega_v1/MANIFESTO_PARTICAO_EVIDENCIAS_MATA02_v1.json`: partição entre evidência real, elemento semissintético, contexto visual e referência do alvo.

## Regras centrais

1. O centro é `-0.1591666667, -51.395` e o raio informado é `6000 m`.
2. O valor de `17 h` pertence somente ao cenário hipotético.
3. O BASE não recebe fotografias, perfil, pistas, coordenadas da câmera ou coordenada do alvo.
4. As coordenadas das imagens de drone representam a câmera no instante da captura.
5. A setorização permanece em `3 x 8`, com 24 setores.
6. A amostragem permanece em 3.600 pontos por setor.
7. Os pesos do BASE permanecem `0,30 / 0,25 / 0,20 / 0,25`.
8. Quando GEO-03 estiver carregada e tiver feições no domínio, executa-se o BASE completo.
9. Quando GEO-03 estiver carregada sem feições ou estiver indisponível, o BASE se abstém; eventual ranking com módulos disponíveis é apenas diagnóstico separado.

## Estado atual

- Entrada documental: preparada.
- Coordenada do alvo: não fornecida.
- Inventário dos 34 anexos, metadados e hashes: concluído em `../mata02_mzg2_entrada_cega_v1/INVENTARIO_IMAGENS_ANEXADAS_MATA02_v1.json`.
- Snapshot e hashes das camadas geográficas: pendentes da execução.
- Invólucro específico MATA-02: não criado nesta etapa.
- Testes específicos MATA-02: não criados nesta etapa.
- Execução e mapas: não realizados nesta etapa.

Nenhuma ausência foi preenchida por suposição. Nenhum resultado deve ser atribuído a este pacote antes de uma execução registrada e verificável.
