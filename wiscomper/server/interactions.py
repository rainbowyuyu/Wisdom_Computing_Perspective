"""Bounded exploration state and deterministic snapshots; no generated code."""
from __future__ import annotations

import copy
import math

from .schema import Scene, InteractionStateRequest


LIMITS={key:(-10000.,10000.) for key in ('x','y','z','rotation','rotation_x','rotation_y')}
LIMITS.update(scale=(.01,20.),opacity=(0.,1.),draw=(0.,1.))


def clip(prop,value):
    low,high=LIMITS[prop]
    return min(high,max(low,value))


def add_recipe_interactions(scene:Scene,recipe:str)->Scene:
    """Known old recipes can gain freedoms without rewriting their saved geometry."""
    if scene.interactions or scene.mode!='3d' or scene.evidence=='computed':return scene
    nodes={o.id:o for o in scene.objects}
    interactions=[]
    if recipe=='fan' and {'rotor','front-guard','rear-guard','guard-shell'}<=nodes.keys():
        interactions=[
            dict(id='rotor-angle',label='手动转动叶轮',value=0,min=-180,max=180,step=1,unit='°',
                 description='暂停后拖动叶轮，或移动滑块，观察叶片姿态。播放时保留这次角度调整。',
                 bindings=[dict(target_id='rotor',property='rotation',multiplier=math.pi/180)],
                 drag=dict(target_id='rotor',axis='horizontal',sensitivity=.7)),
            dict(id='guards-visible',label='显示护罩',kind='toggle',value=1,min=0,max=1,step=1,
                 description='暂时隐藏护罩，便于观察叶片与电机之间的关系。',
                 bindings=[dict(target_id=ident,property='opacity',multiplier=1) for ident in ('front-guard','rear-guard','guard-shell')]),
        ]
    elif recipe=='model3d' and 'rotor' in nodes:
        interactions=[dict(id='rotor-angle',label='转子观察角',value=0,min=-180,max=180,step=1,unit='°',
            description='沿电机转轴手动转动转子，观察装配位置；不计算电磁力。',
            bindings=[dict(target_id='rotor',property='rotation_y',multiplier=math.pi/180)],
            drag=dict(target_id='rotor',axis='horizontal',sensitivity=.7))]
    if not interactions:return scene
    data=scene.model_dump();data['interactions']=interactions
    return Scene.model_validate(data)


def validate_exploration(scene:Scene,state:dict|InteractionStateRequest|None,*,strict=True)->dict:
    incoming=state if isinstance(state,InteractionStateRequest) else InteractionStateRequest.model_validate(state or {})
    controls={c.id:c for c in scene.interactions}
    if strict and set(incoming.values)-controls.keys():raise ValueError('交互参数不属于当前场景。')
    values={c.id:c.value for c in scene.interactions}
    for ident,value in incoming.values.items():
        control=controls.get(ident)
        if control is None:continue
        valid=control.min<=value<=control.max and (control.kind!='toggle' or value in (0,1))
        if not valid and strict:raise ValueError('交互参数超出当前场景允许的范围。')
        if valid:values[ident]=value
    if incoming.camera and scene.mode!='3d':
        if strict:raise ValueError('二维场景不支持三维观察视角。')
        camera=None
    else:camera=incoming.camera.model_dump() if incoming.camera else None
    return {'values':values,'camera':camera}


def prepare_project(project:dict)->dict:
    result=copy.deepcopy(project)
    scene=Scene.model_validate(result['scene'])
    scene=add_recipe_interactions(scene,result.get('proposal',{}).get('recipe',''))
    result['scene']=scene.model_dump()
    result['exploration']=validate_exploration(scene,result.get('exploration'),strict=False)
    return result


def bake_scene(scene:Scene|dict,exploration:dict|None)->Scene:
    """Bake offsets at all clipping crossings, preserving interpolation exactly.

    Clipping only existing frame endpoints would change intermediate frames.
    Add each crossing at which an affine track reaches the property bounds.
    """
    scene=scene if isinstance(scene,Scene) else Scene.model_validate(scene)
    state=validate_exploration(scene,exploration)
    data=scene.model_dump();deltas={}
    for interaction in scene.interactions:
        delta=state['values'][interaction.id]-interaction.value
        for binding in interaction.bindings:
            target=deltas.setdefault(binding.target_id,{})
            target[binding.property]=target.get(binding.property,0)+delta*binding.multiplier
    for obj in data['objects']:
        offsets={k:v for k,v in deltas.get(obj['id'],{}).items() if abs(v)>1e-12}
        if not offsets:continue
        tracks=[];current={prop:obj[prop] for prop in LIMITS}
        for frame in obj['frames']:
            current={**current,**{k:v for k,v in frame.items() if k in LIMITS and v is not None}}
            tracks.append({'t':frame['t'],**current})
        output=[]
        for i,frame in enumerate(tracks):
            output.append(dict(frame))
            if i+1==len(tracks):continue
            nxt=tracks[i+1];times=set()
            for prop,delta in offsets.items():
                a,b=frame[prop]+delta,nxt[prop]+delta
                if abs(b-a)<1e-12:continue
                for limit in LIMITS[prop]:
                    u=(limit-a)/(b-a)
                    if 1e-10<u<1-1e-10:times.add(frame['t']+u*(nxt['t']-frame['t']))
            for t in sorted(times):
                u=(t-frame['t'])/(nxt['t']-frame['t'])
                output.append({'t':t,**{prop:frame[prop]+(nxt[prop]-frame[prop])*u for prop in LIMITS}})
        for prop,delta in offsets.items():obj[prop]=clip(prop,obj[prop]+delta)
        for frame in output:
            for prop,delta in offsets.items():frame[prop]=clip(prop,frame[prop]+delta)
        obj['frames']=output
    # A baked snapshot is an exported state, so its controls are intentionally
    # removed: replay must not apply the saved offsets a second time. The source
    # project's scene and reset defaults remain unchanged in storage.
    data['interactions']=[]
    if state['camera']:data['camera']=state['camera']
    try:return Scene.model_validate(data)
    except ValueError as exc:raise ValueError('当前交互导出超过场景限制，请缩小变化范围后重试。') from exc
