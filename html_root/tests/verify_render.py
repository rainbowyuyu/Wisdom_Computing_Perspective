"""Live Manim integration check. Requires backend on port 8000 and ffprobe."""
import json
from pathlib import Path
import subprocess
import time

import httpx

ARTIFACTS = Path(__file__).parent / 'artifacts'
ARTIFACTS.mkdir(exist_ok=True)
BASE = 'http://127.0.0.1:8000'


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]


def main():
    report = []
    with httpx.Client(timeout=300, trust_env=False) as client:
        for name, problem in [('equation', 'x^2-5*x+6=0'), ('matrix','矩阵 [[1,2],[0,1]]'), ('integral', r'\int_0^1 x^{2}+3x\,dx'), ('derivative', '求导 x^2'), ('geometry', None)]:
            if problem:
                solution = events(client.post(BASE+'/api/solve/stream', json={'problem':problem}))[-1]['solution']
            else:
                # Known coordinates exercise the geometry renderer; this is not an AI integration test.
                visual = {'kind':'geometry','points':[[0,0],[3,0],[3,4]],'labels':['A','B','C'],'segments':[[0,1],[1,2],[2,0]]}
                solution = {'title':'几何渲染测试','summary':'斜边长为 5。','source':'ai','verification':'固定 3-4-5 三角形测试数据，用于检查几何渲染。', 'steps':[
                    {'title':'绘制直角三角形','explanation':'测试坐标 A(0,0)、B(3,0)、C(3,4)，两直角边长为 3 和 4。','formula':'AB=3, BC=4','visual':visual},
                    {'title':'勾股定理','explanation':'两直角边的平方和等于斜边的平方。','formula':r'AC=\sqrt{3^2+4^2}=5','visual':visual},
                    {'title':'作斜边中线','explanation':'标记斜边中点 M，保留三角形并连接 BM。中点坐标为 $M=(1.5,2)$。','formula':r'BM=\sqrt{1.5^2+2^2}=\frac{5}{2}','visual':{**visual,'points':visual['points']+[[1.5,2]],'labels':['A','B','C','M'],'segments':visual['segments']+[[1,3]]}}]}
            started = time.monotonic()
            result = None
            with client.stream('POST', BASE+'/api/solve/render', json={'solution':solution}) as response:
                for line in response.iter_lines():
                    if not line.startswith('data: '): continue
                    event = json.loads(line[6:])
                    if event['type'] == 'error': raise RuntimeError(event['message'])
                    if event['type'] == 'complete': result = event
                    if event['type'] == 'progress': print(name, event['chapter']+1, '/', event['total'], flush=True)
            assert result is not None
            video = Path(__file__).resolve().parents[1]/'static'/result['video_url'].lstrip('/')
            metadata = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=width,height','-of','json',str(video)]))
            assert abs(float(metadata['format']['duration']) - len(solution['steps'])*5) < .1
            subprocess.run(['ffmpeg','-y','-ss',str(len(solution['steps'])*5-1),'-i',str(video),'-frames:v','1',str(ARTIFACTS/f'manim-{name}.png'),'-loglevel','error'], check=True)
            if name == 'equation': Path(__file__).with_name('render-result.json').write_text(json.dumps(result),encoding='utf-8')
            item = {'case':name,'seconds':round(time.monotonic()-started,2),'video_url':result['video_url'],'duration':metadata['format']['duration'],'chapters':len(result['chapters'])}
            report.append(item);print(json.dumps(item),flush=True)
    (ARTIFACTS/'live-render-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__ == '__main__': main()
