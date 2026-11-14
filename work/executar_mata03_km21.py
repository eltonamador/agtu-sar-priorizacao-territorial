"""MATA-03: ensaio único, sem referência de encontro, preservando os casos anteriores."""
from pathlib import Path
import copy, csv, hashlib, importlib.util, json, math, sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/campo_mata03_km21'
GEO = ROOT / 'outputs/sprint2_s2_06_geo05_v33'
PHOTO = Path('/Users/elton.amador/Library/CloudStorage/GoogleDrive-elton.amador@gmail.com/Meu Drive/Mestrado - IA Tecnologia e Diversos/Mestrado/Dissertação/Projeto/fotos/KM21')
LAT, LON, RADIUS = 13/60+6/3600, -(51+7/60+59/3600), 7000.0
NOW = datetime.now(timezone.utc).isoformat()

def read(p):
    return json.loads(Path(p).read_text())

def write(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str)+'\n')

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def load(name, p):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

def substitute(obj):
    if isinstance(obj, dict): return {k: substitute(v) for k,v in obj.items()}
    if isinstance(obj, list): return [substitute(v) for v in obj]
    if isinstance(obj, str):
        for a,b in [('MATA-02','MATA-03'), ('MATA02','MATA03'), ('mata02','mata03'), ('MZG2','KM21'), ('mzg2','km21'), ('6000','7000')]:
            obj = obj.replace(a,b)
    return obj

def main():
    if (OUT/'resultado_BASE.json').exists():
        raise SystemExit('Resultado já existe: não sobrescrever uma execução concluída.')
    OUT.mkdir(parents=True, exist_ok=True)
    helper = load('legacy_serializers_only', ROOT/'work/mata02_mzg2_processamento_cego_v1/run_mata02_mzg2_blind.py')
    motor = helper._load_motor()
    cfg = substitute(read(ROOT/'outputs/campo_mata02_mzg2/entrada_auditada_v2/config_entrada_mata02_v2.json'))
    protocol = 'MATA03-KM21-SOURCE-RADIUS-v1.0'
    cfg['protocol_id'] = 'MATA03-KM21-INPUT-AUDIT-v1.0'
    cfg['name'] = 'Processamento territorial do cenário controlado MATA-03/KM21'
    cfg['status'] = 'ENTRADA_CONGELADA_PARA_EXECUCAO'
    cfg['dependencies']['upstream_buffer_protocol'] = protocol
    cfg['ground_truth_used'] = False
    write(OUT/'config_execucao.json', cfg)
    motor.validate_firewall_config(cfg)

    premises = {
        'case_id':'MATA-03', 'revision':1, 'frozen_at':NOW,
        'nature':'CENARIO_CONTROLADO_SEMISSINTETICO_EM_TERRITORIO_REAL',
        'coordinates':{'lat':LAT,'lon':LON,'source':'Captura KM21.PNG, bússola do iPhone',
                       'elevation_displayed_m':27,'capture_clock_display':'08:28',
                       'capture_date_source':'Cronologia fornecida pelo pesquisador, não demonstrada pela tela',
                       'role':'Ponto inicial de planejamento; não é posição confirmada do contato das 12h'},
        'chronology':{'arrival':'2026-10-22T08:28:00-03:00','walk_start':'2026-10-22T09:00:00-03:00',
                      'last_contact':'2026-10-22T12:00:00-03:00','expected_return':'2026-10-22T17:30:00-03:00',
                      'search_start':'2026-10-23T07:30:00-03:00',
                      'since_contact_h':19.5,'since_walk_start_h':22.5,'since_E0_h':23+2/60,'overdue_h':14,
                      'continuous_walking_assumed':False},
        'domain':{'radius_m':RADIUS,'ideal_circle_area_km2':math.pi*49,
                  'radius_origin':'INFORMADO_PELO_PESQUISADOR',
                  'meaning':'Domínio operacional de ensaio, não erro de GPS, distribuição de presença ou alcance validado'},
        'direction':{'azimuth_deg':285,'label':'ONO','reference':'A partir do norte, sentido horário',
                     'nature':'RELATADO','confidence':'NAO_AVALIADA','angular_tolerance_deg':None,
                     'north_true_or_magnetic':'NAO_INFORMADO','origin':'E0 como convenção analítica, não percurso comprovado',
                     'phone_heading_223_is_clue':False},
        'person':{'age':43,'occupation':'Trabalhador rural e pequeno produtor','experience_years':15,
                  'physical_condition':'Boa, sem limitações conhecidas no cenário','mobility':'A pé',
                  'familiarity':'Moderada a elevada nos acessos habituais',
                  'clothing':['calça comprida','camisa de manga longa','botas','boné'],
                  'equipment':['facão','mochila pequena','garrafa de água','telefone celular'],
                  'activity':'Inspeção de propriedade, cercas e áreas de trabalho',
                  'last_contact_condition':'Consciente, orientado, sem relato de lesão'},
        'environment':'Cerrado amazônico, fragmentos florestais e ocupação semirrural; não floresta contínua',
        'environmental_temperature_humidity':'Hipóteses do cenário, não medições extraídas das fotografias',
        'ground_truth_absent':True,
        'evaluation':'Demonstração de processamento, coerência e rastreabilidade; não eficácia operacional',
        'excluded':['KM21SoloVit.HEIC (conteúdo e metadados não acessados)',
                    'Coordenada de encontro de MATA-02','Orientação 223° da tela como direção da pessoa'],
        'sampling':'60 x 60 pontos estratificados por setor; não censo de todos os pixels',
        'direction_used_in_BASE':False,
        'photo_pixels_used_in_ranking':False,
        'field_obstacles_not_measured':'Emaranhamento, cercas, travessias, passagem sob dossel e umidade atual não inferidos quantitativamente'
    }
    write(OUT/'premissas_congeladas.json', premises)
    evidence_hash = sha(OUT/'premissas_congeladas.json')
    item = {
        'protocol_id':protocol,'scenario_id':'MATA-03','candidate_id':'MATA-03-E0',
        'estimated_lat':LAT,'estimated_lon':LON,'adaptive_radius_m':RADIUS,
        'buffer_area_m2':math.pi*RADIUS**2,'review_status':'REVISAR',
        'execution_classification':'CENARIO_CONTROLADO_SEMISSINTETICO_EM_TERRITORIO_REAL',
        'confirmatory_eligible':False,'ground_truth_used':False,'source_row_hash':evidence_hash,
        'coordinate_capture_timestamp_local':'2026-10-22T08:28:00-03:00',
        'event_timestamp_local':'2026-10-22T08:28:00-03:00',
        'detection_quality':None,'detection_quality_imputed':False,
        'additional_factors_applied_by_engine':False,'point_semantics':'PONTO_INICIAL_DE_PLANEJAMENTO',
        'r0_semantics':'source_declared_operational_domain',
        'radius_method':'DOMINIO_OPERACIONAL_DIRETO_SEM_BUFFER_ADAPTATIVO',
        'radius_origin':'INFORMADO_PELO_PESQUISADOR',
        'radius_rationale':'DOMINIO_DE_7_KM_INFORMADO_PARA_O_ENSAIO; NAO_DERIVADO_NESTA_EXECUCAO',
        'source_metadata_verification':'COORDENADA_E_HORA_CONFERIDAS_NA_CAPTURA; DATA_DECLARADA_NO_CENARIO',
        'source_record_origin':'CENARIO_FORNECIDO_PELO_USUARIO_E_CAPTURA_KM21_PNG'
    }
    entry = {k:item[k] for k in ['protocol_id','execution_classification','ground_truth_used','confirmatory_eligible',
             'r0_semantics','radius_method','radius_origin','detection_quality_imputed','additional_factors_applied_by_engine']}
    entry.update(protocol_version='1.0', record_count=1, scenario_count=1, radius_m=RADIUS,
                 radius_review_status='REVISAR', adaptive_buffer_status='NAO_EXECUTADO_ENTRADA_INSUFICIENTE',
                 detection_quality_available=False, results=[item])
    poly=[]
    for i in range(144):
        a,b=motor.destination(LAT,LON,RADIUS,i*360/144)
        poly.append([b,a])
    poly.append(poly[0])
    props=copy.deepcopy(item)
    props['radius_m']=RADIUS
    geometry={'type':'FeatureCollection','features':[{'type':'Feature','id':'MATA-03::MATA-03-E0','properties':props,
               'geometry':{'type':'Polygon','coordinates':[poly]}}]}
    jp=OUT/'entrada_raio_fonte_mata03_km21.json'
    gp=OUT/'entrada_raio_fonte_mata03_km21.geojson'
    mp=OUT/'manifesto_entrada.json'
    write(jp,entry);write(gp,geometry)
    manifest={k:v for k,v in entry.items() if k!='results'}
    manifest['files']=[{'path':p.name,'role':'output','bytes':p.stat().st_size,'sha256':sha(p)} for p in (jp,gp)]
    write(mp,manifest)
    rows=motor.validate_buffer_contract(read(jp),read(gp),read(mp),jp,gp,cfg)
    sectors=motor.make_sector_records(rows,cfg)
    assert len(sectors)==24
    assert all(len(s['sample_points'])==3600 for s in sectors)
    extent=[motor.destination(LAT,LON,17000,b) for b in range(360)]
    assert all(-.25<=a<=.45 and -51.95<=b<=-50.70 for a,b in extent)
    roads,rt=motor.load_road_segments(GEO/'osm_highways_raw.json',cfg)
    hydro,ht=motor.load_hydro_segments(GEO/'osm_hydrography_raw.json',cfg)
    nh=helper._domain_segment_count(motor,hydro,LAT,LON,RADIUS)
    nr=helper._domain_segment_count(motor,roads,LAT,LON,RADIUS)
    write(OUT/'verificacao_espacial.json', {'domain_radius_m':RADIUS,'halo_checked_m':17000,
          'OSM_bbox_contains_domain_and_nearest_search_halo':True,'road_segments_in_domain':nr,
          'hydro_segments_in_domain':nh,'hydro_completeness_on_ground':'NAO_VERIFICADA',
          'coordinate_system':'EPSG:4326','sectors':24,'samples_per_sector':3600,
          'sample_total':86400,'target_reference_not_used':True})
    print('Entrada congelada; 24 setores; iniciando extração territorial.',flush=True)
    hgt=motor.HGTSampler(GEO)
    wc=motor.WorldCoverSampler(GEO/'worldcover_tiles')
    cell=float(cfg['feature_extraction']['spatial_index_cell_deg'])
    try:
        features=motor.extract_sector_features(sectors,rows,cfg,
             motor.SpatialSegmentIndex(roads,cell),motor.SpatialSegmentIndex(hydro,cell),hgt,wc,rt,ht)
    finally:
        wc.close()
    sampling=[{'sector_id':r['sector_id'],'terrain_valid':r['terrain_sample_count'],
               'terrain_expected':r['terrain_expected_sample_count'],'worldcover_valid':r['worldcover_sample_count'],
               'worldcover_expected':r['worldcover_expected_sample_count']} for r in features]
    assert all(s['terrain_valid']==s['terrain_expected']==s['worldcover_valid']==s['worldcover_expected']==3600 for s in sampling)
    if nh==0:
        features=helper._apply_hydro_abstention(features)
    ranked=motor.rank_sector_records(features,cfg)
    repeated=motor.rank_sector_records(copy.deepcopy(features),copy.deepcopy(cfg))
    assert ranked==repeated
    arithmetic=[]
    if nh:
        for r in ranked:
            expected=sum(w*r[k] for w,k in [(.30,'road_trail_access_score'),(.25,'hydro_access_score'),
                        (.20,'terrain_access_score'),(.25,'landcover_access_score')])
            delta=abs(expected-r['score_base'])
            assert delta<1e-8
            arithmetic.append({'sector_id':r['sector_id'],'independent_weighted_sum':expected,'difference':delta})
    assert all(r['ground_truth_used'] is False for r in ranked)
    decisions=motor.summarize_buffer_decisions(ranked,cfg)
    motor.write_csv(OUT/'atributos_setores.csv',helper._clean_feature_rows(features))
    motor.write_csv(OUT/'ranking_BASE.csv',ranked)
    write(OUT/'ranking_BASE.json',ranked)
    write(OUT/'decisoes_BASE.json',decisions)
    write(OUT/'setores_BASE.geojson',motor.build_sector_geojson(sectors,cfg,{r['sector_id']:r for r in ranked}))
    if nh==0:
        diag=helper._rank_available_modules(features)
        for r in diag: r['protocol_id']='MATA03-KM21-DIAGNOSTICO-SEM-GEO03-v1.0'
        motor.write_csv(OUT/'ranking_DIAGNOSTICO_SEM_GEO03.csv',diag)
        write(OUT/'ranking_DIAGNOSTICO_SEM_GEO03.json',diag)
    write(OUT/'qa_calculos.json',{'sampling':sampling,'weighted_sum_check':arithmetic,
          'ranking_repeated_identical':True,'feature_extraction_repeated':False,
          'full_raster_zonal_census':False,'operational_efficacy_tested':False,
          'probabilities_calibrated':False,'ground_truth_used':False})
    explicit={'KM21.PNG','KM21Solo0386.HEIC','KM21Solo0387.HEIC','KM21Solo0388.HEIC'}
    explicit.update(f'KM21Drone{n:04d}.JPG' for n in [867,868,869,870,871,872,873,875])
    inventory=[]
    for p in sorted(PHOTO.iterdir()):
        if not p.is_file() or p.name.startswith('.'): continue
        excluded=p.name=='KM21SoloVit.HEIC'
        rec={'name':p.name,'bytes':p.stat().st_size,'explicitly_attached':p.name in explicit,
             'excluded_potential_outcome':excluded,'content_read':False,'used_in_ranking':False}
        if not excluded:
            rec['sha256']=sha(p)
        inventory.append(rec)
    write(OUT/'inventario_imagens.json',{'files':inventory,'explicit_count':len(explicit),
          'declared_count':16,'target_candidate_not_read':True,
          'note':'Arquivos extras não são novas ocorrências. KM21SoloVit não teve conteúdo nem EXIF acessados.'})
    source_paths=[ROOT/'work/ext_espacial_setores_v1_1/motor_setorizacao_priorizacao.py',Path(__file__),
                  ROOT/'work/mata02_mzg2_processamento_cego_v1/run_mata02_mzg2_blind.py',
                  GEO/'N00W052.hgt.gz',GEO/'worldcover_tiles/ESA_WorldCover_10m_2021_v200_N00W054_Map.tif',
                  GEO/'osm_highways_raw.json',GEO/'osm_hydrography_raw.json',
                  GEO/'geo02_overpass_query.txt',GEO/'geo03_overpass_query.txt']
    write(OUT/'manifesto_BASE.json',{'case':'MATA-03','created_at':NOW,'ground_truth_used':False,
          'sources':[{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in source_paths],
          'outputs':[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.iterdir()) if p.is_file()],
          'old_case_files_modified':False})
    result={'case':'MATA-03','protocol':cfg['protocol_id'],'direction_deg':285,
            'direction_applied_to_BASE':False,'hydro_segments_in_domain':nh,
            'decisions':decisions,'top3':helper._top3_rows(ranked),
            'classification':'ESCORE_HEURISTICO_TERRITORIAL_NAO_PROBABILISTICO',
            'target_unrevealed':True}
    write(OUT/'resultado_BASE.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2,default=str),flush=True)

if __name__=='__main__':
    main()
