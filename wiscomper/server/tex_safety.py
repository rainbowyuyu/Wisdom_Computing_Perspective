"""Small mathematical TeX language, not a general TeX document interface."""
import re

COMMANDS = set('''frac dfrac tfrac sqrt left right middle lvert rvert lVert rVert
sum prod int iint iiint oint lim limits nolimits sin cos tan cot sec csc
arcsin arccos arctan sinh cosh tanh log ln exp min max det gcd sup inf
alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa
lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega
Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega
cdot times div pm mp le leq ge geq ne neq approx sim simeq equiv propto
in notin subset supset subseteq supseteq cup cap emptyset infinity infty
to mapsto rightarrow leftarrow leftrightarrow Rightarrow Leftarrow Leftrightarrow
implies iff partial nabla forall exists neg land lor angle perp parallel
vec overrightarrow overline underline hat widehat bar dot ddot tilde widetilde
text textrm textbf mathrm mathbf mathit mathbb mathcal mathsf operatorname
quad qquad thinspace ldots cdots vdots ddots ell degree circ prime
binom dbinom tbinom begin end cases aligned matrix pmatrix bmatrix vmatrix
big Big bigg Bigg bigl bigr Bigl Bigr biggl biggr Biggl Biggr
Re Im top bot lfloor rfloor lceil rceil langle rangle backslash space
underbrace overbrace substack displaystyle textstyle scriptstyle
mod bmod pmod'''.split())
ENVIRONMENTS = {'aligned','matrix','pmatrix','bmatrix','vmatrix','Vmatrix','cases','smallmatrix'}


def validate_tex(value: str) -> str:
    if not value or len(value) > 400:
        raise ValueError('Manim 公式不能为空，且最多 400 个字符。')
    # Reject TeX lexical rewrites, comments, parameters and non-math document text.
    if any(ord(c) > 127 or ord(c) < 32 and c not in '\n\t' for c in value) or any(c in value for c in ('%', '#', '`', '\x00', '^^')):
        raise ValueError('Manim 公式请使用标准数学 LaTeX，中文说明请放在文字图层。')
    tokens = re.findall(r'\\([A-Za-z]+|.)', value)
    if len(tokens) > 120 or any(t not in COMMANDS and t not in ',;:! {}_\\|$' for t in tokens):
        raise ValueError('公式包含不支持的 LaTeX 指令；请使用标准数学表达式。')
    braces = re.sub(r'\\[{}]', '', value)
    depth = 0
    for c in braces:
        depth += (c == '{') - (c == '}')
        if depth < 0 or depth > 16:
            raise ValueError('公式括号层数或配对不正确。')
    if depth:
        raise ValueError('公式括号未配对。')
    stack = []
    for match in re.finditer(r'\\(begin|end)\s*\{([^{}]*)\}', value):
        action, name = match.groups()
        if name not in ENVIRONMENTS:
            raise ValueError('Manim 仅支持数学矩阵、分段和对齐环境。')
        if action == 'begin':
            stack.append(name)
        elif not stack or stack.pop() != name:
            raise ValueError('公式环境未配对。')
    if stack:
        raise ValueError('公式环境未结束。')
    return value
