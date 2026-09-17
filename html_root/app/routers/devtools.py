# 开发者工具：Manim 云端渲染（同步与流式）
# [安全] RCE 高危：用户代码在服务端执行。当前有简单关键字拦截与超时。
# 推荐：Docker/Firecracker 沙箱隔离 + 网络限制 + 资源限制，详见项目根目录 SECURITY.md
import ast
import tempfile
import time
from pathlib import Path
import asyncio
import json
import logging
import re
import os
import subprocess
import sys
import traceback
import uuid
from typing import Optional
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..config import VIDEOS_DIR, client, api_key
from ..llm_errors import llm_error_message
from .solve import ai_client, stop_process
from ..models import ManimCodeModel, ManimCodeEditModel, ManimKeyframeModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/devtools", tags=["devtools"])


def normalize_scene_code(code):
    """Accept one named Scene without changing strings, formulas or indentation."""
    tree=ast.parse(code)
    if any(isinstance(node,ast.ClassDef) and node.name=='GenScene' for node in tree.body):
        return code
    scenes=[node for node in tree.body if isinstance(node,ast.ClassDef)
            and any(isinstance(method,ast.FunctionDef) and method.name=='construct' for method in node.body)
            and any(isinstance(base,ast.Name) and base.id in {'Scene','MovingCameraScene','ThreeDScene'} for base in node.bases)]
    if any(node.name=='GenScene' for node in scenes): return code
    if len(scenes)!=1: raise ValueError('请提供唯一的 Manim Scene，或将要运行的场景命名为 GenScene。')
    node=scenes[0]
    # An alias preserves references to the original class within the script.
    return code.rstrip()+'\n\nclass GenScene('+node.name+'):\n    pass\n'


def _locate_manim_video(media_dir: str, output_file: str, py_path: str) -> Optional[str]:
    """Manim 渲染完成后查找并移动视频到 static/videos，返回 /videos/xxx.mp4 或 None。"""
    import shutil
    py_base = os.path.basename(py_path).replace(".py", "")
    final_path = os.path.join(media_dir, output_file)
    possible_paths = [
        os.path.join(media_dir, output_file),
        os.path.join(media_dir, "videos", py_base, "480p15", "GenScene.mp4"),
        os.path.join(media_dir, "videos", py_base, "480p15", output_file),
    ]
    for p in possible_paths:
        if os.path.exists(p):
            if os.path.abspath(p) != os.path.abspath(final_path):
                shutil.move(p, final_path)
            try:
                os.remove(py_path)
            except Exception:
                pass
            return f"/videos/{output_file}"
    td = os.path.join(media_dir, "videos", py_base, "480p15")
    if os.path.isdir(td):
        for f in os.listdir(td):
            if f.endswith(".mp4"):
                shutil.move(os.path.join(td, f), final_path)
                try:
                    os.remove(py_path)
                except Exception:
                    pass
                return f"/videos/{output_file}"
    if os.path.isdir(os.path.join(media_dir, "videos")):
        for root, _, files in os.walk(os.path.join(media_dir, "videos")):
            for f in files:
                if f.endswith(".mp4") and py_base in root:
                    shutil.move(os.path.join(root, f), final_path)
                    try:
                        os.remove(py_path)
                    except Exception:
                        pass
                    return f"/videos/{output_file}"
            break
    return None


def _locate_preview_png(media_dir: str, output_file: str, py_base: str) -> Optional[str]:
    """Manim -s 渲染后查找预览 PNG。"""
    import shutil
    for root, _, files in os.walk(media_dir):
        if output_file in files:
            src = os.path.join(root, output_file)
            final_path = os.path.join(media_dir, output_file)
            if os.path.abspath(src) != os.path.abspath(final_path):
                shutil.move(src, final_path)
            return final_path
    return None


def _apply_breakpoint(code: str, breakpoint_line: int) -> str:
    """Stop after the enclosing complete construct statement, including multiline calls."""
    tree = ast.parse(code)
    scene = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'GenScene'), None)
    construct = next((node for node in scene.body if isinstance(node, ast.FunctionDef) and node.name == 'construct'), None) if scene else None
    if scene and construct is None:
        parents=[node for node in tree.body if isinstance(node,ast.ClassDef) and any(isinstance(base,ast.Name) and base.id==node.name for base in scene.bases)]
        construct=next((method for parent in parents for method in parent.body if isinstance(method,ast.FunctionDef) and method.name=='construct'),None)
    if not construct: raise ValueError('需要 GenScene.construct 方法')
    statement = next((node for node in construct.body if node.lineno <= breakpoint_line <= node.end_lineno), None)
    if statement is None: raise ValueError('断点必须位于 construct 方法的可执行语句中')
    lines = code.splitlines(keepends=True)
    position = statement.end_lineno
    before = ''.join(lines[:position]).rstrip('\n')+'\n'
    return before + ' '*statement.col_offset + 'return  # preview boundary\n' + ''.join(lines[position:])


@router.post("/render_keyframe")
async def render_keyframe(data: ManimKeyframeModel, request: Request):
    proc=None; temporary=None; acquired=False
    try:
        code=normalize_scene_code(data.code)
        validate_edit_code(code)
        code=_apply_breakpoint(code,data.breakpoint_line) if data.breakpoint_line is not None else code
        while not acquired:
            if await request.is_disconnected(): return JSONResponse(status_code=499,content={'status':'error','message':'已停止预览'})
            try: await asyncio.wait_for(DEV_RENDER_SLOTS.acquire(),2);acquired=True
            except asyncio.TimeoutError: pass
        temporary=tempfile.TemporaryDirectory(prefix='wisdom-preview-');folder=Path(temporary.name)
        script=folder/'scene.py';script.write_text(code,encoding='utf-8')
        output=uuid.uuid4().hex+'_preview.png';log=folder/'render.log'
        cmd=[sys.executable,'-m','manim','-ql','-s','--disable_caching','--media_dir',str(folder),'-o',output,str(script),'GenScene']
        with log.open('w',encoding='utf-8') as writer:
            proc=subprocess.Popen(cmd,stdout=writer,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0,start_new_session=os.name!='nt')
            started=time.monotonic()
            while proc.poll() is None:
                if await request.is_disconnected(): return JSONResponse(status_code=499,content={'status':'error','message':'已停止预览'})
                if time.monotonic()-started>90: raise TimeoutError('预览超过90秒，请简化动画后重试')
                await asyncio.sleep(.2)
        if proc.returncode: raise ValueError(log.read_text(encoding='utf-8',errors='replace')[-2500:])
        candidates=list(folder.rglob(output))
        if not candidates: raise ValueError('未找到关键帧图像')
        import shutil
        shutil.copy2(candidates[0],Path(VIDEOS_DIR)/output)
        return {'status':'success','preview_url':'/videos/'+output}
    except asyncio.CancelledError: raise
    except Exception as error: return JSONResponse(status_code=400,content={'status':'error','message':str(error)[-2500:]})
    finally:
        if proc and proc.poll() is None: await asyncio.to_thread(stop_process,proc)
        if temporary: temporary.cleanup()
        if acquired: DEV_RENDER_SLOTS.release()


@router.post("/run_manim")
async def run_custom_manim(data: ManimCodeModel):
    forbidden = ["import os", "import sys", "import subprocess", "rm -rf", "shutil"]
    for keyword in forbidden:
        if keyword in data.code:
            return JSONResponse(status_code=400, content={"status": "error", "message": f"安全拦截: 禁止使用 '{keyword}'"})

    task_id = str(uuid.uuid4())
    py_filename = f"dev_{task_id}.py"
    py_path = os.path.join(VIDEOS_DIR, py_filename)
    media_dir = os.path.abspath(VIDEOS_DIR)
    output_file = f"{task_id}.mp4"

    try:
        with open(py_path, "w", encoding="utf-8") as f:
            f.write(data.code)
        cmd = [
            sys.executable, "-m", "manim",
            "-ql", "--media_dir", media_dir, "-o", output_file,
            os.path.abspath(py_path), "GenScene",
        ]
        logger.info(f"Running Manim DevTools: {' '.join(cmd)}")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60),
        )
        if result.returncode == 0:
            possible_paths = [
                os.path.join(media_dir, output_file),
                os.path.join(media_dir, "videos", py_filename.replace(".py", ""), "480p15", "GenScene.mp4"),
                os.path.join(media_dir, "videos", py_filename.replace(".py", ""), "480p15", output_file),
            ]
            final_path = os.path.join(VIDEOS_DIR, output_file)
            found = False
            for p in possible_paths:
                if os.path.exists(p):
                    import shutil
                    shutil.move(p, final_path)
                    found = True
                    break
            if found:
                try:
                    os.remove(py_path)
                except Exception:
                    pass
                return {"status": "success", "video_url": f"/videos/{output_file}"}
            logger.error(f"Render success but file not found. Search paths: {possible_paths}")
            return JSONResponse(status_code=500, content={"status": "error", "message": "渲染成功但未找到输出文件"})
        error_msg = result.stderr if result.stderr else result.stdout
        error_lines = [line for line in error_msg.split("\n") if "Error" in line or "Exception" in line or "Traceback" in line]
        if not error_lines:
            error_lines = error_msg.split("\n")[-10:]
        return JSONResponse(status_code=400, content={"status": "error", "message": "\n".join(error_lines)})
    except subprocess.TimeoutExpired:
        return JSONResponse(status_code=400, content={"status": "error", "message": "渲染超时"})
    except Exception as e:
        logger.error(f"run_custom_manim: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


DEV_RENDER_SLOTS = asyncio.Semaphore(2)


@router.post("/run_manim_stream")
async def run_manim_stream_endpoint(data: ManimCodeModel, request: Request):
    def event(kind, **values):
        return 'data: '+json.dumps({'type':kind,**values},ensure_ascii=False)+'\n\n'
    async def generate():
        proc=None; acquired=False; temporary=None
        try:
            code=normalize_scene_code(data.code)
            validate_edit_code(code)
            yield event('start',message='正在准备渲染资源…')
            while not acquired:
                if await request.is_disconnected(): return
                try: await asyncio.wait_for(DEV_RENDER_SLOTS.acquire(),5);acquired=True
                except asyncio.TimeoutError: yield event('heartbeat',message='正在等待渲染资源…')
            temporary=tempfile.TemporaryDirectory(prefix='wisdom-code-')
            folder=Path(temporary.name);script=folder/'scene.py';script.write_text(code,encoding='utf-8')
            output=uuid.uuid4().hex+'.mp4'
            cmd=[sys.executable,'-m','manim','-ql','--disable_caching','--media_dir',str(folder),'-o',output,str(script),'GenScene']
            log=folder/'render.log'
            with log.open('w',encoding='utf-8') as writer:
                proc=subprocess.Popen(cmd,stdout=writer,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0,
                    start_new_session=os.name!='nt')
                started=time.monotonic();offset=0
                while proc.poll() is None:
                    if await request.is_disconnected(): return
                    if time.monotonic()-started>240: raise TimeoutError('渲染超过4分钟，请缩短动画后重试。')
                    await asyncio.sleep(.3)
                    with log.open(encoding='utf-8',errors='replace') as reader:
                        reader.seek(offset);chunk=reader.read(16000);offset=reader.tell()
                    if chunk: yield event('log',message=chunk)
            logs=log.read_text(encoding='utf-8',errors='replace')
            if proc.returncode: raise ValueError(logs[-4000:] or 'Manim 渲染失败')
            candidates=list(folder.rglob(output))
            if not candidates: raise ValueError('渲染完成但未找到视频')
            import shutil
            shutil.copy2(candidates[0],Path(VIDEOS_DIR)/output)
            yield event('complete',video_url='/videos/'+output,message='渲染完成')
        except asyncio.CancelledError: raise
        except Exception as error: yield event('error',message=str(error)[-4000:])
        finally:
            if proc and proc.poll() is None: await asyncio.to_thread(stop_process,proc)
            if temporary: temporary.cleanup()
            if acquired: DEV_RENDER_SLOTS.release()
    return StreamingResponse(generate(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})


@router.post("/generate_video_copy")
async def generate_video_copy(data: ManimCodeModel):
    """
    根据 Manim 代码调用大模型生成视频文案（标题 + 简介 + 章节建议），
    供开发者工具「总结视频脚本内容」功能使用。
    """
    code = (data.code or "").strip()
    if not code:
        return JSONResponse(status_code=400, content={"status": "error", "message": "代码不能为空"})

    if len(code)>40000:
        return JSONResponse(status_code=400, content={"status":"error","message":"脚本超过40000字符，请精简后再总结"})
    snippet = code

    # Summaries must describe the actual source, not masquerade as generated output.
    if not api_key or client is None:
        return JSONResponse(status_code=503, content={"status":"error","message":"脚本说明尚未配置模型，请检查服务端设置。"})

    prompt = (
        "你是一名为 Manim 动画写简要说明的助手。下面是一段 Manim Python 代码，请用一两句话概括这段脚本在演示什么（例如：画了什么图、做了哪种动画、涉及什么知识点），用于在脚本库中区分不同脚本。\n\n"
        "要求：\n"
        "- 输出 1～3 句简短说明即可，不需要标题、简介、章节等完整文案；\n"
        "- 使用 Markdown，可分段或用列表，但保持简洁；\n"
        "- 只输出说明内容，不要解释思路。\n\n"
        "Manim 代码：\n"
        "```python\n" + snippet + "\n```"
    )

    try:
        completion = await ai_client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": prompt}],
        )
        text = completion.choices[0].message.content.strip()
        return {"status": "success", "copy": text}
    except Exception as e:
        logger.error(f"generate_video_copy error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "生成视频文案时出错：" + str(e)})


def _is_add_or_play_line(line: str) -> bool:
    """判断该行是否为 add/play 行（对象在此行才显示在画面上）"""
    line = line.strip()
    if re.search(r"self\.add\s*\(", line):
        return True
    if re.search(r"self\.play\s*\(", line):
        return True
    return False


def _get_keyframe_lines(code: str, instruction: str = "") -> list:
    """
    根据 Manim 规则提取关键帧断点行号（1-based）。
    对象在 add 或 play(Create/Write/Transform 等) 时才显示在画面上，定义行不显示。
    instruction 含「添加」时优先取最后一个（新增对象通常在末尾）。
    """
    add_pattern = re.compile(r"self\.add\s*\(")
    anim_keywords = re.compile(
        r"\b(Create|Write|Transform|ReplacementTransform|FadeIn|FadeOut|GrowFromCenter|DrawBorderThenFill)\s*\("
    )
    play_pattern = re.compile(r"self\.play\s*\(")
    lines = code.splitlines()
    add_lines = []
    play_anim_lines = []
    play_other_lines = []
    for i, line in enumerate(lines):
        ln = i + 1
        if add_pattern.search(line):
            add_lines.append(ln)
        elif play_pattern.search(line):
            if anim_keywords.search(line):
                play_anim_lines.append(ln)
            else:
                play_other_lines.append(ln)
    result = add_lines or play_anim_lines or play_other_lines
    if not result:
        return []
    # 「添加」类指令：新对象通常在最后，取最后一个 add/play
    if instruction and ("添加" in instruction or "add" in instruction.lower()):
        return [result[-1]]
    return result[:3]


def validate_edit_code(code):
    tree = ast.parse(code)
    scene = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'GenScene'), None)
    inherited = scene and any(isinstance(base,ast.Name) and any(isinstance(parent,ast.ClassDef) and parent.name==base.id and any(isinstance(n,ast.FunctionDef) and n.name=='construct' for n in parent.body) for parent in tree.body) for base in scene.bases)
    if scene is None or not (inherited or any(isinstance(n, ast.FunctionDef) and n.name == 'construct' for n in scene.body)):
        raise ValueError('请提供 class GenScene(Scene) 与 construct 方法')
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(n.name.split('.')[0] not in {'manim','numpy','math','random'} for n in node.names):
            raise ValueError('动画仅支持 manim、numpy、math、random 导入')
        if isinstance(node, ast.ImportFrom) and (node.level or (node.module or '').split('.')[0] not in {'manim','numpy','math','random'}):
            raise ValueError('动画包含不支持的导入')
        if isinstance(node, ast.Name) and (node.id.startswith('__') or node.id in {'eval','exec','open','compile','globals','locals','getattr','setattr','__import__'}):
            raise ValueError('动画包含不支持的动态执行或文件操作')
        if isinstance(node, ast.Attribute) and node.attr.startswith('__'):
            raise ValueError('动画不能访问内部属性')
    compile(tree, '<animation>', 'exec')
    return sorted({node.end_lineno for node in ast.walk(scene) if isinstance(node, ast.Expr)
                   and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                   and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == 'self'
                   and node.value.func.attr in {'play','add','wait'}})


@router.post("/edit_code")
async def edit_manim_code(data: ManimCodeEditModel):
    if not api_key:
        return JSONResponse(status_code=503, content={'status':'error','message':'代码助手尚未配置模型，请检查服务端设置。'})
    prompt = (
        '你是 Manim Community 代码助手。根据用户要求创建、修改或修复完整脚本。返回 JSON：'
        '{"code":"完整 Python 脚本","summary":"简明中文变更说明"}。'
        '使用 from manim import * 和 class GenScene(Scene)，实现 construct。空代码时从零创建。'
        '保留用户已有内容，只修改与需求有关的部分。使用 Create、TransformMatchingTex、Transform 等连续动画。'
        '不访问网络或文件系统，不调用命令，只可导入 manim、numpy、math、random。'
        '中文用 Text(font="Microsoft YaHei")，数学用 MathTex。颜色使用存在的 Manim 常量或十六进制字符串。'
        'summary 不得声称代码已经运行或渲染成功。完整代码不得截断，不要用省略号。'
    )
    messages=[{'role':'system','content':prompt},{'role':'user','content':json.dumps({
        'instruction':data.instruction, 'code':data.code, 'render_log':data.render_log or ''},ensure_ascii=False)}]
    try:
        for attempt in range(2):
            response=await ai_client.chat.completions.create(model='qwen-plus',messages=messages,
                response_format={'type':'json_object'},temperature=.2,max_tokens=10000)
            content=response.choices[0].message.content
            try:
                result=json.loads(content)
                code=result['code'].strip()
                if len(code)>40000: raise ValueError('脚本超过40000字符，请精简')
                lines=validate_edit_code(code)
                return {'status':'success','code':code,'summary':str(result.get('summary','已生成代码建议'))[:1200],
                        'keyframe_lines':lines[-1:],'validation':'syntax_checked'}
            except (ValueError, SyntaxError, KeyError, TypeError) as error:
                if attempt: raise
                messages += [{'role':'assistant','content':content},{'role':'user','content':f'代码检查失败：{error}。修正并输出完整 JSON。'}]
    except Exception as error:
        logger.warning('Code assistant failed: %s',type(error).__name__)
        return JSONResponse(status_code=502,content={'status':'error','message':llm_error_message(error)})
