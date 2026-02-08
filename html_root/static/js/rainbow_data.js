// static/js/rainbow_data.js

export const RAINBOW_LIB_INFO = {
    title: "Rainbow_Yu Manim Extensions 🐋✨",
    description: "基于 Manim 的动画控制与操作的改进与补充库。提供更便捷的数据结构展示和矩阵运算动画。",
    github: "https://github.com/rainbowyuyu/manim_extend_rainbow",
    modules: [
        {
            title: "Basic Unit - SquTex",
            image: "assets/tool_block/squ_tex.png",
            desc: "数据块组件，常用于数据结构和二进制编码演示。支持组合动画。",
            code: `from manim import *
from yty_manim.basic_unit.squ_tex import SquTex

class GenScene(Scene):
    def construct(self):
        # 创建数据块
        t = SquTex("rainbow")
        
        # 逐个展示动画
        self.play(t.animate_one_by_one(FadeIn, scale=1.5))
        self.wait()`
        },
        {
            title: "Basic Unit - SquTexSlide",
            desc: "滑动数据块，支持内部或外部滑动，带有平滑的淡入淡出效果。",
            code: `from manim import *
from yty_manim.basic_unit.squ_tex import SquTexSlide

class GenScene(Scene):
    def construct(self):
        s = SquTexSlide("rainbow")
        self.add(s)
        self.wait()
        
        # 执行滑动动画
        for i in range(len(s)):
            self.play(*s.slide(-1))
        self.wait()`
        },
        {
            title: "Basic Unit - Stack",
            desc: "栈结构演示，支持 push/pop/swap/reverse 以及可视化的指针跟随。",
            code: `from manim import *
from yty_manim.basic_unit.squ_tex import Stack

class GenScene(Scene):
    def construct(self):
        # 创建栈
        s = Stack([1,2,3,4,5], need_pointer=True, pointer_direction=UP)
        self.play(Create(s))
        
        # 指针移动
        self.play(s.animate.move_pointer(2))
        
        # 交换元素
        self.play(*s.swap(0, 3))
        
        # 弹出元素
        self.play(*s.pop(-1))
        self.wait()`
        },
        {
            title: "Application - PageReplacement",
            desc: "操作系统页面置换算法演示（OPT/LRU/FIFO/CLOCK）。",
            code: `from manim import *
from yty_manim.application.page_replacement import OptPageReplacement

class GenScene(Scene):
    def construct(self):
        # 定义页面访问序列
        input_lst = [7,0,1,2,0,3,0,4,2,3]
        
        # 创建 OPT 算法演示对象
        p = OptPageReplacement(input_lst, page_frame_num=3)
        self.add(p)
        self.wait()
        
        # 步进演示
        for i in range(len(input_lst)-1):
           p.step_on(self, i)
        self.wait()`
        },
        {
            title: "Application - MatrixCal",
            desc: "矩阵控制基类，支持生成带负号和括号的矩阵，精准控制行列元素。",
            code: `from manim import *
from yty_manim.application.matrix_yty import MatrixCal

class GenScene(Scene):
    def construct(self):
        mat = MatrixCal([[1, 2], [-3, 4]])
        self.add(mat)
        self.wait()`
        },
        {
            title: "Application - TitleAnimate",
            image: "assets/tool_block/matrix_example.png",
            desc: "标题文字的高级入场和出场动画效果。",
            code: `from manim import *
from yty_manim.application.title_animate import TitleAnimate

class GenScene(Scene):
    def construct(self):
        ta = TitleAnimate("RainbowYu")
        
        # 生成动画
        ta.generate(self, run_time=0.5)
        self.wait(1)
        
        # 消失动画
        ta.disappear(self, run_time=0.2)
        self.wait()`
        }
    ]
};