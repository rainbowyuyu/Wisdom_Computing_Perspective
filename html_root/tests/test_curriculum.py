import json
import re

import pytest
import sympy as sp
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import solve
from app.solution_models import RenderRequest
from app.routers.solution_library import SavedSolution
from logic.curriculum import EXAMPLES, exact_example, worked_solution, study_advice, teaching_context
from logic.manim_tex import normalize_tex
from app.usage_guard import identity
from app.solution_models import SolveRequest


@pytest.mark.parametrize('item', EXAMPLES, ids=lambda e:e['id'])
def test_every_example_is_complete_renderable_and_storable(item):
    solution = worked_solution(item)
    assert solution.source == 'curriculum'
    assert 3 <= len(solution.steps) <= 5
    assert exact_example(item['problem']).summary == solution.summary
    for step in solution.steps:
        assert step.explanation and step.formula and step.hint
        normalize_tex(step.formula)
    RenderRequest(solution=solution)
    # Same shape consumed by my formulas, wrongbook and course material snapshots.
    SavedSolution(problem=item['problem'], solution=solution)


@pytest.mark.parametrize('item', EXAMPLES, ids=lambda e:e['id'])
def test_changed_or_extra_conditions_never_reuse_example_answers(item):
    assert exact_example(item['problem']+' 另外要求x>100。') is None
    changed = re.sub(r'[0-9]', lambda m: str((int(m[0])+1)%10), item['problem'], count=1)
    if changed == item['problem']:
        changed = item['problem'].replace('x', 't', 1)
    assert changed != item['problem']
    assert exact_example(changed) is None


def test_answers_against_independent_exact_calculations():
    x,y=sp.symbols('x y', real=True)
    assert sp.solve(x*x-5*x+6,x)==[2,3]
    assert sp.solve_univariate_inequality(abs(2*x-1)<3,x,relational=False)==sp.Interval.open(-1,2)
    assert sp.solve((x+1)/(x-1)-2,x)==[3]
    assert [r for r in sp.solve((x-1)*(x-3)-8,x) if r>3]==[5]
    assert sp.solveset(sp.sin(x)-sp.Rational(1,2),x,sp.Interval(0,2*sp.pi))==sp.FiniteSet(sp.pi/6,5*sp.pi/6)
    assert sp.Matrix([1,2]).dot(sp.Matrix([2,1]))/5==sp.Rational(4,5)
    assert sum(3+2*n for n in range(10))==120
    assert sum(2*3**n for n in range(5))==242
    assert sp.solve_univariate_inequality(abs(x)/sp.sqrt(2)>3,x,relational=False)==sp.Union(sp.Interval.open(-sp.oo,-3*sp.sqrt(2)),sp.Interval.open(3*sp.sqrt(2),sp.oo))
    assert sp.binomial(3,1)*sp.binomial(2,1)/sp.binomial(5,2)==sp.Rational(3,5)
    assert sp.limit((x*x-1)/(x-1),x,1)==2
    assert sp.diff(x*x*sp.sin(x),x)==2*x*sp.sin(x)+x*x*sp.cos(x)
    assert sp.simplify(sp.diff((x-1)*sp.exp(x),x)-x*sp.exp(x))==0
    assert sp.integrate(x**-2,(x,1,sp.oo))==1
    assert sp.solve([x+y-3,2*x-y],(x,y))=={x:1,y:2}
    assert sp.Matrix([[2,1],[1,2]]).eigenvals()=={1:1,3:1}
    assert sp.diff(3*sp.exp(2*x),x)==2*3*sp.exp(2*x)
    n=sp.symbols('n',integer=True,nonnegative=True)
    assert sp.summation(sp.Rational(1,2)**n,(n,0,sp.oo))==2
    f=x*x*y+y*y
    assert [sp.diff(f,z).subs({x:1,y:2}) for z in (x,y)]==[4,5]
    assert sp.Rational(4,10)*sp.Rational(2,100)/sp.Rational(14,1000)==sp.Rational(4,7)


def test_catalog_and_solution_work_without_provider(monkeypatch):
    app=FastAPI();app.include_router(solve.router)
    monkeypatch.setattr(solve,'api_key',None)
    with TestClient(app) as client:
        catalog=client.get('/solve/examples').json()
        assert len(catalog['items'])==20 and not catalog['external_search']
        result=client.get('/solve/examples/uni-bayes').json()
        assert result['solution']['source']=='curriculum'
        assert client.get('/solve/examples/unknown').status_code==404
        response=client.post('/solve/stream',json={'problem':result['problem']})
        events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        assert events[-1]['type']=='complete'
        assert events[-1]['solution']['source']=='curriculum'


def test_advice_is_specific_and_does_not_block_complete_geometry():
    assert study_advice('如图，求AB的长度。')['blocking']
    assert study_advice('如图，求AB的长度。','A(0,0),B(3,4)') is None
    assert study_advice('已知圆(x-1)^2+y^2=4，求面积。') is None
    assert not study_advice('已知函数f。（1）定义域（2）单调性（3）最值')['blocking']
    assert study_advice('证明黎曼猜想')['blocking']
    assert study_advice('求定积分', failure=True)['suggestions']
    assert '不是用户题目的答案' in teaching_context('无放回抽球的概率')
    assert teaching_context('随便聊聊')==''


def test_partial_answer_keeps_steps_but_emits_decomposition(monkeypatch):
    partial=worked_solution(EXAMPLES[0])
    partial.completion='partial'
    partial.next_tasks=['结合前一问，讨论参数的两种符号情况']
    async def ai(_):return partial
    monkeypatch.setattr(solve,'ai_solution',ai)
    monkeypatch.setattr(solve,'api_key','test')
    app=FastAPI();app.include_router(solve.router)
    with TestClient(app) as client:
        response=client.post('/solve/stream',json={'problem':'完成复杂参数证明'})
        events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        advice=next(e['advice'] for e in events if e['type']=='advice')
        assert advice['suggestions']==partial.next_tasks
        assert events[-1]['solution']['completion']=='partial'


def test_cache_is_private_and_sensitive_to_conditions(monkeypatch):
    solve.SOLUTION_CACHE.clear()
    data=SolveRequest(problem='一道题',context='一个图形')
    token=identity.set(('ip','student1'))
    try:
        solve.remember_solution(data,worked_solution(EXAMPLES[0]))
        first=solve.cached_solution(data)
        assert first
        first.summary='modified locally'
        assert solve.cached_solution(data).summary!='modified locally'
        assert solve.cached_solution(SolveRequest(problem='一道题且x>0',context='一个图形')) is None
        assert solve.cached_solution(SolveRequest(problem='一道题',context='另一个图形')) is None
        identity.set(('ip','student2'))
        assert solve.cached_solution(data) is None
        identity.set(('ip',None))
        assert solve.cached_solution(data) is None
    finally:
        identity.reset(token)
        solve.SOLUTION_CACHE.clear()
