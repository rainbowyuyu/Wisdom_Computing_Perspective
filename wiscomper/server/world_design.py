"""Bounded world-design interface owned by Wiscomper.

This is a deterministic design catalogue, not an LLM semantic parser. It creates
validated schematic scenes and an explicit physics contract; PhysCast performs
simulation. CLI: python -m server.world_design, one JSON object on stdin.
No credentials, network calls, generated code, or project-database edits.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from typing import Any

from .schema import Scene

SCHEMA = 'world-design-v1'
MAX_INPUT_BYTES = 65536
DOMAINS = ('pendulum', 'rocket', 'wind_turbine')
BLUE, RED, INK, GRAY = '#1557B0', '#D14545', '#183153', '#6B7C93'

# name: default, SI unit, lower bound, upper bound, display label
PARAMETERS = {
    'pendulum': {
        'length_m': (2., 'm', .1, 20., '摆长'),
        'mass_kg': (1., 'kg', .01, 100., '摆球质量'),
        'gravity_m_s2': (9.81, 'm/s^2', .1, 25., '重力加速度'),
        'damping_s_inv': (.03, '1/s', 0., 2., '角速度阻尼系数'),
        'theta0_rad': (.5, 'rad', -2.8, 2.8, '初始摆角'),
        'omega0_rad_s': (0., 'rad/s', -4., 4., '初始角速度'),
    },
    'rocket': {
        'dry_mass_kg': (50., 'kg', 1., 10000., '干质量'),
        'propellant_mass_kg': (25., 'kg', .1, 5000., '推进剂质量'),
        'thrust_N': (1500., 'N', 1., 1000000., '恒定推力'),
        'burn_time_s': (8., 's', .5, 30., '燃烧时长'),
        'drag_coefficient': (.45, '1', 0., 2., '阻力系数'),
        'area_m2': (.08, 'm^2', .001, 50., '迎风面积'),
        'gravity_m_s2': (9.81, 'm/s^2', .1, 25., '重力加速度'),
    },
    'wind_turbine': {
        'wind_scale': (1., '1', 0., 3., '原模型风载激励倍率'),
        'wave_scale': (1., '1', 0., 3., '原模型波浪激励倍率'),
        'current_scale': (1., '1', 0., 3., '原模型海流激励倍率'),
    },
}

class DesignError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)

def _number(value: Any, label: str, low: float, high: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise DesignError('invalid_parameter', f'{label} 必须是 {low:g} 到 {high:g} 之间的有限数值。')
    return float(value)

def _domain(prompt: str, requested: Any) -> tuple[str, str]:
    if requested is not None:
        if not isinstance(requested, str) or requested not in DOMAINS:
            raise DesignError('unsupported_domain', '当前世界设计支持 pendulum、rocket、wind_turbine。')
        return requested, 'explicit_domain'
    groups = {
        'pendulum': ('钟摆', '单摆', '摆锤', 'pendulum'),
        'rocket': ('火箭', 'rocket'),
        'wind_turbine': ('风机', '风力发电', '风电', 'wind turbine', 'wind_turbine'),
    }
    folded = prompt.casefold()
    matches = [key for key, words in groups.items() if any(word in folded for word in words)]
    if len(matches) > 1:
        raise DesignError('ambiguous_domain', '这句话包含多个世界类型，请明确 domain 或分别创建。')
    if not matches:
        raise DesignError('unsupported_domain', '尚未识别到已接入世界类型；目前可创建钟摆、火箭或风力发电机世界。')
    if any(word in folded for word in ('双摆', '多摆', 'double pendulum', '轴流风机', '工业风扇')):
        raise DesignError('unsupported_model_variant', '当前设计目录不支持该模型变体，请指定已接入的单摆或风力发电机。')
    return matches[0], 'deterministic_keyword_router'

# Only labelled parameters with documented units are extracted. This parser is
# deliberately finite: arbitrary scientific language remains an LLM task.
_NUMBER = r'[+-]?(?:[0-9]+(?:[.][0-9]*)?|[.][0-9]+)(?:[eE][+-]?[0-9]+)?'
_UNIT_TABLES = {
    'length': {'m':1., '米':1., 'cm':.01, '厘米':.01, 'mm':.001, '毫米':.001},
    'mass': {'kg':1., '千克':1., '公斤':1., 'g':.001, '克':.001},
    'angle': {'rad':1., '弧度':1., 'deg':math.pi/180, 'degree':math.pi/180, 'degrees':math.pi/180, '°':math.pi/180, '度':math.pi/180},
    'angular_velocity': {'rad/s':1., '弧度/秒':1., 'deg/s':math.pi/180, '度/秒':math.pi/180},
    'time': {'s':1., 'sec':1., '秒':1., 'ms':.001, '毫秒':.001},
    'acceleration': {'m/s^2':1., 'm/s²':1., 'm/s2':1., '米/秒²':1.},
    'inverse_time': {'1/s':1., 's^-1':1., 's⁻¹':1.},
    'force': {'N':1., '牛顿':1., 'kN':1000., '千牛':1000.},
    'area': {'m^2':1., 'm²':1., '平方米':1., 'cm^2':.0001, 'cm²':.0001, '平方厘米':.0001},
    'scalar': {'倍':1.},
}
_PROMPT_FIELDS = {
    'pendulum': [
        ('length_m', ('摆长','杆长','length'), 'length'),
        ('mass_kg', ('摆球质量','质量','mass'), 'mass'),
        ('theta0_rad', ('初始摆角','初始角度','初角','摆角','initial angle','theta0'), 'angle'),
        ('omega0_rad_s', ('初始角速度','initial angular velocity','omega0'), 'angular_velocity'),
        ('damping_s_inv', ('阻尼系数','阻尼','damping'), 'inverse_time'),
    ],
    'rocket': [
        ('dry_mass_kg', ('干质量','dry mass'), 'mass'),
        ('propellant_mass_kg', ('推进剂质量','燃料质量','propellant mass'), 'mass'),
        ('thrust_N', ('推力','thrust'), 'force'),
        ('burn_time_s', ('燃烧时长','燃烧时间','burn time'), 'time'),
        ('drag_coefficient', ('阻力系数','drag coefficient'), 'scalar'),
        ('area_m2', ('迎风面积','截面积','reference area'), 'area'),
    ],
    'wind_turbine': [
        ('wind_scale', ('风载倍率','风载倍数','风载','wind scale'), 'scalar'),
        ('wave_scale', ('波浪倍率','波浪倍数','wave scale'), 'scalar'),
        ('current_scale', ('海流倍率','海流倍数','current scale'), 'scalar'),
    ],
}

def _prompt_parameters(prompt: str, domain: str) -> tuple[dict, dict, list[str], list[tuple[int,int]]]:
    fields=list(_PROMPT_FIELDS[domain])
    if domain!='wind_turbine':
        fields.append(('gravity_m_s2',('重力加速度','gravity'),'acceleration'))
    fields += [('duration_s',('仿真时长','模拟时长','仿真时间','模拟时间','持续时间','仿真','模拟','持续','duration','simulate for'),'time'),
               ('dt_s',('积分步长','时间步长','步长','time step','dt'),'time')]
    parsed, provenance, warnings, used = {}, {}, [], []
    for key,labels,unit_kind in fields:
        units=_UNIT_TABLES[unit_kind]
        label='(?:'+'|'.join(re.escape(v) for v in sorted(labels,key=len,reverse=True))+')'
        unit='(?:'+'|'.join(re.escape(v) for v in sorted(units,key=len,reverse=True))+')'
        pattern=re.compile(label+r'\s*(?:为|设为|等于|is|=|:|：)?\s*('+_NUMBER+r')\s*('+unit+r')?',re.I)
        for match in pattern.finditer(prompt):
            if any(match.start()<end and match.end()>start for start,end in used):
                continue
            number, input_unit=match.group(1),match.group(2)
            tail=prompt[match.end():match.end()+1]
            if input_unit and tail and ((tail.isascii() and tail.isalpha()) or tail in '/^²³⁻·*'):
                warnings.append(f'未完整识别“{match.group(0)}”后的单位；请在参数区显式填写 {key}。')
                continue
            if not input_unit and tail and (tail.isalpha() or '\u4e00'<=tail<='\u9fff') and tail not in '的和并':
                warnings.append(f'未识别“{match.group(0)}”后的单位；请在参数区显式填写 {key}。')
                continue
            if not input_unit and unit_kind in {'angle','angular_velocity'}:
                warnings.append(f'“{match.group(0)}”缺少角度单位；请写明度/弧度或在参数区填写 {key}。')
                continue
            factor=next((factor for name,factor in units.items() if input_unit and name.casefold()==input_unit.casefold()),1.)
            value=float(number)*factor
            if key in parsed and not math.isclose(parsed[key],value,rel_tol=1e-10,abs_tol=1e-12):
                raise DesignError('ambiguous_parameter',f'句子为 {key} 给出了不同数值，请保留一个明确值。')
            parsed[key]=value
            provenance[key]={'source':'prompt','text':match.group(0),'input_unit':input_unit or 'assumed_SI'}
            used.append(match.span())
    unbound=[m.group(0) for m in re.finditer(_NUMBER,prompt) if not any(m.start()>=start and m.end()<=end for start,end in used)]
    if unbound:
        warnings.append('句子中尚未绑定到模型参数的数字：'+', '.join(unbound[:12])+'。请检查参数区；这些数字未用于计算。')
    return parsed,provenance,warnings,used

def _obj(ident: str, kind: str, **values: Any) -> dict:
    return {'id': ident, 'kind': kind, 'color': BLUE, 'stroke': BLUE, **values}

def _label(ident: str, text: str, x: float, y: float, **values: Any) -> dict:
    return _obj(ident, 'text', text=text, x=x, y=y, font_size=.31, color=INK, **values)

def _scene(domain: str, p: dict[str, float], duration: float) -> dict:
    """Use Wiscomper's existing validated renderer schema; geometry is schematic."""
    if domain == 'pendulum':
        length = 2.3  # display normalization; physical length remains p['length_m']
        pivot_y=.5
        x, y = length * math.sin(p['theta0_rad']), pivot_y - length * math.cos(p['theta0_rad'])
        objects = [
            _obj('support', 'line', points=[[-1.4, pivot_y+.25], [1.4, pivot_y+.25]], stroke=GRAY),
            _obj('pivot', 'circle', y=pivot_y, radius=.10, color=INK),
            _obj('rod', 'line', points=[[0, pivot_y], [x, y]], line_width=.055),
            _obj('bob', 'circle', x=x, y=y, radius=.28, color=RED),
            _obj('gravity', 'arrow', points=[[x+.6, y+.25], [x+.6, y-.8]], stroke=RED),
            _label('gravity-label', 'mg', x+1., y-.25),
            _label('parameter-label', f"L = {p['length_m']:g} m    m = {p['mass_kg']:g} kg    θ₀ = {p['theta0_rad']:.3g} rad", 0, -2.7),
            _obj('equation', 'formula', latex=r'\ddot\theta+b\dot\theta+\frac{g}{L}\sin\theta=0', y=3.2, color=INK),
        ]
        title = '钟摆世界 · 结构与初始条件'
        summary = '固定铰支点、无质量刚杆与点质量摆球；初始角度控制画面，物理轨迹由 PhysCast 求解。'
        targets = ['pivot', 'rod', 'bob']
    elif domain == 'rocket':
        objects = [
            _obj('ground', 'line', points=[[-5., -2.6], [5., -2.6]], stroke=GRAY),
            _obj('rocket-body', 'rect', x=0, y=.1, width=.85, height=3., color=BLUE),
            _obj('rocket-nose', 'path', points=[[-.425, 1.6], [0, 2.45], [.425, 1.6]], color=BLUE),
            _obj('rocket-fin-left', 'path', points=[[-.42,-.7],[-1.,-1.65],[-.42,-1.35]], color=RED),
            _obj('rocket-fin-right', 'path', points=[[.42,-.7],[1.,-1.65],[.42,-1.35]], color=RED),
            _obj('thrust', 'arrow', points=[[-1.7,-1.4],[-1.7,1.1]], stroke=RED),
            _label('thrust-label', '推力 T(t)', -2.8, .4),
            _obj('gravity', 'arrow', points=[[1.7,1.2],[1.7,-.5]], stroke=GRAY),
            _label('weight-label', '重力 mg', 2.8, .5),
            _label('mass-label', f"干质量 {p['dry_mass_kg']:g} kg · 推进剂 {p['propellant_mass_kg']:g} kg", 0, -3.15),
            _obj('equation', 'formula', latex=r'm(t)\dot v=T(t)-m(t)g-\tfrac12\rho C_D A v|v|', y=3.25, color=INK, font_size=.32),
        ]
        title = '火箭世界 · 竖直飞行基线'
        summary = '单级竖直点质量火箭；推力、变质量、重力和阻力组成方程。此图只说明构件与受力。'
        targets = ['rocket-body', 'thrust', 'gravity']
    else:
        objects = [
            _obj('tower', 'rect', x=0, y=.1, width=.22, height=3.6, color=GRAY),
            _obj('nacelle', 'rect', x=.2, y=2., width=.8, height=.38),
            _obj('hub', 'circle', x=0, y=2., radius=.17, color=RED),
            _obj('floating-base', 'rect', x=0, y=-1.9, width=2.3, height=.45),
            _obj('water', 'path', points=[[-5.,-1.65],[-4.,-1.5],[-3.,-1.7],[-2.,-1.5],[-1.,-1.7],[0,-1.5],[1.,-1.7],[2.,-1.5],[3.,-1.7],[4.,-1.5],[5.,-1.65]], filled=False, stroke=BLUE),
            _obj('mooring-left', 'line', points=[[-.8,-2.1],[-2.4,-3.]], stroke=GRAY),
            _obj('mooring-right', 'line', points=[[.8,-2.1],[2.4,-3.]], stroke=GRAY),
            _obj('wind', 'arrow', points=[[-4.9,1.7],[-2.9,1.7]], stroke=RED),
            _label('wind-label', f"风载 × {p['wind_scale']:g}", -4., 2.25),
            _obj('current', 'arrow', points=[[2.8,-2.4],[4.8,-2.4]], stroke=BLUE),
            _label('current-label', f"海流 × {p['current_scale']:g}", 3.7,-2.95),
            _label('wave-label', f"波浪 × {p['wave_scale']:g}", -3.7,-2.95),
            _label('model-label', '调用原耦合降阶模型；倍率不是风速或波高', 0, 3.45),
        ]
        for i in range(3):
            angle = i*2*math.pi/3
            objects.append(_obj(f'blade-{i}', 'line', points=[[0,2.],[1.3*math.sin(angle),2.+1.3*math.cos(angle)]], line_width=.11))
        title = '风机世界 · 风浪流耦合'
        summary = '浮式风力发电机、支承平台和系泊结构示意；实际参数与响应来自 PhysCast 原有耦合降阶模型。'
        targets = ['tower', 'floating-base', 'water']
    objects.append(_label('evidence-label', '设计示意 · 尚未运行仿真', 0, -3.65))
    return Scene.model_validate({
        'version': 1, 'title': title, 'summary': summary, 'duration': min(45.,max(6.,duration)),
        'mode': '2d', 'background': '#F5F7FB', 'objects': objects,
        'evidence': 'schematic',
        'steps': [{'title': '结构、边界与变量', 'explanation': summary, 'start': 0, 'end': min(45.,max(6.,duration)), 'focus': targets}],
        'assumptions': ['构件尺寸为统一视口下的设计示意；不代表 CAD 几何、网格或数值仿真结果。',
                        '仿真时间以设计契约 duration_s 为准；场景 duration 仅用于原渲染器的演示时间线。'],
        'selection': {'engine': 'canvas2d', 'category': 'mechanism', 'reason': '采用 Wiscomper 已验证的 Scene 契约呈现结构、受力和模型边界。'},
    }).model_dump(mode='json')

DESCRIPTIONS = {
    'pendulum': {
        'title': '钟摆世界',
        'model': 'damped_nonlinear_planar_pendulum',
        'objects': [
            {'id':'pivot','kind':'fixed_support','label':'固定铰支点'},
            {'id':'rod','kind':'massless_rigid_rod','label':'无质量刚杆','parameter_keys':['length_m']},
            {'id':'bob','kind':'point_mass','label':'点质量摆球','parameter_keys':['mass_kg']},
        ],
        'constraints': [
            {'id':'fixed_length','equation':'x^2+y^2=L^2','description':'摆球到支点距离恒定。'},
            {'id':'dynamics','equation':'theta_ddot + b*theta_dot + (g/L)*sin(theta) = 0','description':'非线性平面单摆，线性角速度阻尼。'},
        ],
        'observables': [('theta_rad','摆角','rad'),('omega_rad_s','角速度','rad/s'),('x_m','水平位置','m'),('y_m','竖直位置','m'),('energy_J','机械能','J')],
        'assumptions': ['运动局限于竖直平面；杆无质量、长度固定，摆球视为点质量。','重力均匀，阻尼与角速度线性相关；不含轴承间隙、杆弹性或空气流场。'],
        'sources': ['server/schema.py','server/builders.py','server/world_design.py'],
    },
    'rocket': {
        'title': '火箭世界',
        'model': 'vertical_variable_mass_rocket',
        'objects': [
            {'id':'rocket','kind':'variable_point_mass','label':'火箭总成','parameter_keys':['dry_mass_kg','propellant_mass_kg','area_m2']},
            {'id':'engine','kind':'finite_burn_thrust','label':'有限时长恒推力发动机','parameter_keys':['thrust_N','burn_time_s']},
            {'id':'environment','kind':'uniform_gravity_drag','label':'重力与空气阻力环境','parameter_keys':['gravity_m_s2','drag_coefficient']},
        ],
        'constraints': [
            {'id':'mass','equation':'m(t)=m_dry+m_prop*max(0,1-t/t_burn)','description':'推进剂在燃烧阶段均匀消耗。'},
            {'id':'thrust','equation':'T(t)=T0 for t<t_burn; T(t)=0 otherwise','description':'燃烧结束后推力归零。'},
            {'id':'dynamics','equation':'h_dot=v; m*v_dot=T-m*g-0.5*rho*C_D*A*v*abs(v)','description':'竖直一维运动，地面接触逻辑由 PhysCast 求解器定义。'},
        ],
        'observables': [('altitude_m','高度','m'),('velocity_m_s','竖直速度','m/s'),('mass_kg','质量','kg'),('acceleration_m_s2','加速度','m/s^2'),('thrust_N','推力','N')],
        'assumptions': ['单级竖直点质量教学模型；不含姿态、制导、多级分离或轨道力学。','恒推力、恒定重力与准稳态阻力；密度模型及落地处理以 PhysCast 实际运行 provenance 为准。'],
        'sources': ['server/schema.py','server/world_design.py'],
    },
    'wind_turbine': {
        'title': '风机世界',
        'model': 'physcast_existing_coupled_rom',
        'objects': [
            {'id':'rotor','kind':'wind_energy_rotor','label':'风力发电机叶轮'},
            {'id':'tower','kind':'tower','label':'塔架'},
            {'id':'platform','kind':'floating_support','label':'浮式支承平台'},
            {'id':'mooring','kind':'mooring','label':'系泊约束'},
            {'id':'environment','kind':'wind_wave_current','label':'风浪流耦合激励','parameter_keys':['wind_scale','wave_scale','current_scale']},
        ],
        'constraints': [
            {'id':'source_model','description':'复用 PhysCast 原有耦合降阶模型及其实际参数和通道，不把轴流风扇样例当作风力发电机。'},
            {'id':'forcing','equation':'F = wind_scale*F_wind + wave_scale*F_wave + current_scale*F_current','description':'倍率只缩放原模型已有激励；不是风速、浪高、流速或重新标定后的物理量。'},
        ],
        'observables': [('surge_m','平台纵荡','m'),('pitch_rad','平台俯仰','rad'),('eta_m','柔性位移','m'),('rotor_rad_s','转子角速度','rad/s'),('energy_J','系统机械能','J')],
        'assumptions': ['拓扑为浮式风机概念示意，数值计算复用原平台降阶动力学模型。','构件几何不自动参与有限元或 CFD；有效范围、单位及坐标遵循原模型运行记录。'],
        'sources': ['server/schema.py','server/world_design.py'],
    },
}

def design_world(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise DesignError('invalid_payload', '世界设计参数必须是 JSON 对象。')
    if 'source_geometry' in payload and 'engineering_geometry' in payload:
        raise DesignError('conflicting_geometry_sources', '几何只能有一个来源，不能同时传入 source_geometry 与 engineering_geometry。')
    if 'engineering_geometry' in payload:
        from .engineering_design import import_turbine_array_design
        return import_turbine_array_design(payload)
    if 'source_geometry' in payload:
        from .engineering_design import import_engineering_design
        return import_engineering_design(payload)
    allowed = {'prompt','domain','parameters','duration_s','dt_s'}
    if set(payload)-allowed:
        raise DesignError('invalid_payload', '世界设计包含不支持的字段：'+', '.join(sorted(set(payload)-allowed)))
    prompt = payload.get('prompt','')
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>6000:
        raise DesignError('invalid_payload', 'prompt 必须是 1 到 6000 字的非空文本。')
    prompt=prompt.strip()
    domain, routing = _domain(prompt,payload.get('domain'))
    supplied=payload.get('parameters',{})
    if not isinstance(supplied,dict):
        raise DesignError('invalid_parameter', 'parameters 必须是 SI 数值参数对象。')
    spec=PARAMETERS[domain]
    if set(supplied)-set(spec):
        raise DesignError('invalid_parameter', '当前模型不接受参数：'+', '.join(sorted(set(supplied)-set(spec))))
    extracted, prompt_metadata, warnings, parsed_spans = _prompt_parameters(prompt,domain)
    params, metadata = {}, {}
    for key,(default,unit,low,high,label) in spec.items():
        value=supplied.get(key,extracted.get(key,default))
        if isinstance(value,dict):
            if set(value)-{'value','unit'} or value.get('unit',unit)!=unit or 'value' not in value:
                raise DesignError('invalid_parameter', f'{key} 应使用 value 与 SI unit={unit}。')
            value=value['value']
        params[key]=_number(value,key,low,high)
        metadata[key]={'label':label,'unit':unit,'source':'user' if key in supplied else 'prompt' if key in extracted else 'teaching_default','bounds':[low,high]}
        if key in extracted:
            metadata[key]['prompt_input']=prompt_metadata[key]
            if key in supplied and params[key]!=extracted[key]:
                warnings.append(f'{label}以参数区的显式值 {params[key]:g} {unit} 为准，覆盖句子中的 {extracted[key]:g} {unit}。')
    duration=_number(payload.get('duration_s',extracted.get('duration_s',12.)),'duration_s',1.,60.)
    dt=_number(payload.get('dt_s',extracted.get('dt_s',.02)),'dt_s',.005,.05)
    for key,value in [('duration_s',duration),('dt_s',dt)]:
        if key in payload and key in extracted and value!=extracted[key]:
            warnings.append(f'{key} 以显式值 {value:g} s 为准，覆盖句子中的 {extracted[key]:g} s。')
    if domain=='wind_turbine' and dt not in (.005,.01,.02,.025,.05):
        raise DesignError('invalid_parameter','风机原模型 dt_s 支持 0.005、0.01、0.02、0.025、0.05。')
    if domain=='wind_turbine' and not math.isclose(duration*10,round(duration*10),abs_tol=1e-8):
        raise DesignError('invalid_parameter','风机原模型 duration_s 必须为 0.1 秒的整数倍；请显式调整时长。')
    if duration/dt>12000:
        raise DesignError('invalid_parameter','积分步数不得超过 12000。')
    details=DESCRIPTIONS[domain]
    assumptions=list(details['assumptions'])
    defaults=[meta['label'] for meta in metadata.values() if meta['source']=='teaching_default']
    if defaults:
        assumptions.append('未指定参数采用可编辑的教学基线：'+ '、'.join(defaults)+'；不代表实际设备标定值。')
    assumptions.append('只解析已支持的参数名称及单位；解析值和默认值均列在参数区，未绑定数字会单独提示。')
    canonical={'schema':SCHEMA,'prompt':prompt,'domain':domain,'parameters':params,'duration_s':duration,'dt_s':dt}
    design_id='design_'+hashlib.sha256(json.dumps(canonical,ensure_ascii=False,sort_keys=True,allow_nan=False).encode('utf-8')).hexdigest()[:20]
    return {
        **canonical,'id':design_id,'title':details['title'],'status':'designed','source':'wiscomper',
        'parameter_metadata':metadata,'objects':details['objects'],'constraints':details['constraints'],
        'observables':[{'id':ident,'label':label,'unit':unit} for ident,label,unit in details['observables']],
        'assumptions':assumptions,'warnings':warnings,'scene':_scene(domain,params,duration),
        'simulation':{'provider':'physcast','action':'world_simulate','model':details['model'],
                      'parameters':params,'duration_s':duration,'dt_s':dt},
        'design_metadata':{'generator':'wiscomper_bounded_world_design','routing':routing,'paid_model_used':False,
                           'source_files':details['sources'],'scene_evidence':'schematic',
                           'parameter_policy':'explicit_inputs_override_bounded_prompt_parser_then_labelled_defaults',
                           'time_sources':{'duration_s':'user' if 'duration_s' in payload else 'prompt' if 'duration_s' in extracted else 'teaching_default',
                                           'dt_s':'user' if 'dt_s' in payload else 'prompt' if 'dt_s' in extracted else 'teaching_default'},
                           'prompt_parameters':prompt_metadata,
                           'prompt_has_unparsed_numbers':any('尚未绑定' in warning for warning in warnings),
                           'scope':'三个已接入模型族的确定性设计目录；不声称通用语义建模或工程验证。'},
    }

def main() -> int:
    try:
        raw=sys.stdin.buffer.read(MAX_INPUT_BYTES+1)
        if len(raw)>MAX_INPUT_BYTES:
            raise DesignError('payload_too_large','设计请求超过 64 KiB。')
        payload=json.loads(raw.decode('utf-8'))
        response={'ok':True,'data':design_world(payload)}
    except (ValueError,UnicodeError) as exc:
        response={'ok':False,'error':{'code':getattr(exc,'code','invalid_payload'),'message':str(exc)}}
    sys.stdout.buffer.write(json.dumps(response,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8'))
    return 0 if response['ok'] else 2

if __name__=='__main__':
    raise SystemExit(main())
