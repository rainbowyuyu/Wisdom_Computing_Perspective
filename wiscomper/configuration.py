"""Read deployment defaults and existing site settings without changing files.

Canonicalize aliases per source so a process MYSQL_PASSWORD can override an
older LEGACY_MYSQL_PASSWORD in a file. Empty explicit values stay authoritative.
No interpolation is performed, especially for passwords containing dollar signs.
"""
import os
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
ALIASES = {
    'MYSQL_HOST': 'LEGACY_MYSQL_HOST',
    'MYSQL_PORT': 'LEGACY_MYSQL_PORT',
    'MYSQL_USER': 'LEGACY_MYSQL_USER',
    'MYSQL_PASSWORD': 'LEGACY_MYSQL_PASSWORD',
    'MYSQL_DB': 'LEGACY_MYSQL_DATABASE',
    'SOLVER_MODEL': 'VISUALIZATION_QWEN_MODEL',
    'PORT': 'VISUALIZE_PORT',
    'AI_GLOBAL_DAILY_CALLS': 'VISUALIZE_DAILY_CALLS',
}


def normalize_settings(values):
    result = {key: value for key, value in values.items() if value is not None}
    for old, new in ALIASES.items():
        if old in result and new not in result:
            result[new] = result[old]
    return result


def load_settings(root=None, environ=None):
    root = Path(root) if root is not None else ROOT
    result = {}
    for filename in ('.env.deploy', '.env', '.env.local'):
        result.update(normalize_settings(dotenv_values(root / filename, interpolate=False, encoding='utf-8-sig')))
    result.update(normalize_settings(os.environ if environ is None else environ))
    return result


def data_directory(settings, root=None):
    root = Path(root) if root is not None else ROOT
    value = Path(settings.get('VISUALIZE_DATA') or 'data')
    return (value if value.is_absolute() else root / value).resolve()


def server_port(settings):
    value = int(settings.get('VISUALIZE_PORT') or settings.get('PORT') or '3088')
    if not 1 <= value <= 65535:
        raise ValueError('服务端口必须介于 1 和 65535 之间。')
    return value


def ai_enabled(settings):
    return str(settings.get('AI_ENABLED', '1')).strip().lower() in {'1', 'true', 'yes', 'on'}
