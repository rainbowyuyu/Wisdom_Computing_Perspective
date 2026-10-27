"""Exercise the exact shipped ZIP and stdlib installer against an old-site fixture."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from tools import build_deployment as builder
from tools.build_deployment import build


def test_archive_install_and_rollback_keep_existing_private_files(tmp_path):
    archive = build(tmp_path / 'release')
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        assert all(not Path(name).is_absolute() and '..' not in Path(name).parts for name in names)
        assert not any(Path(name).name in {'.env', '.env.local'} for name in names)
        assert not any(Path(name).suffix.lower() in {'.db', '.sqlite3', '.sqlite', '.sql', '.dpapi'} for name in names)
        assert not any(part in {'node_modules', '.venv', 'data', 'var', '__pycache__', 'engineering-imports'} for name in names for part in Path(name).parts)
        assert not any(name.endswith(('docs/assets/build_artwork.py', 'docs/assets/render_artwork.mjs')) for name in names)
        zipped.extractall(tmp_path / 'uploaded')
    package = tmp_path / 'uploaded' / archive.stem
    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
    assert {'main.py','configuration.py','server/app.py','runtime/qwen.py','web/index.html','deploy/preflight.py',
            'README.en.md','docs/assets/wiscomper-hero.png','docs/assets/wiscomper-workflow.png',
            'docs/assets/wiscomper-hero.svg'} <= {f['path'] for f in manifest['files']}
    for row in (package / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        sha, name = row.split('  ', 1)
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == sha
    target = tmp_path / 'old-site'
    target.mkdir()
    private = {'.env': b'MYSQL_DB=old_database\r\nMYSQL_PASSWORD=synthetic-deployment-test\r\n',
               '.env.local': b'# existing local configuration\nSMTP_FROM=example@example.invalid\n',
               'data/user.sqlite3': b'keep old data', 'var/usage.sqlite3': b'keep usage',
               'storage/video.mp4': b'keep video', 'static/avatars/user.png': b'keep avatar'}
    for name, content in private.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (target / 'main.py').write_bytes(b'# old service\n')
    env = {key:value for key,value in os.environ.items() if key not in {'PUBLIC_SITE_URL','VISUALIZE_PORT','VISUALIZE_DATA','LEGACY_ACCOUNT_BACKEND','PORT'}}
    def call(*args):
        result = subprocess.run([sys.executable, '-S', str(package / 'install.py'), *args],
                                env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    call('validate')
    call('dry-run', '--target', str(target))
    assert not (target / 'server').exists()
    result = call('install', '--target', str(target))
    for name, content in private.items():
        assert (target / name).read_bytes() == content
    for item in manifest['files']:
        assert hashlib.sha256((target / item['path']).read_bytes()).hexdigest() == item['sha256']
    call('rollback', '--backup', result['backup_dir'])
    assert (target / 'main.py').read_bytes() == b'# old service\n'
    assert not (target / '.env.deploy').exists()
    assert not (target / 'server/app.py').exists()
    for name, content in private.items():
        assert (target / name).read_bytes() == content


def test_source_selection_omits_private_imports_and_artwork_generators(tmp_path, monkeypatch):
    root = tmp_path / 'source'
    public = {
        'main.py': '# main', 'configuration.py': '# settings', 'README.md': 'Chinese',
        'README.en.md': 'English', '.env.example': 'KEY=',
        'requirements-server.txt': '', 'requirements.txt': '', 'requirements-manim.txt': '',
        'package.json': '{}', 'package-lock.json': '{}',
        'runtime/qwen.py': '# provider', 'runtime/contracts.mjs': '// contract',
        'web/index.html': '<p>Wiscomper</p>', 'docs/assets/wiscomper-hero.png': 'image fixture',
        'docs/assets/wiscomper-workflow.png': 'image fixture', 'docs/assets/wiscomper-hero.svg': '<svg/>',
        'docs/assets/README.md': 'Artwork provenance',
        'deploy/DEPLOY-PACKAGE.md': 'Deploy instructions', 'deploy/nginx-harness.conf.example': '# nginx',
    }
    private = {
        'runtime/engineering-imports/session-a/model.json': '{"private":true}',
        'runtime/engineering-imports/session-a/readme.md': 'Private user content',
        'runtime/engineering-imports/session-a/generated.py': '# private generated code',
        'runtime/Engineering-Imports/session-b/model.json': '{}',
        'runtime/audit/event.json': '{}', 'runtime/sessions/session.json': '{}',
        'runtime/outputs/scene.json': '{}', 'runtime/media/image.png': 'private image',
        'server/.env.local': 'PRIVATE=test-value', 'server/secret.key': 'test key',
        'server/users.sqlite3': 'private database', 'server/__pycache__/compiled.pyc': 'cache',
        'docs/assets/build_artwork.py': '# generation source',
        'docs/assets/render_artwork.mjs': '// generation source',
    }
    for name, content in {**public, **private}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    (root / 'tools').mkdir()
    (root / 'tools/deploy.py').write_bytes(Path(builder.installer.__file__).read_bytes())
    (root / 'tools/deploy_server.py').write_text('# test wrapper', encoding='utf-8')
    monkeypatch.setattr(builder, 'ROOT', root)
    selected = {path.relative_to(root).as_posix() for path in builder.source_files()}
    assert selected == set(public)
    archive = build(tmp_path / 'build', 'wiscomper-test-release')
    assert archive.stem == 'wiscomper-test-release'
    with zipfile.ZipFile(archive) as zipped:
        document = json.loads(zipped.read(archive.stem + '/manifest.json'))
        assert {row['path'] for row in document['files']} == set(public)
        assert not any('engineering-imports' in name.casefold() for name in zipped.namelist())


def test_default_release_name_uses_utc_plus_eight(monkeypatch):
    from datetime import datetime, timedelta
    class FixedClock:
        @staticmethod
        def now(zone):
            assert zone.utcoffset(None) == timedelta(hours=8)
            return datetime(2026, 10, 28, 0, 1, tzinfo=zone)
    monkeypatch.setattr(builder, 'datetime', FixedClock)
    assert builder.release_name() == 'wiscomper-release-20261028'


@pytest.mark.parametrize('name', ['', '../escape', '/absolute', 'a/b', 'a\\b', 'name:', 'CON', 'name.', 'a' * 81])
def test_unsafe_release_names_are_rejected_before_writing(tmp_path, name):
    output = tmp_path / 'not-created'
    with pytest.raises(ValueError, match='Release name'):
        build(output, name)
    assert not output.exists()


@pytest.mark.parametrize('existing', ['folder', 'zip', 'checksum'])
def test_existing_release_outputs_are_never_overwritten(tmp_path, existing):
    name = 'wiscomper-existing'
    if existing == 'folder':
        prior = tmp_path / name
        prior.mkdir()
        (prior / 'keep.txt').write_text('previous package')
    else:
        suffix = '.zip' if existing == 'zip' else '.zip.sha256'
        prior = tmp_path / (name + suffix)
        prior.write_text('previous package')
    with pytest.raises(FileExistsError, match='--release-name'):
        build(tmp_path, name)
    assert (prior / 'keep.txt' if existing == 'folder' else prior).read_text() == 'previous package'
    assert len(list(tmp_path.iterdir())) == 1
