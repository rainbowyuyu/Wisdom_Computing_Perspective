"""Task guidance and bounded checks for model-derived parameter constraints."""
import json
import re

import sympy as sp

from app.solution_models import Solution, Visual, CirclePlot, NumberLineRow, NumberInterval
from logic.solution_engine import expression


def strategy_guidance(problem):
    guidance = [
        "先辨认题型、所求量、全部条件和定义域，再选择方法；不强制所有题目套用同一解题模板。",
        "允许标准化全角符号、换行、² 和 LaTeX 记号；直线标签 l/1、圆的下标只作为名称，不得更改系数、条件或所求量。",
        "每步写出本题的条件如何转成算式、等价变形的理由、必要的分类讨论和结论；不能跳过端点、无解或增根检查。",
        "参数未赋具体值不等于条件不足：能用参数表示的方程、长度、函数或概率应给出含参答案及成立条件。只有缺少无法由题意推出的必要条件才要求补充。",
        "先分别确认已知条件、隐含条件、全部所求和输出形式。答案必须回应原题所求：求圆的方程就给方程，不能只给交点或参数范围；多问逐项作答，未完成的目标明确标记 partial。",
        "只输出需要的 visual 字段，省略空数组、null 和默认值；无法画图时用 reasoning，不用编造采样点来填满图形。",
    ]
    rules = [
        (r"圆|直线|圆锥|抛物线|椭圆|双曲线", "解析几何：先读出圆心、半径、斜率或焦点；把位置关系转为距离、判别式或方程组。半径由平方求出时先取绝对值，再使用正负条件。直线与圆无公共点是 d>r；两圆相交于两点是 |r1-r2|<d<r1+r2，相切另算；最后联立所有限制。"),
        (r"直径|弦|中点|韦达", "弦与直径圆：设两交点并联立方程；两个不同实交点要求判别式严格大于零。优先用韦达求根的和与积，圆心是弦中点，半径平方是两端点距离平方的四分之一；无需强行求根号坐标。把中心和半径代入圆的标准方程，并保留参数条件，检查退化情形。"),
        (r"取值|范围|不等式|参数|最值", "参数/不等式：逐项列出条件，处理绝对值、分母和端点，分别求解再取交集或分类并集；写清开闭区间。对一元、至多二次多项式及绝对值不等式，必须填写 parameter_analysis 供精确求交集和数轴显示。"),
        (r"导数|求导|积分|极限|连续|微分", "微积分：明确变量、定义域、单侧/双侧极限和积分上下限；注明求导或换元法则，分段与不可导点分开处理；图像辅助理解不能替代证明。"),
        (r"概率|抽样|随机|排列|组合|分布", "概率统计：先定义样本空间和事件，区分有放回/无放回、独立/条件概率，先计数后计算，检查概率在[0,1]；不要自动假设等可能或独立。"),
        (r"数列|递推|通项|求和", "数列：写明首项、指标范围与递推关系；区分等差、等比和一般递推，推导通项或求和时检查 n=1 和特殊公比。"),
        (r"证明|三角形|向量|夹角", "证明/向量：列出所用定理的适用条件，每步说明依据；辅助点和坐标须满足原题约束，不能以个别数值图或特殊位置代替一般证明。"),
        (r"方程|根式|对数|分式", "代数：先确定分母非零、根式与对数定义域；平方、约分、换元后检查增根或漏根；联立方程须保留全部条件。"),
        (r"矩阵|行列式|特征|秩|线性", "线性代数：区分方程组、行列式、秩、特征值与特征向量；消元写明行变换。含参主元为零时分支讨论；特征向量不得取零向量；矩阵大小不适配二维动画时保留 LaTeX 矩阵推导。"),
        (r"微分方程|初值|通解|特解", "微分方程：先辨别方程阶数与类型，说明解的适用区间，保留积分常数；除以未知函数前检查零解，代入初值并验证原方程。"),
    ]
    guidance += [text for pattern, text in rules if re.search(pattern, problem)]
    guidance.append(
        "parameter_analysis 格式：purpose=answer 仅限全部所求就是参数范围；参数只是方程、长度、函数、证明等结果的成立条件或题目还求其他量时，必须 purpose=domain，不能拿条件取代答案。variable 为单个字母；constraints 中每项含 label、left、relation、right，拆开连不等式，保留题设正负限制。"
        "表达式用普通数学文本，例如 abs(m)/sqrt(2)、1+m，relation 用 < <= > >= = !=，不要用 LaTeX。"
        "answer 是最终区间的并集：每项 lower/upper 为精确表达式字符串（例如 3*sqrt(2)），null 分别表示负/正无穷，"
        "lower_closed/upper_closed 表示是否包含端点；空列表表示无解。必须与 summary 中对应的参数限制一致。"
        "非一元代数区间题或超出此工具范围时 parameter_analysis=null，不得为了调用工具删掉条件。"
        "geometry.circles 可直接给圆心 center:[x,y]、数值半径 radius 和 label，系统计算圆周，禁止逐点编造圆。"
        "半径未确定时画已知圆与圆心距离，参数范围使用自动生成的数轴；不任取参数假装一般图形。"
    )
    return "\n".join(guidance)


def parse_solution(content):
    """Accept a fenced JSON document, without guessing at damaged math escapes."""
    text = (content or '').strip()
    fence = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.I)
    if fence:
        text = fence[1]
    payload = json.loads(text)
    # A model's optional diagram is not allowed to invalidate its algebra.
    # Convert exact numeric coordinates safely, but never invent a parameter value.
    for step in payload.get('steps', []) if isinstance(payload, dict) else []:
        if not isinstance(step, dict) or not isinstance(step.get('visual'), dict):
            continue
        visual = step['visual']
        if visual.get('kind') == 'geometry' and isinstance(visual.get('circles'), list):
            circles, omitted = [], False
            for raw in visual['circles']:
                try:
                    def numeric(value):
                        return float(expression(str(value), symbols={}))
                    circle = CirclePlot(center=[numeric(v) for v in raw['center']], radius=numeric(raw['radius']), label=raw.get('label',''))
                    circles.append(circle.model_dump())
                except (KeyError, ValueError, TypeError, SyntaxError, OverflowError):
                    omitted = True
            visual['circles'] = circles
            if omitted:
                visual['caption'] = (str(visual.get('caption',''))[:600]+' 含未确定参数或无法计算的圆未按固定半径绘制，请结合公式与数轴阅读。')
        try:
            step['visual'] = Visual.model_validate(visual).model_dump()
        except ValueError:
            step['visual'] = {'kind':'reasoning','caption':'本步图形含未确定的坐标或无法绘制的数据，请按公式与说明理解推导；其余步骤继续展示。'}
    return Solution.model_validate(payload)


def parameter_expression(text, variable):
    # Normalize common math notation before the same restricted AST parser.
    text = text.strip().strip('$').replace('²', '^2').replace('³', '^3').replace('（', '(').replace('）', ')')
    text = text.replace(r'\left', '').replace(r'\right', '').replace(r'\cdot', '*').replace(r'\times', '*')
    for _ in range(6):
        before = text
        text = re.sub(r'\\(?:dfrac|tfrac|frac)\{([^{}]+)\}\{([^{}]+)\}', r'((\1)/(\2))', text)
        text = re.sub(r'\\sqrt\{([^{}]+)\}', r'sqrt(\1)', text)
        text = re.sub(r'\^\{([^{}]+)\}', r'^(\1)', text)
        if before == text: break
    text = re.sub(r'\|([^|]+)\|', r'abs(\1)', text)
    try:
        value = expression(text, {str(variable): variable})
    except (SyntaxError, TypeError, OverflowError, ZeroDivisionError, ValueError) as error:
        raise ValueError(f'参数工具不能读取表达式 {text[:180]!r}；请改用普通数学文本、显式乘号与变量 {variable}，不填入等号、集合或完整不等式。仅该子字段无法使用工具时设 parameter_analysis=null，保留完整题解。') from error
    if value.free_symbols - {variable}:
        raise ValueError("区间计算仅支持一个实参数")
    for fn in value.atoms(sp.Function):
        if fn.func != sp.Abs or not fn.args[0].is_polynomial(variable) or sp.degree(fn.args[0], variable) > 2:
            raise ValueError("区间工具只支持多项式和绝对值，请保留完整条件使用普通推导")
    polynomial = value.xreplace({v: sp.Symbol(f'_abs{i}') for i, v in enumerate(value.atoms(sp.Abs))})
    symbols = polynomial.free_symbols
    if symbols and (not polynomial.is_polynomial(*symbols) or sp.Poly(polynomial, *symbols).total_degree() > 2):
        raise ValueError("区间工具仅支持至多二次表达式，请使用普通推导")
    if len(value.atoms(sp.Abs)) > 2:
        raise ValueError("绝对值分支过多，请使用普通推导")
    return value


def set_intervals(value):
    if value == sp.S.EmptySet:
        return []
    if value == sp.S.Reals:
        value = sp.Interval(-sp.oo, sp.oo)
    parts = value.args if isinstance(value, sp.Union) else [value]
    result = []
    for part in parts:
        if isinstance(part, sp.FiniteSet):
            result.extend(sp.Interval(point, point) for point in part)
        elif isinstance(part, sp.Interval):
            result.append(part)
        else:
            raise ValueError("无法把结果转换为有限个实区间")
    return result


def number_intervals(value):
    rows = []
    def endpoint(v):
        if v in (sp.oo, -sp.oo): return None, ''
        number = float(v)
        if not -1e6 <= number <= 1e6:
            raise ValueError("数轴端点超出可显示范围")
        return number, str(v).replace('sqrt(', '√(').replace('*', '·')
    for part in set_intervals(value):
        if isinstance(part, sp.FiniteSet):
            lo = hi = next(iter(part)); lc = uc = True
        else:
            lo, hi, lc, uc = part.start, part.end, not part.left_open, not part.right_open
        lower, lower_label = endpoint(lo); upper, upper_label = endpoint(hi)
        rows.append(NumberInterval(lower=lower, upper=upper, lower_closed=lc, upper_closed=uc,
                                   lower_label=lower_label, upper_label=upper_label))
    return rows


def verify_parameter_analysis(solution, problem=None):
    """Verify the algebra of supplied conditions, not their extraction from prose."""
    analysis = solution.parameter_analysis
    if analysis is None:
        return solution
    variable = sp.Symbol(analysis.variable, real=True)
    operators = {'<': sp.Lt, '<=': sp.Le, '>': sp.Gt, '>=': sp.Ge, '=': sp.Eq, '!=': sp.Ne}
    intersection = sp.S.Reals
    rows = []
    for condition in analysis.constraints:
        left, right = (parameter_expression(text, variable) for text in (condition.left, condition.right))
        relation = operators[condition.relation](left, right)
        if relation in (sp.S.true, sp.S.false):
            values = sp.S.Reals if relation == sp.S.true else sp.S.EmptySet
        else:
            values = sp.solve_univariate_inequality(relation, variable, relational=False)
        intersection = intersection.intersect(values)
        rows.append(NumberLineRow(label=condition.label, intervals=number_intervals(values)))
    proposed = sp.S.EmptySet
    for interval in analysis.answer:
        lo = -sp.oo if interval.lower is None else parameter_expression(interval.lower, variable)
        hi = sp.oo if interval.upper is None else parameter_expression(interval.upper, variable)
        if lo.free_symbols or hi.free_symbols:
            raise ValueError("最终区间端点不能仍含待求参数")
        proposed = proposed.union(sp.Interval(lo, hi, left_open=not interval.lower_closed, right_open=not interval.upper_closed))
    if proposed != intersection:
        raise ValueError(f"所列条件的交集为 {sp.latex(intersection)}，与你的最终区间不一致。核对原题、所有步骤、summary 和 answer；若条件齐全请据此修正，不能删除限制来凑答案。")
    rows.append(NumberLineRow(label='所有条件的交集', intervals=number_intervals(intersection)))
    # When processing a full question, only a pure interval request may replace
    # its conclusion. Legacy direct callers keep the original interval behavior.
    interval_only = problem is None or bool(re.search(r'(?:求|解|确定|讨论)[^。；;\n]{0,100}(?:范围|取值|解集|不等式)[。？?\s]*$', problem))
    other_goal = bool(problem and re.search(r'(?:求|证明|计算|写出|确定)[^。；;\n]{0,100}(?:方程|通项|面积|体积|概率|长度|半径|圆心|导数|积分|极限|特征|矩阵|函数|轨迹)', problem))
    if analysis.purpose == 'domain' or not interval_only or other_goal:
        analysis.purpose = 'domain'
        parameter_pattern = r'(?<![A-Za-z\\])'+re.escape(analysis.variable)+r'(?![A-Za-z])'
        for step in solution.steps:
            visual = step.visual
            graph_text = step.formula+' '+visual.caption+' '+' '.join(c.label for c in visual.curves)+' '+' '.join(f.label for f in visual.functions)
            if visual.kind in {'plot','geometry'} and re.search(parameter_pattern, graph_text):
                step.visual = Visual(kind='reasoning', caption='本步保留参数的一般推导；参数未确定，不以任意数值图代替题目条件。')
        solution.verification = '已用符号计算校验所列参数条件的交集；主结论与题意到条件的转换仍需核对。'
        return solution
    solution.steps[-1].visual = Visual(kind='number_line', rows=rows, caption='分别求出每个条件的范围，再取公共部分；空心端点不包含，实心端点包含。')
    # Canonicalize the displayed conclusion too: a correct tool field must not mask wrong prose.
    conclusion = f"{analysis.variable} \\in {sp.latex(intersection)}"
    solution.steps[-1].formula = conclusion
    solution.summary = f"联立以上条件，得到 ${conclusion}$。" + ("没有满足所有条件的实数取值。" if intersection == sp.S.EmptySet else '')
    solution.verification = "已用符号计算校验所列不等式及区间交集；题意到条件的转换由 AI 完成，仍需核对是否覆盖原题全部条件。"
    return solution
