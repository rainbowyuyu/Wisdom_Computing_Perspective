#!/usr/bin/env python3
"""Stdlib-only installer. Ship this file as install.py beside manifest.json/payload.

Manifest: {"schema_version": 1, "files": [{"path": "main.py", "sha256": "..."}]}.
No dependency installation, service control, database connection, or SQL is run.
Stop the application while installing/rolling back. Atomicity is per file; the
durable receipt allows recovery after interruption. SHA256 checks integrity, not
publisher authenticity: obtain the complete package through a trusted channel.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
from urllib.parse import urlsplit
import uuid


DEFAULT_TARGET = '/www/wwwroot/wiscomper.com'
DEFAULT_SITE_URL = 'https://www.wiscomper.com'
ROOT_FILES = {
    'main.py', 'configuration.py', 'requirements.txt', 'requirements-server.txt',
    'requirements-lock.txt', 'requirements-manim.txt', 'package.json',
    'package-lock.json', 'README.md', 'README.en.md', '.env.example', '.gitignore',
}
DIRECTORIES = {
    'server': {'.py'},
    'runtime': {'.py', '.mjs', '.js', '.json', '.md', '.ps1', '.sh'},
    'web': {'.html', '.js', '.mjs', '.css', '.json', '.svg', '.png', '.jpg',
            '.jpeg', '.webp', '.gif', '.ico', '.woff', '.woff2', '.ttf', '.md'},
    'docs': {'.md', '.txt'},
    'scripts': {'.py', '.sh', '.ps1'},
    'deploy': {'.py', '.sh', '.conf', '.service', '.md', '.txt', '.example', '.json'},
}
PROTECTED_PARTS = {
    'var', 'data', 'storage', 'uploads', 'upload', 'database', 'databases',
    'node_modules', '.venv', 'venv', '__pycache__', '.git', 'secrets',
    'engineering-imports', 'audit', 'sessions', 'work', 'tmp', 'cache',
    '.cache', 'logs', 'outputs', 'exports', 'generated', 'media',
}
DATABASE_SUFFIXES = {'.db', '.sqlite', '.sqlite3', '.sql', '.db3', '.mdb', '.bak'}
PRIVATE_SUFFIXES = {'.dpapi', '.pem', '.key', '.p12', '.pfx', '.log', '.jsonl'}
DOC_ASSET_SUFFIXES = {'.svg', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.ico'}
CONFIG_KEYS = {'PUBLIC_SITE_URL', 'VISUALIZE_PORT', 'VISUALIZE_DATA', 'LEGACY_ACCOUNT_BACKEND', 'PORT'}
HEX64 = re.compile(r'^[a-f0-9]{64}$')
DEVICE = re.compile(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)', re.I)
MAX_MANIFEST_BYTES = 8 * 1024 * 1024


class DeploymentError(ValueError):
    pass


def absolute(path):
    return Path(os.path.abspath(os.fspath(path)))


def check_chain(path):
    """Reject links/junctions in every existing component, including ancestors."""
    path = absolute(path)
    for item in reversed((path, *path.parents)):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise DeploymentError(f'Links/reparse points are not allowed: {item}')
        if item != path and not stat.S_ISDIR(info.st_mode):
            raise DeploymentError(f'Parent is not a directory: {item}')
    return path


def regular_file(path):
    check_chain(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise DeploymentError(f'Required file is missing: {path}') from None
    if not stat.S_ISREG(info.st_mode):
        raise DeploymentError(f'Expected a regular file: {path}')
    return info


def relative_path(value, *, generated_config=False, directory=False):
    if not isinstance(value, str) or not value or len(value) > 240:
        raise DeploymentError('Manifest path must be a nonempty relative path of at most 240 characters.')
    if any(ord(char) < 32 or ord(char) == 127 for char in value) or '\\' in value or ':' in value:
        raise DeploymentError(f'Unsafe path: {value!r}')
    parts = value.split('/')
    if any(part in ('', '.', '..') or part.endswith((' ', '.')) or DEVICE.match(part) for part in parts):
        raise DeploymentError(f'Unsafe path: {value!r}')
    if value == '.env.deploy' and generated_config:
        return value
    lower = [part.casefold() for part in parts]
    if any(part in PROTECTED_PARTS for part in lower):
        raise DeploymentError(f'Protected data path is not deployable: {value}')
    if any(part.startswith('.env') for part in lower) and value != '.env.example':
        raise DeploymentError(f'Private environment files are not deployable: {value}')
    if any(Path(part).suffix.casefold() in DATABASE_SUFFIXES or '.sqlite-' in part or '.db-' in part for part in lower):
        raise DeploymentError(f'Database/backup files are not deployable: {value}')
    if any(Path(part).suffix.casefold() in PRIVATE_SUFFIXES for part in lower):
        raise DeploymentError(f'Private/generated files are not deployable: {value}')
    if directory:
        if parts[0] not in DIRECTORIES:
            raise DeploymentError(f'Directory is outside the source allowlist: {value}')
    elif len(parts) == 1:
        if value not in ROOT_FILES:
            raise DeploymentError(f'Root file is outside the allowlist: {value}')
    elif (parts[0] not in DIRECTORIES
          or Path(parts[-1]).suffix.casefold() not in DIRECTORIES[parts[0]]
          and not (parts[:2] == ['docs', 'assets'] and Path(parts[-1]).suffix.casefold() in DOC_ASSET_SUFFIXES)):
        raise DeploymentError(f'File is outside the source allowlist: {value}')
    if any(part.startswith('.') for part in parts[1:]):
        raise DeploymentError(f'Hidden source path is not deployable: {value}')
    return value


def unique_paths(paths):
    seen = set()
    for path in paths:
        folded = path.casefold()
        if folded in seen:
            raise DeploymentError(f'Duplicate/case-colliding path: {path}')
        seen.add(folded)
    for path in seen:
        components = path.split('/')
        if any('/'.join(components[:i]) in seen for i in range(1, len(components))):
            raise DeploymentError(f'File/directory path conflict: {path}')


def digest(path):
    regular_file(path)
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def read_json(path):
    if regular_file(path).st_size > MAX_MANIFEST_BYTES:
        raise DeploymentError(f'JSON metadata is too large: {path}')
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (UnicodeError, json.JSONDecodeError):
        raise DeploymentError(f'Invalid UTF-8 JSON: {path}') from None


def validate_package(package):
    package = check_chain(package)
    document = read_json(package / 'manifest.json')
    if not isinstance(document, dict) or document.get('schema_version') != 1:
        raise DeploymentError('Unsupported manifest schema_version; expected 1.')
    records = document.get('files')
    if not isinstance(records, list) or not records or len(records) > 50000:
        raise DeploymentError('Manifest files must contain 1..50000 records.')
    files = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get('sha256'), str) or not HEX64.fullmatch(record['sha256']):
            raise DeploymentError('Each manifest record requires a lowercase SHA256.')
        path = relative_path(record.get('path'))
        files.append({'path': path, 'sha256': record['sha256']})
    unique_paths(item['path'] for item in files)
    payload = check_chain(package / 'payload')
    if not payload.is_dir():
        raise DeploymentError('Package requires a payload directory.')
    actual = set()
    for base, directories, names in os.walk(payload, followlinks=False):
        for name in directories:
            directory = check_chain(Path(base) / name)
            relative_path(directory.relative_to(payload).as_posix(), directory=True)
        for name in names:
            source = Path(base) / name
            regular_file(source)
            path = source.relative_to(payload).as_posix()
            relative_path(path)
            actual.add(path)
    expected = {item['path'] for item in files}
    if actual != expected:
        raise DeploymentError(f'Payload differs from manifest: missing={sorted(expected-actual)!r}, unlisted={sorted(actual-expected)!r}')
    for item in files:
        if digest(payload / item['path']) != item['sha256']:
            raise DeploymentError(f'SHA256 mismatch: {item["path"]}')
    return sorted(files, key=lambda item: item['path'])


def site_url(value):
    try:
        if not isinstance(value, str) or any(char.isspace() or ord(char) < 32 for char in value):
            raise ValueError()
        url = urlsplit(value)
        host = url.hostname or ''
        labels = host.split('.')
        if (url.scheme != 'https' or url.username or url.password or url.port not in (None, 443)
                or url.path not in ('', '/') or url.query or url.fragment
                or len(labels) < 2 or host.endswith('.')
                or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels)
                or host.endswith(('.localhost', '.local', '.internal', '.test'))):
            raise ValueError()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError()
    except (ValueError, TypeError):
        raise DeploymentError('Site URL must be an HTTPS public domain root, without credentials, path, query or custom port.') from None
    return 'https://' + host


def deployment_config(target, url, port):
    # Quote the data directory so spaces and # in an explicit target remain literal.
    data = (target / 'var' / 'wiscomper-harness').as_posix()
    if any(char in data for char in '\r\n\0\''):
        raise DeploymentError('Target path cannot be represented safely in the deployment configuration.')
    return (f'# Generated once by the Wiscomper installer; existing .env files are preserved.\n'
            f'PUBLIC_SITE_URL={url}\nVISUALIZE_PORT={port}\n'
            f"VISUALIZE_DATA='{data}'\nLEGACY_ACCOUNT_BACKEND=mysql\n").encode('utf-8')


def config_values(text, origin):
    """Read only deployment keys; fail closed on complex syntax/interpolation."""
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('export '):
            line = line[7:].lstrip()
        match = re.match(r"^(?:'([A-Za-z_][A-Za-z0-9_]*)'|([A-Za-z_][A-Za-z0-9_]*))\s*(?:=\s*(.*))?$", line)
        if not match or (match[1] or match[2]) not in CONFIG_KEYS:
            continue
        key = match[1] or match[2]
        if match[3] is None:
            values[key] = None
            continue
        value = match[3].strip()
        if value.startswith(('"', "'")):
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0 or value[end+1:].strip() and not value[end+1:].lstrip().startswith('#'):
                raise DeploymentError(f'Use a single-line literal for {key} in {origin}.')
            value = value[1:end]
            if '\\' in value:
                raise DeploymentError(f'Use a literal path with forward slashes for {key} in {origin}.')
        else:
            value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
        if '${' in value:
            raise DeploymentError(f'Use an explicit value instead of interpolation for {key} in {origin}.')
        values[key] = value
    return normalize_config(values)


def normalize_config(values):
    values = {key: value for key, value in values.items() if value is not None}
    if 'PORT' in values and 'VISUALIZE_PORT' not in values:
        values['VISUALIZE_PORT'] = values['PORT']
    return values


def configuration_preflight(target, generated, expected_url, expected_port, allow_empty_config):
    old_configs = [target / '.env', target / '.env.local']
    if not allow_empty_config and not any(path.exists() for path in old_configs):
        raise DeploymentError('Target needs .env or .env.local. For an intentional new/test site, use --allow-empty-config.')
    deploy_path = target / '.env.deploy'
    # Defaults only exist at runtime if this installation actually creates them.
    values = {} if deploy_path.exists() else config_values(generated.decode('utf-8'), 'generated .env.deploy')
    for path in [deploy_path, *old_configs]:
        check_chain(path)
        if path.exists():
            regular_file(path)
            try:
                values.update(config_values(path.read_text(encoding='utf-8-sig'), path.name))
            except UnicodeError:
                raise DeploymentError(f'Configuration is not UTF-8: {path.name}') from None
    values.update(normalize_config({key: os.environ[key] for key in CONFIG_KEYS if key in os.environ}))
    actual_url = values.get('PUBLIC_SITE_URL', '')
    if not actual_url or site_url(actual_url) != expected_url:
        raise DeploymentError('Effective PUBLIC_SITE_URL must match --site-url. Check .env.deploy < .env < .env.local < process environment; remove an explicit empty override or set the intended HTTPS domain. Existing configuration was not changed.')
    if values.get('VISUALIZE_PORT') != str(expected_port):
        raise DeploymentError('Effective VISUALIZE_PORT differs from --port. Align the existing override and --port; configuration was not changed.')
    if values.get('LEGACY_ACCOUNT_BACKEND') != 'mysql':
        raise DeploymentError('Effective LEGACY_ACCOUNT_BACKEND must be mysql to preserve the old account database. Adjust the existing override; no database was contacted.')
    if not values.get('VISUALIZE_DATA'):
        raise DeploymentError('Effective VISUALIZE_DATA must not be empty. Existing configuration was not changed.')


def plan_install(package, target, url, port, allow_empty_config=False):
    files = validate_package(package)
    target = check_chain(target)
    if not target.is_dir() or target.parent == target:
        raise DeploymentError('Target must be an existing site directory, not a filesystem root.')
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise DeploymentError('Port must be between 1 and 65535.')
    url = site_url(url)
    generated = deployment_config(target, url, port)
    configuration_preflight(target, generated, url, port, allow_empty_config)
    records = []
    for item in files:
        records.append({'path': item['path'], 'after_sha256': item['sha256']})
    if not (target / '.env.deploy').exists():
        records.append({'path': '.env.deploy', 'after_sha256': hashlib.sha256(generated).hexdigest()})
    for item in records:
        dest = check_chain(target / item['path'])
        if dest.exists():
            info = regular_file(dest)
            item.update(before_sha256=digest(dest), before_mode=stat.S_IMODE(info.st_mode),
                        before_mtime_ns=info.st_mtime_ns, before_uid=getattr(info, 'st_uid', 0),
                        before_gid=getattr(info, 'st_gid', 0))
        else:
            item['before_sha256'] = None
    return target, records, generated


def fsync_directory(directory):
    if os.name == 'nt':
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_tree(directory):
    for base, _, _ in os.walk(directory, topdown=False, followlinks=False):
        fsync_directory(Path(base))
    fsync_directory(directory.parent)


def atomic_bytes(path, value, mode=0o600):
    check_chain(path)
    fd, temporary = tempfile.mkstemp(prefix='.wiscomper-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path, value):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def copy_verified(source, destination, expected):
    regular_file(source)
    check_chain(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as incoming, destination.open('xb') as outgoing:
        shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    os.chmod(destination, 0o600)
    if digest(destination) != expected:
        raise DeploymentError(f'File changed or failed verification during copy: {source.name}')


def backup_parent(target):
    return target.with_name(target.name + '.deploy-backups')


@contextmanager
def deployment_lock(target):
    parent = check_chain(backup_parent(target))
    parent.mkdir(mode=0o700, exist_ok=True)
    if hasattr(os, 'geteuid'):
        if parent.stat().st_uid != os.geteuid():
            raise DeploymentError('Backup directory must be owned by the account running the installer.')
        os.chmod(parent, 0o700)
    fsync_directory(parent.parent)
    lock = parent / '.lock'
    check_chain(lock)
    with lock.open('a+b') as stream:
        os.chmod(lock, 0o600)
        if stream.tell() == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise DeploymentError('Another install/rollback is running for this target.') from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def replace_verified(source, dest, expected, *, mode=0o644, owner=None, mtime_ns=None):
    check_chain(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.wiscomper-install-', dir=dest.parent)
    os.close(fd)
    temporary = Path(temporary)
    try:
        # copy_verified uses exclusive creation; retain only the reserved random name.
        temporary.unlink()
        copy_verified(source, temporary, expected)
        os.chmod(temporary, mode & 0o777)
        if owner is not None and hasattr(os, 'geteuid') and os.geteuid() == 0:
            os.chown(temporary, *owner)
        if mtime_ns is not None:
            os.utime(temporary, ns=(mtime_ns, mtime_ns))
        if os.name != 'nt':
            with temporary.open('rb') as stream:
                os.fsync(stream.fileno())
        check_chain(dest)
        os.replace(temporary, dest)
        fsync_directory(dest.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def current_hash(path):
    check_chain(path)
    return digest(path) if path.exists() else None


def install(package, target, url=DEFAULT_SITE_URL, port=8000, allow_empty_config=False):
    package, target = absolute(package), absolute(target)
    # Complete read-only preflight before creating the backup parent/lock.
    plan_install(package, target, url, port, allow_empty_config)
    with deployment_lock(target):
        target, records, generated = plan_install(package, target, url, port, allow_empty_config)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12]
        backup = backup_parent(target) / stamp
        backup.mkdir(mode=0o700)
        (backup / 'previous').mkdir(mode=0o700)
        (backup / 'staged').mkdir(mode=0o700)
        for item in records:
            path = item['path']
            if item['before_sha256'] is not None:
                copy_verified(target / path, backup / 'previous' / path, item['before_sha256'])
            if path == '.env.deploy':
                atomic_bytes(backup / 'staged' / path, generated)
            else:
                copy_verified(package / 'payload' / path, backup / 'staged' / path, item['after_sha256'])
        receipt = {'schema_version': 1, 'target': str(target), 'state': 'prepared',
                   'created_at': datetime.now(timezone.utc).isoformat(), 'files': records}
        atomic_json(backup / 'receipt.json', receipt)
        fsync_tree(backup)
        try:
            # Detect edits made while backups were copied before any replacement.
            for item in records:
                if current_hash(target / item['path']) != item['before_sha256']:
                    raise DeploymentError(f'Target changed during preparation: {item["path"]}')
            target_info = target.stat()
            for item in records:
                dest = target / item['path']
                if current_hash(dest) != item['before_sha256']:
                    raise DeploymentError(f'Target changed during installation: {item["path"]}')
                if item['before_sha256'] == item['after_sha256']:
                    continue
                owner = (item.get('before_uid', target_info.st_uid), item.get('before_gid', target_info.st_gid))
                replace_verified(backup / 'staged' / item['path'], dest, item['after_sha256'],
                                 mode=item.get('before_mode', 0o600 if item['path'] == '.env.deploy' else 0o644), owner=owner)
            receipt['state'] = 'installed'
            atomic_json(backup / 'receipt.json', receipt)
        except Exception as error:
            raise DeploymentError(f'Installation interrupted; keep the backup and run rollback --backup "{backup}". Reason: {error}') from error
    return {'status': 'installed', 'target': str(target), 'backup_dir': str(backup), 'file_count': len(records)}


def load_receipt(backup, target=None):
    backup = check_chain(backup)
    receipt = read_json(backup / 'receipt.json')
    if not isinstance(receipt, dict) or receipt.get('schema_version') != 1 or receipt.get('state') not in {'prepared', 'installed', 'rolled_back'}:
        raise DeploymentError('Invalid backup receipt.')
    recorded_target = receipt.get('target')
    if not isinstance(recorded_target, str) or not Path(recorded_target).is_absolute():
        raise DeploymentError('Receipt target must be absolute.')
    site = check_chain(recorded_target)
    if target is not None and absolute(target) != site:
        raise DeploymentError('Requested target differs from backup receipt target.')
    if backup.parent != backup_parent(site) or not site.is_dir() or site.parent == site:
        raise DeploymentError('Backup must be in the target sibling backup directory.')
    files = receipt.get('files')
    if not isinstance(files, list) or not files or len(files) > 50001:
        raise DeploymentError('Invalid backup file list.')
    for item in files:
        if not isinstance(item, dict):
            raise DeploymentError('Invalid backup record.')
        relative_path(item.get('path'), generated_config=True)
        if 'before_sha256' not in item:
            raise DeploymentError('Backup record is missing before_sha256.')
        before, after = item.get('before_sha256'), item.get('after_sha256')
        if not isinstance(after, str) or not HEX64.fullmatch(after) or before is not None and (not isinstance(before, str) or not HEX64.fullmatch(before)):
            raise DeploymentError('Invalid backup record hashes.')
        if item['path'] == '.env.deploy' and before is not None:
            raise DeploymentError('Deployment configuration may only be recorded as newly generated.')
        if before is not None:
            for key in ('before_mode', 'before_mtime_ns', 'before_uid', 'before_gid'):
                if not isinstance(item.get(key), int) or item[key] < 0:
                    raise DeploymentError(f'Invalid original metadata: {item["path"]}')
    unique_paths(item['path'] for item in files)
    return site, receipt


def rollback_plan(backup, target=None):
    site, receipt = load_receipt(backup, target)
    actions = []
    conflicts = []
    for item in receipt['files']:
        path, before, after = item['path'], item['before_sha256'], item['after_sha256']
        if before is not None and digest(backup / 'previous' / path) != before:
            raise DeploymentError(f'Backup SHA256 mismatch: {path}')
        current = current_hash(site / path)
        if current == before:
            continue  # Not installed yet, already restored, or new file already absent.
        if current != after:
            conflicts.append(path)
        else:
            actions.append(item)
    if conflicts:
        raise DeploymentError('Rollback conflict: files changed or disappeared after installation: ' + ', '.join(conflicts) + '. No files were restored or deleted.')
    return site, receipt, actions


def rollback(backup, target=None, dry_run=False):
    backup = absolute(backup)
    site, receipt, actions = rollback_plan(backup, target)
    if dry_run:
        return {'status': 'rollback-dry-run', 'target': str(site), 'file_count': len(actions), 'files': [item['path'] for item in actions]}
    with deployment_lock(site):
        site, receipt, actions = rollback_plan(backup, target)
        for item in reversed(actions):
            dest = site / item['path']
            if current_hash(dest) != item['after_sha256']:
                raise DeploymentError(f'File changed during rollback: {item["path"]}. Stop application writes and retry with the same backup.')
            if item['before_sha256'] is None:
                dest.unlink()
                fsync_directory(dest.parent)
            else:
                replace_verified(backup / 'previous' / item['path'], dest, item['before_sha256'],
                                 mode=item['before_mode'], owner=(item['before_uid'], item['before_gid']),
                                 mtime_ns=item['before_mtime_ns'])
        receipt['state'] = 'rolled_back'
        receipt['rolled_back_at'] = datetime.now(timezone.utc).isoformat()
        atomic_json(backup / 'receipt.json', receipt)
    return {'status': 'rolled-back', 'target': str(site), 'file_count': len(actions), 'backup_dir': str(backup)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('validate', 'dry-run', 'install'):
        command = commands.add_parser(name)
        command.add_argument('--package', type=Path, default=Path(__file__).resolve().parent)
        if name != 'validate':
            command.add_argument('--target', type=Path, default=Path(DEFAULT_TARGET))
            command.add_argument('--site-url', default=DEFAULT_SITE_URL)
            command.add_argument('--port', type=int, default=8000)
            command.add_argument('--allow-empty-config', action='store_true')
    command = commands.add_parser('rollback')
    command.add_argument('--backup', type=Path, required=True)
    command.add_argument('--target', type=Path)
    command.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'validate':
            files = validate_package(args.package)
            result = {'status': 'validated', 'file_count': len(files)}
        elif args.command == 'dry-run':
            target, records, _ = plan_install(args.package, args.target, args.site_url, args.port, args.allow_empty_config)
            result = {'status': 'dry-run', 'target': str(target), 'backup_parent': str(backup_parent(target)),
                      'files': [{'path': item['path'], 'action': 'replace' if item['before_sha256'] is not None else 'create'} for item in records]}
        elif args.command == 'install':
            result = install(args.package, args.target, args.site_url, args.port, args.allow_empty_config)
        else:
            result = rollback(args.backup, args.target, args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (DeploymentError, OSError) as error:
        print('Deployment refused: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
