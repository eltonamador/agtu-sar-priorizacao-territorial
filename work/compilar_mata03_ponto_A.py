"""Compilação editorial do ponto A; não executa nem altera o motor."""
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'outputs/campo_mata03_km21'
CLOSURE = BASE / 'conclusao_direcao285_v1'
SOURCE = BASE / 'comparacao_referencia_v2_20261103/comparacao_referencia.json'
OUT = BASE / 'comparacao_referencia_A_20261103'
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
manifest = read(CLOSURE / 'manifesto_conclusao.json')
def verify():
    result = {}
    for folder, key in [(BASE, 'base_files_sha256'), (CLOSURE, 'files_sha256')]:
        for name, expected in manifest[key].items():
            p = folder / name
            assert sha(p) == expected, str(p)
            result[str(p.relative_to(BASE))] = expected
    return result
before = verify()
source_hash = sha(SOURCE)
assert not OUT.exists(), 'Pacote atual já existe; não sobrescrever.'
OUT.mkdir(parents=True)
result = read(SOURCE)
for key in ['previous_comparison', 'previous_comparison_files_sha256']:
    result.pop(key, None)
result['revision'] = 'Compilação atual com marcador A; referência declarada após a saída do modelo.'
result['reference']['label'] = 'A — local de encontro declarado'
result['interpretation'] = 'O ponto A está no setor R03-NE, segundo de 24 no ranking BASE preservado. Comparação descritiva posterior à saída; não é validação prospectiva nem comprovação de eficácia operacional. Sem trajetória observada, a diferença para a pista de 285° não explica o percurso. Escore não é probabilidade.'
result['compiled_at'] = datetime.now(timezone.utc).isoformat()
assert result['reference']['latitude'] == .255247 and result['reference']['longitude'] == -51.092333
assert result['rank_base'] == 2 and result['original_status'] == 'REVISAR'
(OUT / 'comparacao_referencia_A.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
ranking = read(BASE/'ranking_BASE.json')
sectors = read(BASE/'setores_BASE.geojson')['features']
provenance = read(CLOSURE/'proveniencia_fundo.json')
origin = (result['origin']['latitude'], result['origin']['longitude'])
point = (result['reference']['latitude'], result['reference']['longitude'])
sector_id = result['sector_id']
canvas = Image.new('RGB', (2380,2110), 'white')
draw = ImageDraw.Draw(canvas)
def font(n, bold=False):
    return ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial'+(' Bold' if bold else '')+'.ttf', n)
def text(x,y,t,n=28,fill='#263238',bold=False): draw.text((x,y),t,font=font(n,bold),fill=fill)
text(50,35,'MATA-03 | Ponto A — local de encontro declarado',52,bold=True)
text(50,105,'Ranking preservado • Ensaio controlado • Referência declarada após a saída do modelo',28)
left,top,size=50,165,1650
sat=Image.open(CLOSURE/'fundo_satelite_2021.png').convert('RGB').resize((size,size),Image.Resampling.LANCZOS)
canvas.paste(sat,(left,top))
bbox=provenance['bbox_latlon']
def xy(lon,lat): return (left+(lon-bbox[1])/(bbox[3]-bbox[1])*size,top+(bbox[2]-lat)/(bbox[2]-bbox[0])*size)
overlay=Image.new('RGBA',canvas.size,(0,0,0,0)); od=ImageDraw.Draw(overlay)
colors=[(239,181,65),(85,184,238),(241,120,104)]
top_ids=[r['sector_id'] for r in ranking[:3]]
for feature in sectors:
    sid=feature['properties']['sector_id']; pts=[xy(*p[:2]) for p in feature['geometry']['coordinates'][0]]
    if sid in top_ids: od.polygon(pts,fill=(*colors[top_ids.index(sid)],75))
    od.line(pts,fill=(255,255,255,170),width=3)
    if sid in top_ids: od.line(pts,fill=(*colors[top_ids.index(sid)],255),width=7)
    if sid == sector_id:
        od.line(pts,fill=(255,255,255,255),width=14)
        od.line(pts,fill=(*colors[1],255),width=8)
canvas=Image.alpha_composite(canvas.convert('RGBA'),overlay).convert('RGB'); draw=ImageDraw.Draw(canvas)
ox,oy=xy(origin[1],origin[0]); px,py=xy(point[1],point[0])
draw.line((ox,oy,px,py),fill='white',width=9)
length=math.hypot(px-ox,py-oy)
for start in range(0,int(length),28):
    end=min(start+17,length)
    draw.line((ox+(px-ox)*start/length,oy+(py-oy)*start/length,ox+(px-ox)*end/length,oy+(py-oy)*end/length),fill='#713D95',width=5)
def label(x,y,t):
    box=draw.textbbox((x,y),t,font=font(29,True))
    draw.rectangle((box[0]-9,box[1]-6,box[2]+9,box[3]+7),fill='white',outline='#59636A',width=1)
    text(x,y,t,29,bold=True)
draw.ellipse((ox-13,oy-13,ox+13,oy+13),fill='#243B53',outline='white',width=5); label(ox+22,oy+12,'E0')
draw.polygon([(px,py-23),(px+23,py),(px,py+23),(px-23,py)],fill='#713D95',outline='white',width=5); label(px+40,py+35,'A')
for i,r in enumerate(ranking[:3]):
    x,y=xy(r['representative_lon'],r['representative_lat']); label(x-58,y-18,f"{i+1} · {'-'.join(r['sector_id'].split('::')[-2:])}")
draw.polygon([(1640,205),(1623,260),(1640,249),(1657,260)],fill='white',outline='#243B53'); text(1627,265,'N',30,fill='white',bold=True)
scale=2000/(111319.49079327357*math.cos(math.radians(origin[0])))/(bbox[3]-bbox[1])*size
draw.rectangle((80,1730,80+scale+24,1794),fill='white'); draw.line((92,1754,92+scale,1754),fill='#243B53',width=6)
for x in [92,92+scale]: draw.line((x,1745,x,1763),fill='#243B53',width=4)
text(100,1765,'2 km (aprox.)',20); draw.rectangle((left,top,left+size,top+size),outline='#5F6B73',width=2)
sx=1740; text(sx,180,'RESULTADO DA COMPARAÇÃO',29,bold=True)
items=[('Distância desde E0','6,10 km'),('Azimute geográfico','47,9998°'),('Dentro do domínio de 7 km','Sim'),('Setor do ponto A','R03-NE'),('Posição no ranking BASE','2º de 24'),('Entre as três primeiras áreas','Sim'),('Status original','REVISAR')]
for j,(heading,value) in enumerate(items):
    yy=245+j*106; text(sx,yy,heading,25,fill='#56636E'); text(sx,yy+35,value,37,bold=True)
text(sx,1030,'LEGENDA',29,bold=True)
for i,(name,color) in enumerate(zip(['1 · R01-E','2 · R03-NE','3 · R01-SE'],colors)):
    draw.rectangle((sx,1085+i*52,sx+34,1115+i*52),fill=color); text(sx+49,1080+i*52,name,28)
draw.rectangle((sx,1250,sx+34,1280),outline=colors[1],width=5); text(sx+49,1245,'Setor do ponto A (2º)',26)
draw.polygon([(sx+17,1303),(sx+32,1318),(sx+17,1333),(sx+2,1318)],fill='#713D95'); text(sx+49,1300,'A — local de encontro declarado',23)
draw.line((sx,1380,sx+34,1380),fill='#713D95',width=5); text(sx+49,1360,'Ligação geométrica E0–A',23); text(sx+49,1393,'Não representa o percurso.',23)
text(sx,1470,'LEITURA CORRETA',29,bold=True)
for j,line in enumerate(['Ponto A no 2º setor original.','Referência declarada após a saída:','não é validação prospectiva.','','Pista: 285°; ligação geométrica: 48°.','A pista não alterou o BASE.','Sem trajetória observada, não se','comprovam mudanças de rumo.']): text(sx,1520+j*35,line,25)
text(50,1850,'A: 0,255247; −51,092333 | E0: 0,218333; −51,133056 | Escore BASE do setor de A: 0,736014506',28,bold=True)
text(50,1900,'Comparação descritiva de cenário controlado. Escore não é probabilidade. Não comprova eficácia operacional.',27)
text(50,1950,'Fundo de 2021, apenas contextual; não participou do ranking. Sem alteração de pesos, raio, setores ou resultados originais.',25)
text(50,2000,'© ESA WorldCover project 2021. Contains modified Copernicus Sentinel data (2021), processed by ESA WorldCover consortium.',23)
text(50,2044,'Fontes: ranking_BASE.json, setores_BASE.geojson, resumo_conclusao.json e coordenada declarada posteriormente pelo pesquisador.',23)
canvas.save(OUT/'mapa_comparacao_MATA03_A.png',dpi=(180,180))
assert before == verify() and source_hash == sha(SOURCE)
audit={'created_at':result['compiled_at'],'source_comparison_sha256':source_hash,'frozen_files_verified':len(before),'frozen_files_unchanged':True,'engines_rerun':False,'ranking_changed':False,'reference_post_output':True,'script_sha256':sha(Path(__file__)),'files_sha256':{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file()}}
(OUT/'manifesto_compilacao_A.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'output':str(OUT),'rank':result['rank_base'],'frozen_files_verified':len(before)},ensure_ascii=False))
