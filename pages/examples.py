# rainbow_yu pages.examples 🐋✨

import streamlit as st
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from default_streamlit_app_util import *

st.set_page_config(page_title="智算视界 · 帮助文档", page_icon="assert/images/pure_logo.png", layout="wide")

# === 侧边导航栏 ===
login_config()
mobile_or_computer_warning()

st.header("🎞️ 教学案例库")
st.markdown("欢迎来到教学案例库，点击视频开始播放：")

cols = st.columns(3)  # 创建三列展示多个视频
videos = [
    # 本地视频文件示例
    {"title": "二进制浮点运算", "path": "assert/storage/Booth.mp4"},
    {"title": "微积分", "path": "assert/storage/IntegralVisualization.mp4"},
    {"title": "LRU页面置换", "path": "assert/storage/PageTest.mp4"},
    {"title": "矩阵加法", "path": "assert/storage/MatrixAdditionShow.mp4"},
    {"title": "进制转换", "path": "assert/storage/Dec2BinAxeRe.mp4"},
    {"title": "搜索算法", "path": "assert/storage/AStarVisualization2.mp4"},
    {"title": "函数图像", "path": "assert/storage/SigmoidFunctionPlot.mp4"},
    {"title": "排序算法", "path": "assert/storage/Bb_an.mp4"},
    {"title": "梯度下降", "path": "assert/storage/gradient_descent.mp4"},
]

for i, video in enumerate(videos):
    with cols[i % 3]:
        st.markdown(f"**{video['title']}**")
        if "path" in video:
            st.video(video["path"])
        else:
            st.video(video["url"])

page_foot()