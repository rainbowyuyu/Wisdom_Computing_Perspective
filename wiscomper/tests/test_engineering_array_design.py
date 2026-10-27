"""Source-bound turbine positions; no paid models or hidden physics defaults."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from server.engineering_design import EngineeringImportError, import_turbine_array_design
from server.schema import Scene
from server.world_design import design_world, DesignError


@pytest.fixture
def array_source(tmp_path):
    root=tmp_path/'workspaces';native=tmp_path/'native'/'engineering'
    native.mkdir(parents=True)
    geometry={'schema':'engineering-geometry-v1','kind':'turbine_array','units':'m','coordinate_system':'local_cartesian',
              'evidence_kind':'synthetic_smoke_not_lianjiang','turbines':[
                  {'id':'T1','x_m':-630,'y_m':100,'z_m':0,'yaw_deg':0,'pitch_deg':0},
                  {'id':'T2','x_m':0,'y_m':200,'z_m':0,'yaw_deg':10,'pitch_deg':0}], 'components':[]}
    def save(geometry=geometry,path=None):
        p=path or native/'geometry.json';p.parent.mkdir(parents=True,exist_ok=True)
        raw=json.dumps(geometry,ensure_ascii=False,allow_nan=False).encode('utf-8');p.write_bytes(raw)
        return {**deepcopy(geometry),'source':{'path':str(p),'sha256':hashlib.sha256(raw).hexdigest()}}
    return root,native,geometry,save


def imported(fixture,geometry=None,**extra):
    root,native,g,save=fixture
    return import_turbine_array_design({'prompt':'呈现源文件布局','engineering_geometry':geometry or save(),**extra},workspaces=root,native_outputs=native,settings={})


def test_preserves_full_geometry_and_displays_exact_scaled_locations(array_source):
    root,native,g,save=array_source;supplied=save();original=deepcopy(supplied)
    d=imported(array_source,supplied)
    assert d['domain']=='wind_farm' and d['model_kind']=='engineering_configuration'
    assert d['engineering_geometry']==original==supplied
    assert d['engineering_geometry'] is not supplied
    assert 'engineering_mesh' not in d
    assert d['visualization_kind']=='layout_view' and d['accepted'] is False
    assert '合成验证' in d['title']
    scene=Scene.model_validate(d['scene']);assert scene.mode=='2d'
    scale=d['scene_transform']['uniform_scale'];center=d['scene_transform']['center_source_m']
    markers=[o for o in scene.objects if o.kind=='circle']
    assert len(markers)==len(g['turbines'])
    for marker,row in zip(markers,g['turbines']):
        assert marker.x/scale+center[0]==pytest.approx(row['x_m'])
        assert marker.y/scale+center[1]==pytest.approx(row['y_m'])
    assert all(not obj.frames for obj in scene.objects)
    assert not any(obj.kind in ('sphere','cylinder','cone','box') for obj in scene.objects)


@pytest.mark.parametrize('key,value',[('units','mm'),('coordinate_system','geographic'),('turbines',[])])
def test_rejects_geometry_changed_after_source_binding(array_source,key,value):
    supplied=array_source[3]();supplied[key]=value
    with pytest.raises(EngineeringImportError) as caught:imported(array_source,supplied)
    assert caught.value.code=='geometry_source_mismatch'


def test_rejects_changed_coordinates_and_context_claims(array_source):
    supplied=array_source[3]();supplied['turbines'][0]['x_m']=100
    with pytest.raises(EngineeringImportError) as caught:imported(array_source,supplied)
    assert caught.value.code=='geometry_source_mismatch'
    supplied=array_source[3]();supplied['evidence_kind']='actual_lianjiang'
    with pytest.raises(EngineeringImportError):imported(array_source,supplied)


def test_rejects_changed_file_bytes(array_source):
    supplied=array_source[3]();Path(supplied['source']['path']).write_text('{}',encoding='utf-8')
    with pytest.raises(EngineeringImportError) as caught:imported(array_source,supplied)
    assert caught.value.code=='source_changed'


def test_original_workspace_geometry_allowed_but_reports_not(array_source):
    root,native,g,save=array_source
    allowed=root/('a'*32)/'files'/'geometry'/'array.json'
    assert imported(array_source,save(path=allowed))['source_checks']['source_json_equal']
    denied=root/('a'*32)/'files'/'reports'/'array.json'
    with pytest.raises(EngineeringImportError) as caught:imported(array_source,save(path=denied))
    assert caught.value.code=='source_outside_allowed_roots'


def test_other_paths_and_traversal_rejected(array_source,tmp_path):
    root,native,g,save=array_source
    with pytest.raises(EngineeringImportError):imported(array_source,save(path=tmp_path/'foreign.json'))
    supplied=save();supplied['source']['path']=str(native/'x'/'..'/'geometry.json')
    with pytest.raises(EngineeringImportError):imported(array_source,supplied)


@pytest.mark.parametrize('raw',[b'{"kind":"turbine_array","kind":"floating_platform"}',b'{"number":NaN}',b'{}'+b' '*4194304],ids=['duplicate-key','nonfinite','oversized'])
def test_ambiguous_nonfinite_and_oversized_json_rejected(array_source,raw):
    supplied=array_source[3]();Path(supplied['source']['path']).write_bytes(raw)
    supplied['source']['sha256']=hashlib.sha256(raw).hexdigest()
    with pytest.raises(EngineeringImportError):imported(array_source,supplied)


@pytest.mark.parametrize('modify',[
    lambda g:g.update(units='mm'),
    lambda g:g.update(coordinate_system='geographic'),
    lambda g:g.update(kind='floating_platform'),
    lambda g:g['turbines'][0].pop('z_m'),
    lambda g:g['turbines'][0].update(x_m=True),
    lambda g:g['turbines'][0].update(x_m=10**400),
    lambda g:g['turbines'][0].update(yaw_deg='0'),
    lambda g:g['turbines'][0].update(yaw_deg=10**400),
    lambda g:g['turbines'][1].update(id='T1'),
    lambda g:g['turbines'][0].update(id='<script>'),
    lambda g:g.update(turbines=[]),
])
def test_unsupported_source_semantics_rejected_without_guessing(array_source,modify):
    root,native,g,save=array_source;modify(g)
    with pytest.raises(EngineeringImportError):imported(array_source,save(g))


def test_source_conflict_rejected_by_public_dispatcher():
    with pytest.raises(DesignError) as caught:
        design_world({'prompt':'array','source_geometry':{},'engineering_geometry':{}})
    assert caught.value.code=='conflicting_geometry_sources'


def test_scene_capacity_does_not_drop_locations(array_source):
    root,native,g,save=array_source
    g['turbines']=[{'id':'T'+str(i),'x_m':i*400,'y_m':(i%5)*400,'z_m':0} for i in range(80)]
    d=imported(array_source,save(g));assert len(d['engineering_objects'])==80
    assert len([o for o in d['scene']['objects'] if o['kind']=='circle'])==80
    g['turbines'].append({'id':'T80','x_m':32000,'y_m':0,'z_m':0})
    with pytest.raises(EngineeringImportError):imported(array_source,save(g))


def test_single_position_and_nonzero_elevation_remain_explicit(array_source):
    root,native,g,save=array_source
    g['turbines']=[{'id':'T1','x_m':100,'y_m':200,'z_m':60}]
    d=imported(array_source,save(g))
    assert d['engineering_objects'][0]['position_m']==[100,200,60]
    assert d['scene_transform']['metres_per_view_unit']==1
    assert d['scene_transform']['displayed_points']==1


def test_unconfigured_array_import_is_friendly_without_file_access(monkeypatch):
    def unexpected_read(*args,**kwargs):
        pytest.fail('unconfigured integration must not read a source file')
    monkeypatch.setattr(Path,'read_bytes',unexpected_read)
    with pytest.raises(EngineeringImportError) as caught:
        import_turbine_array_design({'prompt':'查看布局','engineering_geometry':{}},settings={})
    assert caught.value.code=='integration_unavailable'
    assert '普通可视化仍可使用' in str(caught.value)


def test_only_native_root_is_allowed_without_workspace_configuration(array_source):
    root,native,g,save=array_source
    result=import_turbine_array_design({'prompt':'只配置本地输出','engineering_geometry':save(),
        'memory_context':{'items':[{'path':'notes/source.md','workspace_id':'a'*32}]}},
        settings={'WISCOMPER_ENGINEERING_NATIVE_OUTPUTS':str(native)})
    assert result['source_checks']['source_hash_verified']
    assert result['memory_context']['items'][0]['verification']=='unverified_context'


def test_only_workspace_root_does_not_open_unconfigured_native_output(array_source):
    root,native,g,save=array_source
    config={'WISCOMPER_ENGINEERING_WORKSPACES':str(root)}
    source=save(path=root/('a'*32)/'files'/'geometry'/'array.json')
    assert import_turbine_array_design({'prompt':'工程根目录','engineering_geometry':source},settings=config)['source_checks']['source_json_equal']
    with pytest.raises(EngineeringImportError) as caught:
        import_turbine_array_design({'prompt':'其他目录','engineering_geometry':save()},settings=config)
    assert caught.value.code=='source_outside_allowed_roots'


@pytest.mark.skipif(not os.environ.get('WISCOMPER_TEST_ENGINEERING_REQUEST'),reason='real engineering fixture requires explicit opt-in path')
def test_native_smoke_uses_public_design_entrypoint():
    request=json.loads(Path(os.environ['WISCOMPER_TEST_ENGINEERING_REQUEST']).read_text(encoding='utf-8'))
    g=request['spec']['geometry'];d=design_world({'prompt':'查看明确标注的合成验证布局','engineering_geometry':g})
    assert d['engineering_geometry']==g
    assert d['domain']=='wind_farm'
    assert [o['position_m'] for o in d['engineering_objects']]==[[0,0,0],[630,0,0]]
