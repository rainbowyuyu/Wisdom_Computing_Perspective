# main.py
import os
import uuid
import base64
import logging
import traceback
import bcrypt
import json
import asyncio
import sys
import subprocess  # 引入 subprocess 用于同步调用
from fastapi import FastAPI, UploadFile, File, HTTPException, Response, Request, Cookie, Query
from typing import Optional # 新增
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import uvicorn
import mysql.connector
import json # 确保引入
from typing import List

# 引入生成器
from logic.manim_generator import render_matrix_animation

# Windows: asyncio 子进程必须使用 ProactorEventLoop，否则 create_subprocess_exec 会报错
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()

# --- 配置部分 ---

# MySQL 配置
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "password")
MYSQL_DB = os.getenv("MYSQL_DB", "visdom_db")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))

# 创建 MySQL 连接池
try:
    db_pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="mypool",
        pool_size=5,
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        port=MYSQL_PORT
    )
    logger.info("MySQL connection pool created successfully")
except Exception as e:
    logger.error(f"Error creating MySQL pool: {e}")
    db_pool = None

# 简单内存存储验证码
CAPTCHA_STORE = {}

# 简单的内存 Session 存储 { "session_id": "username" }
# 注意：重启服务器会导致所有用户登出。生产环境请使用 Redis。
SESSION_STORE = {}

# 1. 挂载静态文件目录
os.makedirs("static/videos", exist_ok=True)
# 这里先不挂载 /videos，放在最后统一处理，避免路由冲突

# 2. 阿里云/OpenAI 客户端
api_key = os.getenv("ALIYUN_KEY")
client = OpenAI(
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    api_key=api_key or "sk-mock-key"
)


# --- 数据模型 ---
class AuthModel(BaseModel):
    username: str
    password: str
    captcha: str
    captcha_id: str


class CalcModel(BaseModel):
    matrixA: str
    matrixB: str
    operation: str


class FormulaModel(BaseModel):
    username: str
    latex: str
    note: str = ""

class FormulaUpdateModel(BaseModel):
    id: int
    username: str
    latex: str
    note: str


class AnimationScriptModel(BaseModel):
    username: str
    note: str = ""
    code: str


class AnimationScriptUpdateModel(BaseModel):
    id: int
    username: str
    note: str = ""
    code: str


# 定义响应模型
class ExampleVideo(BaseModel):
    filename: str
    title: str
    description: str
    url: str
    poster: str = ""  # 可选


@app.get("/api/examples")
async def get_examples():
    storage_dir = "static/assets/storage"
    metadata_path = os.path.join(storage_dir, "metadata.json")

    videos = []

    # 读取配置文件
    meta_dict = {}
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                meta_list = json.load(f)
                # 转为字典方便查找
                for item in meta_list:
                    meta_dict[item["filename"]] = item
        except Exception as e:
            logger.error(f"Metadata load error: {e}")

    # 扫描目录下所有 mp4 文件
    if os.path.exists(storage_dir):
        for file in os.listdir(storage_dir):
            if file.endswith(".mp4"):
                # 如果有元数据就用，没有就用默认值
                meta = meta_dict.get(file, {
                    "title": file,
                    "description": "暂无简介",
                    "poster": ""
                })

                videos.append({
                    "filename": file,
                    "title": meta.get("title", file),
                    "description": meta.get("description", "暂无简介"),
                    "url": f"/assets/storage/{file}",
                    "poster": meta.get("poster", "")  # 封面图路径，如果为空，前端处理
                })

    return {"status": "success", "data": videos}


# --- 辅助函数：数据库操作 ---
def get_db_connection():
    if not db_pool:
        raise Exception("Database connection not initialized")
    return db_pool.get_connection()


# --- 辅助函数：生成验证码  ---
from logic.captcha import generate_captcha_image_bytes

# --- API 路由 (Auth & CRUD) ---

@app.get("/api/captcha")
async def get_captcha():
    text, img_buf = generate_captcha_image_bytes()
    captcha_id = str(uuid.uuid4())
    CAPTCHA_STORE[captcha_id] = text.upper()

    # 清理过期验证码 (简单实现：如果太多就清空一半)
    if len(CAPTCHA_STORE) > 1000:
        keys = list(CAPTCHA_STORE.keys())
        for k in keys[:500]:
            del CAPTCHA_STORE[k]

    return StreamingResponse(img_buf, media_type="image/png", headers={"X-Captcha-ID": captcha_id})


@app.post("/api/register")
async def register(data: AuthModel):
    # ... (原有逻辑保持不变: 验证码校验 -> 数据库插入) ...
    # 1. 验证码校验
    stored_code = CAPTCHA_STORE.get(data.captcha_id)
    if not stored_code:
        return JSONResponse(status_code=400, content={"status": "error", "message": "验证码已过期，请刷新"})

    if stored_code != data.captcha.upper():
        return JSONResponse(status_code=400, content={"status": "error", "message": "验证码错误"})
    del CAPTCHA_STORE[data.captcha_id]

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE username = %s", (data.username,))
        if cursor.fetchone():
            return JSONResponse(status_code=400, content={"status": "error", "message": "用户名已存在"})

        # 加密密码
        hashed_pw = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
        cursor.execute("INSERT INTO users (username, hashed_password) VALUES (%s, %s)", (data.username, hashed_pw))
        conn.commit()
        return {"status": "success", "message": "注册成功"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.post("/api/login")
async def login(data: AuthModel, response: Response):  # 注入 Response 对象
    # 1. 验证码校验
    stored_code = CAPTCHA_STORE.get(data.captcha_id)
    if not stored_code or stored_code != data.captcha.upper():
        return JSONResponse(status_code=400, content={"status": "error", "message": "验证码错误"})
    del CAPTCHA_STORE[data.captcha_id]

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (data.username,))
        user = cursor.fetchone()

        if user and bcrypt.checkpw(data.password.encode(), user["hashed_password"].encode()):
            # --- 核心修改：生成 Session 并设置 Cookie ---
            session_id = str(uuid.uuid4())
            SESSION_STORE[session_id] = user["username"]

            # 设置 Cookie：key="auth_session", 有效期 1天 (86400秒), httponly 防止 XSS
            response.set_cookie(
                key="auth_session",
                value=session_id,
                max_age=86400,
                httponly=True,
                samesite="lax"
            )
            return {"status": "success", "username": user["username"]}
        else:
            return JSONResponse(status_code=401, content={"status": "error", "message": "用户名或密码错误"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# --- 新增：检查登录状态接口 (用于自动登录) ---
@app.get("/api/user/me")
async def get_current_user(auth_session: Optional[str] = Cookie(None)):
    if not auth_session:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Not logged in"})

    username = SESSION_STORE.get(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Session expired"})

    return {"status": "success", "username": username}


# --- 用户名查重：注册前检查是否已被占用 ---
@app.get("/api/user/check-username")
async def check_username(username: str = Query(..., max_length=64)):
    """检查用户名是否可用，用于注册前提示。"""
    raw = username.strip()
    if not raw:
        return {"available": False}
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE username = %s", (raw,))
        exists = cursor.fetchone() is not None
        return {"available": not exists}
    except Exception as e:
        return JSONResponse(status_code=500, content={"available": False, "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# --- 新增：登出接口 ---
@app.post("/api/logout")
async def logout(response: Response, auth_session: Optional[str] = Cookie(None)):
    if auth_session and auth_session in SESSION_STORE:
        del SESSION_STORE[auth_session]

    # 删除 Cookie
    response.delete_cookie(key="auth_session")
    return {"status": "success", "message": "Logged out"}


# --- 新增：我的算式功能 (MySQL版) ---
@app.post("/api/formulas/save")
async def save_formula(data: FormulaModel):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 简单检查用户存在（可选，通常依赖前端状态或Token）
        # 这里直接插入，利用外键约束报错
        cursor.execute(
            "INSERT INTO formulas (user_id, latex, note) VALUES (%s, %s, %s)",
            (data.username, data.latex, data.note)
        )
        conn.commit()
        return {"status": "success", "message": "保存成功"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.get("/api/formulas/list")
async def list_formulas(username: str):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM formulas WHERE user_id = %s ORDER BY created_at DESC", (username,))
        formulas = cursor.fetchall()
        # 处理 datetime 不可序列化问题 (如果有)
        for f in formulas:
            f['created_at'] = f['created_at'].isoformat()

        return {"status": "success", "data": formulas}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.delete("/api/formulas/delete")
async def delete_formula(id: int, username: str):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM formulas WHERE id = %s AND user_id = %s", (id, username))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.put("/api/formulas/update")
async def update_formula(data: FormulaUpdateModel):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 更新逻辑：必须同时匹配 id 和 username，防止越权修改
        cursor.execute(
            "UPDATE formulas SET latex = %s, note = %s WHERE id = %s AND user_id = %s",
            (data.latex, data.note, data.id, data.username)
        )
        conn.commit()
        if cursor.rowcount == 0: return JSONResponse(status_code=404,
                                                     content={"status": "error", "message": "未找到算式或无权修改"})
        return {"status": "success", "message": "更新成功"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# --- 动画脚本库 (Manim 代码保存与编辑) ---
@app.post("/api/animation_scripts/save")
async def save_animation_script(data: AnimationScriptModel):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO animation_scripts (user_id, note, code) VALUES (%s, %s, %s)",
            (data.username, data.note or "", data.code)
        )
        conn.commit()
        return {"status": "success", "message": "保存成功", "id": cursor.lastrowid}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.get("/api/animation_scripts/list")
async def list_animation_scripts(username: str):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, user_id, note, LEFT(code, 400) AS code_preview, created_at FROM animation_scripts WHERE user_id = %s ORDER BY created_at DESC",
            (username,)
        )
        rows = cursor.fetchall()
        for r in rows:
            r["created_at"] = r["created_at"].isoformat()
        return {"status": "success", "data": rows}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.get("/api/animation_scripts/get")
async def get_animation_script(id: int, username: str):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, note, code, created_at FROM animation_scripts WHERE id = %s AND user_id = %s",
            (id, username)
        )
        row = cursor.fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"status": "error", "message": "未找到脚本"})
        row["created_at"] = row["created_at"].isoformat()
        return {"status": "success", "data": row}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.delete("/api/animation_scripts/delete")
async def delete_animation_script(id: int, username: str):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM animation_scripts WHERE id = %s AND user_id = %s", (id, username))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.put("/api/animation_scripts/update")
async def update_animation_script(data: AnimationScriptUpdateModel):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE animation_scripts SET note = %s, code = %s WHERE id = %s AND user_id = %s",
            (data.note or "", data.code, data.id, data.username)
        )
        conn.commit()
        if cursor.rowcount == 0:
            return JSONResponse(status_code=404, content={"status": "error", "message": "未找到脚本或无权修改"})
        return {"status": "success", "message": "更新成功"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.post("/api/detect")
async def detect_image(file: UploadFile = File(...)):
    try:
        image_content = await file.read()
        base64_image = base64.b64encode(image_content).decode("utf-8")
        if not api_key: return {"status": "success", "latex": r"E = mc^2"}
        completion = client.chat.completions.create(
            model="qwen-vl-max",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "识别图片中的公式，只输出LaTeX代码。"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }]
        )
        latex = completion.choices[0].message.content.strip()
        latex = latex.replace("```latex", "").replace("```", "").replace("\\[", "").replace("\\]", "").strip()
        return {"status": "success", "latex": latex}
    except Exception as e:
        return {"status": "success", "latex": r"\text{Error}"}


@app.post("/api/animate")
async def generate_animation(data: CalcModel):
    try:
        task_id = str(uuid.uuid4())
        video_path = render_matrix_animation(data.matrixA, data.matrixB, data.operation, task_id)
        if video_path and os.path.exists(video_path):
            filename = os.path.basename(video_path)
            return {"status": "success", "video_url": f"/videos/{filename}"}
        raise HTTPException(status_code=500, detail="Failed")
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# --- SSE Stream ---

from logic.prompt import return_prompt


def _run_manim_subprocess_sync(cmd_list, cwd, put_fn):
    """在线程中运行 Manim 子进程，逐行通过 put_fn(('log', text)) 送出 stderr，最后 put_fn(('done', returncode, stderr_full))。兼容 Windows。"""
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

def generate_manim_prompt(latex_a, latex_b, operation):
    op_desc = {
        "formular": "公式推演",
        "visualization": "可视化演示",
        "normal": "通用演示",
    }.get(operation,"数学展示")
    return return_prompt(op_desc, latex_a, latex_b)


@app.post("/api/animate/stream")
async def generate_animation_stream(data: CalcModel):
    async def event_generator():
        task_id = str(uuid.uuid4())
        yield f"data: {json.dumps({'step': 'generating_code', 'message': 'AI 正在构思 Manim 代码...', 'progress': 10})}\n\n"

        prompt = generate_manim_prompt(data.matrixA, data.matrixB, data.operation)
        code = ""
        try:
            completion = client.chat.completions.create(
                model="qwen-plus",
                messages=[{"role": "user", "content": prompt}]
            )
            code = completion.choices[0].message.content.strip()
            code = code.replace("```python", "").replace("```", "").strip()
            yield f"data: {json.dumps({'step': 'code_generated', 'message': '代码生成完毕，准备渲染...', 'code': code, 'progress': 30})}\n\n"
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            yield f"data: {json.dumps({'step': 'error', 'message': f'生成失败: {str(e)}'})}\n\n"
            return

        py_filename = f"gen_{task_id}.py"
        py_path = os.path.join("static/videos", py_filename)
        os.makedirs("static/videos", exist_ok=True)
        try:
            with open(py_path, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception as e:
            logger.error(f"File Write Error: {e}")
            yield f"data: {json.dumps({'step': 'error', 'message': '写入代码文件失败'})}\n\n"
            return

        media_dir = os.path.abspath("static/videos")
        output_file = f"{task_id}.mp4"
        py_abs_path = os.path.abspath(py_path)

        # Manim 命令（渲染速度优化：-ql 为最低质量预设 480p15，渲染最快）
        cmd = [sys.executable, "-m", "manim", "-ql", "--media_dir", media_dir, "-o", output_file, py_abs_path,
               "GenScene"]
        logger.info(f"Executing command: {' '.join(cmd)}")
        yield f"data: {json.dumps({'step': 'rendering', 'message': 'Manim 引擎启动中...', 'progress': 40})}\n\n"

        async def run_manim_stream_logs(cmd_list):
            """运行 Manim 并逐行 yield stderr，最后 yield (returncode, stderr_full)。使用线程内同步子进程，兼容 Windows。"""
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
                final_path = os.path.join("static/videos", output_file)
                import shutil
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
                manim_returncode = item[1]
                manim_stderr = item[2]
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
        logger.error(f"Manim Error: {err_msg}")

        # 自动修正：将错误信息发给大模型，修正代码后重试一次
        yield f"data: {json.dumps({'step': 'fixing_code', 'message': '渲染报错，正在根据错误信息修正代码并重试...', 'progress': 35})}\n\n"
        fix_prompt = (
            "上述 Manim 代码在渲染时报错，错误信息如下：\n\n"
            "```\n" + (err_msg[:3000] if err_msg else "Unknown Error or Timeout") + "\n```\n\n"
            "请根据错误信息修正代码。要求：只输出修正后的完整 Python 代码，不要输出任何解释或 Markdown。"
            "必须保留 `from manim import *` 和类名 `GenScene`，所有动画逻辑在 `def construct(self):` 中。"
        )
        fix_messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": code},
            {"role": "user", "content": fix_prompt}
        ]
        try:
            completion2 = client.chat.completions.create(model="qwen-plus", messages=fix_messages)
            code2 = completion2.choices[0].message.content.strip()
            code2 = code2.replace("```python", "").replace("```", "").strip()
            with open(py_path, "w", encoding="utf-8") as f:
                f.write(code2)
            yield f"data: {json.dumps({'step': 'code_generated', 'message': '已根据报错修正代码，正在重新渲染...', 'code': code2, 'progress': 30})}\n\n"
            yield f"data: {json.dumps({'step': 'rendering', 'message': 'Manim 重新渲染中...', 'progress': 40})}\n\n"
        except Exception as e:
            logger.error(f"LLM fix Error: {e}")
            payload = {"step": "error", "message": "渲染失败，且自动修正请求异常：\n" + str(e)}
            yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
            return

        manim_returncode2 = -1
        manim_stderr2 = ""
        async for item in run_manim_stream_logs(cmd):
            if item[0] == "log":
                yield f"data: {json.dumps({'step': 'rendering', 'message': item[1], 'progress': 40})}\n\n"
            else:
                manim_returncode2 = item[1]
                manim_stderr2 = item[2]
                break
        if manim_returncode2 == 0:
            yield f"data: {json.dumps({'step': 'rendering', 'message': '渲染完成，处理文件中...', 'progress': 90})}\n\n"
            ok, final_url = locate_and_yield_complete()
            if ok:
                yield f"data: {json.dumps({'step': 'complete', 'message': '修正后渲染完成！', 'video_url': final_url, 'progress': 100})}\n\n"
            else:
                yield f"data: {json.dumps({'step': 'error', 'message': '渲染成功但未找到视频文件，请检查日志。'})}\n\n"
            return

        err_msg2 = manim_stderr2 or "Unknown Error or Timeout"
        if manim_returncode2 == -1 or not err_msg2:
            error_msg = "已根据报错修正并重试一次，仍然超时。请尝试简化算式或稍后再试。"
        else:
            short_err = err_msg2.split("\n")[-5:]
            error_msg = "已根据报错修正并重试一次，仍失败：\n" + "\n".join(short_err)
        yield "data: " + json.dumps({"step": "error", "message": error_msg}, ensure_ascii=False) + "\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class ManimCodeModel(BaseModel):
    code: str


class AgentRequest(BaseModel):
    """智能体：自然语言 + 可选图片"""
    prompt: str
    image_base64: Optional[str] = None


# main.py

@app.post("/api/devtools/run_manim")
async def run_custom_manim(data: ManimCodeModel):
    # 1. 安全检查 (稍微放宽，防止误杀)
    # 注意：这种基于字符串的检查非常脆弱，生产环境建议使用沙箱 (Docker/NSjail)
    forbidden = ["import os", "import sys", "import subprocess", "rm -rf", "shutil"]
    for keyword in forbidden:
        if keyword in data.code:
            return JSONResponse(status_code=400,
                                content={"status": "error", "message": f"安全拦截: 禁止使用 '{keyword}'"})

    task_id = str(uuid.uuid4())
    py_filename = f"dev_{task_id}.py"
    py_path = os.path.join("static/videos", py_filename)

    try:
        # 写入代码
        with open(py_path, "w", encoding="utf-8") as f:
            f.write(data.code)

        media_dir = os.path.abspath("static/videos")
        output_file = f"{task_id}.mp4"

        # 2. 构造命令
        # -ql: 低质量快速渲染（480p15），已为 Manim 最快预设
        # 不传 --disable_caching：保留缓存，相同代码再次运行可复用缓存以加速
        cmd = [
            sys.executable, "-m", "manim",
            "-ql",
            "--media_dir", media_dir,
            "-o", output_file,
            os.path.abspath(py_path),
            "GenScene"  # 确保前端传来的代码里类名也是 GenScene
        ]

        logger.info(f"Running Manim DevTools: {' '.join(cmd)}")

        # 3. 执行
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60
        ))

        # 4. 处理结果
        if result.returncode == 0:
            # 查找文件逻辑
            # Manim 的输出路径结构通常是: /media_dir/videos/filename/quality/scene_name.mp4
            # 或者由 -o 参数强行指定

            # 优先检查 -o 指定的直接路径
            # 注意：Manim 的 -o 参数行为比较诡异，它有时只作为文件名，路径还是遵循目录结构

            # 兼容性查找：递归搜索 media_dir 下所有新生成的 mp4
            # 这里我们简化逻辑：尝试几个可能的路径

            possible_paths = [
                # 1. 绝对路径指定 (理想情况)
                os.path.join(media_dir, output_file),
                # 2. 默认结构: videos/dev_xxx/480p15/GenScene.mp4 (如果 -o 无效)
                os.path.join(media_dir, "videos", py_filename.replace(".py", ""), "480p15", "GenScene.mp4"),
                # 3. 指定了文件名: videos/dev_xxx/480p15/uuid.mp4
                os.path.join(media_dir, "videos", py_filename.replace(".py", ""), "480p15", output_file)
            ]

            final_path = os.path.join("static/videos", output_file)
            found = False

            for p in possible_paths:
                if os.path.exists(p):
                    # 移动到静态资源根目录
                    import shutil
                    shutil.move(p, final_path)
                    found = True
                    break

            if found:
                # 清理
                try:
                    os.remove(py_path)
                except:
                    pass
                return {"status": "success", "video_url": f"/videos/{output_file}"}
            else:
                logger.error(f"Render success but file not found. Search paths: {possible_paths}")
                return JSONResponse(status_code=500, content={"status": "error", "message": "渲染成功但未找到输出文件"})

        else:
            # 执行失败
            logger.error(f"Manim Stderr: {result.stderr}")
            logger.error(f"Manim Stdout: {result.stdout}")

            # 返回更有意义的错误信息给前端
            error_msg = result.stderr if result.stderr else result.stdout
            # 过滤掉一些无关的进度条信息
            error_lines = [line for line in error_msg.split('\n') if
                           'Error' in line or 'Exception' in line or 'Traceback' in line]
            if not error_lines:
                error_lines = error_msg.split('\n')[-10:]  # 取最后10行

            return JSONResponse(status_code=400, content={"status": "error", "message": "\n".join(error_lines)})

    except subprocess.TimeoutExpired:
        return JSONResponse(status_code=408, content={"status": "error", "message": "渲染超时 (60s)"})
    except Exception as e:
        logger.error(f"Server Error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/devtools/run_manim_stream")
async def run_manim_stream_endpoint(data: ManimCodeModel):
    """Manim 云端渲染（SSE 流式），向前端推送实时日志与结果。"""
    forbidden = ["import os", "import sys", "import subprocess", "rm -rf", "shutil"]
    for keyword in forbidden:
        if keyword in data.code:
            def err():
                yield f"data: {json.dumps({'type': 'error', 'message': f'安全拦截: 禁止使用 {keyword}'})}\n\n"
            return StreamingResponse(err(), media_type="text/event-stream")

    task_id = str(uuid.uuid4())
    py_filename = f"dev_{task_id}.py"
    py_path = os.path.join("static/videos", py_filename)
    media_dir = os.path.abspath("static/videos")
    output_file = f"{task_id}.mp4"

    async def event_stream():
        try:
            os.makedirs(media_dir, exist_ok=True)
            with open(py_path, "w", encoding="utf-8") as f:
                f.write(data.code)
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
            return

        cmd = [
            sys.executable, "-m", "manim", "-ql",
            "--media_dir", media_dir, "-o", output_file,
            os.path.abspath(py_path), "GenScene"
        ]
        yield f"data: {json.dumps({'type': 'start', 'message': 'Manim 引擎启动中...'})}\n\n"

        def _run_manim_sync(cmd_list, put_sentinel):
            """在线程中运行 Manim 子进程，逐行把 stderr 通过 put_sentinel(line) 送出，最后 put_sentinel(('done', returncode, stderr_text))。"""
            proc = subprocess.Popen(
                cmd_list,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                cwd=None,
            )
            stderr_chunks = []
            try:
                for raw in iter(proc.stderr.readline, b""):
                    stderr_chunks.append(raw)
                    try:
                        text = raw.decode("utf-8", errors="replace").strip()
                        if text:
                            put_sentinel(("line", text))
                    except Exception:
                        pass
            finally:
                proc.wait()
                err_full = b"".join(stderr_chunks).decode("utf-8", errors="replace")
                put_sentinel(("done", proc.returncode, err_full))

        try:
            loop = asyncio.get_event_loop()
            queue = asyncio.Queue()

            def put(item):
                loop.call_soon_threadsafe(queue.put_nowait, item)

            loop.run_in_executor(None, _run_manim_sync, cmd, put)

            returncode = -1
            stderr_full = ""
            while True:
                try:
                    kind = await asyncio.wait_for(queue.get(), timeout=300.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'error', 'message': '渲染超时'}, ensure_ascii=False)}\n\n"
                    return
                if kind[0] == "line":
                    yield f"data: {json.dumps({'type': 'log', 'message': kind[1]}, ensure_ascii=False)}\n\n"
                else:
                    returncode = kind[1]
                    stderr_full = kind[2]
                    break

            if returncode != 0:
                err_text = (stderr_full or "渲染失败")[-2000:]
                yield f"data: {json.dumps({'type': 'error', 'message': err_text}, ensure_ascii=False)}\n\n"
                return

            import shutil
            py_base = py_filename.replace(".py", "")
            final_path = os.path.join(media_dir, output_file)
            possible_paths = [
                os.path.join(media_dir, output_file),
                os.path.join(media_dir, "videos", py_base, "480p15", "GenScene.mp4"),
                os.path.join(media_dir, "videos", py_base, "480p15", output_file),
            ]
            found = False
            for p in possible_paths:
                if os.path.exists(p):
                    if os.path.abspath(p) != os.path.abspath(final_path):
                        shutil.move(p, final_path)
                    found = True
                    break
            if not found:
                td = os.path.join(media_dir, "videos", py_base, "480p15")
                if os.path.isdir(td):
                    for f in os.listdir(td):
                        if f.endswith(".mp4"):
                            shutil.move(os.path.join(td, f), final_path)
                            found = True
                            break
            if not found and os.path.isdir(os.path.join(media_dir, "videos")):
                for root, _, files in os.walk(os.path.join(media_dir, "videos")):
                    for f in files:
                        if f.endswith(".mp4") and py_base in root:
                            shutil.move(os.path.join(root, f), final_path)
                            found = True
                            break
                    if found:
                        break

            if found:
                try:
                    os.remove(py_path)
                except Exception:
                    pass
                yield f"data: {json.dumps({'type': 'complete', 'video_url': f'/videos/{output_file}'})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'message': '渲染成功但未找到输出文件'})}\n\n"
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'message': '渲染超时'})}\n\n"
        except Exception as e:
            msg = str(e).strip() or repr(e)
            logger.error("run_manim_stream: %s\n%s", msg, traceback.format_exc())
            yield f"data: {json.dumps({'type': 'error', 'message': msg}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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


@app.post("/api/agent/execute")
async def agent_execute(data: AgentRequest):
    """智能体：理解用户意图，返回要跳转的页面与预填/触发的动作，由前端调用本站工具完成。"""
    latex_from_image = None
    if data.image_base64:
        try:
            base64_image = data.image_base64.replace("data:image/jpeg;base64,", "").replace("data:image/png;base64,", "").strip()
            if not api_key:
                latex_from_image = r"E = mc^2"
            else:
                completion = client.chat.completions.create(
                    model="qwen-vl-max",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "识别图片中的公式，只输出LaTeX代码，不要任何解释。"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }]
                )
                latex_from_image = completion.choices[0].message.content.strip()
                latex_from_image = latex_from_image.replace("```latex", "").replace("```", "").replace("\\[", "").replace("\\]", "").strip()
        except Exception as e:
            logger.error(f"Agent image recognition: {e}")
            return JSONResponse(status_code=200, content={"status": "error", "message": "图片识别失败：" + str(e)})

    prompt_for_llm = (
        "本网站包含以下功能页面：detect=智能识别（手写/上传识别公式）、calculate=动态计算（输入公式生成动画）、"
        "devtools=开发者工具（含 LaTeX 编辑器、Manim 工作台、Rainbow 拓展库）、my-formulas=我的算式、examples=教学案例、help=帮助。\n\n"
        "用户说：" + data.prompt + "\n\n"
        + ("用户上传了图片，识别到的公式为：" + latex_from_image + "。若需用到公式请以此为准。" if latex_from_image else "用户未上传图片，若需公式请从描述中提取 LaTeX。")
        + '\n\n请只输出一个 JSON，不要其他文字。格式：{"section":"detect|calculate|devtools|my-formulas|examples|help", "devtool":"latex|manim|rainbow"(仅当 section 为 devtools 时), '
        '"formula":"LaTeX 公式或空", "operation":"formular|visualization|normal"(仅当 section 为 calculate 时), "trigger":"generate|recognize|none"}。'
        "trigger：用户要立刻生成动画填 generate；仅识别/展示结果填 recognize；只跳转不执行填 none。"
    )
    try:
        completion = client.chat.completions.create(model="qwen-plus", messages=[{"role": "user", "content": prompt_for_llm}])
        raw = completion.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()
        import re
        section_match = re.search(r'"section"\s*:\s*"(detect|calculate|devtools|my-formulas|examples|help)"', raw)
        devtool_match = re.search(r'"devtool"\s*:\s*"(latex|manim|rainbow)"', raw)
        latex_match = re.search(r'"formula"\s*:\s*"([^"]*)"', raw)
        op_match = re.search(r'"operation"\s*:\s*"(formular|visualization|normal)"', raw)
        trigger_match = re.search(r'"trigger"\s*:\s*"(generate|recognize|none)"', raw)
        section = section_match.group(1) if section_match else "calculate"
        devtool = devtool_match.group(1) if devtool_match else None
        formula = (latex_match.group(1).replace("\\n", "\n").strip() if latex_match and latex_match.group(1) else (latex_from_image or ""))
        operation = op_match.group(1) if op_match else "normal"
        trigger = trigger_match.group(1) if trigger_match else "none"
        if formula and not formula.strip():
            formula = latex_from_image or ""
        return {
            "status": "success",
            "section": section,
            "devtool": devtool,
            "formula": formula,
            "operation": operation,
            "trigger": trigger,
            "message": "已为您跳转到对应步骤"
        }
    except Exception as e:
        logger.error(f"Agent LLM parse: {e}")
        return JSONResponse(status_code=200, content={"status": "error", "message": "理解您的描述时出错：" + str(e)})


# --- 静态资源与路由 ---
app.mount("/css", StaticFiles(directory="static/css"), name="css")
app.mount("/js", StaticFiles(directory="static/js"), name="js")
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")
app.mount("/docs", StaticFiles(directory="static/docs"), name="docs")
# /videos 单独挂载
app.mount("/videos", StaticFiles(directory="static/videos"), name="videos")
# 根静态
app.mount("/static", StaticFiles(directory="static"), name="static_root")


@app.get("/")
async def read_index():
    return FileResponse("static/index.html")


@app.get("/update.md")
async def read_update_log():
    if os.path.exists("static/docs/update.md"):
        return FileResponse("static/docs/update.md")
    if os.path.exists("update.md"):
        return FileResponse("update.md")
    raise HTTPException(status_code=404)


@app.exception_handler(404)
async def not_found_exception_handler(request, exc):
    path = request.url.path
    if path.startswith("/api/") or "." in path.split("/")[-1]:
        return JSONResponse(status_code=404, content={"message": "Not Found"})
    return FileResponse("static/index.html")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)