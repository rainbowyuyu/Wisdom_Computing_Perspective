import json
from pathlib import Path
import re
from xml.etree import ElementTree

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from server.site import NAME, ENGLISH_NAME, PUBLIC_PAGES, SiteConfig, install_site, validate_public_url

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('value', [
    'http://wiscomper.example.com', '//wiscomper.example.com', 'https://localhost', 'https://127.0.0.1',
    'https://[::1]', 'https://192.168.1.1', 'https://internal', 'https://thing.local', 'https://thing.test',
    'https://thing.invalid', 'https://thing.example', 'https://device.home.arpa', 'https://thing.lan',
    'https://example.com:8443', 'https://example.com:',
    'https://user:secret@example.com', 'https://user@example.com', 'https://example.com/app',
    'https://example.com/?x=1', 'https://example.com/?', 'https://example.com/#', 'https://example.com/#fragment',
    'https://example.com\\evil', 'https://example.com\n', ' https://example.com',
    'https://bad_name.example.com', 'https://-bad.example.com', 'https://example.com.',
    'https://example.com:99999', 'https://example.com/%2f', 'https://example.com@evil.com:1234',
])
def test_public_origin_rejects_noncanonical_or_nonproduction_values(value):
    with pytest.raises(ValueError, match='PUBLIC_SITE_URL'):
        validate_public_url(value)


def test_public_origin_is_explicit_and_environment_empty_overrides_file(monkeypatch):
    assert SiteConfig().public_origin == ''
    assert SiteConfig('https://Wiscomper.Example.COM:443/').public_origin == 'https://wiscomper.example.com'
    monkeypatch.delenv('PUBLIC_SITE_URL', raising=False)
    assert SiteConfig.from_settings({'PUBLIC_SITE_URL': 'https://wiscomper.example.com'}).public_host == 'wiscomper.example.com'
    monkeypatch.setenv('PUBLIC_SITE_URL', '')
    assert SiteConfig.from_settings({'PUBLIC_SITE_URL': 'https://wiscomper.example.com'}).public_origin == ''
    monkeypatch.setenv('PUBLIC_SITE_URL', 'http://unsafe.example.com')
    with pytest.raises(ValueError):
        SiteConfig.from_settings({'PUBLIC_SITE_URL': 'https://wiscomper.example.com'})


def test_authority_and_write_origin_allowlist_cannot_be_forwarded_or_userinfo():
    site = SiteConfig('https://wiscomper.example.com')
    for host in ('127.0.0.1:3088', 'localhost:3090', 'testserver', '[::1]:3088', 'wiscomper.example.com', 'wiscomper.example.com:443'):
        assert site.is_allowed_authority(host)
    for host in ('evil.example.com', 'wiscomper.example.com.evil.com', 'wiscomper.example.com:80', 'wiscomper.example.com:8443',
                 'wiscomper.example.com@evil.example.com', 'evil.com@wiscomper.example.com', 'localhost/foo',
                 'localhost,evil.com', 'localhost\n', 'localhost:0', 'localhost:', 'localhost:99999', 'localhost?x=1', 'localhost#', ''):
        assert not site.is_allowed_authority(host), host
    assert site.allowed_origin('wiscomper.example.com', 'http') == 'https://wiscomper.example.com'
    assert site.allowed_origin('localhost:3088', 'http') == 'http://localhost:3088'
    assert site.allowed_origin('[::1]:3088', 'http') == 'http://[::1]:3088'
    assert site.allowed_origin('localhost:80', 'http') == 'http://localhost'
    assert site.allowed_origin('evil.example.com', 'https') is None
    assert site.allowed_origin('localhost:3088', 'javascript') is None
    assert not SiteConfig().is_allowed_authority('wiscomper.example.com')


def client_for(site):
    app = FastAPI()
    install_site(app, lambda: site, ROOT)

    @app.get('/')
    def index():
        return site.render_index(ROOT/'web'/'index.html')

    return TestClient(app)


def schemas(html):
    return [json.loads(source) for source in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def test_unconfigured_local_pages_are_noindex_and_have_no_public_sitemap_urls():
    with client_for(SiteConfig()) as client:
        for path in PUBLIC_PAGES:
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers['x-robots-tag'] == 'noindex, nofollow'
            assert '<meta name="robots" content="noindex, nofollow">' in response.text
            assert 'rel="canonical"' not in response.text
            assert not schemas(response.text)
            assert NAME in response.text
        assert client.get('/robots.txt').text == 'User-agent: *\nDisallow: /\n'
        sitemap = ElementTree.fromstring(client.get('/sitemap.xml').content)
        assert not list(sitemap)


def test_public_metadata_uses_config_only_and_has_no_fabricated_ratings_or_private_urls():
    origin = 'https://wiscomper.example.com'
    site = SiteConfig(origin)
    with client_for(site) as client:
        for path in PUBLIC_PAGES:
            # The application guard separately rejects this host; metadata must still never use it.
            response = client.get(path, headers={'Host': 'injected.example.org', 'X-Forwarded-Host': 'other.example.org'})
            assert response.status_code == 200
            assert response.headers['x-robots-tag'].startswith('index, follow')
            assert response.text.count('rel="canonical"') == 1
            assert f'<link rel="canonical" href="{origin+path}">' in response.text
            assert f'<meta property="og:url" content="{origin+path}">' in response.text
            assert f'<meta name="twitter:image" content="{origin}/site-share.png">' in response.text
            assert 'injected.example.org' not in response.text and 'other.example.org' not in response.text
            structured = schemas(response.text)
            assert len(structured) == 1
            objects = {item['@type']: item for item in structured[0]['@graph']}
            assert objects['WebSite']['url'] == origin+'/'
            assert objects['SoftwareApplication']['alternateName'] == ENGLISH_NAME
            assert 'aggregateRating' not in objects['SoftwareApplication']
            assert 'offers' not in objects['SoftwareApplication']
            assert '/api/' not in json.dumps(structured)
        assert site.robots_header('/api/projects') == 'noindex, nofollow'
        assert site.robots_header('/api/auth/github/callback') == 'noindex, nofollow'
        assert site.robots_header('/web/index.html') == 'noindex, nofollow'
        assert site.robots_header('/render.html') == 'noindex, nofollow'
        robots = client.get('/robots.txt').text
        assert 'Disallow: /api/' in robots and 'Disallow: /web/index.html' in robots
        assert f'Sitemap: {origin}/sitemap.xml' in robots
        assert 'Disallow: /web/\n' not in robots and 'Disallow: /vendor/' not in robots
        sitemap = ElementTree.fromstring(client.get('/sitemap.xml').content)
        urls = [node.text for node in sitemap.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
        assert urls == [origin+path for path in PUBLIC_PAGES]


def test_head_injection_replaces_stale_metadata_without_removing_app_code(tmp_path):
    template = tmp_path/'index.html'
    template.write_text('''<!doctype html><head><meta charset="utf-8"><title>OLD</title><meta name='description' content='OLD'><meta property="og:url" content="https://old.example.com/"><meta name="robots" content="noindex"><meta name="twitter:card" content="summary"><link rel='canonical' href='https://old.example.com/'><script type="application/ld+json">{"name":"OLD"}</script><link rel="stylesheet" href="/web/style.css"></head><body><script type="module" src="/web/app.js"></script><p>Kept body</p></body>''', encoding='utf-8')
    html = SiteConfig('https://wiscomper.example.com').render_index(template).body.decode()
    assert 'OLD' not in html and 'old.example.com' not in html
    assert html.count('<title>') == 1 and html.count('name="robots"') == 1
    assert html.count('application/ld+json') == 1
    assert '/web/app.js' in html and '/web/style.css' in html and 'Kept body' in html


def test_static_public_explanations_and_share_images_are_crawlable_without_a_session():
    with client_for(SiteConfig('https://wiscomper.example.com')) as client:
        explore = client.get('/explore')
        assert explore.text.count('<article class="card"') == 12
        assert explore.text.count('href="/?sample=') == 12
        assert '24 秒' in explore.text and '不计算光强' in explore.text
        assert '/api/bootstrap' not in explore.text and '/web/app.js' not in explore.text
        assert not explore.headers.get('set-cookie')
        about = client.get('/about').text
        assert '本工程服务端' in about and '发送给所选模型提供商' in about and '不申请仓库或邮箱权限' in about
        png = client.get('/site-share.png')
        assert png.status_code == 200 and png.headers['content-type'] == 'image/png'
        svg = client.get('/site-share.svg')
        assert svg.status_code == 200 and '<script' not in svg.text
        assert ElementTree.fromstring(svg.content).attrib['viewBox'] == '0 0 1200 630'
        with Image.open(ROOT/'web/assets/wiscomper-share.png') as image:
            assert image.size == (1200, 630)
