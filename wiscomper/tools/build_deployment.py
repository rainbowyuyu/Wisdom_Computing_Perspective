"""Build a source-only deployment archive; never include local credentials/data."""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', ROOT / 'tools/deploy.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private_path(path):
    """Do not enumerate or package generated content, even JSON or images."""
    parts = [part.casefold() for part in path.relative_to(ROOT).parts]
    return (any(part in installer.PROTECTED_PARTS for part in parts)
            or any(part.startswith('.env') for part in parts)
            or any(Path(part).suffix in installer.DATABASE_SUFFIXES | installer.PRIVATE_SUFFIXES
                   or '.sqlite-' in part or '.db-' in part for part in parts))


def source_files():
    result = []
    roots = ['main.py', 'configuration.py', 'README.md', 'README.en.md', '.env.example',
             'requirements-server.txt', 'requirements.txt', 'requirements-manim.txt',
             'package.json', 'package-lock.json']
    for name in roots:
        installer.relative_path(name)
        installer.regular_file(ROOT / name)
        result.append(ROOT / name)
    for directory in ('server', 'runtime', 'web', 'deploy', 'docs', 'scripts'):
        for base, directories, names in os.walk(ROOT / directory, followlinks=False):
            directories[:] = sorted(name for name in directories
                                    if not private_path(Path(base) / name)
                                    and not (Path(base) / name).is_symlink())
            for name in sorted(names):
                path = Path(base) / name
                if path.is_symlink() or private_path(path):
                    continue
                if '.test.' in name or name.startswith('test_') or path.suffix in {'.pyc', '.pyo'}:
                    continue
                # Artwork generators stay in Git; production only needs their output.
                if directory == 'docs' and path.suffix.casefold() in {'.py', '.mjs', '.js'}:
                    continue
                relative = path.relative_to(ROOT).as_posix()
                installer.relative_path(relative)
                installer.regular_file(path)
                result.append(path)
    return sorted(result)


def release_name(value=None):
    if value is None:
        return 'wiscomper-release-' + datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d')
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', value)
            or value.endswith('.') or installer.DEVICE.match(value)):
        raise ValueError('Release name must be a safe single directory name using letters, numbers, dots, hyphens or underscores.')
    return value


def build(output, name=None):
    name = release_name(name)
    output = Path(output)
    package = output / name
    archive = output / (name + '.zip')
    checksum = output / (archive.name + '.sha256')
    if any(path.exists() for path in (package, archive, checksum)):
        raise FileExistsError(f'Release already exists: {name}. Choose a new --release-name; existing files are preserved.')
    sources = source_files()
    output.mkdir(parents=True, exist_ok=True)
    package.mkdir()  # Refuse to overwrite an earlier release.
    payload = package / 'payload'
    manifest = {'schema_version': 1, 'release': name,
                'created_at': datetime.now(timezone.utc).isoformat(), 'files': []}
    for source in sources:
        relative = source.relative_to(ROOT).as_posix()
        destination = payload / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        manifest['files'].append({'path': relative, 'sha256': digest(destination)})
    (package / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    for source, destination in [('tools/deploy.py', 'install.py'), ('tools/deploy_server.py', 'deploy.py'),
                                ('deploy/DEPLOY-PACKAGE.md', '部署说明.md'),
                                ('deploy/nginx-harness.conf.example', 'nginx-harness.conf.example')]:
        shutil.copyfile(ROOT / source, package / destination)
    installer.validate_package(package)
    entries = sorted(path for path in package.rglob('*') if path.is_file())
    (package / 'SHA256SUMS.txt').write_text(''.join(digest(path) + '  ' + path.relative_to(package).as_posix() + '\n' for path in entries), encoding='utf-8')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for path in sorted(package.rglob('*')):
            if path.is_file():
                zipped.write(path, path.relative_to(output).as_posix())
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip() is not None:
            raise ValueError('Archive verification failed')
    with checksum.open('x', encoding='utf-8') as stream:
        stream.write(digest(archive) + '  ' + archive.name + '\n')
    print(json.dumps({'zip': str(archive), 'sha256': digest(archive), 'bytes': archive.stat().st_size,
                      'payload_files': len(manifest['files'])}, ensure_ascii=False, indent=2))
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--release-name', help='Unique package directory name; defaults to wiscomper-release-YYYYMMDD in UTC+8.')
    args = parser.parse_args()
    build(args.output.resolve(), args.release_name)
