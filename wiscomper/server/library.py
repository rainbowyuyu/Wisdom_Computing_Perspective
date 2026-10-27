"""Session-private formula notes, with a small, scientifically scoped catalog."""
from collections import Counter
import json
import re
import time
from typing import Annotated, Literal
import uuid

from fastapi import HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_ITEMS = 200
MAX_IMPORT_BYTES = 6_000_000
Tag = Annotated[str, Field(min_length=1, max_length=24)]
ProjectId = Annotated[str, Field(pattern=r'^[a-f0-9]{32}$')]


def _builtin(key, title, latex, note, tags, sample=None, sample_note=''):
    return dict(id='builtin-'+key, title=title, latex=latex, note=note, tags=tags,
                sample=sample, sample_note=sample_note, favorite=False, archived=False,
                revision=1, builtin=True,
                prompt=f'请解释“{title}”中的变量、适用条件与变化关系，并设计可视化。公式：{latex}。{note}')


BUILTINS = [
    _builtin('quadratic', '二次方程的因式分解', r'x^2-5x+6=(x-2)(x-3)=0',
             '这个方程的根为 2 和 3；因式分解适用于该具体多项式。', ['代数'], 'formula', '示例逐步展示同一个二次方程的变形。'),
    _builtin('sine', '正弦函数', r'y=\sin x',
             '自变量以弧度计；函数周期为 2π，值域为 [−1,1]。', ['函数', '周期'], 'function', '示例展示 sin(x) 的数值采样曲线，可调整纵向倍率。'),
    _builtin('sine-derivative', '正弦函数的导数', r'\frac{d}{dx}\sin x=\cos x',
             'x 以弧度计。导数给出正弦曲线的局部斜率。', ['函数', '微积分']),
    _builtin('square-integral', '平方函数的定积分', r'\int_0^b x^2\,dx=\frac{b^3}{3}',
             '在示例中 b>0，定积分等于曲线与横轴之间的面积。', ['微积分', '面积'], 'riemann', '示例使用 x²，改变上限与矩形数量，比较近似面积和精确值。'),
    _builtin('riemann-sum', '黎曼和', r'\int_a^b f(x)\,dx=\lim_{n\to\infty}\sum_{i=1}^{n}f(\xi_i)\Delta x',
             '等分区间时 Δx=(b−a)/n，ξᵢ 位于第 i 个子区间；此式要求 f 在该区间黎曼可积。', ['微积分', '面积'], 'riemann', '示例是 f(x)=x²、a=0 的特例，并非任意函数积分器。'),
    _builtin('projectile', '无阻力抛体运动', r'x=v_0\cos\theta\,t,\quad y=v_0\sin\theta\,t-\frac12gt^2',
             '点质量从原点出发；重力均匀，忽略空气阻力。', ['力学', '运动'], 'projectile', '示例采用同一解析方程，发射点与落地点等高。'),
    _builtin('projectile-range', '等高抛体的射程', r'R=\frac{v_0^2\sin(2\theta)}{g}',
             '仅用于出发和落地点等高、忽略空气阻力且 g>0 的抛体；发射角在 0° 到 90° 之间。', ['力学', '运动'], 'projectile', '射程由示例的飞行时间与水平速度计算。'),
    _builtin('pendulum', '有阻尼的非线性单摆', r'\ddot\theta+b\dot\theta+\frac{g}{L}\sin\theta=0',
             '无质量刚性摆杆与点质量；b 是角速度阻尼率，单位 s⁻¹。示例以 RK4 数值积分，g=9.81 m/s²。', ['力学', '振动'], 'pendulum', '示例保留 sinθ，可改变摆长、初角和阻尼。'),
    _builtin('pendulum-period', '小角度单摆周期', r'T\approx2\pi\sqrt{\frac{L}{g}}',
             '仅为小振幅、无阻尼单摆的近似周期；大角度和非零阻尼不能直接使用此式。', ['力学', '振动', '周期'], 'pendulum', '可将示例初角调小、阻尼设为 0，观察近似成立的情形。'),
    _builtin('travelling-wave', '向右传播的正弦波', r'y(x,t)=A\sin\!\left(2\pi\left(\frac{x}{\lambda}-ft\right)\right)',
             'A 为位移振幅、λ 为波长、f 为频率；固定位置的质点垂直于传播方向振动，不随波整体前进。', ['波动', '周期'], 'wave', '示例采用相同相位约定，显示质点上下振动。'),
    _builtin('wave-speed', '正弦波的相速度', r'v_{\mathrm{p}}=f\lambda=\frac{\omega}{k}',
             'ω=2πf，k=2π/λ。此式给出单频正弦波的相速度，不一般等于群速度。', ['波动', '周期'], 'wave', '示例可分别调整频率和波长。'),
    _builtin('rotation-field', '平面刚体旋转速度场', r'\mathbf{v}(x,y)=\Omega(-y,x)',
             'Ω 为恒定角速度，正值表示逆时针旋转；是解析速度场，不包含压力、黏性或流固耦合。', ['场', '运动'], 'field', '箭头与粒子运动来自同一解析旋转场。'),
    _builtin('snell', '斯涅尔折射定律', r'n_1\sin\theta_1=n_2\sin\theta_2',
             '角度均从界面法线量起；采用均匀、各向同性介质的几何光学模型。', ['光学', '波动'], 'refraction', '示例计算折射方向和全反射，不计算光强或菲涅耳系数。'),
    _builtin('critical-angle', '全反射临界角', r'\theta_c=\arcsin\!\left(\frac{n_2}{n_1}\right),\quad n_1>n_2',
             '光从介质 1 射向介质 2；入射角大于临界角时发生全反射，临界处折射光沿界面传播。', ['光学', '波动'], 'refraction', '改变折射率与入射角，可跨过全反射条件。'),
    _builtin('queue-wait', '确定性单服务台的等待递推', r'W_{n+1}=\max(0,W_n+s-a),\quad W_0=0',
             '固定到达间隔 a>0、固定服务时长 s>0、先到先服务、初始空队列。没有随机到达或随机服务。', ['排队', '过程'], 'queue', '示例观察固定 24 秒窗口；使用 D/D/1 模型。'),
    _builtin('queue-load', '确定性队列的负载比', r'\rho=\frac{s}{a}',
             '在初始空队列、固定间隔 a 和固定服务时长 s 下，ρ≤1 不累积等待；ρ>1 时等待随到达次数增长。该结论不直接推广到随机队列的临界情形。', ['排队', '过程'], 'queue', '示例展示有限 24 秒内的等待与完成情况。'),
]


class FormulaInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    title: str = Field(default='', max_length=120)
    latex: str = Field(min_length=1, max_length=4000)
    note: str = Field(default='', max_length=2000)
    tags: list[Tag] = Field(default_factory=list, max_length=8)
    project_id: ProjectId | None = None
    favorite: bool = False
    archived: bool = False

    @field_validator('title', 'latex', 'note')
    @classmethod
    def plain_text(cls, value):
        if any(ord(c) < 32 and c not in '\n\r\t' for c in value):
            raise ValueError('内容中包含不支持的控制字符。')
        value.encode('utf-8')
        return value.strip()

    @field_validator('tags')
    @classmethod
    def clean_tags(cls, value):
        cleaned = []
        for tag in value:
            if not tag.strip() or any(ord(c) < 32 for c in tag):
                raise ValueError('标签不能为空或含控制字符。')
            tag = tag.strip()
            tag.encode('utf-8')
            if tag not in cleaned:
                cleaned.append(tag)
        return cleaned

    @model_validator(mode='after')
    def content(self):
        if not self.latex:
            raise ValueError('公式不能为空。')
        if not self.title:
            self.title = (self.note.splitlines()[0] if self.note else '未命名公式')[:120]
        return self


class FormulaPatch(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected_revision: int = Field(ge=1, le=2_147_483_647)
    title: str | None = Field(default=None, max_length=120)
    latex: str | None = Field(default=None, min_length=1, max_length=4000)
    note: str | None = Field(default=None, max_length=2000)
    tags: list[Tag] | None = Field(default=None, max_length=8)
    project_id: ProjectId | None = None
    favorite: bool | None = None
    archived: bool | None = None

    @model_validator(mode='after')
    def explicit_fields(self):
        changed = self.model_fields_set - {'expected_revision'}
        if not changed or any(getattr(self, key) is None for key in changed - {'project_id'}):
            raise ValueError('请提供要修改的字段；只有关联项目可以设为空。')
        return self


class ImportItem(FormulaInput):
    # Legacy list rows include these fields. They never establish local identity.
    id: Annotated[str, Field(max_length=128)] | Annotated[int, Field(ge=0, le=2**63-1)] | None = None
    user_id: str | None = Field(default=None, max_length=128)
    created_at: str | None = Field(default=None, max_length=64)
    solution_title: None = None
    step_count: None = None
    video_url: None = None


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    items: list[ImportItem] = Field(max_length=MAX_ITEMS)
    format: Literal['wisdom-formulas'] = 'wisdom-formulas'
    version: Literal[1] = 1


def formula_public(item):
    allowed = ('id', 'title', 'latex', 'note', 'tags', 'project_id', 'favorite',
               'archived', 'revision', 'created', 'updated')
    return {**{key: item[key] for key in allowed if key in item}, 'builtin': False}


def saved_items(store, owner, *, include_archived=False):
    items = [formula_public(item) for item in store.list('formula', owner, limit=MAX_ITEMS)]
    return items if include_archived else [item for item in items if not item['archived']]


def _check_project(db, owner, project_id):
    if project_id and not db.execute("SELECT 1 FROM records WHERE kind='project' AND id=? AND owner=?", (project_id, owner)).fetchone():
        raise HTTPException(404, '关联项目不存在或不属于当前会话。')


def _content_key(item):
    return (item['title'], item['latex'], item['note'], tuple(sorted(item['tags'])), item.get('project_id'))


def _insert_items(store, owner, inputs, *, deduplicate=False):
    with store.lock, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        count = db.execute("SELECT COUNT(*) FROM records WHERE kind='formula' AND owner=?", (owner,)).fetchone()[0]
        for data in inputs:
            _check_project(db, owner, data.get('project_id'))
        known = {}
        if deduplicate:
            rows = db.execute("SELECT payload FROM records WHERE kind='formula' AND owner=? ORDER BY updated DESC LIMIT ?", (owner, MAX_ITEMS)).fetchall()
            for row in rows:
                item = json.loads(row[0])
                known.setdefault(_content_key(item), item)
        now = time.time()
        items, inserted = [], 0
        for data in inputs:
            key = _content_key(data)
            if deduplicate and key in known:
                items.append(known[key])
                continue
            if count + inserted >= MAX_ITEMS:
                raise HTTPException(409, f'当前会话最多保存 {MAX_ITEMS} 条公式（包括归档）；可编辑已有条目，或导出备份。')
            item = dict(**data, id=uuid.uuid4().hex, owner=owner, revision=1, created=now, updated=now)
            store._write(db, 'formula', item)
            known[key] = item
            items.append(item)
            inserted += 1
    return [formula_public(item) for item in items], inserted


def install_library(app, store_getter, owner_fn):
    @app.get('/api/library')
    def list_formulas(request: Request, q: Annotated[str, Query(max_length=200)] = '',
                      scope: Literal['all', 'saved', 'builtin', 'archived'] = 'all'):
        owner = owner_fn(request)
        items = []
        if scope in {'all', 'builtin'}:
            items.extend(dict(item) for item in BUILTINS)
        if scope != 'builtin':
            items.extend(item for item in saved_items(store_getter(), owner, include_archived=True)
                         if bool(item['archived']) == (scope == 'archived'))
        terms = q.casefold().split()
        if terms:
            items = [item for item in items if all(term in '\n'.join((item['title'], item['latex'], item['note'], *item['tags'])).casefold() for term in terms)]
        items.sort(key=lambda item: (not item['favorite'], item['builtin'], -item.get('updated', 0), item['id']))
        counts = Counter(tag for item in items for tag in item['tags'])
        topics = [dict(id=tag, label=tag, count=count) for tag, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))]
        return dict(items=items, topics=topics, limits=dict(items=MAX_ITEMS, import_items=MAX_ITEMS))

    @app.post('/api/library', status_code=201)
    def create_formula(request: Request, data: FormulaInput):
        items, _ = _insert_items(store_getter(), owner_fn(request), [data.model_dump()])
        return {'item': items[0]}

    @app.get('/api/library/export')
    def export_formulas(request: Request):
        items = saved_items(store_getter(), owner_fn(request), include_archived=True)
        fields = FormulaInput.model_fields
        payload = dict(format='wisdom-formulas', version=1,
                       items=[{key: item[key] for key in fields if key in item} for item in items])
        return JSONResponse(payload, headers={'Content-Disposition': 'attachment; filename="wisdom-formulas.json"'})

    @app.post('/api/library/import', status_code=201)
    async def import_formulas(request: Request, data: ImportRequest):
        owner = owner_fn(request)
        if len(await request.body()) > MAX_IMPORT_BYTES:
            raise HTTPException(413, '导入文件最多 6 MB。')
        fields = FormulaInput.model_fields
        inputs = [{key: value for key, value in item.model_dump().items() if key in fields} for item in data.items]
        items, inserted = _insert_items(store_getter(), owner, inputs, deduplicate=True)
        return dict(items=items, imported=inserted, skipped=len(items)-inserted)

    @app.patch('/api/library/{ident}')
    def edit_formula(ident: str, request: Request, data: FormulaPatch):
        owner = owner_fn(request)
        if not re.fullmatch(r'[a-f0-9]{32}', ident):
            raise HTTPException(404, '此公式不可修改；内置公式可复制到我的公式。')
        store = store_getter()
        with store.lock, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT payload FROM records WHERE kind='formula' AND id=? AND owner=?", (ident, owner)).fetchone()
            if not row:
                raise HTTPException(404, '公式不存在或不属于当前会话。')
            current = json.loads(row[0])
            if current['revision'] != data.expected_revision:
                raise HTTPException(409, '公式已有新版本，请刷新后继续；本次修改没有覆盖已有内容。')
            updates = data.model_dump(exclude_unset=True, exclude={'expected_revision'})
            candidate = {key: current[key] for key in FormulaInput.model_fields if key in current}
            candidate.update(updates)
            try:
                checked = FormulaInput.model_validate(candidate).model_dump()
            except ValueError:
                raise HTTPException(422, '公式内容或标签格式不正确。') from None
            _check_project(db, owner, checked['project_id'])
            current.update(checked, revision=current['revision']+1, updated=time.time())
            store._write(db, 'formula', current)
        return {'item': formula_public(current)}
