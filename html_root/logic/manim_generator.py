# logic/manim_generator.py
import os
import subprocess
import re
import sys
import numpy as np
import shutil

# 获取项目根目录 (假设此文件在 logic/ 目录下，根目录是上一级)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_VIDEO_DIR = os.path.join(BASE_DIR, "static", "videos")


def parse_latex_to_list(latex_str):
    """
    简易解析 LaTeX 矩阵为 Python List
    """
    if not latex_str:
        return [[1, 0], [0, 1]]

    try:
        # 提取环境中间的内容
        content = latex_str
        if "begin" in latex_str:
            match = re.search(r'\\begin\{.*?\}(.*?)\\end\{.*?\}', latex_str, re.DOTALL)
            if match:
                content = match.group(1)

        rows = content.split(r'\\')
        matrix_data = []
        for row in rows:
            row_str = row.strip()
            if not row_str: continue
            # 处理 & 分割
            cols = row_str.split('&')
            row_nums = []
            for c in cols:
                # 清理花括号和空格
                clean_c = c.strip().replace('{', '').replace('}', '')
                try:
                    row_nums.append(float(clean_c))
                except ValueError:
                    row_nums.append(0.0)  # 容错
            if row_nums:
                matrix_data.append(row_nums)

        if not matrix_data: return [[1, 0], [0, 1]]
        return matrix_data
    except Exception as e:
        print(f"Matrix Parse Error: {e}")
        return [[1, 0], [0, 1]]


def render_matrix_animation(matA_latex, matB_latex, operation, task_id):
    """
    生成 Manim 脚本并执行，使用纯 Manim Community 实现
    """
    matA = parse_latex_to_list(matA_latex)
    matB = parse_latex_to_list(matB_latex)

    scene_name = "GenScene"

    # 构造 Python 脚本内容
    script_content = f"""
from manim import *
import numpy as np

class {scene_name}(Scene):
    def construct(self):
        # 1. 准备数据
        data_a = {matA}
        data_b = {matB}

        # 2. 创建矩阵对象
        m_a = Matrix(data_a).set_color(BLUE)
        m_b = Matrix(data_b).set_color(TEAL)

        op = "{operation}"

        if op == "add":
            self.animate_addition(m_a, m_b, data_a, data_b)
        elif op == "mul":
            self.animate_multiplication(m_a, m_b, data_a, data_b)
        elif op == "det":
            self.animate_determinant(m_a, data_a)
        else:
            t = Text("Unsupported Operation").set_color(RED)
            self.add(t)

    def animate_addition(self, m_a, m_b, da, db):
        # 布局: A + B = ?
        plus = MathTex("+").scale(1.5)
        equals = MathTex("=").scale(1.5)

        group = VGroup(m_a, plus, m_b, equals).arrange(RIGHT)
        self.play(Write(group))
        self.wait(0.5)

        # 计算结果
        try:
            arr_a = np.array(da)
            arr_b = np.array(db)
            if arr_a.shape != arr_b.shape:
                err = Text("Dimension Mismatch!", color=RED).to_edge(DOWN)
                self.play(Write(err))
                return

            res_arr = arr_a + arr_b
            m_res = Matrix(res_arr).set_color(YELLOW).next_to(equals, RIGHT)

            # 简单的逐个元素相加动画示意
            self.play(Write(m_res))

            # 高亮第一个元素
            rect_a = SurroundingRectangle(m_a.get_rows()[0][0], color=YELLOW)
            rect_b = SurroundingRectangle(m_b.get_rows()[0][0], color=YELLOW)
            rect_res = SurroundingRectangle(m_res.get_rows()[0][0], color=YELLOW)

            self.play(Create(rect_a), Create(rect_b))
            self.play(TransformFromCopy(rect_a, rect_res), TransformFromCopy(rect_b, rect_res))
            self.wait(1)

        except Exception as e:
            print(e)

    def animate_multiplication(self, m_a, m_b, da, db):
        times = MathTex("\\\\times").scale(1.5)
        equals = MathTex("=").scale(1.5)

        group = VGroup(m_a, times, m_b, equals).arrange(RIGHT).scale(0.8)
        self.play(Write(group))

        try:
            arr_a = np.array(da)
            arr_b = np.array(db)
            res_arr = np.dot(arr_a, arr_b)

            m_res = Matrix(res_arr).set_color(YELLOW).next_to(equals, RIGHT).scale(0.8)

            # 演示第一行乘第一列
            row = m_a.get_rows()[0]
            col = m_b.get_columns()[0]

            rect_row = SurroundingRectangle(row, color=RED)
            rect_col = SurroundingRectangle(col, color=RED)

            self.play(Create(rect_row), Create(rect_col))
            self.wait(0.5)

            # 显示结果
            self.play(Write(m_res))
            self.play(FadeOut(rect_row), FadeOut(rect_col))
            self.wait(1)

        except Exception as e:
            err = Text("Shape Mismatch", color=RED).to_edge(DOWN)
            self.add(err)

    def animate_determinant(self, m_a, da):
        # 布局: |A|
        det_bars = MathTex("|", "A", "|", "=").scale(1.5)
        group = VGroup(m_a, det_bars).arrange(RIGHT)

        self.play(Write(m_a))
        self.play(ReplacementTransform(m_a.copy(), det_bars[1]))
        self.play(Write(det_bars[0]), Write(det_bars[2]), Write(det_bars[3]))

        try:
            arr = np.array(da)
            if arr.shape[0] != arr.shape[1]:
                self.add(Text("Must be Square Matrix", color=RED).next_to(det_bars, RIGHT))
                return

            val = np.linalg.det(arr)
            res = MathTex(f"{{:.2f}}".format(val)).set_color(YELLOW).next_to(det_bars, RIGHT)

            self.play(Write(res))

            if arr.shape == (2,2):
                # 2x2 特效: ad - bc
                diag1 = Line(m_a.get_rows()[0][0].get_center(), m_a.get_rows()[1][1].get_center(), color=RED)
                diag2 = Line(m_a.get_rows()[0][1].get_center(), m_a.get_rows()[1][0].get_center(), color=BLUE)
                self.play(Create(diag1))
                self.play(Create(diag2))

            self.wait(1)
        except Exception:
            pass

"""
    # 写入临时文件
    py_filename = f"temp_{task_id}.py"
    py_path = os.path.join(BASE_DIR, py_filename)

    with open(py_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    # 执行 Manim 命令
    # -ql: 低质量(渲染快), --format mp4
    output_filename = f"{task_id}.mp4"

    # 构建输出路径
    # Manim 默认会输出到 media/videos/temp_xxx/480p15/GenScene.mp4
    # 我们可以通过 --media_dir 指定输出根目录

    # 使用当前解释器 -m manim，保证与主项目环境一致；-ql 为最快渲染预设（480p15）
    cmd = [
        sys.executable, "-m", "manim",
        "-ql",
        py_path,
        scene_name,
        "--media_dir", os.path.join(BASE_DIR, "manim_media")  # 临时输出目录，避免污染 static
    ]

    try:
        subprocess.run(cmd, check=True, cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 寻找生成的文件并移动
        # 路径通常是: BASE_DIR/manim_media/videos/temp_{task_id}/480p15/GenScene.mp4
        src_dir = os.path.join(BASE_DIR, "manim_media", "videos", f"temp_{task_id}", "480p15")
        src_file = os.path.join(src_dir, f"{scene_name}.mp4")

        target_file = os.path.join(STATIC_VIDEO_DIR, output_filename)

        if os.path.exists(src_file):
            shutil.move(src_file, target_file)
            # 清理临时文件 (可选: 清理 py 文件和 media 文件夹)
            if os.path.exists(py_path):
                os.remove(py_path)
            return target_file
        else:
            print(f"Video file not found at {src_file}")
            return None

    except subprocess.CalledProcessError as e:
        print(f"Manim Failed: {e}")
        return None
    except Exception as e:
        print(f"General Error: {e}")
        return None