"""A private, bounded native DSH Agent runner; provider settings are read afresh.

Only this server module handles credentials. The child receives them in its
environment, never argv, prompts, browser responses, or audit files.
"""
from __future__ import annotations

import base64
from contextlib import closing
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import subprocess
import threading
import time
import tomllib
from urllib.parse import urlsplit
from uuid import uuid4

from configuration import load_settings, data_directory, ai_enabled
from runtime import qwen

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'runtime' / 'bridge.mjs'
HARNESS_VERSION = '0.2.0-rc.2'
MAX_STEPS = 3
DEADLINE_SECONDS = 120
MAX_OUTPUT_TOKENS = 8192
PROVIDERS = {'chatgpt': 'ChatGPT', 'claude': 'Claude', 'qwen': 'Qwen'}


class PlannerError(Exception):
    """A fixed, safe public message, never the original upstream exception."""
    def __init__(self, message, code='PROVIDER_ERROR'):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProviderConfig:
    model: str
    base_url: str
    api: str
    api_key: str = field(repr=False)
    bearer_auth: bool = False
    effort: str = 'low'
    provider: str = ''
    credential_loader: str | None = None
    powershell: str | None = None
    qwen_base_override: bool = False


def _settings():
    # No interpolation: a project .env must never expand unrelated credentials.
    return load_settings(ROOT)


def _json_file(path, optional=False):
    path = Path(path)
    if optional and not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _endpoint(value):
    if not isinstance(value, str):
        raise ValueError('endpoint')
    url = urlsplit(value)
    if (url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password
            or url.query or url.fragment or any(c in value for c in '\r\n\x00')):
        raise ValueError('endpoint')
    if url.scheme == 'http' and url.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise ValueError('tls')
    return value.rstrip('/')


def _codex_route(text):
    data = tomllib.loads(text)
    route = data['model_providers'][data['model_provider']]
    protocol = {'responses': 'openai-responses', 'chat': 'openai-completions'}.get(route.get('wire_api', 'responses'))
    if not protocol:
        raise ValueError('protocol')
    return {'model': data['model'], 'base_url': _endpoint(route['base_url']),
            'api': protocol, 'effort': data.get('model_reasoning_effort', 'low')}


def _active_codex_settings(env):
    switch = Path.home() / '.cc-switch'
    db_path = Path(env.get('CC_SWITCH_DB_PATH', switch / 'cc-switch.db')).resolve()
    settings = _json_file(env.get('CC_SWITCH_SETTINGS_PATH', switch / 'settings.json'), optional=True)
    with closing(sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
        rows = db.execute("SELECT id, settings_config, is_current FROM providers WHERE app_type='codex'").fetchall()
    selected = [r for r in rows if r[0] == settings.get('currentProviderCodex')]
    if not selected:
        selected = [r for r in rows if r[2]]
    if len(selected) != 1:
        raise ValueError('active provider')
    saved = json.loads(selected[0][1])
    route = _codex_route(saved['config'])
    live_path = Path(env.get('CC_SWITCH_CODEX_CONFIG', Path.home() / '.codex' / 'config.toml'))
    if live_path.is_file():
        live = _codex_route(live_path.read_text(encoding='utf-8-sig'))
        if live['base_url'] == route['base_url']:
            route = live
    return ProviderConfig(**route, api_key=saved['auth']['OPENAI_API_KEY'])


def _load_provider(provider, env=None, has_image=False):
    if provider not in PROVIDERS:
        raise PlannerError('请选择 ChatGPT、Claude 或 Qwen。', 'INVALID_PROVIDER')
    env = _settings() if env is None else env
    if not ai_enabled(env):
        raise PlannerError('模型创作暂时关闭，已有作品与示例仍可使用。', 'AI_DISABLED')
    try:
        if provider == 'qwen':
            return ProviderConfig(**qwen.load_settings(env, has_image), api='openai-completions',
                                  effort='off', provider='qwen')
        prefix = 'VISUALIZATION_' + provider.upper() + '_'
        values = [env.get(prefix + key) for key in ('MODEL', 'BASE_URL', 'API_KEY')]
        if any(value is not None for value in values):
            if not all(values):
                raise ValueError('partial override')
            config = ProviderConfig(values[0], values[1], env.get(prefix + 'API',
                'anthropic-messages' if provider == 'claude' else 'openai-responses'), values[2],
                provider == 'claude' and env.get(prefix + 'AUTH', 'bearer') == 'bearer',
                env.get(prefix + 'EFFORT', 'low'))
        elif provider == 'chatgpt':
            config = _active_codex_settings(env)
        else:
            saved = _json_file(env.get('CC_SWITCH_CLAUDE_SETTINGS', Path.home() / '.claude' / 'settings.json'))
            source = saved['env']
            # Explicitly blank AUTH_TOKEN is authoritative and must fail closed.
            token = source.get('ANTHROPIC_AUTH_TOKEN', source.get('ANTHROPIC_API_KEY'))
            model = saved.get('model') or source.get('ANTHROPIC_MODEL') or source.get('ANTHROPIC_DEFAULT_OPUS_MODEL')
            aliases = {'opus': 'ANTHROPIC_DEFAULT_OPUS_MODEL', 'sonnet': 'ANTHROPIC_DEFAULT_SONNET_MODEL', 'haiku': 'ANTHROPIC_DEFAULT_HAIKU_MODEL'}
            if model in aliases:
                model = source.get(aliases[model], model)
            effort = saved.get('modelSettings', {}).get(model, {}).get('effortLevel') or source.get('CLAUDE_CODE_EFFORT_LEVEL', 'low')
            config = ProviderConfig(model, source['ANTHROPIC_BASE_URL'], 'anthropic-messages', token,
                                    'ANTHROPIC_AUTH_TOKEN' in source, effort)
        _endpoint(config.base_url)
        if config.api not in {'openai-responses', 'openai-completions', 'anthropic-messages'}:
            raise ValueError('protocol')
        if not isinstance(config.model, str) or not config.model.strip() or len(config.model) > 160 or re.search(r'[\r\n\x00]', config.model):
            raise ValueError('model')
        if not isinstance(config.api_key, str) or not config.api_key.strip() or re.search(r'[\r\n\x00]', config.api_key):
            raise ValueError('credential')
        if config.effort not in {'off','minimal','low','medium','high','xhigh','max','ultra'}:
            raise ValueError('effort')
        return config
    except PlannerError:
        raise
    except Exception:
        if provider == 'qwen':
            raise PlannerError('Qwen 连接尚未配置：Windows 请检查全局 Qwen 配置；服务器请检查 DashScope 密钥与官方区域设置。', 'NOT_CONFIGURED') from None
        raise PlannerError(f'{PROVIDERS[provider]} 尚未配置可用的服务端连接，请检查 CC Switch 或项目 .env。', 'NOT_CONFIGURED') from None


def _runtime(env=None):
    env = _settings() if env is None else env
    node = env.get('VISUALIZATION_NODE') or shutil.which('node')
    package = ROOT / 'node_modules' / '@deepseek-ai' / 'dsh' / 'package.json'
    try:
        if not node or not BRIDGE.is_file() or _json_file(package)['version'] != HARNESS_VERSION:
            raise ValueError('runtime')
    except (OSError, ValueError, KeyError):
        raise PlannerError('可视化运行时尚未安装，请先运行 npm ci。', 'RUNTIME_UNAVAILABLE') from None
    return str(node)


def capabilities():
    """Configuration only: no model request, discovery, or provider network probe."""
    env = _settings()
    try:
        _runtime(env)
        ready = True
    except PlannerError:
        ready = False
    results = []
    for ident, name in PROVIDERS.items():
        try:
            _load_provider(ident, env)
            available, message = ready, '已配置' if ready else '可视化运行时待安装'
            if ident == 'qwen' and ready:
                message = '已配置，远端认证与模型权限未验证'
        except PlannerError as error:
            available, message = False, str(error)
        results.append({'id': ident, 'name': name, 'available': available, 'message': message})
    return results


def _child_environment(config, task_id):
    allowed = {'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','TEMP','TMP','LANG','LC_ALL','SSL_CERT_FILE','SSL_CERT_DIR'}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update({'DSH_VISUALIZATION_API_KEY': config.api_key, 'DSH_VISUALIZATION_BASE_URL': config.base_url,
                'DSH_VISUALIZATION_MODEL': config.model, 'DSH_VISUALIZATION_API': config.api,
                'DSH_VISUALIZATION_EFFORT': config.effort,
                'DSH_VISUALIZATION_BEARER': '1' if config.bearer_auth else '0',
                'DSH_VISUALIZATION_TASK_ID': task_id,
                'DSH_HOME': str(data_directory(_settings(), ROOT) / 'dsh-home'), 'DSH_TELEMETRY_MODE': 'DISABLED', 'NO_COLOR': '1'})
    if config.provider == 'qwen':
        if config.credential_loader:
            env.pop('DSH_VISUALIZATION_API_KEY', None)
        env['DSH_VISUALIZATION_PROVIDER'] = 'qwen'
        env['DSH_VISUALIZATION_QWEN_BASE_OVERRIDE'] = '1' if config.qwen_base_override else '0'
    return env


def _launch_command(config, node):
    if config.provider == 'qwen' and config.credential_loader:
        if not config.powershell or not config.credential_loader:
            raise PlannerError(PUBLIC_ERRORS['QWEN_NOT_CONFIGURED'], 'QWEN_NOT_CONFIGURED')
        return [config.powershell, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(qwen.LAUNCHER_PATH),
                '-LoaderPath', config.credential_loader, '-NodePath', node, '-BridgePath', str(BRIDGE)]
    return [node, str(BRIDGE)]


def _kill_tree(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        executable = Path(os.environ.get('SYSTEMROOT', 'C:/Windows')) / 'System32' / 'taskkill.exe'
        try:
            subprocess.run([str(executable), '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


PUBLIC_ERRORS = {
    'AUTH': '所选模型的连接认证失败，请检查对应的服务端凭据与账户区域。',
    'QWEN_NOT_CONFIGURED': 'Qwen 密钥加载失败，请检查当前环境的服务端配置。',
    'RATE_LIMIT': '所选模型暂时繁忙，请稍后重试。',
    'QUOTA': '所选模型的额度不足，请检查服务端账户。',
    'MAX_TOKENS': '规划未完整生成，请减少内容后重试。',
    'INVALID_IMAGE': '图片无法解析，请使用清晰的 PNG、JPEG 或 WebP 图片。',
    'INVALID_OUTPUT': '模型未生成有效场景，请把目标描述得更具体后重试。',
    'REQUEST_LIMIT': '本次规划已达到三步上限，请缩小任务后重试。',
    'TOOL_LIMIT': '本次规划已达到工具调用上限。',
    'TIMEOUT': '场景规划已达到两分钟时限，请缩小内容后重试。',
    'CANCELLED': '本次规划已取消。',
    'RUNTIME_UNAVAILABLE': '可视化运行时尚未就绪，请检查本地安装。',
}


def _previous_context(previous):
    """Bound model context without changing the full scene held by the project.

    Trusted physics builders may produce tens of thousands of samples. They are
    rendering evidence, not useful tokens for the next editing instruction.
    """
    if previous is None:
        return None
    if not isinstance(previous, dict):
        raise PlannerError('此前场景数据无效或过大。', 'INVALID_INPUT')

    def sample(values, limit):
        if len(values) <= limit:
            return values
        return [values[round(i * (len(values)-1) / (limit-1))] for i in range(limit)]

    def compact(value, depth=0):
        if depth > 30:
            raise ValueError('depth')
        if isinstance(value, list):
            return [compact(v, depth+1) for v in value]
        if not isinstance(value, dict):
            return value
        if 'objects' in value and isinstance(value['objects'], list):
            result = {k:compact(v, depth+1) for k,v in value.items() if k != 'objects' and v is not None}
            objects=[]
            for obj in value['objects']:
                if not isinstance(obj,dict):
                    raise ValueError('object')
                reduced = {k:compact(v,depth+1) for k,v in obj.items() if k not in {'frames','points'} and v is not None}
                counts={}
                for name,limit in [('frames',6),('points',48)]:
                    values=obj.get(name) or []
                    if name=='frames' and len(values)>limit:
                        # Frames are sparse patches. Carry each property forward
                        # before sampling so omitted intermediate assignments do
                        # not disappear from the model's compact context.
                        carried={};expanded=[]
                        for frame in values:
                            carried.update({k:v for k,v in frame.items() if k!='t' and v is not None})
                            expanded.append({'t':frame['t'],**carried})
                        reduced[name]=compact(sample(expanded,limit),depth+1)
                    else:reduced[name]=compact(sample(values,limit),depth+1)
                    if len(values)>limit:
                        counts[name+'_original_count']=len(values)
                if counts:
                    reduced['_summary']={**counts,'sampling':'uniform; omitted samples remain in the original project'}
                objects.append(reduced)
            result['objects']=objects
            result['_context_summary']='Original rendering data retained in project. This context omits null fields and uniformly samples long paths/keyframes; it is not an exact replacement scene. Controls and interaction bindings are retained. Preserve meaningful interaction freedoms and the recipe; recompute trusted physics instead of treating sampled frames as complete.'
            return result
        return {k:compact(v,depth+1) for k,v in value.items() if v is not None}

    try:
        result=compact(previous)
        encoded=json.dumps(result,ensure_ascii=False,allow_nan=False)
        if len(encoded.encode('utf-8'))>500_000:
            raise ValueError('size')
        return result
    except (ValueError,TypeError,OverflowError,RecursionError):
        raise PlannerError('此前场景数据无效或过大。', 'INVALID_INPUT') from None


def _invoke(config, node, payload, cancelled, on_event):
    try:payload_bytes=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode('utf-8')
    except (ValueError,TypeError,OverflowError,RecursionError):
        raise PlannerError('此前场景数据无效或过大。','INVALID_INPUT') from None
    if len(payload_bytes)>8_000_000:
        raise PlannerError('完整改稿上下文超过本地运行时上限，请先简化当前场景。','INVALID_INPUT')
    task_id = 'visual-' + uuid4().hex
    process = subprocess.Popen(_launch_command(config, node), cwd=ROOT, env=_child_environment(config, task_id),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), start_new_session=os.name != 'nt')
    started = time.monotonic()
    overflow = threading.Event()
    records = []

    def consume():
        size = 0
        try:
            while True:
                line = process.stdout.readline(8_000_001)
                if not line:
                    break
                size += len(line)
                if size > 8_000_000 or len(line) > 8_000_000:
                    overflow.set()
                    continue
                try:
                    item = json.loads(line)
                    if item.get('type') == 'event':
                        stage = item.get('stage')
                        # Callback messages are host-owned; never relay arbitrary stdout.
                        messages = {'planning':'正在理解内容并选择可视化方式。','checking':'正在检查场景结构与动画约束。','finalizing':'正在整理可编辑的可视化方案。'}
                        if on_event and stage in messages:
                            try:
                                on_event({'stage': stage, 'message': messages[stage]})
                            except Exception:
                                # Progress delivery must not strand the child's pipe.
                                pass
                    elif item.get('type') == 'result':
                        records.append(item)
                except (ValueError, UnicodeError, AttributeError):
                    overflow.set()
        finally:
            process.stdout.close()

    def discard():
        size = 0
        try:
            while chunk := process.stderr.read(8192):
                size += len(chunk)
                if size > 131_072:
                    overflow.set()
        finally:
            process.stderr.close()

    def send():
        try:
            process.stdin.write(payload_bytes)
        except (BrokenPipeError, OSError):
            pass
        finally:
            process.stdin.close()

    threads = [threading.Thread(target=consume, daemon=True), threading.Thread(target=discard, daemon=True), threading.Thread(target=send, daemon=True)]
    for thread in threads:
        thread.start()
    try:
        while True:
            if cancelled is not None and cancelled.is_set():
                raise PlannerError(PUBLIC_ERRORS['CANCELLED'], 'CANCELLED')
            if time.monotonic() - started >= DEADLINE_SECONDS:
                raise PlannerError(PUBLIC_ERRORS['TIMEOUT'], 'TIMEOUT')
            if overflow.is_set():
                raise PlannerError(PUBLIC_ERRORS['INVALID_OUTPUT'], 'INVALID_OUTPUT')
            if process.poll() is not None:
                break
            overflow.wait(.05)
        for thread in threads:
            thread.join(timeout=2)
        if overflow.is_set() or len(records) != 1:
            raise PlannerError('可视化运行时未返回完整结果。', 'RUNTIME_ERROR')
        result = records[0]
        if process.returncode or not result.get('ok'):
            code = result.get('code')
            if code not in PUBLIC_ERRORS and code not in {'NETWORK','SERVER_ERROR','PROVIDER_ERROR'}:
                code = 'PROVIDER_ERROR'
            raise PlannerError(PUBLIC_ERRORS.get(code, '所选模型暂时无法完成场景规划，请稍后重试。'), code)
        if not isinstance(result.get('proposal'), dict):
            raise PlannerError(PUBLIC_ERRORS['INVALID_OUTPUT'], 'INVALID_OUTPUT')
        return result['proposal']
    finally:
        _kill_tree(process)
        for thread in threads:
            thread.join(timeout=2)


def plan(prompt, provider, asset_path=None, duration=12, previous=None, cancelled=None, on_event=None):
    """Return an untrusted Proposal mapping. The caller validates/builds it again."""
    if cancelled is not None and cancelled.is_set():
        raise PlannerError(PUBLIC_ERRORS['CANCELLED'], 'CANCELLED')
    if not isinstance(prompt, str) or len(prompt) > 6000 or not (prompt.strip() or asset_path):
        raise PlannerError('请提供图片或不超过 6000 字的可视化内容。', 'INVALID_INPUT')
    if duration not in {12, 20, 30}:
        raise PlannerError('请选择 12、20 或 30 秒动画。', 'INVALID_INPUT')
    from server.schema import Proposal
    image_data_url = None
    asset_id = None
    if asset_path:
        # This is a trusted server argument; never accepted from model/tool input.
        path = Path(asset_path)
        try:
            if path.stat().st_size > 5_242_880:
                raise ValueError('size')
            from PIL import Image
            with Image.open(path) as source:
                media = {'PNG':'image/png','JPEG':'image/jpeg','WEBP':'image/webp'}[source.format]
                if source.width * source.height > 20_000_000:
                    raise ValueError('pixels')
            image_data_url = 'data:' + media + ';base64,' + base64.b64encode(path.read_bytes()).decode('ascii')
            asset_id = path.stem if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', path.stem) else 'uploaded-image'
        except Exception:
            raise PlannerError(PUBLIC_ERRORS['INVALID_IMAGE'], 'INVALID_IMAGE') from None
    previous_exact=previous
    previous = _previous_context(previous)
    env = _settings()
    config, node = _load_provider(provider, env, bool(image_data_url)), _runtime(env)
    payload = {'prompt': prompt, 'duration': duration, 'previous': previous,
               'previous_exact':previous_exact,
               'image_data_url': image_data_url, 'asset_id': asset_id,
               'schema': Proposal.model_json_schema(), 'max_tokens': MAX_OUTPUT_TOKENS,
               'max_steps': MAX_STEPS, 'deadline_ms': DEADLINE_SECONDS * 1000}
    return _invoke(config, node, payload, cancelled, on_event)
