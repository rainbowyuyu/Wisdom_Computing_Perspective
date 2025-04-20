# rainbow_yu pages.login 🐋✨

import bcrypt
from supabase import create_client, Client
import streamlit as st
from postgrest.exceptions import APIError
import uuid
import hashlib
import random
import string
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from default_streamlit_app_util import *

# 配置页面
st.set_page_config(page_title="智算视界 · 用户登录", page_icon="pure_logo.png", layout="wide")

# 初始化 Supabase 客户端
url = "https://fzmjkkiaibpjevtaeasl.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ6bWpra2lhaWJwamV2dGFlYXNsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUxMTUwMjgsImV4cCI6MjA2MDY5MTAyOH0.3ElNnjol9x6qq1_kVbgVzu6gmAz4iC-Is63yWBB-aO4"
supabase: Client = create_client(url, key)


# 注册功能
def register_user(username, password):
    # 检查用户名和密码是否为空
    if not username or not password:
        st.error("用户名和密码不能为空！")
        return False

    # 检查用户名是否已存在
    existing_user = supabase.table("users").select("*").eq("username", username).execute()
    if existing_user.data:
        st.warning("用户名已存在")
        return False  # 用户已存在

    hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = str(uuid.uuid4())
    # 使用 UUID 的 MD5 哈希值并转为整数
    user_id_int = int(hashlib.md5(user_id.encode()).hexdigest(), 16)  # 转为整数

    try:
        response = supabase.table("users").insert({
            "id": user_id_int % 10000,
            "username": username,
            "hashed_password": hashed_pw
        }).execute()
        return True
    except APIError as e:
        st.error(f"注册失败: {e.message}")
        return False


# 登录验证
def login_user(username, password):
    # 检查用户名和密码是否为空
    if not username or not password:
        st.error("用户名和密码不能为空！")
        return False

    user = supabase.table('users').select("*").eq('username', username).execute()
    if not user.data:
        st.error("用户不存在")
        return False  # 用户不存在
    hashed_pw = user.data[0]["hashed_password"]

    if bcrypt.checkpw(password.encode(), hashed_pw.encode()):
        return True
    return False


# 避免易混淆字符
def generate_captcha_text(length=5):
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(random.choices(chars, k=length))

def generate_captcha_image(captcha_text):
    width, height = 120, 40
    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    # 加载字体（更好看的验证码字体，如果没有字体文件就用默认）
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        font = ImageFont.load_default()

    # 画每个字符（加点位移制造扭曲感）
    for i, char in enumerate(captcha_text):
        x = 10 + i * 20 + random.randint(-2, 2)
        y = 5 + random.randint(-2, 2)
        draw.text((x, y), char, font=font, fill=(0, 0, 0))

    # 添加干扰线
    for _ in range(5):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=(150, 150, 150), width=1)

    # 添加干扰点
    for _ in range(30):
        x, y = random.randint(0, width), random.randint(0, height)
        draw.point((x, y), fill=(100, 100, 100))

    # 可选：模糊处理，增加识别难度
    image = image.filter(ImageFilter.GaussianBlur(0.5))

    buf = BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return buf


# 设置蓝色系样式
st.markdown("""
    <style>
    .stButton>button {
        background-color: #007BFF;
        color: white;
        border-radius: 12px;
        border: none;
        padding: 10px 20px;
        font-size: 16px;
    }

    .stButton>button:hover {
        background-color: #0056b3;
    }

    .stTextInput input {
        border: 2px solid #007BFF;
        padding: 10px;
        font-size: 16px;
        border-radius: 8px;
    }

    .stTextInput input:focus {
        border-color: #0056b3;
    }

    .stSidebar {
        background-color: #f0f0f0;
    }

    .stHeader {
        font-size: 2rem;
        font-weight: bold;
    }

    .stMarkdown a {
        color: #007BFF;
    }

    </style>
""", unsafe_allow_html=True)

# 主页面内容
menu = st.sidebar.radio("请选择", ["登录", "注册"])

if menu == "登录":
    st.header("🔐 用户登录")
    if not st.session_state.get("logged_in"):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")

        if "captcha_login" not in st.session_state:
            st.session_state["captcha_login"] = generate_captcha_text()

        # 验证码图片和刷新按钮并排显示
        col1, col2, col3 = st.columns([1.5 ,0.2, 0.1])
        with col1:
            captcha_input = st.text_input("验证码")
        with col2:
            st.image(generate_captcha_image(st.session_state["captcha_login"]), width=120)
        with col3:
            if st.button("🔄", key="refresh_login_captcha"):
                st.session_state["captcha_login"] = generate_captcha_text()

        st.warning("没有账号？ 展开左侧状态栏注册")

        if st.button("登录"):
            if captcha_input.upper() != st.session_state["captcha_login"]:
                st.error("验证码错误，请重试")
                st.session_state["captcha_login"] = generate_captcha_text()
            elif login_user(username, password):
                st.success(f"欢迎回来，{username}！")
                st.session_state["logged_in"] = True
                st.session_state["username"] = username
                del st.session_state["captcha_login"]
            else:
                st.error("用户名或密码错误")

elif menu == "注册":
    st.header("📝 用户注册")
    new_user = st.text_input("新用户名")
    new_password = st.text_input("新密码", type="password")

    if "captcha_reg" not in st.session_state:
        st.session_state["captcha_reg"] = generate_captcha_text()

    # 验证码图片和刷新按钮并排显示
    col1, col2, col3 = st.columns([1.5 ,0.2, 0.1])
    with col1:
        captcha_input_reg = st.text_input("验证码")
    with col2:
        st.image(generate_captcha_image(st.session_state["captcha_reg"]), width=120)
    with col3:
        if st.button("🔄", key="refresh_reg_captcha"):
            st.session_state["captcha_reg"] = generate_captcha_text()


    if st.button("注册"):
        if captcha_input_reg.upper() != st.session_state["captcha_reg"]:
            st.error("验证码错误，请重试")
            st.session_state["captcha_reg"] = generate_captcha_text()
        elif register_user(new_user, new_password):
            st.success("注册成功，请返回登录")
            del st.session_state["captcha_reg"]
        else:
            st.warning("用户名已存在")



# 登录后展示主界面
if st.session_state.get("logged_in"):
    st.sidebar.success(f"已登录：{st.session_state['username']}")
    st.success(f"已登录：{st.session_state['username']}")
    if st.button("登出"):
        st.session_state.clear()  # 清除 session，登出用户
        st.rerun()  # 刷新页面
else:
    st.sidebar.warning("未登录")

page_foot()