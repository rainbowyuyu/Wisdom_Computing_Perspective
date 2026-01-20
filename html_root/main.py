# main.py
import os
import uuid
import base64
import logging
import random
import bcrypt
import json
import asyncio
import sys
import subprocess  # 引入 subprocess 用于同步调用
from io import BytesIO
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import uvicorn
from PIL import Image, ImageDraw, ImageFont, ImageFilter
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
def generate_captcha_image_bytes():
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    text = ''.join(random.choices(chars, k=4))
    width, height = 120, 40
    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        font = ImageFont.load_default()
    for i, char in enumerate(text):
        x = 10 + i * 25 + random.randint(-2, 2)
        y = 5 + random.randint(-2, 2)
        draw.text((x, y), char, font=font, fill=(0, 0, 0))
    for _ in range(3):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=(150, 150, 150), width=1)
    image = image.filter(ImageFilter.GaussianBlur(0.5))
    buf = BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return text, buf


# --- API 路由 (Auth & CRUD) ---

@app.get("/api/captcha")
async def get_captcha():
    text, img_buf = generate_captcha_image_bytes()
    captcha_id = str(uuid.uuid4())
    CAPTCHA_STORE[captcha_id] = text.upper()
    return StreamingResponse(img_buf, media_type="image/png", headers={"X-Captcha-ID": captcha_id})


@app.post("/api/register")
async def register(data: AuthModel):
    # 1. 验证码校验
    stored_code = CAPTCHA_STORE.get(data.captcha_id)
    if not stored_code or stored_code != data.captcha.upper():
        return JSONResponse(status_code=400, content={"status": "error", "message": "验证码错误或已过期"})
    del CAPTCHA_STORE[data.captcha_id]

    # 2. 数据库操作
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 检查用户是否存在
        cursor.execute("SELECT id FROM users WHERE username = %s", (data.username,))
        if cursor.fetchone():
            return JSONResponse(status_code=400, content={"status": "error", "message": "用户名已存在"})

        # 加密密码
        hashed_pw = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()

        # 插入用户
        cursor.execute(
            "INSERT INTO users (username, hashed_password) VALUES (%s, %s)",
            (data.username, hashed_pw)
        )
        conn.commit()

        return {"status": "success", "message": "注册成功"}

    except Exception as e:
        logger.error(f"Register Error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.post("/api/login")
async def login(data: AuthModel):
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

        # 查询用户
        cursor.execute("SELECT * FROM users WHERE username = %s", (data.username,))
        user = cursor.fetchone()

        if not user:
            return JSONResponse(status_code=401, content={"status": "error", "message": "用户不存在"})

        # 验证密码
        if bcrypt.checkpw(data.password.encode(), user["hashed_password"].encode()):
            return {"status": "success", "username": user["username"]}
        else:
            return JSONResponse(status_code=401, content={"status": "error", "message": "密码错误"})
    except Exception as e:
        logger.error(f"Login Error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


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
    op_desc = {"add": "矩阵加法", "mul": "矩阵乘法", "det": "行列式计算", "other": "公式展示"}.get(operation,"数学展示")
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
            yield f"data: {json.dumps({'step': 'error', 'message': f'AI 生成失败: {str(e)}'})}\n\n"
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
                return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=180)
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
            # 截取部分错误信息展示
            short_err = err_msg.split('\n')[-5:] if result else ["Timeout"]
            error_msg = "渲染失败:\n" + "\n".join(short_err)

            payload = {
                "step": "error",
                "message": error_msg
            }

            yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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