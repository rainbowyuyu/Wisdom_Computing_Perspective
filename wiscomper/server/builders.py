"""Trusted, deterministic scene constructors. No generated code is executed."""
import ast
import math
import numpy as np
from .schema import Proposal, Scene

MINT='#69e3c0'; BLUE='#78abff'; GOLD='#ffd38a'; INK='#182839'; WHITE='#e6eef5'

SAMPLES = [
    {'id':'projectile','title':'一条抛物线，从哪里来','category':'运动推演','description':'速度、角度与重力共同决定轨迹','prompt':'解释斜抛运动，画出运动轨迹，并让我调整初速度、发射角度和重力。'},
    {'id':'pendulum','title':'摆动的节奏','category':'动力学','description':'改变摆长与阻尼，观察真实数值积分','prompt':'建立一个有阻尼的单摆，展示摆长和阻尼对运动的影响。'},
    {'id':'function','title':'让函数长出来','category':'数学','description':'曲线绘制与动态点同步','prompt':'绘制 sin(x)，显示动点在曲线上的运动。'},
    {'id':'wave','title':'波在走，介质呢','category':'波动','description':'追踪波峰与介质质点的不同运动','prompt':'解释一维正弦行波，展示质点上下振动，而波形向前传播。'},
    {'id':'field','title':'看见一个旋转的场','category':'场与输运','description':'箭头与粒子共享同一个解析速度场','prompt':'用速度箭头和粒子轨迹解释二维旋转速度场。'},
    {'id':'model3d','title':'拆开一台小电机','category':'三维建模','description':'基本体装配、分解与连续环绕','prompt':'用基础三维几何体展示电机的外壳、转子、轴承和转轴，先装配再展开。'},
    {'id':'fan','title':'风从叶片间穿过','category':'机械建模','description':'立体风机、叶片安装角与轴向气流','prompt':'解释一台轴流风机的构造和工作过程，展示叶片安装角、旋转和空气流动，选择合适的工具。'},
    {'id':'formula','title':'公式里的对应关系','category':'公式变形','description':'由多项式到因式分解','prompt':'把 x^2-5x+6=0 变成 (x-2)(x-3)=0，再解释根是2和3。'},
    {'id':'diagram','title':'水循环，一次旅行','category':'过程关系','description':'对象、连线和运动共同解释过程','prompt':'用海洋、蒸发、云、降雨之间的连续关系解释水循环。'},
    {'id':'riemann','title':'用矩形逼近一片面积','category':'数学与积分','description':'比较 x² 的黎曼和与解析面积','prompt':'用矩形近似 y=x² 在0到b之间的面积，让我调整分割数量、上限和采样位置，并比较解析面积。'},
    {'id':'refraction','title':'光为什么会拐弯','category':'光学','description':'折射率、入射角与全反射的临界点','prompt':'展示光穿过平面界面时的折射和反射，让我调整两侧折射率与入射角，探索全反射条件。'},
    {'id':'queue','title':'队伍为何越排越长','category':'流程与瓶颈','description':'固定到达与服务时间构成可信排队模型','prompt':'建立单服务台的确定性排队模型，让我调整到达间隔与服务时长，在固定24秒窗口观察等待和完成任务。'},
]


def sample_proposal(name,duration=12):
    item=next((s for s in SAMPLES if s['id']==name),None)
    if not item: raise ValueError('样例不存在。')
    return Proposal(title=item['title'],summary=item['description'],recipe=name,duration=duration,
        expression='sin(x)' if name=='function' else '',
        formula=r'x^2-5x+6=0' if name=='formula' else '',
        formula_next=r'(x-2)(x-3)=0' if name=='formula' else '',
        labels=['海洋','水汽','云','降雨'] if name=='diagram' else [])


def evaluate_expression(expression,x):
    """Evaluate only numeric expression AST; names/attributes/calls cannot escape."""
    if not isinstance(expression,str) or len(expression)>300:raise ValueError('函数表达式不能超过300个字符。')
    text=expression.strip().replace('^','**')
    if text.startswith('y='): text=text[2:]
    try: tree=ast.parse(text,mode='eval')
    except (SyntaxError,RecursionError): raise ValueError('请使用 sin(x)、x^2 等明确的函数表达式。') from None
    if sum(1 for _ in ast.walk(tree))>80: raise ValueError('表达式过长，请拆成较简单的函数。')
    funcs={'sin':np.sin,'cos':np.cos,'tan':np.tan,'exp':np.exp,'log':np.log,'ln':np.log,'sqrt':np.sqrt,'abs':np.abs}
    def visit(node,depth=0):
        if depth>16: raise ValueError('表达式嵌套过深。')
        sub=lambda v:visit(v,depth+1)
        if isinstance(node,ast.Constant) and type(node.value) in (int,float) and abs(node.value)<=1e6: return float(node.value)
        if isinstance(node,ast.Name) and node.id in {'x','pi','e'}: return {'x':x,'pi':np.pi,'e':np.e}[node.id]
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)): return sub(node.operand)*(1 if isinstance(node.op,ast.UAdd) else -1)
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Pow)):
            a,b=sub(node.left),sub(node.right)
            if isinstance(node.op,ast.Pow):
                if np.any(np.abs(b)>16): raise ValueError('指数范围过大，请缩小范围。')
                return np.power(a,b)
            return {ast.Add:np.add,ast.Sub:np.subtract,ast.Mult:np.multiply,ast.Div:np.divide}[type(node.op)](a,b)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in funcs and len(node.args)==1 and not node.keywords: return funcs[node.func.id](sub(node.args[0]))
        raise ValueError('仅支持变量x、数字、四则运算及常用数学函数。')
    with np.errstate(all='ignore'):
        result=np.asarray(visit(tree.body),dtype=float)+np.zeros_like(np.asarray(x,dtype=float))
    return result


def obj(ident,kind,**kw): return dict(id=ident,kind=kind,**kw)
def label(ident,text,x,y,**kw): return obj(ident,'text',text=text,x=x,y=y,color=WHITE,font_size=.30,**kw)
def control(ident,label_,value,min_,max_,step,unit=''): return dict(id=ident,label=label_,value=value,min=min_,max=max_,step=step,unit=unit)
def staged(duration,titles,explanations,focus=None):
    return [dict(title=title,explanation=explanations[i],start=round(i*duration/len(titles),6),end=min(duration,round((i+1)*duration/len(titles),6)),focus=(focus or [[]]*len(titles))[i]) for i,title in enumerate(titles)]
def checked_params(proposal,defaults,bounds):
    if set(proposal.parameters)-set(defaults): raise ValueError('当前推演包含不支持的参数。')
    result={**defaults,**proposal.parameters}
    for k,v in result.items():
        low,high=bounds[k]
        if not low<=v<=high: raise ValueError(f'参数 {k} 需在 {low} 至 {high} 之间。')
    return result
def axes():
    return [obj('axis-x','arrow',points=[[-6,-2.7],[6.4,-2.7]],stroke='#536675'),obj('axis-y','arrow',points=[[-6,-2.7],[-6,3.1]],stroke='#536675')]

def draw_frames(points,times):
    lengths=np.linalg.norm(np.diff(np.asarray(points,dtype=float),axis=0),axis=1)
    cumulative=np.r_[0.,np.cumsum(lengths)];total=float(cumulative[-1])
    return [{'t':round(float(t),6),'draw':float(length/total) if total else 1.} for t,length in zip(times,cumulative)]

def motion_samples(duration):return max(120,math.ceil(duration*20))

def short_label(text,count):return text if len(text)<=count else text[:max(1,count-1)]+'…'


def build_scene(proposal,asset_id=None):
    p=proposal if isinstance(proposal,Proposal) else Proposal.model_validate(proposal)
    if p.needs_clarification: raise ValueError(p.question or '需要补充条件。')
    if p.recipe in {'riemann','refraction','queue'}:
        from .extended_builders import build_riemann,build_refraction,build_queue
        scene={'riemann':build_riemann,'refraction':build_refraction,'queue':build_queue}[p.recipe](p)
    elif p.recipe=='fan':
        from .mechanical import build_fan
        scene=build_fan(p)
    else:
        scene=_build_scene(p,asset_id)
    selection=p.selection or scene.selection
    if selection is None:
        from .schema import ToolSelection
        if scene.mode=='3d':
            selection=ToolSelection(engine='threejs',category='mechanism' if p.recipe in {'fan','model3d'} else 'spatial',reason='使用立体构件与连续视角展示空间关系。')
        elif p.recipe=='formula':
            selection=ToolSelection(engine='manim',category='formula',reason='公式采用数学排版预览，使用Manim导出符号对应变形。')
        else:
            category='numerical' if p.recipe in {'function','projectile','pendulum','wave','field','riemann','refraction','queue'} else 'image_annotation' if p.recipe=='image' else 'process'
            selection=ToolSelection(engine='canvas2d',category=category,reason='二维画布保持坐标、路径和标注清晰，适合当前解释。')
    scene.selection=selection
    from .interactions import add_recipe_interactions
    return add_recipe_interactions(Scene.model_validate(scene.model_dump()),p.recipe)


def _build_scene(proposal,asset_id=None):
    p=proposal if isinstance(proposal,Proposal) else Proposal.model_validate(proposal)
    d=p.duration; objects=[]; controls=[]; steps=[]; evidence='schematic'; mode='2d'
    assumptions=list(p.assumptions)
    if p.recipe in {'formula','image','diagram','custom'} and p.parameters:
        raise ValueError('此场景没有可重算的数值参数，请选择对应的数学或物理推演。')
    if p.recipe=='custom':
        if not p.scene: raise ValueError('自定义场景缺少图层与时间轴。')
        scene=p.scene.model_copy(deep=True)
        if scene.duration!=d:raise ValueError('自定义场景时长必须与请求时长一致。')
        for item in scene.objects:
            if item.kind=='image' and (not asset_id or item.asset_id!=asset_id): raise ValueError('场景引用了未提交的图片。')
        return Scene.model_validate(scene.model_dump())
    if p.recipe=='function':
        cfg=checked_params(p,{'amplitude':1,'xmin':-6.28,'xmax':6.28},{'amplitude':(.1,4),'xmin':(-30,0),'xmax':(.1,30)})
        expression=p.expression or 'sin(x)'; xs=np.linspace(cfg['xmin'],cfg['xmax'],241); base_ys=evaluate_expression(expression,xs);ys=base_ys*cfg['amplitude']
        finite=np.isfinite(ys)&(np.abs(ys)<1e5)
        if finite.sum()<3: raise ValueError('这个区间没有足够的有限函数值，请调整表达式或范围。')
        # Fixed across the supported amplitude range, including a large base
        # expression whose downscaled values are still displayable.
        base_finite=np.isfinite(base_ys)&(np.abs(base_ys)<1e6)
        ymax=max(float(np.quantile(np.abs(base_ys[base_finite]),.97)),.01)*4
        displayed=finite&(np.abs(ys)<=ymax*1.1)
        points=np.c_[np.linspace(-5.8,5.8,len(xs)),np.clip(ys/ymax,-1.1,1.1)*2.2]
        xzero=-5.8-cfg['xmin']/(cfg['xmax']-cfg['xmin'])*11.6
        objects=[obj('axis-x','arrow',points=[[-6.3,0],[6.3,0]],stroke='#536675'),obj('axis-y','arrow',points=[[xzero,-2.8],[xzero,2.8]],stroke='#536675')]
        # Split discontinuities rather than drawing through poles/undefined regions.
        segment=[]; paths=[];disconnected=set()
        for i,pt in enumerate(points):
            if not displayed[i] or (segment and abs(pt[1]-segment[-1][1][1])>1):
                if len(segment)>1: paths.append(segment)
                disconnected.update([max(0,i-1),i,min(i+1,len(points)-1)])
                segment=[]
            if displayed[i]: segment.append((i,pt.tolist()))
        if len(segment)>1: paths.append(segment)
        if not paths or len(paths)>24:raise ValueError('函数在当前区间变化过快或间断过多，请缩小区间。')
        for i,segment in enumerate(paths):
            indices,pts=zip(*segment)
            frames=draw_frames(pts,[index*d/(len(xs)-1) for index in indices])
            objects.append(obj(f'curve-{i}','path',points=list(pts),stroke=MINT,filled=False,draw=0,frames=frames))
        # Track domain time instead of jumping directly across missing intervals.
        frames=[]
        for i,pt in enumerate(points):
            visible=bool(displayed[i] and i not in disconnected)
            frames.append(dict(t=round(i*d/(len(xs)-1),6),x=float(pt[0]),y=float(pt[1]) if np.isfinite(pt[1]) else 0.,opacity=1. if visible else 0.))
        objects.append(obj('moving-point','circle',radius=.10,color=GOLD,x=frames[0]['x'],y=frames[0]['y'],frames=frames))
        objects += [label('expression',short_label(f"y = {cfg['amplitude']:g} × ({expression})",100),0,3.2),label('domain',f"x ∈ [{cfg['xmin']:g}, {cfg['xmax']:g}] · 固定 y 轴尺度 ±{ymax:.3g}"+(' · 超范围点已省略' if np.any(finite&~displayed) else ''),0,-3.5)]
        controls=[control('amplitude','纵向倍率',cfg['amplitude'],.1,4,.1)]
        evidence='computed'; assumptions+=['曲线由安全表达式数值采样；同表达式与区间采用固定纵轴尺度，不随纵向倍率改变。','纵轴标尺按原函数有限值绝对值97%分位的4倍设置；超范围和无定义点分段省略，不画虚假水平平台。']
        steps=staged(d,['确定坐标与表达式','沿横轴描点','看整体变化'],['输入函数在所选区间逐点计算。','运动点与曲线来自相同数值数组。','调整纵向倍率后重新计算，不改变横轴取值。'],[['axis-x'],['moving-point'],['curve-0']])
    elif p.recipe=='projectile':
        cfg=checked_params(p,{'speed':12,'angle':45,'gravity':9.81},{'speed':(1,30),'angle':(10,80),'gravity':(.5,20)})
        v,angle,g=cfg['speed'],math.radians(cfg['angle']),cfg['gravity']; vx=v*math.cos(angle); vy=v*math.sin(angle)
        flight=2*vy/g; reach=vx*flight; peak=vy*vy/(2*g)
        ts=np.linspace(0,flight,121); xx=vx*ts; yy=vy*ts-.5*g*ts**2
        ref_v,ref_theta,ref_g=12.,math.pi/4,9.81
        ref_flight=2*ref_v*math.sin(ref_theta)/ref_g;ref_reach=ref_v*math.cos(ref_theta)*ref_flight;ref_peak=(ref_v*math.sin(ref_theta))**2/(2*ref_g)
        scale=min(11/max(reach,ref_reach,.1),4.8/max(peak,ref_peak,.1)); points=[[-5.5+float(x)*scale,-2.5+float(y)*scale] for x,y in zip(xx,yy)]
        ref_times=np.linspace(0,ref_flight,121)
        reference=[[-5.5+ref_v*math.cos(ref_theta)*float(t)*scale,-2.5+(ref_v*math.sin(ref_theta)*float(t)-.5*ref_g*float(t)**2)*scale] for t in ref_times]
        times=np.linspace(0,d,121)
        objects=[obj('axis-x','arrow',points=[[-5.5,-2.5],[6.2,-2.5]],stroke='#536675'),obj('axis-y','arrow',points=[[-5.5,-2.5],[-5.5,2.7]],stroke='#536675'),obj('reference-trajectory','path',points=reference,stroke='#8494a7',filled=False,opacity=.45,line_width=.025),obj('trajectory','path',points=points,stroke=MINT,filled=False,draw=0,frames=draw_frames(points,times)),obj('ball','circle',radius=.17,color=GOLD,x=points[0][0],y=points[0][1],frames=[dict(t=round(float(t),6),x=xy[0],y=xy[1]) for t,xy in zip(times,points)]),label('facts',f'飞行时间 {flight:.2f} s     射程 {reach:.2f} m     最高点 {peak:.2f} m',0,3.5),obj('equation','formula',latex=r'x=v_0\cos\theta\,t,\quad y=v_0\sin\theta\,t-\frac12gt^2',y=-3.5,color=WHITE,font_size=.32),obj('reference-note','text',text=f'灰线固定基准：12 m/s · 45° · g=9.81   |   每画面单位 {1/scale:.2f} m',y=2.95,font_size=.25,color='#a6b4c7')]
        controls=[control('speed','初速度',v,1,30,.5,'m/s'),control('angle','发射角',cfg['angle'],10,80,1,'°'),control('gravity','重力加速度',g,.5,20,.1,'m/s²')]
        evidence='computed'; assumptions+=['点质量、均匀重力、忽略空气阻力、出发和落地点等高。','画面时间均匀映射至实际飞行时间；横纵坐标使用相同显示比例。','灰色基准始终是12m/s、45°、g=9.81的轨迹；当前与基准共享完整可见坐标尺度，便于比较而不裁切。']
        steps=staged(d,['分解初速度','追踪上升和最高点','落地与射程'],['水平方向匀速；竖直方向受重力减速。','竖直速度降到零时到达最高点，水平运动继续。','解析方程计算落地时刻与水平位移。'],[['ball'],['trajectory'],['facts']])
    elif p.recipe=='pendulum':
        cfg=checked_params(p,{'length':1.5,'angle':35,'damping':.05},{'length':(.5,3),'angle':(5,60),'damping':(0,.8)})
        length,theta,decay=cfg['length'],math.radians(cfg['angle']),cfg['damping']; omega=0.; count=motion_samples(d);substeps=math.ceil(d/count*240);dt=d/count/substeps;frames=[]
        def rate(a,b):return b,-9.81/length*math.sin(a)-decay*b
        for i in range(count+1):
            frames.append(dict(t=round(i*d/count,6),x=length*1.5*math.sin(theta),y=2.3-length*1.5*math.cos(theta)))
            if i==count:break
            for _ in range(substeps):
                k1=rate(theta,omega);k2=rate(theta+dt*k1[0]/2,omega+dt*k1[1]/2);k3=rate(theta+dt*k2[0]/2,omega+dt*k2[1]/2);k4=rate(theta+dt*k3[0],omega+dt*k3[1])
                theta+=dt*(k1[0]+2*k2[0]+2*k3[0]+k4[0])/6;omega+=dt*(k1[1]+2*k2[1]+2*k3[1]+k4[1])/6
        rod_frames=[{'t':f['t'],'rotation':math.atan2(f['x'],2.3-f['y'])} for f in frames]
        objects=[obj('pivot','circle',x=0,y=2.3,radius=.10,color=WHITE),obj('rod','line',x=0,y=2.3,points=[[0,0],[0,-length*1.5]],stroke=BLUE,rotation=rod_frames[0]['rotation'],frames=rod_frames),obj('bob','circle',radius=.24,color=MINT,x=frames[0]['x'],y=frames[0]['y'],frames=frames),label('readout',f'摆长 {length:g} m · 初角 {cfg["angle"]:g}° · 阻尼 {decay:g} s⁻¹',0,-3.3),obj('equation','formula',latex=r'\ddot\theta+b\dot\theta+\frac{g}{L}\sin\theta=0',x=0,y=3.45,color=WHITE,font_size=.35)]
        controls=[control('length','摆长',length,.5,3,.1,'m'),control('angle','初始摆角',cfg['angle'],5,60,1,'°'),control('damping','阻尼',decay,0,.8,.01,'s⁻¹')]
        evidence='computed';assumptions+=['无质量刚性摆杆与点质量；线性角速度阻尼；固定步长RK4积分。','画面时间即模型时间，摆长显示按1.5倍统一缩放。']
        steps=staged(d,['释放摆球','重力持续改变速度','观察阻尼的作用'],['初始角度确定摆球位置，初始角速度为零。','杆长固定，切向重力产生摆动。','阻尼增加会让振幅更快衰减；改变摆长会改变节奏。'],[['bob'],['rod'],['bob']])
    elif p.recipe=='wave':
        cfg=checked_params(p,{'amplitude':1,'frequency':.6,'wavelength':4},{'amplitude':(.2,2),'frequency':(.1,1.5),'wavelength':(1,8)})
        count=motion_samples(d)
        objects=[obj('axis','line',points=[[-6.5,0],[6.5,0]],stroke='#536675')]
        for i,x in enumerate(np.linspace(-6,6,55)):
            frames=[{'t':round(j*d/count,6),'y':cfg['amplitude']*math.sin(2*math.pi*(float(x)/cfg['wavelength']-cfg['frequency']*j*d/count))} for j in range(count+1)]
            objects.append(obj(f'particle-{i}','circle',x=float(x),y=frames[0]['y'],radius=.12 if i==27 else .055,color=GOLD if i==27 else MINT,frames=frames))
        objects += [label('note','金色质点只上下振动，波形向右传播',0,-3.4),obj('formula','formula',latex=r'y=A\sin(2\pi(x/\lambda-ft))',y=3.35,color=WHITE)]
        controls=[control('amplitude','振幅',cfg['amplitude'],.2,2,.1),control('frequency','频率',cfg['frequency'],.1,1.5,.1,'Hz'),control('wavelength','波长',cfg['wavelength'],1,8,.2)]
        evidence='computed';assumptions+=['解析一维正弦行波；质点位置是介质位移示意，不表示物质随波整体向前移动。']
        steps=staged(d,['观察一个质点','比较相邻质点','区分传播与振动'],['先看金色标记的上下位移。','相邻位置有相位差，形成整体波形。','调整频率或波长，观察波速 λf 的变化。'],[['particle-27'],[],[]])
    elif p.recipe=='field':
        cfg=checked_params(p,{'omega':.6},{'omega':(-1.5,1.5)})
        omega=cfg['omega'];count=motion_samples(d)
        for i,x in enumerate(np.linspace(-5.4,5.4,10)):
            for j,y in enumerate(np.linspace(-2.4,2.4,5)):
                dx,dy=-omega*y*.18,omega*x*.18
                if abs(dx)+abs(dy)>.001:objects.append(obj(f'vector-{i}-{j}','arrow',points=[[float(x),float(y)],[float(x+dx),float(y+dy)]],stroke=BLUE,opacity=.45,line_width=.025))
        for i in range(20):
            radius=.5+(i%5)*.45;phase=i*2.39996
            frames=[dict(t=round(j*d/count,6),x=radius*math.cos(phase+omega*j*d/count),y=radius*math.sin(phase+omega*j*d/count)) for j in range(count+1)]
            objects.append(obj(f'particle-{i}','circle',radius=.065,color=GOLD if i==0 else MINT,x=frames[0]['x'],y=frames[0]['y'],frames=frames))
        objects += [obj('formula','formula',latex=r'\mathbf{v}(x,y)=\omega(-y,x)',y=3.4,color=WHITE),label('note','箭头表示局部速度；粒子沿同一解析场运动',0,-3.4)]
        controls=[control('omega','旋转角速度',omega,-1.5,1.5,.1,'rad/s')];evidence='computed';assumptions+=['解析平面刚体旋转速度场；不包含压力、黏性或流固耦合，不是CFD结果。']
        steps=staged(d,['速度有方向','把粒子放进场中','改变旋转强度'],['箭头给出每个位置的瞬时速度。','粒子轨迹与速度场满足同一个运动方程。','改变角速度正负可反转旋转方向。'])
    elif p.recipe=='model3d':
        cfg=checked_params(p,{'explode':1.5},{'explode':(0,3)})
        e=cfg['explode'];mode='3d';names=(p.labels+['外壳','转子','轴承','转轴'])[:4]
        objects=[obj('housing','cylinder',label=names[0],radius=1.6,height=2.8,color=BLUE,opacity=.22,frames=[{'t':0,'x':0},{'t':d*.35,'x':0},{'t':d*.75,'x':-e*2},{'t':d,'x':-e*2}]),obj('rotor','cylinder',label=names[1],radius=.95,height=2.2,color=MINT),obj('bearing','cylinder',label=names[2],radius=.5,height=.3,y=1.5,color=GOLD,frames=[{'t':0,'y':1.5},{'t':d*.35,'y':1.5},{'t':d*.75,'y':1.5+e},{'t':d,'y':1.5+e}]),obj('shaft','cylinder',label=names[3],radius=.16,height=4,color=WHITE)]
        controls=[control('explode','拆解距离',e,0,3,.1)]
        assumptions+=['由基本几何体组成的教学结构示意；不代表真实电机尺寸、材料、电磁场或装配公差。']
        steps=staged(d,['先看整体','沿构件展开','观察部件关系'],['半透明外壳帮助观察内部结构。','外壳和轴承沿明确方向移开，转子和转轴保留装配基准。','同一模型连续环绕，部件位置与标签保持一致。'],[['housing'],['bearing'],['rotor','shaft']])
    elif p.recipe=='formula':
        if not p.formula.strip():raise ValueError('请给出要解释的公式。')
        objects=[obj('formula','formula',latex=p.formula,latex_next=p.formula_next,y=.2,font_size=.65,color=WHITE),label('explanation',p.summary[:100] or '对应符号逐步变化，保留中间关系',0,-2.2)]
        steps=staged(d,['理解起始表达式','观察对应变化'],['先确认符号与条件。',p.summary[:600] or '依据给定关系进行一步变化；复杂推导应拆成更多场景。'],[['formula'],['formula']])
        assumptions+=['通用公式由模型提供；此视图展示变形，不自动证明任意等式成立。']
    elif p.recipe=='image':
        if not asset_id:raise ValueError('图片推演需要先上传图片。')
        names=p.labels or ['观察主体','识别关系','说明变化']
        objects=[obj('source-image','image',asset_id=asset_id,width=10,height=6,x=0,y=0)]
        for i,name in enumerate(names[:4]):
            t=i*d/max(1,len(names));objects.append(label(f'annotation-{i}',name,-5.5+i*3.6,-3.6,opacity=0,frames=[{'t':round(t,4),'opacity':0},{'t':round(min(t+.7,d),4),'opacity':1}]))
        objects.append(obj('highlight','rect',width=4,height=3,filled=False,stroke=GOLD,line_width=.05,opacity=0,frames=[{'t':0,'opacity':0},{'t':d*.25,'opacity':1,'scale':1.05},{'t':d,'opacity':.5,'scale':1}]))
        evidence='image_annotation';assumptions+=['保留原始图像并叠加讲解标注；不从单张图自动断言深度、尺寸或真实物理属性。']
        steps=staged(d,['看原图','聚焦结构','连接说明'],['上传的图像作为依据。','框选区域是讲解关注区域。',p.summary[:600] or '标注用于解释图中关系。'],[['source-image'],['highlight'],[]])
    else:
        names=p.labels or ['输入','处理','输出']; n=len(names)
        positions=[(-5.4+i*10.8/(n-1),.2) for i in range(n)] if n>1 else [(0,.2)]
        node_width=min(2.3,10.5/n)
        for i,(name,(x,y)) in enumerate(zip(names,positions)):
            t=i*d*.6/max(1,n-1)
            objects += [obj(f'node-{i}','rect',x=x,y=y,width=node_width,height=1.25,color=INK,stroke=MINT,opacity=0,frames=[{'t':round(t,4),'opacity':0},{'t':round(t+.5,4),'opacity':1}]),obj(f'label-{i}','text',text=short_label(name,max(3,int(node_width/.25)-1)),label=name,x=x,y=y,font_size=.25,color=WHITE,opacity=0,frames=[{'t':round(t,4),'opacity':0},{'t':round(t+.5,4),'opacity':1}])]
            if i<n-1:
                dx=positions[i+1][0];objects.append(obj(f'edge-{i}','arrow',points=[[x+node_width/2+.06,y],[dx-node_width/2-.06,y]],stroke=BLUE,draw=0,frames=[{'t':round(t+.4,4),'draw':0},{'t':round(t+1,4),'draw':1}]))
        path=[dict(t=round(i*d/max(1,n-1),4),x=x,y=y-1.2) for i,(x,y) in enumerate(positions)]
        objects.append(obj('flow-marker','circle',x=positions[0][0],y=-1,radius=.1,color=GOLD,frames=path if n>1 else []))
        steps=staged(d,['识别对象','连起关系','跟随变化'],['把描述中的主要对象放进同一画面。','连线表达先后或因果关系；需要依据题意核对。',p.summary[:600] or '移动标记帮助追踪变化路径。'])
        assumptions+=['流程连线为概念关系示意，不是实验测量或数值仿真。']
    for item in objects:
        for frame in item.get('frames',[]):frame['t']=min(d,frame['t'])
    return Scene.model_validate(dict(title=p.title,summary=p.summary,duration=d,mode=mode,objects=objects,steps=steps,controls=controls,assumptions=list(dict.fromkeys(assumptions))[-12:],evidence=evidence))
