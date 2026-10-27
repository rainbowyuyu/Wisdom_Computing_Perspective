import math

import numpy as np
import pytest

from server.builders import build_scene, sample_proposal
from server.extended_builders import queue_schedule
from server.schema import Proposal


def make(recipe, **parameters):
    return build_scene(Proposal(title='Trusted calculation', recipe=recipe, parameters=parameters))


def nodes(scene):
    return {item.id: item for item in scene.objects}


@pytest.mark.parametrize('recipe', ['riemann', 'refraction', 'queue'])
def test_new_samples_are_deterministic_computed_scenes_with_trusted_controls(recipe):
    scene = build_scene(sample_proposal(recipe))
    assert scene.evidence == 'computed' and scene.controls and not scene.interactions
    assert scene.selection.engine == 'canvas2d'
    assert scene.model_dump() == build_scene(sample_proposal(recipe)).model_dump()
    assert all(item.kind in {'circle', 'rect', 'line', 'arrow', 'path', 'text', 'formula'} for item in scene.objects)


@pytest.mark.parametrize('upper,count,alpha', [(.5, 4, 0), (2, 8, .5), (3, 40, 1)])
def test_riemann_geometry_encodes_the_exact_rectangle_sum(upper, count, alpha):
    data = nodes(make('riemann', upper=upper, count=count, sample_position=alpha))
    rectangles = [data[f'rectangle-{i}'] for i in range(count)]
    # Screen scales are fixed: 3.6 horizontally and .52 vertically.
    area = sum(item.width*item.height/(3.6*.52) for item in rectangles if item.frames[-1].opacity > 0)
    expected = sum(((i+alpha)*upper/count)**2*upper/count for i in range(count))
    assert area == pytest.approx(expected, abs=1e-12)
    for i in range(count):
        sample = data[f'sample-{i}']
        physical_x = (sample.x+5.7)/3.6
        assert physical_x == pytest.approx((i+alpha)*upper/count)
        assert (sample.y+2.5)/.52 == pytest.approx(physical_x**2)
    assert f'{upper**3/3:.5f}' in data['area-readout'].text


def test_midpoint_riemann_error_quarters_when_splitting_count_doubles():
    def area(count):
        return sum(o.width*o.height/(3.6*.52) for o in make('riemann', upper=2, count=count).objects if o.id.startswith('rectangle-'))
    exact = 8/3
    assert (exact-area(8))/(exact-area(16)) == pytest.approx(4)
    with pytest.raises(ValueError, match='整数'): make('riemann', count=4.5)


@pytest.mark.parametrize('n1,n2,angle', [(1, 1.5, 35), (1.5, 1, 25), (2.4, 2.4, 80), (1, 2.4, 0)])
def test_refraction_rays_satisfy_snell_and_reflection_geometry(n1, n2, angle):
    data = nodes(make('refraction', n1=n1, n2=n2, angle=angle))
    endpoint = data['transmitted-ray'].points[-1]
    sine = endpoint[0]/math.hypot(*endpoint)
    assert n2*sine == pytest.approx(n1*math.sin(math.radians(angle)), abs=1e-12)
    incident = data['incident-ray'].points[0]
    if n1 != n2:
        reflected = data['reflected-ray'].points[-1]
        assert reflected == pytest.approx([-incident[0], incident[1]], abs=1e-12)
    else:
        assert 'reflected-ray' not in data and 'reflection-marker' not in data
        assert endpoint == pytest.approx([-incident[0], -incident[1]], abs=1e-12)
        assert '直线透射' in data['critical-readout'].text


def test_total_internal_reflection_removes_propagating_transmission_but_critical_ray_remains():
    critical = math.degrees(math.asin(1/1.5))
    data = nodes(make('refraction', n1=1.5, n2=1, angle=critical))
    assert data['transmitted-ray'].points[-1] == pytest.approx([2.7, 0], abs=1e-7)
    beyond = nodes(make('refraction', n1=1.5, n2=1, angle=critical+.01))
    assert 'transmitted-ray' not in beyond and 'transmission-marker' not in beyond
    assert '全反射' in beyond['result'].text


def test_queue_event_schedule_matches_independent_closed_form_for_stable_and_overloaded_cases():
    for arrival, service in [(.6, 2.4), (3, .4), (1.2, 1.8), (1.5, 1.5), (.7, 1.1)]:
        jobs = queue_schedule(arrival, service)
        for i, job in enumerate(jobs):
            assert job['arrival'] == pytest.approx(i*arrival, abs=1e-10)
            assert job['start'] == pytest.approx(i*max(arrival, service), abs=1e-10)
            assert job['end'] == pytest.approx(i*max(arrival, service)+service, abs=1e-10)
            assert job['wait'] == pytest.approx(i*max(0, service-arrival), abs=1e-10)
        assert jobs[-1]['arrival'] <= 24 and jobs[-1]['arrival']+arrival > 24


def test_queue_customer_state_at_event_keeps_waiting_serving_and_completed_counts():
    scene = make('queue', arrival=.6, service=2.4)
    data = nodes(scene)
    jobs = queue_schedule(.6, 2.4)
    customers = [data[f'customer-{i}'] for i in range(len(jobs))]
    for physical_time in [0, .6, 2.4, 4.8, 12, 24]:
        rendered = []
        for item in customers:
            frame = max((f for f in item.frames if f.t <= physical_time/24*scene.duration+1e-12), key=lambda f:f.t)
            if frame.opacity > .5: rendered.append('wait' if frame.x < -2 else 'done' if frame.x > 2 else 'serve')
        expected = ['done' if j['end'] <= physical_time+1e-10 else 'serve' if j['start'] <= physical_time+1e-10 else 'wait'
                    for j in jobs if j['arrival'] <= physical_time+1e-10]
        assert {key:rendered.count(key) for key in ['wait','serve','done']} == {key:expected.count(key) for key in ['wait','serve','done']}
    assert '完成 10' in data['queue-readout'].text and '等待 30' in data['queue-readout'].text
    assert all(abs(f.x) <= 6.3 and -1.2 <= f.y <= 1.3 for item in customers for f in item.frames)


def test_function_multiplier_changes_geometry_on_a_stable_reference_scale():
    low, high = nodes(make('function', amplitude=1)), nodes(make('function', amplitude=3))
    np.testing.assert_allclose(np.array(high['curve-0'].points)[:,1], np.array(low['curve-0'].points)[:,1]*3, atol=1e-12)
    assert low['domain'].text == high['domain'].text
    clipped = nodes(build_scene(Proposal(title='pole', recipe='function', expression='1/x', parameters={'amplitude':4})))
    assert '超范围' in clipped['domain'].text
    assert all(not (min(p[0] for p in o.points)<0<max(p[0] for p in o.points)) for o in clipped.values() if o.id.startswith('curve-'))
    large_base = build_scene(Proposal(title='large constant', recipe='function', expression='100000', parameters={'amplitude':.1}))
    assert any(o.id == 'curve-0' for o in large_base.objects)


def test_projectile_keeps_a_fixed_physical_reference_without_cutting_extreme_trajectories():
    low, high = nodes(make('projectile', speed=10)), nodes(make('projectile', speed=20))
    def relative_range(data):
        return (data['trajectory'].points[-1][0]+5.5)/(data['reference-trajectory'].points[-1][0]+5.5)
    assert relative_range(high)/relative_range(low) == pytest.approx(4)
    assert low['trajectory'].points != high['trajectory'].points
    for parameters in [{'speed':30,'angle':10,'gravity':.5}, {'speed':1,'angle':80,'gravity':20}]:
        data = nodes(make('projectile', **parameters))
        for ident in ['trajectory','reference-trajectory']:
            assert all(-5.500001 <= x <= 5.500001 and -2.500001 <= y <= 2.300001 for x,y in data[ident].points)


@pytest.mark.parametrize('recipe,parameters', [('riemann',{'upper':3.1}),('riemann',{'count':41}),
    ('riemann',{'sample_position':-1}),('refraction',{'n1':.9}),('refraction',{'angle':81}),
    ('queue',{'arrival':.5}),('queue',{'service':2.5}),('queue',{'horizon':30})])
def test_extended_controls_reject_unsupported_or_invalid_parameters(recipe,parameters):
    with pytest.raises(ValueError): make(recipe,**parameters)
