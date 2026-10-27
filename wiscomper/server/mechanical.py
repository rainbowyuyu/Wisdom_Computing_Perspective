"""Original procedural teaching mechanisms. No external model or media assets."""
from __future__ import annotations

import math

from .schema import Proposal, Scene


def build_fan(proposal: Proposal | dict) -> Scene:
    """A pitched axial fan with a true rotating assembly and fixed cage/stand.

    Blade sections are extruded polygons. Flow is an explicitly qualitative
    illustration; speed is a slow presentation rate, not a measured motor RPM.
    """
    p = proposal if isinstance(proposal, Proposal) else Proposal.model_validate(proposal)
    allowed = {'speed': (.1, 1.), 'pitch': (0., 40.), 'explode': (0., 2.5)}
    values = {'speed': .5, 'pitch': 20., 'explode': 0., **p.parameters}
    if set(p.parameters) - set(allowed):
        raise ValueError('风机模型仅支持 speed、pitch 和 explode 参数。')
    for key, value in values.items():
        lo, hi = allowed[key]
        if not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f'风机参数 {key} 应在 {lo:g} 至 {hi:g} 之间。')
    duration, speed, pitch, explode = p.duration, values['speed'], values['pitch'], values['explode']
    white, mint, steel, blue, gold = '#e7eff3', '#7de4c1', '#8192a0', '#9bbbd2', '#f0c57a'
    objects: list[dict] = []

    def add(ident, kind, **fields):
        item = {'id': ident, 'kind': kind, 'color': mint, 'stroke': mint, **fields}
        # Endpoints remain exact for arbitrary valid noninteger duration.
        for frame in item.get('frames', []):
            frame['t'] = min(duration, max(0, float(frame['t'])))
        objects.append(item)
        return item

    def frame(t, **fields):
        return {'t': min(duration, round(t, 6)), **fields}

    def staged_position(initial, assembled):
        return [frame(0, z=initial), frame(duration * .23, z=assembled), frame(duration, z=assembled)]

    def fade(start, end, peak=1.):
        ramp = min(.55, (end - start) / 4)
        return [frame(start, opacity=0), frame(start + ramp, opacity=peak), frame(end - ramp, opacity=peak), frame(end, opacity=0)]

    add('fan', 'group', label='轴流风机总成', y=.25)
    add('stationary', 'group', parent_id='fan', label='固定机架与外圈')
    # Thick rear ring and front ring make the guard volume readable.
    add('rear-guard', 'group', parent_id='stationary', label='后护罩', z=-.56-explode*.6,
        frames=staged_position(-1.38-explode*.6, -.56-explode*.6))
    add('front-guard', 'group', parent_id='stationary', label='前护罩', z=.62+explode*.85,
        frames=staged_position(1.5+explode*.85, .62+explode*.85))
    for side, colour in [('rear', steel), ('front', blue)]:
        parent = f'{side}-guard'
        add(f'{side}-rim', 'torus', parent_id=parent, label='实体护罩外圈', radius=2.52, tube_radius=.085, color=colour)
        add(f'{side}-inner-rim', 'torus', parent_id=parent, radius=2.39, tube_radius=.027, color=colour, opacity=.75)
        # Sparse solid bars, not a wireframe substitution for the whole model.
        for i in range(8):
            a=i*math.tau/8
            add(f'{side}-guard-rib-{i}', 'cylinder', parent_id=parent, radius=.019, height=2.02,
                x=1.46*math.cos(a), y=1.46*math.sin(a), rotation=a-math.pi/2, color=colour, opacity=.58)
        for i,radius in enumerate([1.06,1.70]):
            add(f'{side}-guard-ring-{i}', 'torus', parent_id=parent, radius=radius, tube_radius=.019, color=colour, opacity=.5)
    # A translucent middle shell reinforces depth but leaves blade geometry legible.
    add('guard-shell', 'cylinder', parent_id='stationary', radius=2.50, height=1.18,
        rotation_x=math.pi/2, color='#6d8ea1', opacity=.055, label='透明示意护筒')
    for i,a in enumerate([math.pi*.25,math.pi*.75,math.pi*1.25,math.pi*1.75]):
        add(f'rim-spacer-{i}', 'cylinder', parent_id='stationary', x=2.5*math.cos(a),y=2.5*math.sin(a),
            radius=.035,height=1.2,rotation_x=math.pi/2,color=steel)
    # The motor housing and mounting bracket never inherit rotor rotation.
    add('motor', 'group', parent_id='stationary', label='固定电机外壳', z=-.98-explode*.6,
        frames=staged_position(-1.9-explode*.6,-.98-explode*.6))
    add('motor-body','cylinder',parent_id='motor',radius=.61,height=.86,rotation_x=math.pi/2,color='#293b4a')
    add('motor-rear-cap','sphere',parent_id='motor',radius=.48,z=-.42,scale=1,color='#354d5e')
    for i,z in enumerate([-.3,-.12,.06,.24]):
        add(f'motor-cooling-ring-{i}','torus',parent_id='motor',radius=.62,tube_radius=.025,z=z,color=steel)
    add('fixed-shaft','cylinder',parent_id='stationary',radius=.115,height=1.55+explode*.6,z=-.52-explode*.3,rotation_x=math.pi/2,color=gold)
    add('mounting-neck','box',parent_id='stationary',width=.42,height=1.6,depth=.42,y=-1.35,z=-1.2,color='#304b5b')
    add('mounting-collar','cylinder',parent_id='stationary',radius=.34,height=.45,y=-.55,z=-1.2,color=steel)
    add('stand-stem','cylinder',parent_id='stationary',radius=.18,height=1.25,y=-2.25,z=-1.2,color=steel)
    add('stand-base','box',parent_id='stationary',width=2.5,height=.20,depth=1.5,y=-2.95,z=-1.0,color='#253e4d')
    add('stand-foot-left','box',parent_id='stationary',width=.45,height=.08,depth=1.15,x=-.9,y=-3.09,z=-1,color='#14232d')
    add('stand-foot-right','box',parent_id='stationary',width=.45,height=.08,depth=1.15,x=.9,y=-3.09,z=-1,color='#14232d')

    start, ramp = duration*.24, min(.8,duration*.12)
    count=math.ceil(duration*20)
    angles=[]
    for i in range(count+1):
        t=duration*i/count;elapsed=max(0.,t-start)
        turns=speed*(elapsed*elapsed/(2*ramp) if elapsed<ramp else elapsed-ramp/2)
        angles.append(frame(t,rotation=math.tau*turns))
    add('rotor','group',parent_id='fan',label='旋转总成 · 轮毂与叶片',frames=angles)
    add('hub','cylinder',parent_id='rotor',radius=.48,height=.46,rotation_x=math.pi/2,z=.06,color=white,label='轮毂')
    add('hub-nose','cone',parent_id='rotor',radius=.45,height=.45,rotation_x=math.pi/2,z=.5,color=white)
    add('hub-badge','circle',parent_id='rotor',radius=.18,z=.735,color=gold,stroke=gold)
    # Swept planform. Blade-local X is radial; pitch rotates its chord about X.
    profile=[[.37,-.12],[.78,-.35],[1.42,-.47],[1.96,-.36],[2.23,-.10],
             [2.24,.12],[2.07,.31],[1.57,.39],[.95,.26],[.48,.11]]
    for i in range(5):
        add(f'blade-root-{i}','group',parent_id='rotor',rotation=i*math.tau/5,label=f'叶片 {i+1} 安装座')
        add(f'blade-{i}','prism',parent_id=f'blade-root-{i}',points=profile,depth=.105,
            rotation_x=math.radians(pitch),color=mint if i else '#a1f1d3',label=f'实体叶片 {i+1} · 安装角 {pitch:g}°')
        add(f'blade-fastener-{i}','cylinder',parent_id=f'blade-root-{i}',radius=.065,height=.09,x=.53,z=.12,rotation_x=math.pi/2,color=gold)

    # Qualitative axial transport. Pitch=0 removes the presented axial component.
    flow_strength=math.sin(math.radians(pitch))/math.sin(math.radians(40))
    flow_start=duration*.57
    add('airflow','group',parent_id='fan',label='轴向气流 · 教学示意',opacity=0,
        frames=[frame(0,opacity=0),frame(flow_start,opacity=0),frame(flow_start+.45,opacity=.75*flow_strength),frame(duration,opacity=.75*flow_strength)])
    transport_speed=(.6+speed*1.8)*max(flow_strength,.05)
    for i in range(6):
        angle=i*math.tau/6+math.pi/6;radius=1.30
        x,y=radius*math.cos(angle),radius*math.sin(angle)
        add(f'air-stream-{i}','arrow',parent_id='airflow',points=[[x,y,-3.0],[x,y,3.1]],stroke='#7ac7e6',line_width=.018,opacity=.65,label='轴向流动方向')
        for j in range(2):
            # Invisible end states remove any visible jump during particle recycling.
            initial=(i*.17+j*.49)%1;period=6.0/transport_speed
            keys=[]
            boundaries={0.,duration}
            cycle_min=math.floor(initial)-1;cycle_max=math.ceil(duration/period+initial)+1
            for cycle in range(cycle_min,cycle_max+1):
                for phase in [0.,.025,.10,.90,.975,1.]:
                    t=(cycle+phase-initial)*period
                    if 0<t<duration:boundaries.add(t)
            # Use piecewise segments at resets: phase1 and phase0 separated by a hidden tiny interval.
            for t in sorted(boundaries):
                phase=(t/period+initial)%1
                if phase<1e-9 or phase>1-1e-9:phase=0.
                opacity=min(1.,phase/.10,(1-phase)/.10)
                keys.append(frame(t,z=-3+6*phase,opacity=max(0.,opacity)))
            # The modulo reset is invisible; insert a hidden endpoint just before it.
            for cycle in range(cycle_min,cycle_max+1):
                t=(cycle-initial)*period
                if .0001<t<=duration+1e-9:
                    keys.append(frame(t-.00005,z=3.,opacity=0.))
            unique={entry['t']:entry for entry in keys}
            keys=[unique[t] for t in sorted(unique)]
            add(f'air-particle-{i}-{j}','sphere',parent_id='airflow',x=x,y=y,radius=.055,color='#b1edff',frames=keys)

    # Three quiet callouts are anchored to nonrotating groups; the label plate stays horizontal.
    add('blade-callout','group',parent_id='fan',label='叶片安装角说明',opacity=1,
        frames=fade(0,duration*.56))
    add('blade-leader','path',parent_id='blade-callout',points=[[-1.55,1.38,.12],[-2.7,2.08,.1],[-3.55,2.08,.1]],stroke='#86b8aa',opacity=.75)
    add('blade-label','text',parent_id='blade-callout',text=f'叶片安装角  {pitch:g}°',x=-3.45,y=2.72,z=.1,font_size=.25,color=white)
    add('blade-detail','text',parent_id='blade-callout',text='实体厚度 · 绕轴旋转',x=-3.45,y=2.35,z=.1,font_size=.17,color='#9bb3ba')
    add('motor-callout','group',parent_id='motor',label='电机说明',opacity=1,frames=fade(0,duration*.56))
    add('motor-leader','path',parent_id='motor-callout',points=[[.4,.2,0],[2.85,1.19,0],[3.5,1.19,0]],stroke='#88a5bc',opacity=.75)
    add('motor-label','text',parent_id='motor-callout',text='电机与固定支架',x=3.5,y=1.84,font_size=.25,color=white)
    add('motor-detail','text',parent_id='motor-callout',text='机壳固定 · 转轴驱动轮毂',x=3.5,y=1.45,font_size=.17,color='#9bb3ba')
    add('flow-label','text',parent_id='fan',text='空气沿轴向穿过叶轮',x=3.3,y=2.8,z=.2,font_size=.26,color='#c2edff',opacity=0,
        frames=[frame(0,opacity=0),frame(flow_start,opacity=0),frame(flow_start+.5,opacity=1),frame(duration,opacity=1)])
    add('flow-note','text',parent_id='fan',text='气流为方向示意，不是 CFD',x=3.3,y=2.35,z=.2,font_size=.17,color='#8ca7b8',opacity=0,
        frames=[frame(0,opacity=0),frame(flow_start,opacity=0),frame(flow_start+.5,opacity=1),frame(duration,opacity=1)])
    add('presentation-note','text',text=f'教学慢放  {speed:g} 转/秒  ·  安装角 {pitch:g}°',x=0,y=-3.55,z=0,font_size=.22,color='#aac1cb')
    assumptions=list(dict.fromkeys([*p.assumptions,
        '原创基本几何体教学风机：五叶片具有挤出厚度和径向安装角；护罩、支架与电机外壳固定，轮毂和叶片随转子整体转动。',
        'speed 是教学慢放的画面转速，单位转/秒，不代表真实风机额定 RPM；播放时间用于机构讲解。',
        '气流线和粒子仅表示轴向输运方向；随安装角和慢放转速调整示意速度，不是 CFD、压力场或定量风量。',
        '尺寸、材料、护罩间距和拆解位移为程序化示意；不构成产品工程图或安全设计依据。']))[-12:]
    return Scene.model_validate({
        'title':p.title,'summary':p.summary or '从装配关系、叶片转动到轴向气流，观察风机如何工作。',
        'duration':duration,'mode':'3d','background':'#0c1621','objects':objects,
        'camera':{'azimuth':.36,'elevation':.20,'distance':13.8,'orbit':.48},
        'controls':[
            {'id':'speed','label':'教学转速','value':speed,'min':.1,'max':1,'step':.1,'unit':'转/秒'},
            {'id':'pitch','label':'叶片安装角','value':pitch,'min':0,'max':40,'step':1,'unit':'°'},
            {'id':'explode','label':'拆解距离','value':explode,'min':0,'max':2.5,'step':.1,'unit':'示意单位'},
        ],
        'steps':[
            {'title':'看清装配关系','explanation':'护罩与电机先靠近叶轮。叶片具有实体厚度与安装角；支架和电机外壳固定。','start':0,'end':duration*.24,'focus':['front-guard','motor','blade-0']},
            {'title':'轮毂带动叶片','explanation':'转子总成绕轴连续旋转，叶片安装角保持不变。教学转速可调，画面会慢放展示机构。','start':duration*.24,'end':duration*.57,'focus':['rotor','hub','blade-0']},
            {'title':'空气沿轴向流动','explanation':'箭头与粒子展示轴向输运。改变安装角可观察叶片姿态；气流是定性示意，未计算风量或压力。','start':duration*.57,'end':duration,'focus':['airflow','rotor']},
        ],
        'assumptions':assumptions,'evidence':'schematic',
    })
