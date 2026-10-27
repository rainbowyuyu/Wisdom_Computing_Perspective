"""Private, bounded search over workspace text and public entry points."""
from collections import Counter
from typing import Annotated

from fastapi import Query, Request

from .builders import SAMPLES
from .library import BUILTINS


FEATURES = (
    ('create', '创作工作台', '开始创作：用文字、公式或图片解释想法。'),
    ('library', '公式库', '检索内置与保存的公式、变量条件和说明。'),
    ('knowledge', '三维知识图谱', '沿公式、示例与作品的关联继续探索。'),
    ('learning', '学习资料与错题本', '收藏、稍后看、笔记、归档恢复与复习。'),
    ('course-packs', '教案与课包', '按顺序整理作品、公式、示例和学习资料。'),
    ('settings', '偏好与悬浮球设置', '主题、动效、播放速度、默认输入与悬浮球外观。'),
    ('sketch', '手写草图', '用画笔或橡皮书写公式和草图，撤销重做后添加为参考图片。'),
    ('search', '全站搜索', '统一查找功能、作品、公式、学习资料和课包。'),
    ('projects', '我的作品', '查看已保存的项目、探索参数与版本。'),
    ('samples', '本地示例', '从数学、物理、三维结构与系统示例开始。'),
    ('versions', '作品版本', '回看、比较或恢复当前作品的历史版本。'),
    ('export', '视频导出', '把当前作品导出为可播放的视频。'),
    ('jobs', '任务进度', '查看创作与导出的进度、结果和失败原因。'),
    ('achievements', '探索足迹', '根据实际保存、导出与复习记录查看成就进度。'),
    ('releases', '版本动态', '查看本站更新及注明来源的旧站发展记录。'),
    ('tutorial', '新手教程', '按真实界面步骤学习输入、探索、保存与导出。'),
    ('help', '使用帮助', '了解操作方式、能力边界与常见问题。'),
)

# All SQL expressions below are fixed application code. Neither queries nor
# record IDs are interpolated into SQL. Large scenes, frames, course materials
# and review histories never cross the SQLite/Python boundary.
def _column(path, length):
    return f"COALESCE(substr(json_extract(payload,'$.{path}'),1,{length}),'')"


TITLE = _column('title', 120)
PRIVATE_FIELDS = {
    'project': (['prompt', 'scene.summary', 'proposal.recipe'], [6000, 4000, 80], '作品'),
    'formula': (['note', 'latex', 'prompt', 'tags'], [4000, 4000, 2000, 1024], '公式'),
    'learning': (['problem', 'note', 'answer', 'tags', 'kind'], [4000, 4000, 4000, 1024, 40], '学习资料'),
    'course-pack': (['description', 'lesson.audience', 'lesson.objectives', 'lesson.key_points',
                     'lesson.preparation', 'lesson.procedure', 'lesson.exercises', 'lesson.reflection'],
                    [2000, 160, 4000, 4000, 4000, 8000, 4000, 4000], '课包'),
}


def _score(title, text, terms):
    if not terms:
        return 0
    title = str(title or '').casefold()
    text = str(text or '').casefold()
    if not all(term in text for term in terms):
        return 0
    phrase = ' '.join(terms)
    return 4 if title == phrase else 3 if title.startswith(phrase) else 2 if all(term in title for term in terms) else 1


def _item(kind, ident, title, description, *, action=None):
    return dict(id=f'{kind}:{ident}', kind=kind, title=str(title or '未命名')[:120],
                description=str(description or '')[:240],
                action=dict(type=action or kind, id=ident))


def search_workspace(store, owner, query='', limit=24):
    terms = query.casefold().split()
    candidates = []
    features = []
    public_items = []
    for ident, title, description in FEATURES:
        item = _item('feature', ident, title, description, action='navigate')
        score = _score(title, title + '\n' + description, terms)
        if not terms or score:
            features.append((score, 0, item))
    for kind, entries in [('sample', SAMPLES), ('formula', BUILTINS)]:
        for entry in entries:
            description = entry.get('description') or entry.get('note') or entry.get('latex') or ''
            text = '\n'.join(str(entry.get(key) or '') for key in ('title', 'description', 'note', 'latex', 'prompt', 'category', 'tags'))
            score = _score(entry['title'], text, terms)
            if not terms or score:
                public_items.append((score, 0, _item(kind, entry['id'], entry['title'], description)))
    with store.connect() as db:
        db.create_function('workspace_search_rank', 2, lambda title, text: _score(title, text, terms), deterministic=True)
        for kind, (paths, sizes, fallback) in PRIVATE_FIELDS.items():
            columns = [_column(path, size) for path, size in zip(paths, sizes)]
            searchable = " || char(10) || ".join([TITLE, *columns])
            # First nonempty content field becomes a short result preview.
            preview = 'COALESCE(' + ','.join(f"NULLIF({column},'')" for column in columns[:3]) + ",'')"
            sql = f"""WITH metadata AS (
                SELECT id, {TITLE} AS title, substr({preview},1,240) AS description,
                    updated, workspace_search_rank({TITLE}, {searchable}) AS score
                FROM records WHERE owner=? AND kind=?
                    AND COALESCE(json_extract(payload,'$.archived'),0)=0)
                SELECT id,title,description,updated,score FROM metadata
                WHERE score>0 OR ?=1 ORDER BY score DESC,updated DESC,id LIMIT ?"""
            rows = db.execute(sql, (owner, kind, int(not terms), limit + 1)).fetchall()
            candidates.extend((row[4], row[3], _item(kind, row[0], row[1] or fallback, row[2])) for row in rows)
    candidates.sort(key=lambda result: (-result[0], -result[1], result[2]['id']))
    if terms:
        ranked = sorted([*candidates, *features, *public_items], key=lambda result: (-result[0], -result[1], result[2]['id']))
    else:
        # Reserve visible entry points even when a space has many recent items.
        feature_count = min(len(features), max(1, limit // 4))
        recent_count = min(len(candidates), max(0, limit - feature_count))
        ranked = [*candidates[:recent_count], *features[:feature_count],
                  *public_items, *features[feature_count:], *candidates[recent_count:]]
    items = [entry[2] for entry in ranked[:limit]]
    return dict(query=query, items=items, has_more=len(ranked) > limit, limit=limit,
                counts=dict(Counter(item['kind'] for item in items)))


def install_search(app, store_getter, owner_fn):
    @app.get('/api/search')
    def search(request: Request, q: Annotated[str, Query(max_length=200)] = '',
               limit: Annotated[int, Query(ge=1, le=40)] = 24):
        return search_workspace(store_getter(), owner_fn(request), q.strip(), limit)
