"""Engineering geometry provenance tests. No solver, model API or paid calls."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from server.engineering_design import import_engineering_design,EngineeringImportError
from server.schema import Scene

WORKSPACE_ID = 'a' * 32
BASIS = 'inputs/design-basis.json'
RELEASE = 'reports/release.json'
REVIEW = 'reports/scope.md'
PROFILES = {
    'C14': {'label':'C14 test assembly', 'kind':'assembly',
            'geometry_path':'geometry/C14/report.json', 'mesh_path':'geometry/C14/mesh.json'},
    'C15N80': {'label':'C15N80 test wet surface', 'kind':'wet_surface',
              'geometry_path':'geometry/C15N80/report.json', 'mesh_path':'geometry/C15N80/mesh.json'},
}
SETTINGS = {
    'WISCOMPER_ENGINEERING_BASIS_PATH': BASIS,
    'WISCOMPER_ENGINEERING_RELEASE_PATH': RELEASE,
    'WISCOMPER_ENGINEERING_REVIEW_PATH': REVIEW,
    'WISCOMPER_ENGINEERING_DEFAULT_CANDIDATE': 'C14',
    'WISCOMPER_ENGINEERING_PROFILES_JSON': json.dumps(PROFILES),
}


@pytest.fixture
def workspace(tmp_path):
    root=tmp_path/'workspaces';base=root/WORKSPACE_ID/'files';out=tmp_path/'artifacts'
    def put(name,value):
        path=base/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value,ensure_ascii=False) if not isinstance(value,str) else value,encoding='utf-8')
        return path
    report={'candidate':'C14','records':[
        {'id':'HULL','role':'hull','CG_m':[0,0,-5],'volume_m3':400,'valid':True},
        {'id':'WT-HUB','role':'RNA envelope','CG_m':[-14,0,170],'volume_m3':200,'valid':True}],
        'passed':True,'checks':[{'id':'cad-only','passed':True}],'limitations':['No structural approval']}
    mesh={'schema':'ai-engineer-scene-v1','units':{'length':'m'},'nodes':[[0,0,-5],[10,0,-5],[0,10,170]],
          'elements':[[0,1,2]],'types':[5],'title':'C14 fixture'}
    basis={'schema':'LJ20-C1-design-basis/v1','units':{'geometry':'m','body_z':'SWL0up'},
        'project':{'power_MW':20,'site':'exactcoordinatesunknown','permanent_steel_limit_t':6000,'capex_CNY':400000000},
        'load_scenarios':{'depth_m':80,'environment_status':'assumed_not_localextremes_orOEMDLC'},
        'reference':{'cavities':42},'failure_inputs':['known-failure']}
    put(PROFILES['C14']['geometry_path'],report);put(PROFILES['C14']['mesh_path'],mesh);put(BASIS,basis)
    put(RELEASE,{'engineering_finalized':False,'stage':'review_only_not_engineering_acceptance'})
    put(REVIEW,'C14 and C15 are review candidates; not accepted.')
    return root,base,out,put,report,mesh,basis


def run(workspace,source=None,**extra):
    root,base,out,*_=workspace
    return import_engineering_design({'prompt':'导入测试报告','source_geometry':{'workspace_id':WORKSPACE_ID,**(source or {})},**extra},workspaces=root,output_root=out,settings=SETTINGS)


def test_exact_coordinates_provenance_and_nonfarm_semantics(workspace):
    d=run(workspace)
    assert d['domain']=='floating_platform' and not d['simulation']['available']
    assert d['accepted'] is False
    assert d['engineering_geometry']['turbines']==[]
    assert d['engineering_objects'][1]['position_m']==[-14,0,170]
    assert d['engineering_objects'][1]['coordinate_semantics']=='center_of_volume_from_CAD_report'
    assert d['parameters']=={}
    assert d['engineering_parameters']['rated_power_MW']==20
    assert d['source_checks']['cad_report_passed'] is True
    assert d['source_checks']['release']['engineering_finalized'] is False
    assert d['source_checks']['design_basis_failure_inputs']==['known-failure']
    assert {'site_coordinates','farm_turbine_coordinates','compatible_20mw_model'}<={item['id'] for item in d['missing_inputs']}
    assert Scene.model_validate(d['scene']).mode=='3d'
    assert not any(o['frames'] for o in d['scene']['objects'])


def test_normalized_file_matches_geometry_and_hash(workspace):
    d=run(workspace);g=d['engineering_geometry'];raw=Path(g['source']['path']).read_bytes();saved=json.loads(raw)
    assert hashlib.sha256(raw).hexdigest()==g['source']['sha256']
    for key in ['schema','kind','coordinate_system','units','components','turbines','candidate']:
        assert saved[key]==g[key]
    mesh=d['engineering_mesh'];raw=Path(mesh['source']['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==mesh['source']['sha256']
    assert raw==Path(mesh['cached_source']['path']).read_bytes()
    assert run(workspace)['id']==d['id']


def test_changed_source_gets_new_immutable_identity(workspace):
    d=run(workspace);root,base,out,put,report,*_=workspace
    report['records'][1]['CG_m'][2]=175;put(PROFILES['C14']['geometry_path'],report)
    new=run(workspace)
    assert new['id']!=d['id'] and new['engineering_objects'][1]['position_m'][2]==175
    assert json.loads(Path(d['engineering_geometry']['source']['path']).read_text(encoding='utf-8'))['components'][1]['position_m'][2]==170


@pytest.mark.parametrize('source',[
    {'geometry_path':'.'},
    {'geometry_path':'../../secrets.json'}, {'mesh_path':'C:/private/data.json'},
    {'candidate':'C15N80','geometry_path':PROFILES['C14']['geometry_path']},
    {'expected_sha256':'0'*64},{'candidate':'C999'},
])
def test_unsafe_paths_hash_changes_and_mixed_candidates_rejected(workspace,source):
    with pytest.raises(EngineeringImportError):run(workspace,source)


def test_no_guess_when_coordinate_is_missing(workspace):
    root,base,out,put,report,*_=workspace
    del report['records'][0]['CG_m'];put(PROFILES['C14']['geometry_path'],report)
    with pytest.raises(EngineeringImportError,match='CG_m'):run(workspace)


def test_coincident_component_centers_do_not_crash_preview(workspace):
    root,base,out,put,report,*_=workspace
    report['records'][1]['CG_m']=report['records'][0]['CG_m'][:]
    put(PROFILES['C14']['geometry_path'],report)
    d=run(workspace)
    assert d['scene_transform']['displayed_points']==2
    assert d['scene_transform']['uniform_scale']==8
    Scene.model_validate(d['scene'])


def test_invalid_mesh_units_and_indices_rejected(workspace):
    root,base,out,put,report,mesh,basis=workspace
    mesh['units']['length']='mm';put(PROFILES['C14']['mesh_path'],mesh)
    with pytest.raises(EngineeringImportError,match='length=m'):run(workspace)
    mesh['units']['length']='m';mesh['elements'][0][2]=999;put(PROFILES['C14']['mesh_path'],mesh)
    with pytest.raises(EngineeringImportError,match='节点'):run(workspace)


def test_memory_is_verified_context_not_physical_input(workspace):
    root,base,out,put,*_=workspace
    p=put('notes/memory.md','连江单平台候选，实际地理坐标缺失。')
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    d=run(workspace,memory_context={'items':[{'path':'notes/memory.md','workspace_id':WORKSPACE_ID,
        'sha256':digest,'excerpt':'风场有10台机组(unsupported caller statement)','title':'连江记忆','kind':'memory'}]})
    assert d['memory_context']['items'][0]['verification']=='file_hash_verified'
    assert d['memory_context']['physical_values_extracted'] is False
    assert d['engineering_geometry']['turbines']==[]
    assert len(d['engineering_objects'])==2


def test_dot_path_in_memory_remains_unverified_instead_of_crashing(workspace):
    d=run(workspace,memory_context={'items':[{'path':'.','workspace_id':WORKSPACE_ID}]})
    assert d['memory_context']['items'][0]['verification']=='unverified_context'
    assert d['memory_context']['physical_values_extracted'] is False


def test_wet_surface_does_not_invent_assembly_components(workspace):
    root,base,out,put,report,mesh,basis=workspace
    put(PROFILES['C15N80']['geometry_path'],{'schema':'C15-r2-wetmesh-audit-v1','candidate':'C15N80'})
    put(PROFILES['C15N80']['mesh_path'],mesh)
    d=run(workspace,{'candidate':'C15N80'})
    assert d['engineering_objects']==[]
    assert d['engineering_geometry']['scope']=='wet_surface'
    assert d['scene_transform']['source_kind']=='sampled_surface_vertices'
    assert any(m['id']=='full_assembly' for m in d['missing_inputs'])


def test_unconfigured_integration_is_friendly_and_creates_no_output(tmp_path):
    with pytest.raises(EngineeringImportError) as caught:
        import_engineering_design({'prompt':'查看工程','source_geometry':{}}, settings={}, output_root=tmp_path/'out')
    assert caught.value.code == 'integration_unavailable'
    assert '普通可视化仍可使用' in str(caught.value)
    assert not (tmp_path/'out').exists()


def test_configuration_is_resolved_at_call_time_and_preserves_existing_identity(workspace,monkeypatch):
    root,base,out,*_=workspace
    config={**SETTINGS, 'WISCOMPER_ENGINEERING_WORKSPACES':str(root),
            'WISCOMPER_ENGINEERING_WORKSPACE_ID':WORKSPACE_ID}
    monkeypatch.setattr('server.engineering_design.load_settings', lambda: config)
    result=import_engineering_design({'prompt':'配置来源','source_geometry':{}},output_root=out)
    assert result['id']==run(workspace)['id']
    assert result['candidate_selection']['basis']=='configured_default_review_candidate'
    monkeypatch.setattr('server.engineering_design.load_settings', lambda: {})
    with pytest.raises(EngineeringImportError) as caught:
        import_engineering_design({'prompt':'未配置来源','source_geometry':{}},output_root=out)
    assert caught.value.code=='integration_unavailable'


@pytest.mark.parametrize('key,value',[
    ('WISCOMPER_ENGINEERING_WORKSPACES','relative/workspaces'),
    ('WISCOMPER_ENGINEERING_PROFILES_JSON','{invalid json'),
    ('WISCOMPER_ENGINEERING_PROFILES_JSON','{}'),
    ('WISCOMPER_ENGINEERING_PROFILES_JSON',json.dumps({'demo':{'label':'demo','kind':'assembly','geometry_path':'../secret','mesh_path':'geometry/mesh.json'}})),
])
def test_invalid_configuration_has_safe_error(workspace,key,value):
    root,base,out,*_=workspace
    config={**SETTINGS,'WISCOMPER_ENGINEERING_WORKSPACES':str(root),key:value}
    with pytest.raises(EngineeringImportError) as caught:
        import_engineering_design({'prompt':'配置测试','source_geometry':{'workspace_id':WORKSPACE_ID}},settings=config,output_root=out)
    assert caught.value.code=='integration_config_invalid'
    assert str(value) not in str(caught.value)


def test_missing_profiles_do_not_guess_local_source(workspace):
    root,base,out,*_=workspace
    with pytest.raises(EngineeringImportError) as caught:
        import_engineering_design({'prompt':'配置测试','source_geometry':{'workspace_id':WORKSPACE_ID}},workspaces=root,settings={},output_root=out)
    assert caught.value.code=='integration_unavailable'


def test_public_dispatcher_reports_disabled_integration_without_breaking_regular_design(monkeypatch):
    from server.world_design import design_world
    monkeypatch.setattr('server.engineering_design.load_settings', lambda: {})
    with pytest.raises(EngineeringImportError) as caught:
        design_world({'prompt':'工程来源','source_geometry':{}})
    assert caught.value.code=='integration_unavailable'
    normal=design_world({'prompt':'展示风机','domain':'wind_turbine'})
    assert normal['schema']=='world-design-v1'


@pytest.mark.skipif(os.environ.get('RUN_REAL_ENGINEERING')!='1',reason='real engineering sources require explicit opt-in')
def test_real_configured_sources(tmp_path):
    from configuration import load_settings
    config=load_settings()
    profiles=json.loads(config.get('WISCOMPER_ENGINEERING_PROFILES_JSON') or '{}')
    if not profiles or not config.get('WISCOMPER_ENGINEERING_WORKSPACE_ID'):
        pytest.skip('local integration is not configured')
    for candidate in profiles:
        d=import_engineering_design({'prompt':'真实源导入验收','source_geometry':{'candidate':candidate}},output_root=tmp_path,settings=config)
        assert d['engineering_mesh']['node_count']>0
        assert d['engineering_geometry']['turbines']==[]
        assert d['accepted'] is False
