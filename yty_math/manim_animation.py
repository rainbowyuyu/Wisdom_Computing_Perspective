import os
import yty_math.file_operation as fo
from yty_math.matrix_yty import *

color_list = [RED, ORANGE, YELLOW, GREEN, TEAL, BLUE, PURPLE, PINK, DARK_BROWN, GOLD]
time_control = 0.5


class MatrixCreation(Scene):
    def __init__(self,data_load=None):
        super().__init__()
        self.data_load = data_load
    def construct(self):
        if self.data_load:
            matrix_data = self.data_load
        else:
            matrix_data = fo.read_matrix_from_file(os.path.join(fo.default_file_path, "cache.txt"))
        m = Matrix(matrix_data).set_color(BLACK)

        # 获取屏幕的宽度和高度
        screen_width = config.frame_width
        screen_height = config.frame_height

        # 确定矩阵的边界尺寸
        matrix_width = m.width
        matrix_height = m.height

        # 计算缩放比例，确保矩阵等比缩放并占满屏幕
        scale_factor = min(screen_width / matrix_width, screen_height / matrix_height)
        m.scale(scale_factor-0.2)

        # 将矩阵放置在屏幕中心
        m.move_to(ORIGIN)

        # 添加到场景
        self.add(m)


class MatrixDetShow(Scene):
    def __init__(self,data_load=None):
        super().__init__()
        self.data_load = data_load
    def construct(self):
        if self.data_load:
            mat_input = self.data_load
        else:
            mat_input = fo.read_matrix_from_file(os.path.join(fo.default_file_path, "matrix0_cache.txt"),'numpy')
        length = len(mat_input)
        mat_mob = MatrixDet(mat_input)
        mat_mob_det = mat_mob.det_mat()
        neg_mat = mat_mob.neg_with_brackets()
        neg_mat = neg_mat.det_mat()
        neg_mat.set_scale_fitness()
        res_vgp = mat_mob_det.cal_result_addition().shift(DOWN * 2).scale_to_fit_width(12)
        self.play(Write(mat_mob), run_time=2)
        self.wait()
        self.play(Transform(mat_mob, mat_mob_det))
        self.wait()
        self.play(mat_mob.animate.set_scale_fitness())
        self.wait()

        res_vgp_cp = res_vgp.copy()
        for i in range(2 * length):
            vgp, vgp_brackets, num_lst = mat_mob.get_process_inform(i if i < length else length - i - 1, neg_mat)
            self.play(vgp.animate.set_color(color_list[i]))
            pro_vgp = cal_progress_times(color_list[i], vgp_brackets, num_lst).shift(DOWN)
            pro_vgp_cp = pro_vgp.copy()
            for j in range(length):
                pro_vgp[2 * j].move_to(vgp[j])
                self.add(pro_vgp[2 * j])
                self.play(pro_vgp[2 * j].animate.move_to(pro_vgp_cp[2 * j]), run_time=time_control)
                self.play(FadeIn(pro_vgp[2 * j + 1]), run_time=time_control)
            self.play(FadeIn(pro_vgp[-1]), run_time=time_control)
            res_vgp[2 * i].move_to(pro_vgp[-1]).set_color(color_list[i])
            self.add(res_vgp[2 * i])
            self.play(res_vgp[2 * i].animate.move_to(res_vgp_cp[2 * i]), run_time=time_control)
            self.play(FadeIn(res_vgp[2 * i + 1]), run_time=time_control)
            self.play(FadeOut(pro_vgp), run_time=time_control)
            if i == length - 1:
                self.play(mat_mob.animate.set_color(WHITE), run_time=time_control)
        self.play(FadeIn(res_vgp[-1]), run_time=time_control)
        self.wait(2)


class MatrixAdditionShow(Scene):
    def __init__(self,*data_load):
        super().__init__()
        self.data_load = data_load
    def construct(self):
        if self.data_load:
            m1_input = self.data_load[0]
            m2_input = self.data_load[1]
        else:
            m1_input = fo.read_matrix_from_file(os.path.join(fo.default_file_path, "matrix0_cache.txt"),'numpy')
            m2_input = fo.read_matrix_from_file(os.path.join(fo.default_file_path, "matrix1_cache.txt"),'numpy')
        color_add = [RED, BLUE]

        t = add_txt.copy().shift(UP * 2)
        e = equal_txt.copy()
        m1 = MatrixMath(m1_input)
        m1.fit_screen(t, LEFT)
        m2 = MatrixMath(m2_input)
        m2.fit_screen(t, RIGHT)
        m3 = m1.addition_mat(m2)
        m3.fit_screen(edge=DR)
        e.next_to(m3, LEFT)
        s1 = Square().scale_to_fit_height(m1[0][0].height / 1.2).move_to(m1[0][0]).set_color(color_add[0])
        s2 = Square().scale_to_fit_height(m2[0][0].height / 1.2).move_to(m2[0][0]).set_color(color_add[1])

        total = VGroup(m1, t, m2, e, m3[-2:])
        self.play(Write(total), run_time=4)

        ori_vgp = VGroup(
            Text(f"{m1_input[0][0]}" if m1_input[0][0] >= 0 else f"({m1_input[0][0]})").set_color(color_add[0]),
            add_txt.copy(),
            Text(f"{m2_input[0][0]}" if m2_input[0][0] >= 0 else f"({m2_input[0][0]})").set_color(color_add[1]),
            equal_txt.copy(),
            Text(f"{m1_input[0][0] + m2_input[0][0]}"),
        ).arrange().shift(DOWN * 1.75 + LEFT * 3.5)
        if ori_vgp.width > 5.5:
            ori_vgp.scale_to_fit_width(5.5)
        self.play(
            FadeIn(ori_vgp),
            FadeIn(s1),
            FadeIn(s2),
            run_time=0.5
        )

        for i in range(len(m1_input)):
            for j in range(len(m1_input[0])):
                first_txt = Text(f"{m1_input[i][j]}" if m1_input[i][j] >= 0 else f"({m1_input[i][j]})").set_color(
                    color_add[0])
                second_txt = Text(f"{m2_input[i][j]}" if m2_input[i][j] >= 0 else f"({m2_input[i][j]})").set_color(
                    color_add[1])
                res_txt = Text(f"{m1_input[i][j] + m2_input[i][j]}")
                txt_vgp = VGroup(first_txt, add_txt.copy(), second_txt, equal_txt.copy(), res_txt).arrange().shift(
                    DOWN * 1.75 + LEFT * 3.5)
                if txt_vgp.width > 5.5:
                    txt_vgp.scale_to_fit_width(5.5)
                self.play(
                    s1.animate.move_to(m1[i][j]),
                    s2.animate.move_to(m2[i][j]),
                    Transform(ori_vgp, txt_vgp),
                    run_time=0.5
                )
                self.play(ori_vgp[-1].copy().animate.scale(m3[0][0].height / 1.3).move_to(m3[i][j]), run_time=0.5)
        self.wait(2)


color_mul = [RED_A, BLUE_A, RED, BLUE]


class MatrixMulShow(Scene):
    def __init__(self,*data_load):
        super().__init__()
        self.data_load = data_load
    def construct(self):
        if self.data_load:
            mat_a_input = self.data_load[0]
            mat_b_input = self.data_load[1]
        else:
            mat_a_input = fo.read_matrix_from_file(os.path.join(fo.default_file_path, "matrix0_cache.txt"),'numpy')
            mat_b_input = fo.read_matrix_from_file(os.path.join(fo.default_file_path, "matrix1_cache.txt"),'numpy')

        run_time = 0.5

        t = times_txt.copy().shift(UP * 2)
        a = MatrixMath(mat_a_input)
        a.fit_screen(t, LEFT)
        b = MatrixMath(mat_b_input)
        b.fit_screen(t, RIGHT)
        c = a.dot_multiplication_mat(b)
        c.fit_screen(edge=DR)
        total = VGroup(a, t, b, equal_txt.copy().next_to(c, LEFT), c[-2:])

        self.play(Write(total), run_time=4)

        s1 = SurroundingRectangle(a.get_row(0), buff=0, fill_opacity=0.5, stroke_opacity=0).set_color(color_mul[0])
        sliding1 = SurroundingRectangle(a.get_row(0)[0], buff=0).set_color(color_mul[2])
        s2 = SurroundingRectangle(b.get_column(0), buff=0, fill_opacity=0.5, stroke_opacity=0).set_color(color_mul[1])
        sliding2 = SurroundingRectangle(b.get_column(0)[0], buff=0).set_color(color_mul[3])

        ori_vgp = VGroup(
            Text(f"{mat_a_input[0][0]}" if mat_a_input[0][0] >= 0 else f"({mat_a_input[0][0]})").set_color(RED),
            times_txt.copy(),
            Text(f"{mat_b_input[0][0]}" if mat_b_input[0][0] >= 0 else f"({mat_b_input[0][0]})").set_color(BLUE),
            equal_txt.copy(),
            Text(f"{mat_a_input[0][0] * mat_b_input[0][0]}"),
        ).arrange().shift(DOWN * 0.75 + LEFT * 3.5)

        if ori_vgp.width > 5.5:
            ori_vgp.scale_to_fit_width(5.5)
        part = VGroup(s1, s2, sliding1, sliding2, ori_vgp)

        self.play(FadeIn(part))

        res_mat = mat_a_input @ mat_b_input
        for i in range(res_mat.shape[0]):
            for j in range(res_mat.shape[1]):
                res_vgp = c.get_mul_progress([i, j], color_mul)
                res_vgp[0].to_edge(LEFT).shift(DOWN * 2.5)
                res_vgp[1].shift(LEFT * 2.6 + DOWN * 2.6)
                if res_vgp[1].width >= 4.3:
                    res_vgp[1].scale_to_fit_width(4.5)
                self.play(
                    FadeIn(res_vgp[0]),
                    s1.animate.move_to(a.get_row(i)),
                    s2.animate.move_to(b.get_column(j)),
                    run_time=run_time
                )

                for k in range(mat_a_input.shape[1]):
                    pro_vgp = VGroup(
                        Text(f"{mat_a_input[i][k]}" if mat_a_input[i][k] >= 0 else f"({mat_a_input[i][k]})").set_color(
                            RED),
                        times_txt.copy(),
                        Text(f"{mat_b_input[k][j]}" if mat_b_input[k][j] >= 0 else f"({mat_b_input[k][j]})").set_color(
                            BLUE),
                        equal_txt.copy(),
                        Text(f"{mat_a_input[i][k] * mat_b_input[k][j]}"),
                    ).arrange().shift(DOWN * 0.75 + LEFT * 3.5)

                    self.play(
                        Transform(ori_vgp, pro_vgp),
                        sliding1.animate.move_to(a.get_row(i)[k]),
                        sliding2.animate.move_to(b.get_column(j)[k]),
                        run_time=run_time,
                    )

                    r1_cp = res_vgp[1].copy()
                    res_vgp[1][2 * k].move_to(ori_vgp[-1])

                    self.play(
                        res_vgp[1][2 * k].animate.move_to(r1_cp[2 * k]),
                        FadeIn(res_vgp[1][2 * k + 1]),
                        run_time=run_time,
                    )

                self.play(FadeIn(res_vgp[1][-1]))
                self.play(res_vgp[1][-1].copy().animate.scale(c[0][0].height / 1.3).move_to(c[i][j]), run_time=run_time)
                self.play(FadeOut(res_vgp), run_time=run_time)

        self.wait(2)