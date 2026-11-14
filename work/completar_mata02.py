"""Complementos MATA-02; não altera BASE, dissertação ou casos anteriores."""
from pathlib import Path
import importlib.util, sys, json, math, csv, hashlib
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/campo_mata02_mzg2'
BASE=OUT/'ensaio_complementar_v2_249'
GEO=ROOT/'outputs/sprint2_s2_06_geo05_v33'
def load(name,path):
    s=importlib.util.spec_from_file_location(name,ROOT/path); m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
features=read(BASE/'setores_BASE.geojson')['features']
def movement():
    out=OUT/'movimento_complementar_v1';out.mkdir(exist_ok=True)
    m=load('mata_mov','work/mata01_mov_v1/motor_movimento_mata01_v1.py');core=m.load_core();v=m.load_v1()
    config=read(ROOT/'work/mata01_mov_v1/config_mata01_mov_v1.json')
    config['protocol_id']='MATA02-MOV-COMPLEMENTAR-v1'
    config['engine_version']='adaptador_MATA02_v1_primitivas_MOV_existentes'
    config['source']={'scenario_id':'MATA-02','candidate_id':'MATA-02-E0','point':{'latitude':-0.15916666666666668,'longitude':-51.395,'input_crs':'EPSG:4326'},'radius_m':6000.,'radius_semantics':'DOMINIO_EXPLORATORIO_NAO_DISTANCIA_PERCORRIDA','ground_truth_available_to_engine':False}
    config['grid']['domain_radius_m']=6000.
    config['temporal_snapshots']=[{'id':'T17_SIMULADO','as_of_local':'2026-10-23T08:30:00-03:00','elapsed_seconds':61200,'changes_cost_surface':False}]
    config['behavioral_clues']={'azimuth_reported_deg':249,'numeric_effect_in_mov_v':False,'reason':'DIRECAO_NAO_ALTERA_RESISTENCIA_FISICA; TRATADA_NO_PERFIL'}
    config['time_policy'].pop('T26_and_T49_share_same_cost_surface')
    config['known_limitations']=['Cenário hipotético em território real; não validado operacionalmente.','Fatores de resistência herdados são heurísticos, não calibrados.','Tempo de 17 h não é tempo de marcha e não define isócrona.','OSM/WorldCover/SRTM não demonstram transitabilidade atual.','Hidrografia OSM contextual, sem fator adicional para evitar duplicação.','Obstáculos de campo sem geometria não recebem penalização inventada.']
    config['sectorization']['rule']='MESMAS_GEOMETRIAS_BASE; HOMOTETIA_AREA_IGUAL'
    write(out/'config_movimento.json',config)
    print('MOV: amostrando grade de 30 m',flush=True)
    cells,half=core.make_grid(v,config);core.sample_rasters(v,cells,config,GEO,GEO/'worldcover_tiles')
    # Testar primeiro setor polar provável, depois demais. Excluir centros fora
    # do polígono discretizado BASE em vez de ampliar o domínio silenciosamente.
    ordered=sorted(features,key=lambda f:f['properties']['sector_index'])
    polys=[[v.aeqd_forward(lat,lon,-0.15916666666666668,-51.395) for lon,lat in f['geometry']['coordinates'][0]] for f in ordered]
    excluded=[]
    for key,c in cells.items():
        i=v._sector_index_for_xy(c.x_m,c.y_m,6000.)
        candidates=[i]+[j for j in range(24) if j!=i]
        found=next((j for j in candidates if v._point_in_polygon_or_boundary((c.x_m,c.y_m),polys[j])),None)
        if found is None:excluded.append(key)
        else:c.sector_id=ordered[found]['properties']['sector_id']
    for key in excluded:del cells[key]
    roads,_=v.load_road_segments(GEO/'osm_highways_raw.json')
    near=[s for s in roads if m.segment_near_domain(s,v,-0.15916666666666668,-51.395,6000,22)]
    core.rasterize_segments(v,cells,half,near,config,'network')
    scenarios=core.cost_scenarios(config)
    for s in scenarios:
        print('MOV:',s['scenario_id'],flush=True);core.dijkstra_cost_surface(cells,(half,half),config,s)
    before=m.cost_digest(cells,'H_REDE_DISPONIVEL__BASE')
    core.dijkstra_cost_surface(cells,(half,half),config,next(s for s in scenarios if s['scenario_id']=='H_REDE_DISPONIVEL__BASE'))
    assert before==m.cost_digest(cells,'H_REDE_DISPONIVEL__BASE')
    assert all(c.elevation_m is not None and c.worldcover_code is not None for c in cells.values())
    assert all(math.isfinite(c.costs[s['scenario_id']]) for c in cells.values() for s in scenarios)
    def targets(cs,cfg):
        result=[]
        for f in ordered:
            p=f['properties'];key=core.nearest_cell(cs,p['representative_lat'],p['representative_lon'],v,cfg)
            assert cs[key].sector_id==p['sector_id']
            result.append({'sector_id':p['sector_id'],'target_radius_m':cs[key].radial_distance_m,'cell_key':key})
        return result
    m.representative_targets=targets
    corridors=m.build_corridors(core,cells,config);corridors['name']='MATA02_CORREDORES_DIAGNOSTICOS'
    assert len(corridors['features'])==48
    write(out/'corredores.geojson',corridors)
    m.write_csv(out/'grade_movimento.csv',m.grid_rows(cells))
    m.write_csv(out/'resumo_setores.csv',m.summarize_sectors(cells))
    m.write_csv(out/'custos_seis_cenarios.csv',[{'row':c.row,'col':c.col,**c.costs} for c in cells.values()])
    write(out/'QA.json',{'status':'PASS','checks':['cobertura_raster','custos_finitos_seis_cenarios','repeticao_deterministica_BASE','48_corredores','destinos_nos_setores_BASE'],'cells':len(cells),'excluded_centers_outside_BASE_polygon':len(excluded),'network_cells':sum(c.road or c.trail for c in cells.values()),'operational_validation':False,'original_MATA01_test_receipt_reused':False})
    write(out/'manifesto.json',{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),m.CORE_PATH,m.V1_ENGINE_PATH,BASE/'setores_BASE.geojson',GEO/'osm_highways_raw.json',GEO/'S01W052.hgt.gz',GEO/'worldcover_tiles/ESA_WorldCover_10m_2021_v200_S03W054_Map.tif',*out.glob('*')] if p.is_file() and p.name!='manifesto.json'})
    print('MOV concluído',flush=True)
def profile():
    out=OUT/'perfil_249_sensibilidade_v1';out.mkdir(exist_ok=True)
    r=load('mata02_profile','work/perfil_vitima_v3/profile_ranker.py')
    now=datetime.now(timezone.utc).isoformat()
    assumptions={'reported_azimuth_deg':249,'reported_confidence':None,'reported_tolerance_deg':None,'north_reference_reported':None,'assumed_for_cartography':'NORTE_GEOGRAFICO; ORIGEM_E0','execution':'SENSIBILIDADE_EXPLORATORIA_NAO_EVIDENCIA_NOVA','tolerance_tests_deg':[5,22.5,45],'confidence_tests':['BAIXA','MEDIA','ALTA'],'no_primary_scenario_selected':True,'original_BASE_status':'REVISAR','warning':'Resultados internos do ranker não constituem liberação operacional; parâmetros faltantes não foram confirmados.'}
    write(out/'premissas.json',assumptions)
    sectors=[{'sector_id':f['properties']['sector_id'],'territorial_score':f['properties']['score_base'],'bearing_start_deg':f['properties']['azimuth_start_deg'],'bearing_end_deg':f['properties']['azimuth_end_deg'],'polygon':f['geometry']['coordinates'][0]} for f in features]
    summary=[]
    for conf in ['NAO_AVALIADA','BAIXA','MEDIA','ALTA']:
        for tol in ([22.5] if conf=='NAO_AVALIADA' else [5,22.5,45]):
            stem=f'{conf}_{tol:g}'
            payload={'protocol_version':'PERFIL-V3-QUANT-v1.0','scenario_id':'MATA-02','candidate_id':'MATA-02-E0','record_status':'RASCUNHO','created_at':now,'ground_truth_absent':True,'source_loc_input_sha256':sha(BASE/'FICHA_CENARIO_MATA02_v2_1.json'),'source_case_revision':3,'source_profile_compiled_sha256':sha(out/'premissas.json'),'source_territorial_manifest_sha256':sha(BASE/'MANIFESTO_SAIDAS.json'),'source_spatial_review_sha256':sha(out/'premissas.json'),'sectors':sectors,'hypotheses':[{'hypothesis_id':'MATA02-DIR249','evidence_group_id':'RELATO249','family':'DIRECAO','hypothesis_type':'DIRECAO_OBSERVADA','spatialized':True,'authorized_for_model':True,'nature':'RELATADO','confidence':conf,'direction':{'origin_candidate_id':'MATA-02-E0','azimuth_deg':249,'tolerance_deg':tol}}]}
            frozen=r.prepare_frozen_input(payload,now);result=r.rank_profile(frozen)
            write(out/f'entrada_{stem}.json',frozen);write(out/f'resultado_{stem}.json',result)
            assert r.canonical_sha256(r.rank_profile(frozen))==r.canonical_sha256(result)
            summary.append({'confidence_assumption':conf,'tolerance_assumption_deg':tol,'top3_primary_lambda':result['primary_rows'][:3],'engine_status':result['operational_status'],'abstained':result['abstained'],'external_status':'EXPLORATORIO_REVISAR_NAO_OPERACIONAL'})
    write(out/'comparacao.json',summary)
    write(out/'QA.json',{'status':'PASS','executions':len(summary),'repeat_deterministic':True,'freeze_and_input_validation':'ranker original','operational_validation':False,'confirmed_confidence_or_tolerance':False})
    write(out/'manifesto.json',{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'work/perfil_vitima_v3/profile_ranker.py',ROOT/'outputs/modulo_perfil_vitima_v3/config_perfil_quantitativo_v3.json',*out.glob('*')] if p.is_file() and p.name!='manifesto.json'})
    print('PERFIL concluído',flush=True)
if __name__=='__main__':
    if sys.argv[-1]=='perfil':profile()
    else:movement()
