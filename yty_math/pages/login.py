# rainbow_yu pages.login 🐋✨

import bcrypt
from supabase import create_client, Client
import streamlit as st
from postgrest.exceptions import APIError
import uuid
import hashlib

# 配置页面
st.set_page_config(page_title="智算视界·用户登录", page_icon="pure_logo.png", layout="wide")

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

        # 登录时的提示链接（改为按钮）
        st.warning("没有账号？ 展开左侧状态栏注册")

        if st.button("登录"):
            if login_user(username, password):
                st.success(f"欢迎回来，{username}！")
                st.session_state["logged_in"] = True
                st.session_state["username"] = username
            else:
                st.error("用户名或密码错误")

elif menu == "注册":
    st.header("📝 用户注册")
    new_user = st.text_input("新用户名")
    new_password = st.text_input("新密码", type="password")
    if st.button("注册"):
        if register_user(new_user, new_password):
            st.success("注册成功，请返回登录")
        else:
            st.warning("用户名已存在")

# 登录后展示主界面
if st.session_state.get("logged_in"):
    st.sidebar.success(f"已登录：{st.session_state['username']}")
    st.success(f"已登录：{st.session_state['username']}")
    if st.button("登出"):
        st.session_state.clear()  # 清除 session，登出用户
        st.rerun()  # 刷新页面