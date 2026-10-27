"""Stable main.py/start.py entry; keep old deployment dependencies isolated."""
import os
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent


def _deployment_environment(environment):
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(environment / '.playwright'))
    metadata = environment / 'wiscomper-runtime.json'
    if not metadata.is_file():
        return
    try:
        if metadata.stat().st_size > 16384:
            raise ValueError()
        node = Path(json.loads(metadata.read_text(encoding='utf-8'))['node'])
        if not node.is_absolute() or not node.is_file():
            raise ValueError()
    except (ValueError, OSError, KeyError, TypeError):
        raise RuntimeError('独立运行环境中的 Node 配置无效，请重新运行部署依赖准备。') from None
    os.environ.setdefault('VISUALIZATION_NODE', str(node))
    directory = str(node.parent)
    if os.environ.get('PATH', '').split(os.pathsep)[0] != directory:
        os.environ['PATH'] = directory + os.pathsep + os.environ.get('PATH', '')


def run():
    # An old Baota command can keep invoking its original Python. Switch before
    # importing any third-party module so the old environment is never modified.
    environment = ROOT / '.venv-wiscomper'
    executable = environment / 'bin' / 'python'
    if sys.platform.startswith('linux') and (ROOT / '.env.deploy').is_file():
        _deployment_environment(environment)
        if executable.is_file() and Path(sys.prefix).resolve() != environment.resolve():
            os.execv(str(executable), [str(executable), str(ROOT / 'main.py'), *sys.argv[1:]])
    from configuration import load_settings, server_port
    import uvicorn
    uvicorn.run('server.app:app',host='127.0.0.1',port=server_port(load_settings()),workers=1,proxy_headers=False,access_log=False)


if __name__=='__main__':
    run()
