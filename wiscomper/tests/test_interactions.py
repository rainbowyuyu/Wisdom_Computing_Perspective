import copy
import math

import pytest
from pydantic import ValidationError

from server.builders import build_scene,sample_proposal
from server.interactions import bake_scene,prepare_project,validate_exploration
from server.schema import Scene


def custom():
    return {'title':'齿轮实验','mode':'3d','duration':12,'objects':[
        {'id':'left','kind':'group','frames':[{'t':0,'rotation':0},{'t':12,'rotation':6}]},
        {'id':'right','kind':'group','frames':[{'t':0,'rotation':0},{'t':12,'rotation':-6}]},
        {'id':'l','kind':'cylinder','parent_id':'left'}, {'id':'r','kind':'cylinder','parent_id':'right'},
    ],'interactions':[dict(id='angle',label='主动轮角度',min=-180,max=180,value=0,step=1,
        bindings=[dict(target_id='left',property='rotation',multiplier=math.pi/180),dict(target_id='right',property='rotation',multiplier=-math.pi/180)],
        drag=dict(target_id='left',axis='horizontal',sensitivity=.5))]}


def test_coupled_control_preserves_opposite_gears_and_original_reset_defaults():
    scene=Scene.model_validate(custom());original=scene.model_dump()
    baked=bake_scene(scene,{'values':{'angle':90},'camera':{'azimuth':1,'elevation':.4,'distance':10,'orbit':0}})
    assert baked.objects[0].rotation==pytest.approx(math.pi/2)
    assert baked.objects[1].rotation==pytest.approx(-math.pi/2)
    assert baked.objects[0].frames[-1].rotation==pytest.approx(6+math.pi/2)
    assert baked.objects[1].frames[-1].rotation==pytest.approx(-6-math.pi/2)
    assert baked.interactions==[] and baked.camera.distance==10
    assert scene.model_dump()==original


def test_baking_clipped_offsets_inserts_crossing_to_preserve_middle_frame():
    scene=Scene.model_validate({'title':'透明度','objects':[{'id':'x','kind':'box','opacity':0,'frames':[{'t':0,'opacity':0},{'t':12,'opacity':1}]}],
        'interactions':[{'id':'fade','label':'透明度偏移','min':-.5,'max':.5,'value':0,'step':.1,'bindings':[{'target_id':'x','property':'opacity','multiplier':1}]}]})
    obj=bake_scene(scene,{'values':{'fade':.5}}).objects[0]
    assert [f.t for f in obj.frames]==[0,6,12]
    assert [f.opacity for f in obj.frames]==[.5,1,1]
    assert obj.opacity==.5


@pytest.mark.parametrize('mutate',[
    lambda d:d['interactions'][0]['bindings'][0].update(target_id='missing'),
    lambda d:d['interactions'][0]['bindings'][0].update(multiplier=0),
    lambda d:d['interactions'][0]['bindings'][0].update(multiplier=float('nan')),
    lambda d:d['interactions'][0]['bindings'][0].update(property='javascript'),
    lambda d:d['interactions'][0]['bindings'].append(copy.deepcopy(d['interactions'][0]['bindings'][0])),
    lambda d:d['interactions'][0]['drag'].update(target_id='l'),
    lambda d:d['interactions'][0].update(kind='toggle'),
    lambda d:d.update(evidence='computed'),
    lambda d:d['interactions'].append(copy.deepcopy(d['interactions'][0])),
])
def test_unsafe_or_unusable_interactions_are_rejected(mutate):
    scene=custom();mutate(scene)
    with pytest.raises(ValidationError):Scene.model_validate(scene)


def test_saturated_binding_and_text_drag_rejected():
    scene=custom();i=scene['interactions'][0]
    i.update(value=0,min=0,max=1,step=.1,bindings=[{'target_id':'left','property':'opacity','multiplier':1}])
    with pytest.raises(ValidationError,match='实际'):Scene.model_validate(scene)
    scene=custom();scene['objects'][2]['kind']='text'
    with pytest.raises(ValidationError,match='文字'):Scene.model_validate(scene)


def test_2d_can_drag_a_parameter_but_cannot_create_fake_depth():
    scene={'title':'位置','objects':[{'id':'marker','kind':'circle'}],'interactions':[{
        'id':'position','label':'位置','min':-3,'max':3,'value':0,'step':.1,
        'bindings':[{'target_id':'marker','property':'x','multiplier':1}],
        'drag':{'target_id':'marker','axis':'horizontal','sensitivity':.02}}]}
    assert Scene.model_validate(scene).interactions
    scene['interactions'][0]['bindings'][0]['property']='z'
    with pytest.raises(ValidationError,match='二维'):Scene.model_validate(scene)


def test_existing_fan_gets_meaningful_controls_without_overwriting_original():
    scene=build_scene(sample_proposal('fan')).model_dump();scene.pop('interactions')
    project={'id':'old','scene':scene,'proposal':{'recipe':'fan'}}
    ready=prepare_project(project)
    assert 'interactions' not in project['scene']
    assert ready['exploration']['values']=={'rotor-angle':0,'guards-visible':1}
    updated={**ready,'exploration':{'values':{'rotor-angle':45,'guards-visible':0},'camera':None}}
    baked=bake_scene(updated['scene'],updated['exploration'])
    nodes={o.id:o for o in baked.objects}
    assert nodes['front-guard'].opacity==0 and nodes['guard-shell'].opacity==0
    assert nodes['rotor'].frames[0].rotation==pytest.approx(math.pi/4)


def test_state_validation_rejects_unknown_out_of_range_and_fractional_toggle():
    scene=build_scene(sample_proposal('fan'))
    for values in ({'unknown':1},{'rotor-angle':181},{'guards-visible':.5}):
        with pytest.raises(ValueError):validate_exploration(scene,{'values':values})
    with pytest.raises(ValueError):validate_exploration(build_scene(sample_proposal('wave')),{'camera':{}})
    assert validate_exploration(scene,{'values':{'rotor-angle':.25}})['values']['rotor-angle']==.25
