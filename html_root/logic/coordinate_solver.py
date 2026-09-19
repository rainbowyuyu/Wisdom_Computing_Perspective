"""Exact chord/diameter construction for completely recognized quadratic tasks.

Unrecognized wording or extra conditions must fall through to the general solver.
No numeric value is invented for a symbolic parameter.
"""
import ast
import re

import sympy as sp

from app.solution_models import CirclePlot, Solution, Visual
from .solution_engine import X, expression, plot, resolve_visual_functions, step


def polynomial_source(text, symbols):
    value = expression(text, symbols)
    normalized = re.sub(r'(?<=\d)(?=[a-zA-Z]|\()', '*', text.replace('^', '**'))
    for node in ast.walk(ast.parse(normalized, mode='eval')):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            if any(isinstance(n, ast.Name) for n in ast.walk(node.right)):
                raise ValueError('原式含变量分母，交由完整定义域推导处理')
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow) and expression(ast.unparse(node.right)) < 0:
            raise ValueError('原式含负指数，需保留定义域')
    return value


def diameter_circle(problem):
    text = problem.translate(str.maketrans({'²':'^2', '³':'^3', '−':'-', '，':',', '：':':', '（':'(', '）':')'}))
    text = re.sub(r'\s+|\$|\\[()[\]]|\\(?:left|right)', '', text).strip('。？?')
    text = re.sub(r'\^\{(-?\d+)\}', r'^\1', text)
    match = re.fullmatch(
        r'(?:已知)?(?:抛物线|二次函数):?y=(?P<curve>.+?)'
        r'(?:与|和)(?P<line>x轴|横轴|(?:直线)?y=[^,]+?)'
        r'(?:交于|相交于)(?P<a>[A-Z])(?:、|,|和|与)?(?P<b>[A-Z])(?:两点|两不同点|两个不同的点|两个不同点)'
        r'[,。]?求(?:以)?(?:线段)?(?P=a)(?P=b)为直径的圆(?:的)?(?:标准)?方程', text)
    if not match or match['a'] == match['b']:
        return None
    # Accept rational coefficients and at most one real parameter in the
    # constant term. Other cases retain every condition for the AI solver.
    names = set(re.findall(r'[A-Za-z]', match['curve'])) - {'x'}
    if len(names) > 1 or names & {'e', 'y'}:
        return None
    symbols = {name:sp.Symbol(name, real=True) for name in names}
    try:
        curve = polynomial_source(match['curve'], {'x':X, **symbols})
        line = sp.S.Zero if match['line'] in {'x轴', '横轴'} else polynomial_source(match['line'].split('=', 1)[1], {'x':X})
        if not curve.is_polynomial(X) or sp.degree(curve, X) != 2:
            return None
        if not line.is_polynomial(X) or sp.degree(line, X) not in (-sp.oo, 0, 1):
            return None
        a, b, c = sp.Poly(curve - line, X).all_coeffs()
        if not a.is_Rational or not b.is_Rational or a == 0:
            return None
        if names and (not c.is_polynomial(*symbols.values()) or sp.Poly(c, *symbols.values()).total_degree() > 2):
            return None
        k, h = line.coeff(X), line.subs(X, 0)
        if not k.is_Rational or not h.is_Rational:
            return None
        delta = sp.factor(b*b - 4*a*c)
        cx = -b/(2*a)
        cy = sp.simplify(k*cx + h)
        radius_squared = sp.factor((1+k*k)*delta/(4*a*a))
        condition = sp.solve_univariate_inequality(delta > 0, next(iter(symbols.values()))) if symbols else delta > 0
    except (ValueError, TypeError, SyntaxError, NotImplementedError, sp.PolynomialError):
        return None
    latex = sp.latex
    intersection = latex(curve-line) + '=0'
    steps = [step('联立曲线与直线', '把直线方程代入抛物线，得到两交点横坐标满足的二次方程。', intersection,
                  hint='交点同时满足两个图形的方程；与横轴相交时令 $y=0$。'),
             step('检查两个不同交点', '两点不同，因此二次方程必须有两个不同实根，判别式严格大于零。',
                  r'\Delta='+latex(delta)+(r'>0\quad\Longrightarrow\quad '+latex(condition) if symbols else ('>0' if delta > 0 else r'\le0')),
                  hint='等号对应相切、两端点重合，不能构成非退化直径圆。')]
    if condition == sp.S.false:
        steps.append(step('核对题设', '给定曲线和直线没有两个不同实交点，题设的两点条件不成立，不能构造所求圆。', r'\Delta='+latex(delta)+r'\le0'))
        return Solution(title='交点条件与直径圆', summary='题设不成立：不存在两个不同实交点，因此不存在所求的非退化圆。', steps=steps,
                        source='sympy', verification='已精确计算交点方程的判别式，检查实交点存在性。')
    total, product = -b/a, c/a
    left = sp.Add((X-cx)**2, (sp.Symbol('y')-cy)**2, evaluate=False)
    equation = latex(left)+'='+latex(radius_squared)
    restriction = (r'\quad('+latex(condition)+')') if symbols else ''
    steps.extend([
        step('用韦达关系避开繁琐求根', '设两个交点横坐标为 $x_1,x_2$。求中点和弦长只需根的和与积。',
             r'x_1+x_2='+latex(total)+r',\quad x_1x_2='+latex(product), hint='不必分别求出含根号的两个交点。'),
        step('由弦中点确定圆心', '直径中点就是圆心；横坐标取两根的平均值，纵坐标代入直线方程。',
             r'O=\left(\frac{x_1+x_2}{2},'+latex(k)+r'\frac{x_1+x_2}{2}+'+latex(h)+r'\right)=\left('+latex(cx)+','+latex(cy)+r'\right)'),
        step('由直径长度求半径平方', '两端点纵坐标之差等于斜率乘横坐标之差。用根的和、积求差的平方，再除以四。',
             r'r^2=\frac{1+('+latex(k)+r')^2}{4}\left[(x_1+x_2)^2-4x_1x_2\right]='+latex(radius_squared),
             hint='保持半径平方的形式，避免开方后再平方。'),
        step('写出圆的方程并检查条件', '把圆心和半径平方代入标准方程；两交点代入圆方程均成立。'+
             ('参数表示一族圆，满足判别式条件即可，无需给参数指定数值。' if symbols else '半径平方为正，得到非退化圆。'),
             equation+restriction, hint='结论包括方程及适用条件，不能只给参数范围。')])
    # Check the circle residual modulo the intersection polynomial. This
    # verifies both endpoints simultaneously, without choosing example roots.
    residual = sp.expand((X-cx)**2+(line-cy)**2-radius_squared)
    if sp.rem(residual, curve-line, X) != 0:
        return None
    if not symbols:
        radius = float(sp.sqrt(radius_squared))
        roots = sorted(float(r) for r in sp.solve(curve-line, X))
        lo, hi = float(cx)-radius*1.4, float(cx)+radius*1.4
        if radius <= 1e4 and max(abs(lo),abs(hi),abs(float(cy))) <= 1e5:
            curves = plot(curve, '抛物线', lo, hi)+plot(line, '交点所在直线', lo, hi)
            points = [(r,float(line.subs(X,r))) for r in roots]
            for index, item in enumerate(steps):
                item.visual = Visual(kind='geometry', curves=curves, points=points+([(float(cx),float(cy))] if index >= 3 else []),
                    labels=[match['a'],match['b']]+(['O'] if index >= 3 else []), segments=[(0,1)] if index >= 3 else [],
                    circles=[CirclePlot(center=(float(cx),float(cy)),radius=radius,label='直径圆')] if index == len(steps)-1 else [],
                    caption='交点、中点和圆均由本题数据计算；先构建弦，再补上所求圆。')
    return resolve_visual_functions(Solution(title='曲线交点与直径圆', summary='所求圆为 $'+equation+'$。'+('适用条件为 $'+latex(condition)+'$。' if symbols else ''),
        steps=steps, source='sympy', verification='已用符号计算校验判别式、韦达关系、圆心和半径，并验证交点满足圆的方程；未对参数任意赋值。'))
