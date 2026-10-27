"""Public site metadata. Canonical URLs come only from validated configuration."""
from dataclasses import dataclass
from html import escape
import ipaddress
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response

from .builders import SAMPLES

NAME = 'Wiscomper 智算视界'
ENGLISH_NAME = 'Wisdom Computer Perspective'
DESCRIPTION = 'Wiscomper 智算视界把文字、公式与图片变成可观察、可交互的动态解释，支持二维与三维创作、参数探索、公式管理和视频导出。'
PUBLIC_PAGES = ('/', '/about', '/explore')
LOCAL_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1', 'testserver'})


def validate_public_url(value):
    """Accept a single HTTPS DNS origin; never silently repair unsafe settings."""
    if value is None or value == '':
        return ''
    if not isinstance(value, str) or value != value.strip() or len(value) > 300:
        raise ValueError('PUBLIC_SITE_URL 必须为空或完整的正式 HTTPS 域名地址。')
    try:
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
        if (parsed.scheme != 'https' or not host or parsed.username is not None or parsed.password is not None
                or port not in (None, 443) or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                or parsed.netloc.endswith(':') or any(c in value for c in ('?', '#', '\\', '\n', '\r', '\t'))):
            raise ValueError
        host = host.encode('idna').decode('ascii').lower()
        labels = host.split('.')
        if (len(host) > 253 or len(labels) < 2 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels)
                or not re.fullmatch(r'(?:[a-z]{2,63}|xn--[a-z0-9-]{2,59})', labels[-1])
                or labels[-1] in {'localhost', 'local', 'internal', 'test', 'invalid', 'example', 'lan', 'home', 'corp', 'onion', 'arpa'}):
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError
    except (ValueError, UnicodeError):
        raise ValueError('PUBLIC_SITE_URL 只接受正式 HTTPS 域名根地址，不接受 IP、凭据、非标准端口、路径、查询或片段。') from None
    return 'https://' + host


def _authority(value):
    """Parse Host without accepting userinfo, paths, forwarded lists or rewrites."""
    try:
        if not isinstance(value, str) or not value or value.endswith(':') or len(value) > 300 or any(c.isspace() for c in value):
            return None
        parsed = urlsplit('//'+value)
        if (parsed.username is not None or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
                or any(c in value for c in ('\\', ',', '?', '#', '%'))):
            return None
        host, port = parsed.hostname, parsed.port
        if not host or port == 0:
            return None
        return host.lower(), port
    except ValueError:
        return None


@dataclass(frozen=True)
class SiteConfig:
    public_origin: str = ''

    def __post_init__(self):
        object.__setattr__(self, 'public_origin', validate_public_url(self.public_origin))

    @classmethod
    def from_settings(cls, settings=None):
        settings = settings or {}
        return cls(os.environ.get('PUBLIC_SITE_URL', settings.get('PUBLIC_SITE_URL') or ''))

    @property
    def public_host(self):
        return urlsplit(self.public_origin).hostname if self.public_origin else None

    @property
    def allowed_hosts(self):
        return LOCAL_HOSTS | ({self.public_host} if self.public_host else set())

    def is_allowed_authority(self, host_header):
        authority = _authority(host_header)
        if not authority:
            return False
        host, port = authority
        return host in LOCAL_HOSTS or (host == self.public_host and port in (None, 443))

    def allowed_origin(self, host_header, scheme='http'):
        if not self.is_allowed_authority(host_header) or scheme not in {'http', 'https'}:
            return None
        host, port = _authority(host_header)
        if host == self.public_host:
            return self.public_origin
        host = '['+host+']' if ':' in host else host
        default = 443 if scheme == 'https' else 80
        return f'{scheme}://{host}' + (f':{port}' if port and port != default else '')

    def robots_header(self, path):
        return 'index, follow, max-image-preview:large' if self.public_origin and path in PUBLIC_PAGES else 'noindex, nofollow'

    def head(self, path='/', title=None, description=DESCRIPTION):
        if path not in PUBLIC_PAGES:
            raise ValueError('Only explicitly public pages can receive site metadata.')
        title = title or f'{NAME} · {ENGLISH_NAME}'
        tags = [f'<title>{escape(title)}</title>', f'<meta name="description" content="{escape(description, quote=True)}">',
                f'<meta name="robots" content="{self.robots_header(path)}">',
                '<meta property="og:type" content="website">', '<meta property="og:locale" content="zh_CN">',
                f'<meta property="og:site_name" content="{NAME}">',
                f'<meta property="og:title" content="{escape(title, quote=True)}">',
                f'<meta property="og:description" content="{escape(description, quote=True)}">',
                '<meta name="twitter:card" content="summary_large_image">',
                f'<meta name="twitter:title" content="{escape(title, quote=True)}">',
                f'<meta name="twitter:description" content="{escape(description, quote=True)}">']
        if self.public_origin:
            canonical = self.public_origin + path
            image = self.public_origin + '/site-share.png'
            tags += [f'<link rel="canonical" href="{canonical}">', f'<meta property="og:url" content="{canonical}">',
                     f'<meta property="og:image" content="{image}">', '<meta property="og:image:type" content="image/png">',
                     '<meta property="og:image:width" content="1200">', '<meta property="og:image:height" content="630">',
                     f'<meta property="og:image:alt" content="{NAME}：让想法成为可以探索的动态世界">',
                     f'<meta name="twitter:image" content="{image}">', f'<meta name="twitter:image:alt" content="{NAME} 可视化创作工作台">']
            base = self.public_origin + '/'
            schema = {'@context': 'https://schema.org', '@graph': [
                {'@type': 'WebSite', '@id': base+'#website', 'name': NAME, 'alternateName': ENGLISH_NAME,
                 'url': base, 'inLanguage': 'zh-CN', 'description': DESCRIPTION},
                {'@type': 'SoftwareApplication', '@id': base+'#application', 'name': NAME, 'alternateName': ENGLISH_NAME,
                 'applicationCategory': 'EducationalApplication', 'operatingSystem': 'Web', 'url': base,
                 'description': DESCRIPTION, 'image': image,
                 'featureList': ['文字、公式和图片创作', '二维与三维交互', '参数探索', '公式库和知识图谱', '版本回看', '视频导出']},
                {'@type': 'WebPage', '@id': canonical+'#page', 'url': canonical, 'name': title, 'description': description,
                 'isPartOf': {'@id': base+'#website'}, 'inLanguage': 'zh-CN'},
            ]}
            encoded = json.dumps(schema, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
            tags.append('<script type="application/ld+json">'+encoded+'</script>')
        return '\n'.join(tags)

    def render_index(self, path):
        html = Path(path).read_text(encoding='utf-8')
        if not re.search(r'</head\s*>', html, re.I):
            raise ValueError('Homepage template is missing its head element.')
        # This is a controlled local template, never user-provided HTML.
        html = re.sub(r'<title\b[^>]*>.*?</title\s*>', '', html, flags=re.I|re.S)
        html = re.sub(r'<meta\b[^>]*(?:name|property)\s*=\s*[\'\"](?:description|robots|og:[^\'\"]*|twitter:[^\'\"]*)[\'\"][^>]*>', '', html, flags=re.I)
        html = re.sub(r'<link\b[^>]*rel\s*=\s*[\'\"]canonical[\'\"][^>]*>', '', html, flags=re.I)
        html = re.sub(r'<script\b[^>]*type\s*=\s*[\'\"]application/ld\+json[\'\"][^>]*>.*?</script\s*>', '', html, flags=re.I|re.S)
        html = re.sub(r'</head\s*>', lambda _: self.head('/')+'\n</head>', html, count=1, flags=re.I)
        return HTMLResponse(html, headers={'Cache-Control': 'no-cache', 'X-Robots-Tag': self.robots_header('/')})


STYLE = '''body{margin:0;background:#f6f8fc;color:#16253b;font:16px/1.8 system-ui,"Microsoft YaHei",sans-serif}header,main,footer{max-width:1050px;margin:auto;padding:24px}header{display:flex;justify-content:space-between;align-items:center;gap:20px}a{color:#285cce}nav{display:flex;gap:20px;flex-wrap:wrap}.brand{display:flex;align-items:center;gap:12px;text-decoration:none;color:inherit}.brand img{width:50px;height:50px}.brand small{display:block;color:#63738a;font-size:11px;line-height:1.5}h1{font-size:clamp(32px,5vw,56px);line-height:1.3;letter-spacing:-1px;margin:26px 0}h2{font-size:25px;margin-top:40px}h3{margin:0 0 10px;font-size:19px}p{color:#53647b}.intro{max-width:780px;font-size:20px}.button{display:inline-block;padding:10px 22px;border-radius:10px;background:#315fd5;color:white;text-decoration:none}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:18px;margin:26px 0}.card{background:white;padding:24px;border:1px solid #e0e7f1;border-radius:18px}.tag{color:#4269ac;font-size:13px}.scope{font-size:14px;padding-top:12px;border-top:1px solid #e9edf4}footer{font-size:13px;color:#69798d;border-top:1px solid #dfe6f0}@media(max-width:600px){header{align-items:flex-start;flex-direction:column}header,main,footer{padding:18px}.intro{font-size:18px}}'''

SAMPLE_SCOPE = {
    'projectile': '均匀重力、点质量、无空气阻力，出发与落地点等高。',
    'pendulum': '非线性单摆与线性角速度阻尼，通过数值积分计算。',
    'function': '安全表达式的数值采样；示例从 sin(x) 开始。',
    'wave': '一维正弦行波，区分波形传播与质点振动。',
    'field': '解析平面旋转速度场，不是计算流体力学求解器。',
    'model3d': '电机结构、装配与拆解示意，不用于工程尺寸验证。',
    'fan': '叶片、转子和护罩的交互结构；气流路径仅作示意。',
    'formula': '展示 x²−5x+6=0 的因式分解与根，不提供任意公式证明。',
    'diagram': '以水循环展示过程关系，不计算真实水量或气候变化。',
    'riemann': '固定函数 x² 的黎曼和，与精确积分面积比较。',
    'refraction': '单平面界面的几何光学，不计算光强、偏振和菲涅耳系数。',
    'queue': '固定到达间隔、固定服务时长、先到先服务；观察窗口为 24 秒。',
}


def public_page(site, path):
    if path == '/about':
        title, description = f'关于 {NAME}', f'了解 {NAME} 的文字、公式、图片创作，二维与三维交互、版本管理和公式知识整理。'
        content = '''<span class="tag">Wisdom Computer Perspective</span><h1>让想法成为<br>可以探索的动态世界。</h1>
        <p class="intro">Wiscomper 智算视界是一套可视化创作工作台。输入一个问题、一条公式或一张图片，把对象、变化与关系放进可以观察和操作的画面。</p>
        <p><a class="button" href="/">进入创作工作台</a>　<a href="/explore">浏览 12 个示例方向</a></p>
        <div class="grid"><section class="card"><h2>把关系讲清楚</h2><p>从文字、公式或图片开始，用二维图层、数学曲线或三维结构组织解释。可以播放、暂停、观察时间变化，选择需要继续修改的对象。</p></section>
        <section class="card"><h2>边操作，边理解</h2><p>旋转三维视角，调整有边界的滑块、开关与构件。数值示例支持参数重算，让观察与模型条件对应起来。</p></section>
        <section class="card"><h2>积累自己的作品</h2><p>在同一项目中持续修改，回看和恢复历史版本。公式库保存公式、条件、笔记和标签；知识图谱把公式、示例与自己的项目连起来。</p></section>
        <section class="card"><h2>分享动态解释</h2><p>在已配置渲染环境中导出视频，或下载场景数据。公式库支持 JSON 导入导出，方便整理与迁移。</p></section></div>
        <h2>从适用条件出发</h2><p>明确的数值示例会说明模型、参数与假设。通用场景用于解释关系；图片标注和结构示意不保证真实尺寸或完整三维重建。条件不足时，先补充描述，再继续创作。</p>
        <h2>自己的创作空间</h2><p>公开介绍页只包含功能和示例说明。个人项目、上传图片、公式笔记与导出文件保存在本工程服务端，按浏览器会话或登录账户隔离，不列入公开目录。公网部署的服务端位于站点运营方提供的机器上，并非你的浏览器设备。</p>
        <p>GitHub 登录仅请求识别账户所需的最小公开身份信息，不申请仓库或邮箱权限。只有提交真实模型创作时，相关文字、公式和图片才会发送给所选模型提供商；具体内容以本次创作输入为准。本地示例、公式管理与参数实验不调用模型。</p>
        <p>公网工作台可匿名探索内置示例；自行创作、上传图片和视频导出需要登录，并受站点设置的每日限额约束。</p>'''
    elif path == '/explore':
        title, description = f'探索示例 · {NAME}', '从数学、运动、波动、光学、机械结构与系统过程出发，了解 Wiscomper 的 12 个可视化示例及适用条件。'
        cards = []
        for sample in SAMPLES:
            cards.append(f'<article class="card" id="{escape(sample["id"], quote=True)}"><span class="tag">{escape(sample["category"])}</span><h2>{escape(sample["title"])}</h2><p>{escape(sample["description"])}</p><p class="scope">{escape(SAMPLE_SCOPE[sample["id"]])}</p><a href="/?sample={escape(sample["id"], quote=True)}">打开这个示例 →</a></article>')
        content = '<span class="tag">从一个具体问题开始</span><h1>12 个方向，打开探索。</h1><p class="intro">这些示例帮助你认识工作台的表达方式。进入首页选择对应示例，即可播放、观察并尝试调整参数。</p><p><a class="button" href="/">打开示例工作台</a></p><div class="grid">'+''.join(cards)+'</div><p>本地示例和参数探索不调用模型。输入自己的需求生成新内容时，工作台使用所选模型；视频导出需要服务端已安装对应渲染环境。</p>'
    else:
        raise ValueError('Unknown public page.')
    html = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{site.head(path,title,description)}<link rel="icon" href="/web/assets/wisdom-logo.svg" type="image/svg+xml"><style>{STYLE}</style></head><body><header><a href="/" class="brand"><img src="/web/assets/wisdom-logo.svg" alt="" width="50" height="50"><span><strong>{NAME}</strong><small>{ENGLISH_NAME}</small></span></a><nav aria-label="网站导航"><a href="/">工作台</a><a href="/about">关于</a><a href="/explore">探索示例</a></nav></header><main>{content}</main><footer>{NAME} · {ENGLISH_NAME}<br><a href="/about">产品介绍</a> · <a href="/explore">示例与适用条件</a></footer></body></html>'''
    return HTMLResponse(html, headers={'Cache-Control': 'public, max-age=300', 'X-Robots-Tag': site.robots_header(path)})


def install_site(app, site_getter, root):
    root = Path(root)

    @app.get('/about', include_in_schema=False)
    def about():
        return public_page(site_getter(), '/about')

    @app.get('/explore', include_in_schema=False)
    def explore():
        return public_page(site_getter(), '/explore')

    @app.get('/robots.txt', include_in_schema=False)
    def robots():
        site = site_getter()
        if not site.public_origin:
            content = 'User-agent: *\nDisallow: /\n'
        else:
            content = 'User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /auth/\nDisallow: /render.html\nDisallow: /web/index.html\nDisallow: /web/render.html\nDisallow: /data/\nSitemap: '+site.public_origin+'/sitemap.xml\n'
        return PlainTextResponse(content, headers={'Cache-Control': 'public, max-age=300'})

    @app.get('/sitemap.xml', include_in_schema=False)
    def sitemap():
        origin = site_getter().public_origin
        entries = ''.join('<url><loc>'+escape(origin+path)+'</loc></url>' for path in PUBLIC_PAGES) if origin else ''
        xml = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+entries+'</urlset>'
        return Response(xml, media_type='application/xml', headers={'Cache-Control': 'public, max-age=300', 'X-Robots-Tag': 'noindex'})

    @app.get('/site-share.svg', include_in_schema=False)
    def share_svg():
        return FileResponse(root/'web'/'assets'/'wiscomper-share.svg', media_type='image/svg+xml', headers={'Cache-Control': 'public, max-age=86400'})

    @app.get('/site-share.png', include_in_schema=False)
    def share_png():
        return FileResponse(root/'web'/'assets'/'wiscomper-share.png', media_type='image/png', headers={'Cache-Control': 'public, max-age=86400'})
