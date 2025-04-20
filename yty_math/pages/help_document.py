# rainbow_yu pages.help_document 🐋✨

import streamlit as st
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from default_streamlit_app_util import *

st.set_page_config(page_title="智算视界 · 帮助文档", page_icon="pure_logo.png", layout="wide")

# === 侧边导航栏 ===
login_config()

st.sidebar.title("📚 帮助文档导航")
section = st.sidebar.radio("跳转到章节", [
    "用户功能概述",
    "自动识别输入",
    "数学算式计算交互",
    "栈结构存储设置",
    "常见问题（FAQ）"
])

# === 页面标题 ===
mobile_or_computer_warning()

st.title("📘 使用帮助文档")

st.markdown("""
欢迎使用 **智算视界·手写算式识别与分步计算可视化系统**！  
本系统致力于通过视觉化与智能识别手段，帮助您更轻松地理解和掌握抽象的算式计算过程。
""")

# === 内容区按选择切换 ===
if section == "用户功能概述":
    st.header("🖊️ 用户功能概述")
    st.markdown("""
    本系统围绕“**手写算式识别 + 分步动画演示**”的理念构建，致力于让用户 **不仅看到计算结果，还能理解计算过程**。

    功能共分为三大层次：
    1. **自动识别输入**：用户手写或上传图像，系统自动识别。
    2. **数学算式交互计算**：提供矩阵加法、乘法、行列式等动画演示。
    3. **栈结构存储设置**：自动保存每一步过程，可撤销、修改并分类查看。
    """)

elif section == "自动识别输入":
    st.header("✍️ 自动识别输入")
    st.markdown("""
    #### 📌 功能亮点：
    - 自由书写界面，支持鼠标、触控笔。
    - 功能区：画笔 / 橡皮擦 / 撤销 / 重做。
    - 上传图像或直接书写，系统进行图像识别。
    - 可选择不同识别模型，预览并编辑识别结果。
    - 支持保存为可复用的矩阵数据。

    > ✅ 小贴士：手写清晰、结构分明的矩阵可提高识别准确率！
    """)

elif section == "数学算式计算交互":
    st.header("➗ 数学算式计算交互")
    st.markdown("""
    #### 📌 功能亮点：
    - 支持常见矩阵运算：
      - 矩阵加法
      - 矩阵乘法
      - 行列式计算
    - 自动生成 **分步动画演示**，逐步展示每个运算步骤。
    - 可 **暂停、重复播放**，便于学习与分析。
    - 运算结果以 **LaTeX格式渲染** 展示，视觉美观。

    > 🎥 温馨提示：你可以在动画播放设置中调节速度和暂停点，更符合你的学习节奏！
    """)

elif section == "栈结构存储设置":
    st.header("💾 栈结构存储设置")
    st.markdown("""
    #### 📌 功能亮点：
    - 每次输入、运算操作都会自动“推入栈中”，实现可回溯的学习记录。
    - 支持一键恢复到任意历史状态。
    - 每条记录配有：
      - 标签 & 分类
      - LaTeX 渲染图像
      - 可自定义文件名与保存路径
    - 支持动画偏好设置，自定义每次播放体验。

    > 📂 提示：记得为常用矩阵加标签，方便未来快速调用！
    """)

elif section == "常见问题（FAQ）":
    st.header("🙋 常见问题（FAQ）")
    faq_data = {
        "手写识别不准确怎么办？": "请确认书写清晰，尝试更换识别模型或手动编辑结果。",
        "能否导出计算过程？": "可以导出动画过程和计算记录（LaTeX格式）。",
        "是否支持复数或更高维矩阵？": "当前支持二维实数矩阵，后续版本将扩展支持范围。"
    }
    for q, a in faq_data.items():
        with st.expander(f"❓ {q}"):
            st.markdown(f"**答**：{a}")
    if st.session_state.get("logged_in"):
        st.sidebar.success(f"已登录：{st.session_state['username']}")

# === 结束语 ===
st.markdown("---")
st.success("🎉 感谢您的使用！如有建议或反馈，欢迎联系我们开发团队。")

page_foot()
