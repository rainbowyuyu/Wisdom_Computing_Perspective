# 智能识别、动态计算动画（含流式）
# 同步 LLM 调用需放入 run_in_executor，避免阻塞事件循环（渲染时可并发加载算式库、识别等）
import asyncio
import base64
import json
import logging
import os
import subprocess
import sys
import uuid
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from logic.manim_generator import render_matrix_animation
from logic.prompt import return_prompt

from ..config import client, api_key, VIDEOS_DIR
from ..models import CalcModel
from .agent import sanitize_latex_for_mathlive
from ..llm_errors import llm_error_message

logger = logging.getLogger(__name__)
router = APIRouter(tags=["detect"])


def _run_manim_subprocess_sync(cmd_list, cwd, put_fn):
    """在线程中运行 Manim 子进程，逐行通过 put_fn(('log', text)) 送出 stderr，最后 put_fn(('done', returncode, stderr_full))。"""
    try:
        proc = subprocess.Popen(
            cmd_list,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            cwd=cwd,
        )
        stderr_chunks = []
        for raw in iter(proc.stderr.readline, b""):
            stderr_chunks.append(raw)
            try:
                text = raw.decode("utf-8", errors="replace").rstrip()
                if text:
                    put_fn(("log", text))
            except Exception:
                pass
        proc.wait()
        err_full = b"".join(stderr_chunks).decode("utf-8", errors="replace")
        put_fn(("done", proc.returncode, err_full))
    except Exception as ex:
        logger.error(f"Manim subprocess: {ex}", exc_info=True)
        put_fn(("done", -1, str(ex) or repr(ex)))


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
        image_content = await file.read()
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
        completion = await loop.run_in_executor(
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
async def generate_animation(data: CalcModel):
    try:
        task_id = str(uuid.uuid4())
        video_path = render_matrix_animation(data.matrixA, data.matrixB, data.operation, task_id)
        if video_path and os.path.exists(video_path):
            filename = os.path.basename(video_path)
            return {"status": "success", "video_url": f"/videos/{filename}"}
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Failed")
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.post("/animate/stream")
async def generate_animation_stream(data: CalcModel):
    async def event_generator():
        # 所有模式都最先生成并返回解题步骤（文字结果），再执行计算/可视化
        try:
            text_prompt = (
                f"用户输入的数学表达式或题目为：{data.matrixA}\n\n"
                "请按以下**结构化格式**输出解题步骤，便于阅读与排版：\n"
                "1. 先写 **题目** 或 **题目要点** 一段概括。\n"
                "2. 若有选项（如 A/B/C/D），按 **A项**、**B项**、**C项**、**D项** 分段，每段内写该选项的极限或结论（行内公式用 $...$，独立公式用 $$...$$）。\n"
                "3. 若题目本身没有任何 A/B/C/D 等选项，请**不要额外说明“无选项”“故不设 A/B/C/D 项”等字样**，直接给出题目与解题步骤即可。\n"
                "4. 最后写 **结论** 或 **答案**，明确正确选项与理由（若无选项则给出最终结果与总结）。\n"
                "要求：分条、分项清晰，不要大段连写。**同一行内的整段公式必须放在一对 $ $ 内**，例如 $\\\\lim_{{x\\\\to 0}}\\\\frac{{x+\\\\cos x}}{{x}}$，不要将分子、分母或极限符号拆到不同行，避免 LaTeX 与文字错位。不要输出任何代码。"
            )
            loop = asyncio.get_event_loop()
            text_completion = await loop.run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model="qwen-plus",
                    messages=[{"role": "user", "content": text_prompt}],
                ),
            )
            text_result = (text_completion.choices[0].message.content or "").strip()
            if text_result:
                yield f"data: {json.dumps({'step': 'text_result', 'content': text_result})}\n\n"
        except Exception as e:
            logger.warning(f"Text result fallback: {e}")

        async def generate_preview_image(py_path: str, task_id: str, part_label: str | None = None, phase_name_text: str = ""):
            """
            使用 Manim 先快速渲染一张关键帧预览图，缓解等待视频渲染时的空窗。
            - 单阶段：task_id_preview.png
            - 双阶段：task_id_calc_preview.png / task_id_vis_preview.png
            失败时返回 None，不影响主渲染流程。
            """
            preview_suffix = f"_{part_label}" if part_label else ""
            preview_file = f"{task_id}{preview_suffix}_preview.png"
            media_dir = os.path.abspath(VIDEOS_DIR)
            cmd = [
                sys.executable,
                "-m",
                "manim",
                "-ql",
                "-s",
                "--media_dir",
                media_dir,
                "-o",
                preview_file,
                os.path.abspath(py_path),
                "GenScene",
            ]
            loop = asyncio.get_event_loop()
            try:
                proc = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=60,
                    ),
                )
            except Exception as e:
                logger.warning(
                    "Preview frame subprocess error (%s): %s",
                    phase_name_text or "single",
                    e,
                )
                return None

            if proc.returncode != 0:
                short_err = (proc.stderr or "")[-300:]
                logger.warning(
                    "Preview frame generation failed (%s): %s",
                    phase_name_text or "single",
                    short_err,
                )
                return None

            def locate_preview() -> str | None:
                for root, _, files in os.walk(media_dir):
                    if preview_file in files:
                        return os.path.join(root, preview_file)
                return None

            src = locate_preview()
            if not src:
                return None

            final_path = os.path.join(VIDEOS_DIR, preview_file)
            try:
                os.makedirs(VIDEOS_DIR, exist_ok=True)
            except Exception:
                pass

            try:
                import shutil

                if os.path.abspath(src) != os.path.abspath(final_path):
                    shutil.move(src, final_path)
            except Exception as e:
                if not os.path.exists(final_path):
                    logger.warning(
                        "Move preview frame failed (%s -> %s): %s", src, final_path, e
                    )
            return f"/videos/{preview_file}"

        # 若前端从识别页携带了视觉描述 Prompt，则在生成 Manim 代码时一并传入，
        # 帮助大模型理解图片中的几何/结构信息（如“这是单位圆”“有一条过原点的直线”等）。
        vision_prompt_text = getattr(data, "vision_prompt", None) or ""

        if data.operation == "normal":
            yield f"data: {json.dumps({'step': 'normal_split', 'message': '通用演示将分两步：先计算推演，再可视化演示', 'progress': 5})}\n\n"
            for (phase_name, part, op_desc) in [("计算", "calc", "公式推演"), ("可视化", "vis", "可视化演示")]:
                task_id = str(uuid.uuid4())
                yield f"data: {json.dumps({'step': 'generating_code', 'message': f'正在构思「{phase_name}」Manim 代码...', 'progress': 10})}\n\n"
                prompt = return_prompt(op_desc, data.matrixA, data.matrixB, vision_prompt=vision_prompt_text)
                code = ""
                try:
                    _loop = asyncio.get_event_loop()
                    completion = await _loop.run_in_executor(
                        None,
                        lambda p=prompt: client.chat.completions.create(model="qwen-plus", messages=[{"role": "user", "content": p}]),
                    )
                    code = completion.choices[0].message.content.strip().replace("```python", "").replace("```", "").strip()
                    code = _inject_autoscale_into_construct(code)
                    yield f"data: {json.dumps({'step': 'code_generated', 'message': f'「{phase_name}」代码生成完毕，准备渲染...', 'code': code, 'progress': 30, 'part': part})}\n\n"
                except Exception as e:
                    logger.error(f"LLM Error ({phase_name}): {e}")
                    yield f"data: {json.dumps({'step': 'error', 'message': f'「{phase_name}」生成失败: {str(e)}'})}\n\n"
                    continue
                py_filename = f"gen_{task_id}.py"
                py_path = os.path.join(VIDEOS_DIR, py_filename)
                try:
                    with open(py_path, "w", encoding="utf-8") as f:
                        f.write(code)
                except Exception as e:
                    logger.error(f"File Write Error: {e}")
                    yield f"data: {json.dumps({'step': 'error', 'message': '写入代码文件失败'})}\n\n"
                    continue
                media_dir = os.path.abspath(VIDEOS_DIR)
                output_file = f"{task_id}.mp4"

                # 先尝试生成关键帧预览图，前端会在渲染窗口中展示出来，缓解等待视频期间的焦虑
                try:
                    preview_url = await generate_preview_image(
                        py_path, task_id, part_label=part, phase_name_text=phase_name
                    )
                    if preview_url:
                        yield f"data: {json.dumps({'step': 'rendering', 'message': f'「{phase_name}」已生成关键帧预览', 'progress': 35, 'preview_url': preview_url, 'part': part})}\n\n"
                except Exception as e:
                    logger.warning(
                        "generate_preview_image error (%s): %s", phase_name, e
                    )

                cmd = [sys.executable, "-m", "manim", "-ql", "--media_dir", media_dir, "-o", output_file, os.path.abspath(py_path), "GenScene"]
                yield f"data: {json.dumps({'step': 'rendering', 'message': f'「{phase_name}」Manim 渲染中...', 'progress': 40})}\n\n"

                async def run_manim_stream_logs(cmd_list):
                    loop = asyncio.get_event_loop()
                    q = asyncio.Queue()
                    def put(item):
                        loop.call_soon_threadsafe(q.put_nowait, item)
                    loop.run_in_executor(None, lambda: _run_manim_subprocess_sync(cmd_list, os.path.dirname(os.path.abspath(py_path)), put))
                    while True:
                        item = await q.get()
                        yield item
                        if item[0] == "done":
                            break

                manim_returncode, manim_stderr = -1, ""
                async for item in run_manim_stream_logs(cmd):
                    if item[0] == "log":
                        yield f"data: {json.dumps({'step': 'rendering', 'message': item[1], 'progress': 40})}\n\n"
                    else:
                        manim_returncode, manim_stderr = item[1], item[2]
                        break

                def locate_video():
                    base_search_path = os.path.join(media_dir, "videos", py_filename.replace(".py", ""), "480p15")
                    expected_file = os.path.join(base_search_path, output_file)
                    if not os.path.exists(expected_file):
                        target_dir = os.path.join(media_dir, "videos", py_filename.replace(".py", ""), "480p15")
                        if os.path.exists(target_dir):
                            for f in os.listdir(target_dir):
                                if f.endswith(".mp4"):
                                    return os.path.join(target_dir, f)
                    return expected_file if os.path.exists(expected_file) else None

                found = locate_video()
                if manim_returncode == 0 and found:
                    import shutil
                    final_path = os.path.join(VIDEOS_DIR, output_file)
                    shutil.move(found, final_path)
                    final_url = f"/videos/{output_file}"
                    try:
                        os.remove(py_path)
                    except Exception:
                        pass
                    yield f"data: {json.dumps({'step': 'complete', 'message': f'「{phase_name}」渲染完成！', 'video_url': final_url, 'progress': 100, 'part': part, 'code': code})}\n\n"
                    continue
                err_msg = manim_stderr or "Unknown Error or Timeout"
                yield f"data: {json.dumps({'step': 'fixing_code', 'message': f'「{phase_name}」渲染报错，正在修正并重试...', 'progress': 35})}\n\n"
                fix_prompt = (
                    "上述 Manim 代码在渲染时报错，错误信息如下：\n\n```\n" + (err_msg[:3000] if err_msg else "Unknown Error") + "\n```\n\n"
                    "请根据错误信息修正代码。只输出完整 Python 代码，不要解释。必须保留 from manim import * 和类名 GenScene，所有动画在 def construct(self): 中。"
                )
                try:
                    _loop = asyncio.get_event_loop()
                    completion2 = await _loop.run_in_executor(
                        None,
                        lambda: client.chat.completions.create(
                            model="qwen-plus",
                            messages=[{"role": "user", "content": prompt}, {"role": "assistant", "content": code}, {"role": "user", "content": fix_prompt}],
                        ),
                    )
                    code2 = completion2.choices[0].message.content.strip().replace("```python", "").replace("```", "").strip()
                    code2 = _inject_autoscale_into_construct(code2)
                    with open(py_path, "w", encoding="utf-8") as f:
                        f.write(code2)
                    yield f"data: {json.dumps({'step': 'rendering', 'message': f'「{phase_name}」重新渲染中...', 'progress': 40})}\n\n"
                    manim_returncode2, manim_stderr2 = -1, ""
                    async for item in run_manim_stream_logs(cmd):
                        if item[0] == "log":
                            yield f"data: {json.dumps({'step': 'rendering', 'message': item[1], 'progress': 40})}\n\n"
                        else:
                            manim_returncode2, manim_stderr2 = item[1], item[2]
                            break
                    found2 = locate_video()
                    if manim_returncode2 == 0 and found2:
                        import shutil
                        final_path = os.path.join(VIDEOS_DIR, output_file)
                        shutil.move(found2, final_path)
                        final_url = f"/videos/{output_file}"
                        try:
                            os.remove(py_path)
                        except Exception:
                            pass
                        yield f"data: {json.dumps({'step': 'complete', 'message': f'「{phase_name}」修正后渲染完成！', 'video_url': final_url, 'progress': 100, 'part': part, 'code': code2})}\n\n"
                    else:
                        yield f"data: {json.dumps({'step': 'error', 'message': f'「{phase_name}」修正后仍失败，将继续下一阶段。'})}\n\n"
                except Exception as e:
                    logger.error(f"LLM fix Error ({phase_name}): {e}")
                    yield f"data: {json.dumps({'step': 'error', 'message': f'「{phase_name}」修正请求异常，将继续下一阶段。'})}\n\n"
            return

        task_id = str(uuid.uuid4())
        yield f"data: {json.dumps({'step': 'generating_code', 'message': '正在构思 Manim 代码...', 'progress': 10})}\n\n"
        prompt = generate_manim_prompt(data.matrixA, data.matrixB, data.operation, vision_prompt=vision_prompt_text)
        code = ""
        try:
            _loop = asyncio.get_event_loop()
            completion = await _loop.run_in_executor(
                None,
                lambda p=prompt: client.chat.completions.create(model="qwen-plus", messages=[{"role": "user", "content": p}]),
            )
            code = completion.choices[0].message.content.strip().replace("```python", "").replace("```", "").strip()
            code = _inject_autoscale_into_construct(code)
            yield f"data: {json.dumps({'step': 'code_generated', 'message': '代码生成完毕，准备渲染...', 'code': code, 'progress': 30})}\n\n"
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            yield f"data: {json.dumps({'step': 'error', 'message': f'生成失败: {str(e)}'})}\n\n"
            return

        py_filename = f"gen_{task_id}.py"
        py_path = os.path.join(VIDEOS_DIR, py_filename)
        try:
            with open(py_path, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception as e:
            logger.error(f"File Write Error: {e}")
            yield f"data: {json.dumps({'step': 'error', 'message': '写入代码文件失败'})}\n\n"
            return

        media_dir = os.path.abspath(VIDEOS_DIR)
        output_file = f"{task_id}.mp4"

        # 单阶段模式也先尝试生成一张关键帧预览图
        try:
            preview_url = await generate_preview_image(
                py_path, task_id, part_label=None, phase_name_text="单阶段"
            )
            if preview_url:
                yield f"data: {json.dumps({'step': 'rendering', 'message': '已生成关键帧预览，视频渲染中…', 'progress': 35, 'preview_url': preview_url})}\n\n"
        except Exception as e:
            logger.warning("generate_preview_image error (single): %s", e)

        py_abs_path = os.path.abspath(py_path)
        cmd = [sys.executable, "-m", "manim", "-ql", "--media_dir", media_dir, "-o", output_file, py_abs_path, "GenScene"]
        yield f"data: {json.dumps({'step': 'rendering', 'message': 'Manim 引擎启动中...', 'progress': 40})}\n\n"

        async def run_manim_stream_logs(cmd_list):
            loop = asyncio.get_event_loop()
            queue = asyncio.Queue()
            def put(item):
                loop.call_soon_threadsafe(queue.put_nowait, item)
            loop.run_in_executor(None, _run_manim_subprocess_sync, cmd_list, os.path.dirname(py_abs_path), put)
            while True:
                item = await queue.get()
                yield item
                if item[0] == "done":
                    break

        def locate_and_yield_complete():
            base_search_path = os.path.join(media_dir, "videos", py_filename.replace(".py", ""), "480p15")
            expected_file = os.path.join(base_search_path, output_file)
            if not os.path.exists(expected_file):
                if os.path.exists(os.path.join(media_dir, output_file)):
                    expected_file = os.path.join(media_dir, output_file)
                else:
                    target_dir = os.path.join(media_dir, "videos", py_filename.replace(".py", ""), "480p15")
                    if os.path.exists(target_dir):
                        for f in os.listdir(target_dir):
                            if f.endswith(".mp4"):
                                expected_file = os.path.join(target_dir, f)
                                break
            if os.path.exists(expected_file):
                import shutil
                final_path = os.path.join(VIDEOS_DIR, output_file)
                shutil.move(expected_file, final_path)
                final_url = f"/videos/{output_file}"
                try:
                    os.remove(py_path)
                except Exception:
                    pass
                return True, final_url
            return False, None

        manim_returncode = -1
        manim_stderr = ""
        async for item in run_manim_stream_logs(cmd):
            if item[0] == "log":
                yield f"data: {json.dumps({'step': 'rendering', 'message': item[1], 'progress': 40})}\n\n"
            else:
                manim_returncode, manim_stderr = item[1], item[2]
                break

        if manim_returncode == 0:
            yield f"data: {json.dumps({'step': 'rendering', 'message': '渲染完成，处理文件中...', 'progress': 90})}\n\n"
            ok, final_url = locate_and_yield_complete()
            if ok:
                yield f"data: {json.dumps({'step': 'complete', 'message': '渲染完成！', 'video_url': final_url, 'progress': 100})}\n\n"
            else:
                yield f"data: {json.dumps({'step': 'error', 'message': '渲染成功但未找到视频文件，请检查日志。'})}\n\n"
            return

        err_msg = manim_stderr or "Unknown Error or Timeout"
        yield f"data: {json.dumps({'step': 'fixing_code', 'message': '渲染报错，正在根据错误信息修正代码并重试...', 'progress': 35})}\n\n"
        fix_prompt = (
            "上述 Manim 代码在渲染时报错，错误信息如下：\n\n"
            "```\n" + (err_msg[:3000] if err_msg else "Unknown Error or Timeout") + "\n```\n\n"
            "请根据错误信息修正代码。要求：只输出修正后的完整 Python 代码，不要输出任何解释或 Markdown。"
            "必须保留 `from manim import *` 和类名 `GenScene`，所有动画逻辑在 `def construct(self):` 中。"
        )
        try:
            _loop = asyncio.get_event_loop()
            completion2 = await _loop.run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model="qwen-plus",
                    messages=[{"role": "user", "content": prompt}, {"role": "assistant", "content": code}, {"role": "user", "content": fix_prompt}],
                ),
            )
            code2 = completion2.choices[0].message.content.strip().replace("```python", "").replace("```", "").strip()
            code2 = _inject_autoscale_into_construct(code2)
            with open(py_path, "w", encoding="utf-8") as f:
                f.write(code2)
            yield f"data: {json.dumps({'step': 'rendering', 'message': 'Manim 重新渲染中...', 'progress': 40})}\n\n"
            manim_returncode2, manim_stderr2 = -1, ""
            async for item in run_manim_stream_logs(cmd):
                if item[0] == "log":
                    yield f"data: {json.dumps({'step': 'rendering', 'message': item[1], 'progress': 40})}\n\n"
                else:
                    manim_returncode2, manim_stderr2 = item[1], item[2]
                    break
            if manim_returncode2 == 0:
                yield f"data: {json.dumps({'step': 'rendering', 'message': '渲染完成，处理文件中...', 'progress': 90})}\n\n"
                ok, final_url = locate_and_yield_complete()
                if ok:
                    yield f"data: {json.dumps({'step': 'complete', 'message': '修正后渲染完成！', 'video_url': final_url, 'progress': 100})}\n\n"
                else:
                    yield f"data: {json.dumps({'step': 'error', 'message': '渲染成功但未找到视频文件，请检查日志。'})}\n\n"
            else:
                err_msg2 = manim_stderr2 or "Unknown Error or Timeout"
                short_err = err_msg2.split("\n")[-5:]
                error_msg = "已根据报错修正并重试一次，仍失败：\n" + "\n".join(short_err)
                yield "data: " + json.dumps({"step": "error", "message": error_msg}, ensure_ascii=False) + "\n\n"
        except Exception as e:
            logger.error(f"LLM fix Error: {e}")
            yield "data: " + json.dumps({"step": "error", "message": "渲染失败，且自动修正请求异常：\n" + str(e)}, ensure_ascii=False) + "\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
