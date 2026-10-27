"""Server compatibility uses synthetic credentials and temporary directories."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from configuration import load_settings, data_directory, server_port, ai_enabled
from runtime import planner, qwen
from server.legacy_accounts import LegacyAccounts
from test_planner import SECRET, PROPOSAL
from test_qwen import qwen_local, qwen_offline
from test_planner import endpoint


def test_old_files_load_without_rewriting_or_interpolation(tmp_path):
    original = (b'MYSQL_HOST=localhost\nMYSQL_DB=legacy\nMYSQL_USER=site\n'
                b"MYSQL_PASSWORD='literal-${KEEP_SECRET}'\nPORT=8000\n"
                b'ALIYUN_KEY=synthetic-key\nSOLVER_MODEL=qwen-plus\nAI_GLOBAL_DAILY_CALLS=300\n')
    (tmp_path / '.env').write_bytes(original)
    (tmp_path / '.env.deploy').write_text('PUBLIC_SITE_URL=https://www.wiscomper.com\nVISUALIZE_PORT=3088\nVISUALIZE_DATA=var/wiscomper-harness\nLEGACY_ACCOUNT_BACKEND=mysql\n')
    settings = load_settings(tmp_path, {})
    assert settings['LEGACY_MYSQL_PASSWORD'] == 'literal-${KEEP_SECRET}'
    assert settings['LEGACY_MYSQL_DATABASE'] == 'legacy'
    assert settings['LEGACY_ACCOUNT_BACKEND'] == 'mysql'
    assert settings['VISUALIZATION_QWEN_MODEL'] == 'qwen-plus'
    assert settings['VISUALIZE_DAILY_CALLS'] == '300'
    assert settings['PUBLIC_SITE_URL'] == 'https://www.wiscomper.com'
    assert server_port(settings) == 8000
    assert data_directory(settings, tmp_path) == tmp_path / 'var/wiscomper-harness'
    assert (tmp_path / '.env').read_bytes() == original


def test_aliases_obey_source_precedence_and_explicit_new_names(tmp_path):
    (tmp_path / '.env.deploy').write_text('LEGACY_MYSQL_HOST=default\n')
    (tmp_path / '.env').write_text('LEGACY_MYSQL_HOST=file\nLEGACY_MYSQL_PASSWORD=file-secret\n')
    (tmp_path / '.env.local').write_text('MYSQL_HOST=local\nMYSQL_PASSWORD=local-secret\n')
    settings = load_settings(tmp_path, {'MYSQL_HOST': 'process', 'MYSQL_PASSWORD': 'process-secret'})
    assert settings['LEGACY_MYSQL_HOST'] == 'process'
    assert settings['LEGACY_MYSQL_PASSWORD'] == 'process-secret'
    assert load_settings(tmp_path, {})['LEGACY_MYSQL_HOST'] == 'local'
    assert load_settings(tmp_path, {'MYSQL_HOST':'alias','LEGACY_MYSQL_HOST':'explicit'})['LEGACY_MYSQL_HOST'] == 'explicit'
    assert load_settings(tmp_path, {'LEGACY_MYSQL_PASSWORD':''})['LEGACY_MYSQL_PASSWORD'] == ''
    assert server_port({}) == 3088
    with pytest.raises(ValueError): server_port({'VISUALIZE_PORT':'70000'})


def test_legacy_account_adapter_accepts_original_mysql_keys_without_connecting():
    settings = {'MYSQL_HOST':'localhost','MYSQL_PORT':'3306','MYSQL_DB':'legacy','MYSQL_USER':'site','MYSQL_PASSWORD':'synthetic'}
    accounts = LegacyAccounts(lambda: settings, lambda: None)
    options = accounts._mysql_options()
    assert options['database'] == 'legacy' and options['password'] == 'synthetic'


@pytest.mark.parametrize('key_name', ['ALIYUN_KEY','DASHSCOPE_API_KEY','QWEN_API_KEY'])
def test_server_qwen_uses_only_explicit_private_environment(monkeypatch, tmp_path, key_name):
    monkeypatch.setattr(qwen, 'WINDOWS', False)
    monkeypatch.setattr(qwen, 'CONFIG_PATH', tmp_path / 'missing-global-config.json')
    monkeypatch.setenv('OPENAI_API_KEY', 'unrelated-secret')
    monkeypatch.setenv('NODE_OPTIONS', 'untrusted-hook')
    env = {key_name: SECRET, 'SOLVER_MODEL':'qwen-plus', 'VISUALIZE_DATA':str(tmp_path/'private')}
    monkeypatch.setattr(planner, '_settings', lambda: env)
    config = planner._load_provider('qwen')
    assert config.api_key == SECRET and not config.credential_loader and not config.powershell
    assert config.model == 'qwen-plus' and SECRET not in repr(config)
    assert planner._load_provider('qwen', env, True).model == 'qwen3-vl-plus'
    child = planner._child_environment(config, 'test-task')
    assert child['DSH_VISUALIZATION_API_KEY'] == SECRET
    assert child['DSH_VISUALIZATION_PROVIDER'] == 'qwen'
    assert child['DSH_HOME'] == str(tmp_path/'private'/'dsh-home')
    assert not {'ALIYUN_KEY','DASHSCOPE_API_KEY','QWEN_API_KEY','OPENAI_API_KEY','NODE_OPTIONS'} & child.keys()
    command = planner._launch_command(config, '/usr/bin/node')
    assert command == ['/usr/bin/node', str(planner.BRIDGE)] and SECRET not in repr(command)


@pytest.mark.parametrize('values', [{}, {'ALIYUN_KEY':'bad\nkey'}, {'ALIYUN_KEY':SECRET,'VISUALIZATION_QWEN_BASE_URL':'https://example.com/v1'}])
def test_server_qwen_missing_and_invalid_configuration_fails_closed(monkeypatch, values):
    monkeypatch.setattr(qwen, 'WINDOWS', False)
    with pytest.raises(planner.PlannerError) as error:
        planner._load_provider('qwen', values)
    assert error.value.code == 'NOT_CONFIGURED' and SECRET not in str(error.value)


def test_server_qwen_native_flow_uses_same_guarded_contract(qwen_offline, monkeypatch, tmp_path):
    monkeypatch.setattr(qwen, 'WINDOWS', False)
    monkeypatch.setattr(planner, '_settings', lambda: {'VISUALIZE_DATA':str(tmp_path/'native-data')})
    config = planner._load_provider('qwen', {'ALIYUN_KEY':SECRET})
    from server.schema import Proposal
    payload = {'prompt':'解释输入输出','duration':12,'previous':None,'image_data_url':None,'asset_id':None,
               'schema':Proposal.model_json_schema(),'max_tokens':8192,'max_steps':3,'deadline_ms':120_000}
    assert planner._invoke(config, planner._runtime(), payload, None, None) == PROPOSAL
    assert len(qwen_offline[1]) == 3
    assert all(call['auth'] == 'Bearer ' + SECRET for call in qwen_offline[1])
    assert all(call['body']['model'] == 'qwen-plus' for call in qwen_offline[1])


@pytest.mark.parametrize('disabled', ['0','false','off','', 'invalid'])
def test_old_ai_switch_prevents_calls_before_loading_credentials(disabled):
    assert not ai_enabled({'AI_ENABLED':disabled})
    with pytest.raises(planner.PlannerError) as error:
        planner._load_provider('qwen', {'AI_ENABLED':disabled})
    assert error.value.code == 'AI_DISABLED'


def test_main_import_needs_only_standard_library():
    entry = Path(__file__).resolve().parents[1] / 'main.py'
    check = subprocess.run([sys.executable, '-S', '-c',
        'import runpy,sys; assert callable(runpy.run_path(sys.argv[1])["run"])', str(entry)],
        capture_output=True, text=True, timeout=10)
    assert check.returncode == 0, check.stderr


def test_baota_old_start_entry_reexecutes_before_loading_dependencies(tmp_path, monkeypatch):
    import main
    environment = tmp_path / '.venv-wiscomper'
    executable = environment / 'bin' / 'python'
    executable.parent.mkdir(parents=True)
    executable.write_text('test-only')
    node = tmp_path / 'node-runtime' / 'node'
    node.parent.mkdir()
    node.write_text('test-only')
    (environment / 'wiscomper-runtime.json').write_text(json.dumps({'node':str(node)}))
    (tmp_path / '.env.deploy').write_text('VISUALIZE_PORT=8000')
    monkeypatch.setattr(main, 'ROOT', tmp_path)
    monkeypatch.setattr(main.sys, 'platform', 'linux')
    monkeypatch.setattr(main.sys, 'prefix', str(tmp_path / 'old-environment'))
    monkeypatch.setattr(main.sys, 'argv', ['start.py'])
    monkeypatch.delenv('PLAYWRIGHT_BROWSERS_PATH', raising=False)
    monkeypatch.delenv('VISUALIZATION_NODE', raising=False)
    monkeypatch.setenv('PATH', 'original-path')
    calls = []
    class ReplacedProcess(Exception):
        pass
    def replace(path, args):
        calls.append((path, args))
        raise ReplacedProcess
    monkeypatch.setattr(main.os, 'execv', replace)
    with pytest.raises(ReplacedProcess):
        main.run()
    assert calls == [(str(executable), [str(executable), str(tmp_path/'main.py')])]
    assert main.os.environ['PLAYWRIGHT_BROWSERS_PATH'] == str(environment / '.playwright')
    assert main.os.environ['VISUALIZATION_NODE'] == str(node)
    assert main.os.environ['PATH'].split(main.os.pathsep)[0] == str(node.parent)
