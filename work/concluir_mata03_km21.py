"""Finish one MATA-03 run; preserve the immutable BASE and held-out target."""
import datetime as dt
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'outputs/campo_mata03_km21'
OUT = BASE / 'conclusao_direcao285_v1'
OUT.mkdir(parents=True, exist_ok=True)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())
def save(name, obj):
    (OUT/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
def short(s): return '-'.join(s.split('::')[-2:])
before = {p.name:sha(p) for p in BASE.iterdir() if p.is_file()}
ranking = read(BASE/'ranking_BASE.json')
ranking.sort(key=lambda r:r['rank_base_within_buffer'])
geo = read(BASE/'setores_BASE.geojson')
polygons = {f['properties']['sector_id']:f['geometry']['coordinates'][0] for f in geo['features']}
now = dt.datetime.now(dt.timezone.utc).isoformat()
spec = importlib.util.spec_from_file_location('perfil_mata03', ROOT/'work/perfil_vitima_v3/profile_ranker.py')
engine = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = engine
spec.loader.exec_module(engine)
config = ROOT/'outputs/modulo_perfil_vitima_v3/config_perfil_quantitativo_v3.json'

def run(confidence, tolerance):
    payload = {
        'protocol_version':'PERFIL-V3-QUANT-v1.0',
        'scenario_id':'MATA-03', 'candidate_id':'MATA-03-E0',
        'record_status':'CONGELADO', 'created_at':now,
        'ground_truth_absent':True,
        'source_loc_input_sha256':sha(BASE/'entrada_raio_fonte_mata03_km21.json'),
        'source_case_revision':1,
        'source_profile_compiled_sha256':sha(BASE/'premissas_congeladas.json'),
        'source_territorial_manifest_sha256':sha(BASE/'manifesto_BASE.json'),
        'source_spatial_review_sha256':sha(BASE/'verificacao_espacial.json'),
        'sectors':[{'sector_id':r['sector_id'], 'territorial_score':r['score_base'],
                    'bearing_start_deg':r['azimuth_start_deg'], 'bearing_end_deg':r['azimuth_end_deg'],
                    'polygon':polygons[r['sector_id']]} for r in ranking],
        'hypotheses':[{'hypothesis_id':'MATA03-DIR285', 'evidence_group_id':'RELATO285',
                       'family':'DIRECAO', 'hypothesis_type':'DIRECAO_OBSERVADA',
                       'spatialized':True, 'authorized_for_model':True, 'nature':'RELATADO',
                       'confidence':confidence,
                       'direction':{'origin_candidate_id':'MATA-03-E0', 'azimuth_deg':285,
                                    'tolerance_deg':tolerance}}]
    }
    frozen = engine.prepare_frozen_input(payload, frozen_at=now)
    result = engine.rank_profile(frozen, config_path=config)
    return frozen, result

frozen, primary = run('NAO_AVALIADA', 22.5)
assert primary == engine.rank_profile(frozen, config_path=config)
save('entrada_PERFIL_285_nao_avaliada.json', frozen)
save('resultado_PERFIL_285_nao_avaliada.json', primary)
sensitivity = []
for confidence in ['BAIXA','MEDIA','ALTA']:
    for tolerance in [5,22.5,45]:
        inp, res = run(confidence, tolerance)
        name = f'sensibilidade_{confidence}_{str(tolerance).replace(".","p")}'
        save(name+'_entrada.json',inp)
        save(name+'_resultado.json',res)
        sensitivity.append({'confidence_assumed':confidence,'tolerance_deg_assumed':tolerance,
                            'operational_status':res['operational_status'],
                            'operational_effect_applied':res['operational_effect_applied'],
                            'primary_top3':[{k:r[k] for k in ['sector_id','profile_score','effective_lambda','profile_rank']}
                                            for r in sorted(res['primary_rows'],key=lambda x:x['profile_rank'])[:3]],
                            'operational_top3':[r['sector_id'] for r in sorted(res['operational_rows'],key=lambda x:x.get('profile_rank',x.get('territorial_rank',999)))[:3]]})
save('sensibilidade_285_resumo.json',sensitivity)
print(json.dumps({'primary_status':primary['operational_status'],'primary_abstained':primary['abstained'],
                  'sensitivity':sensitivity}, ensure_ascii=False),flush=True)

# A reference satellite background, not input for score calculation.
lat,lon = .21833333333333335,-51.13305555555556
earth = 6371008.8
dlat = math.degrees(8000/earth)
dlon = math.degrees(8000/(earth*math.cos(math.radians(lat))))
bbox = [lat-dlat,lon-dlon,lat+dlat,lon+dlon]
params = dict(SERVICE='WMS',VERSION='1.3.0',REQUEST='GetMap',
              LAYERS='esa-worldcover-s2rgbnir-10m-2021-v2_tcc',STYLES='',CRS='EPSG:4326',
              BBOX=','.join(map(str,bbox)),WIDTH=2048,HEIGHT=2048,FORMAT='image/png',
              TRANSPARENT='FALSE',TIME='2021-01-01')
url = 'https://titiler.terrascope.be/wms?'+urllib.parse.urlencode(params)
sat = OUT/'fundo_satelite_2021.png'
background = {'url':url,'bbox_latlon':bbox,'year':2021,'used_in_ranking':False,'status':'UNAVAILABLE'}
try:
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Academic-cartography/1.0'}),timeout=45) as response:
        data=response.read()
    import io
    check=Image.open(io.BytesIO(data))
    check.load()
    assert check.format=='PNG' and check.size==(2048,2048)
    sat.write_bytes(data)
    background.update(status='AVAILABLE',sha256=sha(sat),size=list(check.size))
except Exception as exc:
    background['error']=str(exc)
save('proveniencia_fundo.json',background)

W,H=2380,2110
canvas=Image.new('RGBA',(W,H),'white')
d=ImageDraw.Draw(canvas)
fontdir=Path('/System/Library/Fonts/Supplemental')
def font(n,bold=False): return ImageFont.truetype(str(fontdir/('Arial Bold.ttf' if bold else 'Arial.ttf')),n)
def text(x,y,s,n=28,fill='#22323b',bold=False):
    d.text((x,y),s,font=font(n,bold),fill=fill)
def wrap(s,width,n):
    words=s.split(); lines=[]; line=''
    for word in words:
        nxt=(line+' '+word).strip()
        if d.textlength(nxt,font=font(n))>width and line: lines.append(line);line=word
        else:line=nxt
    if line:lines.append(line)
    return lines
def para(x,y,s,width=560,n=28,gap=9,fill='#22323b',bold=False):
    for line in wrap(s,width,n):
        text(x,y,line,n,fill,bold);y+=n+gap
    return y
text(50,36,'MATA-03 | KM21 — priorização territorial',52,bold=True)
text(50,105,'Ensaio controlado em território real • raio informado: 7 km • direção relatada: 285° (ONO)',29)
left,top,size=50,165,1650
if background['status']=='AVAILABLE':
    img=Image.open(sat).convert('RGBA').resize((size,size),Image.Resampling.LANCZOS)
else:
    img=Image.new('RGBA',(size,size),'#e5ece8')
canvas.alpha_composite(img,(left,top))
def xy(p):
    x=left+(p[0]-bbox[1])/(bbox[3]-bbox[1])*size
    y=top+(bbox[2]-p[1])/(bbox[2]-bbox[0])*size
    return (round(x),round(y))
overlay=Image.new('RGBA',canvas.size,(0,0,0,0)); od=ImageDraw.Draw(overlay)
colors=['#EFB541','#55B8EE','#F17868']
for i,r in enumerate(ranking[:3]):
    poly=[xy(p) for p in polygons[r['sector_id']]]
    rgb=tuple(int(colors[i][j:j+2],16) for j in (1,3,5))
    od.polygon(poly,fill=rgb+(75,))
canvas=Image.alpha_composite(canvas,overlay);d=ImageDraw.Draw(canvas)
for r in ranking:
    points=[xy(p) for p in polygons[r['sector_id']]]
    d.line(points,fill='white',width=4)
    d.line(points,fill='#324650',width=2)
for i,r in enumerate(ranking[:3]):
    points=[xy(p) for p in polygons[r['sector_id']]]
    d.line(points,fill='white',width=12)
    d.line(points,fill=colors[i],width=7)
center=xy((lon,lat))
angle=math.radians(285)
end=(center[0]+math.sin(angle)*size*6500/16000,center[1]-math.cos(angle)*size*6500/16000)
dx,dy=end[0]-center[0],end[1]-center[1];length=math.hypot(dx,dy)
for start in range(0,int(length),40):
    a=(center[0]+dx*start/length,center[1]+dy*start/length)
    stop=min(start+26,length)
    b=(center[0]+dx*stop/length,center[1]+dy*stop/length)
    d.line([a,b],fill='white',width=13);d.line([a,b],fill='#B074E3',width=7)
ux,uy=dx/length,dy/length
arrow=[end,(end[0]-ux*35-uy*19,end[1]-uy*35+ux*19),(end[0]-ux*35+uy*19,end[1]-uy*35-ux*19)]
d.polygon(arrow,fill='#B074E3',outline='white',width=3)
def label(x,y,s,color='#ffffff'):
    f=font(29,True);box=d.textbbox((0,0),s,font=f);tw=box[2]
    d.rounded_rectangle((x-10,y-7,x+tw+12,y+38),radius=5,fill=color,outline='#29343c',width=2)
    d.text((x,y),s,font=f,fill='#17252e')
label(end[0]-50,end[1]-64,'285° ONO','#eadcf6')
for i,r in enumerate(ranking[:3]):
    x,y=xy((r['representative_lon'],r['representative_lat']))
    label(x-22,y-20,f'AP{i+1}',colors[i])
d.ellipse((center[0]-10,center[1]-10,center[0]+10,center[1]+10),fill='white',outline='#9C1E26',width=4)
label(center[0]+17,center[1]-48,'E0')
# North marker and scale are explicitly for overview only.
nx,ny=left+size-80,top+70
d.line((nx,ny+80,nx,ny+5),fill='white',width=9)
d.polygon([(nx,ny),(nx-16,ny+29),(nx+16,ny+29)],fill='white')
text(nx-13,ny-45,'N',34,'white',True)
sx,sy=left+35,top+size-50; sl=size*2000/16000
d.rectangle((sx-12,sy-49,sx+sl+20,sy+15),fill='white')
d.line((sx,sy,sx+sl,sy),fill='#20313b',width=7)
d.line((sx,sy-10,sx,sy+9),fill='#20313b',width=4)
d.line((sx+sl,sy-10,sx+sl,sy+9),fill='#20313b',width=4)
text(sx,sy-43,'0                         2 km',24)
d.rectangle((left,top,left+size,top+size),outline='#29343c',width=3)

x,y=1745,170
y=para(x,y,'STATUS: REVISAR',n=38,bold=True,fill='#A36116')+22
y=para(x,y,'Ordem territorial BASE',n=31,bold=True)+12
for i,r in enumerate(ranking[:3]):
    d.rectangle((x,y+4,x+22,y+27),fill=colors[i])
    y=para(x+37,y,f'AP{i+1}  {short(r["sector_id"])}  |  {r["score_base"]:.6f}',width=520,n=31,bold=True)+10
y+=16
y=para(x,y,'Margem 1º–2º: 0,001181\n'.strip(),n=28)+5
y=para(x,y,'Liderança em 3 de 5 conjuntos de pesos. Pequenas diferenças não sustentam uma ordem forte.',n=28)+24
y=para(x,y,'Direção informada',n=31,bold=True)+10
y=para(x,y,'A seta indica o relato de 285° a partir do norte. Não representa rota confirmada, cone de probabilidade ou limite de busca.',n=28)+16
y=para(x,y,'Confiança e tolerância angular não informadas. No resultado principal, a pista é registrada, mas não altera os escores.',n=28)+23
y=para(x,y,'Como interpretar',n=31,bold=True)+10
y=para(x,y,'AP1–AP3 são os três maiores escores territoriais. Não são localizações previstas da pessoa nem setores liberados para atuação automática.',n=28)+16
y=para(x,y,'Cada setor tem cerca de 6,4 km². São unidades analíticas; o comando deve subdividi-las e conferir os acessos e obstáculos em campo.',n=28)+22
y=para(x,y,'Limites do mapa',n=31,bold=True)+10
y=para(x,y,'Fundo de satélite de 2021; registros de campo de 2026. O dossel não revela a dificuldade de passagem no interior da mata.',n=27)+14
y=para(x,y,'Mapa de visão geral. Não validado para navegação ou planejamento automático de voo.',n=27,bold=True)
footer=1842
text(50,footer,'E0: 0°13′06″ N, 51°07′59″ O  |  Área circular ideal: 153,94 km²  |  24 setores analíticos',27)
text(50,footer+43,'Dados pessoais e cronologia simulados; fotografias e referência territorial reais. Posição do alvo não utilizada.',27)
text(50,footer+86,'© ESA WorldCover project 2021 • Contains modified Copernicus Sentinel data (2021), processed by ESA WorldCover consortium.',23)
text(50,footer+124,'Base cartográfica: composição Sentinel-2 de 2021 via Terrascope. Escores: execução BASE preservada; não são probabilidades.',24)
if background['status']!='AVAILABLE':
    text(70,top+35,'FUNDO DE SATÉLITE INDISPONÍVEL — esquema espacial',32,'#8B2F20',True)
canvas.convert('RGB').save(OUT/'mapa_MATA03_285_ONO.png')

errata = [
    'O campo top3 vazio de resultado_BASE.json decorre da serialização. O Top-3 desta conclusão é lido diretamente de ranking_BASE.json.',
    'A descrição antiga de nove amostras por setor não representa esta execução: foram 3.600 amostras estratificadas por setor, não estatística zonal de todos os pixels.',
    'A área nominal de amostragem em config_execucao.json conserva valores de raio 6 km. Para 7 km, a área ideal por amostra é 1.781,690278 m² e a escala linear nominal 42,210073 m. Essa informação descritiva não participa da soma ponderada conferida.',
    'manifesto_BASE.json precede resultado_BASE.json. Este fechamento registra os hashes de todos os 15 arquivos BASE sem reescrevê-los.'
]
save('errata_documental_sem_alteracao_BASE.json',errata)
summary = {'case':'MATA-03','created_at':now,'base_status':'REVISAR',
           'top3':[{'sector':short(r['sector_id']),'score':r['score_base']} for r in ranking[:3]],
           'margin':ranking[0]['score_base']-ranking[1]['score_base'],
           'direction':{'azimuth_deg':285,'label':'ONO','nature':'RELATADO','confidence':'NAO_AVALIADA',
                        'tolerance_informed_deg':None,'north_reference':'NAO_INFORMADO',
                        'assumed_schema_tolerance_deg':22.5,'assumption_does_not_activate_main_score':True},
           'profile_status':primary['operational_status'],
           'sensitivity_is_assumption_analysis_not_new_cases':True,
           'target_used':False,'mata02_target_used':False,'dissertation_changed':False,
           'satellite_status':background['status'],'errata':errata}
save('resumo_conclusao.json',summary)
lines=[
    'MATA-03 / KM21 — conclusão da execução com direção relatada de 285° (ONO)',
    '', '1. Resultado principal',
    'Estado territorial: REVISAR. O escore é um índice multicritério territorial, não uma probabilidade de presença.',
    *[f'{i+1}. {short(r["sector_id"])}: {r["score_base"]:.9f}' for i,r in enumerate(ranking[:3])],
    'Margem entre os dois primeiros: 0,001180969. O primeiro colocado vence em 3 dos 5 conjuntos de pesos (estabilidade 0,60).',
    'Os motivos de revisão são UPSTREAM_REVIEW_REQUIRED, LOW_MARGIN e RANKING_UNSTABLE.',
    '', '2. Tratamento da direção',
    'A informação recebida é 285° (ONO) a partir do norte, de natureza RELATADO. Não foram informadas confiança, tolerância angular ou referência norte verdadeiro/magnético.',
    'Os 223° da captura de bússola são orientação do telefone e não foram tratados como direção de deslocamento.',
    f'O motor PERFIL V3 retornou {primary["operational_status"]}; abstenção do perfil: {primary["abstained"]}.',
    'NAO_AVALIADA recebe qualidade zero pela regra vigente: a direção fica visível e registrada, mas não altera o ranking principal. Isso não contradiz o relato e não demonstra que ONO seja uma direção errada.',
    'A tolerância de 22,5° no arquivo principal é apenas requisito do esquema do motor; é uma premissa de engenharia não confirmada e não tem efeito com qualidade zero.',
    'Foram executadas nove combinações auxiliares de confiança BAIXA/MEDIA/ALTA e tolerância ±5°/±22,5°/±45°. São análises condicionais de sensibilidade, não novos casos nem calibração.',
]
for r in sensitivity:
    lines.append(f'  {r["confidence_assumed"]}, ±{r["tolerance_deg_assumed"]}°: '+
                 ', '.join(short(t['sector_id']) for t in r['primary_top3'])+
                 f'; estado PERFIL {r["operational_status"]}; efeito aplicado: {r["operational_effect_applied"]}.')
lines += [
    '', '3. Por que esses escores aparecem',
    'O BASE pondera acesso (0,30), hidrografia (0,25), relevo (0,20) e cobertura (0,25). As três primeiras áreas combinam valores elevados do componente hidrográfico e relevo com valores intermediários de acesso e cobertura.',
    'R01-E: componentes GEO-02 a GEO-05 = 0,554997901; 0,945008047; 0,787706577; 0,707611111. A decomposição é 0,166499370 + 0,236252012 + 0,157541315 + 0,176902778 ≈ 0,737195475.',
    'Essa decomposição explica a aritmética, não valida a plausibilidade de presença. O ranking não incorporou automaticamente personalidade, tempo de caminhada, detecção de pessoa em imagens, cercas ou condições do sub-bosque.',
    '', '4. Procedência e limites',
    'Raio informado: 7 km; área circular ideal: 153,938040 km²; área poligonal: 153,889199 km². Cada uma das 24 unidades analíticas tem aproximadamente 6,4 km².',
    'E0: 0,2183333333; -51,1330555556. A referência espacial de chegada não é uma confirmação da posição às 12h00.',
    'Cronologia simulada: 19h30 desde o último contato; 22h30 desde o início do deslocamento; 23h02 desde a referência de chegada. Esses intervalos não significam caminhada contínua.',
    'Ambiente: cerrado amazônico, fragmentos florestais e ocupação semi-rural. Não representa floresta contínua.',
    'Amostragem territorial: 3.600 pontos estratificados por setor, 86.400 válidos; não se afirma que todos os pixels foram amostrados.',
    'As fotografias são contexto visual de campo, não ortomosaico ou detector automático de vítimas. Os arquivos HEIC não receberam inspeção visual/extração completa de EXIF neste fechamento.',
    'O inventário distingue os 12 arquivos explicitamente relacionados pelo usuário dos arquivos adicionais encontrados na pasta. A descrição de 16 imagens de referência não equivale a 16 imagens contextuais verificadas.',
    'A imagem identificada como SoloVit foi mantida fora do processamento. Não foram lidos seus conteúdos nem seus metadados neste fechamento. Não foi utilizada a localização revelada do MATA-02.',
    'O fundo Sentinel-2 é de 2021 e serve apenas à leitura do mapa. Não é imagem Google Earth nem levantamento contemporâneo de 2026. Fonte e URL constam em proveniencia_fundo.json.',
    'MOV, URG e DET não foram executados para este fechamento. Não houve validação de eficácia operacional, navegação móvel, GeoPDF ou missão de drone.',
    '', '5. Erratas documentais preservando a versão BASE', *errata,
    '', '6. Preservação',
    'Os 15 arquivos BASE, os ensaios anteriores e a dissertação permanecem inalterados. Os hashes antes/depois estão no manifesto deste fechamento.',
    'Este pacote documenta uma execução do modelo e suas limitações; não é uma ordem de busca. A decisão permanece com o profissional responsável.'
]
(OUT/'nota_execucao.txt').write_text('\n'.join(lines)+'\n')
after={p.name:sha(p) for p in BASE.iterdir() if p.is_file()}
assert before==after, 'BASE changed unexpectedly'
manifest={'created_at':now,'base_unchanged':True,'base_files_sha256':before,
          'files_sha256':{p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='manifesto_conclusao.json'},
          'profile_engine_sha256':sha(ROOT/'work/perfil_vitima_v3/profile_ranker.py'),
          'profile_config_sha256':sha(config),'target_accessed':False}
save('manifesto_conclusao.json',manifest)
print(json.dumps({'done':True,'output':str(OUT),'base_unchanged':True,'satellite':background['status']}),flush=True)
