# rainbow_yu pages.application 🐋✨

import streamlit as st

import streamlit as st
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from default_streamlit_app_util import *

st.set_page_config(page_title="智算视界 · 帮助文档", page_icon="assert/images/pure_logo.png", layout="wide")

# === 侧边导航栏 ===
login_config()

st.header("🎞️ 示例库")
st.markdown("欢迎来到资源库，点击视频开始播放：")

cols = st.columns(3)  # 创建三列展示多个视频
videos = [
    # 本地视频文件示例
    {"title": "示例视频 1", "path": "videos/video1.mp4"},
    {"title": "示例视频 2", "path": "videos/video2.mp4"},
    {"title": "示例视频 3", "path": "videos/video3.mp4"},
    # 可嵌入 YouTube 示例（可替换为 st.video 链接）
    {"title": "AI 科普", "url": "https://www.youtube.com/watch?v=aircAruvnKk"},
    {"title": "计算机视觉简介", "url": "https://www.youtube.com/watch?v=4GZ4XB4WD6s"},
    {"title": "神经网络入门", "url": "https://www.youtube.com/watch?v=6EStbTGqIeE"},
]

for i, video in enumerate(videos):
    with cols[i % 3]:
        st.markdown(f"**{video['title']}**")
        if "path" in video:
            st.video(video["path"])
        else:
            st.video(video["url"])

page_foot()