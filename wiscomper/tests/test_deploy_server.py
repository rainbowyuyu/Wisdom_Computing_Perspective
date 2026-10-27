from argparse import Namespace
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tools import deploy as core
from tools import deploy_server as setup


@pytest.fixture
def release(tmp_path, monkeypatch):
    for name in core.CONFIG_KEYS:
        monkeypatch.delenv(name, raising=False)
    package, target = tmp_path / 'package', tmp_path / 'site'
    (package / 'payload/deploy').mkdir(parents=True)
    target.mkdir()
    sources = {'main.py': b'# new main\n', 'package.json': b'{}', 'package-lock.json': b'{}',
               'requirements-server.txt': b'# fake requirements\n', 'deploy/preflight.py': b'# fake preflight\n'}
    for path, content in sources.items():
        (package / 'payload' / path).write_bytes(content)
    (package / 'manifest.json').write_text(json.dumps({'schema_version': 1, 'files': [
        {'path': path, 'sha256': hashlib.sha256(content).hexdigest()} for path, content in sources.items()]}), encoding='utf-8')
    (target / 'main.py').write_bytes(b'# original main\n')
    (target / '.env').write_bytes(b'MYSQL_USER=existing\nALIYUN_KEY=server-private-placeholder\n')
    (target / 'var').mkdir()
    (target / 'var/old.sqlite3').write_bytes(b'old database must remain')
    (target / 'storage').mkdir()
    (target / 'storage/video.mp4').write_bytes(b'old user video must remain')
    return package, target


@pytest.fixture
def links_supported(tmp_path):
    destination, link = tmp_path / 'link-target', tmp_path / 'link-probe'
    destination.mkdir()
    try:
        link.symlink_to(destination, target_is_directory=True)
    except OSError:
        pytest.skip('directory symlink creation requires developer mode on Windows')
    link.unlink()


def args(target, **kwargs):
    return Namespace(target=target, site_url='https://www.wiscomper.com', port=8000,
                     service_user=None, skip_browser=True, with_manim=False, **kwargs)


def fake_environment(monkeypatch, *, fail_at=None, preflight_status=0):
    calls = []

    def run(command, log, *, cwd=None, env=None, timeout=1200):
        command = list(map(str, command))
        calls.append(command)
        if fail_at and fail_at in command:
            raise setup.SetupError('fake dependency failure')
        if command[1:3] == ['-m', 'venv']:
            python = Path(command[-1]) / 'bin/python'
            python.parent.mkdir(parents=True)
            python.write_text('# fake python', encoding='utf-8')
        if command[1:2] == ['ci']:
            (cwd / 'node_modules').mkdir()

    monkeypatch.setattr(setup, 'run', run)
    monkeypatch.setattr(setup.shutil, 'which', lambda name: '/test-bin/' + name)
    monkeypatch.setattr(setup.subprocess, 'check_output', lambda *a, **k: 'v24.1.0\n')
    def subprocess_run(command, **kwargs):
        if '-c' in command and 'config.load_settings' in command[3]:
            return SimpleNamespace(returncode=0, stdout=json.dumps({'path': str(Path(command[-1]) / 'var/wiscomper-harness')}))
        return SimpleNamespace(returncode=preflight_status)
    monkeypatch.setattr(setup.subprocess, 'run', subprocess_run)
    monkeypatch.setattr(setup, 'service_identity', lambda *a: (1000, 1000))
    monkeypatch.setattr(setup, 'own_tree', lambda *a: None)
    monkeypatch.setattr(setup.os, 'geteuid', lambda: 1000, raising=False)
    monkeypatch.setattr(setup, 'stopped', lambda port: None)
    monkeypatch.setattr(setup, 'installer', lambda _: core)
    monkeypatch.setattr(setup, 'operation_lock', lambda *a: nullcontext())
    return calls


@pytest.mark.parametrize('version,expected', [('v22.19.0', True), ('22.99.3\n', True), ('v24.0.0', True),
    ('v26.1.3', True), ('v22.18.9', False), ('v23.11.0', False), ('v20.19.0', False),
    ('v24.0.0-rc.1', False), ('node v24.0.0', False), ('', False)])
def test_node_version_contract(version, expected):
    assert setup.node_supported(version) is expected


def test_stopped_refuses_listening_ipv4_or_ipv6(monkeypatch):
    for listening in (socket.AF_INET, socket.AF_INET6):
        class Probe:
            def __init__(self, family): self.family = family
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def settimeout(self, value): pass
            def connect_ex(self, address): return 0 if self.family == listening else 1
        monkeypatch.setattr(setup.socket, 'socket', Probe)
        with pytest.raises(setup.SetupError, match='仍在运行'):
            setup.stopped(8000)


def test_stopped_checks_port_argument_before_connect(monkeypatch):
    monkeypatch.setattr(setup.socket, 'socket', lambda *args: pytest.fail('invalid port must not probe'))
    for value in (0, 65536, 'secret-value', True):
        with pytest.raises(setup.SetupError, match='端口无效'):
            setup.stopped(value)


def test_port_change_still_checks_old_service(release, monkeypatch):
    _, target = release
    observed = []
    monkeypatch.setattr(setup, 'stopped', observed.append)
    setup.ensure_stopped(target, core, 8090)
    assert observed == [8000, 8090]
    (target / '.env.local').write_text('PORT=8011\n', encoding='utf-8')
    observed.clear()
    setup.ensure_stopped(target, core, 8090)
    assert observed == [8011, 8090]


@pytest.mark.parametrize('failure', ['install', 'ci'])
def test_dependency_failure_never_replaces_old_site(release, monkeypatch, failure):
    package, target = release
    before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob('*') if p.is_file()}
    fake_environment(monkeypatch, fail_at=failure)
    with pytest.raises(setup.SetupError, match='fake dependency failure'):
        setup._deploy(args(target), package, core, target)
    assert {str(p.relative_to(target)): p.read_bytes() for p in target.rglob('*') if p.is_file()} == before
    assert not (target / '.env.deploy').exists()
    assert not (target / 'node_modules').exists()


def test_preflight_failure_never_runs_npm_or_replaces_code(release, monkeypatch):
    package, target = release
    calls = fake_environment(monkeypatch, preflight_status=1)
    with pytest.raises(setup.SetupError, match='检查未通过'):
        setup._deploy(args(target), package, core, target)
    assert (target / 'main.py').read_bytes() == b'# original main\n'
    assert not any('ci' in command for command in calls)
    assert not (target / '.env.deploy').exists()


def test_service_user_access_failure_happens_before_replacing_site(release, monkeypatch):
    package, target = release
    fake_environment(monkeypatch)

    def failed_access(*args):
        raise setup.SetupError('fake service-user permission failure')

    monkeypatch.setattr(setup, 'check_service_access', failed_access)
    with pytest.raises(setup.SetupError, match='permission failure'):
        setup._deploy(args(target), package, core, target)
    assert (target / 'main.py').read_bytes() == b'# original main\n'
    assert not (target / '.env.deploy').exists()


def test_service_access_probe_uses_selected_uid_and_never_reads_env_content(tmp_path, monkeypatch):
    runtime, target = tmp_path / 'runtime', tmp_path / 'site'
    runtime.mkdir()
    target.mkdir()
    observed = []
    monkeypatch.setattr(setup, 'effective_data_directory', lambda *args: target / 'var/wiscomper-harness')
    monkeypatch.setattr(setup.os, 'geteuid', lambda: 0, raising=False)
    monkeypatch.setattr(setup.subprocess, 'run', lambda command, **kwargs: (observed.append((command, kwargs)), SimpleNamespace(returncode=0))[1])
    setup.check_service_access(target, runtime, 1000, 1001, runtime / 'prepare.log', tmp_path / 'package', '/usr/bin/node')
    command, options = observed[0]
    assert options['user'] == 1000 and options['group'] == 1001 and options['extra_groups'] == []
    assert 'os.access' in command[3] and 'read_text' not in command[3] and 'open(' not in command[3]
    assert observed[1][0] == ['/usr/bin/node', '--version']
    assert observed[1][1]['user'] == 1000


def test_effective_data_directory_uses_shipped_loader_and_private_env_not_app(tmp_path, monkeypatch):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    observed = []
    data = tmp_path / 'custom-private-data'
    monkeypatch.setattr(setup.subprocess, 'run', lambda command, **kwargs:
        (observed.append((command, kwargs)), SimpleNamespace(returncode=0, stdout=json.dumps({'path': str(data)})))[1])
    actual = setup.effective_data_directory(tmp_path / 'site', runtime, tmp_path / 'package', runtime / 'prepare.log')
    command, options = observed[0]
    assert actual == data
    assert command[-2:] == [str(tmp_path / 'package/payload/configuration.py'), str(tmp_path / 'site')]
    assert 'load_settings' in command[3] and 'server.app' not in command[3] and 'Store' not in command[3]
    assert options['stdout'] == subprocess.PIPE


@pytest.mark.parametrize('exists', [True, False])
def test_unwritable_custom_data_is_rejected_without_changing_files(tmp_path, monkeypatch, exists):
    runtime, target = tmp_path / 'runtime', tmp_path / 'site'
    runtime.mkdir()
    target.mkdir()
    data_parent = tmp_path / 'custom-data-parent'
    data_parent.mkdir()
    data = data_parent / 'workbench'
    if exists:
        data.mkdir()
    monkeypatch.setattr(setup, 'effective_data_directory', lambda *args: data)
    monkeypatch.setattr(setup.os, 'geteuid', lambda: 1000, raising=False)
    monkeypatch.setattr(setup.os, 'access', lambda path, mode:
        not (Path(path) in (data, data_parent) and mode & os.W_OK))

    def fake_probe(command, **kwargs):
        assert '-c' in command, 'Node must not run after failed data access'
        monkeypatch.setattr(sys, 'argv', ['-c', *command[4:]])
        try:
            exec(command[3], {})
        except SystemExit as result:
            return SimpleNamespace(returncode=result.code)
        pytest.fail('expected probe exit')

    monkeypatch.setattr(setup.subprocess, 'run', fake_probe)
    with pytest.raises(setup.SetupError, match='VISUALIZE_DATA'):
        setup.check_service_access(target, runtime, 1000, 1000, runtime / 'prepare.log', tmp_path / 'package', '/usr/bin/node')
    assert data.exists() is exists
    assert not (target / '.env.deploy').exists()


def test_node_access_is_checked_as_service_user(tmp_path, monkeypatch):
    runtime, target = tmp_path / 'runtime', tmp_path / 'site'
    runtime.mkdir()
    target.mkdir()
    monkeypatch.setattr(setup, 'effective_data_directory', lambda *args: target / 'var/wiscomper-harness')
    monkeypatch.setattr(setup.os, 'geteuid', lambda: 0, raising=False)
    calls = []
    def fake_probe(command, **options):
        calls.append((command, options))
        return SimpleNamespace(returncode=1 if command[-1] == '--version' else 0)
    monkeypatch.setattr(setup.subprocess, 'run', fake_probe)
    with pytest.raises(setup.SetupError, match='Node.js'):
        setup.check_service_access(target, runtime, 1000, 1001, runtime / 'prepare.log', tmp_path / 'package', '/root/.nvm/node')
    assert calls[-1][0] == ['/root/.nvm/node', '--version']
    assert calls[-1][1]['user'] == 1000 and calls[-1][1]['group'] == 1001


def test_new_deployment_and_rollback_preserve_env_database_and_old_dependencies(release, monkeypatch, links_supported):
    package, target = release
    (target / 'node_modules').mkdir()
    (target / 'node_modules/old-module.js').write_bytes(b'old module')
    (target / '.venv-wiscomper').mkdir()
    (target / '.venv-wiscomper/old-python').write_bytes(b'old python')
    original_env = (target / '.env').read_bytes()
    fake_environment(monkeypatch)
    setup._deploy(args(target), package, core, target)
    backup = next(p for p in core.backup_parent(target).iterdir() if p.is_dir())
    assert (target / 'main.py').read_bytes() == b'# new main\n'
    assert (target / 'node_modules').is_symlink()
    assert (target / '.venv-wiscomper').is_symlink()
    assert (target / '.env').read_bytes() == original_env
    assert (target / 'var/old.sqlite3').read_bytes() == b'old database must remain'
    assert (target / 'storage/video.mp4').read_bytes() == b'old user video must remain'
    setup.restore(package, backup)
    assert (target / 'main.py').read_bytes() == b'# original main\n'
    assert (target / 'node_modules/old-module.js').read_bytes() == b'old module'
    assert (target / '.venv-wiscomper/old-python').read_bytes() == b'old python'
    assert not (target / '.env.deploy').exists()
    assert (target / '.env').read_bytes() == original_env
    setup.restore(package, backup)  # second rollback is harmless


def test_link_failure_restores_program_and_original_runtime(release, monkeypatch, links_supported):
    package, target = release
    (target / 'node_modules').mkdir()
    (target / 'node_modules/original').write_bytes(b'preserve this')
    fake_environment(monkeypatch)
    original_symlink = Path.symlink_to

    def failing_symlink(self, destination, **kwargs):
        if self == target / 'node_modules':
            raise OSError('simulated disk error during second link')
        return original_symlink(self, destination, **kwargs)

    monkeypatch.setattr(Path, 'symlink_to', failing_symlink)
    with pytest.raises(setup.SetupError, match='已恢复'):
        setup._deploy(args(target), package, core, target)
    assert (target / 'main.py').read_bytes() == b'# original main\n'
    assert (target / 'node_modules/original').read_bytes() == b'preserve this'
    assert not (target / '.venv-wiscomper').exists()
    assert not (target / '.env.deploy').exists()


def test_runtime_conflict_refuses_code_rollback_before_any_mutation(release, monkeypatch, links_supported):
    package, target = release
    fake_environment(monkeypatch)
    setup._deploy(args(target), package, core, target)
    backup = next(p for p in core.backup_parent(target).iterdir() if p.is_dir())
    (target / 'node_modules').unlink()
    (target / 'node_modules').mkdir()
    (target / 'node_modules/new-edit').write_bytes(b'new user edit')
    with pytest.raises(setup.SetupError, match='已被修改'):
        setup.restore(package, backup)
    assert (target / 'main.py').read_bytes() == b'# new main\n'
    assert (target / 'node_modules/new-edit').read_bytes() == b'new user edit'


def test_tampered_payload_detected_after_preparation_before_code_or_links(release, monkeypatch):
    package, target = release
    fake_environment(monkeypatch)
    (package / 'payload/main.py').write_bytes(b'# replaced after archive validation')
    with pytest.raises(core.DeploymentError, match='SHA256'):
        setup._deploy(args(target), package, core, target)
    assert (target / 'main.py').read_bytes() == b'# original main\n'
    assert not (target / 'node_modules').exists()


def test_original_dependency_identity_is_required_for_rollback(release):
    _, target = release
    runtime = target.with_name(target.name + '.deploy-runtimes') / 'release'
    backup = target.with_name(target.name + '.deploy-backups') / 'release'
    backup.mkdir(parents=True)
    (target / 'node_modules').mkdir()
    entries = setup.link_plan(target, runtime, backup)
    state = {'schema_version': 1, 'target': str(target), 'runtime': str(runtime), 'links': entries}
    (target / 'node_modules').rename(target / 'original-retained')
    (target / 'node_modules').mkdir()
    with pytest.raises(setup.SetupError, match='已被替换'):
        setup.runtime_rollback_plan(target, backup, state)
    assert (target / 'original-retained').is_dir()


def test_wrapper_lock_rejects_concurrent_operation(release, monkeypatch):
    _, target = release
    fake = SimpleNamespace(LOCK_EX=1, LOCK_NB=2, LOCK_UN=4)

    def flock(fd, flags):
        if flags != fake.LOCK_UN:
            raise OSError('locked')

    fake.flock = flock
    monkeypatch.setitem(sys.modules, 'fcntl', fake)
    with pytest.raises(setup.SetupError, match='另一个部署'):
        with setup.operation_lock(target, core):
            pytest.fail('must not enter')


def test_dependency_error_output_never_exposes_command_error(tmp_path, monkeypatch):
    def failing_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, 'private-url:password')
    monkeypatch.setattr(setup.subprocess, 'run', failing_run)
    with pytest.raises(setup.SetupError) as error:
        setup.run(['fake', 'private-url:password'], tmp_path / 'private.log')
    assert 'password' not in str(error.value)
