import asyncio
import json
from types import SimpleNamespace

import pytest
import sympy as sp
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import solve
from app.solution_models import ExactInterval, ParameterAnalysis, RenderRequest, SolveRequest, Visual
from app.routers.solution_library import SavedSolution
from logic.solution_engine import local_solution, resolve_visual_functions
from logic.solution_adaptation import verify_parameter_analysis
from logic.task_planning import solve_subtask

PROBLEM = '已知抛物线y=x^2+2x+m与x轴交于A、B两点，求以线段AB为直径的圆的方程。'


@pytest.mark.parametrize('problem', [PROBLEM, PROBLEM.replace('^2','²'),
    PROBLEM.replace('y=x^2+2x+m', r'$y=x^{2}+2x+m$'),
    PROBLEM.replace('x轴','横轴').replace('A、B','P、Q').replace('AB','PQ')])
def test_symbolic_circle_answer_is_not_a_missing_parameter(problem):
    result = local_solution(problem)
    assert result and result.completion == 'solved'
    assert '1 - m' in result.summary and 'm < 1' in result.summary
    assert r'\left(x + 1\right)^{2}' in result.steps[-1].formula
    assert result.source == 'sympy'
    assert all(s.visual.kind == 'reasoning' for s in result.steps)
    assert len(result.steps) == 6
    RenderRequest(solution=result)
    SavedSolution(problem=problem, solution=result)


@pytest.mark.parametrize('curve,line,endpoints,center,r2', [
    ('x^2+2x-3','x轴',[(-3,0),(1,0)],(-1,0),4),
    ('2x^2-4x-6','x轴',[(-1,0),(3,0)],(1,0),4),
    ('-x^2+4','x轴',[(-2,0),(2,0)],(0,0),4),
    ('x^2','直线y=x+2',[(-1,1),(2,4)],(.5,2.5),4.5),
    ('x^2','直线y=4',[(-2,4),(2,4)],(0,4),4),
])
def test_changed_data_produces_real_geometry(curve,line,endpoints,center,r2):
    result = local_solution(f'已知抛物线y={curve}与{line}交于A、B两点，求以线段AB为直径的圆的方程。')
    assert result and result.completion == 'solved'
    visual = result.steps[-1].visual
    assert visual.points[:2] == endpoints
    assert visual.points[2] == center
    circle = next(c for c in visual.curves if c.label == '直径圆')
    assert all((x-center[0])**2+(y-center[1])**2 == pytest.approx(r2) for x,y in circle.points)
    assert all((x-center[0])**2+(y-center[1])**2 == pytest.approx(r2) for x,y in endpoints)
    assert not any(c.label == '直径圆' for c in result.steps[0].visual.curves)
    RenderRequest(solution=result)


@pytest.mark.parametrize('constant', ['1', '2'])
def test_tangent_and_disjoint_parabolas_do_not_invent_a_circle(constant):
    result = local_solution(PROBLEM.replace('+m', '+'+constant))
    assert '不存在' in result.summary
    assert all(not s.visual.circles for s in result.steps)


@pytest.mark.parametrize('change', [lambda p:p+'另求圆面积。', lambda p:p.replace('x轴','y轴'),
    lambda p:p.replace('x^2','x^3'), lambda p:p.replace('x^2','a*x^2'), lambda p:p.replace('求以','当m=0时，求以'),
    lambda p:p.replace('+m','+(m-1)/(m-1)'), lambda p:p.replace('+m','+x*x^(-1)')])
def test_unknown_or_additional_conditions_fall_back_without_truncating(change):
    assert local_solution(change(PROBLEM)) is None


@pytest.mark.parametrize('problem,answer', [
    ('(x+1)/(x-1)=2', sp.FiniteSet(3)),
    ('(x+1)/(x+2)=3', sp.FiniteSet(sp.Rational(-5,2))),
    ('(x^2-1)/(x-1)=2', sp.S.EmptySet),
    ('x/x*x=0', sp.S.EmptySet),
    ('1/x=0', sp.S.EmptySet),
    ('x/x=1', sp.S.Reals-sp.FiniteSet(0)),
    ('1/(1/x)=x', sp.S.Reals-sp.FiniteSet(0)),
    ('(x^2-1)/(x-1)=x+1', sp.S.Reals-sp.FiniteSet(1)),
])
def test_rational_equations_preserve_original_domain(problem,answer):
    result = local_solution(problem)
    assert result and result.steps[-1].formula == r'x\in '+sp.latex(answer)
    assert result.source == 'sympy'
    RenderRequest(solution=result)


def domain_solution(purpose='domain'):
    result = local_solution(PROBLEM)
    result.parameter_analysis = ParameterAnalysis(purpose=purpose, variable='m',
        constraints=[{'label':'两个不同实交点','left':'4-4*m','relation':'>','right':'0'}], answer=[{'upper':'1'}])
    return result


@pytest.mark.parametrize('purpose', ['domain','answer'])
def test_parameter_tool_does_not_overwrite_other_requested_answers(purpose):
    original = domain_solution(purpose)
    result = verify_parameter_analysis(original.model_copy(deep=True), PROBLEM)
    assert result.summary == original.summary
    assert result.steps[-1] == original.steps[-1]
    assert result.parameter_analysis.purpose == 'domain'


def test_wrong_domain_still_requires_correction():
    result = domain_solution()
    result.parameter_analysis.answer[0].upper_closed = True
    with pytest.raises(ValueError,match='交集'):
        verify_parameter_analysis(result, PROBLEM)


@pytest.mark.parametrize('lower,upper', [(r'-\infty',r'\infty'),('-∞','+∞'),('-inf','inf'),('-oo','oo')])
def test_common_infinity_notation_does_not_discard_a_valid_solution(lower,upper):
    interval = ExactInterval(lower=lower, upper=upper, lower_closed=True, upper_closed=True)
    assert interval.lower is None and interval.upper is None
    assert not interval.lower_closed and not interval.upper_closed
    result = domain_solution()
    result.parameter_analysis.answer = [ExactInterval(lower=lower,upper='1')]
    assert verify_parameter_analysis(result, PROBLEM).completion == 'solved'


def test_reversed_infinity_and_invalid_expressions_are_actionable():
    from logic.solution_adaptation import parameter_expression
    with pytest.raises(ValueError, match='区间方向'):
        ExactInterval(lower='inf',upper='1')
    with pytest.raises(ValueError, match='普通数学文本'):
        parameter_expression('m < 1', sp.Symbol('m',real=True))


def test_unassigned_parameter_cannot_be_replaced_by_an_arbitrary_plot():
    result = domain_solution()
    result.steps[0].visual = Visual(kind='geometry', circles=[{'center':[-1,0],'radius':1,'label':'固定已知圆'}])
    result.steps[0].formula = r'O=(-1,0),\ r=1'
    result.steps[-1].visual = Visual(kind='plot',functions=[{'expression':'x^2+2*x+0.5'}], caption='取 m=0.5 展示')
    result = verify_parameter_analysis(result, PROBLEM)
    assert result.steps[0].visual.kind == 'geometry'
    assert result.steps[-1].visual.kind == 'reasoning'
    assert '1 - m' in result.steps[-1].formula


def test_ai_pipeline_keeps_symbolic_answer_even_with_parameter_tool(monkeypatch):
    original = domain_solution('answer')
    async def create(**_):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=original.model_dump_json()))])
    monkeypatch.setattr(solve, 'ai_client', SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    result = asyncio.run(solve.ai_solution(SolveRequest(problem=PROBLEM)))
    assert result.summary == original.summary
    assert result.steps[-1].formula == original.steps[-1].formula


def test_optional_symbolic_function_does_not_erase_known_circle():
    result = local_solution(PROBLEM)
    result.steps[-1].visual = Visual(kind='geometry', circles=[{'center':[0,0],'radius':2,'label':'C'}],
        functions=[{'expression':'x^2'},{'expression':'x+m'}], segments=[])
    resolved = resolve_visual_functions(result)
    assert len(resolved.steps[-1].visual.curves) == 2
    assert resolved.steps[-1].visual.curves[0].label == 'C'
    assert '参数' in resolved.steps[-1].visual.caption
    RenderRequest(solution=resolved)


def test_tutor_and_agent_use_same_exact_answer_without_ai(monkeypatch):
    monkeypatch.setattr(solve, 'api_key', None)
    app = FastAPI()
    app.include_router(solve.router)
    with TestClient(app) as client:
        response = client.post('/solve/stream', json={'problem':PROBLEM})
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[-1]['type'] == 'complete'
    assert events[-1]['solution']['source'] == 'sympy'
    node = {'goal':'完整求解','depends_on':[]}
    result = asyncio.run(solve_subtask({'problem':PROBLEM, 'context':'', 'nodes':[node]}, node))
    assert result.summary == events[-1]['solution']['summary']
