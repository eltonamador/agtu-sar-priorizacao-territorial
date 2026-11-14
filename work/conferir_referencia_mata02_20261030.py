"""Conferência posterior, sem executar o motor nem alterar saídas congeladas."""
import csv
import hashlib
import importlib.util
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'outputs/campo_mata02_mzg2'
BASE = CASE / 'ensaio_complementar_v2_249'
PROFILE = CASE / 'direcao_249_confirmada_v2_20261030'
OUT = CASE / 'conferencia_referencia_declarada_v1_20261030'
REF = (-0.172250, -51.429583)
E0 = (-0.15916666666666668, -51.395)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def inverse(p1, p2):
    """Vincenty inverse, WGS84; fail rather than report a nonconverged value."""
    a, f = 6378137.0, 1 / 298.257223563
    b = a * (1 - f)
    phi1, lon1 = map(math.radians, p1)
    phi2, lon2 = map(math.radians, p2)
    u1, u2 = [math.atan((1 - f) * math.tan(phi)) for phi in (phi1, phi2)]
    s1, c1, s2, c2 = math.sin(u1), math.cos(u1), math.sin(u2), math.cos(u2)
    L = lon2 - lon1
    lam = L
    for it in range(200):
        sl, cl = math.sin(lam), math.cos(lam)
        ss = math.hypot(c2 * sl, c1 * s2 - s1 * c2 * cl)
        if ss == 0:
            return 0.0, None
        cs = s1 * s2 + c1 * c2 * cl
        sig = math.atan2(ss, cs)
        sa = c1 * c2 * sl / ss
        ca2 = 1 - sa * sa
        c2sm = cs - 2 * s1 * s2 / ca2 if ca2 else 0
        C = f / 16 * ca2 * (4 + f * (4 - 3 * ca2))
        new = L + (1 - C) * f * sa * (sig + C * ss * (c2sm + C * cs * (-1 + 2 * c2sm ** 2)))
        if abs(new - lam) < 1e-13:
            break
        lam = new
    else:
        raise ValueError('Vincenty não convergiu')
    u2coef = ca2 * (a * a - b * b) / (b * b)
    A = 1 + u2coef / 16384 * (4096 + u2coef * (-768 + u2coef * (320 - 175 * u2coef)))
    B = u2coef / 1024 * (256 + u2coef * (-128 + u2coef * (74 - 47 * u2coef)))
    delta = B * ss * (c2sm + B / 4 * (cs * (-1 + 2 * c2sm ** 2) - B / 6 * c2sm * (-3 + 4 * ss ** 2) * (-3 + 4 * c2sm ** 2)))
    d = b * A * (sig - delta)
    az = math.degrees(math.atan2(c2 * sl, c1 * s2 - s1 * c2 * cl)) % 360
    return d, az


def in_ring(point, ring):
    x, y = point
    inside = False
    for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1]):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def contains(point, geometry):
    polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
    return any(in_ring(point, poly[0]) and not any(in_ring(point, hole) for hole in poly[1:]) for poly in polygons)


def short(s):
    return '-'.join(s.split('::')[-2:])


def render(rows, geo, target, d, az):
    # Reuse only drawing helpers. Never call the data acquisition or model routines.
    spec = importlib.util.spec_from_file_location('cart_mata02_reference', ROOT / 'work/gerar_mapa_mata02_base_v1.py')
    cart = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cart)
    old = cart.old
    size, bounds = cart.SIZE, cart.bounds
    source = CASE / 'mapa_priorizacao_v1/fontes/ESA_WorldCover_S2_TCC_2021_MATA02.png'
    assert sha(source) == '3741190f3185e004e38cffd8b2798368730042e0d0a71c49de916336547f88ae'
    assert list(bounds) == read(source.with_suffix('.metadata.json'))['bounds_lon_lat']
    image = Image.open(source).convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)
    assert image.size == (size, size)
    old.add_osm(image, bounds)
    overlay = Image.new('RGBA', image.size)
    od = ImageDraw.Draw(overlay)
    colors = cart.COLORS
    by_id = {f['properties']['sector_id']: f for f in geo['features']}
    for row, color in zip(rows[:3], colors):
        points = [old.lonlat_to_px(*p, bounds) for p in by_id[row['sector_id']]['geometry']['coordinates'][0]]
        od.polygon(points, fill=old.hex_rgba(color, 48))
    image = Image.alpha_composite(image, overlay)
    draw = ImageDraw.Draw(image)
    for feature in geo['features']:
        pts = [old.lonlat_to_px(*p, bounds) for p in feature['geometry']['coordinates'][0]]
        draw.line(pts, fill=(255, 255, 255, 155), width=2)
    for row, color in zip(rows[:3], colors):
        pts = [old.lonlat_to_px(*p, bounds) for p in by_id[row['sector_id']]['geometry']['coordinates'][0]]
        draw.line(pts, fill='white', width=10)
        draw.line(pts, fill=color, width=6)
    pts = [old.lonlat_to_px(*p, bounds) for p in by_id[target['sector_id']]['geometry']['coordinates'][0]]
    draw.line(pts, fill='white', width=10)
    draw.line(pts, fill='#007e87', width=6)
    domain = read(CASE / 'entrada_auditada_v2/entrada_raio_fonte_mata02_mzg2.geojson')['features'][0]['geometry']['coordinates'][0]
    draw.line([old.lonlat_to_px(*p, bounds) for p in domain], fill=cart.RED, width=5)
    direction = read(BASE / 'referencia_249_contextual.geojson')['features'][0]['geometry']['coordinates']
    a, b = [old.lonlat_to_px(*p, bounds) for p in (direction[0], direction[-1])]
    old.draw_dashed_segment(draw, a, b, fill='white', width=11, dash=24, gap=12)
    old.draw_dashed_segment(draw, a, b, fill=cart.PURPLE, width=6, dash=24, gap=12)
    cart.tag(draw, (a[0] - 165, a[1] + 25), '249° — relato', cart.PURPLE, 27)
    for i, row in enumerate(rows[:3]):
        cart.tag(draw, old.lonlat_to_px(row['representative_lon'], row['representative_lat'], bounds), f"AP{i+1}  {short(row['sector_id'])}", colors[i], 30)
    cart.tag(draw, old.lonlat_to_px(target['representative_lon'], target['representative_lat'], bounds), 'R02-W | 22º', '#007e87', 31)
    ox, oy = old.lonlat_to_px(E0[1], E0[0], bounds)
    draw.ellipse((ox-13, oy-13, ox+13, oy+13), fill='white', outline=cart.RED, width=5)
    cart.tag(draw, (ox+50, oy-35), 'E0', cart.RED, 32)
    rx, ry = old.lonlat_to_px(REF[1], REF[0], bounds)
    draw.polygon([(rx, ry-22), (rx+22, ry), (rx, ry+22), (rx-22, ry)], fill='#ffe878', outline='#111111', width=5)
    cart.tag(draw, (rx-5, ry+57), 'REF — declarada', '#111111', 29)
    draw.rectangle((size-130, 20, size-25, 173), fill='white')
    draw.polygon([(size-77, 35), (size-101, 111), (size-77, 94), (size-53, 111)], fill=cart.INK)
    draw.text((size-77, 144), 'N', font=cart.f(32, True), fill=cart.INK, anchor='mm')
    scale = size * 1000 / (2 * cart.EXTENT)
    draw.rectangle((25, size-117, 80+2*scale, size-25), fill='white')
    for i in range(2):
        draw.rectangle((40+i*scale, size-65, 40+(i+1)*scale, size-50), fill=cart.INK if i == 0 else 'white', outline=cart.INK, width=2)
    for i, label in enumerate(['0', '1', '2 km']):
        draw.text((40+i*scale, size-103), label, font=cart.f(25), fill=cart.INK, anchor='la' if i == 0 else 'ma')
    canvas = Image.new('RGB', (2380, 2110), 'white')
    cd = ImageDraw.Draw(canvas)
    cart.block(cd, 'MATA-02 | Conferência da referência declarada', 50, 32, 2280, 46, bold=True)
    cart.block(cd, 'Comparação posterior com saídas preservadas • ocorrência hipotética em território real • sem recalibração', 50, 101, 2280, 29, color='#59666a')
    canvas.paste(image.convert('RGB'), (50, 165))
    cd.rectangle((50, 165, 1700, 1815), outline='#738086', width=2)
    x, w, y = 1745, 580, 175
    def para(text, size=28, bold=False, color=cart.INK, gap=20):
        nonlocal y
        y = cart.block(cd, text, x, y, w, size, color, bold) + gap
    para('REFERÊNCIA REVELADA', 31, True)
    para('−0,172250; −51,429583\nFonte: declaração do pesquisador. Precisão não informada.', 27)
    para('GEOMETRIA', 31, True)
    para('Distância de E0: 4,113 km\nAzimute geográfico: 249,40°\nDiferença para o relato: 0,40°\nDentro do raio de 6 km.', 29)
    para('RESULTADO BASE', 31, True)
    para('Setor da referência: R02-W\n22º entre 24 setores\nEscore: 0,502631', 30, True, '#007e87')
    para('Não está entre os três primeiros. O alinhamento com a pista não equivale a acerto do ranking.', 29)
    para('VARIAÇÕES DO PERFIL', 31, True)
    para('Posição de R02-W: 12º a 21º nas nove hipóteses de confiança e tolerância. Nenhuma o coloca no Top-3.', 28)
    para('Sem confiança avaliada: 22º. Não se escolheu uma hipótese depois de conhecer a referência.', 26, color='#59666a')
    para('TOP-3 BASE PRESERVADO', 30, True)
    for i, row in enumerate(rows[:3]):
        para(f"AP{i+1}  {short(row['sector_id'])}", 29, True, colors[i], 9)
    para('LEITURA CORRETA', 31, True, gap=10)
    para('Estado original: REVISAR. Esta é uma conferência descritiva, não uma validação de eficácia nem uma ordem de emprego de equipes.', 27)
    assert y < 1985, y
    footer = cart.block(cd, 'Losango amarelo: referência posteriormente declarada. Contorno verde-azulado: setor que a contém, sem representar prioridade. Polígonos coloridos: Top-3 BASE. Vermelho: domínio de análise. W = oeste; SW = sudoeste; E = leste.', 50, 1840, 1640, 25, color='#59666a')
    footer = cart.block(cd, 'Linha roxa tracejada: direção relatada de 249°, não trajetória. Representação desde E0 e norte geográfico conforme hipótese cartográfica anterior; origem exata e norte verdadeiro/magnético não confirmados.', 50, footer+10, 1640, 25, color='#59666a')
    assert footer < 2000, footer
    end = cart.block(cd, 'Base orbital histórica: Sentinel-2 / ESA WorldCover 2021, não outubro/2026. © ESA WorldCover project 2021; Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium. Vias/hidrografia: © OpenStreetMap contributors, consulta de 17/08/2026.', 50, 2010, 2280, 23, color='#59666a')
    assert end < 2100, end
    canvas.save(OUT / 'Mapa_MATA02_conferencia_referencia.png', dpi=(200, 200))
    return dict(bounds_lonlat=list(bounds), reference_pixel=[rx, ry], dimensions=list(canvas.size), visual_inspection='PENDENTE')


def main():
    if OUT.exists():
        # Resume only this script's incomplete delivery, never a completed package.
        assert not (OUT / 'QA_CONFERENCIA.json').exists(), 'Entrega concluída não será sobrescrita.'
        assert read(OUT / 'REFERENCIA_DECLARADA.json')['original_message'] == '-0.172250, -51.429583'
    preserved = [p for folder in (BASE, PROFILE, CASE / 'entrada_auditada_v2', CASE / 'mapa_priorizacao_v1', CASE / 'movimento_complementar_v1') for p in folder.rglob('*') if p.is_file()]
    before = {str(p.relative_to(ROOT)): sha(p) for p in preserved}
    rows = sorted(read(BASE / 'ranking_BASE_completo.json'), key=lambda r:r['rank_base_within_buffer'])
    geo = read(BASE / 'setores_BASE.geojson')
    matches = [f['properties']['sector_id'] for f in geo['features'] if contains((REF[1], REF[0]), f['geometry'])]
    assert matches == ['MATA-02::MATA-02-E0::R02::W'], matches
    target = next(r for r in rows if r['sector_id'] == matches[0])
    assert target['rank_base_within_buffer'] == 22
    d, az = inverse(E0, REF)
    assert abs(d - 4112.593775) < .001 and abs(az - 249.404438577) < 1e-7
    # Independent spherical sanity check; it is not the WGS84 reported metric.
    p1, p2, dl = math.radians(E0[0]), math.radians(REF[0]), math.radians(REF[1]-E0[1])
    hav = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    sphere_d = 6371008.8 * 2 * math.asin(math.sqrt(hav))
    assert abs(d-sphere_d) < 5
    comparison = []
    for conf, tol in [('NAO_AVALIADA',22.5)] + [(c,t) for c in ('BAIXA','MEDIA','ALTA') for t in (5,22.5,45)]:
        result = read(PROFILE / f'resultado_{conf}_{tol:g}.json')
        r = next(r for r in result['primary_rows'] if r['sector_id'] == matches[0])
        comparison.append(dict(confidence_assumed=conf, tolerance_assumed_deg=tol, rank=r['profile_rank'], score=r['profile_score'], effective_lambda=r['effective_lambda'], abstained=result['abstained']))
    assert [r['rank'] for r in comparison] == [22,21,19,17,20,16,12,20,16,12]
    assert all(r['rank'] > 3 for r in comparison)
    OUT.mkdir(parents=True, exist_ok=True)
    recorded = datetime.now(timezone.utc).isoformat()
    save('REFERENCIA_DECLARADA.json', dict(case_id='MATA-02', coordinate_lat_lon=REF, original_message='-0.172250, -51.429583', recorded_at_utc=recorded, nature='REFERENCIA_POSTERIOR_DECLARADA_DE_CENARIO_HIPOTETICO', source='Declaração do pesquisador nesta conversa', accuracy_m=None, independently_verified=False, used_in_frozen_ranking=False))
    findings = dict(case_id='MATA-02', initial_lat_lon=E0, reference_lat_lon=REF, method='WGS84 inverse Vincenty; polygon containment on original GeoJSON', distance_m=d, initial_true_azimuth_deg=az, difference_from_249_deg=az-249, inside_domain=True, informed_radius_m=6000, radial_margin_m=6000-d, eta=d/6000, sector_id=matches[0], base_rank=22, base_score=target['score_base'], in_base_top3=False, original_base_status='REVISAR', profile_comparison=comparison, in_any_frozen_profile_top3=False, motor_reexecuted=False, recalibration_performed=False, effectiveness_validated=False)
    save('COMPARACAO_RESULTADOS.json', findings)
    save('DECOMPOSICAO_SETOR_ORIGINAL.json', target)
    save('REFERENCIA_E_SETOR.geojson', dict(type='FeatureCollection', features=[dict(type='Feature', properties=dict(kind='REFERENCIA_DECLARADA_NAO_PREVISAO',case_id='MATA-02'),geometry=dict(type='Point',coordinates=[REF[1],REF[0]])), next(f for f in geo['features'] if f['properties']['sector_id']==matches[0])]))
    with (OUT / 'COMPARACAO_PERFIL.csv').open('w', newline='') as stream:
        writer=csv.DictWriter(stream, fieldnames=list(comparison[0]));writer.writeheader();writer.writerows(comparison)
    map_qa = render(rows, geo, target, d, az)
    near_old, _ = inverse((-0.172222,-51.430278),REF)
    report = f'''MATA-02 / MZG2 — CONFERÊNCIA POSTERIOR DA REFERÊNCIA DECLARADA

1. OBJETO E LIMITES
Referência recebida: -0.172250, -51.429583. Trata-se da localização declarada pelo pesquisador para o cenário hipotético, não de desfecho de ocorrência real verificado. Fonte instrumental e precisão não informadas. Comparação descritiva com o BASE congelado e as dez saídas PERFIL existentes. Não se alteraram entradas anteriores, geodados, pesos, raio, setores, motor, mapas anteriores ou dissertação.

2. RESULTADO
E0: -0.15916666666666668, -51.395. Raio informado: 6.000 m.
Distância geodésica WGS84: {d:.3f} m. Azimute geográfico inicial: {az:.6f}°.
Diferença para a pista 249°: {az-249:.6f}°. A comparação pressupõe a origem E0 e norte geográfico, como na representação anterior; a origem exata e a referência verdadeiro/magnético não foram confirmadas.
Dentro do domínio: sim. Margem radial: {6000-d:.3f} m. Razão distância/raio: {d/6000:.6f}.
Inclusão conferida nos polígonos originais: R02-W (oeste; segundo anel, aproximadamente 3,46–4,90 km).
BASE: 22º de 24, escore 0.502631369. Não está no Top-3.
AP1 R01-SW, AP2 R03-SW, AP3 R03-E permanecem preservados. A posição da referência não foi usada para escolher parâmetros.

3. VARIAÇÕES PERFIL JÁ EXISTENTES
Confiança/tolerância assumidas: ±5° / ±22,5° / ±45°.
BAIXA: 21º / 19º / 17º.
MÉDIA: 20º / 16º / 12º.
ALTA: 20º / 16º / 12º.
NÃO AVALIADA: 22º (controle ±22,5°, efeito quantitativo abstido).
Nenhuma configuração contém a referência no Top-3. MÉDIA e ALTA coincidem pelo limite de evidência RELATADO; não são replicações independentes. Os extremos 12º e 21º não são intervalo de confiança. Não há ranking PERFIL principal eleito nem probabilidade de encontro calculada.

4. O QUE EXPLICA A CLASSIFICAÇÃO, SEM REINTERPRETAR O RESULTADO
A decomposição original de R02-W é:
GEO-02 acesso: 0.130212583; contribuição ponderada 0.039063775.
GEO-03 hidrografia: 0.996283422; contribuição 0.249070855.
GEO-04 relevo: 0.660365639; contribuição 0.132073128.
GEO-05 cobertura: 0.329694444; contribuição 0.082423611.
A soma ponderada é 0.502631369. Acesso mapeado e cobertura têm valores baixos na convenção do BASE. Isso descreve o cálculo, não demonstra que a pessoa não poderia estar ali, nem que o setor seja desprovido de trilhas ou água. A pista direcional eleva a posição de R02-W em algumas hipóteses, mas não supera o ordenamento territorial a ponto de colocá-lo no Top-3. MOV não foi incorporado retrospectivamente ao ranking. Não se pode atribuir uma causa comportamental à localização com este ensaio.

5. INTERPRETAÇÃO PARA A DISSERTAÇÃO
O domínio contém a referência e a direção é coerente com ela sob as convenções adotadas. O ranking, porém, não a priorizou entre os três primeiros. As duas constatações devem ser apresentadas juntas. Manter o estado REVISAR e o resultado desfavorável, sem chamar o ensaio de validação de eficácia. Conforme decisão metodológica anterior, a localização declarada tem função descritiva, não de critério único de qualidade nem de alvo de otimização.
Recomendação para MATA-03: usar versão e regras registradas antes de conhecer sua referência. Qualquer alteração motivada por esta conferência deve constituir nova versão de desenvolvimento e não substituir o resultado original de MATA-02. Um caso hipotético isolado não calibra a distribuição real de pessoas desaparecidas.

6. ALERTAS DE PROVENIÊNCIA
A coordenada recebida está a aproximadamente {near_old:.1f} m do E0 previamente informado para MATA-01 (-0.172222, -51.430278). Não se assume erro de identificação: foi mantida como referência do MATA-02 conforme a conversa. Registrar possível sobreposição territorial; os casos não devem ser tratados automaticamente como amostras espaciais independentes.
Há metadado legado em R02-W que menciona nove pontos, enquanto o pacote registra 3.600 amostras por setor. Essa inconsistência descritiva já existente foi apenas anotada; não se modificou o original e ela não muda a inclusão geométrica nem os postos lidos nesta conferência.
A cartografia reutiliza a composição orbital histórica de 2021, não imagem de outubro de 2026. As fontes geoespaciais e a precisão da referência têm limitações próprias. Os valores métricos com casas decimais indicam precisão de cálculo, não acurácia do ponto informado.

7. VERIFICAÇÃO E ARQUIVOS
WGS84 conferido independentemente por um segundo agente e por cálculo esférico de sanidade ({sphere_d:.3f} m; diferença esperada de método). Inclusão conferida no GeoJSON original. Os dez postos foram lidos de saídas preservadas, sem nova execução do modelo. Hashes antes e depois registram preservação dos pacotes consultados. O mapa deve ser inspecionado visualmente; o estado final dessa inspeção consta de QA_CONFERENCIA.json.
Fontes principais: ensaio_complementar_v2_249/ranking_BASE_completo.json e setores_BASE.geojson; direcao_249_confirmada_v2_20261030/resultado_*.json; entrada_auditada_v2/entrada_raio_fonte_mata02_mzg2.geojson. Nenhum resultado novo de eficácia, teste de campo ou avaliação por especialistas foi produzido.
'''
    (OUT / 'RELATORIO_CONFERENCIA_MATA02.txt').write_text(report)
    after = {str(p.relative_to(ROOT)):sha(p) for p in preserved}
    assert before == after
    save('MANIFESTO_PRESERVACAO.json', dict(checked_at_utc=recorded, all_preserved=True, file_count=len(before), before_sha256=before, after_sha256=after))
    save('QA_CONFERENCIA.json', dict(geometry_verified=True, ranks_verified_against_frozen_outputs=True, independent_review=True, spherical_sanity_distance_m=sphere_d, preserved_files=len(before), originals_unchanged=True, engine_not_reexecuted=True, map=map_qa))
    print(json.dumps(dict(output=str(OUT), distance_m=d, azimuth=az, sector=short(matches[0]), base_rank=22, original_files_unchanged=len(before)),indent=2))


if __name__ == '__main__':
    main()
