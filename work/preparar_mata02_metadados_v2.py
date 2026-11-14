"""Auditoria local e preparação de entrada; não executa ranking nem consulta rede."""
from pathlib import Path
import csv, hashlib, importlib.util, json, math, re, sys
from datetime import datetime
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = Path('/Users/elton.amador/Library/CloudStorage/GoogleDrive-elton.amador@gmail.com/Meu Drive/Mestrado - IA Tecnologia e Diversos/Mestrado/Dissertação/Projeto/fotos/MZG2')
OUT = ROOT / 'outputs/campo_mata02_mzg2/entrada_auditada_v2'
OUT.mkdir(parents=True, exist_ok=True)
LAT, LON = -(9/60+33/3600), -(51+23/60+42/3600)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def norm(v):
    if isinstance(v, bytes): return v.decode('utf-8', errors='replace').strip('\0')
    if isinstance(v, (tuple,list)): return [norm(x) for x in v]
    if isinstance(v, dict): return {str(k):norm(x) for k,x in v.items()}
    if isinstance(v,(str,int,float,bool)) or v is None: return v
    return float(v)
def coord(g, key, ref):
    if key not in g: return None
    a,b,c = map(float,g[key]); return (a+b/60+c/3600)*(-1 if g.get(ref) in ('S','W') else 1)
def distance(lat,lon):
    if lat is None or lon is None: return None
    a,b=map(math.radians,(LAT,lat)); dl=math.radians(lon-LON)
    h=math.sin((b-a)/2)**2+math.cos(a)*math.cos(b)*math.sin(dl/2)**2
    return 6371008.8*2*math.asin(math.sqrt(h))

files=sorted((SRC/'Drone').glob('*.JPG'))+[SRC/n for n in ('MZG2Solo_0403.jpeg','MZG2Solo_0407.jpeg','MZG2Solo_0428.jpeg','MZG2.png')]
rows=[]
allowed={'ImageSource','GpsStatus','AltitudeType','GpsLatitude','GpsLongitude','AbsoluteAltitude','RelativeAltitude','GimbalRollDegree','GimbalYawDegree','GimbalPitchDegree','FlightYawDegree','DroneModel'}
for p in files:
    data=p.read_bytes()
    with Image.open(p) as im:
        ex=im.getexif(); sub=ex.get_ifd(34665); gps=ex.get_ifd(34853)
        xmp={k.decode():v.decode() for k,v in re.findall(rb'drone-dji:([A-Za-z]+)="([^"<>]*)"',data) if k.decode() in allowed}
        la,lo=coord(gps,2,1),coord(gps,4,3)
        row={'name':p.name,'path':str(p),'category':'DRONE' if p.parent.name=='Drone' else 'SCREEN' if p.suffix=='.png' else 'GROUND',
             'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'width':im.width,'height':im.height,
             'make':ex.get(271),'model':ex.get(272),'datetime_original':sub.get(36867),'datetime_digitized':sub.get(36868),
             'offset_time_original':sub.get(36881),'datetime_ifd0':ex.get(306),'latitude_exif':la,'longitude_exif':lo,
             'gps_datum':norm(gps.get(18)),'gps_date':gps.get(29),'gps_time':norm(gps.get(7)),
             'altitude_exif_m':float(gps[6])*(-1 if gps.get(5)==b'\x01' else 1) if 6 in gps else None,
             'horizontal_error_exif_m':norm(gps.get(31)),'camera_to_E0_horizontal_m':distance(la,lo),'xmp_dji_selected':xmp}
        im.verify()
    row['image_container_verification']='PASS'
    rows.append(row)
drone=[r for r in rows if r['category']=='DRONE']
ref=next(r for r in rows if '155038_0060' in r['name'])
screen=next(r for r in rows if r['category']=='SCREEN')
old=json.loads((ROOT/'work/mata02_mzg2_entrada_cega_v1/INVENTARIO_IMAGENS_ANEXADAS_MATA02_v1.json').read_text())
old_hashes={r['name']:r['sha256'] for r in old['files']}
for r in rows:
    r['prior_inventory_hash_matches']=r['sha256']==old_hashes[r['name']] if r['name'] in old_hashes else None
write('INVENTARIO_METADADOS.json',{'scope':'71 arquivos da pasta Drone e 4 anexos terrestres/tela; não inclui os demais arquivos Solo','method':'Pillow EXIF e verificação de contêiner; extração textual seletiva XMP DJI; SHA256; haversine R=6371008.8 m','clock_caveat':'Horários do aparelho sem fuso não recebem UTC inferido. Não representam o horário da ocorrência hipotética.','privacy':'Sem números de série nem coordenadas de laser; inventário contextual segregado do motor.','files':rows})
cols=['name','category','sha256','width','height','model','datetime_original','offset_time_original','latitude_exif','longitude_exif','altitude_exif_m','camera_to_E0_horizontal_m','image_container_verification','prior_inventory_hash_matches']
with (OUT/'INVENTARIO_METADADOS.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)

# Reutiliza somente o serializador de entrada, nunca main()/ranking do invólucro antigo.
wp=ROOT/'work/mata02_mzg2_processamento_cego_v1/run_mata02_mzg2_blind.py'
spec=importlib.util.spec_from_file_location('mata02_input_serializer',wp)
wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
motor=wrapper._load_motor()
overlay=json.loads((wp.parent/'config_mata02_mzg2_blind_v1.json').read_text())
overlay['version']='2.0'
overlay['protocol_id']='MATA02-MZG2-INPUT-AUDIT-v2.0'
overlay['status']='ENTRADA_PREPARADA_SEM_EXECUCAO'
up=overlay['upstream'];up['protocol_id']='MATA02-MZG2-SOURCE-RADIUS-v2.0'
up['estimated_lat']=LAT;up['estimated_lon']=LON
up['source_record_origin']='CENARIO_FORNECIDO_PELO_USUARIO_E_CAPTURA_MZG2_PNG; AUDITORIA_V2'
up['coordinate_capture_timestamp_local']=datetime.strptime(screen['datetime_original'],'%Y:%m:%d %H:%M:%S').isoformat()
up['source_metadata_verification']='COORDENADA_LIDA_NA_TELA; EXIF_CAPTURA_2026_10_22_15_59_53_SEM_FUSO; SEM_GPS_EXIF_NA_TELA; ACURACIA_DESCONHECIDA'
up['review_status']='REVISAR'
config=wrapper.build_effective_config(motor,overlay)
config['scope']['description']='Entrada do ensaio complementar MATA-02: domínio informado de 6000 m; sem ranking executado.'
config['limitations']=[x for x in config['limitations'] if 'pista ao Norte' not in x]
config['limitations'].append('Direção do relato e geometria da trilha não informadas; 357 graus é orientação do aparelho, não da pessoa. Perfil e imagens não alimentam BASE.')
config['engine_version']='EXT-ESP-SET-v1.1; configuracao_de_entrada_auditada_v2'
write('config_entrada_mata02_v2.json',config)
write('overlay_entrada_mata02_v2.json',overlay)
j,g,m=wrapper.build_source_radius_inputs(motor,OUT,config,overlay)
validated=motor.validate_buffer_contract(json.loads(j.read_text()),json.loads(g.read_text()),json.loads(m.read_text()),j,g,config)

scenario={
 'scenario_id':'MATA-02','version':'2.0','nature':'Cenário hipotético em território real; ensaio complementar, não ocorrência real nem validação de eficácia',
 'planning_reference':{'latitude':LAT,'longitude':LON,'crs':'EPSG:4326 adotado no contrato; datum não exibido na tela','source':'MZG2.png, bússola iPhone','last_known_person_position':False,'horizontal_accuracy_m':None,'capture_datetime_exif':'2026:10:22 15:59:53','capture_timezone_offset_exif':None,'display_time':'15:59','display_elevation_m':12,'display_heading_deg':357,'heading_is_person_clue':False},
 'domain':{'radius_m':6000,'area_km2':math.pi*36,'radius_origin':'Hipótese exploratória informada pelo pesquisador; não estimativa validada de deslocamento'},
 'hypothetical_clock':{'last_contact':'2026-10-22T15:30:00-03:00','planning':'2026-10-23T08:30:00-03:00','timezone_basis':'America/Belem, convenção local do exercício','elapsed_hours':17,'real_event_timestamp':None},
 'hypothetical_profile':{'sex':'masculino','age':47,'occupation':'extrativista e pequeno agricultor','experience_years':25,'familiarity':'caminhos conhecidos; conhecimento desigual da área','mobility':'a pé, condicionamento habitual de trabalho rural; mata/encharcamento podem limitar deslocamento; possível pausa noturna','health_diagnosis':None,'clothing':None,'speed_kmh':None,'night_rest_hours':None},
 'hypothetical_circumstances':'Saiu para verificar área de coleta próxima a fragmento florestal; teria utilizado trilhas secundárias e vegetação densa; retorno previsto para o fim da tarde não ocorreu.',
 'clues':[{'description':'Relato de colega sobre direção inicialmente tomada','bearing_deg':None,'angular_uncertainty_deg':None,'quality_numeric':None,'quantitative_eligible':False}, {'description':'Indicação de trilha secundária até área de coleta','geometry':None,'quantitative_eligible':False}, {'description':'Possibilidade de marcas em vegetação/solo','confirmed':False,'geometry':None,'quantitative_eligible':False}, {'description':'Caminhos rurais possivelmente utilizados para retorno','person_use_confirmed':False,'quantitative_eligible':False}],
 'visual_observations':'Fotos terrestres: vegetação, passagem estreita, transição para área aberta e tábuas. Foto aérea 0060: via, floresta, áreas abertas e superfícies claras possivelmente úmidas. Sem inferência de pista da pessoa ou traçado métrico.',
 'environment_unconfirmed':['hidrografia local validada','transitabilidade atual','altimetria local validada','geometria das trilhas'],
 'cellular_location':None,'target_reference':None,
 'base_excluded':['fotografias','coordenadas de câmera','perfil','pistas','relógio hipotético','elevação da tela','orientação 357 graus'],
 'prior_record_corrections':['Saúde e vestuário não fornecidos no cenário atual; não herdados da v1.','Nenhuma pista Norte ou hábito de buscar água foi declarado neste caso.','Não transferir classificações de imagens antigas para novas sem inspeção; imagens permanecem fora do BASE.'],
 'drone_reference':{'file':ref['name'],'capture_exif':ref['datetime_original'],'timezone_offset_exif':ref['offset_time_original'],'camera_latitude':ref['latitude_exif'],'camera_longitude':ref['longitude_exif'],'horizontal_distance_to_E0_m':ref['camera_to_E0_horizontal_m'],'role':'Posição da câmera, não ponto no terreno nem vítima'},
 'status':'ENTRADA_PREPARADA; MOTOR_NAO_EXECUTADO'}
write('FICHA_CENARIO_MATA02_v2.json',scenario)
assert (datetime.fromisoformat(scenario['hypothetical_clock']['planning'])-datetime.fromisoformat(scenario['hypothetical_clock']['last_contact'])).total_seconds()/3600==17
assert len(validated)==1 and validated[0]['adaptive_radius_m']==6000
assert all(r['prior_inventory_hash_matches'] is not False for r in rows)
qa={'input_contract':'PASS usando validate_buffer_contract do motor existente','image_container_checks':len(rows),'metadata_extracted':len(rows),'drone_count':len(drone),'drone_with_gps':sum(r['latitude_exif'] is not None for r in drone),'drone_time_min':min(r['datetime_original'] for r in drone),'drone_time_max':max(r['datetime_original'] for r in drone),'duplicates_by_sha256':len(rows)-len({r['sha256'] for r in rows}),'prior_hash_matches':sum(r['prior_inventory_hash_matches'] is True for r in rows),'elapsed_hours_check':'PASS','ranking_executed':False,'geographic_layers_loaded':False,'visual_inspection':'Fotos terrestres e tela fornecidas; fotografia aérea 0060 inspecionada; demais imagens auditadas por metadados/contêiner, não revisão visual integral','readiness':'Entrada aceita pelo contrato; execução depende de verificar cobertura e disponibilidade GEO02-GEO05 e adaptar executor à configuração v2.'}
write('QA_PREPARACAO.json',qa)
write('PROVENIENCIA_CODIGO.json',{'serializer':{'path':str(wp),'sha256':sha(wp)},'motor':{'path':str(wrapper.MOTOR_PATH),'sha256':sha(wrapper.MOTOR_PATH)},'preparation_script':{'path':str(Path(__file__)),'sha256':sha(Path(__file__))},'functions_used':['build_effective_config (descrições herdadas corrigidas apenas na saída v2)','build_source_radius_inputs','validate_buffer_contract'],'not_called':['main','ranking','consultas de camadas ou rede']})
print(json.dumps({'qa':qa,'reference':scenario['drone_reference'],'ground_metadata':[r for r in rows if r['category']!='DRONE']},ensure_ascii=False,indent=2))
