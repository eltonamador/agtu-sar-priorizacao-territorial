#!/usr/bin/env python3
"""Cartografia dos resultados existentes: não executa nem modifica o motor."""
import hashlib
import importlib.util
import io
import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'outputs/campo_mata02_mzg2/ensaio_complementar_v2_249'
OUT = ROOT / 'outputs/campo_mata02_mzg2/mapa_priorizacao_v1'
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'fontes').mkdir(exist_ok=True)
SIZE = 1650
LAT, LON = -0.15916666666666668, -51.395
EXTENT = 6750.
R = 6371008.8
COLORS = ['#176687', '#a56a00', '#bd5131']
INK, PURPLE, RED = '#263238', '#743d99', '#9c2032'
BASE_SCRIPT = ROOT / 'work/mata01_figura_multipainel_cega_v3/gerar_figura_mata01_cega_v3.py'
spec = importlib.util.spec_from_file_location('mapa_anterior', BASE_SCRIPT)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
old.LAT0, old.LON0, old.EXTENT_M, old.MAP_SIZE = LAT, LON, EXTENT, SIZE
bounds = old.lonlat_bounds()

def read(path):
    return json.loads(path.read_text())

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

def save_json(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

def f(size, bold=False):
    return ImageFont.truetype(old.FONT_BOLD if bold else old.FONT_REGULAR, size)

def block(draw, text, x, y, width, size=30, color=INK, bold=False, leading=1.3):
    font = f(size, bold)
    lines = []
    for para in text.split('\n'):
        line = ''
        for word in para.split():
            candidate = (line + ' ' + word).strip()
            if line and draw.textlength(candidate, font=font) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    for line in lines:
        draw.text((x, y), line, font=font, fill=color)
        y += round(size * leading)
    return y

def tag(draw, xy, text, color=INK, size=30, anchor='mm'):
    box = draw.textbbox(xy, text, font=f(size, True), anchor=anchor)
    draw.rectangle((box[0]-9, box[1]-6, box[2]+9, box[3]+7), fill='white', outline=color, width=2)
    draw.text(xy, text, font=f(size, True), fill=color, anchor=anchor)

def base():
    image_path = OUT / 'fontes/ESA_WorldCover_S2_TCC_2021_MATA02.png'
    meta_path = OUT / 'fontes/ESA_WorldCover_S2_TCC_2021_MATA02.metadata.json'
    minlon, minlat, maxlon, maxlat = bounds
    query = dict(SERVICE='WMS', VERSION='1.3.0', REQUEST='GetMap',
                 LAYERS='esa-worldcover-s2rgbnir-10m-2021-v2_tcc', STYLES='',
                 CRS='EPSG:4326', BBOX=f'{minlat},{minlon},{maxlat},{maxlon}',
                 WIDTH=2048, HEIGHT=2048, FORMAT='image/png', TRANSPARENT='FALSE', TIME='2021-01-01')
    url = 'https://titiler.terrascope.be/wms?' + urllib.parse.urlencode(query)
    if not image_path.exists():
        print('Consultando composição Sentinel-2 no recorte MATA-02...', flush=True)
        req = urllib.request.Request(url, headers={'User-Agent': 'Academic-cartography/1.0'})
        with urllib.request.urlopen(req, timeout=45) as response:
            data = response.read()
            headers = dict(response.headers)
            code = response.status
        img = Image.open(io.BytesIO(data))
        img.load()
        assert img.size == (2048, 2048)
        assert img.format == 'PNG'
        image_path.write_bytes(data)
        save_json('fontes/' + meta_path.name, dict(
            provider='ESA WorldCover / Terrascope (VITO)', request_url=url,
            bounds_lon_lat=list(bounds), crs='EPSG:4326', wms_axis_order='latitude,longitude',
            retrieved_at_utc=datetime.now(timezone.utc).isoformat(), http_status=code,
            response_headers=headers, sha256=sha(image_path), source_period=2021,
            purpose='Contexto cartográfico; não usado para recalcular o ranking',
            attribution='© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium'))
    meta = read(meta_path)
    assert meta['sha256'] == sha(image_path)
    assert meta['bounds_lon_lat'] == list(bounds)
    return Image.open(image_path).convert('RGBA').resize((SIZE,SIZE), Image.Resampling.LANCZOS), meta

def main():
    paths = [SRC / name for name in ['ranking_BASE_completo.json', 'setores_BASE.geojson',
             'referencia_249_contextual.geojson', 'RESULTADO_ENSAIO.json']]
    hashes_before = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    rows = sorted(read(paths[0]), key=lambda r:r['rank_base_within_buffer'])
    top = rows[:3]
    assert [r['sector_id'].split('::')[-2:] for r in top] == [['R01','SW'],['R03','SW'],['R03','E']]
    geo = read(paths[1])
    assert len(geo['features']) == 24
    image, metadata = base()
    print('Base orbital recebida; desenhando polígonos conferidos.', flush=True)
    old.add_osm(image,bounds)
    draw = ImageDraw.Draw(image)
    lookup = {r['sector_id']: i for i,r in enumerate(top)}
    for feature in geo['features']:
        poly = [old.lonlat_to_px(*p,bounds) for p in feature['geometry']['coordinates'][0]]
        assert all(0 <= x < SIZE and 0 <= y < SIZE for x,y in poly)
        draw.line(poly, fill='white', width=4, joint='curve')
        draw.line(poly, fill='#515b5d', width=2, joint='curve')
        idx = lookup.get(feature['properties']['sector_id'])
        if idx is None:
            continue
        layer = Image.new('RGBA',image.size)
        ld = ImageDraw.Draw(layer)
        rgb = tuple(int(COLORS[idx][k:k+2],16) for k in (1,3,5))
        ld.polygon(poly, fill=rgb+(65,))
        mask = Image.new('L',image.size)
        ImageDraw.Draw(mask).polygon(poly,fill=255)
        pattern = Image.new('RGBA',image.size)
        pd = ImageDraw.Draw(pattern)
        if idx == 1:
            for yy in range(0,SIZE,32):
                for xx in range(0,SIZE,32):
                    pd.ellipse((xx-3,yy-3,xx+3,yy+3),fill=rgb+(220,))
        else:
            for shift in range(-SIZE,SIZE*2,36):
                if idx == 0:
                    pd.line((shift,SIZE,shift+SIZE,0),fill=rgb+(200,),width=3)
                else:
                    pd.line((shift,0,shift+SIZE,SIZE),fill=rgb+(200,),width=3)
        layer.alpha_composite(Image.composite(pattern,Image.new('RGBA',image.size),mask))
        image.alpha_composite(layer)
        draw = ImageDraw.Draw(image)
        draw.line(poly,fill='white',width=11,joint='curve')
        draw.line(poly,fill=COLORS[idx],width=7,joint='curve')
    buffer_path = ROOT / 'outputs/campo_mata02_mzg2/entrada_auditada_v2/entrada_raio_fonte_mata02_mzg2.geojson'
    ring = read(buffer_path)['features'][0]['geometry']['coordinates'][0]
    draw.line([old.lonlat_to_px(*p,bounds) for p in ring], fill=RED, width=4,joint='curve')
    line = read(paths[2])['features'][0]['geometry']['coordinates']
    a,b = old.lonlat_to_px(*line[0],bounds),old.lonlat_to_px(*line[-1],bounds)
    old.draw_dashed_segment(draw,a,b,fill='white',width=13,dash=26,gap=14)
    old.draw_dashed_segment(draw,a,b,fill=PURPLE,width=7,dash=26,gap=14)
    angle = math.atan2(b[1]-a[1],b[0]-a[0])
    arrow = [b,(b[0]-34*math.cos(angle-.42),b[1]-34*math.sin(angle-.42)),
                (b[0]-34*math.cos(angle+.42),b[1]-34*math.sin(angle+.42))]
    draw.polygon(arrow,fill=PURPLE,outline='white',width=2)
    tag(draw,((a[0]+b[0])/2-75,(a[1]+b[1])/2-48),'249° — relato',PURPLE,29)
    for i,row in enumerate(top):
        xy = old.lonlat_to_px(row['representative_lon'],row['representative_lat'],bounds)
        tag(draw,xy,f"AP{i+1}  {row['ring_id']}-{row['direction']}",COLORS[i],31)
    ox,oy = old.lonlat_to_px(LON,LAT,bounds)
    draw.ellipse((ox-14,oy-14,ox+14,oy+14),fill='white',outline=RED,width=5)
    draw.line((ox-23,oy,ox+23,oy),fill=RED,width=4)
    draw.line((ox,oy-23,ox,oy+23),fill=RED,width=4)
    tag(draw,(ox+64,oy-31),'E0',RED,35)
    for label,az in [('N',0),('NE',45),('L',90),('SE',135),('S',180),('SO',225),('O',270),('NO',315)]:
        distance = 6350
        x = SIZE/2+distance*math.sin(math.radians(az))*SIZE/(2*EXTENT)
        y = SIZE/2-distance*math.cos(math.radians(az))*SIZE/(2*EXTENT)
        draw.text((x,y),label,font=f(31,True),fill=INK,anchor='mm',stroke_width=4,stroke_fill='white')
    draw.rectangle((SIZE-138,22,SIZE-25,177),fill='white',outline='#59666a',width=1)
    draw.polygon([(SIZE-82,42),(SIZE-106,112),(SIZE-82,98),(SIZE-58,112)],fill=INK)
    draw.text((SIZE-82,145),'N',font=f(34,True),fill=INK,anchor='mm')
    scale = SIZE*1000/(2*EXTENT)
    draw.rectangle((25,SIZE-119,45+2*scale,SIZE-25),fill='white')
    for i in range(2):
        draw.rectangle((40+i*scale,SIZE-65,40+(i+1)*scale,SIZE-50),fill=INK if i==0 else 'white',outline=INK,width=2)
    draw.text((40,SIZE-104),'0',font=f(27),fill=INK)
    draw.text((40+scale,SIZE-104),'1',font=f(27),fill=INK,anchor='ma')
    draw.text((40+2*scale,SIZE-104),'2 km',font=f(27),fill=INK,anchor='ra')
    canvas = Image.new('RGB',(2380,1985),'white')
    d = ImageDraw.Draw(canvas)
    block(d,'MATA-02 | Posições dos setores em relação ao ponto inicial',50,35,2280,44,bold=True)
    block(d,'Ensaio complementar • território real, ocorrência hipotética • raio de 6 km • resultado BASE: REVISAR',50,99,2280,30,color='#59666a')
    canvas.paste(image.convert('RGB'),(50,165))
    d.rectangle((50,165,50+SIZE,165+SIZE),outline='#738086',width=2)
    x,w,y = 1745,580,174
    y=block(d,'REFERÊNCIA INICIAL',x,y,w,31,bold=True)+16
    y=block(d,'E0 — registro do iPhone\n0°09′33″ S  |  51°23′42″ O\n−0,1591667; −51,3950000',x,y,w,30)+18
    y=block(d,'Ponto do exercício; não comprova o último local onde a pessoa foi vista.',x,y,w,27,color='#59666a')+35
    y=block(d,'TRÊS PRIMEIROS DO BASE',x,y,w,31,bold=True)+17
    directions = ['Sudoeste • 0–3,46 km de E0','Sudoeste • 4,90–6,00 km de E0','Leste • 4,90–6,00 km de E0']
    for i,row in enumerate(top):
        y=block(d,f"AP{i+1}  {row['ring_id']}-{row['direction']}",x,y,w,34,COLORS[i],True)
        y=block(d,directions[i],x,y+4,w,29)
        y=block(d,'Escore: '+f"{row['score_base']:.6f}".replace('.',','),x,y+2,w,28,color='#59666a')+22
    y=block(d,'AP1–AP3 são áreas, não posições da pessoa. Os rótulos apenas identificam cada setor.',x,y,w,27,color='#59666a')+30
    y=block(d,'DIREÇÃO RELATADA: 249°',x,y,w,31,PURPLE,True)+10
    y=block(d,'Linha roxa tracejada, desenhada a partir de E0. A pista não entrou no ranking BASE mostrado.',x,y,w,29)+14
    y=block(d,'249° está na faixa Oeste (W), junto ao limite de 247,5° com Sudoeste (SW). Não é rota confirmada.',x,y,w,27,color='#59666a')+30
    y=block(d,'LEITURA COM CAUTELA',x,y,w,31,bold=True)+9
    y=block(d,'REVISAR: baixa margem entre escores, sensibilidade aos pesos e alertas de barreira/revisão da entrada. Não é probabilidade de presença nem ordem operacional.',x,y,w,28)+20
    y=block(d,'Anéis: R01 até 3,46 km; R02 de 3,46 a 4,90 km; R03 de 4,90 a 6,00 km. Limite vermelho: domínio de análise.',x,y,w,27,color='#59666a')
    assert y<1810,y
    footer='Base orbital: composição anual Sentinel-2 / ESA WorldCover 2021 (histórica; não é imagem de outubro de 2026). Vias e hidrografia: © OpenStreetMap contributors, 17/08/2026.'
    y=block(d,footer,50,1840,2280,24,color='#59666a')+6
    y=block(d,'© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium.',50,y,2280,22,color='#59666a')+5
    y=block(d,'Norte geográfico adotado apenas para representação; referência magnética do relato não informada. Extensão da seta não estima deslocamento. Coordenadas geográficas; escala local aproximada.',50,y,2280,22,color='#59666a')
    assert y<1980,y
    target = OUT / 'Mapa_MATA02_E0_AP1_AP2_AP3_249.png'
    canvas.save(target,dpi=(200,200))
    assert hashes_before == {str(p.relative_to(ROOT)):sha(p) for p in paths}
    save_json('QA_CARTOGRAFIA.json',dict(
        status='VERIFICACOES_NUMERICAS_OK_INSPECAO_VISUAL_PENDENTE',
        source_hashes=hashes_before, frozen_sources_unchanged=True,
        top3=[{k:r[k] for k in ('sector_id','score_base','representative_lon','representative_lat','inner_radius_m','outer_radius_m')} for r in top],
        map_bounds_lon_lat=list(bounds), dimensions=[2380,1985], sector_count=24,
        direction_included_in_BASE=False, direction_graphic_only=True, angle_from_geographic_north_for_display=249,
        image_sha256=sha(target), satellite_metadata=metadata,
        renderer=str(Path(__file__).relative_to(ROOT)), reused_geometry_render_helpers=str(BASE_SCRIPT.relative_to(ROOT))))
    print(json.dumps({'png':str(target),'qa':str(OUT/'QA_CARTOGRAFIA.json')},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
