"""Deterministic math tools. Never eval/sympify untrusted source text."""
import ast
import math
import re

import sympy as sp

from app.solution_models import Curve, Solution, SolutionStep, Visual

X = sp.Symbol("x")
FUNCTIONS = {"sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "exp": sp.exp, "log": sp.log, "sqrt": sp.sqrt, "abs": sp.Abs, "Abs": sp.Abs}


def numeric_latex(text):
    """Recognize only a whole literal number or numeric fraction, without eval."""
    text = text.strip()
    number = r"[+-]?\d{1,12}(?:\.\d{1,12})?"
    if re.fullmatch(number, text): return sp.Rational(text)
    fraction = re.fullmatch(r"\\(?:frac|dfrac|tfrac)\{("+number+r")\}\{("+number+r")\}", text)
    if fraction and sp.Rational(fraction[2]) != 0:
        return sp.Rational(fraction[1]) / sp.Rational(fraction[2])
    return None


def validate_summary_consistency(solution):
    """Catch explicit scalar contradictions; this does not prove an AI solution.

    Compare only the final equation's named quantity with a summary statement
    about that same quantity. Other numbers (coordinates, counts, conditions)
    must never be mistaken for the answer.
    """
    formula = solution.steps[-1].formula
    if '=' not in formula: return
    # A list of roots is not one scalar equality chain.
    if re.search(r"(?<!\\)[,;]|\\(?:quad|qquad|begin)|\\(?:text|mathrm)\{(?:或|or)\}", formula): return
    target, result = formula.split('=', 1)[0], formula.rsplit('=', 1)[1]
    expected = numeric_latex(result)
    if expected is None: return
    def name(value):
        value = re.sub(r"\\(?:left|right|lvert|rvert|vert)", '', value)
        return re.sub(r"[\s|]", '', value)
    target = name(target)
    if not re.fullmatch(r"[A-Za-z]{1,8}(?:_\{?\d\}?)?", target): return
    inline = list(re.finditer(r"\$([^$]+)\$", solution.summary))
    for index, token in enumerate(inline):
        parts = token[1].split('=')
        claimed = None
        if len(parts) == 2 and name(parts[0]) == target:
            claimed = numeric_latex(parts[1])
        elif name(token[1]) == target and index+1 < len(inline):
            following = inline[index+1]
            between = solution.summary[token.end():following.start()].strip()
            if re.fullmatch(r"(?:的)?(?:长度|值|面积|结果|答案)?(?:为|是|等于|=|：|:)", between):
                claimed = numeric_latex(following[1])
        if claimed is not None and claimed != expected:
            raise ValueError(f"摘要中 {target} 的值与最后一步的 {result.strip()} 不一致，请保留正确分数并核对整个解答")


def expression(text, symbols=None):
    symbols = {"x": X} if symbols is None else symbols
    text = text.strip().replace("^", "**").replace("π", "pi").replace("×", "*").replace("−", "-")
    text = re.sub(r"(?<=\d)(?=[a-zA-Z]|\()", "*", text)
    if len(text) > 180:
        raise ValueError("表达式过长")
    tree = ast.parse(text, mode="eval")
    if len(list(ast.walk(tree))) > 65:
        raise ValueError("表达式过于复杂")
    powers = [node for node in ast.walk(tree) if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow)]
    if len(powers) > 3 or any(any(isinstance(child, ast.BinOp) and isinstance(child.op, ast.Pow) for child in ast.walk(node.left)) for node in powers):
        raise ValueError("请简化嵌套幂表达式")

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if not math.isfinite(node.value) or abs(node.value) > 1e6:
                raise ValueError("数值超出范围")
            return sp.Rational(str(node.value))
        if isinstance(node, ast.Name) and node.id in {**symbols, "pi": sp.pi, "e": sp.E}:
            return {"pi": sp.pi, "e": sp.E, **symbols}[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow):
                if not isinstance(node.right, (ast.Constant, ast.UnaryOp)) or not right.is_number or abs(float(right)) > 12:
                    raise ValueError("幂指数必须是绝对值不超过 12 的常数")
                return left ** right
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div): return left / right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS and len(node.args) == 1 and not node.keywords:
            return FUNCTIONS[node.func.id](visit(node.args[0]))
        raise ValueError("仅支持数学表达式")

    result = visit(tree.body)
    if result.has(sp.zoo, sp.oo, -sp.oo, sp.nan) or sp.count_ops(result) > 50:
        raise ValueError("表达式无定义或过于复杂")
    return result


def plot(expr, label="f(x)", lo=-5, hi=5):
    fn = sp.lambdify(X, expr, modules="math")
    segments, current = [], []
    for i in range(161):
        x = lo + (hi - lo) * i / 160
        try:
            y = float(fn(x))
            if not math.isfinite(y) or abs(y) > 1000:
                raise ValueError()
            if current and abs(y - current[-1][1]) > 100:
                if len(current) >= 2: segments.append(Curve(label=label, points=current))
                current = []
            current.append((x, y))
        except (ValueError, TypeError, ZeroDivisionError, OverflowError):
            if len(current) >= 2: segments.append(Curve(label=label, points=current))
            current = []
    if len(current) >= 2: segments.append(Curve(label=label, points=current))
    return segments[:3]


def resolve_visual_functions(solution):
    """The AI chooses expressions; the math tool computes the plotted points."""
    for item in solution.steps:
        if item.visual.circles:
            for circle in item.visual.circles:
                cx, cy = circle.center
                item.visual.curves.append(Curve(label=circle.label, points=[
                    (cx + circle.radius*math.cos(i*math.tau/160), cy + circle.radius*math.sin(i*math.tau/160)) for i in range(161)]))
            item.visual.circles = []
        if item.visual.functions:
            curves = list(item.visual.curves)
            omitted = False
            for spec in item.visual.functions:
                try:
                    curves.extend(plot(expression(spec.expression), spec.label, *spec.domain))
                except (ValueError, SyntaxError, TypeError, OverflowError, ZeroDivisionError):
                    omitted = True
            item.visual.curves = curves[:6]
            item.visual.functions = []
            if omitted:
                item.visual.caption = item.visual.caption[:600] + ' 含未确定参数或无法采样的函数未绘制，请结合公式阅读推导。'
            if not curves and not (item.visual.kind == 'geometry' and len(item.visual.points) >= 2):
                item.visual = Visual(kind='reasoning', caption=item.visual.caption if omitted else '该区间未取得可绘制的实数函数值，请检查定义域。')
    return solution


def step(title, explanation, formula="", curves=None, points=None, caption="", matrix=None, hint=""):
    kind = "matrix" if matrix is not None else "plot" if curves else "reasoning"
    return SolutionStep(title=title, explanation=explanation, formula=formula, hint=hint,
                        visual=Visual(kind=kind, caption=caption, curves=curves or [], points=points or [], matrix=matrix))


def local_solution(problem):
    """Only claim local verification for whole inputs matching supported tasks."""
    from .coordinate_solver import diameter_circle
    coordinate_solution = diameter_circle(problem)
    if coordinate_solution is not None:
        return coordinate_solution
    from .rational_solver import rational_equation
    rational_solution = rational_equation(problem)
    if rational_solution is not None:
        return rational_solution
    t = problem.strip().strip("。？?")
    t = re.sub(r"^\$+|\$+$", "", t).strip()
    if (t.startswith(r"\(") and t.endswith(r"\)")) or (t.startswith(r"\[") and t.endswith(r"\]")):
        t = t[2:-2].strip()
    # Parse the entire supported LaTeX integral, never discard prose/conditions.
    bound = r"(\{-?\d+(?:\.\d+)?\}|-?\d+(?:\.\d+)?)"
    integral = re.fullmatch(r"\\int\s*_\s*" + bound + r"\s*\^\s*" + bound + r"\s*(.+?)\s*(?:\\mathrm\{d\}|d)\s*x", t)
    if integral:
        body = re.sub(r"\\[,;! ]|\\(?:left|right)", "", integral[3]).strip()
        body = body.replace(r"\cdot", "*").replace(r"\times", "*")
        t = f"定积分 {body} 从 {integral[1].strip('{}')} 到 {integral[2].strip('{}')}"
    t = re.sub(r"\^\{(-?\d+)\}", r"^\1", t)
    latex_matrix = re.fullmatch(r"(?:求|计算)?(?:矩阵|行列式)?\s*\\begin\{([bpv]?matrix)\}(.*?)\\end\{\1\}(?:的行列式)?", t, re.S)
    if latex_matrix:
        rows = [[expression(value.strip()) for value in row.split('&')] for row in latex_matrix[2].split(r'\\') if row.strip()]
        if len(rows) != 2 or any(len(row) != 2 or any(value.free_symbols for value in row) for row in rows): return None
        t = '矩阵 ' + str([[float(value) for value in row] for row in rows])
    definite = re.fullmatch(r"(?:求定积分|定积分|积分)\s+(.+?)\s+从\s+(-?[\d.]+)\s+到\s+(-?[\d.]+)", t)
    if definite:
        expr = expression(definite[1])
        if not expr.is_polynomial(X) or sp.degree(expr, X) > 12: return None
        a, b = expression(definite[2]), expression(definite[3])
        if not a < b or abs(float(a)) > 1000 or abs(float(b)) > 1000: return None
        primitive = sp.integrate(expr, X)
        answer = sp.simplify(primitive.subs(X, b)-primitive.subs(X, a))
        curves = plot(expr, "被积函数", float(a), float(b))
        steps = [step("确定积分区间", "曲线与横轴之间的有向面积代表定积分；横轴下方面积按负值计入。", r"\int_{"+sp.latex(a)+"}^{"+sp.latex(b)+"}("+sp.latex(expr)+r")\,dx", curves=curves),
                 step("观察面积累积", "拖动滑块从积分下限移向上限，观察面积如何逐渐累积。", r"A(t)=\int_{"+sp.latex(a)+"}^{t}("+sp.latex(expr)+r")\,dx", curves=curves),
                 step("求出一个原函数", "按幂函数积分法则逐项积分。定积分中积分常数会相消。", "F(x)="+sp.latex(primitive), curves=curves),
                 step("代入上下限", "根据牛顿—莱布尼茨公式，用上限处的原函数值减去下限处的值。", "F("+sp.latex(b)+")-F("+sp.latex(a)+")="+sp.latex(answer), curves=curves)]
        for item in steps[1:]: item.visual.area = True
        steps[-1].formula = r"\left[" + sp.latex(primitive) + r"\right]_{" + sp.latex(a) + "}^{" + sp.latex(b) + "}=" + sp.latex(primitive.subs(X, b)) + "-(" + sp.latex(primitive.subs(X, a)) + ")=" + sp.latex(answer)
        return Solution(title="定积分与有向面积", summary=f"定积分为 ${sp.latex(answer)}$。", source="sympy", verification="通过符号积分求原函数并代入上下限；图形使用同一被积函数采样。", steps=steps)
    matrix_match = re.fullmatch(r"(?:求|计算)?(?:矩阵|线性变换|行列式)\s*(\[\[.*\]\])(?:的行列式)?", t, re.S)
    if matrix_match:
        raw = ast.literal_eval(matrix_match[1])
        visual = Visual(kind="matrix", matrix=raw)
        m = sp.Matrix([[sp.Rational(str(v)) for v in row] for row in visual.matrix])
        a, b, c, d = list(m)
        det = m.det()
        return Solution(title="二维线性变换与行列式", summary=f"行列式为 {det}。", source="sympy",
            verification="SymPy 精确计算 ad−bc；图中显示基向量和单位正方形的变换。",
            steps=[step("识别矩阵", "矩阵的两列分别是两个标准基向量变换后的位置。", sp.latex(m), matrix=raw),
                   step("观察变换", "拖动进度滑块，观察单位正方形如何变成平行四边形。", r"T(\mathbf{x})=A\mathbf{x}", matrix=raw),
                   step("计算有向面积", "主对角线乘积减去副对角线乘积，得到面积的有向缩放倍数。", f"\\det(A)=({sp.latex(a)})({sp.latex(d)})-({sp.latex(b)})({sp.latex(c)})={sp.latex(det)}", matrix=raw),
                   step("解释结果", "面积缩放倍数为行列式的绝对值。" + ("矩阵不可逆，平面被压缩为直线或点。" if det == 0 else "矩阵可逆。" + ("方向发生翻转。" if det < 0 else "方向保持不变。")), f"|\\det(A)|={sp.latex(abs(det))}", matrix=raw)])

    match = re.fullmatch(r"(?:求导|求导数|微分|画图|绘制|求不定积分|积分)\s*[:：]?\s*(.+)", t)
    if match:
        expr = expression(match[1])
        curves = plot(expr)
        if t.startswith(("求导", "微分")):
            result = sp.diff(expr, X)
            both = curves + plot(result, "f′(x)")
            solution = Solution(title="导数与切线斜率", summary=f"导数为 ${sp.latex(result)}$。", source="sympy",
                verification="导数由 SymPy 符号微分计算，曲线由同一表达式采样。",
                steps=[step("观察原函数", "先观察函数的增减变化。拖动滑块可以沿曲线移动。", "f(x)="+sp.latex(expr), curves=curves),
                       step("建立导数定义", "导数描述一点附近函数值相对于自变量的瞬时变化率。", r"f'(x)=\lim_{h\to0}\frac{f(x+h)-f(x)}{h}", curves=curves),
                       step("应用求导法则", "按表达式结构应用幂函数、乘积、商和复合函数的求导法则。", "f'(x)="+sp.latex(result), curves=both),
                       step("比较两条曲线", "原函数上升时导数为正，下降时导数为负；导数为零的点需进一步判断是否为极值。拖动滑块观察切线斜率。", "f'(x)="+sp.latex(result), curves=both)])
            if len(curves) == 1 and len(both) == 2:
                for item in solution.steps[2:]: item.visual.tangent = True
            return solution
        if t.startswith(("积分", "求不定积分")):
            if not expr.is_polynomial(X) or sp.degree(expr, X) > 12:
                return None
            result = sp.integrate(expr, X)
            return Solution(title="多项式不定积分", summary=f"原函数为 ${sp.latex(result)} + C$。", source="sympy",
                verification="已对结果求导，验证其等于被积函数。",
                steps=[step("识别被积函数", "将多项式视为各个幂函数项的和，逐项积分。", sp.latex(expr), curves=curves),
                       step("应用幂函数积分法则", "每项指数加一，再除以新的指数；常数项的原函数是一次函数。", r"\int x^n\,dx=\frac{x^{n+1}}{n+1}+C\quad(n\ne-1)", curves=curves),
                       step("合并并补上积分常数", "图中取 C=0；其它原函数是该曲线沿竖直方向平移得到的。", r"\int ("+sp.latex(expr)+r")\,dx="+sp.latex(result)+"+C", curves=plot(result, "F(x), C=0")),
                       step("反向验证", "对得到的原函数求导，恰好返回原来的被积函数。", r"F'(x)="+sp.latex(sp.diff(result, X)), curves=curves)])
        return Solution(title="函数图像探索", summary="通过曲线上的采样点观察函数值与变化趋势。", source="sympy",
            verification="曲线由输入表达式计算采样得到；图像展示的是有限区间。",
            steps=[step("读取表达式", "以 x 为自变量，计算对应的函数值。", "y="+sp.latex(expr), curves=curves),
                   step("观察函数图像", "拖动滑块读取曲线上的点。未定义或数值过大的区域会断开显示。", "y="+sp.latex(expr), curves=curves)])

    equation = re.fullmatch(r"(?:(?:求解|解方程|解|求方程的解)\s*[:：]?\s*)?([\d\sx+*/^().=−-]+)", t)
    if not equation or equation[1].count("=") != 1:
        return None
    for part in equation[1].split("="):
        tree = ast.parse(re.sub(r"(?<=\d)(?=x|\()", "*", part.strip().replace("^", "**")), mode="eval")
        if any(isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and any(isinstance(child, ast.Name) for child in ast.walk(node.right)) for node in ast.walk(tree)):
            return None  # Rational equations need explicit domain/excluded-root analysis.
    left, right = (expression(part) for part in equation[1].split("="))
    expr = sp.expand(left-right)
    if not expr.is_polynomial(X) or sp.degree(expr, X) not in (1, 2): return None
    roots = sp.solve(expr, X)
    if not all(sp.simplify(expr.subs(X, r)) == 0 for r in roots): return None
    real_roots = [float(r) for r in roots if r.is_real and abs(float(r)) < 1e4]
    padding = max(1.0, (max(real_roots)-min(real_roots))*.35) if real_roots else 1
    lo, hi = (min(real_roots)-padding, max(real_roots)+padding) if real_roots else (-5, 5)
    curves = plot(expr, "左边 − 右边", lo, hi)
    points = [(r, 0) for r in real_roots]
    answer = r",\quad ".join("x="+sp.latex(r) for r in roots)
    steps = [step("整理方程", "将等式右侧移到左侧；函数的实数零点对应方程的实数解。", sp.latex(expr)+"=0", curves=curves)]
    if sp.degree(expr, X) == 2:
        a, b, c = sp.Poly(expr, X).all_coeffs()
        delta = b*b-4*a*c
        factored = sp.factor(expr)
        if all(root.is_Rational for root in roots):
            steps += [step("分解为因式的乘积", "提取公因式并分解二次多项式，保持等式两边相等。", sp.latex(factored)+"=0", curves=curves),
                      step("令每个因式为零", "乘积为零意味着至少一个因式为零，分别解这些一次方程。", r"\quad\mathrm{or}\quad ".join(sp.latex(X-r)+"=0" for r in roots), curves=curves, points=points)]
        else:
            steps += [step("计算判别式", "将实际系数代入判别式，判断根的情况。", r"\Delta=("+sp.latex(b)+")^2-4("+sp.latex(a)+")("+sp.latex(c)+")="+sp.latex(delta), curves=curves),
                      step("代入求根公式", "代入本题系数和判别式，分别取正号和负号。", r"x=\frac{"+sp.latex(-b)+r"\pm\sqrt{"+sp.latex(delta)+"}}{"+sp.latex(2*a)+"}", curves=curves, points=points)]
    else:
        a, b = sp.Poly(expr, X).all_coeffs()
        steps.append(step("两边减去常数项", "对等式两边实施同样的减法，保持等式成立。", sp.latex(a*X)+"="+sp.latex(-b), curves=curves))
        steps.append(step("两边除以未知数系数", "一次项系数非零，两边同除以该系数。", "x="+sp.latex(-b/a), curves=curves, points=points))
    steps.append(step("代回验证与结论", "将每个解代回原方程，两边相等。" + ("图中的标记是实数解对应的零点。" if points else "本题没有实数零点，解位于复数域。"), answer, curves=curves, points=points))
    return Solution(title="方程的解与函数零点", summary="解为："+", ".join(str(r) for r in roots), steps=steps, source="sympy", verification="已用 SymPy 将所有解代回原方程，残差均为 0。")
