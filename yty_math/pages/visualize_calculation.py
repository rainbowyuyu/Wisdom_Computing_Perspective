# rainbow_yu pages.可视化计算 🐋✨

import streamlit as st
from streamlit_drawable_canvas import st_canvas
import shutil
from PIL import Image
import numpy as np
import copy
import os
import manim
import time
from io import BytesIO
from manim import config
import cv2
import pandas as pd
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from manim_animation import MatrixCreation  # 假设你在这个模块定义了 MatrixCreation 类
import picture_roi as picture_roi
import yolo_detection as yolo_detection
import dbscan_line as dbscan_line
import get_number as get_number
import file_operation as file_operation
import manim_animation as manim_animation
import file_operation


class FinalApp:
    def __init__(self):
        self.selected_model_version = None

    def run(self):
        st.set_page_config(page_title="智算视界·可视化计算", page_icon="pure_logo.png", layout="wide")

        st.warning("👈 需要切换页面和其他功能设置请点击侧边导航栏按钮")

        st.markdown(
            """
            <style>
            /* 展开侧边栏 */
            [data-testid="collapsedControl"] {
                display: none;
            }
            [data-testid="stSidebar"] {
                min-width: 300px;
                max-width: 300px;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        if "page" not in st.session_state:
            st.session_state.page = "识别算式"

        st.sidebar.image("logo.png", use_container_width=True)
        st.sidebar.title("页面")


        # 读取状态或用户点击
        action = st.sidebar.radio("选择页面", ["识别算式", "手写输入", "动画演示"],
                                  index=["识别算式", "手写输入", "动画演示"].index(st.session_state.page))


        if action == "识别算式":
            st.session_state.page = action
            st.title("识别算式")
            self.handle_image_selection()

            if "image_bytes" in st.session_state:
                if st.button("识别图片"):
                    process_and_display_image()

            if "matrix" in st.session_state:
                if st.button("创建矩阵"):
                    create_matrix()

        elif action == "手写输入":
            st.session_state.page = action
            st.title("手写输入")
            self.canvas()

        elif action == "动画演示":
            st.session_state.page = action
            st.title("动画演示")
            self.animate()

    def handle_image_selection(self):
        success = select_and_display_image()
        if success:
            st.success("图片上传成功！")

        self.selected_model_version = st.sidebar.selectbox(
            "选择模型版本",
            ["v4.2", "v5xp", "v5x", "v4x", "v4n", "v3.5", "v3", "v2", "v1.5", "v1", "v0", "yolo"]
        )
        st.sidebar.text(f"已选择模型版本: {self.selected_model_version}")
        st.session_state.selected_model_version = self.selected_model_version

    def canvas(self):
        draw_canvas()

    def animate(self):
        matrix_calculator_app()

def draw_canvas(
    canvas_key="canvas",
    canvas_height=400,
    canvas_width=600,
    bg_color="#FFFFFF",
):

    # 初始化 session_state
    if "history" not in st.session_state:
        st.session_state.history = []

    if "current_image" not in st.session_state:
        st.session_state.current_image = None

    # 工具选择
    tool = st.radio("选择工具", ["笔", "橡皮擦"], horizontal=True)
    stroke_width = st.slider("笔刷大小", 1, 50, 5)
    stroke_color = "#000000" if tool == "笔" else "#FFFFFF"

    # 创建画布
    canvas_result = st_canvas(
        fill_color="rgba(255,255,255,1)",
        stroke_width=stroke_width,
        stroke_color=stroke_color,
        background_color=bg_color,
        height=canvas_height,
        width=canvas_width,
        drawing_mode="freedraw",
        key=canvas_key,
        update_streamlit=True,
    )

    # 保存当前步骤
    if st.button("保存当前步骤"):
        if canvas_result.image_data is not None:
            img_copy = copy.deepcopy(canvas_result.image_data)
            st.session_state.history.append(img_copy)
            st.session_state.current_image = img_copy

    # 撤销操作
    if st.button("撤回"):
        if st.session_state.history:
            st.session_state.history.pop()
            if st.session_state.history:
                st.session_state.current_image = st.session_state.history[-1]
            else:
                st.session_state.current_image = None
        else:
            st.warning("没有可以撤回的步骤")

    # 显示当前画布
    if st.session_state.current_image is not None:
        st.image(st.session_state.current_image, caption="当前画布", use_container_width=True)

    # 返回当前图像（可保存或后续使用）
    return st.session_state.current_image

def select_and_display_image():
    uploaded_file = st.file_uploader("选择一张图片", type=["jpg", "jpeg", "png"])

    if uploaded_file is not None:
        # 读取文件内容为字节流（只读一次）
        image_bytes = uploaded_file.read()

        # 显示图片（可以用 BytesIO）
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        st.image(image, caption="上传的图片", use_container_width=True)

        # 保存状态
        st.session_state.uploaded_image = image
        st.session_state.image_bytes = image_bytes
        return True
    return False


def process_and_display_image():
    if "image_bytes" not in st.session_state:
        st.warning("未找到上传图片，请先上传。")
        return

    selected_model_version = st.session_state.get("selected_model_version", "v4.2")

    # 转换为 OpenCV 图像
    file_bytes = np.asarray(bytearray(st.session_state.image_bytes), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if img is None:
        st.error("图片加载失败")
        return

    img = picture_roi.extract_roi(picture=img, output_mode="cv2")
    img, msk, detections = yolo_detection.detect_objects(
        img, yolo_detection.load_model(selected_model_version)
    )

    img, col_list, row_list = dbscan_line.create_line(img, msk)
    matrix = get_number.organize_detections(
        get_number.class_name_and_center(detections, img),
        row_list, col_list
    )

    st.session_state.matrix = matrix
    st.session_state.col = len(col_list)
    st.session_state.row = len(row_list)

    img = picture_roi.opencv_to_pillow(img)
    st.image(img, caption="处理后的图片", use_container_width=True)

    update_entry_widgets()

def update_entry_widgets():
    matrix = st.session_state.matrix
    num_rows = len(matrix)
    num_cols = len(matrix[0]) if matrix else 0

    df = pd.DataFrame(matrix,
                      index=[f"R{i}" for i in range(num_rows)],
                      columns=[f"C{j}" for j in range(num_cols)])

    st.write("识别出的矩阵：")
    edited_df = st.data_editor(df, num_rows="dynamic", hide_index=True, use_container_width=True)
    st.session_state.matrix = edited_df.values.tolist()

def create_matrix():
    config.transparent = True

    if "matrix" not in st.session_state:
        st.warning("请先识别并生成矩阵。")
        return

    matrix = st.session_state.matrix

    # 显示进度条
    progress_text = "正在使用 Manim 渲染矩阵动画，请稍候..."
    progress_bar = st.progress(0, text=progress_text)

    # 模拟进度：加载阶段
    progress_bar.progress(10, text="准备动画类和参数...")
    time.sleep(0.5)

    try:
        # 渲染动画
        animation = MatrixCreation(matrix)

        progress_bar.progress(30, text="创建动画对象...")
        time.sleep(0.5)

        animation.render()

        progress_bar.progress(100, text="🎉 渲染完成！")

        st.success("Manim 渲染完成 ✅")
    except Exception as e:
        st.error(f"渲染失败：{e}")
        progress_bar.empty()

    st.image(file_operation.streamlit_manim_path, caption="生成的矩阵", use_container_width=True)


def matrix_calculator_app():
    # 初始化 session_state
    if 'matrix_name' not in st.session_state:
        st.session_state.matrix_name = ["", ""]
    if 'operation' not in st.session_state:
        st.session_state.operation = None
    if 'matrix1' not in st.session_state:
        st.session_state.matrix1 = None
    if 'matrix2' not in st.session_state:
        st.session_state.matrix2 = None
    if 'latex_img_path' not in st.session_state:
        st.session_state.latex_img_path = None

    def is_matrix_valid():
        matrix1 = np.array(read_matrix_from_file(st.session_state.matrix_name[0]))
        matrix2 = np.array(read_matrix_from_file(st.session_state.matrix_name[1]))

        st.session_state.matrix1 = matrix1
        st.session_state.matrix2 = matrix2

        op = st.session_state.operation
        if op == 'add' and matrix1.shape == matrix2.shape:
            return True
        elif op == 'mul' and matrix1.shape[1] == matrix2.shape[0]:
            return True
        elif op == 'det' and matrix1.shape[0] == matrix1.shape[1]:
            return True
        else:
            return False

    def select_matrix(number, image_name):
        folder = default_save_path
        txt_path = os.path.join(folder, f"{image_name}.txt")
        if os.path.exists(txt_path):
            st.session_state.matrix_name[number] = txt_path
            shutil.copy(txt_path, os.path.join(default_file_path, f"matrix{number}_cache.txt"))

    def generate_latex_result():
        # 这里应根据实际逻辑生成LaTeX图像
        latex_img_path = "results/result_latex.png"
        st.session_state.latex_img_path = latex_img_path


    # 图片选择区域
    st.header("选择数学算式图像")
    folder = streamlit_save_path
    images = [f for f in os.listdir(folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    image_names = [os.path.splitext(img)[0] for img in images]

    selected_image = st.selectbox("从以下图像中选择：", image_names)

    # 预览图像
    if selected_image:
        img_path = os.path.join(folder, f"{selected_image}.png")
        if os.path.exists(img_path):
            st.image(img_path, caption=selected_image, width=300)

    # 操作选择区域
    st.header("选择矩阵操作")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("行列式"):
            st.session_state.operation = 'det'
    with col2:
        if st.button("矩阵加法"):
            st.session_state.operation = 'add'
    with col3:
        if st.button("矩阵乘法"):
            st.session_state.operation = 'mul'

    if st.session_state.operation:
        st.subheader(f"当前操作: {st.session_state.operation}")
        if st.session_state.operation == 'det':
            if st.button("选择为矩阵"):
                select_matrix(0, selected_image)
        else:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("选择为矩阵1"):
                    select_matrix(0, selected_image)
            with col2:
                if st.button("选择为矩阵2"):
                    select_matrix(1, selected_image)

        # 显示选中矩阵名
        st.text(f"矩阵1: {os.path.basename(st.session_state.matrix_name[0])}")
        if st.session_state.operation != 'det':
            st.text(f"矩阵2: {os.path.basename(st.session_state.matrix_name[1])}")

        # 验证并显示结果
        if is_matrix_valid():
            st.success("矩阵验证通过，可以进行计算。")
            if st.button("生成 LaTeX 结果图像"):
                generate_latex_result()

                if st.session_state.latex_img_path and os.path.exists(st.session_state.latex_img_path):
                    st.image(st.session_state.latex_img_path, caption="计算结果（LaTeX）")
                else:
                    st.warning("LaTeX 结果图像未生成，请确保路径正确。")
        else:
            st.error("矩阵维度不匹配或无效，请重新选择。")


default_software_path = os.getcwd()

default_file_path = os.path.join(default_software_path, r"math_cache")
default_save_path = os.path.join(default_software_path, r"math_saves")
streamlit_save_path = os.path.join(default_software_path, r"yty_math/math_saves")
default_manim_source_code = os.path.join(default_software_path, r"manim_animation.py")
default_manim_result_code = os.path.join(default_software_path, r"manim_result.py")
default_manim_path = os.path.join(default_software_path, rf"media\images\manim_animation\MatrixCreation_ManimCE_v{manim.__version__}.png")
streamlit_manim_path = os.path.join(default_software_path, rf"media/images/MatrixCreation_ManimCE_v{manim.__version__}.png")
default_video_path = os.path.join(default_software_path, r"media\videos\manim_animation\1080p60")
default_result_path = os.path.join(default_software_path, r"media\images\manim_result")
default_model_path = os.path.join(default_software_path, "models")


# 写矩阵到文件的函数
def write_matrix_to_file(file_path, matrix, name):
    # 构造文件名
    full_file_path = os.path.join(file_path, f"{name}.txt")

    # 打开文件进行写入，如果文件存在则覆盖
    with open(full_file_path, 'w') as f:
        for i in range(len(matrix)):
            for j in range(len(matrix[0])):
                f.write(str(matrix[i][j]) + ' ')
            f.write('\n')


# 读取矩阵数据的函数
def read_matrix_from_file(file_path, mode='list'):
    if file_path == "":
        return None
    with open(file_path, 'r') as file:
        matrix_data = []
        for line in file:
            # 将每一行的数据按空格分割并转为整数列表
            matrix_data.append([int(x) for x in line.split()])
    if mode == 'numpy':
        return np.array(matrix_data)
    else:
        return matrix_data

if __name__ == "__main__":
    app = FinalApp()
    app.run()
