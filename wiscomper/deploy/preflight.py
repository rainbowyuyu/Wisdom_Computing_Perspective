"""Read-only checks before replacing a legacy Wiscomper installation.

This module never imports server.app, opens the workbench Store, sends mail or
calls a model. MySQL receives one information_schema SELECT and no DDL/DML.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys

# Run from a deployment ZIP's payload/deploy directory before copying the app.
APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from configuration import ai_enabled, load_settings, server_port
from runtime.qwen import official_endpoint
from server.site import validate_public_url


REQUIRED_COLUMNS = {
    'users': {'id', 'username', 'hashed_password', 'email', 'email_verified', 'email_verified_at', 'created_at'},
    'account_access': {'user_id', 'role', 'disabled', 'daily_limit', 'updated_at'},
    'account_email_codes': {'id', 'user_id', 'email', 'purpose', 'code_hash', 'expires_at',
                            'consumed_at', 'attempts', 'requester_ip_hash', 'created_at'},
    'account_email_limits': {'bucket', 'window_start', 'used'},
}


def _mysql_schema(settings, add, connect=None):
    missing = [key for key in ('LEGACY_MYSQL_HOST', 'LEGACY_MYSQL_USER', 'LEGACY_MYSQL_DATABASE')
               if not settings.get(key)]
    if missing:
        add('error', 'MYSQL_CONFIG_MISSING', '数据库配置缺少：' + '、'.join(missing))
        return
    try:
        port = int(settings.get('LEGACY_MYSQL_PORT') or 3306)
        if not 1 <= port <= 65535:
            raise ValueError
    except (ValueError, TypeError):
        add('error', 'MYSQL_PORT_INVALID', '数据库端口无效，请检查 MYSQL_PORT。')
        return
    connection = cursor = None
    try:
        if connect is None:
            import mysql.connector
            connect = mysql.connector.connect
        connection = connect(host=settings['LEGACY_MYSQL_HOST'], port=port,
                             user=settings['LEGACY_MYSQL_USER'],
                             password=settings.get('LEGACY_MYSQL_PASSWORD') or '',
                             database=settings['LEGACY_MYSQL_DATABASE'],
                             connection_timeout=5, autocommit=True, charset='utf8mb4')
        cursor = connection.cursor()
        tables = tuple(REQUIRED_COLUMNS)
        cursor.execute('SELECT TABLE_NAME,COLUMN_NAME FROM information_schema.COLUMNS '
                       'WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN (' + ','.join(['%s'] * len(tables)) + ')',
                       (settings['LEGACY_MYSQL_DATABASE'], *tables))
        actual = {table: set() for table in tables}
        for table, column in cursor.fetchall():
            if table in actual:
                actual[table].add(column)
        missing = [f'{table}.{column}' for table, columns in REQUIRED_COLUMNS.items()
                   for column in sorted(columns - actual[table])]
        if missing:
            add('error', 'MYSQL_SCHEMA_MISSING', '旧数据库缺少必要字段：' + '、'.join(missing)
                + '。未修改数据库，请先核对旧站邮箱及权限迁移。')
        else:
            add('ok', 'MYSQL_SCHEMA_READY', '旧数据库的账号、权限和邮箱验证表结构可用；未改动数据。')
    except ImportError:
        add('error', 'MYSQL_DRIVER_MISSING', '缺少 mysql-connector-python，请先安装部署依赖。')
    except Exception as error:
        # Do not disclose driver exception text, hosts, usernames or credentials.
        code = {1045: 'MYSQL_AUTH_FAILED', 1049: 'MYSQL_DATABASE_MISSING',
                1044: 'MYSQL_ACCESS_DENIED', 2003: 'MYSQL_CONNECT_FAILED',
                2005: 'MYSQL_CONNECT_FAILED'}.get(getattr(error, 'errno', None), 'MYSQL_CHECK_FAILED')
        add('error', code, '无法只读检查旧数据库，请核对服务器连接配置、授权和数据库服务。')
    finally:
        for resource in (cursor, connection):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    pass


def check_deployment(target, site_url='https://www.wiscomper.com', port=8000, *,
                     environ=None, connect=None, which=shutil.which, find_spec=importlib.util.find_spec):
    """Return safe findings; injectable connections let tests avoid real MySQL."""
    findings = []

    def add(level, code, message):
        findings.append({'level': level, 'code': code, 'message': message})

    target = Path(target)
    if not target.is_absolute() or not target.is_dir():
        add('error', 'TARGET_INVALID', '目标必须是已存在网站目录的绝对路径。')
        return {'ok': False, 'checks': findings}
    if not any((target / name).is_file() for name in ('.env', '.env.local')):
        add('error', 'ENV_MISSING', '目标网站没有 .env 或 .env.local；不会用本机配置替代。')
        return {'ok': False, 'checks': findings}
    try:
        expected_site = validate_public_url(site_url)
        if not expected_site:
            raise ValueError
        expected_port = server_port({'VISUALIZE_PORT': str(port)})
    except (ValueError, TypeError):
        add('error', 'DEPLOY_ARGUMENT_INVALID', '部署域名必须是正式 HTTPS 域名根地址，端口须为 1–65535。')
        return {'ok': False, 'checks': findings}
    defaults = {'PUBLIC_SITE_URL': expected_site, 'VISUALIZE_PORT': str(expected_port),
                'VISUALIZE_DATA': str(target / 'var' / 'wiscomper-harness'), 'LEGACY_ACCOUNT_BACKEND': 'mysql'}
    try:
        settings = {**defaults, **load_settings(root=target, environ=environ)}
    except Exception:
        add('error', 'ENV_READ_FAILED', '无法读取服务器配置文件；未修改任何配置。')
        return {'ok': False, 'checks': findings}
    try:
        actual_site = validate_public_url(settings.get('PUBLIC_SITE_URL'))
        if not actual_site or actual_site != expected_site:
            raise ValueError
        add('ok', 'PUBLIC_SITE_READY', '公网域名配置与本次部署一致。')
    except (ValueError, TypeError):
        add('error', 'PUBLIC_SITE_CONFLICT', '现有 PUBLIC_SITE_URL 与本次部署不一致或为空，请先核对；不会以本机模式上线。')
    try:
        if server_port(settings) != expected_port:
            raise ValueError
        add('ok', 'PORT_READY', '有效监听端口与部署参数一致。')
    except (ValueError, TypeError):
        add('error', 'PORT_CONFLICT', '现有 PORT / VISUALIZE_PORT 与本次部署端口不一致，请核对代理和部署参数。')
    if settings.get('LEGACY_ACCOUNT_BACKEND') != 'mysql':
        add('error', 'ACCOUNT_BACKEND_CONFLICT', '保留旧账号的部署必须使用 MySQL，不能切换为空白 SQLite 账号库。')
    else:
        _mysql_schema(settings, add, connect)

    smtp_missing = [key for key in ('SMTP_HOST',) if not settings.get(key)]
    if not (settings.get('SMTP_FROM') or settings.get('SMTP_USERNAME')):
        smtp_missing.append('SMTP_FROM')
    if settings.get('SMTP_USERNAME') and not settings.get('SMTP_PASSWORD'):
        smtp_missing.append('SMTP_PASSWORD')
    secret = settings.get('EMAIL_CODE_SECRET') or ''
    if not isinstance(secret, str) or len(secret) < 32 or secret.startswith('replace_'):
        smtp_missing.append('EMAIL_CODE_SECRET')
    try:
        if not 1 <= int(settings.get('SMTP_PORT') or 465) <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        smtp_missing.append('SMTP_PORT')
    if str(settings.get('SMTP_USE_TLS', '1')).lower() in {'0', 'false', 'no'}:
        smtp_missing.append('SMTP_USE_TLS')
    if smtp_missing or settings.get('SMTP_HOST') == 'smtp.example.com':
        add('warning', 'SMTP_NOT_READY', '邮箱验证码配置待完善：' + '、'.join(smtp_missing or ['SMTP_HOST']) + '。密码登录仍可用，未发送测试邮件。')
    else:
        add('ok', 'SMTP_CONFIG_PRESENT', '邮箱配置字段齐全；本检查不连接邮箱服务器、不发送邮件。')
    if not settings.get('GITHUB_CLIENT_ID') or not settings.get('GITHUB_CLIENT_SECRET'):
        add('warning', 'GITHUB_NOT_CONFIGURED', 'GitHub 登录尚未配置完整；请使用邮箱或用户名登录。')
    else:
        add('ok', 'GITHUB_CONFIG_PRESENT', 'GitHub 配置字段齐全；仍需确认 OAuth 应用回调使用本次正式域名。')

    if not ai_enabled(settings):
        add('warning', 'AI_DISABLED', '沿用 AI_ENABLED=0：模型创作已暂停，内置示例和已有作品仍可浏览。')
    else:
        key = next((settings[name] for name in ('DASHSCOPE_API_KEY', 'QWEN_API_KEY', 'ALIYUN_KEY') if settings.get(name)), '')
        if not isinstance(key, str) or not key.strip() or any(c in key for c in '\r\n\x00'):
            add('error', 'QWEN_KEY_MISSING', '服务器缺少 Qwen 密钥，请在原私有配置中设置 ALIYUN_KEY 或 DASHSCOPE_API_KEY。')
        else:
            try:
                official_endpoint(settings.get('VISUALIZATION_QWEN_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'))
                if any(name in settings for name in ('VISUALIZATION_QWEN_API_KEY', 'VISUALIZATION_QWEN_API', 'VISUALIZATION_QWEN_AUTH')):
                    raise ValueError
                add('ok', 'QWEN_CONFIG_PRESENT', 'Qwen 服务器密钥字段及官方地址已配置；未调用模型，未验证远端权限。')
            except (ValueError, TypeError):
                add('error', 'QWEN_CONFIG_INVALID', 'Qwen 只支持官方 DashScope 地址和标准服务器密钥字段，请核对区域配置。')
    missing_tools = [name for name in ('ffmpeg', 'latex', 'dvisvgm') if not which(name)]
    if missing_tools:
        add('warning', 'RENDER_TOOLS_MISSING', '可选视频导出工具未齐全：' + '、'.join(missing_tools) + '。网页交互可视化不受影响。')
    if find_spec('playwright') is None:
        add('warning', 'PLAYWRIGHT_MISSING', '未安装 Playwright，浏览器视频导出不可用。')
    else:
        add('warning', 'CHROMIUM_NEEDS_CHECK', '视频导出还需为实际服务用户安装 Playwright Chromium 和系统依赖；本检查不启动浏览器。')
    if find_spec('manim') is None:
        add('warning', 'MANIM_MISSING', '未安装可选 Manim 后端，二维/三维网页交互仍可使用。')
    return {'ok': not any(item['level'] == 'error' for item in findings), 'checks': findings}


def main(argv=None):
    parser = argparse.ArgumentParser(description='只读检查旧站配置与 MySQL 表结构；不会修改数据库。')
    parser.add_argument('--target', required=True)
    parser.add_argument('--site-url', default='https://www.wiscomper.com')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    result = check_deployment(args.target, args.site_url, args.port)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in result['checks']:
            print(f'[{item["level"].upper()}] {item["code"]}: {item["message"]}')
        print('部署检查通过（提示项请按说明处理）。' if result['ok'] else '部署检查未通过；旧网站尚未被替换。')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
