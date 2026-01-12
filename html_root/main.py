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
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import uvicorn
from supabase import create_client, Client
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# 引入生成器
from logic.manim_generator import render_matrix_animation

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()

# --- 配置部分 ---
# Supabase 配置 (建议放入 .env，这里为了对应 login.py 直接使用)
SUPABASE_URL = "https://fzmjkkiaibpjevtaeasl.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ6bWpra2lhaWJwamV2dGFlYXNsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUxMTUwMjgsImV4cCI6MjA2MDY5MTAyOH0.3ElNnjol9x6qq1_kVbgVzu6gmAz4iC-Is63yWBB-aO4"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 简单内存存储验证码 (生产环境建议用 Redis)
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


# --- 辅助函数：生成验证码 ---
def generate_captcha_image_bytes():
    # 生成随机字符
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    text = ''.join(random.choices(chars, k=4))  # 4位验证码

    width, height = 120, 40
    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    # 尝试加载字体
    try:
        # 尝试系统字体，Linux/Windows路径可能不同，这里简单fallback
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        font = ImageFont.load_default()

    # 绘制字符
    for i, char in enumerate(text):
        x = 10 + i * 25 + random.randint(-2, 2)
        y = 5 + random.randint(-2, 2)
        draw.text((x, y), char, font=font, fill=(0, 0, 0))

    # 干扰线
    for _ in range(3):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=(150, 150, 150), width=1)

    # 模糊
    image = image.filter(ImageFilter.GaussianBlur(0.5))

    buf = BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return text, buf


# --- API 路由 ---

@app.get("/api/captcha")
async def get_captcha():
    """获取验证码图片和ID"""
    text, img_buf = generate_captcha_image_bytes()
    captcha_id = str(uuid.uuid4())
    # 存入内存，有效期逻辑需自行扩展，这里仅演示
    CAPTCHA_STORE[captcha_id] = text.upper()

    # 将 ID 放入 Header 返回，图片放入 Body
    return StreamingResponse(img_buf, media_type="image/png", headers={"X-Captcha-ID": captcha_id})


@app.post("/api/register")
async def register(data: AuthModel):
    # 1. 校验验证码
    stored_code = CAPTCHA_STORE.get(data.captcha_id)
    if not stored_code or stored_code != data.captcha.upper():
        return JSONResponse(status_code=400, content={"status": "error", "message": "验证码错误或已过期"})

    # 销毁验证码 (一次性)
    del CAPTCHA_STORE[data.captcha_id]

    # 2. 检查用户名是否存在
    try:
        existing = supabase.table("users").select("*").eq("username", data.username).execute()
        if existing.data:
            return JSONResponse(status_code=400, content={"status": "error", "message": "用户名已存在"})

        # 3. 加密密码 & 生成 ID
        hashed_pw = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()

        # 模仿 login.py 的 ID 生成逻辑
        user_uuid = str(uuid.uuid4())
        user_id_int = int(hashlib.md5(user_uuid.encode()).hexdigest(), 16) % 10000

        # 4. 插入数据库
        supabase.table("users").insert({
            "id": user_id_int,
            "username": data.username,
            "hashed_password": hashed_pw
        }).execute()

        return {"status": "success", "message": "注册成功"}

    except Exception as e:
        logger.error(f"Register Error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/login")
async def login(data: AuthModel):
    # 1. 校验验证码
    stored_code = CAPTCHA_STORE.get(data.captcha_id)
    if not stored_code or stored_code != data.captcha.upper():
        return JSONResponse(status_code=400, content={"status": "error", "message": "验证码错误"})

    del CAPTCHA_STORE[data.captcha_id]

    # 2. 查询用户
    try:
        user_res = supabase.table('users').select("*").eq('username', data.username).execute()
        if not user_res.data:
            return JSONResponse(status_code=401, content={"status": "error", "message": "用户不存在"})

        user = user_res.data[0]
        stored_hash = user["hashed_password"]

        # 3. 验证密码
        if bcrypt.checkpw(data.password.encode(), stored_hash.encode()):
            return {"status": "success", "username": user["username"]}
        else:
            return JSONResponse(status_code=401, content={"status": "error", "message": "密码错误"})

    except Exception as e:
        logger.error(f"Login Error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/detect")
async def detect_image(file: UploadFile = File(...)):
    try:
        image_content = await file.read()
        base64_image = base64.b64encode(image_content).decode("utf-8")

        if not api_key:
            return {"status": "success", "latex": r"E = mc^2"}  # 默认 Mock 数据也改得更有趣一点

        completion = client.chat.completions.create(
            model="qwen-vl-max",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "你是一个专业的数学公式识别助手。请识别图片中的数学公式（无论是矩阵、微积分、代数式还是几何公式），"
                            "并直接输出标准的 LaTeX 代码。不要使用 markdown 标记（如 ```latex），"
                            "不要输出任何解释性文字，只输出公式本身。如果公式较长，请确保 LaTeX 语法正确。"
                        )
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                    }
                ]
            }]
        )

        latex_res = completion.choices[0].message.content.strip()
        # 清洗数据
        clean_latex = latex_res.replace("```latex", "").replace("```", "").replace("\\[", "").replace("\\]", "").strip()
        # 如果包含 $ 符号也去掉，保证纯净
        if clean_latex.startswith("$") and clean_latex.endswith("$"):
            clean_latex = clean_latex[1:-1].strip()

        return {"status": "success", "latex": clean_latex}

    except Exception as e:
        logger.error(f"OCR Error: {e}")
        return {"status": "success", "latex": r"\text{Error}"}


@app.post("/api/animate")
async def generate_animation(data: CalcModel):
    # ... (保持原有的 Manim 逻辑) ...
    try:
        task_id = str(uuid.uuid4())
        video_path = render_matrix_animation(data.matrixA, data.matrixB, data.operation, task_id)

        if video_path and os.path.exists(video_path):
            filename = os.path.basename(video_path)
            return {"status": "success", "video_url": f"/videos/{filename}", "result_latex": r"\text{Done}"}
        else:
            raise HTTPException(status_code=500, detail="Failed")
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# 静态文件挂载放最后
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)