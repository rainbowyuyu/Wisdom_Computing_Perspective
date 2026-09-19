"""Shared, bounded MathTex rendering with a portable Chinese TeX template."""
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil

from manim import MathTex, TexTemplate, VGroup, config


CJK = re.compile(r'[\u3400-\u9fff\uf900-\ufaff]')
ALLOWED = set('''
frac dfrac tfrac cfrac binom dbinom tbinom sqrt sin cos tan cot sec csc arcsin arccos arctan
sinh cosh tanh coth log ln exp lim limsup liminf min max sup inf arg gcd deg dim ker hom det
to infty pi theta alpha beta gamma Gamma Delta delta epsilon varepsilon zeta eta Theta
lambda Lambda mu nu xi Xi rho varrho sigma Sigma varsigma tau upsilon Upsilon phi varphi Phi
chi psi Psi omega Omega ell hbar Re Im nabla prime partial emptyset varnothing
left right middle begin end cdot cdotp times div pm mp ast star circ bullet bigcirc
quad qquad enspace thinspace medspace thickspace text textnormal textrm textsf texttt textbf textit
mathrm mathbf mathbb mathcal mathscr mathfrak mathsf mathtt mathit mathnormal boldsymbol bm
operatorname vec hat widehat bar overline underline tilde widetilde dot ddot overrightarrow overleftarrow
sum prod coprod int iint iiint oint bigcup bigcap bigvee bigwedge
le ge leq geq leqslant geqslant ne neq approx equiv sim simeq cong propto ll gg lesssim gtrsim
in notin ni subset subseteq subsetneq supset supseteq supsetneq cup cap setminus smallsetminus
forall exists nexists neg land lor wedge vee angle measuredangle triangle perp parallel nparallel
degree rightarrow leftarrow leftrightarrow Rightarrow Leftarrow Leftrightarrow
longrightarrow longleftarrow longleftrightarrow Longrightarrow Longleftarrow Longleftrightarrow
implies iff mapsto because therefore cdots ldots vdots ddots dots
underbrace overbrace overset underset stackrel substack displaystyle textstyle scriptstyle scriptscriptstyle
limits nolimits lvert rvert vert lVert rVert Vert langle rangle lbrace rbrace lceil rceil lfloor rfloor
big Big bigg Bigg bigl bigr Bigl Bigr biggl biggr Biggl Biggr
boxed fbox phantom hphantom vphantom smash mathstrut substack not bmod pmod mod
abs norm set bra ket braket cancel bcancel xcancel
'''.split())
ENVIRONMENTS = {'matrix','pmatrix','bmatrix','Bmatrix','vmatrix','Vmatrix','smallmatrix',
                'array','aligned','alignedat','gathered','cases','dcases'}
SYMBOLS = {
    '−':'-', '×':r'\times ', '÷':r'\div ', '·':r'\cdot ', '≤':r'\le ', '≥':r'\ge ',
    '≠':r'\ne ', '≈':r'\approx ', '∞':r'\infty ', 'π':r'\pi ', 'θ':r'\theta ',
    'Δ':r'\Delta ', '∈':r'\in ', '∉':r'\notin ', '∩':r'\cap ', '∪':r'\cup ',
    '∅':r'\emptyset ', '±':r'\pm ', '∓':r'\mp ', '⇒':r'\Rightarrow ', '⇔':r'\Leftrightarrow ',
    '→':r'\to ', '∂':r'\partial ', '∇':r'\nabla ', '²':'^{2}', '³':'^{3}',
    '（':'(', '）':')', '，':',', '：':':', '\u00a0':' ',
}
_step = None


def set_tex_step(index):
    global _step
    _step = index + 1


class LatexRenderError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__('WISDOM_LATEX_ERROR: '+message)
        target = os.getenv('WISDOM_TEX_ERROR')
        if target:
            Path(target).write_text(json.dumps({'code':code,'step':_step,'message':message},ensure_ascii=False),encoding='utf-8')


ALLOWED.update({'mid', 'nmid', 'parallel', 'perp'})


def normalize_tex(text):
    text = str(text).strip()
    for left,right in [('$$','$$'),(r'\[',r'\]'),(r'\(',r'\)'),('$','$')]:
        if text.startswith(left) and text.endswith(right) and len(text)>=len(left)+len(right):
            text=text[len(left):-len(right)].strip();break
    if len(text)>1600:
        raise LatexRenderError('length','单个公式过长，请拆成多个解题步骤。')
    for source,target in SYMBOLS.items(): text=text.replace(source,target)
    # KaTeX and conventional mathematical shorthand, expanded only to fixed macros.
    text=re.sub(r'\\(?:R|RR)(?![A-Za-z])',lambda _:r'\mathbb{R}',text)
    text=re.sub(r'\\(?:N|NN)(?![A-Za-z])',lambda _:r'\mathbb{N}',text)
    text=re.sub(r'\\(?:Z|ZZ)(?![A-Za-z])',lambda _:r'\mathbb{Z}',text)
    text=re.sub(r'\\(?:rank|tr)(?![A-Za-z])',lambda m:r'\operatorname{'+m[0][1:]+'}',text)
    text=re.sub(r'(?<!\\)%',r'\\%',text)
    for name in ('equation','equation*','displaymath'):
        left,right=r'\begin{'+name+'}',r'\end{'+name+'}'
        if text.startswith(left) and text.endswith(right):text=text[len(left):-len(right)].strip()
    for name,replacement in [('align','aligned'),('align*','aligned'),('gather','gathered'),('gather*','gathered')]:
        text=text.replace(r'\begin{'+name+'}',r'\begin{'+replacement+'}').replace(r'\end{'+name+'}',r'\end{'+replacement+'}')
    if '^^' in text or re.search(r'(?<!\\)[#$]',text) or any(ord(ch)<32 and ch not in '\n\r\t' for ch in text):
        raise LatexRenderError('syntax','公式含无效字符，请检查数学表达式。')
    depth=0
    for token in re.findall(r'\\(?:[A-Za-z]+|[\s\S])|[{}]',text):
        if token=='{':depth+=1
        elif token=='}':depth-=1
        elif token.startswith('\\'):
            command=token[1:]
            if command not in ALLOWED and command not in {'\\',' ', '\n', ',', ';', ':', '!', '|','{','}','_','#','%','$','&'}:
                raise LatexRenderError('command',f'暂不支持公式命令 {token}，请改用标准数学写法。')
        if depth<0:break
    if depth!=0:raise LatexRenderError('syntax','公式括号不完整，请检查左右花括号。')
    stack=[]
    for token,name in re.findall(r'\\(begin|end)\{([^}]+)\}',text):
        if name not in ENVIRONMENTS:
            raise LatexRenderError('environment',f'暂不支持公式环境 {name}。')
        if token=='begin':stack.append(name)
        elif not stack or stack.pop()!=name:
            raise LatexRenderError('syntax','公式环境未正确配对。')
    if stack:raise LatexRenderError('syntax','公式环境未正确结束。')
    # Bare row separators/alignment marks need a math sub-environment.
    if not re.search(r'\\begin\{',text) and (r'\\' in text or re.search(r'(?<!\\)&',text)):
        text=r'\begin{aligned}'+text+r'\end{aligned}'
    return text


@lru_cache(maxsize=2)
def tex_template(chinese=False):
    engine='xelatex' if chinese or not shutil.which('latex') else 'latex'
    if not shutil.which(engine):
        raise LatexRenderError('compiler',f'缺少 {engine} 编译器，请安装对应 TeX 环境。')
    if not shutil.which('dvisvgm'):
        raise LatexRenderError('converter','缺少 dvisvgm，无法将公式转换为动画图形。')
    preamble=r'''\usepackage{amsmath,amssymb,mathtools,bm,mathrsfs,cancel}
\DeclarePairedDelimiter{\abs}{\lvert}{\rvert}
\DeclarePairedDelimiter{\norm}{\lVert}{\rVert}
\DeclarePairedDelimiter{\set}{\lbrace}{\rbrace}
\DeclarePairedDelimiter{\bra}{\langle}{\rvert}
\DeclarePairedDelimiter{\ket}{\lvert}{\rangle}
\DeclarePairedDelimiter{\braket}{\langle}{\rangle}
\newcommand{\degree}{^{\circ}}
'''
    if chinese:preamble+=r'\usepackage[UTF8,fontset=fandol]{ctex}'
    return TexTemplate(tex_compiler=engine,output_format='.xdv' if engine=='xelatex' else '.dvi',preamble=preamble)


def formula(text):
    text=normalize_tex(text)
    if not text:return VGroup()
    template=tex_template(bool(CJK.search(text)))
    config.get_dir('tex_dir').mkdir(parents=True,exist_ok=True)
    try:
        item=MathTex(text,font_size=42,tex_template=template)
    except Exception as error:
        logs=sorted(config.get_dir('tex_dir').glob('*.log'),key=lambda p:p.stat().st_mtime,reverse=True)
        detail=logs[0].read_text(encoding='utf-8',errors='replace') if logs else ''
        missing=re.search(r"File [`']([^`'\r\n]+\.sty)' not found",detail)
        if missing:raise LatexRenderError('package',f'TeX 缺少宏包 {missing[1]}，请补齐服务器数学和中文宏包。') from error
        if 'font-not-found' in detail or 'cannot be found' in detail or 'not loadable' in detail:
            raise LatexRenderError('font','中文公式字体不可用，请安装 Fandol 中文字体。') from error
        raise LatexRenderError('compile','公式未能编译，请检查该步骤的 LaTeX 语法或运行 TeX 环境自检。') from error
    if item.width>12:item.scale_to_fit_width(12)
    if item.height>1.4:item.scale_to_fit_height(1.4)
    return item
