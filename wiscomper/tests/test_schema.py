import pytest
from pydantic import ValidationError

from server.schema import Control, Proposal, Scene


def minimal(**updates):return {'title':'scene','objects':[{'id':'point','kind':'circle'}],**updates}


@pytest.mark.parametrize('values',[
    {'min':1,'max':1,'value':1,'step':.1},
    {'min':2,'max':1,'value':1,'step':.1},
    {'min':0,'max':1,'value':2,'step':.1},
    {'min':0,'max':1,'value':.5,'step':2},
    {'min':0,'max':1,'value':float('nan'),'step':.1},
])
def test_controls_require_usable_finite_ranges(values):
    with pytest.raises(ValidationError):Control(id='p',label='parameter',**values)


def test_scene_strings_parameters_and_control_ids_are_bounded():
    with pytest.raises(ValidationError):Scene.model_validate(minimal(assumptions=['a'*201]))
    with pytest.raises(ValidationError):Proposal(title='test',recipe='diagram',parameters={'a'*65:1})
    control={'id':'p','label':'p','value':0,'min':-1,'max':1,'step':.1}
    with pytest.raises(ValidationError):Scene.model_validate(minimal(controls=[control,control]))
    with pytest.raises(ValidationError):Scene.model_validate(minimal(camera={'elevation':2}))


def test_trusted_tracks_can_be_dense_but_model_tracks_remain_small():
    scene=minimal(duration=45,objects=[{'id':'point','kind':'circle','frames':[{'t':i/20,'x':i/100} for i in range(901)]}])
    assert len(Scene.model_validate(scene).objects[0].frames)==901
    with pytest.raises(ValidationError):Proposal(title='test',recipe='custom',duration=45,scene=scene)
    definitions=Proposal.model_json_schema()['$defs']
    assert definitions['ModelVisualObject']['properties']['frames']['maxItems']==180
    assert definitions['ModelScene']['properties']['controls']['maxItems']==0


def test_total_scene_track_budget_is_enforced():
    frames=[{'t':i/20} for i in range(901)]
    with pytest.raises(ValidationError,match='总量'):
        Scene.model_validate(minimal(duration=45,objects=[{'id':f'o{i}','kind':'circle','frames':frames} for i in range(67)]))


def test_unknown_fields_duplicate_times_and_nonfinite_geometry_rejected():
    for obj in [
        {'id':'p','kind':'circle','javascript':'alert(1)'},
        {'id':'p','kind':'circle','frames':[{'t':1},{'t':1}]},
        {'id':'p','kind':'path','points':[[0,0],[1,float('inf')]]},
        {'id':'p','kind':'path','points':[[0,0,0,0],[1,1]]},
    ]:
        with pytest.raises(ValidationError):Scene.model_validate(minimal(objects=[obj]))


def test_spatial_assembly_supports_local_axes_and_valid_parent():
    scene=Scene.model_validate(minimal(mode='3d',selection={'engine':'threejs','category':'mechanism','reason':'观察装配关系'},objects=[
        {'id':'blade','kind':'prism','parent_id':'rotor','points':[[0,0],[2,0],[1,1]],'depth':.2,'rotation_y':.3},
        {'id':'rotor','kind':'group','frames':[{'t':0,'rotation':0},{'t':12,'rotation':12,'rotation_x':.1}]},
        {'id':'housing','kind':'torus','radius':2,'tube_radius':.1},
    ]))
    assert scene.objects[0].parent_id=='rotor'


@pytest.mark.parametrize('objects',[
    [{'id':'a','kind':'group','parent_id':'a'}],
    [{'id':'a','kind':'group','parent_id':'b'},{'id':'b','kind':'group','parent_id':'a'}],
    [{'id':'a','kind':'box','parent_id':'missing'}],
    [{'id':'a','kind':'box','parent_id':'b'},{'id':'b','kind':'group','parent_id':'missing'}],
    [{'id':'a','kind':'box'},{'id':'b','kind':'box','parent_id':'a'}],
    [{'id':'a','kind':'prism','points':[[0,0],[1,0],[2,0]]}],
    [{'id':'a','kind':'prism','points':[[0,0,0],[1,0,0],[0,1,0]]}],
    [{'id':'a','kind':'torus','radius':1,'tube_radius':2}],
])
def test_invalid_assemblies_rejected(objects):
    with pytest.raises(ValidationError):Scene.model_validate(minimal(mode='3d',objects=objects))


@pytest.mark.parametrize('obj',[
    {'id':'a','kind':'prism','points':[[0,0],[1,0],[1,1]]},
    {'id':'a','kind':'group'},
    {'id':'a','kind':'circle','rotation_y':1},
    {'id':'a','kind':'box','frames':[{'t':1,'rotation_x':.5}]},
])
def test_2d_cannot_silently_ignore_spatial_features(obj):
    with pytest.raises(ValidationError,match='三维'):Scene.model_validate(minimal(objects=[obj]))


def test_selected_renderer_matches_scene_dimension():
    with pytest.raises(ValidationError,match='工具'):
        Scene.model_validate(minimal(selection={'engine':'threejs','category':'mechanism','reason':'三维'}))


@pytest.mark.parametrize('recipe',['fan','model3d','diagram'])
def test_clarification_cannot_be_built_as_a_finished_model(recipe):
    from server.builders import build_scene
    with pytest.raises(ValueError,match='请补充目标'):
        build_scene(Proposal(title='未确定',recipe=recipe,needs_clarification=True,question='请补充目标'))
