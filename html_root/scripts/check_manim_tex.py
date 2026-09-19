"""Run the exact website MathTex pipeline: python scripts/check_manim_tex.py."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = [
    r'\frac{1}{2}+\sqrt{3}\leqslant 4',
    r'm>4\quad\text{且}\quad m<6',
    r'\begin{cases}x^2,&x\ge0\\-x,&x<0\end{cases}',
    r'\begin{bmatrix}1&2\\3&4\end{bmatrix}',
    r'\norm{\bm{x}}=\sqrt{x^2+y^2}',
    r'P=\frac{\binom{3}{1}\binom{2}{1}}{\binom{5}{2}}=60%',
]


def worker():
    sys.path.insert(0,str(ROOT))
    from manim import tempconfig
    from logic.manim_tex import formula
    with tempfile.TemporaryDirectory(prefix='wisdom-tex-check-') as folder:
        previous=Path.cwd()
        try:
            os.chdir(folder)
            with tempconfig({'media_dir':folder}):
                for sample in SAMPLES:
                    item=formula(sample)
                    if not item.width or not item.height:raise RuntimeError('Empty formula output')
        finally:os.chdir(previous)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',action='store_true')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.worker:
        worker();return 0
    tools={name:shutil.which(name) for name in ('latex','xelatex','dvisvgm','kpsewhich')}
    result={'status':'missing','tools':tools,'samples':len(SAMPLES),'compile_passed':False}
    if tools['xelatex'] and tools['dvisvgm']:
        try:
            completed=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker'],cwd=ROOT,
                env={**os.environ,'PYTHONIOENCODING':'utf-8'},capture_output=True,encoding='utf-8',errors='replace',timeout=180)
            result['compile_passed']=completed.returncode==0
            result['status']='ready' if result['compile_passed'] else 'existing-partial'
            if completed.returncode:result['detail']=(completed.stderr+'\n'+completed.stdout)[-3500:]
        except subprocess.TimeoutExpired:
            result.update(status='existing-partial',detail='TeX 自检超时，请检查宏包下载、字体缓存与编译器配置。')
    if args.json:print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        print('Manim TeX: '+result['status'])
        for name,path in tools.items():print(f'{name}: {path or "未找到"}')
        print(f'中文、分段、矩阵等 {len(SAMPLES)} 组真实排版：'+('通过' if result['compile_passed'] else '未通过'))
        if result.get('detail'):print(result['detail'])
    return 0 if result['compile_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
