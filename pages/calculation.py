# rainbow_yu pages.visualize_calculation 🐋✨

import streamlit
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
import re

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from default_streamlit_app_util import *
from yty_math.manim_animation import MatrixCreation, MatrixDetShow, MatrixAdditionShow, MatrixMulShow
from yty_math.manim_result import DetResult, AddResult, MulResult
import yty_math.picture_roi as picture_roi
import yty_math.yolo_detection as yolo_detection
import yty_math.dbscan_line as dbscan_line
import yty_math.get_number as get_number
import yty_math.file_operation as file_operation
import yty_math.manim_animation as manim_animation
import yty_math.file_operation



class FinalApp:
    def __init__(self):
        self.selected_model_version = None
        self.selected_method = "matrix"

    def run(self):
        st.set_page_config(page_title="智算视界 · 可视化计算", page_icon="assert/images/pure_logo.png", layout="wide")

        mobile_or_computer_warning()

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

        login_config()

        st.sidebar.title("页面")


        # 读取状态或用户点击
        action = st.sidebar.radio("选择页面", ["识别算式", "手写输入", "动画演示"],
                                  index=["识别算式", "手写输入", "动画演示"].index(st.session_state.page))

        if action == "识别算式":
            st.session_state.page = action
            st.title("识别算式")

            col1, col2, col3 = st.columns(3)

            with col1:
                self.handle_image_selection()


            with col2:
                st.markdown("## 🔍 图片识别")
                # 设置识别图片按钮，并使用唯一的 key
                rec_but = st.button(
                    "识别图片",
                    key="recognize_button",  # 这里的 key 需要确保唯一
                    disabled="image_bytes" not in st.session_state  # 没有图片时禁用按钮
                )
                if rec_but:  # 触发识别图片
                    process_and_display_image()

            with col3:
                st.markdown("## 📝 算式创建")
                # 设置创建矩阵按钮，并使用唯一的 key
                cola, colb= st.columns(2)
                with cola:
                    cre_but = st.button(
                        "创建算式",
                        key="create_button",  # 这里的 key 需要确保唯一
                        disabled="matrix" not in st.session_state  # 没有矩阵时禁用按钮
                    )
                with colb:
                    save_but = st.button(
                        "保存算式",
                        key="save_button",  # 这里的 key 需要确保唯一
                        disabled="manim_temp" not in st.session_state
                    )
                if cre_but:  # 触发创建矩阵
                    create_matrix()
                if save_but:  # 触发创建矩阵
                    save_matrix()

        elif action == "手写输入":
            st.session_state.page = action
            st.title("手写输入")
            self.canvas()

        elif action == "动画演示":
            st.session_state.page = action
            st.title("动画演示")
            self.animate()

        page_foot()

    def handle_image_selection(self):
        success = select_and_display_image()

        self.selected_model_version = st.sidebar.selectbox(
            "选择模型版本",
            ["v4.2", "v4n", "v3.5", "v3", "v2", "v1.5", "v1", "v0"]
        )
        st.sidebar.text(f"已选择模型版本: {self.selected_model_version}")
        st.session_state.selected_model_version = self.selected_model_version

    def canvas(self):
        draw_canvas()

    def animate(self):
        self.selected_method = st.sidebar.selectbox(
            "选择解题方式",
            ["矩阵", "二进制浮点运算", "微积分", "页面置换", "排序算法", "其他新增算法"]
        )
        st.sidebar.text(f"已选择解题方式: {self.selected_method}")
        st.session_state.selected_method = self.selected_method

        matrix_calculator_app()

def draw_canvas(
    canvas_key="canvas",
    canvas_height=400,
    canvas_width=600,
    bg_color="#FFFFFF",
):
    st.markdown("## ✏️ 绘图区域")
    st.markdown("使用下方工具进行手绘，支持导出当前图像")

    # 初始化 session_state
    if "history" not in st.session_state:
        st.session_state.history = []

    if "current_image" not in st.session_state:
        st.session_state.current_image = None

    # 分栏布局：工具选择 & 设置
    col1, col2 = st.columns(2)
    with col1:
        tool = st.radio("🛠️ 选择工具", ["🖊️ 笔", "🩹 橡皮擦"], horizontal=True)
        stroke_color = "#000000" if tool == "🖊️ 笔" else "#FFFFFF"
        stroke_width = st.slider("🎨 画笔大小", 1, 50, 5)
    with col2:
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


    st.markdown("---")

    # 导出功能按钮
    export_col1, export_col2 = st.columns([1, 3])
    with export_col1:
        if st.button("📤 导出图像"):
            if canvas_result.image_data is not None:
                img_copy = copy.deepcopy(canvas_result.image_data)
                st.session_state.history.append(img_copy)
                st.session_state.current_image = img_copy
                st.success("✅ 图像导出成功!")

    # 显示导出后的图像
    if st.session_state.current_image is not None:
        st.image(st.session_state.current_image, caption="🖼️ 当前画布预览", use_container_width=True)

    return st.session_state.current_image

def select_and_display_image():
    st.markdown("## 📤 上传图片")
    uploaded_file = st.file_uploader(
        "请选择一张图片（jpg / jpeg / png）", type=["jpg", "jpeg", "png"], label_visibility="collapsed"
    )

    if uploaded_file is not None:
        st.success("✅ 图片上传成功！")

        image_bytes = uploaded_file.read()
        image = Image.open(BytesIO(image_bytes)).convert("RGB")

        st.image(image, caption="🖼️ 上传的图片预览", use_container_width=True)

        st.session_state.uploaded_image = image
        st.session_state.image_bytes = image_bytes
        return True

    st.info("👆 请上传一张图片以开始")
    return False


def process_and_display_image():

    if "image_bytes" not in st.session_state:
        st.warning("⚠️ 请先上传一张图片")
        return

    # 获取 YOLO 模型版本
    selected_model_version = st.session_state.get("selected_model_version", "v4.2")

    # OpenCV 解码图片
    file_bytes = np.asarray(bytearray(st.session_state.image_bytes), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if img is None:
        st.error("图片加载失败，请确认格式正确")
        return

    # 处理图像（你自己的函数）
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

    # 显示处理后图像
    img = picture_roi.opencv_to_pillow(img)
    st.image(img, caption="✅ 处理后的图片", use_container_width=True)

    update_entry_widgets()


def update_entry_widgets():
    st.markdown("## 📋 识别算式编辑")

    matrix = st.session_state.get("matrix", [])
    if not matrix:
        st.warning("⚠️ 未识别到矩阵")
        return

    num_rows = len(matrix)
    num_cols = len(matrix[0]) if matrix else 0

    df = pd.DataFrame(
        matrix,
        index=[f"R{i}" for i in range(num_rows)],
        columns=[f"C{j}" for j in range(num_cols)]
    )

    st.markdown("👇 你可以在下方对识别结果进行修改：")
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
    )

    st.session_state.matrix = edited_df.values.tolist()

def create_matrix():
    config.transparent = True

    if "matrix" not in st.session_state:
        st.warning("请先识别并生成矩阵。")
        return

    matrix = st.session_state.matrix

    manin_rander(MatrixCreation,matrix)

    st.image(file_operation.streamlit_manim_path, caption="生成的矩阵", use_container_width=True)

def save_matrix():

    st.image(file_operation.streamlit_manim_path, caption="生成的矩阵", use_container_width=True)

    filename = st.text_input("请输入保存的文件名，输入后再次点击保存算式即可👆", key="filename_input")

    if filename:
        full_filename = f"{filename}.txt"
        invalid_chars = r'[\\/:*?"<>|]'
        if re.search(invalid_chars, filename):
            st.error("文件名无效，不能包含以下字符：\\ / : * ? \" < > |")
        else:
            # 保存矩阵到文件
            with open(os.path.join(file_operation.streamlit_save_path,full_filename), "w", encoding="utf-8") as f:
                for row in st.session_state.matrix:
                    f.write(" ".join(map(str, row)) + "\n")

            # 图片复制
            dst_path = os.path.join(file_operation.streamlit_save_path, f"{filename}.png")
            shutil.copy(file_operation.streamlit_manim_path, dst_path)

            st.success(f"矩阵已成功保存为 {full_filename}")

def matrix_calculator_app():
    # Initialize session state variables
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

        if matrix1.ndim != 2 or matrix2.ndim != 2:
            st.error("至少有一个矩阵不是二维矩阵，请检查输入。")
            return False

        st.session_state.matrix1 = matrix1
        st.session_state.matrix2 = matrix2

        op = st.session_state.operation
        if op == 'add':
            # 矩阵加法需要两个矩阵的形状相同
            return matrix1.shape == matrix2.shape
        elif op == 'mul':
            # 矩阵乘法需要矩阵1的列数等于矩阵2的行数
            return matrix1.shape[1] == matrix2.shape[0]
        elif op == 'det':
            # 行列式操作需要矩阵是方阵
            return matrix1.shape[0] == matrix1.shape[1]
        else:
            return False

    def select_matrix(number, image_name):
        folder = file_operation.streamlit_save_path
        txt_path = os.path.join(folder, f"{image_name}.txt")
        if os.path.exists(txt_path):
            st.session_state.matrix_name[number] = txt_path
        else:
            st.warning(f"矩阵文件 {txt_path} 不存在，请重新选择.")

    def generate_latex_result():
        latex_img_path = file_operation.streamlit_result_path
        st.session_state.latex_img_path = latex_img_path

    # Image selection area
    st.header("选择数学算式图像")
    folder = file_operation.streamlit_save_path
    images = [f for f in os.listdir(folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    image_names = [os.path.splitext(img)[0] for img in images]

    selected_image = st.selectbox("从以下图像中选择：", image_names)

    # Preview selected image
    if selected_image:
        img_path = os.path.join(folder, f"{selected_image}.png")
        if os.path.exists(img_path):
            st.image(img_path, caption=selected_image, width=300)

    # Operation selection area
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

        # Display selected matrix names
        st.text(f"矩阵1: {os.path.basename(st.session_state.matrix_name[0])}")
        if st.session_state.operation != 'det':
            st.text(f"矩阵2: {os.path.basename(st.session_state.matrix_name[1])}")

        # Validate and show results
        if is_matrix_valid():
            st.success("算式验证通过，可以进行计算。")
            if st.button("计算结果"):
                generate_latex_result()
                if st.session_state.operation == 'det':
                    manin_rander(MatrixDetShow, st.session_state.matrix1, )
                    manin_rander(DetResult, st.session_state.matrix1)
                    st.session_state.latex_img_path = os.path.join(file_operation.streamlit_video_path,"MatrixDetShow.mp4.png")
                    st.session_state.video_path = os.path.join(file_operation.streamlit_video_path, "MatrixDetShow.mp4")
                elif st.session_state.operation == 'add':
                    manin_rander(MatrixAdditionShow, st.session_state.matrix1, st.session_state.matrix2, text="视频")
                    manin_rander(AddResult, st.session_state.matrix1, st.session_state.matrix2, text="结果")
                    st.session_state.latex_img_path = os.path.join(file_operation.streamlit_video_path,"MatrixAdditionShow.mp4.png")
                    st.session_state.video_path = os.path.join(file_operation.streamlit_video_path, "MatrixAdditionShow.mp4")
                elif st.session_state.operation == 'mul':
                    manin_rander(MatrixMulShow, st.session_state.matrix1, st.session_state.matrix2, text="视频")
                    manin_rander(MulResult, st.session_state.matrix1, st.session_state.matrix2, text="结果")
                    st.session_state.latex_img_path = os.path.join(file_operation.streamlit_video_path,"MatrixMulShow.mp4.png")
                    st.session_state.video_path = os.path.join(file_operation.streamlit_video_path,"MatrixMulShow.mp4")
                else:
                    st.error("为正确选择计算方式")

                st.video(st.session_state.video_path)
                try:
                    st.image(st.session_state.latex_img_path, caption="计算结果（LaTeX）")
                except Exception as e:
                    st.warning(f"LaTeX 结果图像未生成，请确保路径正确。{e}")
        else:
            st.error("矩阵维度不匹配或无效，请重新选择。")


# Write matrix to file
def write_matrix_to_file(file_path, matrix, name):
    full_file_path = os.path.join(file_path, f"{name}.txt")
    with open(full_file_path, 'w') as f:
        for row in matrix:
            f.write(' '.join(map(str, row)) + '\n')


# Read matrix from file
def read_matrix_from_file(file_path, mode='numpy'):
    if file_path == "":
        return None
    with open(file_path, 'r') as file:
        matrix_data = [list(map(int, line.split())) for line in file]
    return np.array(matrix_data) if mode == 'numpy' else matrix_data


def manin_rander(
        manin_class,
        *args,
        text = "LaTeX",
):
    # 显示进度条
    progress_text = "正在使用 Manim 渲染矩阵动画，请稍候..."
    progress_bar = st.progress(0, text=progress_text)

    # 模拟进度：加载阶段
    progress_bar.progress(10, text="准备动画类和参数...")
    time.sleep(0.5)

    try:
        # 渲染动画
        animation = manin_class(*args)
        progress_bar.progress(30, text="创建动画对象...")
        time.sleep(0.5)
        animation.render()
        progress_bar.progress(100, text="🎉 渲染完成！")
        st.session_state.manim_temp = True
        st.success(f"✅ {text} 渲染完成")
    except Exception as e:
        st.error(f"渲染失败：{e}")
        progress_bar.empty()


if __name__ == "__main__":
    app = FinalApp()
    app.run()
