"""Bounded real rational equations with original denominator restrictions."""
import ast
import re

import sympy as sp

from app.solution_models import Solution
from .solution_engine import X, expression, step


def rational_equation(problem):
    text = problem.strip().strip('。？?').replace('²', '^2').replace('−', '-')
    text = re.sub(r'\^\{(-?\d+)\}', r'^\1', text)
    match = re.fullmatch(r'(?:(?:求解|解方程|解|求方程的解)\s*[:：]?\s*)?([\d\sx+*/^().=-]+)', text)
    if not match or match[1].count('=') != 1:
        return None
    parts = match[1].split('=')
    try:
        values = [expression(p) for p in parts]
        restrictions = []
        for part in parts:
            normalized = re.sub(r'(?<=\d)(?=x|\()', '*', part.strip().replace('^', '**'))
            tree = ast.parse(normalized, mode='eval')
            for node in ast.walk(tree):
                denominator = None
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                    denominator = node.right
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
                    if expression(ast.unparse(node.right)) < 0:
                        denominator = node.left
                if denominator is not None and any(isinstance(n, ast.Name) for n in ast.walk(denominator)):
                    restrictions.append(expression(ast.unparse(denominator)))
        if not restrictions:
            return None
        forbidden = sp.S.EmptySet
        for restriction in restrictions:
            numerator = sp.fraction(sp.cancel(restriction))[0]
            if not numerator.is_polynomial(X) or sp.degree(numerator, X) > 2:
                return None
            forbidden = forbidden.union(sp.solveset(numerator, X, domain=sp.S.Reals))
        residual = sp.cancel(values[0]-values[1])
        numerator = sp.fraction(residual)[0]
        if not numerator.is_polynomial(X) or sp.degree(numerator, X) > 2:
            return None
        candidates = sp.solveset(numerator, X, domain=sp.S.Reals)
        domain = sp.S.Reals - forbidden
        answer = candidates.intersect(domain)
        if isinstance(answer, sp.ConditionSet):
            return None
        if isinstance(answer, sp.FiniteSet) and any(sp.simplify(residual.subs(X, root)) != 0 for root in answer):
            return None
    except (ValueError, SyntaxError, TypeError, NotImplementedError, sp.PolynomialError):
        return None
    excluded = candidates.intersect(forbidden)
    latex = sp.latex
    steps = [
        step('记录原式定义域', '先保留原式每个分母非零的条件，包括约分后可能消失的分母；本题在实数范围内求解。',
             r'x\in '+latex(domain), hint='必须在约分和去分母之前记录禁值。'),
        step('在定义域内通分整理', '把右侧移到左侧并通分。在原定义域内，分式为零等价于分子为零。',
             latex(numerator)+'=0', hint='这里的等价变形只在上一步的定义域内成立。'),
        step('求候选解', '解整理后的方程；恒等式的候选解为全体实数，矛盾式没有候选解。', r'x\in '+latex(candidates)),
        step('排除禁值并代回验证', ('排除原分母为零的候选值 $'+latex(excluded)+'$。' if excluded != sp.S.EmptySet else '候选解与原式定义域取交集。')+
             ('定义域内原式恒成立。' if numerator == 0 else '留下的每个实根均满足原方程；空集表示无实数解。'), r'x\in '+latex(answer))]
    return Solution(title='分式方程与定义域', summary='实数解集为 $'+latex(answer)+'$。', steps=steps, source='sympy',
        verification='已保留原始分母限制，精确求解至多二次的分子方程并排除禁值；有限个解已代回验证。')
