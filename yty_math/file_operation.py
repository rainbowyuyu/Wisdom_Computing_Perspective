import os
import numpy as np
import manim

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
streamlit_video_path = os.path.join(default_software_path, r"../media/videos/1080p60")
streamlit_result_path = os.path.join(default_software_path, r"../media/images")
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
