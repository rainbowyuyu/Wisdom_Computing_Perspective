import json
from pathlib import Path

from app.config import get_db_connection
from logic.solution_engine import local_solution
from test_teaching import teaching_page
from test_solution_library import accounts, live_library_server

BROKEN=r'x - 2=0\quad\mathrm{or}\quadx - 3=0'
FIXED=r'x - 2=0\quad\mathrm{or}\quad x - 3=0'


def assert_math(target):
    assert target.locator('.katex').count()>0
    assert target.locator('.katex-error, .math-render-error').count()==0
    assert target.evaluate("e=>!e.classList.contains('math-render-error')")
    assert r'\quadx' not in target.inner_text()


def test_legacy_history_database_reader_and_export(teaching_page):
    page,origin,kind=teaching_page
    solution=local_solution('x^2-5*x+6=0').model_dump(mode='json')
    solution['steps'][2]['formula']=BROKEN
    record={'problem':'x^2-5*x+6=0','solution':solution,'context':'','video':None}
    ident=page.request.post(origin+'/api/formulas/solutions',data=record).json()['id']
    # Simulate an existing row written before the fix, bypassing current validators.
    conn=get_db_connection();cursor=conn.cursor()
    cursor.execute('UPDATE formula_solutions SET payload=%s WHERE formula_id=%s',(json.dumps(record),ident))
    conn.commit();cursor.close();conn.close()
    restored=page.request.get(origin+f'/api/formulas/solutions/{ident}').json()['data']
    assert restored['solution']['steps'][2]['formula']==FIXED
    page.evaluate("record=>localStorage.setItem('wisdom.tutor.history.v1',JSON.stringify([{...record,date:Date.now()}]))",record)
    page.goto(origin+'/?section=calculate' if kind=='static' else 'http://127.0.0.1:5173/calculate',wait_until='domcontentloaded')
    page.wait_for_selector('.tutor-history summary')
    page.locator('.tutor-history summary').click();page.locator('[data-history="0"]').click()
    page.locator('[data-step="2"]').click()
    assert_math(page.locator('.tutor-formula'))
    assert page.evaluate('window.StepTutor.getState().steps[2].formula')==FIXED
    page.locator('.tutor-more summary').click()
    with page.expect_download() as downloaded:page.locator('[data-action=export]').click()
    exported=Path(downloaded.value.path()).read_text(encoding='utf-8')
    assert FIXED in exported and BROKEN not in exported
    page.locator('.tutor-stage').screenshot(path=f'tests/artifacts/latex-step-fixed-{kind}.png')
    page.evaluate("async id=>{const m=await import('/static/js/solution-library.js');await m.openSavedSolution(id)}",ident)
    page.locator('[data-reader-step="2"]').click()
    assert_math(page.locator('.reader-step .tutor-formula'))
    page.locator('[data-reader=open]').click()
    page.locator('[data-step="2"]').click();assert_math(page.locator('.tutor-formula'))
    page.reload();page.wait_for_selector('.step-tutor')
    page.locator('.tutor-history summary').click();page.locator('[data-history="0"]').click()
    page.locator('[data-step="2"]').click();assert_math(page.locator('.tutor-formula'))


def test_shared_formula_corpus_and_developer_preview(teaching_page):
    page,_,kind=teaching_page
    corpus=[FIXED,r'\frac{\sqrt{x^2+1}}{2}',r'\int_0^1 x^2\,dx=\frac{1}{3}',
            r'\begin{bmatrix}a&b\\c&d\end{bmatrix}',r'\begin{cases}x^2&x\ge0\\-x&x<0\end{cases}',
            r'\begin{aligned}a&=b+c\\d&=e\end{aligned}',r'\vec{v}=\begin{pmatrix}1\\2\end{pmatrix}',
            r'\lim_{x\to0}\frac{\sin x}{x}=1',r'\sum_{n=1}^{\infty}\frac{1}{n^2}=\frac{\pi^2}{6}']
    page.wait_for_function('!!window.katex && !!window.renderMathInElement')
    report=page.evaluate(r'''async formulas=>{
        const m=await import('/static/js/math-text.js');const host=document.createElement('section');host.id='qa-math';document.body.append(host);
        for(const f of formulas){const el=document.createElement('div');host.append(el);m.renderFormula(el,f);const prose=document.createElement('p');host.append(prose);m.textWithMath(prose,'推导 $'+f+'$，成立。');}
        const result={errors:host.querySelectorAll('.math-render-error,.katex-error').length,count:host.querySelectorAll('.katex').length};
        const late=document.createElement('div');host.append(late);const katex=window.katex;window.katex=null;m.renderFormula(late,'x^2');window.dispatchEvent(new Event('math-renderer-ready'));window.katex=katex;window.dispatchEvent(new Event('math-renderer-ready'));result.late=!!late.querySelector('.katex');
        const invalid=document.createElement('div');host.append(invalid);m.renderFormula(invalid,String.raw`\unknown{x}`);result.invalid=invalid.classList.contains('math-render-error')&&!invalid.querySelector('.katex');
        host.remove();return result;
    }''',corpus)
    assert report=={'errors':0,'count':len(corpus)*2,'late':True,'invalid':True}
    page.evaluate("window.showSection('devtools')")
    page.wait_for_function("document.querySelector('#devtools')?.dataset.devInitialized")
    for formula in [BROKEN,r'\[\frac{1}{2}\]',corpus[3]]:
        page.evaluate('(f)=>window.DevTools.fillLatexInDevtools(f)',formula)
        assert_math(page.locator('#dev-latex-preview'))


def test_formula_cards_share_the_same_renderer(teaching_page):
    page,origin,_=teaching_page
    username=page.request.get(origin+'/api/user/me').json()['username']
    formula=r'\[\begin{bmatrix}a&b\\c&d\end{bmatrix}\]'
    result=page.request.post(origin+'/api/formulas/save',data={'username':username,'latex':formula,'note':'矩阵 LaTeX 回归'})
    assert result.json()['status']=='success'
    page.evaluate("window.showSection('my-formulas')")
    page.wait_for_selector('.formula-card .katex')
    assert_math(page.locator('.formula-card').filter(has_text='矩阵 LaTeX 回归'))
