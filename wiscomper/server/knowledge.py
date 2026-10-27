"""Bounded graph of local formulas, examples and project metadata."""
from collections import Counter
import hashlib

from fastapi import Request

from .builders import SAMPLES
from .library import BUILTINS, saved_items

MAX_PROJECTS = 64
MAX_TOPICS = 24


def project_summaries(store, owner):
    # Project payloads contain frame arrays; retrieve only the three graph fields.
    with store.connect() as db:
        rows = db.execute("""SELECT id, substr(json_extract(payload,'$.title'),1,120),
            substr(json_extract(payload,'$.prompt'),1,1000), json_extract(payload,'$.proposal.recipe')
            FROM records WHERE kind='project' AND owner=? ORDER BY updated DESC LIMIT ?""",
            (owner, MAX_PROJECTS)).fetchall()
        count = db.execute("SELECT COUNT(*) FROM records WHERE kind='project' AND owner=?", (owner,)).fetchone()[0]
    return [dict(id=row[0], title=row[1] or '未命名作品', prompt=row[2] or '', recipe=row[3]) for row in rows], count


def build_knowledge(store, owner):
    formulas = [*BUILTINS, *saved_items(store, owner)]
    projects, project_count = project_summaries(store, owner)
    nodes, links = [], []
    for name, label in [('studio', '创作工作台'), ('library', '公式库'), ('samples', '示例集'), ('projects', '我的作品')]:
        target = 'create' if name == 'studio' else name
        nodes.append(dict(id='nav:'+name, label=label, kind='hub', action=dict(type='navigate', id=target)))
    links.extend(dict(source='nav:studio', target='nav:'+name, label='进入') for name in ('library', 'samples', 'projects'))
    features = [
        ('input-text', '文字创作', '描述要解释的现象、结构或过程。', 'nav:studio'),
        ('input-formula', '公式创作', '输入公式并说明变量、条件与想观察的变化。', 'nav:studio'),
        ('input-image', '图片创作', '选择本地图片，再描述需要理解或重建的内容。', 'nav:studio'),
        ('sketch', '手写草图', '用画笔和橡皮书写公式、绘制关系，添加为参考图片。', 'nav:studio'),
        ('search', '全站搜索', '查找真实功能、作品、公式、学习资料与课包。', 'nav:studio'),
        ('provider', '选择模型', '选择当前可用的创作模型。', 'nav:studio'),
        ('versions', '版本回看', '打开作品后查看、比较或恢复历史版本。', 'nav:projects'),
        ('export', '视频导出', '打开作品后选择可用的渲染方式导出视频。', 'nav:projects'),
        ('jobs', '任务进度', '查看创建和导出任务的真实进度与结果。', 'nav:studio'),
        ('help', '使用帮助', '了解创作、参数探索、版本与导出的操作。', 'nav:studio'),
        ('settings', '个人设置', '调整播放、动效、默认输入与悬浮球外观。', 'nav:studio'),
        ('learning', '学习资料', '收藏作品、安排稍后看、记录笔记与错题复习。', 'nav:projects'),
        ('course-packs', '课包与教案', '按顺序整理项目、公式、示例和学习记录。', 'nav:projects'),
        ('achievements', '使用成就', '根据实际保存、导出与复习记录查看进度。', 'nav:studio'),
        ('releases', '版本日志', '查看新工程更新与注明来源的旧站发展记录。', 'nav:studio'),
        ('tutorial', '新手引导', '按真实界面步骤认识输入、探索、保存与导出。', 'nav:studio'),
    ]
    for name, label, description, parent in features:
        ident = 'feature:'+name
        nodes.append(dict(id=ident, label=label, kind='feature', description=description,
                          action=dict(type='navigate', id=name)))
        links.append(dict(source=parent, target=ident, label='功能'))
    links.extend([
        dict(source='nav:library', target='feature:input-formula', label='填入公式'),
        dict(source='nav:samples', target='feature:input-text', label='参考需求'),
        dict(source='feature:learning', target='feature:course-packs', label='整理材料'),
        dict(source='nav:library', target='feature:course-packs', label='收录公式'),
        dict(source='feature:tutorial', target='feature:help', label='继续阅读'),
        dict(source='feature:sketch', target='feature:input-image', label='用作参考图片'),
        dict(source='feature:search', target='feature:learning', label='检索资料'),
    ])
    sample_ids = {sample['id'] for sample in SAMPLES}
    project_ids = {project['id'] for project in projects}
    counts = Counter(tag for formula in formulas for tag in formula['tags'])
    topic_tags = [tag for tag, _ in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:MAX_TOPICS]]
    topics = {tag: 'topic:'+hashlib.sha256(tag.encode()).hexdigest()[:16] for tag in topic_tags}
    for tag, ident in topics.items():
        nodes.append(dict(id=ident, label=tag, kind='topic', tags=[tag], description=f'{counts[tag]} 条相关公式',
                          action=dict(type='navigate', id='library')))
        links.append(dict(source='nav:library', target=ident, label='主题'))
    for sample in SAMPLES:
        ident = 'sample:'+sample['id']
        nodes.append(dict(id=ident, label=sample['title'], kind='sample', description=sample['description'],
                          prompt=sample['prompt'], tags=[sample['category']], sample=sample['id'],
                          action=dict(type='sample', id=sample['id'])))
        links.append(dict(source='nav:samples', target=ident, label='示例'))
    for project in projects:
        ident = 'project:'+project['id']
        nodes.append(dict(id=ident, label=project['title'], kind='project', description=project['prompt'],
                          prompt=project['prompt'], project_id=project['id'], action=dict(type='project', id=project['id'])))
        links.append(dict(source='nav:projects', target=ident, label='作品'))
        if project['recipe'] in sample_ids:
            # Recipe equivalence is not proof that a project originated from this sample.
            links.append(dict(source='sample:'+project['recipe'], target=ident, label='同类场景'))
    for formula in formulas:
        ident = 'formula:'+formula['id']
        prompt = formula.get('prompt') or f'请解释“{formula["title"]}”的变量、适用条件与变化关系，并设计可视化。公式：{formula["latex"]}'
        node = dict(id=ident, label=formula['title'], kind='formula', latex=formula['latex'],
                    description=formula['note'], tags=formula['tags'], builtin=formula['builtin'],
                    prompt=prompt, action=dict(type='formula', id=formula['id']))
        if formula.get('sample') in sample_ids:
            node.update(sample=formula['sample'], sample_note=formula.get('sample_note', ''))
            links.append(dict(source=ident, target='sample:'+formula['sample'], label='相关示例'))
        if formula.get('project_id') in project_ids:
            node['project_id'] = formula['project_id']
            links.append(dict(source=ident, target='project:'+formula['project_id'], label='关联作品'))
        nodes.append(node)
        if not any(tag in topics for tag in formula['tags']):
            links.append(dict(source='nav:library', target=ident, label='内置公式' if formula['builtin'] else '保存的公式'))
        links.extend(dict(source=topics[tag], target=ident, label='相关公式') for tag in formula['tags'] if tag in topics)
    for source, target, label in [
        ('sine', 'sine-derivative', '求导'), ('riemann-sum', 'square-integral', '平方函数特例'),
        ('projectile', 'projectile-range', '等高落地条件'), ('pendulum', 'pendulum-period', '小角度无阻尼近似'),
        ('travelling-wave', 'wave-speed', '相速度'), ('snell', 'critical-angle', '高折射率到低折射率'),
        ('queue-wait', 'queue-load', '固定间隔的负载比'),
    ]:
        links.append(dict(source='formula:builtin-'+source, target='formula:builtin-'+target, label=label))
    return dict(nodes=nodes, links=links,
                limits=dict(projects=MAX_PROJECTS, topics=MAX_TOPICS),
                omitted=dict(projects=max(0, project_count-MAX_PROJECTS), topics=max(0, len(counts)-MAX_TOPICS)))


def install_knowledge(app, store_getter, owner_fn):
    @app.get('/api/knowledge')
    def knowledge(request: Request):
        return build_knowledge(store_getter(), owner_fn(request))
