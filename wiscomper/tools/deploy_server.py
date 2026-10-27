#!/usr/bin/env python3
"""Packaged as deploy.py: prepare a private runtime, then replace program files.

No SQL migrations, existing environment edits or automatic service restarts.
Run with the site stopped, using Python 3.11+ and a supported Node on PATH.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import uuid


class SetupError(RuntimeError):
    pass


def installer(package):
    spec = importlib.util.spec_from_file_location('wiscomper_install', package / 'install.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stopped(port):
    if type(port) is not int or not 1 <= port <= 65535:
        raise SetupError('部署端口无效。')
    for family, address in ((socket.AF_INET, '127.0.0.1'), (socket.AF_INET6, '::1')):
        try:
            with socket.socket(family) as probe:
                probe.settimeout(1)
                listening = probe.connect_ex((address, port)) == 0
        except OSError:
            if family == socket.AF_INET6:
                continue  # IPv6 is not available on every host.
            raise SetupError('无法检查原服务端口，请先确认站点已停止。') from None
        if listening:
            raise SetupError(f'端口 {port} 仍在运行。请先在宝塔停止原 Python 项目，再执行部署。')


@contextmanager
def operation_lock(target, api):
    """Serialize the complete wrapper, including preparation and link changes.

Use a separate lock from the code installer's short transaction lock to avoid
recursive locking. The one-command install and rollback share this lock.
"""
    import fcntl
    parent = api.check_chain(api.backup_parent(target))
    parent.mkdir(mode=0o700, exist_ok=True)
    path = api.check_chain(parent / '.runtime-lock')
    with path.open('a+b') as stream:
        os.chmod(path, 0o600)
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SetupError('另一个部署或回滚正在进行，请等待完成。') from None
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def node_supported(version):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)\s*', version)
    if not match:
        return False
    major, minor, _ = map(int, match.groups())
    return major >= 24 or major == 22 and minor >= 19


def configured_port(target, api):
    """The old service may still use 8000 while this upgrade selects a new port."""
    values = {}
    for filename in ('.env.deploy', '.env', '.env.local'):
        path = api.check_chain(target / filename)
        if path.exists():
            api.regular_file(path)
            values.update(api.config_values(path.read_text(encoding='utf-8-sig'), filename))
    values.update(api.normalize_config({key: os.environ[key] for key in ('PORT', 'VISUALIZE_PORT') if key in os.environ}))
    try:
        port = int(values.get('VISUALIZE_PORT') or 8000)
        if not 1 <= port <= 65535:
            raise ValueError
        return port
    except (ValueError, TypeError):
        raise SetupError('现有站点端口配置无效，无法确认服务已停止。') from None


def ensure_stopped(target, api, requested_port=None):
    ports = {configured_port(target, api)}
    if requested_port is not None:
        ports.add(requested_port)
    for port in sorted(ports):
        stopped(port)


def run(command, log, *, cwd=None, env=None, timeout=1200):
    # Do not display arbitrary package-manager errors, which may contain private URLs.
    with log.open('ab') as output:
        os.chmod(log, 0o600)
        try:
            subprocess.run(list(map(str, command)), cwd=cwd, env=env, stdout=output,
                           stderr=subprocess.STDOUT, check=True, timeout=timeout)
        except (subprocess.SubprocessError, OSError):
            raise SetupError(f'准备失败，原站尚未替换。请在服务器查看本地日志：{log}') from None


def service_identity(target, name=None):
    import pwd
    if name:
        try:
            account = pwd.getpwnam(name)
        except KeyError:
            raise SetupError('指定的宝塔运行用户不存在。') from None
        return account.pw_uid, account.pw_gid
    info = target.stat()
    return info.st_uid, info.st_gid


def own_tree(path, uid, gid):
    if os.geteuid() != 0:
        if uid != os.geteuid():
            raise SetupError('当前用户不能为宝塔运行用户准备目录权限，请使用有权限的用户执行。')
        return
    os.chown(path, uid, gid, follow_symlinks=False)
    for parent, directories, files in os.walk(path, followlinks=False):
        for name in directories + files:
            os.chown(Path(parent) / name, uid, gid, follow_symlinks=False)


def effective_data_directory(target, runtime, package, log):
    """Read only the shipped configuration loader in the prepared Python env."""
    code = """import importlib.util,json,sys
from pathlib import Path
try:
    spec=importlib.util.spec_from_file_location('wiscomper_configuration',sys.argv[1])
    config=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    root=Path(sys.argv[2])
    settings={'VISUALIZE_DATA':str(root/'var'/'wiscomper-harness'),**config.load_settings(root=root)}
    print(json.dumps({'path':str(config.data_directory(settings,root))}))
except Exception:
    print('CONFIGURATION_CHECK_FAILED',file=sys.stderr)
    raise SystemExit(1)
"""
    with log.open('ab') as output:
        os.chmod(log, 0o600)
        try:
            result = subprocess.run([str(runtime / 'venv/bin/python'), '-I', '-c', code,
                                     str(package / 'payload/configuration.py'), str(target)],
                                    stdout=subprocess.PIPE, stderr=output, text=True, encoding='utf-8', timeout=15)
            if result.returncode or not isinstance(result.stdout, str) or len(result.stdout) > 16384:
                raise ValueError
            value = json.loads(result.stdout)
            path = value.get('path') if isinstance(value, dict) else None
            if not isinstance(path, str) or not path or len(path) > 4096 or not Path(path).is_absolute():
                raise ValueError
            return Path(path)
        except (ValueError, OSError, subprocess.SubprocessError):
            raise SetupError('无法读取实际工作台数据目录配置，原站未替换。') from None


def check_service_access(target, runtime, uid, gid, log, package, node):
    """Check actual service-user access without reading or changing old files."""
    # A root deployment can otherwise succeed although www cannot traverse a
    # private parent or read the unchanged .env. Existing permissions stay intact.
    data_directory = effective_data_directory(target, runtime, package, log)
    code = """import os,sys
from pathlib import Path
root=Path(sys.argv[1])
ok=os.access(root,os.R_OK|os.X_OK)
for name in ('.env','.env.local','.env.deploy','main.py'):
    p=root/name
    if p.exists():ok=ok and os.access(p,os.R_OK)
data=Path(sys.argv[2])
if data.exists():ok=ok and data.is_dir() and os.access(data,os.R_OK|os.W_OK|os.X_OK)
else:
    default=data==(root/'var'/'wiscomper-harness').resolve()
    while not data.exists():data=data.parent
    ok=ok and data.is_dir() and os.access(data,os.X_OK if default else os.W_OK|os.X_OK)
raise SystemExit(0 if ok else 1)
"""
    options = {'user': uid, 'group': gid, 'extra_groups': []} if os.geteuid() == 0 else {}
    with log.open('ab') as output:
        os.chmod(log, 0o600)
        try:
            result = subprocess.run([str(runtime / 'venv/bin/python'), '-I', '-c', code, str(target), str(data_directory)],
                                    stdout=output, stderr=subprocess.STDOUT, timeout=15, **options)
            if result.returncode:
                raise SetupError('宝塔运行用户无法读取原 .env、访问站点目录或写入实际工作台数据目录；请检查 --service-user、VISUALIZE_DATA 和目录权限，原站未替换。')
            try:
                result = subprocess.run([str(node), '--version'], stdout=output, stderr=subprocess.STDOUT,
                                        timeout=15, **options)
            except (subprocess.SubprocessError, OSError):
                raise SetupError('宝塔运行用户无法执行 Node.js；请使用该用户可访问的 Node 安装，原站未替换。') from None
            if result.returncode:
                raise SetupError('宝塔运行用户无法执行 Node.js；请使用该用户可访问的 Node 安装，原站未替换。')
        except (subprocess.SubprocessError, OSError):
            raise SetupError('无法以宝塔运行用户验证目录访问权限，原站未替换。') from None


def path_identity(path):
    """Identify an existing entry without following a dependency symlink."""
    if not os.path.lexists(path):
        return None
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
        raise SetupError('运行环境路径必须是目录或目录链接。')
    return {'device': info.st_dev, 'inode': info.st_ino, 'mode': info.st_mode,
            'link': os.readlink(path) if path.is_symlink() else None}


def link_plan(target, runtime, backup):
    return [dict(name=name, destination=str(runtime / source),
                 had_original=os.path.lexists(target / name), original=path_identity(target / name))
            for name, source in (('.venv-wiscomper', 'venv'), ('node_modules', 'node/node_modules'))]


def replace_links(target, runtime, backup, receipt, install):
    state = dict(schema_version=1, target=str(target), runtime=str(runtime),
                 port=receipt['port'], links=link_plan(target, runtime, backup), state='prepared')
    install.atomic_json(backup / 'runtime-receipt.json', state)
    for entry in state['links']:
        path, previous = target / entry['name'], backup / ('previous-' + entry['name'])
        if path_identity(path) != entry['original'] or os.path.lexists(previous):
            raise SetupError('运行环境在准备过程中发生变化，未覆盖新改动。')
        if entry['had_original']:
            os.replace(path, previous)
            install.fsync_directory(backup)
            install.fsync_directory(target)
        path.symlink_to(entry['destination'], target_is_directory=True)
        install.fsync_directory(target)
    state['state'] = 'installed'
    install.atomic_json(backup / 'runtime-receipt.json', state)


def runtime_rollback_plan(target, backup, state):
    if state.get('schema_version') != 1 or state.get('target') != str(target):
        raise SetupError('运行环境回滚记录不匹配。')
    runtime = Path(state.get('runtime', ''))
    if (not runtime.is_absolute() or runtime.name in {'.', '..', ''}
            or runtime.parent != target.with_name(target.name + '.deploy-runtimes')):
        raise SetupError('运行环境路径不匹配。')
    expected = {'.venv-wiscomper': str(runtime / 'venv'), 'node_modules': str(runtime / 'node/node_modules')}
    entries = state.get('links', [])
    if len(entries) != 2 or {item.get('name') for item in entries} != set(expected):
        raise SetupError('运行环境记录不完整。')
    actions = []
    for item in entries:
        name, destination = item['name'], item.get('destination')
        if destination != expected[name] or type(item.get('had_original')) is not bool:
            raise SetupError('运行环境记录不正确。')
        original = item.get('original')
        if item['had_original']:
            if (not isinstance(original, dict) or set(original) != {'device', 'inode', 'mode', 'link'}
                    or any(type(original[key]) is not int or original[key] < 0 for key in ('device', 'inode', 'mode'))
                    or original['link'] is not None and not isinstance(original['link'], str)):
                raise SetupError('原运行环境身份记录不完整。')
        elif original is not None:
            raise SetupError('原运行环境记录不正确。')
        path, previous = target / name, backup / ('previous-' + name)
        is_new = path.is_symlink() and os.readlink(path) == destination
        saved = os.path.lexists(previous)
        if saved and (not item['had_original'] or path_identity(previous) != original):
            raise SetupError('原运行环境备份已被替换，未继续回滚。')
        if is_new:
            if saved != item['had_original']:
                raise SetupError('原运行环境备份缺失，请保留现场后检查。')
            actions.append((path, previous if saved else None, True))
        elif not os.path.lexists(path) and saved:
            actions.append((path, previous, False))
        elif saved:
            raise SetupError(f'{name} 已被修改，未自动覆盖。')
        elif not item['had_original'] and os.path.lexists(path):
            raise SetupError(f'{name} 已被修改，未自动删除。')
        elif item['had_original'] and path_identity(path) != original:
            raise SetupError(f'{name} 原目录缺失或已被替换，未假定回滚成功。')
        # Otherwise this entry is still the original, or was already restored.
    return actions


def restore(package, backup):
    api = installer(package)
    target, _ = api.load_receipt(backup)
    with operation_lock(target, api):
        _restore(api, target, backup)
    print('程序及运行环境已回滚。数据库、.env 与用户文件保持原位，请重启宝塔项目。')


def _restore(api, target, backup):
    metadata = backup / 'runtime-receipt.json'
    state = api.read_json(metadata) if metadata.exists() else None
    if state is not None and (type(state.get('port')) is not int or not 1 <= state['port'] <= 65535):
        raise SetupError('运行环境记录中的端口无效。')
    ensure_stopped(target, api, state['port'] if state else None)
    actions = runtime_rollback_plan(target, backup, state) if state else []
    api.rollback_plan(backup)
    api.rollback(backup)
    for path, previous, remove in reversed(actions):
        # Check again immediately before each rename; another administrator may
        # have edited a path while the code files were being restored.
        latest = runtime_rollback_plan(target, backup, state)
        if (path, previous, remove) not in latest:
            raise SetupError('运行环境在回滚中发生变化，请保持服务停止后检查。')
        if remove:
            path.unlink()  # only the checked symlink, never its directory contents
        if previous is not None:
            os.replace(previous, path)
        api.fsync_directory(target)
        api.fsync_directory(backup)
    if state:
        state['state'] = 'rolled_back'
        api.atomic_json(metadata, state)


def deploy(args, package):
    if os.name != 'posix' or not sys.platform.startswith('linux'):
        raise SetupError('此一键入口用于宝塔/Linux；本机请继续使用原启动器。')
    if sys.version_info < (3, 11):
        raise SetupError('请使用宝塔项目中的 Python 3.11 或更新版本运行本脚本。')
    api = installer(package)
    target = api.absolute(args.target)
    api.plan_install(package, target, args.site_url, args.port)
    with operation_lock(target, api):
        _deploy(args, package, api, target)


def _deploy(args, package, api, target):
    ensure_stopped(target, api, args.port)
    node, npm = shutil.which('node'), shutil.which('npm')
    if not node or not npm:
        raise SetupError('请先在宝塔安装 Node.js 24，并将其 bin 目录加入当前 PATH。')
    node, npm = str(Path(node).resolve()), str(Path(npm).resolve())
    try:
        version = subprocess.check_output([node, '--version'], text=True, stderr=subprocess.PIPE, timeout=10)
    except (subprocess.SubprocessError, OSError):
        raise SetupError('无法读取 Node.js 版本，请检查 PATH 和 Node 安装。') from None
    if not node_supported(version):
        raise SetupError('需要 Node.js 22.19+（22系列）或24及以上；推荐24。')
    uid, gid = service_identity(target, args.service_user)
    if os.geteuid() != 0 and uid != os.geteuid():
        raise SetupError('当前用户不能为宝塔运行用户准备目录，请使用有权限的用户执行。')
    parent = api.check_chain(target.with_name(target.name + '.deploy-runtimes'))
    parent.mkdir(mode=0o755, exist_ok=True)
    runtime = parent / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12])
    runtime.mkdir(mode=0o755)
    log = runtime / 'prepare.log'
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'NODE_OPTIONS'):
        env.pop(key, None)
    python = runtime / 'venv/bin/python'
    print('1/4 准备独立 Python 环境，不修改旧站的 Python 依赖。', flush=True)
    run([sys.executable, '-m', 'venv', runtime / 'venv'], log, env=env)
    run([python, '-m', 'pip', 'install', '-r', package / 'payload/requirements-server.txt'], log, env=env)
    print('2/4 只读检查旧库、域名和配置。', flush=True)
    result = subprocess.run([str(python), str(package / 'payload/deploy/preflight.py'), '--target', str(target),
                             '--site-url', args.site_url, '--port', str(args.port)], env=env, timeout=60)
    if result.returncode:
        raise SetupError('检查未通过，原站程序未替换。修正配置或缺失的表结构后再试。')
    print('3/4 准备网页依赖与视频导出环境。', flush=True)
    dependency_root = runtime / 'node'
    dependency_root.mkdir()
    for name in ('package.json', 'package-lock.json'):
        shutil.copyfile(package / 'payload' / name, dependency_root / name)
    run([npm, 'ci', '--omit=dev', '--no-fund', '--no-audit'], log, cwd=dependency_root, env=env)
    env['PLAYWRIGHT_BROWSERS_PATH'] = str(runtime / 'venv/.playwright')
    if not args.skip_browser:
        run([python, '-m', 'playwright', 'install', 'chromium'], log, env=env)
    if args.with_manim:
        run([python, '-m', 'pip', 'install', 'manim==0.22.0'], log, env=env)
    (runtime / 'venv/wiscomper-runtime.json').write_text(json.dumps({'node': node}), encoding='utf-8')
    own_tree(runtime, uid, gid)
    check_service_access(target, runtime, uid, gid, log, package, node)
    ensure_stopped(target, api, args.port)
    print('4/4 校验、备份并更新程序。', flush=True)
    result = api.install(package, target, args.site_url, args.port)
    backup = Path(result['backup_dir'])
    try:
        replace_links(target, runtime, backup, {'port': args.port}, api)
        data = api.check_chain(target / 'var/wiscomper-harness')
        if not data.exists():
            data.mkdir(parents=True, mode=0o700)
            if os.geteuid() == 0:
                os.chown(data, uid, gid)
        # Generated sidecar needs to be readable by the selected service user.
        if os.geteuid() == 0:
            os.chown(target / '.env.deploy', uid, gid)
    except Exception as error:
        try:
            _restore(api, target, backup)
        except Exception:
            raise SetupError(f'更新中断，未覆盖可能存在的新改动。保持服务停止并回滚：\n{sys.executable} {package / "deploy.py"} rollback --backup {backup}') from None
        raise SetupError('运行环境切换未完成，程序和原运行环境已恢复；独立准备目录保留以便检查。') from None
    print(f'更新完成。备份：{backup}\n启动命令仍为 python main.py，监听 127.0.0.1:{args.port}。')
    print('请按包内 nginx-harness.conf.example 检查宝塔反向代理，再重启原 Python 项目。')
    print(f'回滚：python3 {package / "deploy.py"} rollback --backup {backup}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('install')
    command.add_argument('--target', type=Path, default=Path('/www/wwwroot/wiscomper.com'))
    command.add_argument('--site-url', default='https://www.wiscomper.com')
    command.add_argument('--port', type=int, default=8000)
    command.add_argument('--service-user', help='宝塔 Python 项目运行用户；默认使用站点目录所有者')
    command.add_argument('--skip-browser', action='store_true')
    command.add_argument('--with-manim', action='store_true')
    command = commands.add_parser('rollback')
    command.add_argument('--backup', type=Path, required=True)
    args = parser.parse_args(argv)
    package = Path(__file__).resolve().parent
    try:
        if args.command == 'rollback':
            restore(package, args.backup)
        else:
            deploy(args, package)
        return 0
    except (SetupError, ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'部署未完成：{error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
