# main.py
import os
import uuid
import base64
import logging
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

        # Manim 命令
        cmd = [sys.executable, "-m", "manim", "-ql", "--media_dir", media_dir, "-o", output_file, py_abs_path,
               "GenScene"]
        logger.info(f"Executing command: {' '.join(cmd)}")
        yield f"data: {json.dumps({'step': 'rendering', 'message': 'Manim 引擎启动中(同步模式)...', 'progress': 40})}\n\n"

        # --- 核心：同步执行函数 ---
        def run_manim_sync():
            try:
                # capture_output=True 捕获输出，text=True 返回字符串
                # Windows 下这个同步调用是最稳定的
                return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=300)
            except subprocess.TimeoutExpired:
                return None
            except Exception as ex:
                logger.error(f"Subprocess Error: {ex}")
                return None

        # --- 核心：在线程池中执行 ---
        loop = asyncio.get_running_loop()
        # run_in_executor(None, func) 使用默认线程池
        # 这里会等待直到渲染完成，期间不会阻塞主线程（其他 API 可用）
        # 但流式进度条会停留在 40%，直到这一行执行完毕
        result = await loop.run_in_executor(None, run_manim_sync)

        # 渲染结束后手动更新进度
        if result and result.returncode == 0:
            yield f"data: {json.dumps({'step': 'rendering', 'message': '渲染完成，处理文件中...', 'progress': 90})}\n\n"

            # 文件检查逻辑
            base_search_path = os.path.join(media_dir, "videos", py_filename.replace(".py", ""), "480p15")
            expected_file = os.path.join(base_search_path, output_file)

            # 兼容性搜索：如果 -o 参数生效位置不同，尝试直接找输出文件
            if not os.path.exists(expected_file):
                # 尝试在 media_dir 根目录找
                if os.path.exists(os.path.join(media_dir, output_file)):
                    expected_file = os.path.join(media_dir, output_file)
                # 尝试遍历
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
                except:
                    pass
                yield f"data: {json.dumps({'step': 'complete', 'message': '渲染完成！', 'video_url': final_url, 'progress': 100})}\n\n"
            else:
                logger.error("Video file not found.")
                yield f"data: {json.dumps({'step': 'error', 'message': '渲染成功但未找到视频文件，请检查日志。'})}\n\n"
        else:
            err_msg = result.stderr if result else "Unknown Error or Timeout"
            logger.error(f"Manim Error: {err_msg}")
            # 超时时给出友好提示：让用户知道是服务器性能与算式复杂度导致
            if result is None:
                error_msg = (
                    "渲染超时：当前算式或动画较复杂，受服务器性能与算力限制，处理时间超过了允许上限。"
                    "请尝试简化算式或稍后再试。"
                )
            else:
                short_err = err_msg.split('\n')[-5:]
                error_msg = "渲染失败:\n" + "\n".join(short_err)

            payload = {
                "step": "error",
                "message": error_msg
            }

            yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class ManimCodeModel(BaseModel):
    code: str


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
        # -ql: 低质量快速渲染
        # --disable_caching: 禁用缓存，防止旧文件干扰
        # --format=mp4: 强制 mp4
        cmd = [
            sys.executable, "-m", "manim",
            "-ql",
            "--media_dir", media_dir,
            "-o", output_file,
            "--disable_caching",
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
    # Windows 平台不需要额外策略设置了，因为我们使用了同步 run_in_executor
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)