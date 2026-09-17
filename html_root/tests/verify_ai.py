"""Opt-in live Qwen/OCR/agent/Manim verification; uses configured backend credentials."""
import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import subprocess

import httpx
from PIL import Image, ImageDraw, ImageFont

BASE = 'http://127.0.0.1:8000'
OUT = Path(__file__).parent / 'artifacts'


def solve(client, problem, context=''):
    response = client.post(BASE + '/api/solve/stream', json={'problem': problem, 'context': context})
    response.raise_for_status()
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[-1]['type'] == 'complete', events[-1]
    return events[-1]['solution']


def main():
    OUT.mkdir(exist_ok=True)
    image = Image.new('RGB', (1200, 260), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 45)
    draw.text((30, 35), 'Solve x^2 - 5x + 6 = 0, subject to x > 2.', font=font, fill='black')
    draw.text((30, 115), 'Explain why one root is excluded.', font=font, fill='black')
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG')
    with httpx.Client(timeout=300, trust_env=False) as client:
        def recognition():
            response = client.post(BASE + '/api/detect', files={'file': ('problem.jpg', buffer.getvalue(), 'image/jpeg')})
            response.raise_for_status()
            result = response.json()
            assert result['status'] == 'success', result
            assert '2' in result['problem_text'] and ('>' in result['problem_text'] or '大于' in result['problem_text']), result
            return result

        def agent():
            response = client.post(BASE + '/api/agent/execute', json={
                'prompt': '请完整解答图片中的题目，保留所有限制条件，逐步进行可视化。',
                'image_base64': base64.b64encode(buffer.getvalue()).decode(),
            })
            response.raise_for_status()
            result = response.json()
            assert result['status'] == 'success', result
            step = next(s for s in result['steps'] if s['section'] == 'calculate')
            assert '2' in step['formula'] and ('>' in step['formula'] or '大于' in step['formula']), step
            assert step['trigger'] == 'generate', step
            solution = solve(client, step['formula'])
            return {'plan': result, 'solution': solution}

        def geometry():
            return solve(client, '证明任意三角形的三条中线交于一点，并说明交点分割中线的比例。用坐标法逐步解释，图中明确绘制三角形的三条边和中线。')

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {name: pool.submit(fn) for name, fn in [('ocr', recognition), ('agent', agent), ('geometry', geometry)]}
            results = {}
            for name, future in futures.items():
                results[name] = future.result()
                (OUT / f'verified-live-{name}.json').write_text(json.dumps(results[name], ensure_ascii=False, indent=2), encoding='utf-8')
                print(name + ': success', flush=True)

        geometry_solution = results['geometry']
        visuals = [step['visual'] for step in geometry_solution['steps'] if step['visual']['kind'] == 'geometry']
        assert visuals and all(v['segments'] is not None for v in visuals)
        rendered = None
        with client.stream('POST', BASE + '/api/solve/render', json={'solution': geometry_solution}) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith('data: '):
                    continue
                event = json.loads(line[6:])
                assert event['type'] != 'error', event
                if event['type'] == 'progress':
                    print('Manim chapter:', event['chapter'] + 1, '/', event['total'], flush=True)
                if event['type'] == 'complete':
                    rendered = event
        assert rendered is not None
        video = Path(__file__).resolve().parents[1] / 'static' / rendered['video_url'].lstrip('/')
        metadata = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=width,height', '-of', 'json', str(video)]))
        assert abs(float(metadata['format']['duration']) - 5 * len(geometry_solution['steps'])) < .1
        subprocess.run(['ffmpeg', '-y', '-ss', str(float(metadata['format']['duration']) - 1), '-i', str(video), '-frames:v', '1', str(OUT / 'verified-live-geometry.png'), '-loglevel', 'error'], check=True)
        report = {'ocr': 'success', 'image_agent_to_solver': 'success', 'geometry_solver': 'success', 'render': rendered, 'metadata': metadata}
        (OUT / 'verified-live-ai-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'video': rendered['video_url'], 'duration': metadata['format']['duration']}), flush=True)


if __name__ == '__main__':
    main()
