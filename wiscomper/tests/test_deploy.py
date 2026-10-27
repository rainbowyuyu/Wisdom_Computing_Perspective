"""Run the packaged standard-library installer against isolated fake old sites."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools' / 'deploy.py'
spec = importlib.util.spec_from_file_location('wiscomper_deploy', SCRIPT)
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


@pytest.fixture(autouse=True)
def isolate_configuration(monkeypatch):
    for key in deploy.CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode() if isinstance(value, str) else value)


def package(tmp_path, files=None):
    directory = tmp_path / 'release'
    directory.mkdir()
    shutil.copy2(SCRIPT, directory / 'install.py')
    content = files or {'main.py': 'new main\n', 'server/new.py': 'new module\n', 'web/index.html': '<p>new</p>\n'}
    records = []
    for name, value in content.items():
        write(directory / 'payload' / name, value)
        records.append({'path': name, 'sha256': hashlib.sha256((directory / 'payload' / name).read_bytes()).hexdigest()})
    write(directory / 'manifest.json', json.dumps({'schema_version': 1, 'files': records}))
    return directory


def old_site(tmp_path):
    site = tmp_path / 'wiscomper.com'
    site.mkdir()
    preserved = {
        '.env': b'SECRET=preserve-me\n', '.env.local': b'LOCAL_SECRET=do-not-print\n',
        'var/old-user.txt': b'private old state', 'data/workbench.sqlite3': b'old db bytes',
        'storage/users.json': b'old user content', 'uploads/photo.png': b'old media',
        'database/users.db': b'old account data', 'legacy.db': b'old SQLite',
        'web/custom-user-note.txt': b'existing unrelated file',
    }
    for name, value in preserved.items():
        write(site / name, value)
    write(site / 'main.py', 'old main\n')
    write(site / 'web/index.html', '<p>old</p>\n')
    return site, preserved


def run(package_dir, *arguments, expected=0, env=None):
    process = subprocess.run([sys.executable, str(package_dir / 'install.py'), *map(str, arguments)],
                             cwd=package_dir, env=env, capture_output=True, text=True, timeout=30)
    assert process.returncode == expected, process.stdout + process.stderr
    if expected:
        return process.stderr
    return json.loads(process.stdout)


def assert_preserved(site, preserved):
    for name, value in preserved.items():
        assert (site / name).read_bytes() == value, name


def test_cli_dry_run_install_and_rollback_preserve_old_site(tmp_path):
    release = package(tmp_path)
    site, preserved = old_site(tmp_path)
    old_mtime = (site / 'main.py').stat().st_mtime_ns
    result = run(release, 'validate')
    assert result == {'status': 'validated', 'file_count': 3}
    plan = run(release, 'dry-run', '--target', site)
    assert any(item == {'path': '.env.deploy', 'action': 'create'} for item in plan['files'])
    assert (site / 'main.py').read_text() == 'old main\n'
    assert not (site / '.env.deploy').exists()
    assert not deploy.backup_parent(site).exists()

    installed = run(release, 'install', '--target', site)
    backup = Path(installed['backup_dir'])
    assert backup.parent == site.with_name(site.name + '.deploy-backups')
    assert not backup.is_relative_to(site)
    assert (backup / 'previous/main.py').read_text() == 'old main\n'
    assert (site / 'main.py').read_text() == 'new main\n'
    assert_preserved(site, preserved)
    config = (site / '.env.deploy').read_text()
    assert 'PUBLIC_SITE_URL=https://www.wiscomper.com\n' in config
    assert 'VISUALIZE_PORT=8000\n' in config
    assert f"VISUALIZE_DATA='{site.as_posix()}/var/wiscomper-harness'" in config
    assert 'LEGACY_ACCOUNT_BACKEND=mysql' in config
    assert not (site / 'var/wiscomper-harness').exists()  # Installer never starts app/DB.
    dry = run(release, 'rollback', '--backup', backup, '--dry-run')
    assert dry['file_count'] == 4
    assert (site / 'main.py').read_text() == 'new main\n'
    restored = run(release, 'rollback', '--backup', backup)
    assert restored['status'] == 'rolled-back'
    assert (site / 'main.py').read_text() == 'old main\n'
    assert (site / 'main.py').stat().st_mtime_ns == old_mtime
    assert (site / 'web/index.html').read_text() == '<p>old</p>\n'
    assert not (site / 'server/new.py').exists()
    assert not (site / '.env.deploy').exists()
    assert_preserved(site, preserved)
    assert run(release, 'rollback', '--backup', backup)['file_count'] == 0


def test_existing_deploy_config_is_preserved_and_not_rolled_back(tmp_path):
    release = package(tmp_path)
    site, preserved = old_site(tmp_path)
    config = deploy.deployment_config(site, 'https://demo.example.com', 8123) + b'CUSTOM_SETTING=preserve\n'
    write(site / '.env.deploy', config)
    preserved['.env.deploy'] = config
    install = run(release, 'install', '--target', site, '--site-url', 'https://demo.example.com/', '--port', 8123)
    receipt = json.loads((Path(install['backup_dir']) / 'receipt.json').read_text())
    assert '.env.deploy' not in [item['path'] for item in receipt['files']]
    assert_preserved(site, preserved)
    run(release, 'rollback', '--backup', install['backup_dir'])
    assert_preserved(site, preserved)


def test_existing_incomplete_deploy_config_cannot_inherit_unwritten_defaults(tmp_path):
    release = package(tmp_path)
    site, _ = old_site(tmp_path)
    existing = 'CUSTOM_SETTING=preserve\n'
    write(site / '.env.deploy', existing)
    assert 'PUBLIC_SITE_URL' in run(release, 'install', '--target', site, expected=2)
    assert (site / '.env.deploy').read_text() == existing
    assert not deploy.backup_parent(site).exists()


@pytest.mark.parametrize('changed', ['main.py', 'server/new.py', '.env.deploy'])
def test_rollback_modified_file_conflict_is_all_or_nothing(tmp_path, changed):
    release = package(tmp_path)
    site, preserved = old_site(tmp_path)
    result = run(release, 'install', '--target', site)
    write(site / changed, 'later user edit\n')
    error = run(release, 'rollback', '--backup', result['backup_dir'], expected=2)
    assert 'Rollback conflict' in error and changed in error
    assert (site / changed).read_text() == 'later user edit\n'
    assert (site / 'web/index.html').read_text() == '<p>new</p>\n'
    assert_preserved(site, preserved)


def test_corrupt_backup_is_rejected_before_any_rollback(tmp_path):
    release = package(tmp_path)
    site, _ = old_site(tmp_path)
    result = run(release, 'install', '--target', site)
    backup = Path(result['backup_dir'])
    write(backup / 'previous/main.py', 'damaged backup')
    assert 'Backup SHA256 mismatch' in run(release, 'rollback', '--backup', backup, expected=2)
    assert (site / 'main.py').read_text() == 'new main\n'
    assert (site / 'server/new.py').exists()


@pytest.mark.parametrize('path', [
    '../main.py', '/main.py', 'C:/main.py', 'web\\index.html', 'web//index.html',
    'web/../main.py', 'web/index.html:stream', 'web/NUL.js', 'web/con.css',
    'web/index.html ', 'web/hidden./index.html', 'web/\x00.js',
    '.env', '.env.local', '.env.deploy', 'var/cache.js', 'data/main.py',
    'web/uploads/photo.png', 'storage/main.py', 'database/schema.sql',
    'server/users.db', 'web/accounts.sqlite', 'other/main.py',
    'runtime/engineering-imports/model.json', 'runtime/Engineering-Imports/model.json',
    'runtime/audit/events.json', 'runtime/sessions/session.json', 'runtime/outputs/scene.json',
    'runtime/media/image.png', 'runtime/exported.log', 'server/private.pem',
    'docs/assets/build_artwork.py', 'docs/assets/render_artwork.mjs', 'docs/outside-assets.png',
])
def test_malicious_or_protected_manifest_paths_are_rejected(tmp_path, path):
    release = package(tmp_path)
    site, preserved = old_site(tmp_path)
    write(release / 'manifest.json', json.dumps({'schema_version': 1, 'files': [{'path': path, 'sha256': '0' * 64}]}))
    run(release, 'install', '--target', site, expected=2)
    assert (site / 'main.py').read_text() == 'old main\n'
    assert not deploy.backup_parent(site).exists()
    assert_preserved(site, preserved)


@pytest.mark.parametrize('case', ['hash', 'unlisted', 'missing', 'duplicate', 'case_collision', 'prefix'])
def test_manifest_inventory_and_hashes_are_enforced(tmp_path, case):
    release = package(tmp_path)
    manifest_path = release / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if case == 'hash':
        write(release / 'payload/main.py', 'tampered source')
    elif case == 'unlisted':
        write(release / 'payload/web/unlisted.js', 'extra')
    elif case == 'missing':
        (release / 'payload/main.py').unlink()
    elif case == 'duplicate':
        manifest['files'].append(manifest['files'][0])
    elif case == 'case_collision':
        manifest['files'] += [{'path': name, 'sha256': '0' * 64} for name in ['web/a.js', 'web/A.js']]
    else:
        manifest['files'] += [{'path': name, 'sha256': '0' * 64} for name in ['web/a.js', 'web/a.js/b.js']]
    write(manifest_path, json.dumps(manifest))
    run(release, 'validate', expected=2)


def test_even_empty_protected_payload_directory_is_rejected(tmp_path):
    release = package(tmp_path)
    (release / 'payload/web/uploads').mkdir()
    assert 'Protected data path' in run(release, 'validate', expected=2)


def test_validly_hashed_private_import_manifest_is_rejected(tmp_path):
    release = package(tmp_path, {'main.py': '# new', 'runtime/engineering-imports/task/geometry.json': '{"private":true}'})
    site, preserved = old_site(tmp_path)
    assert 'Protected data path' in run(release, 'install', '--target', site, expected=2)
    assert (site / 'main.py').read_text() == 'old main\n'
    assert not deploy.backup_parent(site).exists()
    assert_preserved(site, preserved)


def test_public_translated_readme_and_documentation_images_are_allowed(tmp_path):
    content = {'README.en.md': '# Wiscomper', 'docs/assets/hero.png': b'png fixture',
               'docs/assets/hero.svg': '<svg/>', 'docs/assets/README.md': '# Sources'}
    release = package(tmp_path, content)
    assert run(release, 'validate')['file_count'] == len(content)


def test_missing_configuration_requires_explicit_new_site_option(tmp_path):
    release = package(tmp_path)
    site = tmp_path / 'fresh-site'; site.mkdir()
    assert '--allow-empty-config' in run(release, 'dry-run', '--target', site, expected=2)
    assert not deploy.backup_parent(site).exists()
    assert run(release, 'dry-run', '--target', site, '--allow-empty-config')['status'] == 'dry-run'


@pytest.mark.parametrize('override', [
    'PUBLIC_SITE_URL=\n', 'PUBLIC_SITE_URL=https://wrong.example.com\n',
    'PUBLIC_SITE_URL=${ANOTHER_URL}\n', 'VISUALIZE_PORT=3088\n',
    'PORT=3088\n', "'PUBLIC_SITE_URL'=''\n",
    'LEGACY_ACCOUNT_BACKEND=sqlite\n', 'VISUALIZE_DATA=\n',
])
def test_effective_config_overrides_refuse_unsafe_deployment(tmp_path, override):
    release = package(tmp_path)
    site, _ = old_site(tmp_path)
    write(site / '.env.local', override)
    run(release, 'install', '--target', site, expected=2)
    assert (site / '.env.local').read_text() == override
    assert not deploy.backup_parent(site).exists()
    assert not (site / '.env.deploy').exists()


def test_process_empty_site_url_is_not_ignored(tmp_path):
    release = package(tmp_path)
    site, _ = old_site(tmp_path)
    environment = {**os.environ, 'PUBLIC_SITE_URL': ''}
    assert 'Effective PUBLIC_SITE_URL' in run(release, 'install', '--target', site, expected=2, env=environment)
    assert not (site / '.env.deploy').exists()


def test_legacy_port_alias_matches_runtime_configuration_precedence(tmp_path):
    release = package(tmp_path)
    site, _ = old_site(tmp_path)
    write(site / '.env', 'PORT=8123\n')
    assert 'VISUALIZE_PORT' in run(release, 'dry-run', '--target', site, expected=2)
    assert run(release, 'dry-run', '--target', site, '--port', 8123)['status'] == 'dry-run'
    environment = {**os.environ, 'PORT': '8444'}
    assert 'VISUALIZE_PORT' in run(release, 'dry-run', '--target', site, '--port', 8123, expected=2, env=environment)
    assert run(release, 'dry-run', '--target', site, '--port', 8444, env=environment)['status'] == 'dry-run'
    write(site / '.env.local', 'PORT=9000\nVISUALIZE_PORT=8123\n')
    assert run(release, 'dry-run', '--target', site, '--port', 8123)['status'] == 'dry-run'


@pytest.mark.parametrize('where', ['payload', 'target', 'backup'])
def test_directory_links_are_rejected(tmp_path, where):
    release = package(tmp_path)
    site, preserved = old_site(tmp_path)
    outside = tmp_path / 'outside'; outside.mkdir()
    write(outside / 'index.html', 'outside sentinel')
    link = release / 'payload/linked' if where == 'payload' else site / 'web' if where == 'target' else deploy.backup_parent(site)
    if link.exists():
        shutil.rmtree(link)
    try:
        if os.name == 'nt':
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], check=True, capture_output=True)
        else:
            link.symlink_to(outside, target_is_directory=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip('This host cannot create directory links.')
    run(release, 'install', '--target', site, expected=2)
    assert (outside / 'index.html').read_text() == 'outside sentinel'
    assert (site / '.env').read_bytes() == preserved['.env']


def test_interrupted_install_can_be_rolled_back_using_prepared_receipt(tmp_path, monkeypatch):
    release = package(tmp_path)
    site, preserved = old_site(tmp_path)
    original = deploy.replace_verified
    calls = []
    def interrupted(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise OSError('simulated interruption')
        return original(*args, **kwargs)
    monkeypatch.setattr(deploy, 'replace_verified', interrupted)
    with pytest.raises(deploy.DeploymentError, match='Installation interrupted'):
        deploy.install(release, site)
    backups = list(deploy.backup_parent(site).glob('*/receipt.json'))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text())['state'] == 'prepared'
    assert (site / 'main.py').read_text() == 'new main\n'
    run(release, 'rollback', '--backup', backups[0].parent)
    assert (site / 'main.py').read_text() == 'old main\n'
    assert not (site / 'server/new.py').exists()
    assert not (site / '.env.deploy').exists()
    assert_preserved(site, preserved)


def test_parent_file_conflict_and_wrong_rollback_target_are_rejected(tmp_path):
    release = package(tmp_path)
    site, _ = old_site(tmp_path)
    write(site / 'server', 'existing non-directory')
    run(release, 'install', '--target', site, expected=2)
    (site / 'server').unlink()
    installed = run(release, 'install', '--target', site)
    other = tmp_path / 'other-site'; other.mkdir()
    assert 'differs' in run(release, 'rollback', '--backup', installed['backup_dir'], '--target', other, expected=2)
    assert (site / 'main.py').read_text() == 'new main\n'
