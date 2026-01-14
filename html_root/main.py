# main.py
import os
import uuid
import base64
import logging
import random
import string
import hashlib
import bcrypt
from io import BytesIO
from fastapi import FastAPI, UploadFile, File, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import uvicorn
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import mysql.connector
from mysql.connector import pooling

# 引入生成器
from logic.manim_generator import render_matrix_animation

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()

# --- 配置部分 ---

# MySQL 配置 (建议从环境变量读取)
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "password")  # 请修改为你的密码
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
    # 不中断程序，允许静态文件服务运行，但数据库功能会报错
    db_pool = None

# 简单内存存储验证码
CAPTCHA_STORE = {}

# 1. 挂载静态文件
os.makedirs("static/videos", exist_ok=True)
app.mount("/videos", StaticFiles(directory="static/videos"), name="videos")

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


# --- 辅助函数：数据库操作 ---
def get_db_connection():
    if not db_pool:
        raise Exception("Database connection not initialized")
    return db_pool.get_connection()


# --- 辅助函数：生成验证码 (保持不变) ---
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


# --- API 路由 ---

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

        if cursor.rowcount == 0:
            return JSONResponse(status_code=404, content={"status": "error", "message": "未找到算式或无权修改"})

        return {"status": "success", "message": "更新成功"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.post("/api/detect")
async def detect_image(file: UploadFile = File(...)):
    # ... (保持不变) ...
    try:
        image_content = await file.read()
        base64_image = base64.b64encode(image_content).decode("utf-8")

        if not api_key:
            return {"status": "success", "latex": r"E = mc^2"}

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
    # ... (保持不变) ...
    try:
        task_id = str(uuid.uuid4())
        video_path = render_matrix_animation(data.matrixA, data.matrixB, data.operation, task_id)
        if video_path and os.path.exists(video_path):
            filename = os.path.basename(video_path)
            return {"status": "success", "video_url": f"/videos/{filename}"}
        raise HTTPException(status_code=500, detail="Failed")
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ... (前面的 API 定义保持不变) ...

# 1. 显式挂载静态资源目录
# 这样 /css/main.css, /js/main.js 等请求会直接被这里处理
app.mount("/css", StaticFiles(directory="static/css"), name="css")
app.mount("/js", StaticFiles(directory="static/js"), name="js")
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")
# 如果还有其他静态文件在 static 根目录下 (比如 update.md)，可以单独处理或移入子目录
# 这里为了兼容 update.md
app.mount("/static", StaticFiles(directory="static"), name="static_root")


# 2. 首页路由
@app.get("/")
async def read_index():
    return FileResponse("static/index.html")


# 3. 处理 update.md (前端 settings.js 请求的是 /update.md)
@app.get("/update.md")
async def read_update_log():
    if os.path.exists("static/update.md"):
        return FileResponse("static/update.md")
    if os.path.exists("update.md"):
        return FileResponse("update.md")
    raise HTTPException(status_code=404)


# 4. Catch-all (用于前端路由刷新)
# 把它放在最后，作为兜底
@app.exception_handler(404)
async def not_found_exception_handler(request, exc):
    # 如果请求的是 API 或 静态资源，返回 404
    path = request.url.path
    if path.startswith("/api/") or "." in path.split("/")[-1]:
        return JSONResponse(status_code=404, content={"message": "Not Found"})

    # 否则返回 index.html (支持 SPA 前端路由)
    return FileResponse("static/index.html")


# 移除原来的 app.mount("/", ...)
# 因为它会接管所有请求，导致上面的逻辑失效。
# 我们已经显式挂载了 /css, /js, /videos 等，主页由 @app.get("/") 处理。

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)