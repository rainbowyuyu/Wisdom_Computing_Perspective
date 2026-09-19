"""Tool-backed step tutor and cancellable rendering of data-only Manim scenes."""
import asyncio
from contextlib import suppress
import importlib.util
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import signal
import sys
import tempfile
import time
import uuid
from collections import OrderedDict

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, APIStatusError

from ..config import api_key, client, VIDEOS_DIR
from ..solution_models import RenderRequest, Solution, SolveRequest
from ..llm_errors import llm_error_message
from ..usage_guard import GuardedClient, UsageDenied, identity
from logic.solution_engine import local_solution, resolve_visual_functions, validate_summary_consistency
from logic.solution_adaptation import strategy_guidance, parse_solution, verify_parameter_analysis
from logic.curriculum import EXAMPLES, catalog, exact_example, worked_solution, teaching_context, study_advice
from logic.task_planning import needs_agent

router = APIRouter(prefix="/solve", tags=["step tutor"])
logger = logging.getLogger(__name__)
RENDER_SLOTS = asyncio.Semaphore(2)
SCENE = Path(__file__).resolve().parents[2] / "logic" / "solution_scene.py"
HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}
ai_client = GuardedClient(AsyncOpenAI(api_key=client.api_key, base_url=client.base_url, timeout=70, max_retries=0), asynchronous=True)
SOLVE_TIMEOUT = 150
LOCAL_TIMEOUT = 10
HEARTBEAT_INTERVAL = 8
RENDER_QUEUE_TIMEOUT = 60
SOLUTION_CACHE = OrderedDict()


def cache_key(data):
    who = identity.get()
    # Separate authenticated users; never share a user's question/context with guests.
    return (who[1], data.problem, data.context, os.getenv('SOLVER_MODEL', 'qwen-plus')) if who and who[1] else None


def cached_solution(data):
    key = cache_key(data)
    if key is None:
        return None
    now = time.monotonic()
    for old_key, (expires, _) in list(SOLUTION_CACHE.items()):
        if expires <= now:
            SOLUTION_CACHE.pop(old_key, None)
    if key in SOLUTION_CACHE:
        SOLUTION_CACHE.move_to_end(key)
        return SOLUTION_CACHE[key][1].model_copy(deep=True)
    return None


def remember_solution(data, solution):
    key = cache_key(data)
    if key is not None:
        SOLUTION_CACHE[key] = (time.monotonic() + 600, solution.model_copy(deep=True))
        SOLUTION_CACHE.move_to_end(key)
        while len(SOLUTION_CACHE) > 64:
            SOLUTION_CACHE.popitem(last=False)


def stop_process(proc):
    """Also terminate TeX/FFmpeg children when a renderer is cancelled."""
    if proc.poll() is not None: return
    if sys.platform == "win32" and getattr(proc, "pid", None):
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
    elif getattr(proc, "pid", None):
        try: os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError: pass
    else:
        proc.kill()
    if proc.poll() is None: proc.kill()
    proc.wait()


def event(kind, **data):
    return "data: " + json.dumps({"type": kind, **data}, ensure_ascii=False, allow_nan=False) + "\n\n"


def tex_failure_message(folder, failure):
    try:
        diagnostic = json.loads((folder / 'tex-error.json').read_text(encoding='utf-8'))
        if diagnostic.get('code') in {'length','syntax','command','environment','compiler','converter','package','font','compile'}:
            step = diagnostic.get('step')
            prefix = f'第 {step} 步：' if type(step) is int and 1 <= step <= 12 else ''
            message = diagnostic.get('message')
            if isinstance(message, str): return prefix + message[:200]
    except (OSError, ValueError, AttributeError):
        pass
    return ('动画中的公式排版失败，请检查步骤公式或运行 TeX 环境自检。'
            if 'WISDOM_LATEX_ERROR' in failure else 'Manim 渲染失败，请检查服务端渲染环境后重试。')


@router.get("/capabilities")
async def capabilities():
    return {"symbolic": True, "ai": bool(api_key), "manim": importlib.util.find_spec("manim") is not None,
            "tools": ["sympy", "interactive_svg", "manim"], "max_steps": 12}


@router.get('/examples')
async def list_examples():
    return {'items': catalog(), 'source': '本站整理', 'external_search': False}


@router.get('/examples/{ident}')
async def read_example(ident: str):
    item = next((e for e in EXAMPLES if e['id'] == ident), None)
    if item is None:
        raise HTTPException(status_code=404, detail='例题不存在')
    solution = await asyncio.to_thread(worked_solution, item)
    return {'problem': item['problem'], 'solution': solution.model_dump()}


async def ai_solution(data):
    schema = json.dumps(Solution.model_json_schema(), ensure_ascii=False)
    prompt = (
        "你是一位严谨的中文数学教师。根据用户完整题目生成分步解答，输出一个 JSON 对象。"
        "不要虚构题目条件，条件不足时在步骤中指出需要补充什么，不要编造答案。"
        "每一步包含标题、推理说明、单个 LaTeX 公式（不带美元分隔符）、提示和对应可视化。"
        "表达简洁：explanation 每步不超过180字，hint不超过80字，summary不超过200字；长等式拆成多个实质步骤。"
        "标题、说明、提示、caption 和 summary 中出现的数学表达式必须用 $...$ 包裹，分数、根式均用 LaTeX。"
        "连续步骤的 formula 应展示本题算式从上一步到下一步的实际等价变化，代入具体数值，不能只列通用公式。"
        "图像逐步构建：保留前一步仍然需要的曲线和点，使用相同的坐标与点名，再增加本步辅助线、交点或结果；"
        "不要在每步给出相同的完整图。积分先画曲线，再设置 area=true 展示有向面积；"
        "仅在 plot 的第一条曲线为原函数、第二条为其导数且同一区间连续时设置 tangent=true。"
        "通常安排 4-8 步，每一步展示实质推理。为适合的步骤选用 plot(真实函数采样曲线)、"
        "matrix(2×2线性变换矩阵)、geometry(依序连接的坐标点与标签)；纯逻辑步骤使用 reasoning。"
        "plot 的 points 是真实计算出的 [x,y] 点列，每条至少 20 点，不要用示意曲线冒充计算数据。"
        "绘制函数时优先用 visual.functions=[{expression:'x^2',label:'f(x)',domain:[-5,5]}]，curves=[]；"
        "系统会调用数学工具计算采样点。expression 只支持 x、数字、pi、e、+ - * / ^ 和 sin/cos/tan/exp/log/sqrt。"
        "题目含未赋值的参数（如 m）时必须保留参数推导，不得任意代入数值；无法数值绘图的步骤使用 reasoning，不能把参数放入 functions 或 points。"
        "geometry 中 points 是有依据的坐标，labels 对应点名，segments 必须明确给出需要连接的点索引对（从0开始），"
        "例如三角形三点的边为 [[0,1],[1,2],[2,0]]，增加中点后单独添加中线；不能把所有点依次连起来。"
        "仅标记点时 segments=[]。caption 解释图中几何关系，不编造未经计算的长度。"
        "公式按正常 JSON 转义，每个 LaTeX 命令在 JSON 解码后只有一个反斜杠。中文连接词用 \\text{且} 等写法；"
        "过长推导优先拆步，必要时可用 aligned、cases 或矩阵环境展示少量多行公式；使用标准 LaTeX，不输出宏定义、可执行代码或 HTML。"
        "summary 给出答案和适用条件。source 必须为 ai，verification 必须诚实说明由 AI 推导，未经符号计算验证。"
        "输出前核对 summary 的结论与最后一步的计算结果完全一致，分数不得遗漏分母。"
        + "\n" + strategy_guidance(data.problem) + teaching_context(data.problem) + "\n"
        + "优先采用与学生学段相符的方法：高中题优先配方、因式分解、几何和基本不等式，不默认用大学定理；大学题写明定理条件。"
        "不把数值近似当精确答案；需要分类讨论时列出各分支。复杂到无法完整求解时，明确指出尚未完成的部分及可拆解的子目标，summary 不得声称已得到完整答案。"
        "仅完整解决全部所求时 completion=solved；只完成部分为 partial，缺少必需条件为 needs_information。后两种情况必须给出 next_tasks（1至4个具体拆解目标或待补充条件），步骤只写已确定内容。\n"
        + "严格遵守以下 JSON Schema：\n" + schema
    )
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": data.problem + ("\n已知图像或上下文："+data.context if data.context else "")}]
    for attempt in range(2):
        try:
            result = await ai_client.chat.completions.create(
                model=os.getenv("SOLVER_MODEL", "qwen-plus"), response_format={"type": "json_object"},
                messages=messages, temperature=0.2, max_tokens=6500,
            )
        except (APIConnectionError, APITimeoutError, APIStatusError) as error:
            if attempt or (isinstance(error, APIStatusError) and error.status_code < 500):
                raise
            await asyncio.sleep(0.5)
            continue
        content = result.choices[0].message.content
        try:
            solution = parse_solution(content)
            validate_summary_consistency(solution)
            solution.source = "ai"
            solution.verification = "AI 推导与图形数据，未经符号计算验证；请核对题目条件和结论。"
            if solution.completion == 'solved':
                solution = await asyncio.to_thread(verify_parameter_analysis, solution, data.problem)
            break
        except (ValueError, SyntaxError, TypeError, NotImplementedError) as error:
            if attempt: raise
            messages += [{"role": "assistant", "content": content}, {"role": "user", "content": str(error) + "。重新输出完整 JSON，保留原题全部条件。"}]
    return await asyncio.to_thread(resolve_visual_functions, solution)


@router.post("/stream")
async def solve_stream(data: SolveRequest, request: Request):
    async def generate():
        task = None
        started = time.monotonic()
        try:
            yield event("status", message="正在识别题型并选择计算工具…", tool="planner")
            advice = study_advice(data.problem, data.context)
            if advice:
                yield event('advice', advice=advice)
                if advice['blocking']:
                    yield event('error', message=advice['message'])
                    return
            if needs_agent(data.problem):
                yield event('handoff', message='题目包含多个阶段，正在转交智能体拆解与安排任务。')
                return
            try:
                solution = await asyncio.wait_for(asyncio.to_thread(
                    lambda: exact_example(data.problem) or local_solution(data.problem)), LOCAL_TIMEOUT) if not data.context else None
            except (ValueError, SyntaxError, TypeError, OverflowError, asyncio.TimeoutError):
                solution = None
            if solution is None:
                solution = cached_solution(data)
                if solution is not None:
                    yield event('status', message='正在复用本账户最近完成的同题解答，本次不调用 AI。', tool='cache')
            if solution is None:
                if not api_key:
                    yield event("error", message="这道题需要 AI 推导，但服务端尚未配置 ALIYUN_KEY。可先体验：解方程 x^2-5*x+6=0、求导 sin(x)、矩阵 [[1,2],[0,1]]。")
                    return
                yield event("status", message="数学智能体正在组织逐步推导和图形…", tool="ai")
                task = asyncio.create_task(ai_solution(data))
                while not task.done():
                    if await request.is_disconnected(): return
                    remaining = SOLVE_TIMEOUT - (time.monotonic() - started)
                    if remaining <= 0:
                        raise asyncio.TimeoutError()
                    done, _ = await asyncio.wait({task}, timeout=min(HEARTBEAT_INTERVAL, remaining))
                    if not done:
                        elapsed = int(time.monotonic() - started)
                        yield event("heartbeat", elapsed=elapsed, message=f"正在推导与检查解答，已等待 {elapsed} 秒；可随时停止，超时后可重试。")
                solution = task.result()
                remember_solution(data, solution)
            if solution.completion != 'solved':
                yield event('advice', advice={'blocking': solution.completion == 'needs_information',
                    'message': '当前仅完成部分推导，请按建议继续。' if solution.completion == 'partial' else '还需要补充条件，当前不能确定完整答案。',
                    'suggestions': solution.next_tasks or ['核对题面并补充所求量、定义域及缺少的条件']})
            yield event("plan", title=solution.title, source=solution.source, verification=solution.verification, total=len(solution.steps))
            for index, item in enumerate(solution.steps):
                if await request.is_disconnected(): return
                yield event("step", index=index, step=item.model_dump())
                await asyncio.sleep(0)
            yield event("complete", solution=solution.model_dump())
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            yield event('advice', advice=study_advice(data.problem, data.context, failure=True))
            yield event("error", message="本次推导等待超时，任务已停止，请重试。题目和已收到的步骤已保留。")
        except Exception as error:
            logger.warning("Step tutor failed: %s", type(error).__name__)
            if not isinstance(error, UsageDenied):
                yield event('advice', advice=study_advice(data.problem, data.context, failure=True))
            yield event("error", message=llm_error_message(error))
        finally:
            if task and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
    return StreamingResponse(generate(), media_type="text/event-stream", headers=HEADERS)


async def _render_solution_once(data: RenderRequest, request: Request):
    async def generate():
        proc = None
        temp = None
        acquired = False
        try:
            if not importlib.util.find_spec("manim"):
                yield event("error", message="Manim 尚未安装。分步讲解与交互图形仍可使用。")
                return
            yield event("status", message="动画任务已提交，正在等待渲染资源…", tool="manim")
            queued = time.monotonic()
            while not acquired:
                if await request.is_disconnected(): return
                remaining = RENDER_QUEUE_TIMEOUT - (time.monotonic() - queued)
                if remaining <= 0:
                    yield event("error", message="动画渲染资源暂时繁忙，排队已超时。题解已保留，请稍后重试动画。")
                    return
                try:
                    await asyncio.wait_for(RENDER_SLOTS.acquire(), timeout=min(5, remaining))
                    acquired = True
                except asyncio.TimeoutError:
                    yield event("heartbeat", message="渲染队列中，可以继续查看步骤。")
            temp = tempfile.mkdtemp(prefix="wisdom-solve-")
            folder = Path(temp)
            payload = folder / "solution.json"
            payload.write_text(data.solution.model_dump_json(), encoding="utf-8")
            env = os.environ.copy()
            env["WISDOM_SOLUTION_JSON"] = str(payload)
            env["WISDOM_TEX_ERROR"] = str(folder / 'tex-error.json')
            env["PYTHONIOENCODING"] = "utf-8"
            cmd = [sys.executable, "-m", "manim", "-ql", "--disable_caching", "--media_dir", temp,
                   "-o", "solution.mp4", str(SCENE), "SolutionScene"]
            started = time.monotonic()
            with (folder / "render.log").open("wb") as log:
                proc = subprocess.Popen(cmd, cwd=temp, env=env, stdout=log, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    start_new_session=sys.platform != "win32")
                yield event("status", message="Manim 正在绘制分步动画；你可以继续操作图形。", tool="manim")
                last_chapter = -1
                last_heartbeat = started
                while proc.poll() is None:
                    if await request.is_disconnected(): return
                    if time.monotonic() - started > 240:
                        yield event("error", message="动画渲染超时，已停止任务。可以保留交互解答并重试动画。")
                        return
                    content = (folder / "render.log").read_text(encoding="utf-8", errors="replace")[-12000:]
                    matches = re.findall(r"WISDOM_CHAPTER:(\d+)", content)
                    chapter = int(matches[-1]) if matches else -1
                    if chapter > last_chapter:
                        last_chapter = chapter
                        yield event("progress", chapter=chapter, total=len(data.solution.steps), message=f"正在完成第 {chapter+1} 步动画")
                    if time.monotonic() - last_heartbeat > 5:
                        last_heartbeat = time.monotonic()
                        yield event("heartbeat", message="Manim 渲染中…")
                    await asyncio.sleep(0.4)
            if proc.returncode:
                failure = (folder/"render.log").read_text(encoding="utf-8", errors="replace")[-12000:]
                logger.warning("Solution render failed: %s", failure[-2400:])
                message = tex_failure_message(folder, failure)
                try:
                    diagnostic=json.loads((folder/'tex-error.json').read_text(encoding='utf-8'))
                    if not isinstance(diagnostic,dict):diagnostic={}
                except (OSError,ValueError):diagnostic={}
                yield event("error", message=message + "交互解答已保留。", _diagnostic=diagnostic, _failure=failure[-4000:])
                return
            outputs = [p for p in folder.rglob("solution.mp4") if "partial_movie_files" not in str(p)]
            if not outputs:
                yield event("error", message="渲染结束但未找到视频，请重试。")
                return
            name = "solution_" + uuid.uuid4().hex + ".mp4"
            shutil.copyfile(outputs[0], Path(VIDEOS_DIR)/name)
            chapters = [{"title": s.title, "start": i*5.0, "end": (i+1)*5.0} for i, s in enumerate(data.solution.steps)]
            yield event("complete", video_url="/videos/"+name, chapters=chapters)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Solution render failed")
            yield event("error", message="动画服务暂时不可用，交互解答已保留。")
        finally:
            def cleanup():
                if proc: stop_process(proc)
                if temp: shutil.rmtree(temp, ignore_errors=True)
            from ..async_cleanup import finish_cleanup
            async def cleanup_and_release():
                try: await asyncio.to_thread(cleanup)
                finally:
                    if acquired: RENDER_SLOTS.release()
            await finish_cleanup(cleanup_and_release())
    return StreamingResponse(generate(), media_type="text/event-stream", headers=HEADERS)


@router.post('/render')
async def render_solution(data: RenderRequest, request: Request):
    from ..async_cleanup import finish_cleanup
    from ..render_repair import repair_scope, eligible, judge_and_repair, validate_formula_change, repair_progress

    async def generate():
        working=data.model_copy(deep=True)
        repaired=False
        with repair_scope() as budget:
            for attempt in range(2):
                if await request.is_disconnected():return
                response=await _render_solution_once(working,request)
                failed=None
                try:
                    async for frame in response.body_iterator:
                        item=json.loads(frame[6:])
                        if item['type']=='error':failed=item
                        else:
                            if item['type']=='complete' and repaired:
                                item.update(solution=working.solution.model_dump(),repaired=True)
                            yield event(item.pop('type'),**item)
                finally:
                    await finish_cleanup(response.body_iterator.aclose())
                if not failed:return
                diagnostic=failed.pop('_diagnostic',{})
                failure=failed.pop('_failure',failed['message'])
                step=diagnostic.get('step')
                can_repair=(not budget['used'] and attempt==0 and type(step) is int
                    and 1<=step<=len(working.solution.steps) and eligible(failure,diagnostic))
                if not can_repair:
                    if repaired:failed['message']='自动修复后仍未完成动画。'+failed['message']
                    yield event('error',message=failed['message']);return
                yield event('status',message=f'第 {step} 步公式渲染失败，正在请模型判断并修复排版（最多一次）…',tool='manim',repairing=True)
                async def repair():
                    current=working.solution.steps[step-1]
                    answer=await judge_and_repair(ai_client,'formula',
                        {'step':step,'title':current.title,'explanation':current.explanation,'formula':current.formula},failure,budget)
                    return validate_formula_change(current.formula,answer.formula)
                replacement=None
                async for update in repair_progress(repair,request):
                    kind=update.pop('type')
                    if kind=='repair_result':replacement=update['value']
                    elif kind=='repair_failed':
                        yield event('error',message=failed['message']+' 修复未完成：'+update['message']);return
                    else:yield event(kind,**update)
                if replacement is None:return
                working.solution.steps[step-1].formula=replacement
                repaired=True
                yield event('status',message='公式排版修复已通过检查，正在重新排队生成动画…',tool='manim',repairing=True)
    return StreamingResponse(generate(),media_type='text/event-stream',headers=HEADERS)
