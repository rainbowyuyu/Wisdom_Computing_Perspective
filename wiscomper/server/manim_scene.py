"""Trusted 2D Manim backend: validated data only, no generated Python."""
import json
from bisect import bisect_right
import math
import os
import re
from pathlib import Path

import numpy as np
from manim import (Scene as ManimScene, config, Arc, Rectangle, VMobject, VGroup, Polygon,
                   Text, MathTex, ImageMobject, ValueTracker, TransformMatchingTex,
                   TexTemplate, ORIGIN, linear)
from manim.utils import tex_file_writing
from manim.mobject.text.tex_mobject import MathTexPart
from server.schema import Scene
from server.tex_safety import validate_tex

# Manim's normal compiler command omits this flag; always disable shell execution.
_compiler_command = tex_file_writing.make_tex_compilation_command
def _safe_compiler_command(*args, **kwargs):
    command = _compiler_command(*args, **kwargs)
    return [command[0], '-no-shell-escape', *command[1:]]
tex_file_writing.make_tex_compilation_command = _safe_compiler_command

FIELDS = ('x','y','z','rotation','scale','opacity','draw')

def state_at(obj, seconds):
    table = getattr(obj, '_manim_table', None)
    if table is None:
        state = {key: getattr(obj, key) for key in FIELDS}
        times, states = [], [state]
        for frame in obj.frames:
            state = {key: getattr(frame, key) if getattr(frame, key) is not None else state[key] for key in FIELDS}
            times.append(frame.t);states.append(state)
        table = (times,states)
        object.__setattr__(obj,'_manim_table',table)
    times,states = table
    index = bisect_right(times,seconds)
    if index == 0 or index == len(times):
        return states[index]
    fraction = (seconds-times[index-1])/(times[index]-times[index-1])
    return {key: states[index][key]+(states[index+1][key]-states[index][key])*fraction for key in FIELDS}


def place(mob, state):
    mob.scale(state['scale'], about_point=ORIGIN)
    mob.rotate(state['rotation'], about_point=ORIGIN)
    mob.shift([state['x'],state['y'],state['z']])
    # Preserve stroke-only paths and empty shapes while scaling their alpha.
    mob.fade(1-state['opacity'])
    return mob


def partial_points(points, fraction):
    points=np.array([[*p,0][:3] for p in points],dtype=float)
    if fraction>=1:return points
    lengths=np.linalg.norm(np.diff(points,axis=0),axis=1)
    remaining=float(sum(lengths))*max(0,fraction)
    output=[points[0]]
    for index,length in enumerate(lengths):
        if remaining>=length:
            output.append(points[index+1]);remaining-=length
        else:
            output.append(points[index]+(points[index+1]-points[index])*(remaining/length if length else 0));break
    return np.array(output)


def geometry_at(obj, fraction):
    """Match Canvas path-distance reveal, image-free fixed geometry only."""
    kind=obj.kind
    if kind in {'circle','sphere'}:
        result=Arc(radius=obj.radius,start_angle=0,angle=2*math.pi*max(.000001,fraction))
        result.set_fill(obj.color,opacity=1 if obj.filled and fraction>0 else 0)
        result.set_stroke(obj.stroke,width=obj.line_width*60,opacity=1 if fraction>0 else 0)
        return result
    if kind in {'rect','box','cylinder'}:
        width=obj.radius*2 if kind=='cylinder' else obj.width
        points=[[-width/2,obj.height/2],[width/2,obj.height/2],[width/2,-obj.height/2],[-width/2,-obj.height/2],[-width/2,obj.height/2]]
        fill=Rectangle(width=width,height=obj.height,stroke_width=0,fill_color=obj.color,fill_opacity=1 if obj.filled else 0)
        stroke=VMobject(stroke_color=obj.stroke,stroke_width=obj.line_width*60)
        stroke.set_points_as_corners(partial_points(points,fraction))
        if fraction<=0:stroke.set_opacity(0)
        return VGroup(fill,stroke)
    points=partial_points(obj.points,fraction)
    line=VMobject(stroke_color=obj.stroke,stroke_width=obj.line_width*60)
    line.set_points_as_corners(points)
    if fraction<=0:line.set_opacity(0)
    if kind!='arrow':return line
    delta=points[-1]-points[-2]
    angle=math.atan2(delta[1],delta[0]);head=max(.13,obj.line_width*4)
    tip=Polygon(points[-1],points[-1]-head*np.array([math.cos(angle-.45),math.sin(angle-.45),0]),
                points[-1]-head*np.array([math.cos(angle+.45),math.sin(angle+.45),0]),
                stroke_width=0,fill_color=obj.stroke,fill_opacity=1 if fraction>0 else 0)
    return VGroup(line,tip)


def make_object(obj, asset_root, *, formula_next=False):
    kind = obj.kind
    if kind == 'formula':
        latex = validate_tex(obj.latex_next if formula_next else obj.latex)
        template = TexTemplate(documentclass=r'\documentclass[preview]{standalone}',
                               preamble=r'\usepackage{amsmath}\usepackage{amssymb}',
                               tex_compiler='latex', output_format='.dvi')
        # Isolate ordinary algebra symbols so matching x, signs and coefficients
        # travel as glyphs. Do not split through structured TeX commands.
        combined=obj.latex+obj.latex_next
        tokens=sorted(set(re.findall(r'[A-Za-z]|[0-9]+|[+=()\-]',combined))) if '\\' not in combined else []
        if tokens:
            latex=re.sub(r'([_^])([A-Za-z0-9])',r'\1{\2}',latex)
        result = MathTex(latex, color=obj.color, font_size=obj.font_size*72, tex_template=template,substrings_to_isolate=tokens)
        if tokens:
            # 0.22 records isolated substrings in an SVG lookup while retaining
            # one main MathTexPart. Promote those groups for matching animation.
            parts=[];used=set()
            original=result.family_members_with_points()
            for text,match_id in result._substring_matches:
                group=result.id_to_vgroup_dict.get(match_id)
                if group is None:continue
                glyphs=group.family_members_with_points()
                glyphs=[g for g in glyphs if id(g) not in used]
                if not glyphs:continue
                part=MathTexPart();part.tex_string=text;part.add(*glyphs)
                parts.append(part);used.update(id(g) for g in glyphs)
            remaining=[g for g in original if id(g) not in used]
            if remaining:
                part=MathTexPart();part.tex_string='remainder:'+latex;part.add(*remaining);parts.append(part)
            if parts:result.submobjects=parts
        if result.width > 14:
            result.scale(14/result.width)
        return result.move_to(ORIGIN)
    if kind == 'text':
        result = Text(obj.text, color=obj.color, font='Microsoft YaHei' if os.name=='nt' else 'Noto Sans CJK SC',
                    font_size=obj.font_size*60, disable_ligatures=True).move_to(ORIGIN)
        if result.width > 14: result.scale(14/result.width)
        return result
    if kind == 'image':
        root = Path(asset_root).resolve()
        path = (root/f'{obj.asset_id}.png').resolve()
        if path.parent != root or not path.is_file():
            raise ValueError('Image asset unavailable')
        result = ImageMobject(str(path))
        result.scale(min(obj.width/result.width,obj.height/result.height))
        return result
    return geometry_at(obj,1)


class TimedTexTransform(TransformMatchingTex):
    """Glyph matching in local coordinates, with the same absolute pose track."""
    def __init__(self,source,target,obj,start_time):
        self.visual_object=obj
        self.start_time=start_time
        super().__init__(source,target,transform_mismatches=True,rate_func=linear)

    def interpolate(self,alpha):
        # Re-sample all child transforms even at repeated endpoints: do not
        # accumulate prior placement, nor skip an opacity keyframe mid-morph.
        for animation in self.animations:
            animation.interpolate(alpha)
        place(self.mobject,state_at(self.visual_object,self.start_time+alpha))

    def clean_up_from_scene(self,scene):
        super().clean_up_from_scene(scene)
        place(self.to_add,state_at(self.visual_object,self.start_time+1))


class DSHScene(ManimScene):
    def construct(self):
        source = Path(os.environ['DSH_SCENE_PATH'])
        if source.stat().st_size > 8_000_000:
            raise ValueError('Scene too large')
        scene = Scene.model_validate(json.loads(source.read_text(encoding='utf-8')))
        if scene.mode != '2d':
            raise ValueError('Use browser export for a 3D scene')
        config.frame_width = 16
        config.frame_height = 9
        self.camera.frame_width = 16
        self.camera.frame_height = 9
        self.camera.background_color = scene.background
        clock = ValueTracker(0)
        formulas = []
        for obj in scene.objects:
            base = make_object(obj,os.environ['DSH_ASSET_ROOT'])
            mob = base.copy()
            if obj.kind == 'formula' and obj.latex_next:
                formulas.append((obj,mob,base))
                place(mob,state_at(obj,0))
            else:
                def update(target, dt=0, obj=obj, base=base):
                    state = state_at(obj,clock.get_value())
                    target.become(geometry_at(obj,state['draw']) if state['draw']!=1 and obj.kind not in {'text','formula','image'} else base)
                    place(target,state)
                mob.add_updater(update);update(mob)
            self.add(mob)
        self.add(clock)
        if not formulas:
            self.play(clock.animate.set_value(scene.duration),run_time=scene.duration,rate_func=linear)
            return
        # Matching glyphs travel between expressions, rather than stacking captions.
        before = scene.duration/2-.5
        for obj,mob,base in formulas:
            # Formula motion is sampled in each stable half; morph happens at midpoint.
            def formula_update(target, dt=0, obj=obj, base=base):
                target.become(base)
                place(target,state_at(obj,clock.get_value()))
            mob.add_updater(formula_update)
        self.play(clock.animate.set_value(before),run_time=before,rate_func=linear)
        transforms=[];after_mobs=[]
        for obj,mob,base in formulas:
            mob.clear_updaters()
            mob.become(base)
            next_base = make_object(obj,os.environ['DSH_ASSET_ROOT'],formula_next=True)
            target=next_base.copy()
            transforms.append(TimedTexTransform(mob,target,obj,before))
            after_mobs.append((obj,target,next_base))
        self.play(clock.animate.set_value(before+1),*transforms,run_time=1,rate_func=linear)
        for obj,mob,base in after_mobs:
            def update_formula(target,dt=0,obj=obj,base=base):
                target.become(base);place(target,state_at(obj,clock.get_value()))
            mob.add_updater(update_formula)
        self.play(clock.animate.set_value(scene.duration),run_time=before,rate_func=linear)
