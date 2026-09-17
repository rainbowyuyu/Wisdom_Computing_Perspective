import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.routers import solve
from app.solution_models import Visual, SolveRequest
from logic.solution_engine import expression, local_solution, resolve_visual_functions


def test_geometry_segments_reference_real_vertices():
    visual = Visual(kind='geometry', points=[(0,0),(4,0),(1,3),(2.5,1.5)], segments=[(0,1),(1,2),(2,0),(0,3)])
    assert visual.segments[-1] == (0,3)
    assert Visual(kind='geometry', points=[(0,0),(1,1)], segments=[]).segments == []
    for segments in [[(0,4)], [(1,1)], [(-1,2)], [(0,1.5)]]:
        with pytest.raises(ValidationError):
            Visual(kind='geometry', points=visual.points, segments=segments)


def test_ai_formula_command_escaping_preserves_matrix_rows():
    from app.solution_models import SolutionStep
    step = SolutionStep(title='Test', explanation='Test', formula=r'\\frac{2}{3},\\quad G')
    assert step.formula == r'\frac{2}{3},\quad G'
    matrix = r'\begin{bmatrix}a&b\\c&d\end{bmatrix}'
    assert SolutionStep(title='Test', explanation='Test', formula=matrix).formula == matrix
    legacy=SolutionStep(title='Test',explanation='Test',formula=r'x-2=0\quad\mathrm{or}\quadx-3=0')
    assert legacy.formula==r'x-2=0\quad\mathrm{or}\quad x-3=0'


def test_recognition_latex_preserves_matrix_rows_and_math_commands():
    from app.routers.agent import sanitize_latex_for_mathlive
    matrix = r"\begin{bmatrix}1 & 2 \\ 0 & 1\end{bmatrix}"
    assert sanitize_latex_for_mathlive(matrix) == matrix
    assert sanitize_latex_for_mathlive(r"\nabla f \neq 0") == r"\nabla f \neq 0"
    assert local_solution(matrix).summary == '行列式为 1。'


@pytest.mark.parametrize('problem,answer', [
    ('解方程 x^2-5*x+6=0', '2, 3'), ('解方程 x^2=0', '0'),
    ('解方程 x^2+1=0', '-I, I'), ('2*x+4=0', '-2'),
    ('定积分 x^2 从 0 到 1', r'\frac{1}{3}'),
    ('求导 sin(x)', r'\cos'), ('积分 x^2', r'\frac{x^{3}}{3}'),
    ('矩阵 [[1,2],[0,1]]', '1'), ('矩阵 [[1,2],[2,4]]', '0'),
])
def test_math_result_and_shared_visuals(problem, answer):
    result = local_solution(problem)
    assert result.source == 'sympy'
    assert answer in result.summary
    assert len(result.steps) >= 3
    assert all(s.explanation for s in result.steps)
    if 'x^2-5' in problem:
        assert result.steps[-1].visual.points == [(2., 0.), (3., 0.)]
        for x, y in result.steps[0].visual.curves[0].points:
            assert y == pytest.approx(x*x-5*x+6)


@pytest.mark.parametrize('text', ["__import__('os').system('echo unsafe')", 'x.__class__', 'open("file")', '[x for x in range(5)]', 'x**9999999', '(x**12)**12', '1/0', '1e999'])
def test_expression_rejects_code_and_unbounded_operations(text):
    with pytest.raises((ValueError, SyntaxError, TypeError, OverflowError)):
        expression(text)


@pytest.mark.parametrize('problem', ['已知三角形，请证明角平分线定理', 'x/x*x=0', 'x^2=1 且 x>0', '积分 sin(x)'])
def test_local_tool_does_not_drop_conditions(problem):
    assert local_solution(problem) is None


def test_sse_plan_steps_and_completion(monkeypatch):
    app = FastAPI(); app.include_router(solve.router)
    monkeypatch.setattr(solve, 'api_key', None)
    with TestClient(app) as client:
        response = client.post('/solve/stream', json={'problem':'x^2-5*x+6=0'})
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        assert response.headers['x-accel-buffering'] == 'no'
        assert [e['index'] for e in events if e['type']=='step'] == [0,1,2,3]
        assert events[-1]['type']=='complete'
        assert events[-1]['solution']['source']=='sympy'
        unknown = client.post('/solve/stream', json={'problem':'证明费马大定理'})
        assert 'ALIYUN_KEY' in unknown.text
        assert '"type": "complete"' not in unknown.text
        assert client.post('/solve/stream', json={'problem':' '}).status_code == 422
        assert client.get('/solve/capabilities').status_code == 200


def test_ai_contract_and_tool_failure(monkeypatch):
    app = FastAPI(); app.include_router(solve.router)
    monkeypatch.setattr(solve, 'api_key', 'test')
    def broken(_): raise ValueError('invalid model response')
    monkeypatch.setattr(solve, 'ai_solution', broken)
    with TestClient(app) as client:
        response = client.post('/solve/stream', json={'problem':'证明一条几何定理'})
        assert '"type": "error"' in response.text
        assert '"type": "complete"' not in response.text
    with pytest.raises(ValidationError): Visual(kind='matrix', matrix=[[1,2,3],[4,5,6]])
    with pytest.raises(ValidationError): Visual(kind='plot', curves=[])
    with pytest.raises(ValidationError): Visual(kind='geometry', points=[[0,0]])
    with pytest.raises(ValidationError): Visual(kind='matrix', matrix=[[float('nan'),2],[0,1]])


def test_ai_selected_function_is_computed_by_the_math_tool():
    solution = local_solution('x^2=1')
    solution.steps[0].visual = Visual(kind='plot', functions=[{'expression':'sin(x)', 'domain':[-2,2]}])
    result = resolve_visual_functions(solution)
    curve = result.steps[0].visual.curves[0]
    import math
    assert not result.steps[0].visual.functions
    assert len(curve.points) == 161
    assert all(y == pytest.approx(math.sin(x)) for x, y in curve.points)


def test_async_ai_completion_streams_all_steps(monkeypatch):
    expected = local_solution('x^2=1')
    expected.source = 'ai'
    async def planned(_): return expected
    monkeypatch.setattr(solve, 'api_key', 'test')
    monkeypatch.setattr(solve, 'ai_solution', planned)
    app = FastAPI(); app.include_router(solve.router)
    with TestClient(app) as client:
        response = client.post('/solve/stream', json={'problem':'一个需要模型理解的数学问题'})
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[-1]['type'] == 'complete'
    assert events[-1]['solution']['source'] == 'ai'
    assert len([e for e in events if e['type']=='step']) == len(expected.steps)


def test_disconnect_cancels_async_model_request(monkeypatch):
    async def scenario():
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def pending(_):
            started.set()
            try: await asyncio.Event().wait()
            finally: cancelled.set()
        class Request:
            async def is_disconnected(self): return False
        monkeypatch.setattr(solve, 'api_key', 'test')
        monkeypatch.setattr(solve, 'ai_solution', pending)
        response = await solve.solve_stream(SolveRequest(problem='证明一个几何定理'), Request())
        stream = response.body_iterator
        await anext(stream); await anext(stream)
        receiving = asyncio.create_task(anext(stream))
        await asyncio.wait_for(started.wait(), 1)
        receiving.cancel()
        with pytest.raises(asyncio.CancelledError): await receiving
        await asyncio.wait_for(cancelled.wait(), 1)
    asyncio.run(scenario())


def test_cancelled_render_kills_process_and_releases_slot(monkeypatch, tmp_path):
    class Process:
        killed = False
        returncode = None
        def poll(self): return self.returncode
        def kill(self): self.killed=True; self.returncode=-9
        def wait(self): return self.returncode
    process = Process()
    class Request:
        async def is_disconnected(self): return False
    async def scenario():
        monkeypatch.setattr(solve.subprocess, 'Popen', lambda *a, **k: process)
        monkeypatch.setattr(solve, 'RENDER_SLOTS', asyncio.Semaphore(1))
        response = await solve.render_solution(solve.RenderRequest(solution=local_solution('x^2=1')), Request())
        stream = response.body_iterator
        await anext(stream) # queued
        await anext(stream) # child running
        await stream.aclose() # browser disconnect
        assert process.killed
        assert solve.RENDER_SLOTS._value == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('problem', [
    r'\int_0^1 x^{2}+3x \, dx',
    r'\int_{0}^{1} \left(x^{2}+3x\right)\,\mathrm{d}x',
    r'\(\int_0^1 x^2+3x dx\)',
])
def test_latex_integral_from_visual_editor(problem):
    result = local_solution(problem)
    assert result.source == 'sympy'
    assert result.summary == r'定积分为 $\frac{11}{6}$。'
    assert not result.steps[0].visual.area
    assert result.steps[1].visual.area
    assert all(s.visual.curves == result.steps[0].visual.curves for s in result.steps)
    assert result.steps[-1].formula.endswith(r'=\frac{11}{6}')


def test_latex_integral_never_discards_conditions():
    assert local_solution(r'\int_0^1 x^2 dx，且 x>2') is None
    assert local_solution(r'\int_0^1 x^2 dx + 9') is None


def test_algebra_steps_use_actual_problem_transformations():
    result = local_solution('x^2-5*x+6=0')
    assert result.steps[1].formula == r'\left(x - 3\right) \left(x - 2\right)=0'
    assert 'x - 2=0' in result.steps[2].formula
    result = local_solution('2*x+4=0')
    assert result.steps[1].formula == '2 x=-4'
    assert result.steps[2].formula == 'x=-2'


@pytest.mark.parametrize('summary,conflict', [
    (r'中线 $BM$ 的长度为 $5$。', True),
    (r'中线 $BM=5$。', True),
    (r'中线 $BM$ 的长度为 $\frac{5}{2}$。', False),
    (r'中线 $BM$ 的长度为 $2.5$。', False),
    (r'斜边 $AC$ 的长度为 $5$，中线长度是其一半。', False),
    (r'使用 $5$ 个步骤，计算 $BM$。', False),
])
def test_explicit_summary_contradiction_is_detected_without_guessing(summary, conflict):
    from logic.solution_engine import validate_summary_consistency
    solution=local_solution('x^2=1')
    solution.steps[-1].formula=r'|BM|=\sqrt{\frac{25}{4}}=\frac{5}{2}'
    solution.summary=summary
    if conflict:
        with pytest.raises(ValueError, match='不一致'): validate_summary_consistency(solution)
    else: validate_summary_consistency(solution)


def test_ai_retries_an_inconsistent_summary_once(monkeypatch):
    from types import SimpleNamespace
    bad=local_solution('x^2=1')
    bad.steps[-1].formula=r'|BM|=\frac{5}{2}'
    bad.summary=r'中线 $BM$ 的长度为 $5$。'
    good=bad.model_copy(deep=True);good.summary=r'中线 $BM$ 的长度为 $\frac{5}{2}$。'
    calls=[]
    async def create(**kwargs):
        calls.append(kwargs)
        content=(bad if len(calls)==1 else good).model_dump_json()
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    monkeypatch.setattr(solve,'ai_client',SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    result=asyncio.run(solve.ai_solution(SolveRequest(problem='求中线长度')))
    assert result.summary==good.summary
    assert len(calls)==2 and '不一致' in calls[-1]['messages'][-1]['content']
    assert result.source=='ai' and '未经符号计算验证' in result.verification


def test_summary_consistency_does_not_collapse_multiple_roots():
    from logic.solution_engine import validate_summary_consistency
    result=local_solution('x^2-5*x+6=0')
    result.summary=r'方程有两个解：$x=2$ 或 $x=3$。'
    validate_summary_consistency(result)


@pytest.mark.parametrize('failure', ['schema','contradiction'])
def test_ai_stops_after_one_failed_repair(monkeypatch, failure):
    from types import SimpleNamespace
    payload=local_solution('x^2=1').model_dump()
    if failure=='schema': payload['steps'][0]['hint']='提示'*400
    else:
        payload['steps'][-1]['formula']=r'BM=\frac{5}{2}'
        payload['summary']=r'$BM$ 的长度为 $5$。'
    calls=[]
    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
    monkeypatch.setattr(solve,'ai_client',SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    with pytest.raises(ValueError): asyncio.run(solve.ai_solution(SolveRequest(problem='求中线长度')))
    assert len(calls)==2


def test_quadratic_formula_typesets_every_step(tmp_path, monkeypatch):
    """Compile the actual generated equations, so raw command fallback cannot pass."""
    from manim import MathTex, tempconfig
    from logic.solution_scene import formula
    # Match the renderer subprocess: MiKTeX requires its working directory and
    # output directory on the same Windows drive.
    monkeypatch.chdir(tmp_path)
    solution=local_solution('x^2-5*x+6=0')
    with tempconfig({'media_dir':str(tmp_path)}):
        for step in solution.steps:
            assert isinstance(formula(step.formula),MathTex)
        with pytest.raises(ValueError,match='WISDOM_LATEX_ERROR'):
            formula(r'x-2=0\quad\mathrm{or}\quadx-3=0')
        with pytest.raises(ValueError,match='WISDOM_LATEX_ERROR'):
            formula(r'\frac{1}{')
