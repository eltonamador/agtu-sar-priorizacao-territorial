#!/usr/bin/env python3
"""Entrega única MATA-02: nova proveniência do relato e sensibilidade limitada.

Não recalcula geodados, não altera o motor, não sobrescreve o BASE nem a dissertação.
"""
import copy
import csv
import hashlib
import importlib.util
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'outputs/campo_mata02_mzg2'
BASE = CASE / 'ensaio_complementar_v2_249'
PREVIOUS = CASE / 'perfil_249_sensibilidade_v1'
OUT = CASE / 'direcao_249_confirmada_v2_20261030'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def short(sector_id):
    return '-'.join(sector_id.split('::')[-2:])


def render(rows, geo):
    cart = module('cartografia_mata02_reuso', ROOT / 'work/gerar_mapa_mata02_base_v1.py')
    old, bounds, size = cart.old, cart.bounds, cart.SIZE
    source = CASE / 'mapa_priorizacao_v1/fontes/ESA_WorldCover_S2_TCC_2021_MATA02.png'
    meta = read(source.with_suffix('.metadata.json'))
    assert sha(source) == meta['sha256']
    assert list(bounds) == meta['bounds_lon_lat']
    image = Image.open(source).convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)
    old.add_osm(image, bounds)
    draw = ImageDraw.Draw(image)
    colors = cart.COLORS
    top = {row['sector_id']: i for i, row in enumerate(rows[:3])}
    conditional = next(row for row in rows if short(row['sector_id']) == 'R02-SW')
    for feature in geo['features']:
        poly = [old.lonlat_to_px(*point, bounds) for point in feature['geometry']['coordinates'][0]]
        assert all(0 <= x < size and 0 <= y < size for x, y in poly)
        draw.line(poly, fill='white', width=4, joint='curve')
        draw.line(poly, fill='#515b5d', width=2, joint='curve')
        sid = feature['properties']['sector_id']
        if sid in top:
            i = top[sid]
            rgb = tuple(int(colors[i][k:k + 2], 16) for k in (1, 3, 5))
            layer = Image.new('RGBA', image.size)
            ImageDraw.Draw(layer).polygon(poly, fill=rgb + (55,))
            image.alpha_composite(layer)
            draw = ImageDraw.Draw(image)
            draw.line(poly, fill='white', width=11, joint='curve')
            draw.line(poly, fill=colors[i], width=7, joint='curve')
        elif sid == conditional['sector_id']:
            # C1 é alternativa condicionada, não uma quarta prioridade.
            for a, b in zip(poly, poly[1:]):
                old.draw_dashed_segment(draw, a, b, fill='white', width=10, dash=16, gap=9)
                old.draw_dashed_segment(draw, a, b, fill='#545454', width=5, dash=16, gap=9)
    ring = read(CASE / 'entrada_auditada_v2/entrada_raio_fonte_mata02_mzg2.geojson')['features'][0]['geometry']['coordinates'][0]
    draw.line([old.lonlat_to_px(*point, bounds) for point in ring], fill=cart.RED, width=4)
    line = read(BASE / 'referencia_249_contextual.geojson')['features'][0]['geometry']['coordinates']
    a, b = old.lonlat_to_px(*line[0], bounds), old.lonlat_to_px(*line[-1], bounds)
    old.draw_dashed_segment(draw, a, b, fill='white', width=13, dash=26, gap=14)
    old.draw_dashed_segment(draw, a, b, fill=cart.PURPLE, width=7, dash=26, gap=14)
    angle = math.atan2(b[1] - a[1], b[0] - a[0])
    draw.polygon([b, (b[0] - 34 * math.cos(angle - .42), b[1] - 34 * math.sin(angle - .42)),
                  (b[0] - 34 * math.cos(angle + .42), b[1] - 34 * math.sin(angle + .42))],
                 fill=cart.PURPLE, outline='white', width=2)
    cart.tag(draw, ((a[0] + b[0]) / 2 - 50, (a[1] + b[1]) / 2 - 55), '249° — relato', cart.PURPLE, 29)
    for i, row in enumerate(rows[:3]):
        cart.tag(draw, old.lonlat_to_px(row['representative_lon'], row['representative_lat'], bounds),
                 f"AP{i + 1}  {short(row['sector_id'])}", colors[i], 31)
    cart.tag(draw, old.lonlat_to_px(conditional['representative_lon'], conditional['representative_lat'], bounds),
             'C1  R02-SW', '#545454', 29)
    ox, oy = old.lonlat_to_px(cart.LON, cart.LAT, bounds)
    draw.ellipse((ox - 14, oy - 14, ox + 14, oy + 14), fill='white', outline=cart.RED, width=5)
    cart.tag(draw, (ox + 64, oy - 31), 'E0', cart.RED, 35)
    for label, az in [('N', 0), ('NE', 45), ('L', 90), ('SE', 135), ('S', 180), ('SO', 225), ('O', 270), ('NO', 315)]:
        x = size / 2 + 6350 * math.sin(math.radians(az)) * size / (2 * cart.EXTENT)
        y = size / 2 - 6350 * math.cos(math.radians(az)) * size / (2 * cart.EXTENT)
        draw.text((x, y), label, font=cart.f(31, True), fill=cart.INK, anchor='mm', stroke_width=4, stroke_fill='white')
    draw.rectangle((size - 138, 22, size - 25, 177), fill='white', outline='#59666a', width=1)
    draw.polygon([(size - 82, 42), (size - 106, 112), (size - 82, 98), (size - 58, 112)], fill=cart.INK)
    draw.text((size - 82, 145), 'N', font=cart.f(34, True), fill=cart.INK, anchor='mm')
    scale = size * 1000 / (2 * cart.EXTENT)
    draw.rectangle((25, size - 119, 45 + 2 * scale, size - 25), fill='white')
    for i in range(2):
        draw.rectangle((40 + i * scale, size - 65, 40 + (i + 1) * scale, size - 50),
                       fill=cart.INK if i == 0 else 'white', outline=cart.INK, width=2)
    draw.text((40, size - 104), '0', font=cart.f(27), fill=cart.INK)
    draw.text((40 + scale, size - 104), '1', font=cart.f(27), fill=cart.INK, anchor='ma')
    draw.text((40 + 2 * scale, size - 104), '2 km', font=cart.f(27), fill=cart.INK, anchor='ra')
    canvas = Image.new('RGB', (2380, 2110), 'white')
    d = ImageDraw.Draw(canvas)
    cart.block(d, 'MATA-02 | Resultado territorial e direção relatada de 249°', 50, 35, 2280, 44, bold=True)
    cart.block(d, 'Um único ensaio • território real, ocorrência hipotética • raio informado: 6 km • status: REVISAR', 50, 99, 2280, 30, color='#59666a')
    canvas.paste(image.convert('RGB'), (50, 165))
    d.rectangle((50, 165, 50 + size, 165 + size), outline='#738086', width=2)
    x, w, y = 1745, 580, 174
    def paragraph(text, size=27, bold=False, color=cart.INK, gap=15):
        nonlocal y
        y = cart.block(d, text, x, y, w, size, color, bold) + gap
    paragraph('REFERÊNCIA INICIAL', 31, True)
    paragraph('E0 — 0°09′33″ S; 51°23′42″ O\n−0,1591667; −51,3950000', 28)
    paragraph('Registro de campo adotado no exercício; não comprova UPV de ocorrência real.', 25, color='#59666a', gap=25)
    paragraph('TRÊS PRIMEIROS DO BASE', 30, True)
    ranges = ['Sudoeste • 0–3,46 km', 'Sudoeste • 4,90–6,00 km', 'Leste • 4,90–6,00 km']
    for i, row in enumerate(rows[:3]):
        paragraph(f"AP{i + 1}  {short(row['sector_id'])}", 32, True, colors[i], 3)
        paragraph(ranges[i] + ' de E0\nEscore: ' + f"{row['score_base']:.6f}".replace('.', ','), 27, gap=18)
    paragraph('C1  R02-SW — CONDICIONAL', 29, True, '#545454', 5)
    paragraph('Sudoeste • 3,46–4,90 km. Substitui AP3 somente no teste de direção mais ampla (±45°) com confiança média/alta assumida. Não é quarta prioridade.', 26, gap=24)
    paragraph('PISTA: DIREÇÃO DE 249°', 30, True, cart.PURPLE, 7)
    paragraph('Linha roxa = direção informada do desaparecido, representada desde E0. Não é rota nem distância percorrida.', 27)
    paragraph('Precisão angular e confiabilidade não medidas. Não foi escolhido um ranking PERFIL único.', 26, color='#59666a', gap=23)
    paragraph('LEITURA DO RESULTADO', 30, True, gap=7)
    paragraph('AP1 e AP2 permanecem nas 9 variações testadas. AP3 permanece em 7; C1 entra em 2. Essas contagens não são probabilidades.', 26)
    paragraph('REVISAR: escores próximos, sensibilidade aos pesos e alertas da entrada/vegetação. Cada setor tem cerca de 4,71 km²; exige revisão e subdivisão pelo comando.', 26)
    assert y < 1990, y
    yfoot = cart.block(d, 'Polígonos coloridos: Top-3 BASE preservado. Contorno cinza tracejado: alternativa condicionada. Limite vermelho: domínio de análise. SW = sudoeste; E = leste.', 50, 1845, 1640, 25, color='#59666a')
    yfoot = cart.block(d, 'O norte geográfico e a origem E0 são hipóteses cartográficas. O relato não informou se o norte é verdadeiro ou magnético. Não são posições da pessoa nem ordens operacionais.', 50, yfoot + 10, 1640, 25, color='#59666a')
    assert yfoot < 2000, yfoot
    attribution = 'Base orbital histórica: Sentinel-2 / ESA WorldCover 2021, não outubro/2026. © ESA WorldCover project 2021; Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium. Vias/hidrografia: © OpenStreetMap contributors, consulta de 17/08/2026.'
    end = cart.block(d, attribution, 50, 2010, 2280, 23, color='#59666a')
    assert end < 2100, end
    path = OUT / 'Mapa_MATA02_direcao_249_resultados.png'
    canvas.save(path, dpi=(200, 200))
    return dict(path=str(path), dimensions=list(canvas.size), bounds_lon_lat=list(bounds),
                background_metadata=meta, background_sha256=sha(source), visual_inspection='PENDENTE')


def main():
    if OUT.exists():
        raise SystemExit('Destino já existe; nada sobrescrito.')
    preserved = [path for folder in (BASE, PREVIOUS, CASE / 'entrada_auditada_v2', CASE / 'mapa_priorizacao_v1')
                 for path in folder.rglob('*') if path.is_file()]
    before = {str(path.relative_to(ROOT)): sha(path) for path in preserved}
    OUT.mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    premises = read(PREVIOUS / 'premissas.json')
    premises.update(case_id='MATA-02', package_version='DIRECAO-249-v2', recorded_at_utc=now,
                    user_statement='a referência é azimute de 249° a partir do norte, foi o informação de direção do desaparecido',
                    confirmed_meaning='DIRECAO_INFORMADA_DO_DESAPARECIDO', evidence_nature='RELATADO',
                    direction_origin_confirmed=False, repeated_prompts_treated_as_one_case=True,
                    confidence_and_tolerance_are_sensitivity_assumptions=True,
                    original_outputs_preserved=True, no_new_ground_truth=True,
                    limited_scope='Reexecução somente do PERFIL com BASE congelado e atualização de proveniência; não reexecuta geodados ou MOV.')
    save('PREMISSAS_E_CONFIRMACAO.json', premises)
    engine_path = ROOT / 'work/perfil_vitima_v3/profile_ranker.py'
    config = ROOT / 'outputs/modulo_perfil_vitima_v3/config_perfil_quantitativo_v3.json'
    engine = module('perfil_mata02_direcao249_v2', engine_path)
    tests = [('NAO_AVALIADA', 22.5)] + [(c, t) for c in ('BAIXA', 'MEDIA', 'ALTA') for t in (5, 22.5, 45)]
    summaries = []
    for confidence, tolerance in tests:
        name = f'{confidence}_{tolerance:g}'
        payload = copy.deepcopy(read(PREVIOUS / f'entrada_{name}.json'))
        payload['created_at'] = now
        payload['source_case_revision'] = 4
        payload['source_profile_compiled_sha256'] = sha(OUT / 'PREMISSAS_E_CONFIRMACAO.json')
        frozen = engine.prepare_frozen_input(payload, frozen_at=now)
        save(f'entrada_{name}.json', frozen)
        result = engine.rank_profile(frozen, config_path=config)
        repeat = engine.rank_profile(frozen, config_path=config)
        assert result['primary_rows'] == repeat['primary_rows']
        old_result = read(PREVIOUS / f'resultado_{name}.json')
        assert result['primary_rows'] == old_result['primary_rows'], name
        save(f'resultado_{name}.json', result)
        summaries.append(dict(confidence_assumed=confidence, tolerance_assumed_deg=tolerance,
                              abstained=result['abstained'], engine_operational_status=result.get('operational_status'),
                              effective_lambda=result['primary_rows'][0]['effective_lambda'],
                              top3=[dict(sector=short(r['sector_id']), score=r['profile_score'], base_rank=r['territorial_rank'])
                                    for r in result['primary_rows'][:3]],
                              unchanged_from_previous_sensitivity=True))
    rows = sorted(read(BASE / 'ranking_BASE_completo.json'), key=lambda row: row['rank_base_within_buffer'])
    geo = read(BASE / 'setores_BASE.geojson')
    assert len(rows) == len(geo['features']) == 24
    assert [short(r['sector_id']) for r in rows[:3]] == ['R01-SW', 'R03-SW', 'R03-E']
    active = [s for s in summaries if s['confidence_assumed'] != 'NAO_AVALIADA']
    assert all([r['sector'] for r in s['top3'][:2]] == ['R01-SW', 'R03-SW'] for s in active)
    assert sum(s['top3'][2]['sector'] == 'R03-E' for s in active) == 7
    assert sum(s['top3'][2]['sector'] == 'R02-SW' for s in active) == 2
    with (OUT / 'COMPARACAO_SENSIBILIDADE.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['confianca_assumida', 'tolerancia_assumida_graus', 'lambda_efetivo', 'abstencao_perfil', 'primeiro', 'segundo', 'terceiro'])
        for s in summaries:
            writer.writerow([s['confidence_assumed'], s['tolerance_assumed_deg'], s['effective_lambda'], s['abstained'], *[r['sector'] for r in s['top3']]])
    map_qa = render(rows, geo)
    result = dict(case_id='MATA-02', status='EXPLORATORIO_REVISAR_NAO_OPERACIONAL',
                  base_status='REVISAR', new_primary_profile_ranking_selected=False,
                  base_top3=[dict(sector=short(r['sector_id']), score=r['score_base'],
                                 inner_radius_m=r['inner_radius_m'], outer_radius_m=r['outer_radius_m'],
                                 area_m2=r['sector_area_m2']) for r in rows[:3]],
                  sensitivity=summaries, first_two_stable_in_test_grid=True,
                  third_sector_counts={'R03-E': 7, 'R02-SW': 2},
                  counts_are_probabilities=False, media_alta_not_independent=True,
                  numerical_results_equal_previous_sensitivity=True,
                  update_changes_provenance_not_existing_numeric_inputs=True,
                  movement_geodata_dissertation_not_reexecuted_or_modified=True,
                  limitations=['Cenário de desaparecimento hipotético em território real',
                               'Sem referência de encontro usada no cálculo',
                               'Raio de 6 km informado, não calibrado',
                               'Origem E0 e norte geográfico adotados apenas para representação',
                               'Confiabilidade e tolerância angular do relato desconhecidas',
                               'Perfil quantitativo limitado à pista direcional nesta execução',
                               'MOV permanece separado do ranking; não há estimativa de tempo de percurso',
                               'Base orbital de 2021; não comprova condições locais em 2026',
                               'Escores não são probabilidades e não demonstram eficácia operacional'])
    save('RESULTADOS_CONSOLIDADOS.json', result)
    report = '''MATA-02 / MZG2 — CONCLUSÃO DE UM ÚNICO PEDIDO
Atualização: direção relatada de 249° a partir do norte.

1. O QUE FOI FEITO
Registrou-se a confirmação de que 249° se refere à direção informada do desaparecido. O relato permanece RELATADO: sua confiabilidade, tolerância angular, origem exata e referência de norte não foram medidas. Os 11 envios repetidos não foram tratados como 11 casos. Preservaram-se o BASE, os demais casos, o motor e a dissertação.
Reexecutou-se somente o componente PERFIL: nove combinações de confiança/tolerância e um controle sem confiança avaliada. Foram reutilizados os geodados, a geometria, a cartografia orbital e o movimento já calculados. Os números coincidem com a análise anterior de sensibilidade, que já usava 249°: a novidade desta entrega é a confirmação do significado e sua proveniência, não um resultado numérico artificialmente diferente.

2. ÁREAS CANDIDATAS — BASE PRESERVADO, STATUS REVISAR
AP1 — R01-SW: sudoeste, de 0 a 3,46 km de E0; escore 0,644159.
AP2 — R03-SW: sudoeste, de 4,90 a 6 km de E0; escore 0,634348.
AP3 — R03-E: leste, de 4,90 a 6 km de E0; escore 0,630079.
São setores de aproximadamente 4,71 km² cada, não pontos previstos de encontro. O raio informado de 6 km delimita cerca de 113 km². A faixa radial não é distância percorrida por uma trilha.

3. POR QUE ESSAS ÁREAS
No BASE, a soma usa 0,30·GEO-02 (vias/acesso), 0,25·GEO-03 (hidrografia), 0,20·GEO-04 (relevo) e 0,25·GEO-05 (cobertura), com as transformações já existentes. Escores maiores expressam o índice territorial do modelo, não probabilidade de a pessoa estar ali.
AP1: componentes 0,542529 / 0,971831 / 0,684036 / 0,406542; melhor combinação BASE. Declividade amostrada média de 4,15° e proporção florestal de 83,2%; há alerta de vegetação densa.
AP2: componentes 0,511751 / 0,989851 / 0,680756 / 0,388833; combinação próxima da primeira, com declividade amostrada média de 4,20° e proporção florestal de 87,6%; há alerta de vegetação densa.
AP3: componentes 0,491216 / 0,973693 / 0,710398 / 0,388847; favorabilidade relativa no relevo e demais componentes mantém sua posição BASE. Está a leste e NÃO recebe apoio da direção de 249°. Ausência de alerta específico não comprova passagem segura.
Os componentes e proporções foram lidos dos resultados congelados, não novamente estimados nesta atualização. Boa pontuação hidrográfica não deve ser interpretada como água ausente. Cobertura vista de cima não mede diretamente a dificuldade no sub-bosque. O custo MOV não integra este ranking.

4. EFEITO DA DIREÇÃO
249° cai na faixa Oeste (W: 247,5°–292,5°), a apenas 1,5° da fronteira com Sudoeste (SW: 202,5°–247,5°). O modelo compara sobreposição angular por setor, não simula uma trajetória. Por isso, compatibilidade direcional e favorabilidade territorial não produzem necessariamente um vencedor Oeste.
Tolerâncias testadas, NÃO informadas pelo usuário: ±5°, ±22,5° e ±45°. Confianças testadas: baixa, média e alta. Peso nominal do perfil: 0,10; peso efetivo 0,033333 (baixa) ou 0,066667 (média/alta), pois a natureza RELATADO limita a força da evidência. Média e alta coincidem por construção; não são replicações independentes.
AP1 e AP2 continuam em primeiro e segundo nas nove combinações. AP3 permanece em terceiro em sete delas. Apenas com ±45° e confiança média/alta assumida, R02-SW (sudoeste intermediário, 3,46–4,90 km) passa do 7º posto BASE para o 3º, com escore de perfil 0,619672. Esse setor aparece no mapa como C1, alternativa condicionada, NÃO quarta prioridade.
No controle sem confiança avaliada, o perfil se abstém e não altera o BASE. Nenhuma confiança ou tolerância foi escolhida como fato. Logo, não há um ranking PERFIL definitivo. As contagens 9/9 e 7/9 descrevem apenas essa grade limitada de testes, não chances de localização nem robustez universal.

5. COMO INTERPRETAR PARA O EXERCÍCIO
AP1 e AP2 são as primeiras candidatas analíticas mais estáveis nas hipóteses testadas. AP3 e C1 representam a divergência a discutir: favorabilidade territorial a leste versus maior influência de uma direção ampla a oeste/sudoeste. Não se excluem outros setores nem se transforma a seta em corredor de busca já confirmado. Antes de emprego real, o comando precisa conferir a pista, acessos, barreiras e capacidade das equipes e subdividir áreas analíticas grandes.
O estado continua REVISAR: margem BASE de aproximadamente 0,009812, estabilidade de 0,60 e três vitórias em cinco configurações de pesos, além dos alertas de revisão da entrada/vegetação. Confirmar o significado da direção não resolve essas limitações nem autoriza elevar o estado a PRIORIZADO.

6. LIMITES E PRÓXIMO USO
Este é um ensaio de ocorrência hipotética sobre território documentado em campo, sem comprovação de eficácia de busca. O ponto do iPhone é referência adotada no exercício. A seta parte de E0 e usa norte geográfico por convenção cartográfica; origem efetiva e norte magnético/verdadeiro do relato continuam não confirmados. Seu comprimento não estima deslocamento.
A imagem de fundo é composição histórica Sentinel-2/ESA WorldCover 2021, não Google Earth nem fotografia de outubro de 2026. As fotos próprias de 2026 complementam o contexto, mas não são um ortomosaico georreferenciado de todo o raio. Pessoas visíveis nas fotos não foram usadas como alvo para calibrar a saída.
A explicação aos especialistas deve mostrar o resultado com essas ressalvas e avaliar clareza, utilidade percebida e limitações. Não foi alterado o formulário, nem aplicada avaliação por especialistas, nem incorporada esta entrega ao texto da dissertação.

7. VERIFICAÇÃO REALIZADA NESTA ENTREGA
Reexecução do PERFIL, repetibilidade dos escores, igualdade com a sensibilidade anterior, 24 setores e Top-3 BASE, contagem das alternativas, integridade dos arquivos preservados e limites da cartografia. Não foi executada novamente toda a suíte de testes nem feita validação externa/operacional. A situação da inspeção visual está registrada em QA_ENTREGA.json.
'''
    (OUT / 'RELATORIO_MATA02_DIRECAO_249.txt').write_text(report)
    after = {str(path.relative_to(ROOT)): sha(path) for path in preserved}
    assert before == after
    qa = dict(status='VERIFICACOES_NUMERICAS_OK_INSPECAO_VISUAL_PENDENTE',
              processed_cases=1, profile_executions=10, repeatability_runs=10,
              numeric_identity_with_previous_sensitivity=True, sector_count=24,
              preserved_source_count=len(before), frozen_sources_unchanged=True,
              map=map_qa, full_test_suite_rerun=False, external_validation=False)
    save('QA_ENTREGA.json', qa)
    save('MANIFESTO.json', dict(recorded_at_utc=now, source_hashes=before,
                              engine_sha256=sha(engine_path), config_sha256=sha(config),
                              execution_script_sha256=sha(Path(__file__)),
                              output_hashes={path.name: sha(path) for path in OUT.iterdir() if path.is_file()}))
    print(json.dumps(dict(output_directory=str(OUT), source_files_preserved=len(before),
                          result='UM_CASO_CONCLUIDO_REVISAR', map=map_qa['path']), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
