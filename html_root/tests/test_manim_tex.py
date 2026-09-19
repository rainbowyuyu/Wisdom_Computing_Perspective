import json
from pathlib import Path

import pytest
from manim import MathTex, tempconfig

from logic import manim_tex
from app.routers.solve import tex_failure_message


@pytest.mark.parametrize('source', [
    r'm>4\quad\text{且}\quad m<6',
    r'\begin{cases}x^2,&\text{当 }x\ge0\\-x,&\text{当 }x<0\end{cases}',
    r'\begin{bmatrix}1&2\\3&4\end{bmatrix}',
    r'\norm{\bm{x}}=\sqrt{x^2+y^2}',
    r'\abs{-2}=2,\quad\mathscr{F},\quad\cancel{x}',
    r'P=\frac{\binom{3}{1}\binom{2}{1}}{\binom{5}{2}}=60%',
    r'\begin{align*}x&=1\\y&=2\end{align*}',
    r'x&=1\\y&=2',
    r'\limsup_{n\to\infty}a_n\leqslant\sup_{n\in\N}a_n',
    r'x∈\R,\quad x²≥0,\quad\theta=90\degree',
    '+'.join(['x']*230),  # Previously rejected solely because it exceeded 450 characters.
])
def test_real_mathtex_compilation(source,tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    with tempconfig({'media_dir':str(tmp_path)}):
        item=manim_tex.formula(source)
        assert isinstance(item,MathTex)
        assert 0<item.width<=12.01 and 0<item.height<=1.41
        assert list(tmp_path.rglob('*.svg'))


@pytest.mark.parametrize('source', [
    r'\input{secret}',r'\include{secret}',r'\write18{anything}',r'\csname input\endcsname',
    r'\special{anything}',r'\newcommand{\evil}{x}',r'\def\evil{x}',r'\usepackage{shellesc}',
    r'^^5cinput{secret}',r'\frac{1}{',r'\begin{cases}x\end{matrix}',
    r'\quadx',r'\begin{document}x\end{document}',
])
def test_invalid_or_executable_tex_is_rejected_before_compilation(source):
    with pytest.raises(manim_tex.LatexRenderError):manim_tex.normalize_tex(source)


def test_environment_error_identifies_step_without_raw_traceback(tmp_path,monkeypatch):
    monkeypatch.setenv('WISDOM_TEX_ERROR',str(tmp_path/'tex-error.json'))
    manim_tex.set_tex_step(3)
    with pytest.raises(manim_tex.LatexRenderError):manim_tex.normalize_tex(r'\frac{1}{')
    diagnostic=json.loads((tmp_path/'tex-error.json').read_text(encoding='utf-8'))
    assert diagnostic['code']=='syntax' and diagnostic['step']==4
    message=tex_failure_message(tmp_path,'a private traceback')
    assert message.startswith('第 4 步：') and '括号' in message
    assert 'traceback' not in message


def test_missing_compiler_is_reported_as_environment_not_formula(monkeypatch):
    manim_tex.tex_template.cache_clear()
    monkeypatch.setattr(manim_tex.shutil,'which',lambda _:None)
    try:
        with pytest.raises(manim_tex.LatexRenderError,match='缺少 xelatex') as error:
            manim_tex.tex_template(True)
        assert error.value.code=='compiler'
    finally:manim_tex.tex_template.cache_clear()
