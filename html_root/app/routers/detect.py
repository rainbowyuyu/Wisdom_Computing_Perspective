# 智能识别、动态计算动画（含流式）
# 同步 LLM 调用需放入 run_in_executor，避免阻塞事件循环（渲染时可并发加载算式库、识别等）
import asyncio
import base64
import json
import logging
import os
import uuid
import threading
from fastapi import APIRouter, File, UploadFile, Request
from fastapi.responses import JSONResponse, StreamingResponse
from logic.manim_generator import render_matrix_animation
from logic.prompt import return_prompt

from ..config import client, api_key, VIDEOS_DIR
from ..models import CalcModel
from .agent import sanitize_latex_for_mathlive
from ..llm_errors import llm_error_message
from ..usage_guard import run_with_context
from ..async_cleanup import finish_cleanup

logger = logging.getLogger(__name__)
router = APIRouter(tags=["detect"])


def generate_manim_prompt(latex_a, latex_b, operation, vision_prompt: str | None = None):
    op_desc = {"formular": "公式推演", "visualization": "可视化演示", "normal": "通用演示", "solution": "完整解题演示"}.get(operation, "数学展示")
    extra = {}
    if vision_prompt and isinstance(vision_prompt, str):
        extra["vision_prompt"] = vision_prompt
    return return_prompt(op_desc, latex_a, latex_b, **extra)


def _inject_autoscale_into_construct(code: str) -> str:
    """
    将自动缩放/居中的兜底逻辑注入到 GenScene.construct 末尾：
    - 不改变大模型生成的主要结构
    - 统一使用 VGroup(*self.mobjects) + scale_to_fit_width/height + move_to(ORIGIN)
    - 若解析失败，原样返回（不影响渲染）
    """
    if not code or "_AUTO_FIT_LAYOUT_" in code:
        return code
    try:
        lines = code.splitlines()
        class_idx = None
        for i, line in enumerate(lines):
            if "class GenScene" in line:
                class_idx = i
                break
        if class_idx is None:
            return code
        class_indent = len(lines[class_idx]) - len(lines[class_idx].lstrip(" "))

        construct_idx = None
        for i in range(class_idx + 1, len(lines)):
            stripped = lines[i].lstrip()
            if stripped.startswith("def construct(self):"):
                construct_idx = i
                break
        if construct_idx is None:
            return code

        construct_indent = len(lines[construct_idx]) - len(lines[construct_idx].lstrip(" "))
        body_start = construct_idx + 1
        end_idx = len(lines) - 1

        for i in range(body_start, len(lines)):
            stripped = lines[i].lstrip()
            if not stripped:
                continue
            indent = len(lines[i]) - len(lines[i].lstrip(" "))
            # 走到与 construct 同级或更外层的非注释/非装饰器代码，视为方法结束
            if indent <= construct_indent and not stripped.startswith(("#", "@")):
                end_idx = i - 1
                break

        insert_pos = max(body_start, end_idx + 1)
        pad = " " * (construct_indent + 4)
        snippet = [
            "",
            pad + "# _AUTO_FIT_LAYOUT_: 自动缩放所有对象以适配画面边界",
            pad + "try:",
            pad + "    group = VGroup(*self.mobjects)",
            pad + "    frame = self.camera.frame",
            pad + "    frame_w = frame.width",
            pad + "    frame_h = frame.height",
            pad + "    if group.width > frame_w * 0.9:",
            pad + "        group.scale_to_fit_width(frame_w * 0.9)",
            pad + "    if group.height > frame_h * 0.9:",
            pad + "        group.scale_to_fit_height(frame_h * 0.9)",
            pad + "    group.move_to(frame.get_center())",
            pad + "except Exception:",
            pad + "    pass",
        ]
        new_lines = lines[:insert_pos] + snippet + lines[insert_pos:]
        return "\n".join(new_lines)
    except Exception:
        return code


@router.post("/detect")
async def detect_image(file: UploadFile = File(...)):
    try:
        image_content = await file.read(5_000_001)
        if len(image_content) > 5_000_000:
            return JSONResponse(status_code=413, content={"status":"error","message":"图片请控制在 5 MB 以内。"})
        base64_image = base64.b64encode(image_content).decode("utf-8")
        if not api_key:
            return {"status": "error", "message": "图片识别需要配置 ALIYUN_KEY；也可以直接输入文字题目进行分步解答。"}

        # 使用多模态大模型一次性返回：
        # - latex: 识别出的 LaTeX 公式
        # - vision_prompt: 面向后续 Manim 代码生成的几何/结构自然语言描述
        prompt_text = (
            "你是一名数学视觉理解助手。请仔细、逐符号比对图片中的公式和几何/图像结构，只根据图片内容输出一个 JSON 对象：\n"
            '{ "latex": "...", "problem_text": "...", "vision_prompt": "..." }\n\n'
            "- problem_text：完整转写题面文字、所有条件、选项和问题，不求解；如果只有公式则与 latex 相同。\n"
            "- latex：只包含主要的数学表达式或题目中的核心公式，使用标准 LaTeX，不要任何解释或多余文字；\n"
            "- 严格按照图片中的公式抄写，**不要自行添加/删除/修改任何数字、系数、上下标或积分上下限**，看不清时用 ? 占位而不要猜测；\n"
            "- 特别注意区分 **1 与 \\infty、0 与 6/9** 等相似符号：例如图片为 “∫_0^1 x^2 dx”，则 latex 必须是 `\\\\int_0^1 x^{2} \\\\, dx`，绝不能写成 `\\\\int_0^\\\\infty 3x^{2} dx` 之类；\n"
            "- vision_prompt：用中文简洁描述图像中的空间/几何/函数关系，例如坐标轴、曲线形状、圆/直线/点的位置关系等，"
            "便于后续根据该描述生成 Manim 动画（不要写成解题步骤，只描述“画面里有哪些对象、它们大致长什么样、彼此关系如何”）。\n"
            "务必保证输出是合法的 JSON，且只输出这一行 JSON，不要解释。"
        )
        loop = asyncio.get_event_loop()
        completion = await run_with_context(
            None,
            lambda: client.with_options(timeout=70, max_retries=0).chat.completions.create(
                model="qwen-vl-max",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                    ],
                }],
            ),
        )
        raw = completion.choices[0].message.content.strip()
        # 兼容 ```json ... ``` 包裹的情况
        if "```" in raw:
            parts = raw.split("```")
            if len(parts) >= 2:
                raw = parts[1]
            raw = raw.replace("json", "").strip()
        vision_prompt = None
        problem_text = ""
        try:
            parsed = json.loads(raw)
            latex = str(parsed.get("latex", "")).strip()
            problem_text = str(parsed.get("problem_text", latex)).strip()
            vision_prompt = str(parsed.get("vision_prompt", "")).strip() or None
        except Exception:
            # JSON 解析失败则退化到旧逻辑：整个内容视为 LaTeX，仅做简单清洗
            latex = raw
            vision_prompt = None

        # 统一对识别出的 LaTeX 做规范化处理，去掉 $$、\[ \]、```latex 等包裹，便于 MathLive 正确解析
        latex = sanitize_latex_for_mathlive(latex)
        return {"status": "success", "latex": latex, "problem_text": problem_text or latex, "vision_prompt": vision_prompt}
    except Exception as e:
        logger.warning("Image recognition failed: %s", type(e).__name__)
        return {"status": "error", "message": llm_error_message(e)}


@router.post("/animate")
async def generate_animation(data: CalcModel, request: Request):
    from .solve import RENDER_SLOTS
    acquired=False;work=None;cancelled=threading.Event()
    try:
        await asyncio.wait_for(RENDER_SLOTS.acquire(),60);acquired=True
        if await request.is_disconnected():return JSONResponse(status_code=408,content={'status':'error','message':'请求已停止。'})
        task_id = str(uuid.uuid4())
        work=asyncio.create_task(asyncio.to_thread(render_matrix_animation,data.matrixA,data.matrixB,data.operation,task_id,cancelled))
        while not work.done():
            if await request.is_disconnected():cancelled.set()
            await asyncio.wait({work},timeout=.3)
        video_path=work.result()
        if video_path and os.path.exists(video_path):
            filename = os.path.basename(video_path)
            return {"status": "success", "video_url": f"/videos/{filename}"}
        return JSONResponse(status_code=500,content={'status':'error','message':'矩阵动画未能完成或渲染超时，请检查矩阵并稍后重试。'})
    except asyncio.TimeoutError:
        return JSONResponse(status_code=503,content={'status':'error','message':'渲染资源繁忙，排队超时，请稍后重试。'})
    except ValueError as error:
        return JSONResponse(status_code=422,content={'status':'error','message':str(error)})
    except Exception as error:
        logger.warning('Matrix animation failed: %s',type(error).__name__)
        return JSONResponse(status_code=500,content={'status':'error','message':'动画服务暂时不可用，请稍后重试。'})
    finally:
        cancelled.set()
        async def cleanup():
            try:
                if work and not work.done():
                    try: await work
                    except Exception: logger.warning("Cancelled matrix render failed during cleanup")
            finally:
                if acquired: RENDER_SLOTS.release()
        await finish_cleanup(cleanup())


@router.post("/animate/stream")
async def generate_animation_stream(data: CalcModel, request: Request):
    """Legacy admin flow, sharing bounded rendering with the creator workspace."""
    from .devtools import _render_keyframe_with_repair, _run_manim_with_repair
    from ..models import ManimCodeModel, ManimKeyframeModel
    from ..render_repair import repair_progress

    def event(step, **values):
        return 'data: '+json.dumps({'step':step,**values},ensure_ascii=False)+'\n\n'

    async def event_generator():
        budget={'used':False}
        try:
            if await request.is_disconnected(): return
            yield event('generating_code',message='正在整理题目与解题步骤…',progress=5)
            completion=await run_with_context(None,lambda: client.chat.completions.create(
                model='qwen-plus',messages=[{'role':'user','content':
                    f'请按学生的计算方式分步解答以下题目，最后给出结论；公式使用标准 LaTeX，行内 $...$，独立 $$...$$。不要输出代码。\n题目：{data.matrixA}\n补充：{data.matrixB}'}]))
            solution=(completion.choices[0].message.content or '').strip()
            if solution: yield event('text_result',content=solution)
            phases=[('calc','公式推演'),('vis','可视化演示')] if data.operation=='normal' else [(None,{'formular':'公式推演','visualization':'可视化演示','solution':'完整解题演示'}.get(data.operation,'数学展示'))]
            if data.operation=='normal':
                yield event('normal_split',message='先计算推演，再可视化演示',progress=10)
            for part,description in phases:
                if await request.is_disconnected(): return
                yield event('generating_code',message=f'正在构思{description}…',progress=15,part=part)
                prompt=return_prompt(description,data.matrixA,data.matrixB,vision_prompt=data.vision_prompt or '')
                completion=await run_with_context(None,lambda p=prompt: client.chat.completions.create(
                    model='qwen-plus',messages=[{'role':'user','content':p}]))
                code=(completion.choices[0].message.content or '').strip().replace('```python','').replace('```','').strip()
                code=_inject_autoscale_into_construct(code)
                model=ManimCodeModel(code=code)
                yield event('code_generated',message='代码已生成，正在准备渲染…',code=code,progress=30,part=part)
                preview=None
                async for update in repair_progress(lambda:_render_keyframe_with_repair(ManimKeyframeModel(code=code),request,budget),request,timeout=450):
                    if update['type']=='repair_result':preview=update['value']
                    elif update['type']=='repair_failed':
                        yield event('error',message=update['message'],part=part);return
                    else:yield event('rendering',message='正在生成关键帧；可修复的错误会自动分析并修复一次…',progress=35,part=part)
                if preview is None:return
                if isinstance(preview,dict) and preview.get('preview_url'):
                    if preview.get('repaired'):
                        code=preview['code'];model=ManimCodeModel(code=code)
                        yield event('code_generated',code=code,message='关键帧错误已修复，继续生成视频…',progress=35,part=part)
                    yield event('rendering',message='关键帧已就绪，正在生成视频…',preview_url=preview['preview_url'],progress=35,part=part)
                elif isinstance(preview,JSONResponse):
                    detail=json.loads(preview.body).get('message','预览失败')
                    yield event('error',message=detail+'；解答和代码已保留，请检查后手动重试。',part=part)
                    return
                if await request.is_disconnected(): return
                response=await _run_manim_with_repair(model,request,budget)
                try:
                    async for frame in response.body_iterator:
                        payload=json.loads(frame[6:])
                        kind=payload['type']
                        if kind=='complete':
                            yield event('complete',message='渲染完成',video_url=payload['video_url'],code=payload.get('code',code),progress=100,part=part)
                        elif kind=='error':
                            yield event('error',message=payload['message']+'；解答和代码已保留，请检查后手动重试。',part=part)
                            return
                        else:
                            yield event('rendering',message=payload.get('message','正在渲染…'),progress=40,part=part)
                finally:
                    await finish_cleanup(response.body_iterator.aclose())
        except asyncio.CancelledError: raise
        except Exception as error:
            logger.warning('Legacy animation failed: %s',type(error).__name__)
            yield event('error',message=llm_error_message(error))

    return StreamingResponse(event_generator(),media_type='text/event-stream',
        headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
