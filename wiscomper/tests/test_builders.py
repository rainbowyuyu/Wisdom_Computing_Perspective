import math

import numpy as np
import pytest

from server.builders import SAMPLES, build_scene, evaluate_expression, sample_proposal
from server.schema import Proposal


def objects(scene):return {obj.id:obj for obj in scene.objects}


@pytest.mark.parametrize('sample',[sample['id'] for sample in SAMPLES])
@pytest.mark.parametrize('duration',[6,12,30,45,6.123456789])
def test_all_trusted_samples_fit_contract(sample,duration):
    scene=build_scene(sample_proposal(sample,duration))
    assert scene.duration==duration
    assert all(obj.frames[-1].t<=duration for obj in scene.objects if obj.frames)
    assert sum(len(obj.frames) for obj in scene.objects)<=60000


@pytest.mark.parametrize('expression',[
    '__import__("os").system("echo unsafe")','().__class__','x[0]','[x for x in [1]]',
    '(lambda:1)()','open("secret")','sin(x,where=True)','x**100','True','1e100',
    'x;'+'0'*300,
])
def test_expression_rejects_code_and_unbounded_operations(expression):
    with pytest.raises(ValueError):evaluate_expression(expression,np.linspace(-1,1,10))


def test_expression_supported_math_matches_numpy():
    x=np.linspace(.1,2,20)
    np.testing.assert_allclose(evaluate_expression('sin(x)^2+cos(x)^2+log(x)+sqrt(x)',x),1+np.log(x)+np.sqrt(x))
    np.testing.assert_allclose(evaluate_expression('y=3',x),np.full_like(x,3))


def test_function_sparse_domain_and_discontinuities():
    sparse=build_scene(Proposal(title='sparse',recipe='function',expression='sqrt(x-0.099)',parameters={'xmin':0,'xmax':.1}))
    assert any(o.id.startswith('curve') for o in sparse.objects)
    scene=build_scene(Proposal(title='pole',recipe='function',expression='1/x'))
    for obj in scene.objects:
        if obj.id.startswith('curve'):
            assert not (min(p[0] for p in obj.points)<0<max(p[0] for p in obj.points))
    point=objects(scene)['moving-point']
    assert next(frame for frame in point.frames if frame.t==6).opacity==0


@pytest.mark.parametrize('parameters',[{'speed':12,'angle':45,'gravity':9.81},{'speed':30,'angle':10,'gravity':.5},{'speed':1,'angle':80,'gravity':20}])
def test_projectile_physics_and_draw_head_match_motion(parameters):
    scene=build_scene(Proposal(title='projectile',recipe='projectile',parameters=parameters))
    data=objects(scene);path=data['trajectory'];ball=data['ball']
    v,theta,g=parameters['speed'],math.radians(parameters['angle']),parameters['gravity']
    flight=2*v*math.sin(theta)/g;reach=v*math.cos(theta)*flight
    scale=(path.points[-1][0]-path.points[0][0])/reach
    for frame in ball.frames:
        t=frame.t/scene.duration*flight
        assert frame.x==pytest.approx(-5.5+scale*v*math.cos(theta)*t,abs=1e-10)
        assert frame.y==pytest.approx(-2.5+scale*(v*math.sin(theta)*t-g*t*t/2),abs=1e-10)
    distances=np.r_[0,np.cumsum(np.linalg.norm(np.diff(np.array(path.points),axis=0),axis=1))]
    np.testing.assert_allclose([f.draw for f in path.frames],distances/distances[-1],atol=1e-12)
    assert [f.t for f in path.frames]==[f.t for f in ball.frames]
    # Any linear interpolation between two keys therefore shares the same path head.
    index=37;u=.37;fraction=path.frames[index].draw*(1-u)+path.frames[index+1].draw*u
    head=np.array(path.points[index])+(np.array(path.points[index+1])-path.points[index])*(fraction*distances[-1]-distances[index])/(distances[index+1]-distances[index])
    target=np.array([ball.frames[index].x,ball.frames[index].y])*(1-u)+np.array([ball.frames[index+1].x,ball.frames[index+1].y])*u
    np.testing.assert_allclose(head,target,atol=1e-12)


def test_nonlinear_pendulum_period_and_geometric_constraint():
    length=.5;angle=60
    scene=build_scene(Proposal(title='pendulum',recipe='pendulum',duration=30,parameters={'length':length,'angle':angle,'damping':0}))
    data=objects(scene);bob=data['bob'];rod=data['rod']
    theta=np.array([f.rotation for f in rod.frames]);times=np.array([f.t for f in rod.frames])
    # Independent elliptic-integral period for the nonlinear undamped pendulum.
    phi=np.linspace(0,math.pi/2,10001);k=math.sin(math.radians(angle)/2)
    expected=4*math.sqrt(length/9.81)*np.trapezoid(1/np.sqrt(1-k*k*np.sin(phi)**2),phi)
    crossings=[]
    for i in range(len(theta)-1):
        if theta[i]>0>=theta[i+1]:crossings.append(times[i]+(times[i+1]-times[i])*theta[i]/(theta[i]-theta[i+1]))
    assert np.mean(np.diff(crossings))==pytest.approx(expected,abs=.001)
    positions=np.array([[f.x,f.y] for f in bob.frames])
    np.testing.assert_allclose(np.linalg.norm(positions-[0,2.3],axis=1),length*1.5,atol=1e-10)
    mid_theta=(theta[:-1]+theta[1:])/2
    rod_tip=np.c_[length*1.5*np.sin(mid_theta),2.3-length*1.5*np.cos(mid_theta)]
    assert np.max(np.linalg.norm((positions[:-1]+positions[1:])/2-rod_tip,axis=1))<.005


def test_pendulum_damping_reduces_late_amplitude():
    scene=build_scene(Proposal(title='damped',recipe='pendulum',duration=20,parameters={'damping':.8}))
    rod=objects(scene)['rod']
    assert max(abs(f.rotation) for f in rod.frames if f.t>15)<.01


def test_high_frequency_long_wave_has_resolved_time_sampling():
    amplitude,frequency=2,1.5
    scene=build_scene(Proposal(title='wave',recipe='wave',duration=45,parameters={'amplitude':amplitude,'frequency':frequency,'wavelength':1}))
    particle=objects(scene)['particle-27']
    assert len(particle.frames)==901
    for a,b in zip(particle.frames,particle.frames[1:]):
        t=(a.t+b.t)/2
        exact=amplitude*math.sin(2*math.pi*(particle.x-frequency*t))
        assert abs((a.y+b.y)/2-exact)<.056
        assert b.t-a.t<=.050001
    assert all(frame.x is None for frame in particle.frames)


@pytest.mark.parametrize('omega',[-1.5,0,1.5])
def test_field_particles_share_velocity_direction_and_keep_radius(omega):
    scene=build_scene(Proposal(title='field',recipe='field',duration=30,parameters={'omega':omega}))
    first=objects(scene)['particle-0'];frames=first.frames
    np.testing.assert_allclose([math.hypot(f.x,f.y) for f in frames],.5,atol=1e-12)
    assert frames[1].y==pytest.approx(.5*math.sin(omega*frames[1].t),abs=1e-12)
    if omega==0:assert not any(o.kind=='arrow' for o in scene.objects)


def test_diagram_eight_nodes_have_forward_edges_and_single_node_is_centered():
    scene=build_scene(Proposal(title='eight',recipe='diagram',labels=['说明'*32]*8))
    assert all(o.points[1][0]>o.points[0][0] for o in scene.objects if o.kind=='arrow')
    assert all(len(o.text)<=5 and len(o.label)==64 for o in scene.objects if o.kind=='text')
    one=objects(build_scene(Proposal(title='one',recipe='diagram',labels=['一个对象'])))
    assert one['node-0'].x==0


@pytest.mark.parametrize('recipe,parameters',[
    ('projectile',{'gravity':0}),('projectile',{'speed':31}),('pendulum',{'length':0}),
    ('pendulum',{'angle':61}),('wave',{'frequency':1.6}),('wave',{'wavelength':0}),
    ('field',{'omega':2}),('function',{'unsupported':1}),('diagram',{'unused':1}),
])
def test_out_of_range_or_ineffective_parameters_are_rejected(recipe,parameters):
    with pytest.raises(ValueError):build_scene(Proposal(title='invalid',recipe=recipe,parameters=parameters))


def test_long_valid_proposal_keeps_required_assumptions_and_bounded_steps():
    scene=build_scene(Proposal(title='full',recipe='formula',formula='x=1',summary='说明'*500,assumptions=[f'条件{i}' for i in range(12)]))
    assert len(scene.assumptions)==12 and '不自动证明' in scene.assumptions[-1]
    assert all(len(step.explanation)<=600 for step in scene.steps)
