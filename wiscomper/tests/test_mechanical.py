import math

import pytest

from server.builders import build_scene
from server.mechanical import build_fan
from server.schema import Proposal


def proposal(**values):
    return Proposal(title='风机如何推动空气', recipe='fan', **values)


def table(scene):return {obj.id:obj for obj in scene.objects}


@pytest.mark.parametrize('duration',[6,6.123456789,12,30,45])
def test_fan_has_thick_pitched_blades_and_stable_parent_structure(duration):
    scene=build_fan(proposal(duration=duration))
    objects=table(scene)
    assert scene.mode=='3d' and scene.evidence=='schematic'
    blades=[o for o in scene.objects if o.kind=='prism']
    assert len(blades)==5
    assert all(o.depth>.1 and o.rotation_x==pytest.approx(math.radians(20)) for o in blades)
    assert all(o.filled and len(o.points)>=8 for o in blades)
    assert all(objects[o.parent_id].parent_id=='rotor' for o in blades)
    assert objects['hub'].parent_id=='rotor'
    assert objects['front-guard'].parent_id==objects['motor'].parent_id=='stationary'
    assert objects['stationary'].frames==[]
    assert objects['rotor'].frames[0].rotation==0
    assert objects['rotor'].frames[-1].rotation>math.tau
    assert all(frame.t<=duration for o in scene.objects for frame in o.frames)
    assert any(o.kind=='torus' and o.filled for o in scene.objects)
    assert any(o.kind=='cone' and o.filled for o in scene.objects)
    assert all(o.filled for o in scene.objects)
    assert '教学慢放' in ' '.join(scene.assumptions) and '不是 CFD' in ' '.join(scene.assumptions)


def test_fan_parameters_change_geometry_rotation_and_qualitative_flow():
    slow=table(build_fan(proposal(parameters={'speed':.1,'pitch':0,'explode':0})))
    fast=table(build_fan(proposal(parameters={'speed':1,'pitch':40,'explode':2.5})))
    assert fast['rotor'].frames[-1].rotation==pytest.approx(slow['rotor'].frames[-1].rotation*10)
    assert slow['blade-0'].rotation_x==0
    assert fast['blade-0'].rotation_x==pytest.approx(math.radians(40))
    assert fast['front-guard'].frames[-1].z>slow['front-guard'].frames[-1].z+2
    assert fast['motor'].frames[-1].z<slow['motor'].frames[-1].z-1
    assert slow['airflow'].frames[-1].opacity==0
    assert fast['airflow'].frames[-1].opacity>.7
    # Rotation is attached only to the actual assembly, so cage/stand cannot spin.
    assert not any(f.rotation for f in fast['front-guard'].frames)
    assert not any(f.rotation for f in fast['motor'].frames)


def test_fan_builder_route_has_tool_selection_and_usable_controls():
    scene=build_scene(proposal())
    assert scene.selection.engine=='threejs'
    assert {c.id:c.value for c in scene.controls}=={'speed':.5,'pitch':20,'explode':0}
    assert all(c.min<=c.value<=c.max for c in scene.controls)
    assert scene.steps[0].focus and scene.steps[-1].focus==['airflow','rotor']


@pytest.mark.parametrize('parameters',[{'speed':0},{'speed':1.01},{'pitch':-1},{'pitch':41},{'explode':2.51},{'rpm':500}])
def test_fan_rejects_unsupported_or_out_of_bounds_parameters(parameters):
    with pytest.raises(ValueError):build_fan(proposal(parameters=parameters))


def test_flow_particle_recycling_happens_only_when_hidden():
    scene=build_fan(proposal(duration=30,parameters={'speed':1,'pitch':40}))
    for particle in [o for o in scene.objects if o.id.startswith('air-particle')]:
        for left,right in zip(particle.frames,particle.frames[1:]):
            if right.z<left.z:
                assert left.opacity==right.opacity==0
                assert right.t-left.t<.001
