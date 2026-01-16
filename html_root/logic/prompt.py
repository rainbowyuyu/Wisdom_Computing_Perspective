# rainbow_yu animate_cal.__init__ 🐋✨
# Date : 2026/1/16 14:35

def return_prompt(
        op_desc,
        latex_a,
        latex_b,
        **kwargs
):
    return f"""
你是一名**精通 Manim Community Edition（v0.17+）的 Python 动画工程专家**，擅长将数学计算过程转化为**结构清晰、节奏自然、排版美观的动画演示**。

请**生成一份完整、可直接运行的 Python 脚本**，用于使用 **Manim** 渲染以下数学计算过程：

操作类型（自然语言描述）：
{op_desc}

输入公式 A（LaTeX）：
{latex_a}

输入公式 B（可选，LaTeX）：
{latex_b}

---

【硬性技术要求（必须严格遵守）】

1. **必须导入**
   from manim import *

2. **必须定义**
   一个继承自 Scene 的类，类名固定为：
   GenScene

3. **所有动画逻辑**
   必须写在 GenScene 的 construct(self) 方法中

4. **所有数学公式**
   必须使用 MathTex 渲染，且 LaTeX 字符串必须使用：
   r"..."（原始字符串）

5. **背景颜色**
   保持 Manim 默认黑色背景，不允许修改背景配置

6. **禁止**

   * 输出 Markdown 标记
   * 输出解释性文字
   * 输出除 Python 代码以外的任何内容

---

【动画结构与视觉规范（非常重要）】

动画必须严格按照以下 **三阶段结构** 组织：

### 第一阶段：输入展示

* 将输入公式 A（以及 B，如果存在）显示在画面上方
* 多个输入公式使用 VGroup 纵向排列（aligned_edge=LEFT）
* 使用合理的缩放（scale ≈ 0.5）
* 公式之间保持足够垂直间距（buff ≥ 0.3）

### 第二阶段：计算过程

* 计算步骤逐行展示，每一步是一个独立的 MathTex 对象
* 适当大小（scale ≈ 0.6）
* 新步骤出现在上一行的正下方
* 所有计算过程公式整体居中对齐
* 使用 Transform / ReplacementTransform 表达“推导关系”
* 不允许公式发生重叠、穿插或越界

### 第三阶段：最终结果

* 最终结果单独显示
* 居中、适当放大（scale ≈ 0.6）
* 使用简洁动画（如 FadeIn / Write）
* 结尾保留画面至少 1.5 秒（self.wait(1.5)）

---

【动画与排版稳定性要求】

* 所有 MathTex 对象在动画前必须完成定位（.to_edge / .next_to / .move_to）
* 不允许在 Transform 过程中出现跳动、闪烁
* 推荐使用：

  * VGroup
  * arrange(DOWN)
  * next_to
* 避免使用硬编码坐标（如 [x, y, z]）

---

【兼容性与健壮性】

* 代码必须兼容 Manim Community Edition v0.17+
* 不使用实验性 API
* 不使用 ThreeDScene
* 不使用外部资源
* 不使用 TexTemplate 自定义（使用默认 LaTeX 环境）

---

【最终输出要求】

* 输出内容 **仅包含完整 Python 源代码**
* 脚本可以直接通过以下命令渲染成功：

python -m manim -ql your_file.py GenScene

---

【风格目标】

生成的动画应满足：

* 逻辑清晰
* 层次分明
* 排版稳定
* 观感“像教材级 / 课程演示级”
"""