import json
import os
from pathlib import Path
import subprocess
import pytest

from server.tex_safety import validate_tex


@pytest.mark.parametrize('formula',[r'x^2+2x+1=(x+1)^2',r'\frac{d}{dx}\sin x=\cos x',r'\begin{pmatrix}a&b\\c&d\end{pmatrix}',r'\int_0^1 x^2\,dx=\frac13'])
def test_standard_math(formula):
    assert validate_tex(formula)==formula


@pytest.mark.parametrize('formula',[r'\input{secret}',r'\write18{echo bad}',r'\csname input\endcsname',r'\def\a{\a}\a',r'\begin{document}x\end{document}',r'^^5cinput',r'\href{file:///C:/secret}{x}',r'\begin{matrix}x\end{cases}','x%comment',r'\frac{x}{y'])
def test_tex_never_exposes_document_commands(formula):
    with pytest.raises(ValueError):validate_tex(formula)


def test_manim_interpolation_preserves_hollow_shapes():
    pytest.importorskip('manim')
    from server.schema import VisualObject
    from server.manim_scene import state_at,make_object,place
    obj=VisualObject(id='hollow',kind='circle',filled=False,frames=[{'t':1,'x':2,'opacity':.4},{'t':3,'x':6}])
    assert state_at(obj,.5)['x']==0
    assert state_at(obj,2)['x']==4
    assert state_at(obj,4)['opacity']==.4
    mob=place(make_object(obj,'.'),state_at(obj,2))
    assert mob.get_fill_opacity()==0
    assert abs(mob.get_stroke_opacity()-.4)<1e-6


def test_manim_path_reveal_preserves_length_and_arrow_bend():
    pytest.importorskip('manim')
    import numpy as np
    from server.manim_scene import geometry_at
    from server.schema import VisualObject
    path=VisualObject(id='trail',kind='path',points=[[0,0],[1,0],[10,0]])
    assert np.allclose(geometry_at(path,.5).get_end(),[5,0,0])
    arrow=VisualObject(id='turn',kind='arrow',points=[[0,0],[1,0],[1,4]])
    group=geometry_at(arrow,.6)
    assert np.allclose(group[0].get_end(),[1,2,0])
    assert np.allclose(group[0].get_start(),[0,0,0])
    cylinder=VisualObject(id='cylinder',kind='cylinder',radius=2,width=1,height=3)
    assert geometry_at(cylinder,1).width==4


def test_manim_image_keeps_aspect_ratio(tmp_path):
    pytest.importorskip('manim')
    from PIL import Image
    from server.manim_scene import make_object
    from server.schema import VisualObject
    Image.new('RGB',(100,100)).save(tmp_path/'square.png')
    mob=make_object(VisualObject(id='image',kind='image',asset_id='square',width=10,height=6),tmp_path)
    assert mob.width==pytest.approx(6)
    assert mob.height==pytest.approx(6)


def test_formula_morph_samples_intermediate_opacity(tmp_path):
    pytest.importorskip('manim')
    from manim import MathTex,tempconfig
    from server.manim_scene import TimedTexTransform
    from server.schema import VisualObject
    with tempconfig({'media_dir':str(tmp_path)}):
        obj=VisualObject(id='eq',kind='formula',latex='x',latex_next='y',y=2,frames=[{'t':2.5,'opacity':1},{'t':3,'opacity':0},{'t':3.5,'opacity':1}])
        animation=TimedTexTransform(MathTex('x'),MathTex('y'),obj,2.5)
        animation.begin();animation.interpolate(.5)
        assert all(m.get_fill_opacity()==0 for m in animation.mobject.family_members_with_points())
        animation.interpolate(.75)
        assert any(m.get_fill_opacity()>0 for m in animation.mobject.family_members_with_points())
        assert animation.mobject.get_center()[1]==pytest.approx(2,abs=.1)
        animation.finish()


def test_algebra_parts_match_as_symbols(tmp_path):
    pytest.importorskip('manim')
    from manim import tempconfig,TransformMatchingTex
    from server.manim_scene import make_object
    from server.schema import VisualObject
    with tempconfig({'media_dir':str(tmp_path)}):
        obj=VisualObject(id='eq',kind='formula',latex='(x+1)^2',latex_next='x^2+2x+1')
        for next_phase in [False,True]:
            math=make_object(obj,'.',formula_next=next_phase)
            keys={p.tex_string for p in TransformMatchingTex.get_mobject_parts(math)}
            assert {'x','1','2','+'}<=keys


@pytest.mark.skipif(os.getenv('RUN_REAL_MANIM')!='1',reason='explicit local Manim integration')
def test_real_manim_transform_and_geometry(tmp_path):
    from server.exporter import export_video
    from server.schema import Scene
    scene=Scene.model_validate({
        'title':'平方展开与运动轨迹','duration':6,'objects':[
            {'id':'equation','kind':'formula','latex':r'(x+1)^2','latex_next':r'x^2+2x+1','y':1.5,'font_size':.7},
            {'id':'particle','kind':'circle','radius':.2,'y':-1,'frames':[{'t':0,'x':-4},{'t':6,'x':4}]},
            {'id':'trail','kind':'path','points':[[-4,-1],[4,-1]],'filled':False,'frames':[{'t':0,'draw':0},{'t':6,'draw':1}]},
            {'id':'label','kind':'text','text':'同一个式子，另一种写法','y':3,'font_size':.3}
        ]
    }).model_dump()
    output=tmp_path/'manim-formula.mp4'
    export_video(scene,output,engine='manim',fps=15,timeout=180)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_streams','-show_format','-of','json',str(output)],text=True))
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    assert (video['width'],video['height'])==(1280,720)
    assert abs(float(probe['format']['duration'])-6)<.15
    assert output.stat().st_size>5000
