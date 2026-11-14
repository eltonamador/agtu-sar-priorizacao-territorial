"""Ensaio territorial complementar; pista 249° segregada do BASE."""
from pathlib import Path
import copy, hashlib, importlib.util, json, math

ROOT=Path(__file__).resolve().parents[1]
ENTRY=ROOT/'outputs/campo_mata02_mzg2/entrada_auditada_v2'
OUT=ROOT/'outputs/campo_mata02_mzg2/ensaio_complementar_v2_249'
GEO=ROOT/'outputs/sprint2_s2_06_geo05_v33'
OUT.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def write(n,v):(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
wp=ROOT/'work/mata02_mzg2_processamento_cego_v1/run_mata02_mzg2_blind.py'
sp=importlib.util.spec_from_file_location('legacy_serializers_only',wp)
w=importlib.util.module_from_spec(sp);sp.loader.exec_module(w)
m=w._load_motor()
c=read(ENTRY/'config_entrada_mata02_v2.json')
c['protocol_id']='MATA02-COMPLEMENTAR-BASE-v2.0'
c['status']='CONFIGURACAO_CONGELADA_ANTES_DA_EXTRACAO'
c['scope']['description']='Ensaio complementar territorial de 6000 m; pista 249 graus apenas contextual, sem alteração do BASE.'
c['limitations']=[s.replace('Direção do relato e geometria da trilha não informadas','Azimute 249 graus informado posteriormente; tolerância angular, qualidade e geometria da trilha não informadas') for s in c['limitations']]
write('config_execucao.json',c)
clue={'id':'MATA02-PISTA-249-v1','scenario_id':'MATA-02','source':'Informação do pesquisador nesta conversa','nature':'Pista do cenário hipotético; não observação extraída das fotografias','azimuth_deg':249,'measurement':'A partir do norte, sentido horário por convenção de azimute','north_reference_declared':None,'mapping_convention':'Norte geográfico apenas para representação; confirmar se a informação original era magnética','origin':'E0 adotado como origem do desenho; ponto exato da observação não informado','angular_uncertainty_deg':None,'quality_numeric':None,'witness_location':None,'observation_timestamp':None,'distance_travelled_m':None,'used_in_base_ranking':False,'quantitative_profile_status':'NAO_EXECUTADO_PARAMETROS_INSUFICIENTES','why':'Não atribuir cone de 45 graus, confiança média, peso ou alcance de 6 km à pista. O traço é apenas referência gráfica.'}
write('PISTA_DIRECIONAL_249.json',clue)
f=read(ENTRY/'FICHA_CENARIO_MATA02_v2.json');f['version']='2.1';f['clues'][0]['bearing_deg']=249
f['clues'][0]['description']='Relato de direção 249 graus a partir do norte, informado posteriormente pelo pesquisador'
f['clues'][0]['quantitative_eligible']=False
f['clues'][0]['ineligibility_reason']='Sem tolerância angular, qualidade e confirmação do referencial norte/origem da observação'
f['status']='CONTEXTO_ATUALIZADO_SEPARADO_DO_BASE'
write('FICHA_CENARIO_MATA02_v2_1.json',f)
names=['entrada_raio_fonte_mata02_mzg2.json','entrada_raio_fonte_mata02_mzg2.geojson','manifesto_entrada_raio_fonte_mata02_mzg2.json']
j,g,man=[ENTRY/n for n in names]
rows=m.validate_buffer_contract(read(j),read(g),read(man),j,g,c)
sectors=m.make_sector_records(rows,c)
assert len(sectors)==24
assert all(len(s['sample_points'])==3600 for s in sectors)
lat,lon=rows[0]['estimated_lat'],rows[0]['estimated_lon']
ring=read(g)['features'][0]['geometry']['coordinates'][0]
# Domínio mais halo de consulta de 10 km contidos no retângulo de aquisição OSM.
query=GEO/'geo02_overpass_query.txt';hq=GEO/'geo03_overpass_query.txt'
assert '(-0.25,-51.95,0.45,-50.70)' in query.read_text() and '(-0.25,-51.95,0.45,-50.70)' in hq.read_text()
ext=[m.destination(lat,lon,10000,b) for b in range(360)]
assert all(-.25<a<.45 and -51.95<b<-50.70 for a,b in ext)
roads,rt=m.load_road_segments(GEO/'osm_highways_raw.json',c)
hydro,ht=m.load_hydro_segments(GEO/'osm_hydrography_raw.json',c)
nh=w._domain_segment_count(m,hydro,lat,lon,6000)
nr=w._domain_segment_count(m,roads,lat,lon,6000)
coverage={'osm_query_bbox':[-.25,-51.95,.45,-50.70],'domain_and_10km_radius_within_query':True,'roads_segments_intersecting_domain':nr,'hydro_segments_intersecting_domain':nh,'roads_snapshot':rt,'hydro_snapshot':ht,'dem_tile_required':'S01W052','worldcover_tile_required':'S03W054','caveat':'Extensão da consulta não comprova completude do mapeamento. Fontes históricas não comprovam transitabilidade atual.'}
write('COBERTURA_FONTES.json',coverage)
print(json.dumps(coverage,ensure_ascii=False),flush=True)
hgt=m.HGTSampler(GEO);wc=m.WorldCoverSampler(GEO/'worldcover_tiles')
ci=float(c['feature_extraction']['spatial_index_cell_deg'])
try:
    features=m.extract_sector_features(sectors,rows,c,m.SpatialSegmentIndex(roads,ci),m.SpatialSegmentIndex(hydro,ci),hgt,wc,rt,ht)
finally:wc.close()
sampling=[{'sector_id':r['sector_id'],'terrain_valid':r['terrain_sample_count'],'terrain_expected':r['terrain_expected_sample_count'],'worldcover_valid':r['worldcover_sample_count'],'worldcover_expected':r['worldcover_expected_sample_count']} for r in features]
write('QA_AMOSTRAS.json',sampling)
if nh==0:features=w._apply_hydro_abstention(features)
rank=m.rank_sector_records(features,c)
assert rank==m.rank_sector_records(copy.deepcopy(features),copy.deepcopy(c))
if nh:
    for r in rank:
        expected=.30*r['geo02_score']+.25*r['geo03_score']+.20*r['geo04_score']+.25*r['geo05_score']
        assert abs(expected-r['score_base'])<1e-8
assert all(s['terrain_valid']==s['terrain_expected']==3600 and s['worldcover_valid']==s['worldcover_expected']==3600 for s in sampling)
assert all(r['ground_truth_used'] is False for r in rank)
write('QA_EXECUCAO.json',{'contract':'PASS','sector_count_24':'PASS','raster_valid_samples_each_sector_3600':'PASS','weighted_score_independent_recalculation':'PASS' if nh else 'NAO_APLICAVEL_BASE_ABSTIDO','deterministic_reranking_same_features':'PASS','ground_truth_absent_from_base':'PASS','direction_clue_segregated':'PASS','extraction_independently_repeated':False,'efficacy_validated':False})
decisions=m.summarize_buffer_decisions(rank,c)
m.write_csv(OUT/'atributos_setores.csv',w._clean_feature_rows(features))
m.write_csv(OUT/'ranking_BASE.csv',rank)
write('ranking_BASE_completo.json',rank)
geo=m.build_sector_geojson(sectors,c,{r['sector_id']:r for r in rank})
write('setores_BASE.geojson',geo)
diagnostic=[]
if nh==0:
    diagnostic=w._rank_available_modules(features)
    for r in diagnostic:r['ranking_protocol_id']='MATA02-COMPLEMENTAR-DIAGNOSTICO-v2.0'
    m.write_csv(OUT/'ranking_DIAGNOSTICO_nao_equivalente_BASE.csv',diagnostic)
    write('top3_DIAGNOSTICO.json',w._top3_rows(diagnostic))
# Linha até a borda: convenção de desenho, não distância estimada nem rota.
pts=[]
for d in range(0,6001,100):
    a,b=m.destination(lat,lon,d,249);pts.append([b,a])
write('referencia_249_contextual.geojson',{'type':'FeatureCollection','features':[{'type':'Feature','properties':{'azimuth':249,'north':'true_for_display_only','distance_is_display_extent_not_travel':True,'not_route':True,'not_priority_area':True,'not_used_in_base':True,'origin_assumed_E0':True,'note':'Traço contextual recortado no domínio; não delimita cone nem percurso.'},'geometry':{'type':'LineString','coordinates':pts}}]})
result={'protocol_id':c['protocol_id'],'case':'MATA-02','scope':'Ensaio complementar em território real com ocorrência hipotética','decision':decisions,'hydro_branch':'BASE_COMPLETO' if nh else 'BASE_ABSTIDO_GEO03_SEM_FEICOES','diagnostic_generated':not bool(nh),'direction_249_used_in_base':False,'profile_executed':False,'sector_count':len(sectors),'samples_per_sector':3600,'full_raster_census':False,'ranking_repeat_identical_on_same_features':True,'extraction_repeated':False,'operational_validation':False,'probability_of_presence':False,'reference_target_used':False}
write('RESULTADO_ENSAIO.json',result)
sources=[j,g,man,ENTRY/'config_entrada_mata02_v2.json',wp,w.MOTOR_PATH,Path(__file__),query,hq,GEO/'osm_highways_raw.json',GEO/'osm_hydrography_raw.json',GEO/'S01W052.hgt.gz',GEO/'worldcover_tiles/ESA_WorldCover_10m_2021_v200_S03W054_Map.tif']
write('MANIFESTO_FONTES.json',[{'path':str(p),'sha256':sha(p)} for p in sources])
write('MANIFESTO_SAIDAS.json',[{'file':p.name,'sha256':sha(p)} for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='MANIFESTO_SAIDAS.json'])
print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
