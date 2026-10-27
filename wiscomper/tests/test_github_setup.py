"""Synthetic local config files only; never use or print real credentials."""
import codecs
import json
import os
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

import pytest

from scripts import configure_github as setup


def test_local_prefill_contains_only_application_metadata():
    urls=setup.local_urls()
    parsed=urlsplit(urls['create_app_url']);query=parse_qs(parsed.query)
    assert parsed.scheme=='https' and parsed.netloc=='github.com' and parsed.path=='/settings/applications/new'
    assert set(query)=={'oauth_application[name]','oauth_application[url]','oauth_application[callback_url]','oauth_application[description]'}
    assert query['oauth_application[callback_url]']==['http://127.0.0.1:3088/api/auth/github/callback']
    assert 'secret' not in urls['create_app_url'].lower()


def test_atomic_setup_preserves_unrelated_multiline_comments_bom_and_newlines(tmp_path):
    path=tmp_path/'.env'
    unchanged='# private project settings\r\nOTHER_KEY="keep # and ="\r\nMULTILINE="line1\r\nline2"\r\nVISUALIZE_DAILY_CALLS=42\r\n'
    path.write_bytes(codecs.BOM_UTF8+(unchanged+"export GITHUB_CLIENT_ID='old'\r\nGITHUB_CLIENT_SECRET='old-secret'\r\nGITHUB_CLIENT_ID=duplicate\r\nPUBLIC_SITE_URL=\r\n").encode())
    setup.configure(path,'synthetic-client','synthetic-secret',environment={})
    raw,values,bindings=setup.read_env(path)
    assert raw.startswith(codecs.BOM_UTF8) and unchanged.encode() in raw
    assert values['GITHUB_CLIENT_ID']=='synthetic-client' and values['GITHUB_CLIENT_SECRET']=='synthetic-secret'
    assert values['PUBLIC_SITE_URL']=='' and values['VISUALIZE_DAILY_CALLS']=='42'
    assert sum(item.key=='GITHUB_CLIENT_ID' for item in bindings)==1
    assert not list(tmp_path.glob('*.tmp')) and not list(tmp_path.glob('*.lock'))


def test_setup_creates_missing_env_without_touching_example(tmp_path):
    path=tmp_path/'.env';example=tmp_path/'.env.example';example.write_text('SAMPLE=untouched')
    setup.configure(path,'synthetic-client','synthetic-secret',environment={})
    status=setup.check(path,environment={})
    assert status['configured'] and status['client_secret_present'] and not status['public_mode']
    assert not status['network_request'] and not status['remote_authorization_verified']
    assert 'synthetic-secret' not in json.dumps(status) and 'synthetic-client' not in json.dumps(status)
    assert example.read_text()=='SAMPLE=untouched'


@pytest.mark.parametrize('source,environment',[
    ('PUBLIC_SITE_URL=https://public.example\n',{}),
    ('',{'GITHUB_CLIENT_ID':'inherited'}),('',{'GITHUB_CLIENT_SECRET':'inherited'}),
    ('',{'PUBLIC_SITE_URL':''}),('BAD="unterminated\n',{}),
])
def test_setup_fails_closed_for_public_mode_override_or_unparseable_env(tmp_path,source,environment):
    path=tmp_path/'.env';path.write_text(source,encoding='utf-8')
    with pytest.raises(setup.SetupError):setup.configure(path,'synthetic-client','synthetic-secret',environment=environment)
    assert path.read_text(encoding='utf-8')==source
    assert not list(tmp_path.glob('*.tmp')) and not list(tmp_path.glob('*.lock'))


@pytest.mark.parametrize('ident,secret',[('bad\nID','secret'),('client','bad\nsecret'),('','secret'),('client','')])
def test_invalid_credentials_never_reach_file_or_error(tmp_path,ident,secret):
    path=tmp_path/'.env'
    with pytest.raises(setup.SetupError) as error:setup.configure(path,ident,secret,environment={})
    assert not path.exists()
    assert 'bad\n' not in str(error.value)


def test_replace_failure_preserves_original_and_removes_staging_file(tmp_path,monkeypatch):
    path=tmp_path/'.env';path.write_text('UNRELATED=keep\n')
    def fail(*args):raise OSError('synthetic-error')
    monkeypatch.setattr(setup.os,'replace',fail)
    with pytest.raises(OSError):setup.configure(path,'synthetic-client','synthetic-secret',environment={})
    assert path.read_text()=='UNRELATED=keep\n'
    assert sorted(item.name for item in tmp_path.iterdir())==['.env']


def test_concurrent_file_change_aborts_without_overwriting(tmp_path,monkeypatch):
    path=tmp_path/'.env';path.write_text('UNRELATED=before\n')
    original=setup.tempfile.mkstemp
    def race(*args,**kwargs):
        result=original(*args,**kwargs);path.write_text('UNRELATED=concurrent\n');return result
    monkeypatch.setattr(setup.tempfile,'mkstemp',race)
    with pytest.raises(setup.SetupError):setup.configure(path,'synthetic-client','synthetic-secret',environment={})
    assert path.read_text()=='UNRELATED=concurrent\n'
    assert sorted(item.name for item in tmp_path.iterdir())==['.env']


def test_second_config_writer_cannot_take_existing_lock(tmp_path):
    path=tmp_path/'.env';lock=tmp_path/'.env.github-setup.lock';lock.write_text('')
    with pytest.raises(setup.SetupError):setup.configure(path,'synthetic-client','synthetic-secret',environment={})
    assert not path.exists() and lock.exists()


def test_check_and_guide_never_emit_secret_or_make_requests(tmp_path,monkeypatch,capsys):
    path=tmp_path/'.env'
    path.write_text('GITHUB_CLIENT_ID=synthetic-client\nGITHUB_CLIENT_SECRET=synthetic-secret\nPUBLIC_SITE_URL=\n')
    for name in setup.KEYS:monkeypatch.delenv(name,raising=False)
    assert setup.main(['--check','--env-file',str(path)])==0
    output=capsys.readouterr();report=json.loads(output.out)
    assert report['configured'] and report['callback_url']=='http://127.0.0.1:3088/api/auth/github/callback'
    assert 'synthetic-secret' not in output.out+output.err and 'synthetic-client' not in output.out+output.err
    assert setup.main(['--guide','--env-file',str(path)])==0
    output=capsys.readouterr();assert 'synthetic-secret' not in output.out+output.err
    assert json.loads(output.out)['create_app_url'].startswith('https://github.com/settings/applications/new?')


def test_noninteractive_input_fails_before_reading_secret(monkeypatch):
    monkeypatch.setattr(setup.sys.stdin,'isatty',lambda:False)
    monkeypatch.setattr(setup.getpass,'getpass',lambda *_:pytest.fail('must not read redirected credentials'))
    with pytest.raises(setup.SetupError,match='交互终端'):setup.hidden_input('Secret:')


def test_env_override_presence_is_reported_without_value(tmp_path):
    report=setup.check(tmp_path/'.env',environment={'GITHUB_CLIENT_ID':'process-client','GITHUB_CLIENT_SECRET':'process-secret'})
    assert report['configured'] and report['environment_overrides']==['GITHUB_CLIENT_ID','GITHUB_CLIENT_SECRET']
    assert 'process-secret' not in json.dumps(report)


def test_save_authorized_id_only_keeps_all_other_bindings(tmp_path):
    path=tmp_path/'.env'
    unchanged="GITHUB_CLIENT_SECRET='keep-existing-secret'\r\nPUBLIC_SITE_URL=\r\nOTHER=keep\r\n"
    path.write_bytes(("GITHUB_CLIENT_ID=old\r\n"+unchanged).encode())
    setup.save_client_id(path,'public-client-id',environment={})
    raw,values,_=setup.read_env(path)
    assert unchanged.encode() in raw
    assert values['GITHUB_CLIENT_ID']=='public-client-id'


def test_interactive_blank_id_preserves_saved_id(tmp_path,monkeypatch,capsys):
    path=tmp_path/'.env';path.write_text('GITHUB_CLIENT_ID=existing-client\n')
    for name in setup.KEYS:monkeypatch.delenv(name,raising=False)
    values=iter(['','new-synthetic-secret'])
    monkeypatch.setattr(setup,'hidden_input',lambda _:next(values))
    assert setup.main(['--env-file',str(path)])==0
    _,saved,_=setup.read_env(path)
    assert saved['GITHUB_CLIENT_ID']=='existing-client' and saved['GITHUB_CLIENT_SECRET']=='new-synthetic-secret'
    output=capsys.readouterr()
    assert 'existing-client' not in output.out+output.err and 'new-synthetic-secret' not in output.out+output.err
