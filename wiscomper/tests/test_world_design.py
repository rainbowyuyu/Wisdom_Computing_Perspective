"""Bounded world-design tests: no API calls or model generation."""
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from server.schema import Scene
from server.world_design import design_world, DesignError, PARAMETERS


@pytest.mark.parametrize('domain,prompt',[
    ('pendulum','做一个钟摆的世界仿真'),
    ('rocket','做一个火箭世界仿真'),
    ('wind_turbine','做一个风机世界仿真'),
])
def test_defaults_have_complete_contract_and_valid_schematic(domain,prompt):
    result=design_world({'prompt':prompt})
    assert result['schema']=='world-design-v1'
    assert result['source']=='wiscomper'
    assert result['domain']==domain
    assert result['status']=='designed'
    assert result['parameters']=={key:values[0] for key,values in PARAMETERS[domain].items()}
    assert result['simulation']['parameters']==result['parameters']
    assert result['duration_s']==12 and result['dt_s']==.02
    assert all(meta['source']=='teaching_default' for meta in result['parameter_metadata'].values())
    assert result['objects'] and result['constraints'] and result['observables']
    scene=Scene.model_validate(result['scene'])
    assert scene.evidence=='schematic'
    assert not any(item.frames for item in scene.objects)
    assert result['design_metadata']['paid_model_used'] is False
    assert result['id']==design_world({'prompt':prompt})['id']


def test_chinese_parameters_are_parsed_and_converted_to_si():
    d=design_world({'prompt':'钟摆世界，摆长 150 厘米，质量 500 克，初始角度 30 度，仿真时长 20 秒，步长 10 毫秒'})
    assert d['parameters']['length_m']==1.5
    assert d['parameters']['mass_kg']==.5
    assert d['parameters']['theta0_rad']==pytest.approx(math.pi/6)
    assert d['duration_s']==20 and d['dt_s']==.01
    assert d['parameter_metadata']['length_m']['source']=='prompt'
    assert d['design_metadata']['time_sources']['duration_s']=='prompt'
    assert d['warnings']==[]


def test_rocket_named_parameters_and_units():
    d=design_world({'prompt':'火箭世界，干质量 60kg，推进剂质量 20kg，推力 2kN，燃烧时间 5秒，迎风面积 800cm²，阻力系数0.4'})
    assert d['parameters']['dry_mass_kg']==60
    assert d['parameters']['propellant_mass_kg']==20
    assert d['parameters']['thrust_N']==2000
    assert d['parameters']['burn_time_s']==5
    assert d['parameters']['area_m2']==pytest.approx(.08)
    assert d['parameters']['drag_coefficient']==.4
    assert not d['warnings']


def test_structured_values_override_prompt_and_preserve_provenance():
    d=design_world({'prompt':'钟摆，摆长1米','parameters':{'length_m':{'value':2.5,'unit':'m'}}})
    assert d['parameters']['length_m']==2.5
    assert d['parameter_metadata']['length_m']['source']=='user'
    assert d['parameter_metadata']['length_m']['prompt_input']['text']=='摆长1米'
    assert any('覆盖' in warning for warning in d['warnings'])


@pytest.mark.parametrize('prompt',['双摆世界','做一个汽车世界仿真','钟摆和火箭世界','轴流风机世界'])
def test_unsupported_or_ambiguous_model_fails(prompt):
    with pytest.raises(DesignError):
        design_world({'prompt':prompt})


@pytest.mark.parametrize('params',[
    {'length_m':float('nan')},{'length_m':True},{'length_m':-1},
    {'length_m':{'value':1,'unit':'cm'}},{'unknown':1},{'theta0_rad':3.},
])
def test_invalid_parameters_fail(params):
    with pytest.raises(DesignError):
        design_world({'prompt':'钟摆世界','parameters':params})


def test_unbound_numbers_and_missing_angle_units_are_visible():
    d=design_world({'prompt':'钟摆世界，初始角度30，采样100次'})
    assert d['parameters']['theta0_rad']==.5
    assert d['design_metadata']['prompt_has_unparsed_numbers']
    assert any('缺少角度单位' in warning for warning in d['warnings'])
    assert any('100' in warning for warning in d['warnings'])


def test_duplicate_conflicting_values_are_rejected():
    with pytest.raises(DesignError,match='不同数值'):
        design_world({'prompt':'钟摆摆长1米，摆长2米'})


def test_wind_does_not_relabel_fan_or_accept_physical_wind_speed():
    d=design_world({'prompt':'风机世界，风载倍率1.5倍，波浪倍率0.8倍，海流倍率0.2倍'})
    assert d['parameters']=={'wind_scale':1.5,'wave_scale':.8,'current_scale':.2}
    assert d['simulation']['model']=='physcast_existing_coupled_rom'
    with pytest.raises(DesignError):
        design_world({'prompt':'风机世界','parameters':{'wind_speed':12}})
    with pytest.raises(DesignError):
        design_world({'prompt':'风机世界','dt_s':.03})


def test_cli_uses_utf8_json_and_roundtrips_formula_backslashes():
    process=subprocess.run([sys.executable,'-m','server.world_design'],
        cwd=str(Path(__file__).resolve().parents[1]),
        input=json.dumps({'prompt':'钟摆世界，摆长1米'},ensure_ascii=False).encode('utf-8'),
        capture_output=True,timeout=15)
    assert process.returncode==0,process.stderr.decode('utf-8',errors='replace')
    d=json.loads(process.stdout)['data']
    assert d['parameters']['length_m']==1
    formula=next(o['latex'] for o in d['scene']['objects'] if o['kind']=='formula')
    assert r'\ddot\theta' in formula
    assert not any(ord(char)<32 for char in formula)


@pytest.mark.parametrize('prompt,key,default',[
    ('rocket thrust 2kN/m','thrust_N',1500.),
    ('pendulum length 2m/s','length_m',2.),
    ('pendulum mass 2kg/m^2','mass_kg',1.),
])
def test_compound_units_are_not_silently_truncated(prompt,key,default):
    d=design_world({'prompt':prompt})
    assert d['parameters'][key]==default
    assert d['parameter_metadata'][key]['source']=='teaching_default'
    assert d['warnings'] and d['design_metadata']['prompt_has_unparsed_numbers']


def test_wind_time_grid_requires_explicit_point_one_seconds():
    with pytest.raises(DesignError,match='0.1'):
        design_world({'prompt':'风机世界','duration_s':1.03})
