"""Comparação descritiva posterior; não executa nem modifica o motor congelado."""
import hashlib
import json
import math
import argparse
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'outputs/campo_mata03_km21'
CLOSURE = BASE / 'conclusao_direcao285_v1'
OUT = BASE / 'comparacao_referencia_v2_20261103'
PREVIOUS = BASE / 'comparacao_referencia_v1'
POINT = (0.255247, -51.092333)

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

manifest = read(CLOSURE / 'manifesto_conclusao.json')
manifest_hash = sha(CLOSURE / 'manifesto_conclusao.json')

def verify_frozen():
    verified = {}
    for folder, key in [(BASE, 'base_files_sha256'), (CLOSURE, 'files_sha256')]:
        for name, expected in manifest[key].items():
            path = folder / name
            actual = sha(path)
            if actual != expected:
                raise RuntimeError(f'Arquivo congelado divergente: {path}')
            verified[str(path.relative_to(BASE))] = actual
    assert sha(CLOSURE / 'manifesto_conclusao.json') == manifest_hash
    return verified

before = verify_frozen()
previous_hashes = {p.name: sha(p) for p in sorted(PREVIOUS.iterdir()) if p.is_file()}
premises = read(BASE / 'premissas_congeladas.json')
origin = (premises['coordinates']['lat'], premises['coordinates']['lon'])
ranking = read(BASE / 'ranking_BASE.json')
sectors = read(BASE / 'setores_BASE.geojson')['features']
summary = read(CLOSURE / 'resumo_conclusao.json')
provenance = read(CLOSURE / 'proveniencia_fundo.json')

def vincenty(p1, p2):
    a, f = 6378137.0, 1 / 298.257223563
    b = a * (1-f)
    lat1, lon1, lat2, lon2 = map(math.radians, (*p1, *p2))
    u1, u2 = math.atan((1-f)*math.tan(lat1)), math.atan((1-f)*math.tan(lat2))
    su1, cu1, su2, cu2 = math.sin(u1), math.cos(u1), math.sin(u2), math.cos(u2)
    L = lon2-lon1
    lam = L
    for iteration in range(200):
        sl, cl = math.sin(lam), math.cos(lam)
        ss = math.hypot(cu2*sl, cu1*su2-su1*cu2*cl)
        if ss == 0:
            return 0.0, 0.0
        cs = su1*su2+cu1*cu2*cl
        sigma = math.atan2(ss, cs)
        sa = cu1*cu2*sl/ss
        c2a = 1-sa*sa
        c2sm = cs-2*su1*su2/c2a if c2a else 0
        c = f/16*c2a*(4+f*(4-3*c2a))
        new = L+(1-c)*f*sa*(sigma+c*ss*(c2sm+c*cs*(-1+2*c2sm*c2sm)))
        if abs(new-lam) < 1e-13:
            lam = new
            break
        lam = new
    else:
        raise RuntimeError('Vincenty não convergiu')
    usq = c2a*(a*a-b*b)/(b*b)
    A = 1+usq/16384*(4096+usq*(-768+usq*(320-175*usq)))
    B = usq/1024*(256+usq*(-128+usq*(74-47*usq)))
    ds = B*ss*(c2sm+B/4*(cs*(-1+2*c2sm*c2sm)-B/6*c2sm*(-3+4*ss*ss)*(-3+4*c2sm*c2sm)))
    distance = b*A*(sigma-ds)
    bearing = math.degrees(math.atan2(cu2*math.sin(lam), cu1*su2-su1*cu2*math.cos(lam))) % 360
    return distance, bearing

def inside(lon, lat, poly):
    hit = False
    for (x1,y1), (x2,y2) in zip(poly, poly[1:]+poly[:1]):
        if (y1 > lat) != (y2 > lat) and lon < (x2-x1)*(lat-y1)/(y2-y1)+x1:
            hit = not hit
    return hit

matches = [s for s in sectors if inside(POINT[1], POINT[0], s['geometry']['coordinates'][0])]
assert len(matches) == 1
sector_id = matches[0]['properties']['sector_id']
row = next(r for r in ranking if r['sector_id'] == sector_id)
distance, bearing = vincenty(origin, POINT)
delta = abs((bearing-285+180) % 360-180)
assert sector_id.endswith('::R03::NE')
assert row['rank_base_within_buffer'] == 2
assert abs(distance-6099.998178911) < .01
assert abs(bearing-47.999827279) < 1e-7
radius = premises['domain']['radius_m']
created = datetime.now(timezone.utc).isoformat()
result = {
    'case_id': 'MATA-03', 'comparison_created_at': created,
    'nature': 'COMPARACAO_DESCRITIVA_POSTERIOR_DE_ENSAIO_CONTROLADO',
    'revision': 'Revisão da referência declarada solicitada pelo pesquisador após conhecimento da saída; não é novo teste cego.',
    'previous_comparison': str(PREVIOUS.relative_to(ROOT)),
    'previous_comparison_files_sha256': previous_hashes,
    'reference': {'latitude':POINT[0], 'longitude':POINT[1], 'source':'Coordenada declarada pelo pesquisador na conversa após a saída congelada', 'accuracy_m':None},
    'origin': {'latitude':origin[0], 'longitude':origin[1]},
    'method':'Geodésica inversa Vincenty / elipsoide WGS84; ponto em polígono sobre os setores congelados',
    'distance_m':distance, 'initial_geographic_bearing_deg':bearing,
    'reported_direction_deg':285, 'angular_difference_deg':delta,
    'north_reference_caveat':'Norte da direção relatada não especificado; comparação angular pressupõe referências compatíveis.',
    'domain_radius_m':radius, 'inside_domain':distance <= radius,
    'radial_margin_m':radius-distance, 'sector_id':sector_id,
    'rank_base':row['rank_base_within_buffer'], 'sectors_count':len(ranking),
    'score_base':row['score_base'], 'in_top3':row['rank_base_within_buffer'] <= 3,
    'original_status':summary['base_status'], 'original_profile_status':summary['profile_status'],
    'original_top3':summary['top3'],
    'original_direction_confidence':'NAO_AVALIADA',
    'original_ranking_changed':False, 'parameters_changed':False,
    'frozen_files_verified':len(before), 'frozen_manifest_sha256':manifest_hash,
    'interpretation':'A referência revista está no setor R03-NE, segundo de 24 no ranking BASE original. É uma comparação descritiva posterior, não melhora do motor, novo teste cego ou comprovação de eficácia operacional. A diferença angular para a pista é de aproximadamente 123°, sem trajetória observada que explique o percurso. Escore não é probabilidade.',
    'reference_sector_rank_by_frozen_weight_set': {'BASE':2,'IGUAIS':4,'SEM_BARREIRAS':1,'APENAS_ACESSO':1,'ENFASE_BARREIRAS':4}
}

parser = argparse.ArgumentParser()
parser.add_argument('--refresh-generated', action='store_true', help='Regenerar somente este pacote novo para ajuste de apresentação.')
args = parser.parse_args()
if OUT.exists() and not args.refresh_generated:
    raise RuntimeError(f'Diretório de comparação já existe; não será sobrescrito: {OUT}')
if OUT.exists():
    old_manifest = read(OUT / 'manifesto_comparacao.json')
    assert old_manifest['case_id'] == 'MATA-03'
    assert old_manifest['previous_comparison_files_sha256'] == previous_hashes
OUT.mkdir(parents=True, exist_ok=args.refresh_generated)
(OUT / 'comparacao_referencia.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

report = f'''MATA-03 — REVISÃO DA REFERÊNCIA DECLARADA — V2

Resultado: a referência revista está dentro do domínio de 7 km, a aproximadamente 6,10 km de E0, no setor R03-NE, segundo entre 24 no ranking BASE original. O status REVISAR permanece.

ESCOPO DA REVISÃO
Coordenada atual adotada por solicitação do pesquisador: 0.255247, -51.092333. A comparação anterior está preservada em comparacao_referencia_v1; não é caracterizada como erro. A revisão ocorreu após conhecimento da saída. Não corresponde a nova aplicação cega, recalibração ou melhora do modelo.

REFERÊNCIAS
E0: {origin[0]:.9f}, {origin[1]:.9f}.
Ponto declarado: {POINT[0]:.6f}, {POINT[1]:.6f}.
Fonte do ponto: informação posterior do pesquisador na conversa. Precisão de posicionamento não informada; casas decimais não demonstram acurácia.

COMPARAÇÃO
Distância geodésica WGS84: {distance:.6f} m (aproximadamente 6,10 km).
Azimute geográfico inicial: {bearing:.9f}°.
Diferença angular para 285°: {delta:.9f}°.
Domínio informado: 7.000 m. Margem radial restante: {radius-distance:.6f} m.
Setor único contendo a referência: {sector_id} (R03-NE).
Limites radiais do setor: {row['inner_radius_m']:.6f}–{row['outer_radius_m']:.6f} m.
Limites angulares do setor: {row['azimuth_start_deg']}°–{row['azimuth_end_deg']}°.
Posição no ranking BASE: {row['rank_base_within_buffer']} de {len(ranking)}.
Escore BASE: {row['score_base']:.9f}. Não é probabilidade.
Top-3 original: R01-E (0,737195475), R03-NE (0,736014506), R01-SE (0,735688670).
Status original: REVISAR. PERFIL principal: ABSTENCAO_PERFIL.

INTERPRETAÇÃO E LIMITES
1. A referência revista coincide com o segundo setor do ranking BASE original, sem alteração de pesos ou escores. Isso descreve a relação geométrica com esta referência e não demonstra eficácia operacional ou melhora do motor.
2. O azimute geográfico E0–referência é aproximadamente 48°, com diferença de aproximadamente 123° para a pista de 285°. O norte da pista não foi especificado como verdadeiro ou magnético; a comparação pressupõe referências compatíveis. A linha no mapa é uma ligação geométrica, não o percurso realizado. Mudanças de rumo permanecem hipótese, não explicação demonstrada.
3. O raio de 7 km é um domínio informado para o ensaio, não uma probabilidade de contenção calibrada. Estar dentro dele não demonstra que a prioridade foi adequada.
4. Trata-se de território e imagens reais com pessoa e cronologia simuladas. A localização declarada é referência descritiva do ensaio, não prova de resgate real nem base para calcular uma taxa geral de acerto.
5. O ponto inicial corresponde à referência de chegada; não há posição confirmada do contato das 12h. As 19h30 desde esse contato não representam caminhada contínua.
6. A pista de 285° tinha confiança não avaliada e não alterou o ranking BASE. Mantém-se ABSTENCAO_PERFIL, sem aumento retrospectivo de confiança. Nos conjuntos de pesos congelados, R03-NE ocupa BASE 2º, IGUAIS 4º, SEM_BARREIRAS 1º, APENAS_ACESSO 1º e ENFASE_BARREIRAS 4º: a inclusão no Top-3 não é invariável. Mantêm-se os alertas de margem baixa e instabilidade.
7. O fundo Sentinel-2/ESA WorldCover é de 2021, apenas contextual. Não representa aquisição de 2026 e não participou do ranking. Não é Google Earth.

PRESERVAÇÃO
Foram conferidos {len(before)} arquivos contra o manifesto de conclusão antes e depois da geração. Nenhum resultado congelado ou parâmetro foi alterado. Os arquivos da comparação anterior também foram conferidos e preservados. Este pacote gera uma comparação nova; atualizações editoriais dependentes são realizadas em versões separadas.
O ranking_BASE.json é a fonte da ordenação, conforme a errata documental já existente no pacote; não se utilizou a lista Top-3 vazia do resultado_BASE.json.
Históricos de ausência da referência permanecem intactos; esta comparação é um registro posterior separado.

FONTES LOCAIS
premissas_congeladas.json; ranking_BASE.json; setores_BASE.geojson; conclusao_direcao285_v1/resumo_conclusao.json; conclusao_direcao285_v1/manifesto_conclusao.json; conclusao_direcao285_v1/proveniencia_fundo.json.

Registro de geração: {created}
'''
(OUT / 'relatorio_comparacao.txt').write_text(report, encoding='utf-8')

# Figura analítica composta de dados geográficos existentes; não altera fotografias.
canvas = Image.new('RGB', (2380,2110), 'white')
draw = ImageDraw.Draw(canvas)
font_path = '/System/Library/Fonts/Supplemental/Arial.ttf'
bold_path = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
def font(n, bold=False):
    return ImageFont.truetype(bold_path if bold else font_path, n)
def text(x,y,t,n=28,fill='#263238',bold=False):
    draw.text((x,y),t,font=font(n,bold),fill=fill)
text(50,35,'MATA-03 | Referência declarada revista — V2',52,bold=True)
text(50,105,'Ranking original preservado • Ensaio controlado • Referência revista após conhecimento da saída',28)
left, top, size = 50,165,1650
sat = Image.open(CLOSURE/'fundo_satelite_2021.png').convert('RGB').resize((size,size), Image.Resampling.LANCZOS)
canvas.paste(sat,(left,top))
bbox = provenance['bbox_latlon']
def xy(lon,lat):
    return (left+(lon-bbox[1])/(bbox[3]-bbox[1])*size, top+(bbox[2]-lat)/(bbox[2]-bbox[0])*size)
overlay = Image.new('RGBA',canvas.size,(0,0,0,0))
od = ImageDraw.Draw(overlay)
colors = [(239,181,65),(85,184,238),(241,120,104)]
top_ids = [r['sector_id'] for r in ranking[:3]]
for feature in sectors:
    sid = feature['properties']['sector_id']
    pts = [xy(*p[:2]) for p in feature['geometry']['coordinates'][0]]
    if sid in top_ids:
        color = colors[top_ids.index(sid)]
        od.polygon(pts, fill=(*color,75))
    od.line(pts,fill=(255,255,255,170),width=3)
    if sid in top_ids:
        od.line(pts,fill=(*colors[top_ids.index(sid)],255),width=7)
    if sid == sector_id:
        od.line(pts,fill=(255,255,255,255),width=14)
        od.line(pts,fill=(169,104,211,255),width=8)
canvas = Image.alpha_composite(canvas.convert('RGBA'),overlay).convert('RGB')
draw = ImageDraw.Draw(canvas)
ox,oy=xy(origin[1],origin[0]); px,py=xy(POINT[1],POINT[0])
draw.line((ox,oy,px,py),fill='white',width=9)
length=math.hypot(px-ox,py-oy)
for start in range(0,int(length),28):
    end=min(start+17,length)
    draw.line((ox+(px-ox)*start/length,oy+(py-oy)*start/length,ox+(px-ox)*end/length,oy+(py-oy)*end/length),fill='#713D95',width=5)
def label(x,y,t):
    box=draw.textbbox((x,y),t,font=font(29,True))
    draw.rectangle((box[0]-9,box[1]-6,box[2]+9,box[3]+7),fill='white',outline='#59636A',width=1)
    text(x,y,t,29,bold=True)
draw.ellipse((ox-13,oy-13,ox+13,oy+13),fill='#243B53',outline='white',width=5)
label(ox+22,oy+12,'E0')
draw.polygon([(px,py-23),(px+23,py),(px,py+23),(px-23,py)],fill='#713D95',outline='white',width=5)
label(px+40,py+35,'Referência')
for i,r in enumerate(ranking[:3]):
    x,y=xy(r['representative_lon'],r['representative_lat'])
    label(x-58,y-18,f"{i+1} · {'-'.join(r['sector_id'].split('::')[-2:])}")
# Norte geográfico e escala aproximada local.
draw.polygon([(1640,205),(1623,260),(1640,249),(1657,260)],fill='white',outline='#243B53')
text(1627,265,'N',30,fill='white',bold=True)
scale_width=2000/(111319.49079327357*math.cos(math.radians(origin[0])))/(bbox[3]-bbox[1])*size
draw.rectangle((80,1730,80+scale_width+24,1794),fill='white')
draw.line((92,1754,92+scale_width,1754),fill='#243B53',width=6)
draw.line((92,1745,92,1763),fill='#243B53',width=4)
draw.line((92+scale_width,1745,92+scale_width,1763),fill='#243B53',width=4)
text(100,1765,'2 km (aprox.)',20)
draw.rectangle((left,top,left+size,top+size),outline='#5F6B73',width=2)

sx=1740
text(sx,180,'RESULTADO DA COMPARAÇÃO',29,bold=True)
items=[('Distância desde E0','6,10 km'),('Azimute geográfico','47,9998°'),('Dentro do domínio de 7 km','Sim'),('Setor da referência','R03-NE'),('Posição no ranking BASE','2º de 24'),('Entre as três primeiras áreas','Sim'),('Status original','REVISAR')]
yy=245
for heading,value in items:
    text(sx,yy,heading,25,fill='#56636E')
    text(sx,yy+35,value,37,bold=True)
    yy+=106
text(sx,1030,'LEGENDA',29,bold=True)
for i,(name,color) in enumerate(zip(['1 · R01-E','2 · R03-NE','3 · R01-SE'],colors)):
    draw.rectangle((sx,1085+i*52,sx+34,1115+i*52),fill=color)
    text(sx+49,1080+i*52,name,28)
draw.rectangle((sx,1250,sx+34,1280),outline='#A968D3',width=5)
text(sx+49,1245,'Setor da referência (2º)',26)
draw.polygon([(sx+17,1303),(sx+32,1318),(sx+17,1333),(sx+2,1318)],fill='#713D95')
text(sx+49,1300,'Ponto declarado posteriormente',25)
draw.line((sx,1380,sx+34,1380),fill='#713D95',width=5)
text(sx+49,1360,'Ligação geométrica E0–referência',23)
text(sx+49,1393,'Não representa o percurso.',23)
text(sx,1470,'LEITURA CORRETA',29,bold=True)
for j,line in enumerate(['Referência no 2º setor original.','Revisão após conhecer a saída:','não é nova validação cega.','','Pista: 285°; ligação geométrica: 48°.','A pista não alterou o BASE.','Sem trajetória observada, não se','comprovam mudanças de rumo.']):
    text(sx,1520+j*35,line,25)
text(50,1850,'Referência: 0,255247; −51,092333 | E0: 0,218333; −51,133056 | Escore BASE da referência: 0,736014506',28,bold=True)
text(50,1900,'Comparação descritiva de cenário controlado. Escore não é probabilidade. Não comprova eficácia operacional.',27)
text(50,1950,'Fundo de 2021, apenas contextual; não participou do ranking. Sem alteração de pesos, raio, setores ou resultados originais.',25)
text(50,2000,'© ESA WorldCover project 2021. Contains modified Copernicus Sentinel data (2021), processed by ESA WorldCover consortium.',23)
text(50,2044,'Fontes: ranking_BASE.json, setores_BASE.geojson, resumo_conclusao.json e coordenada declarada posteriormente pelo pesquisador.',23)
canvas.save(OUT/'mapa_comparacao_MATA03.png',dpi=(180,180))
after=verify_frozen()
assert before == after
assert previous_hashes == {p.name: sha(p) for p in sorted(PREVIOUS.iterdir()) if p.is_file()}
output_manifest={
    'case_id':'MATA-03','created_at':created,
    'comparison_is_post_hoc':True,'frozen_files_verified_before_and_after':len(after),
    'previous_comparison_files_sha256':previous_hashes,'previous_comparison_unchanged':True,
    'frozen_files_unchanged':True,'frozen_manifest_sha256':manifest_hash,
    'script_sha256':sha(Path(__file__)),
    'input_files_sha256':after,
    'files_sha256':{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != 'manifesto_comparacao.json'}
}
(OUT/'manifesto_comparacao.json').write_text(json.dumps(output_manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'output':str(OUT),'distance_m':distance,'bearing_deg':bearing,'rank':row['rank_base_within_buffer'],'frozen_files_unchanged':len(after)},ensure_ascii=False))
