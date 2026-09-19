import asyncio
import json
from types import SimpleNamespace

import pytest
import sympy as sp

from app.routers import solve
from app.solution_models import Solution, Visual, RenderRequest
from logic.solution_adaptation import parameter_expression, parse_solution, strategy_guidance, verify_parameter_analysis
from logic.solution_engine import local_solution, resolve_visual_functions


def parameter_solution(constraints=None, answer=None, variable='m'):
    payload = local_solution('x^2=1').model_dump()
    payload['parameter_analysis'] = {'variable':variable, 'constraints': constraints if constraints is not None else [
        {'label':'直线与圆无公共点','left':'abs(m)/sqrt(2)','relation':'>','right':'3'},
        {'label':'半径为正','left':'m','relation':'>','right':'0'},
        {'label':'圆心距大于半径差','left':'abs(1-m)','relation':'<','right':'5'},
        {'label':'圆心距小于半径和','left':'5','relation':'<','right':'1+m'},
    ], 'answer': answer if answer is not None else [{'lower':'3*sqrt(2)','upper':'6'}]}
    return Solution.model_validate(payload)


def test_geometry_conditions_have_exact_open_intersection():
    result = verify_parameter_analysis(parameter_solution())
    assert result.steps[-1].visual.kind == 'number_line'
    rows = result.steps[-1].visual.rows
    interval = rows[-1].intervals[0]
    assert interval.lower == pytest.approx(3*2**.5)
    assert interval.upper == 6
    assert not interval.lower_closed and not interval.upper_closed
    assert len(rows[0].intervals) == 2
    assert '3 \\sqrt{2}' in result.summary
    assert '题意到条件的转换由 AI' in result.verification
    RenderRequest(solution=result)


@pytest.mark.parametrize('answer', [
    [{'lower':'4','upper':'6'}],
    [{'lower':'3*sqrt(2)','upper':'6','lower_closed':True}],
    [{'lower':'3*sqrt(2)','upper':'6','upper_closed':True}],
])
def test_wrong_bounds_and_tangent_endpoints_are_rejected(answer):
    with pytest.raises(ValueError, match='交集'):
        verify_parameter_analysis(parameter_solution(answer=answer))


@pytest.mark.parametrize('constraints,answer', [
    ([{'label':'二次不等式','left':'t^2','relation':'<=','right':'4'}], [{'lower':'-2','upper':'2','lower_closed':True,'upper_closed':True}]),
    ([{'label':'等式','left':'t','relation':'=','right':'2'}], [{'lower':'2','upper':'2','lower_closed':True,'upper_closed':True}]),
    ([{'label':'绝对值','left':'abs(t)','relation':'>','right':'2'}], [{'upper':'-2'},{'lower':'2'}]),
    ([{'label':'条件一','left':'t','relation':'>','right':'3'},{'label':'条件二','left':'t','relation':'<','right':'1'}], []),
])
def test_other_variables_quadratics_singletons_unions_and_empty_sets(constraints,answer):
    result = verify_parameter_analysis(parameter_solution(constraints,answer,'t'))
    assert result.steps[-1].visual.kind == 'number_line'
    assert 't \\in' in result.summary


@pytest.mark.parametrize('text', [r'\frac{|m|}{\sqrt{2}}', 'abs(m)/sqrt(2)', r'\dfrac{\left|m\right|}{\sqrt{2}}'])
def test_tool_expression_conversion_preserves_math(text):
    m = sp.Symbol('m',real=True)
    assert parameter_expression(text,m) == sp.Abs(m)/sp.sqrt(2)


@pytest.mark.parametrize('text', ["__import__('os').system('echo nope')", 'm.__class__', 'm^12', 'sqrt(m)', 'sin(m)', '1/(m-1)'])
def test_tool_rejects_code_and_unsupported_conditions(text):
    with pytest.raises((ValueError, SyntaxError)):
        parameter_expression(text,sp.Symbol('m',real=True))


def test_circles_are_sampled_from_center_and_radius_with_equal_geometry_space():
    solution = local_solution('x^2=1')
    solution.steps[0].visual = Visual(kind='geometry',circles=[{'center':[-1,1],'radius':3,'label':'C'}],segments=[])
    result = resolve_visual_functions(solution)
    circle = result.steps[0].visual.curves[0]
    assert len(circle.points) == 161
    assert all((x+1)**2+(y-1)**2 == pytest.approx(9) for x,y in circle.points)
    assert result.steps[0].visual.kind == 'geometry'
    assert not result.steps[0].visual.circles
    RenderRequest(solution=result)


def test_fenced_model_json_is_read_without_rewriting_latex():
    original = parameter_solution()
    recovered = parse_solution('```json\n'+original.model_dump_json()+'\n```')
    assert recovered == original
    with pytest.raises(ValueError): parse_solution('{"steps":broken}')


def test_symbolic_radius_keeps_known_circle_and_does_not_invent_parameter():
    payload=parameter_solution().model_dump()
    payload['steps'][0]['visual']={'kind':'geometry','segments':[], 'circles':[
        {'center':['-1','1/2'],'radius':'sqrt(9)','label':'known'},
        {'center':[4,2],'radius':'m','label':'unknown'},
    ]}
    solution=parse_solution(json.dumps(payload))
    assert solution.steps[0].visual.circles[0].center == (-1,.5)
    assert solution.steps[0].visual.circles[0].radius == 3
    assert len(solution.steps[0].visual.circles) == 1
    assert '未确定参数' in solution.steps[0].visual.caption
    payload['steps'][0]['visual']['circles']=payload['steps'][0]['visual']['circles'][1:]
    solution=parse_solution(json.dumps(payload))
    assert solution.steps[0].visual.kind == 'reasoning'
    assert solution.parameter_analysis is not None


@pytest.mark.parametrize('problem,expected', [
    ('求直线与圆没有公共点时参数的范围','d>r'),
    ('求两圆相交时的取值范围','|r1-r2|<d<r1+r2'),
    ('求条件概率','有放回'),
    ('求数列通项','n=1'),
    ('求分式方程的解','增根'),
    ('求分段函数的导数','不可导点'),
    ('证明三角形结论','不能以个别数值图'),
])
def test_guidance_selects_relevant_methods(problem,expected):
    assert expected in strategy_guidance(problem)


def test_wrong_interval_triggers_model_repair_then_canonical_answer(monkeypatch):
    bad = parameter_solution(answer=[{'lower':'4','upper':'6'}])
    good = parameter_solution()
    responses = iter([bad,good]); calls=[]
    async def create(**kwargs):
        calls.append(json.loads(json.dumps(kwargs)))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=next(responses).model_dump_json()))])
    monkeypatch.setattr(solve,'ai_client',SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    result=asyncio.run(solve.ai_solution(solve.SolveRequest(problem='直线与圆和两圆相交，求参数范围')))
    assert len(calls)==2
    assert '交集' in calls[1]['messages'][-1]['content']
    assert result.steps[-1].visual.kind=='number_line'
    assert '3 \\sqrt{2}' in result.summary
