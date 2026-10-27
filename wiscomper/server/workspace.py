"""Private workspace preferences, study records and ordered teaching packs."""
import hashlib
import json
import re
import time
from typing import Annotated, Literal
import uuid

from fastapi import HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .builders import SAMPLES
from .library import BUILTINS

MAX_LEARNING = 300
MAX_PACKS = 40
MAX_PACK_ITEMS = 40
MAX_REVIEWS = 100
LEARNING_EXPORT_BUDGET = 4_500_000
PACK_EXPORT_BUDGET = 1_300_000
ID = Annotated[str, Field(pattern=r'^[a-f0-9]{32}$')]
RefId = Annotated[str, Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')]
Tag = Annotated[str, Field(min_length=1, max_length=24)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
SAMPLE_MAP = {item['id']: item for item in SAMPLES}
FORMULA_MAP = {item['id']: item for item in BUILTINS}


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    @field_validator('*', mode='before')
    @classmethod
    def clean_text(cls, value):
        if isinstance(value, str):
            if any(ord(c) < 32 and c not in '\n\r\t' for c in value):
                raise ValueError('内容包含不支持的控制字符。')
            value.encode('utf-8')
        return value


class Preferences(Strict):
    theme: Literal['system', 'light', 'dark'] = 'system'
    autoplay: bool = True
    reduced_motion: bool = False
    default_speed: Finite = Field(default=1, ge=.25, le=2)
    default_input: Literal['text', 'formula', 'image'] = 'text'
    graph_motion: bool = True
    graph_labels: bool = True
    floating_visible: bool = True
    floating_size: int = Field(default=64, ge=44, le=96)
    floating_opacity: Finite = Field(default=1, ge=.35, le=1)
    floating_x: Finite | None = Field(default=None, ge=0, le=1)
    floating_y: Finite | None = Field(default=None, ge=0, le=1)
    tutorial_completed: bool = False


class PreferenceRequest(Strict):
    expected_revision: int = Field(ge=0, le=2_147_483_647)
    preferences: Preferences


class StudyInput(Strict):
    kind: Literal['favorite', 'watch_later', 'wrongbook', 'note']
    title: str = Field(min_length=1, max_length=120)
    note: str = Field(default='', max_length=4000)
    problem: str = Field(default='', max_length=4000)
    answer: str = Field(default='', max_length=4000)
    tags: list[Tag] = Field(default_factory=list, max_length=8)
    project_id: ID | None = None
    formula_id: RefId | None = None
    sample_id: RefId | None = None
    time_sec: Finite | None = Field(default=None, ge=0, le=86_400)
    archived: bool = False

    @field_validator('title', 'note', 'problem', 'answer')
    @classmethod
    def trim(cls, value):
        return value.strip()

    @field_validator('tags')
    @classmethod
    def tags_valid(cls, value):
        result = []
        for tag in value:
            tag.encode('utf-8')
            if not tag.strip() or any(ord(c) < 32 for c in tag):
                raise ValueError('标签不能为空或含控制字符。')
            if tag.strip() not in result:
                result.append(tag.strip())
        return result

    @model_validator(mode='after')
    def valid(self):
        if not self.title or self.kind == 'wrongbook' and not self.problem:
            raise ValueError('请填写标题；错题必须有题目。')
        if self.time_sec is not None and not self.project_id:
            raise ValueError('时间戳必须关联一个项目。')
        return self


class StudyPatch(Strict):
    expected_revision: int = Field(ge=1, le=2_147_483_647)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=4000)
    problem: str | None = Field(default=None, max_length=4000)
    answer: str | None = Field(default=None, max_length=4000)
    tags: list[Tag] | None = Field(default=None, max_length=8)
    project_id: ID | None = None
    formula_id: RefId | None = None
    sample_id: RefId | None = None
    time_sec: Finite | None = Field(default=None, ge=0, le=86_400)
    archived: bool | None = None

    @model_validator(mode='after')
    def present(self):
        changed = self.model_fields_set - {'expected_revision'}
        nullable = {'project_id', 'formula_id', 'sample_id', 'time_sec'}
        if not changed or any(getattr(self, key) is None for key in changed-nullable):
            raise ValueError('请提供有效修改字段。')
        return self


class ReviewInput(Strict):
    expected_revision: int = Field(ge=1, le=2_147_483_647)
    grade: Literal['again', 'hard', 'good', 'easy']
    note: str = Field(default='', max_length=2000)


class Snapshot(Strict):
    title: str = Field(min_length=1, max_length=120)
    note: str = Field(default='', max_length=4000)
    latex: str = Field(default='', max_length=4000)
    problem: str = Field(default='', max_length=4000)
    answer: str = Field(default='', max_length=4000)
    prompt: str = Field(default='', max_length=2000)
    tags: list[Tag] = Field(default_factory=list, max_length=8)

    @model_validator(mode='after')
    def bounded_plaintext(self):
        if not self.title.strip():
            raise ValueError('快照标题不能为空。')
        self.tags = StudyInput.tags_valid(self.tags)
        return self


class PackItem(Strict):
    kind: Literal['project', 'formula', 'sample', 'learning']
    id: RefId | None = None
    note: str = Field(default='', max_length=2000)
    snapshot: Snapshot | None = None

    @model_validator(mode='after')
    def reference_or_snapshot(self):
        if not self.id and not self.snapshot:
            raise ValueError('学习材料需要引用或便携文本快照。')
        return self


class Lesson(Strict):
    audience: str = Field(default='', max_length=160)
    duration: int = Field(default=45, ge=1, le=480)
    objectives: str = Field(default='', max_length=4000)
    key_points: str = Field(default='', max_length=4000)
    preparation: str = Field(default='', max_length=4000)
    procedure: str = Field(default='', max_length=8000)
    exercises: str = Field(default='', max_length=4000)
    reflection: str = Field(default='', max_length=4000)


class PackInput(Strict):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=2000)
    lesson: Lesson = Field(default_factory=Lesson)
    items: list[PackItem] = Field(default_factory=list, max_length=MAX_PACK_ITEMS)
    archived: bool = False

    @field_validator('title')
    @classmethod
    def title_valid(cls, value):
        if not value.strip():
            raise ValueError('课包标题不能为空。')
        return value.strip()


class PackPatch(Strict):
    expected_revision: int = Field(ge=1, le=2_147_483_647)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    lesson: Lesson | None = None
    items: list[PackItem] | None = Field(default=None, max_length=MAX_PACK_ITEMS)
    archived: bool | None = None

    @model_validator(mode='after')
    def present(self):
        changed = self.model_fields_set - {'expected_revision'}
        if not changed or any(getattr(self, key) is None for key in changed):
            raise ValueError('请提供有效修改字段。')
        return self


class PackImport(Strict):
    format: Literal['wiscomper-course-pack']
    version: Literal[1]
    pack: PackInput


class StudyImport(Strict):
    format: Literal['wiscomper-learning']
    version: Literal[1]
    items: list[StudyInput] = Field(max_length=MAX_LEARNING)


def public(value):
    return {key: item for key, item in value.items() if key != 'owner' and not key.startswith('_')}


def _record(db, kind, ident, owner):
    if not re.fullmatch(r'[a-f0-9]{32}', ident):
        raise HTTPException(404, '记录不存在或不属于当前账户。')
    row = db.execute('SELECT payload FROM records WHERE kind=? AND id=? AND owner=?', (kind, ident, owner)).fetchone()
    if not row:
        raise HTTPException(404, '记录不存在或不属于当前账户。')
    return json.loads(row[0])


def _reference(db, kind, ident, owner):
    """Only descriptive columns leave a project record; never load scene frames."""
    if kind == 'sample':
        item = SAMPLE_MAP.get(ident)
        if not item:
            raise HTTPException(404, '示例不存在。')
        return Snapshot(title=item['title'], note=item['description'], prompt=item['prompt']).model_dump()
    if kind == 'formula' and ident in FORMULA_MAP:
        item = FORMULA_MAP[ident]
    elif kind == 'project':
        if not re.fullmatch(r'[a-f0-9]{32}', ident):
            raise HTTPException(404, '关联项目不存在或不属于当前账户。')
        row = db.execute("""SELECT substr(json_extract(payload,'$.title'),1,120),
            substr(json_extract(payload,'$.prompt'),1,2000), substr(json_extract(payload,'$.scene.summary'),1,4000)
            FROM records WHERE kind='project' AND id=? AND owner=?""", (ident, owner)).fetchone()
        if not row:
            raise HTTPException(404, '关联项目不存在或不属于当前账户。')
        return Snapshot(title=row[0] or '未命名作品', prompt=row[1] or '', note=row[2] or '').model_dump()
    else:
        item = _record(db, 'learning' if kind == 'learning' else 'formula', ident, owner)
    return Snapshot(**{key: item[key] for key in Snapshot.model_fields if key in item}).model_dump()


def _study_links(db, data, owner):
    for field, kind in [('project_id', 'project'), ('formula_id', 'formula'), ('sample_id', 'sample')]:
        if data.get(field):
            _reference(db, kind, data[field], owner)
    if data.get('time_sec') is not None:
        row = db.execute("SELECT json_extract(payload,'$.scene.duration') FROM records WHERE kind='project' AND id=? AND owner=?", (data['project_id'], owner)).fetchone()
        if not row or not isinstance(row[0], (float, int)) or data['time_sec'] > row[0]:
            raise HTTPException(422, '时间戳超出关联场景的时长。')


def _pack_items(db, inputs, owner):
    items = []
    for entry in inputs:
        entry = dict(entry)
        if entry.get('id'):
            entry['snapshot'] = _reference(db, entry['kind'], entry['id'], owner)
        items.append(entry)
    return items


def _new_record(store, db, kind, owner, data, limit):
    count = db.execute('SELECT COUNT(*) FROM records WHERE kind=? AND owner=?', (kind, owner)).fetchone()[0]
    if count >= limit:
        raise HTTPException(409, f'当前最多保存 {limit} 条此类记录（含归档），可编辑已有记录或导出备份。')
    now = time.time()
    item = dict(**data, id=uuid.uuid4().hex, owner=owner, revision=1, created=now, updated=now)
    store._write(db, kind, item)
    return item


def _check_revision(item, expected):
    if item['revision'] != expected:
        raise HTTPException(409, '记录已有新版本，请刷新后继续；本次修改没有覆盖已有内容。')


def _hash(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _study_base(data):
    return {key: data[key] for key in StudyInput.model_fields if key in data}


def _study_new(data):
    return dict(**data, status='new', review_count=0, interval_days=0, next_review_at=time.time() if data['kind'] == 'wrongbook' else None, reviews=[])


def _portable_study(item):
    data = _study_base(item)
    # Private identifiers cannot link to another user's project after import.
    data.update(project_id=None, formula_id=item.get('formula_id') if item.get('formula_id') in FORMULA_MAP else None, time_sec=None)
    return data


def _portable_pack(item):
    portable = {key: item[key] for key in PackInput.model_fields}
    portable['items'] = [{**entry, 'id': entry.get('id') if entry['kind'] == 'sample' or entry.get('id') in FORMULA_MAP else None} for entry in item['items']]
    return portable


def _learning_rows(db, owner):
    # Lists/exports never materialize the 100-note review history of each row.
    rows = db.execute("SELECT json_remove(payload,'$.reviews') FROM records WHERE kind='learning' AND owner=? ORDER BY updated DESC LIMIT ?",
                      (owner, MAX_LEARNING)).fetchall()
    return [json.loads(row[0]) for row in rows]


def _check_learning_budget(db, owner):
    payload = dict(format='wiscomper-learning', version=1, items=[_portable_study(item) for item in _learning_rows(db, owner)])
    if len(json.dumps(payload, ensure_ascii=False, indent=2).encode()) > LEARNING_EXPORT_BUDGET:
        raise HTTPException(409, '学习资料内容已达到可迁移容量上限，请精简已有记录后再保存。')


def _check_pack_budget(item):
    payload = dict(format='wiscomper-course-pack', version=1, pack=_portable_pack(item))
    if len(json.dumps(payload, ensure_ascii=False, indent=2).encode()) > PACK_EXPORT_BUDGET:
        raise HTTPException(409, '课包内容超过可迁移容量，请减少材料或精简笔记后保存。')


RELEASES = [
    {'version': 'harness-1.2', 'date': '2026-10-23', 'title': '个人工作台与学习资料', 'channel': 'harness',
     'changes': ['熟悉的三维星图回来了。拖动、缩放，沿着公式和作品之间的联系继续探索。', '收藏、稍后看、笔记和错题本集中到「我的空间」，教案与课包也能一起整理。', '悬浮球、播放和深浅主题可以按习惯调整，七步教程随时重看。', '新增手写草图与全站搜索；保存和切换页面时更稳妥，窄窗口也能顺手操作。']},
    {'version': 'harness-1.1', 'date': '2026-10-23', 'title': '智算视界独立工作台', 'channel': 'harness',
     'changes': ['文字、公式与图片创作，受控 DSH 场景工具与二维、三维预览。', '公式库、知识图谱、项目版本回看与恢复、视频导出。', 'GitHub 登录与正式域名的公开介绍、站点地图和检索元数据。']},
    {'version': '0.4.7', 'date': '2026-09-19', 'title': '旧站：邮箱验证与账户设置', 'channel': 'legacy',
     'source': '旧站 static/docs/update.md，节选；不是本工程已实现声明',
     'changes': ['旧站记录了邮箱验证码、密码找回与账户设置优化。本工程采用独立 GitHub 身份，不复制原有密码或邮箱服务。']},
    {'version': '0.4.4', 'date': '2026-09-17', 'title': '旧站：分步解题与学习资料联动', 'channel': 'legacy',
     'source': '旧站 static/docs/update.md，节选；不是本工程已实现声明',
     'changes': ['旧站加入分步题解、教案课包、错题复习、教学视频笔记，以及相关搜索和图谱入口。', '本工程沿用资料关联的使用方式，将材料连接到自己的项目、公式和示例。']},
    {'version': '0.4.3', 'date': '2026-03-06', 'title': '旧站：成就与移动端联动', 'channel': 'legacy',
     'source': '旧站 static/docs/update.md，节选；不是本工程已实现声明',
     'changes': ['独立徽章、成就墙和移动端展示。当前成就统计采用本工程真实记录，不把浏览量或条目数量解释为掌握度。']},
    {'version': '0.4.1', 'date': '2026-02-27', 'title': '旧站：知识图谱与智算星云', 'channel': 'legacy',
     'source': '旧站 static/docs/update.md，节选；不是本工程已实现声明',
     'changes': ['首页知识图谱连接站内工具，星云入口展示学习进度与成就。']},
    {'version': '0.3.6', 'date': '2026-02-20', 'title': '旧站：智能体与个人设置', 'channel': 'legacy',
     'source': '旧站 static/docs/update.md，节选；不是本工程已实现声明',
     'changes': ['多步骤任务与按用户保存的设置，教程随功能扩充。']},
]


def install_workspace(app, store_getter, owner_fn):
    @app.get('/api/preferences')
    def get_preferences(request: Request):
        owner = owner_fn(request)
        rows = store_getter().list('preferences', owner, limit=1)
        item = rows[0] if rows else None
        return dict(preferences=Preferences(**(item['preferences'] if item else {})).model_dump(), revision=item['revision'] if item else 0)

    @app.put('/api/preferences')
    def put_preferences(request: Request, data: PreferenceRequest):
        owner, store = owner_fn(request), store_getter()
        with store.lock, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute("SELECT payload FROM records WHERE kind='preferences' AND owner=? ORDER BY updated DESC LIMIT 1", (owner,)).fetchall()
            current = json.loads(rows[0][0]) if rows else None
            _check_revision(current or {'revision': 0}, data.expected_revision)
            preferences = Preferences(**(current['preferences'] if current else {})).model_dump()
            preferences.update(data.preferences.model_dump(exclude_unset=True))
            if current:
                current.update(preferences=preferences, revision=current['revision']+1, updated=time.time())
                store._write(db, 'preferences', current)
            else:
                current = _new_record(store, db, 'preferences', owner, {'preferences': preferences}, 10)
        return dict(preferences=current['preferences'], revision=current['revision'])

    @app.get('/api/learning')
    def list_learning(request: Request, kind: Literal['all', 'favorite', 'watch_later', 'wrongbook', 'note'] = 'all',
                      status: Literal['all', 'due', 'new', 'reviewing', 'mastered', 'archived'] = 'all',
                      q: Annotated[str, Query(max_length=200)] = ''):
        owner = owner_fn(request)
        with store_getter().connect() as db:
            rows = _learning_rows(db, owner)
        now = time.time()
        active = [item for item in rows if not item['archived']]
        due = lambda item: item['kind'] == 'wrongbook' and item['status'] != 'mastered' and (item.get('next_review_at') or 0) <= now
        stats = dict(total=len(active), due=sum(due(item) for item in active), mastered=sum(item['status'] == 'mastered' for item in active),
                     reviews=sum(item['review_count'] for item in rows), archived=len(rows)-len(active))
        rows = [item for item in rows if (kind == 'all' or item['kind'] == kind) and bool(item['archived']) == (status == 'archived')]
        if status == 'due': rows = [item for item in rows if due(item)]
        elif status in {'new', 'reviewing', 'mastered'}: rows = [item for item in rows if item['status'] == status]
        terms = q.casefold().split()
        if terms:
            rows = [item for item in rows if all(term in '\n'.join((item['title'], item['note'], item['problem'], item['answer'], *item['tags'])).casefold() for term in terms)]
        summaries = [{key: value for key, value in public(item).items() if key != 'reviews'} for item in rows]
        return dict(items=summaries, stats=stats, limits=dict(items=MAX_LEARNING, reviews=MAX_REVIEWS))

    @app.post('/api/learning', status_code=201)
    def add_learning(request: Request, data: StudyInput):
        owner, store = owner_fn(request), store_getter()
        checked = data.model_dump()
        with store.lock, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            _study_links(db, checked, owner)
            # Collecting the same project/sample/formula twice is idempotent for saved lists.
            if data.kind in {'favorite', 'watch_later'} and any(checked.get(key) for key in ('project_id', 'formula_id', 'sample_id')):
                for item in _learning_rows(db, owner):
                    if item['kind'] == data.kind and all(item.get(key) == checked.get(key) for key in ('project_id', 'formula_id', 'sample_id')):
                        return dict(item=public(item), duplicate=True)
            item = _new_record(store, db, 'learning', owner, _study_new(checked), MAX_LEARNING)
            _check_learning_budget(db, owner)
        return dict(item=public(item), duplicate=False)

    @app.get('/api/learning/export')
    def export_learning(request: Request):
        owner = owner_fn(request)
        with store_getter().connect() as db:
            rows = _learning_rows(db, owner)
        return JSONResponse(dict(format='wiscomper-learning', version=1, items=[_portable_study(item) for item in rows]),
                            headers={'Content-Disposition': 'attachment; filename="wiscomper-learning.json"'})

    @app.post('/api/learning/import', status_code=201)
    async def import_learning(request: Request, data: StudyImport):
        owner, store = owner_fn(request), store_getter()
        if len(await request.body()) > 5_000_000:
            raise HTTPException(413, '学习资料导入最多 5 MB。')
        imported, skipped = [], 0
        with store.lock, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            known = {_hash(_portable_study(item)) for item in _learning_rows(db, owner)}
            for entry in data.items:
                checked = entry.model_dump()
                _study_links(db, checked, owner)
                fingerprint = _hash(_portable_study(checked))
                if fingerprint in known:
                    skipped += 1
                    continue
                item = _new_record(store, db, 'learning', owner, _study_new(checked), MAX_LEARNING)
                imported.append(public(item)); known.add(fingerprint)
            _check_learning_budget(db, owner)
        return dict(items=imported, imported=len(imported), skipped=skipped)

    @app.get('/api/learning/{ident}')
    def get_learning(ident: str, request: Request):
        with store_getter().connect() as db:
            return {'item': public(_record(db, 'learning', ident, owner_fn(request)))}

    @app.patch('/api/learning/{ident}')
    def edit_learning(ident: str, request: Request, data: StudyPatch):
        owner, store = owner_fn(request), store_getter()
        with store.lock, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            item = _record(db, 'learning', ident, owner)
            _check_revision(item, data.expected_revision)
            checked = _study_base(item)
            checked.update(data.model_dump(exclude_unset=True, exclude={'expected_revision'}))
            try: checked = StudyInput.model_validate(checked).model_dump()
            except ValueError: raise HTTPException(422, '学习资料内容格式不正确。') from None
            _study_links(db, checked, owner)
            item.update(checked, revision=item['revision']+1, updated=time.time())
            store._write(db, 'learning', item)
            _check_learning_budget(db, owner)
        return {'item': public(item)}

    @app.post('/api/learning/{ident}/review')
    def review_learning(ident: str, request: Request, data: ReviewInput):
        owner, store = owner_fn(request), store_getter()
        with store.lock, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            item = _record(db, 'learning', ident, owner)
            _check_revision(item, data.expected_revision)
            if item['kind'] != 'wrongbook' or item['archived']:
                raise HTTPException(409, '只有未归档的错题可以记录复习。')
            now, previous = time.time(), item['interval_days']
            interval = {'again': 0, 'hard': 1, 'good': min(90, max(3, previous*2)), 'easy': min(180, max(7, previous*3))}[data.grade]
            status = 'mastered' if data.grade == 'easy' else 'reviewing'
            review = dict(grade=data.grade, note=data.note, reviewed_at=now, interval_days=interval)
            item.update(status=status, review_count=item['review_count']+1, interval_days=interval,
                        next_review_at=None if status == 'mastered' else now+(600 if data.grade == 'again' else interval*86400),
                        reviews=(item['reviews']+[review])[-MAX_REVIEWS:], revision=item['revision']+1, updated=now)
            store._write(db, 'learning', item)
        return {'item': public(item)}

    @app.get('/api/course-packs')
    def list_packs(request: Request, archived: bool = False):
        owner = owner_fn(request)
        with store_getter().connect() as db:
            rows = db.execute("""SELECT id,json_extract(payload,'$.title'),json_extract(payload,'$.description'),
                json_extract(payload,'$.revision'),updated,json_array_length(payload,'$.items')
                FROM records WHERE kind='course-pack' AND owner=? AND json_extract(payload,'$.archived')=?
                ORDER BY updated DESC LIMIT ?""", (owner, int(archived), MAX_PACKS)).fetchall()
        return dict(items=[dict(id=row[0], title=row[1], description=row[2], archived=archived, revision=row[3], updated=row[4], item_count=row[5])
                           for row in rows], limits=dict(packs=MAX_PACKS, items=MAX_PACK_ITEMS))

    @app.post('/api/course-packs', status_code=201)
    def add_pack(request: Request, data: PackInput):
        owner, store = owner_fn(request), store_getter()
        checked = data.model_dump()
        with store.lock, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            checked['items'] = _pack_items(db, checked['items'], owner)
            _check_pack_budget(checked)
            item = _new_record(store, db, 'course-pack', owner, {**checked, '_portable_hash': _hash(_portable_pack(checked))}, MAX_PACKS)
        return {'item': public(item)}

    @app.post('/api/course-packs/import', status_code=201)
    async def import_pack(request: Request, data: PackImport):
        owner, store = owner_fn(request), store_getter()
        if len(await request.body()) > 1_500_000:
            raise HTTPException(413, '课包导入最多 1.5 MB。')
        checked = data.pack.model_dump()
        with store.lock, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            checked['items'] = _pack_items(db, checked['items'], owner)
            _check_pack_budget(checked)
            fingerprint = _hash(_portable_pack(checked))
            duplicate = db.execute("SELECT id FROM records WHERE kind='course-pack' AND owner=? AND json_extract(payload,'$._portable_hash')=? LIMIT 1", (owner, fingerprint)).fetchone()
            if duplicate:
                return dict(item=public(_record(db, 'course-pack', duplicate[0], owner)), imported=0, skipped=1)
            item = _new_record(store, db, 'course-pack', owner, {**checked, '_portable_hash': fingerprint}, MAX_PACKS)
        return dict(item=public(item), imported=1, skipped=0)

    @app.get('/api/course-packs/{ident}')
    def get_pack(ident: str, request: Request):
        with store_getter().connect() as db:
            return {'item': public(_record(db, 'course-pack', ident, owner_fn(request)))}

    @app.patch('/api/course-packs/{ident}')
    def edit_pack(ident: str, request: Request, data: PackPatch):
        owner, store = owner_fn(request), store_getter()
        with store.lock, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            item = _record(db, 'course-pack', ident, owner)
            _check_revision(item, data.expected_revision)
            checked = {key: item[key] for key in PackInput.model_fields}
            checked.update(data.model_dump(exclude_unset=True, exclude={'expected_revision'}))
            try: checked = PackInput.model_validate(checked).model_dump()
            except ValueError: raise HTTPException(422, '课包格式不正确。') from None
            if 'items' in data.model_fields_set:
                checked['items'] = _pack_items(db, checked['items'], owner)
            _check_pack_budget(checked)
            item.update(checked, _portable_hash=_hash(_portable_pack(checked)), revision=item['revision']+1, updated=time.time())
            store._write(db, 'course-pack', item)
        return {'item': public(item)}

    @app.get('/api/course-packs/{ident}/export')
    def export_pack(ident: str, request: Request):
        with store_getter().connect() as db:
            item = _record(db, 'course-pack', ident, owner_fn(request))
        portable = _portable_pack(item)
        return JSONResponse(dict(format='wiscomper-course-pack', version=1, pack=portable),
                            headers={'Content-Disposition': 'attachment; filename="wiscomper-course-pack.json"'})

    @app.get('/api/achievements')
    def achievements(request: Request):
        owner, store = owner_fn(request), store_getter()
        with store.connect() as db:
            counts = dict(db.execute('SELECT kind,COUNT(*) FROM records WHERE owner=? GROUP BY kind', (owner,)).fetchall())
            recipes = db.execute("SELECT COUNT(DISTINCT json_extract(payload,'$.proposal.recipe')) FROM records WHERE owner=? AND kind='project' AND json_extract(payload,'$.proposal.recipe') IS NOT NULL", (owner,)).fetchone()[0]
            exports = db.execute("SELECT COUNT(*) FROM records WHERE owner=? AND kind='job' AND json_extract(payload,'$.kind')='export' AND json_extract(payload,'$.status')='completed'", (owner,)).fetchone()[0]
            reviews = db.execute("SELECT COALESCE(SUM(json_extract(payload,'$.review_count')),0) FROM records WHERE owner=? AND kind='learning'", (owner,)).fetchone()[0]
        metrics = dict(projects=counts.get('project', 0), formulas=counts.get('formula', 0), scene_types=recipes,
                       revisions=counts.get('revision', 0), exports=exports, reviews=reviews, packs=counts.get('course-pack', 0))
        badges = [
            ('first-project', '第一个动态世界', '保存 1 个作品', 'projects', 1),
            ('project-collection', '积累作品', '保存 5 个作品', 'projects', 5),
            ('formula-note', '留下一个公式', '保存 1 条公式', 'formulas', 1),
            ('three-perspectives', '从不同角度探索', '保存 3 类场景', 'scene_types', 3),
            ('revision', '继续打磨', '留下 1 个历史版本', 'revisions', 1),
            ('export', '完成一次导出', '成功生成 1 个视频', 'exports', 1),
            ('review', '回头再想一遍', '记录 3 次错题复习', 'reviews', 3),
            ('pack', '整理一份课包', '保存 1 个课包', 'packs', 1),
        ]
        return dict(metrics=metrics, items=[dict(id=key, title=title, description=description, progress=metrics[metric], target=target,
                                               unlocked=metrics[metric] >= target) for key, title, description, metric, target in badges],
                    note='根据本账户实际保存、导出和自报复习记录统计；不代表知识掌握程度或学习能力评估。')

    @app.get('/api/releases')
    def releases(request: Request):
        owner_fn(request)
        return dict(current='harness-1.2', items=RELEASES)
