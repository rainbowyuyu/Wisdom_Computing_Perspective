"""Official Qwen transport: Windows DPAPI or a server-owned environment key.

Windows never reuses plaintext/ambient Qwen keys; the global loader is sourced
afresh by qwen-launch.ps1. Linux deployments reuse the existing site's private
environment configuration and pass its key only to the bounded child process.
"""
from pathlib import Path
import json
import os
import re
import shutil
from urllib.parse import urlsplit

QWEN_HOME = Path.home() / '.codex' / 'tools' / 'qwen'
CONFIG_PATH = QWEN_HOME / 'config.json'
LOADER_PATH = QWEN_HOME / 'Load-Qwen.ps1'
LAUNCHER_PATH = Path(__file__).with_name('qwen-launch.ps1')
WINDOWS = os.name == 'nt'
OFFICIAL_HOSTS = frozenset({'dashscope.aliyuncs.com', 'dashscope-intl.aliyuncs.com', 'dashscope-us.aliyuncs.com'})


def official_endpoint(value):
    if not isinstance(value, str) or any(c in value for c in '\r\n\x00\\'):
        raise ValueError('official endpoint')
    url = urlsplit(value)
    if (url.scheme != 'https' or url.hostname not in OFFICIAL_HOSTS or url.username or url.password
            or url.port not in {None, 443} or url.query or url.fragment
            or url.path.rstrip('/') != '/compatible-mode/v1'):
        raise ValueError('official endpoint')
    return value.rstrip('/')


def load_settings(env, has_image=False):
    # Endpoint/protocol cannot be redirected by legacy model configuration.
    if any(name in env for name in ('VISUALIZATION_QWEN_API_KEY', 'VISUALIZATION_QWEN_API', 'VISUALIZATION_QWEN_AUTH')):
        raise ValueError('unsupported credential/protocol override')
    text_model = env.get('VISUALIZATION_QWEN_MODEL', env.get('SOLVER_MODEL', 'qwen-plus'))
    vision_model = env.get('VISUALIZATION_QWEN_VISION_MODEL', 'qwen3-vl-plus')
    for model in (text_model, vision_model):
        if not isinstance(model, str) or not re.fullmatch(r'qwen[a-z0-9][a-z0-9.-]{0,150}|qwen-[a-z0-9][a-z0-9.-]{0,149}', model):
            raise ValueError('model')
    override = env.get('VISUALIZATION_QWEN_BASE_URL')
    if not WINDOWS:
        key = next((env[name] for name in ('DASHSCOPE_API_KEY', 'QWEN_API_KEY', 'ALIYUN_KEY') if env.get(name)), '')
        if not isinstance(key, str) or not key.strip() or any(c in key for c in '\r\n\x00'):
            raise ValueError('credential')
        base = official_endpoint(override if override is not None else 'https://dashscope.aliyuncs.com/compatible-mode/v1')
        return {'model': vision_model if has_image else text_model, 'base_url': base,
                'api_key': key, 'qwen_base_override': override is not None}
    saved = json.loads(CONFIG_PATH.read_text(encoding='utf-8-sig'))
    if saved.get('provider') != 'qwen_dashscope' or saved.get('credential_format') != 'windows_dpapi_current_user':
        raise ValueError('credential format')
    credential = Path(saved['credential_file'])
    if not credential.is_file() or not 0 < credential.stat().st_size <= 65_536:
        raise ValueError('credential file')
    if not LOADER_PATH.is_file() or not LAUNCHER_PATH.is_file():
        raise ValueError('loader')
    base = official_endpoint(saved['compatible_base_url'])
    if override is not None:
        base = official_endpoint(override)
    shell = shutil.which('pwsh')
    if not shell:
        fallback = Path(os.environ.get('SYSTEMROOT', 'C:/Windows')) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
        if fallback.is_file():
            shell = str(fallback)
    if not shell:
        raise ValueError('PowerShell')
    return {'model': vision_model if has_image else text_model, 'base_url': base,
            'api_key': '', 'credential_loader': str(LOADER_PATH), 'powershell': shell,
            'qwen_base_override': override is not None}
