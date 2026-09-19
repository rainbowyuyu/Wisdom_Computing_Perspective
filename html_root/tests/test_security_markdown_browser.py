"""Real browser URL parsing, namespace attacks, and useful Markdown formatting."""
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]/'static/js'


@pytest.fixture(scope='module')
def page():
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page()
        page.route('http://security.test/',lambda r:r.fulfill(content_type='text/html',body='<main id="output"></main>'))
        page.route('http://security.test/sanitize.js',lambda r:r.fulfill(content_type='text/javascript',body=(ROOT/'sanitize.js').read_text(encoding='utf-8')))
        page.route('http://security.test/vendor/dompurify.es.mjs',lambda r:r.fulfill(content_type='text/javascript',body=(ROOT/'vendor/dompurify.es.mjs').read_text(encoding='utf-8')))
        page.goto('http://security.test/')
        page.evaluate("async()=>{window.clean=(await import('/sanitize.js')).sanitizeMarkdownHtml}")
        yield page
        browser.close()


@pytest.mark.parametrize('payload',[
    '<a href="java&#10;script:window.pwned=1">open</a>',
    '<svg><a xlink:href="javascript:window.pwned=1"><text>open</text></a></svg>',
    '<img src=x onerror="window.pwned=1">',
    '<math><mtext><table><mglyph><style><!--</style><img title="--><img src=1 onerror=window.pwned=1>">',
    '<style>body{display:none}</style><form id="auth"><input name="password"></form>',
    '<iframe srcdoc="<script>parent.pwned=1</script>"></iframe>',
    '<a href="data:text/html,<script>alert(1)</script>">open</a>',
])
def test_hostile_markup_cannot_create_script_urls_or_controls(page,payload):
    result=page.evaluate('''payload=>{
        window.pwned=0;
        const out=document.querySelector('#output');out.innerHTML=window.clean(payload);
        return {danger:out.querySelectorAll('svg,math,style,iframe,form,input,script').length,
            attrs:[...out.querySelectorAll('*')].flatMap(e=>[...e.attributes].map(a=>[a.name,a.value])),pwned:window.pwned};
    }''',payload)
    assert result['danger']==0 and result['pwned']==0
    assert not any(name.startswith('on') or ('javascript:' in value.replace('\n','').lower()) for name,value in result['attrs'])


def test_math_tables_links_and_code_survive(page):
    html=page.evaluate('value=>window.clean(value)', r'<h2>解题</h2><p>公式 \(x^2\)</p><table><tr><td>2</td></tr></table><pre><code>x=2</code></pre><a href="https://example.org/help">帮助</a>')
    assert r'\(x^2\)' in html
    assert '<h2>解题</h2>' in html and '<td>2</td>' in html and '<code>x=2</code>' in html
    assert 'https://example.org/help' in html
