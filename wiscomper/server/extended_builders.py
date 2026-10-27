"""Small, deterministic mathematical models rendered with the existing scene contract."""
from __future__ import annotations

import math

from .schema import Proposal, Scene
from .builders import BLUE, GOLD, INK, MINT, WHITE, checked_params, control, obj, staged


def _proposal(value):
    return value if isinstance(value, Proposal) else Proposal.model_validate(value)


def _text(ident, text, x, y, **fields):
    return obj(ident, 'text', text=text, x=x, y=y, color=WHITE, font_size=.28, **fields)


def _finish(p, objects, controls, steps, assumptions):
    for item in objects:
        for frame in item.get('frames', []):
            frame['t'] = min(p.duration, max(0., frame['t']))
    return Scene.model_validate(dict(title=p.title, summary=p.summary, duration=p.duration, mode='2d',
        objects=objects, controls=controls, steps=steps, evidence='computed',
        assumptions=list(dict.fromkeys([*p.assumptions, *assumptions]))[-12:]))


def build_riemann(proposal: Proposal | dict) -> Scene:
    """Riemann sums for x squared, with an independent exact area for comparison."""
    p = _proposal(proposal)
    cfg = checked_params(p, {'upper': 2., 'count': 8., 'sample_position': .5},
                         {'upper': (.5, 3.), 'count': (4., 40.), 'sample_position': (0., 1.)})
    if cfg['count'] != int(cfg['count']):
        raise ValueError('分割数量 count 必须是4至40之间的整数。')
    upper, count, alpha, d = cfg['upper'], int(cfg['count']), cfg['sample_position'], p.duration
    dx = upper / count
    samples = [(i + alpha) * dx for i in range(count)]
    estimate = math.fsum(x*x*dx for x in samples)
    exact = upper**3 / 3
    # All supported parameter values share the same physical axes.
    px = lambda x: -5.7 + x * 3.6
    py = lambda y: -2.5 + y * .52
    curve = [[px(upper*i/120), py((upper*i/120)**2)] for i in range(121)]
    objects = [
        obj('axis-x', 'arrow', points=[[-5.7, -2.5], [5.6, -2.5]], stroke='#64748b'),
        obj('axis-y', 'arrow', points=[[-5.7, -2.5], [-5.7, 2.6]], stroke='#64748b'),
    ]
    for i, x in enumerate(samples):
        height = x*x*.52
        start = d*(.12 + .58*i/count)
        # The leftmost left-endpoint rectangle has exactly zero area and is hidden.
        opacity = .32 if height > 0 else 0.
        objects.append(obj(f'rectangle-{i}', 'rect', label=f'第{i+1}段：采样x={x:.4g}，面积={x*x*dx:.5g}',
            x=px((i+.5)*dx), y=-2.5+height/2, width=dx*3.6, height=max(height, .0001),
            color=BLUE, stroke=BLUE, line_width=.012, opacity=0,
            frames=[{'t': start, 'opacity': 0}, {'t': start+d*.4/count, 'opacity': opacity}]))
        objects.append(obj(f'sample-{i}', 'circle', x=px(x), y=py(x*x), radius=.04, color=GOLD, stroke=GOLD, line_width=.01,
            opacity=0, frames=[{'t': start, 'opacity': 0}, {'t': start+d*.4/count, 'opacity': 1}]))
    objects += [
        obj('curve', 'path', points=curve, stroke=MINT, line_width=.04, filled=False,
            draw=0, frames=[{'t': 0, 'draw': 0}, {'t': d*.7, 'draw': 1}]),
        obj('formula', 'formula', latex=r'S_N=\sum_{i=0}^{N-1}[(i+\alpha)\Delta x]^2\Delta x,\quad I=\int_0^b x^2\,dx=\frac{b^3}{3}',
            x=0, y=3.5, font_size=.33, color=WHITE),
        _text('area-readout', f'完整矩形和 {estimate:.5f}    解析面积 {exact:.5f}    误差 {estimate-exact:+.5f}', 0, 2.55),
        _text('settings', f'N = {count}    b = {upper:g}    Δx = {dx:.4f}    采样位置 α = {alpha:g}', 0, -3.25),
        _text('note', '固定坐标尺度：x 为 0–3，y 为 0–9；金点决定矩形高度', 0, -3.8),
    ]
    for x in [0, 1, 2, 3]:
        objects.append(_text(f'x-tick-{x}', str(x), px(x), -2.85))
    for y in [3, 6, 9]:
        objects += [obj(f'y-tick-{y}', 'line', points=[[-5.77, py(y)], [-5.63, py(y)]], stroke='#64748b'),
                    _text(f'y-label-{y}', str(y), -6.12, py(y))]
    controls = [control('upper', '积分上限 b', upper, .5, 3, .1),
                control('count', '分割数量 N', count, 4, 40, 1),
                control('sample_position', '区间内采样位置 α', alpha, 0, 1, .1)]
    steps = staged(d, ['固定函数与坐标', '用矩形近似面积', '比较误差与分割数量'],
        ['只研究 y=x² 在0到b上的面积，坐标不随参数重新缩放。',
         '每段宽度为b/N；α=0、0.5、1分别对应左端、中点和右端采样。',
         '读数为整个分割的矩形和。与独立解析面积b³/3比较，观察加密分割后的误差。'],
        [['curve', 'formula'], ['rectangle-0', 'sample-0'], ['area-readout']])
    return _finish(p, objects, controls, steps, [
        '仅计算固定函数y=x²在[0,b]上的黎曼和，并用解析面积b³/3校验；不是任意函数积分器。',
        'N必须是4至40的整数；α表示每个子区间内的相对采样位置，界面时间只控制矩形出现顺序。',
        '坐标尺度固定覆盖x=0至3、y=0至9；零高度矩形面积为零，不绘制可见填充。'])


def build_refraction(proposal: Proposal | dict) -> Scene:
    """Snell's law and total internal reflection at one ideal planar interface."""
    p = _proposal(proposal)
    cfg = checked_params(p, {'n1': 1., 'n2': 1.5, 'angle': 35.},
                         {'n1': (1., 2.4), 'n2': (1., 2.4), 'angle': (0., 80.)})
    n1, n2, angle, d = cfg['n1'], cfg['n2'], math.radians(cfg['angle']), p.duration
    matched = n1 == n2
    sine = n1*math.sin(angle)/n2
    total_internal = sine > 1 + 1e-12
    transmitted = None if total_internal else math.asin(min(1., sine))
    critical = math.degrees(math.asin(n2/n1)) if n1 > n2 else None
    length = 2.7
    origin = [0., 0.]
    incident = [-length*math.sin(angle), length*math.cos(angle)]
    reflected = [length*math.sin(angle), length*math.cos(angle)]
    arc = lambda first, last, radius: [[radius*math.cos(first+(last-first)*i/32), radius*math.sin(first+(last-first)*i/32)] for i in range(33)]
    objects = [
        obj('medium-1', 'rect', x=0, y=1.4, width=12.6, height=2.8, color=BLUE, stroke=BLUE, opacity=.07),
        obj('medium-2', 'rect', x=0, y=-1.4, width=12.6, height=2.8, color=MINT, stroke=MINT, opacity=.10),
        obj('interface', 'line', points=[[-6.3, 0], [6.3, 0]], stroke=WHITE, line_width=.025),
        obj('normal', 'line', points=[[0, -2.85], [0, 2.85]], stroke='#64748b', line_width=.02),
        obj('incident-ray', 'arrow', points=[incident, origin], stroke=GOLD, line_width=.05,
            draw=0, frames=[{'t': 0, 'draw': 0}, {'t': d*.28, 'draw': 1}]),
        obj('reflected-ray', 'arrow', points=[origin, reflected], stroke=BLUE, line_width=.04,
            draw=0, frames=[{'t': d*.28, 'draw': 0}, {'t': d*.7, 'draw': 1}]),
        obj('incident-angle', 'path', points=arc(math.pi/2, math.pi/2+angle, .68), stroke=GOLD, filled=False),
        obj('incident-marker', 'circle', radius=.09, color=GOLD, x=incident[0], y=incident[1],
            frames=[{'t': 0, 'x': incident[0], 'y': incident[1]}, {'t': d*.28, 'x': 0, 'y': 0},
                    {'t': d*.29, 'opacity': 0}]),
        obj('reflection-marker', 'circle', radius=.075, color=BLUE, opacity=0,
            frames=[{'t': d*.28, 'x': 0, 'y': 0, 'opacity': 1},
                    {'t': d*.7, 'x': reflected[0], 'y': reflected[1]}, {'t': d*.72, 'opacity': 0}]),
        obj('law', 'formula', latex=r'n_1\sin\theta_1=n_2\sin\theta_2,\qquad \theta_{\rm r}=\theta_1',
            y=3.65, font_size=.36, color=WHITE),
        _text('medium-1-label', f'介质1   n₁ = {n1:g}', -4.6, 2.25),
        _text('medium-2-label', f'介质2   n₂ = {n2:g}', -4.6, -2.25),
        _text('incident-readout', f'入射角 {cfg["angle"]:g}°', -4.65, 1.7),
        _text('reflection-readout', f'反射角 {cfg["angle"]:g}°', 4.65, 2.25),
        _text('normal-label', '法线', .42, 2.88),
        _text('boundary-label', '平面界面', 5.45, .3),
        _text('critical-readout', f'临界角 θc = {critical:.2f}°' if critical is not None else '由低折射率进入高折射率，不发生全反射', 0, -3.25),
        _text('optics-note', '角度均相对法线；光点只示意传播方向，不表示速度或能量比例', 0, -3.8),
    ]
    if transmitted is not None:
        endpoint = [length*math.sin(transmitted), -length*math.cos(transmitted)]
        objects += [obj('transmitted-ray', 'arrow', points=[origin, endpoint], stroke=MINT, line_width=.05,
                        draw=0, frames=[{'t': d*.28, 'draw': 0}, {'t': d*.7, 'draw': 1}]),
                    obj('transmitted-angle', 'path', points=arc(-math.pi/2, -math.pi/2+transmitted, .85), stroke=MINT, filled=False),
                    obj('transmission-marker', 'circle', radius=.09, color=MINT, opacity=0,
                        frames=[{'t': d*.28, 'opacity': 1, 'x': 0, 'y': 0},
                                {'t': d*.7, 'x': endpoint[0], 'y': endpoint[1]}, {'t': d*.72, 'opacity': 0}]),
                    _text('result', f'折射角 θ₂ = {math.degrees(transmitted):.2f}°', 4.5, -2.25)]
    else:
        objects.append(_text('result', '全反射：无传播到介质2的折射光线', 0, -1.55))
    if matched:
        objects = [item for item in objects if item['id'] not in {'reflected-ray', 'reflection-marker'}]
        next(item for item in objects if item['id'] == 'reflection-readout')['text'] = '折射率相同：无界面反射'
        next(item for item in objects if item['id'] == 'critical-readout')['text'] = '折射率相同，光线直线透射，不发生全反射'
    controls = [control('n1', '介质1折射率', n1, 1, 2.4, .05), control('n2', '介质2折射率', n2, 1, 2.4, .05),
                control('angle', '入射角', cfg['angle'], 0, 80, 1, '°')]
    steps = staged(d, ['先找到法线与入射角', '计算折射与反射方向', '跨过临界角'],
        ['所有角度都从法线量起，入射光由介质1到达平面界面。',
         '折射方向满足斯涅尔定律，反射角等于入射角。图中没有将线宽或光点数量解释为能量。',
         '仅当n₁>n₂且入射角超过asin(n₂/n₁)时发生全反射；此时没有传播折射光线。'],
        [['normal', 'incident-ray'], ['transmitted-ray' if matched else 'reflected-ray', 'result'], ['critical-readout', 'result']])
    return _finish(p, objects, controls, steps, [
        '理想、均匀、各向同性、无吸收介质的单一平面界面；采用几何光学斯涅尔定律。',
        '不计算光强、菲涅耳系数、偏振、色散、倏逝场或量子效应；全反射时移除传播折射光线，同折射率无界面反射。',
        '画面时间控制解释顺序，光点匀速移动只是路径提示，不代表介质中的真实光速。'])


def queue_schedule(arrival: float, service: float, horizon: float = 24.) -> list[dict]:
    """Deterministic FCFS single-server event schedule, including t=horizon arrivals."""
    jobs = []
    for i in range(math.floor(horizon/arrival + 1e-10)+1):
        arrived = round(i*arrival, 12)
        started = max(arrived, jobs[-1]['end'] if jobs else 0.)
        ended = round(started+service, 12)
        jobs.append({'arrival': arrived, 'start': started, 'end': ended, 'wait': started-arrived})
    return jobs


def build_queue(proposal: Proposal | dict) -> Scene:
    """D/D/1 queue: exact event ordering, fixed 24-second observation window."""
    p = _proposal(proposal)
    cfg = checked_params(p, {'arrival': 1.2, 'service': 1.8}, {'arrival': (.6, 3.), 'service': (.4, 2.4)})
    arrival, service, horizon, d = cfg['arrival'], cfg['service'], 24., p.duration
    jobs = queue_schedule(arrival, service, horizon)
    events = sorted({0., horizon} | {job[key] for job in jobs for key in ['arrival', 'start', 'end'] if job[key] <= horizon})
    objects = [
        obj('waiting-zone', 'rect', x=-4.65, y=.25, width=3.9, height=2.85, color=INK, stroke=BLUE, opacity=.75),
        obj('server', 'rect', x=0, y=.25, width=1.6, height=1.45, color=INK, stroke=GOLD),
        obj('complete-zone', 'rect', x=4.55, y=.25, width=3.9, height=2.85, color=INK, stroke=MINT, opacity=.75),
        _text('waiting-title', '等待区 · 先到先服务', -4.65, 2.05),
        _text('server-title', '单台服务', 0, 2.05),
        _text('complete-title', '已完成', 4.55, 2.05),
        obj('queue-arrow', 'arrow', points=[[-2.55, .25], [-1.05, .25]], stroke=BLUE),
        obj('complete-arrow', 'arrow', points=[[1.05, .25], [2.45, .25]], stroke=MINT),
    ]
    tracks = [[] for _ in jobs]
    for event in events:
        waiting = [i for i, job in enumerate(jobs) if job['arrival'] <= event+1e-10 and event < job['start']-1e-10]
        completed = [i for i, job in enumerate(jobs) if job['end'] <= event+1e-10]
        for i, job in enumerate(jobs):
            if event < job['arrival']-1e-10:
                state = {'x': -6., 'y': 1.3, 'opacity': 0.}
            elif i in waiting:
                rank = waiting.index(i)
                state = {'x': -6.+(rank%6)*.53, 'y': 1.3-(rank//6)*.45, 'opacity': 1.}
            elif i in completed:
                rank = completed.index(i)
                state = {'x': 3.+(rank%6)*.53, 'y': 1.3-(rank//6)*.40, 'opacity': 1.}
            else:
                state = {'x': 0., 'y': .25, 'opacity': 1.}
            time = event/horizon*d
            previous = tracks[i][-1] if tracks[i] else None
            if previous and all(previous[key] == value for key, value in state.items()):
                continue
            if previous and time > previous['t']:
                # Discrete occupancy changes happen at the event, not halfway to it.
                # This tiny preceding key avoids a long interpolated trip through empty space.
                before = time-min(1e-5, (time-previous['t'])/4)
                if before > previous['t']:
                    tracks[i].append({**previous, 't': before})
            tracks[i].append({'t': time, **state})
    for i, (job, frames) in enumerate(zip(jobs, tracks)):
        objects.append(obj(f'customer-{i}', 'circle', label=f'任务{i+1}：到达{job["arrival"]:g}s，开始{job["start"]:g}s，结束{job["end"]:g}s',
            radius=.12, color=GOLD, x=frames[0]['x'], y=frames[0]['y'], opacity=frames[0]['opacity'], frames=frames))
    complete_count = sum(job['end'] <= horizon+1e-10 for job in jobs)
    waiting_count = sum(job['arrival'] <= horizon+1e-10 < job['start'] for job in jobs)
    serving_count = len(jobs)-complete_count-waiting_count
    objects += [
        _text('queue-settings', f'固定到达间隔 {arrival:g} s    固定服务时长 {service:g} s    观察窗口 0–24 s', 0, 3.65),
        _text('queue-readout', f'24秒统计：到达 {len(jobs)}    完成 {complete_count}    服务中 {serving_count}    等待 {waiting_count}', 0, 3.05),
        _text('schedule-label', '前4个任务时间表', -5.05, -1.5),
    ]
    tx = lambda time: -4.45 + min(time, horizon)/horizon*10.4
    for i, job in enumerate(jobs[:4]):
        y = -1.95-i*.38
        objects.append(_text(f'customer-label-{i}', str(i+1), -5., y))
        for kind, start, end, color in [('wait', job['arrival'], job['start'], BLUE), ('service', job['start'], job['end'], GOLD)]:
            if start >= horizon or end <= start:
                continue
            left, right = tx(start), tx(end)
            objects.append(obj(f'{kind}-interval-{i}', 'rect', x=(left+right)/2, y=y, width=right-left, height=.19,
                color=color, stroke=color, label=f'任务{i+1}{"等待" if kind=="wait" else "服务"}：{start:g}–{end:g}s'))
    objects += [obj('time-cursor', 'line', x=tx(0), points=[[0, -3.25], [0, -1.75]], stroke=WHITE, opacity=.7,
                    frames=[{'t': 0, 'x': tx(0)}, {'t': d, 'x': tx(horizon)}]),
                _text('queue-legend', '蓝条：等待  金条：服务  白线：当前模拟时刻；圆点按事件切换位置', 0, -3.9)]
    for t in [0, 6, 12, 18, 24]:
        objects.append(_text(f'time-label-{t}', f'{t}s', tx(t), -3.45))
    controls = [control('arrival', '到达间隔', arrival, .6, 3, .1, 's'), control('service', '服务时长', service, .4, 2.4, .1, 's')]
    steps = staged(d, ['按固定间隔到达', '服务台决定等待', '看清瓶颈与未完成任务'],
        ['从模拟0秒开始到达；一个圆点代表一个任务，始终保持先到先服务。',
         '开始时刻=max(到达时刻,上一任务结束时刻)，结束时刻=开始时刻+服务时长。',
         '观察窗口固定为24秒，末端到达计入统计；尚未完成者保留在等待区或服务台，不强行清空。'],
        [['waiting-zone'], ['server', 'time-cursor'], ['queue-readout', 'complete-zone']])
    return _finish(p, objects, controls, steps, [
        'D/D/1确定性单服务台：固定到达间隔、固定服务时长、先到先服务、无丢弃、无随机性或优先级。',
        '从t=0开始到达，观察窗口固定为0至24秒并包含24秒到达；动画时长均匀映射此窗口。',
        '圆点位置表示离散事件后的状态，切换处至多有1e-5画面秒的插值过渡，不表示真实行走速度。',
        '顶部读数为24秒时的统计；下方只展示前4个任务的等待/服务时间表，不使用M/M/1稳态公式。'])
