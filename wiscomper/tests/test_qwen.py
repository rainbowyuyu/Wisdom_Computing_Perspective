"""Qwen stays entirely offline: synthetic loader + localhost SSE transport.

Tests exercise the real PowerShell launcher and native DSH, but never decrypt
the user's credential or connect to DashScope. The fetch preload is test-only;
the production environment strips inherited NODE_OPTIONS.
"""
import base64
import io
import json
import threading

import pytest
from PIL import Image

from runtime import planner, qwen
from server.schema import CreateRequest, Proposal
from test_planner import endpoint, isolate, PROPOSAL, SECRET, embedded_objects, interactive_proposal


@pytest.fixture
def qwen_local(monkeypatch, tmp_path):
    monkeypatch.setattr(qwen, 'WINDOWS', True)
    credential = tmp_path / 'key.dpapi'
    credential.write_text('synthetic-encrypted-marker', encoding='utf-8')
    loader = tmp_path / 'Load-Qwen.ps1'
    loader.write_text("$env:DASHSCOPE_API_KEY = '" + SECRET + "'\n"
                      "$env:QWEN_API_KEY = $env:DASHSCOPE_API_KEY\n"
                      "$env:QWEN_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'\n", encoding='utf-8')
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'provider':'qwen_dashscope','credential_format':'windows_dpapi_current_user',
        'credential_file':str(credential),'compatible_base_url':'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'connection_verified':False}), encoding='utf-8')
    monkeypatch.setattr(qwen,'CONFIG_PATH',config)
    monkeypatch.setattr(qwen,'LOADER_PATH',loader)
    return config, loader, credential


@pytest.fixture
def qwen_offline(qwen_local, endpoint, monkeypatch, tmp_path):
    # This hook can reach only the synthetic localhost server. Production never
    # sets NODE_OPTIONS, and real configured endpoints cannot point at localhost.
    hook = tmp_path / 'offline-fetch.mjs'
    hook.write_text("""const nativeFetch=globalThis.fetch;
      globalThis.fetch=(input,init)=>{
        const url=typeof input==='string'?input:input instanceof URL?input.href:input.url;
        if(url!=='https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions')throw new Error('TEST_NETWORK_BLOCKED');
        if(init.redirect!=='error')throw new Error('REDIRECT_NOT_BLOCKED');
        return nativeFetch(process.env.TEST_QWEN_ORIGIN+'/v1/chat/completions',init);
      };""", encoding='utf-8')
    original=planner._child_environment
    def child(config,task_id):
        result=original(config,task_id)
        result['NODE_OPTIONS']='--import='+hook.as_uri()
        result['TEST_QWEN_ORIGIN']=endpoint[0]
        return result
    monkeypatch.setattr(planner,'_child_environment',child)
    endpoint[2].update(confirmation=True, qwen_stream=True)
    return endpoint


def invoke_qwen(endpoint, cancelled=None, **overrides):
    config=planner._load_provider('qwen',{}, bool(overrides.get('image_data_url')))
    payload={'prompt':'解释输入与输出','duration':12,'previous':None,'image_data_url':None,'asset_id':None,
             'schema':Proposal.model_json_schema(),'max_tokens':8192,'max_steps':3,'deadline_ms':120_000,**overrides}
    if payload.get('previous_exact') is not None:
        payload['previous']=planner._previous_context(payload['previous_exact'])
    return planner._invoke(config,planner._runtime(),payload,cancelled,None)


def test_qwen_config_is_metadata_only_fresh_and_modality_aware(qwen_local, monkeypatch):
    text=planner._load_provider('qwen',{})
    vision=planner._load_provider('qwen',{},True)
    assert text.model=='qwen-plus' and vision.model=='qwen3-vl-plus'
    assert text.api=='openai-completions' and text.effort=='off' and text.api_key==''
    assert planner._load_provider('qwen',{'VISUALIZATION_QWEN_MODEL':'qwen-plus-2025-07-28'}).model=='qwen-plus-2025-07-28'
    env={'VISUALIZATION_QWEN_VISION_MODEL':'qwen3-vl-plus-2025-12-19',
         'VISUALIZATION_QWEN_BASE_URL':'https://dashscope-intl.aliyuncs.com/compatible-mode/v1'}
    changed=planner._load_provider('qwen',env,True)
    assert changed.model==env['VISUALIZATION_QWEN_VISION_MODEL'] and changed.qwen_base_override
    # Decryption is not attempted by health; even this fake encrypted file passes
    # local configuration checks without claiming remote authentication.
    monkeypatch.setattr(planner,'_settings',lambda:{'CC_SWITCH_DB_PATH':str(qwen_local[0].parent/'missing.db'),
        'CC_SWITCH_CLAUDE_SETTINGS':str(qwen_local[0].parent/'missing.json')})
    status=next(item for item in planner.capabilities() if item['id']=='qwen')
    assert status['available'] and '远端认证与模型权限未验证' in status['message']
    assert SECRET not in json.dumps(status) and 'credential' not in json.dumps(status)
    qwen_local[2].unlink()
    with pytest.raises(planner.PlannerError) as error:planner._load_provider('qwen',{})
    assert error.value.code=='NOT_CONFIGURED'


@pytest.mark.parametrize('url',[
    'http://127.0.0.1:3000/v1','https://evil.test/compatible-mode/v1',
    'https://dashscope.aliyuncs.com.evil.test/compatible-mode/v1',
    'https://user:pass@dashscope.aliyuncs.com/compatible-mode/v1',
    'https://dashscope.aliyuncs.com:444/compatible-mode/v1',
    'https://dashscope.aliyuncs.com/compatible-mode/v1?key=x',
    'https://dashscope.aliyuncs.com/compatible-mode/v1#fragment',
    'https://dashscope.aliyuncs.com/other',
])
def test_qwen_rejects_unofficial_or_ambiguous_routes(qwen_local,url):
    with pytest.raises(planner.PlannerError) as error:
        planner._load_provider('qwen',{'VISUALIZATION_QWEN_BASE_URL':url})
    assert error.value.code=='NOT_CONFIGURED' and url not in str(error.value)


@pytest.mark.parametrize('name',['VISUALIZATION_QWEN_API_KEY','VISUALIZATION_QWEN_API','VISUALIZATION_QWEN_AUTH'])
def test_qwen_rejects_plaintext_key_and_protocol_overrides(qwen_local,name):
    with pytest.raises(planner.PlannerError):planner._load_provider('qwen',{name:SECRET})


def test_qwen_environment_and_launch_do_not_decrypt_or_reuse_ambient_keys(qwen_local,monkeypatch):
    for name in ['QWEN_API_KEY','DASHSCOPE_API_KEY','DSH_VISUALIZATION_API_KEY','NODE_OPTIONS','HTTPS_PROXY','OPENAI_API_KEY']:
        monkeypatch.setenv(name,'stale-private-value')
    config=planner._load_provider('qwen',{})
    env=planner._child_environment(config,'visual-'+'a'*32)
    assert 'stale-private-value' not in json.dumps(env)
    assert not {'DSH_VISUALIZATION_API_KEY','QWEN_API_KEY','DASHSCOPE_API_KEY','NODE_OPTIONS','HTTPS_PROXY'} & env.keys()
    command=planner._launch_command(config,planner._runtime())
    assert '-NoProfile' in command and str(qwen.LAUNCHER_PATH) in command and str(qwen_local[1]) in command
    assert SECRET not in repr(command) and 'Bypass' not in repr(command)
    assert CreateRequest(provider='qwen',prompt='公式',request_key='qwen-request').provider=='qwen'


def test_qwen_public_plan_selects_vision_only_for_owned_image(qwen_local,monkeypatch,tmp_path):
    captured=[]
    def receive(config,node,payload,*args):
        captured.append((config,payload));return PROPOSAL
    monkeypatch.setattr(planner,'_invoke',receive)
    source=tmp_path/'owned-image.png';Image.new('RGB',(8,8),'green').save(source)
    assert planner.plan('解释公式','qwen')==PROPOSAL
    assert planner.plan('解释图中的公式','qwen',asset_path=source)==PROPOSAL
    assert [item[0].model for item in captured]==['qwen-plus','qwen3-vl-plus']
    assert captured[0][1]['image_data_url'] is None and captured[1][1]['asset_id']=='owned-image'
    assert all(item[1]['max_steps']==3 and item[1]['max_tokens']==8192 and item[1]['deadline_ms']==120000 for item in captured)


def test_qwen_key_is_loaded_at_launch_after_config_resolution(qwen_offline,qwen_local):
    config=planner._load_provider('qwen',{})
    loader=qwen_local[1]
    loader.write_text(loader.read_text(encoding='utf-8').replace(SECRET,'rotated-synthetic-credential'),encoding='utf-8')
    payload={'prompt':'解释输入与输出','duration':12,'previous':None,'image_data_url':None,'asset_id':None,
             'schema':Proposal.model_json_schema(),'max_tokens':8192,'max_steps':3,'deadline_ms':120_000}
    assert planner._invoke(config,planner._runtime(),payload,None,None)==PROPOSAL
    assert all(call['auth']=='Bearer rotated-synthetic-credential' for call in qwen_offline[1])
    assert config.api_key==''


def test_qwen_native_three_step_fragmented_tools_and_wire_contract(qwen_offline,tmp_path):
    assert invoke_qwen(qwen_offline)==PROPOSAL
    calls=qwen_offline[1]
    assert len(calls)==3
    for call in calls:
        body=call['body']
        assert body['model']=='qwen-plus' and body['enable_thinking'] is False
        assert body['max_tokens']==8192 and body['stream_options']=={'include_usage':True}
        assert body.get('tool_choice','auto')=='auto' and body.get('parallel_tool_calls',False) is False
        assert not {'reasoning_effort','tool_stream','max_completion_tokens','store'} & body.keys()
        assert not any('strict' in tool['function'] for tool in body['tools'])
        assert call['auth']=='Bearer '+SECRET and SECRET not in json.dumps(body)
    assert any(message['role']=='tool' and message.get('tool_call_id') for message in calls[1]['body']['messages'])
    raw=''.join(path.read_text(encoding='utf-8') for path in (tmp_path/'home'/'audit').glob('*.jsonl'))
    assert SECRET not in raw and 'synthetic-encrypted-marker' not in raw


def test_qwen_image_model_preserves_exact_incremental_edit(qwen_offline,tmp_path):
    source=io.BytesIO();Image.new('RGB',(16,16),'blue').save(source,format='PNG')
    encoded=base64.b64encode(source.getvalue()).decode()
    proposal=interactive_proposal()
    proposal['scene']['objects'][0]['frames']=[{'t':12*i/179,'rotation':i/100} for i in range(180)]
    previous={'proposal':proposal,'scene':proposal['scene']}
    qwen_offline[2]['edit']={'mode':'patch','proposal_updates':{'title':'修改标题'}}
    result=invoke_qwen(qwen_offline,image_data_url='data:image/png;base64,'+encoded,asset_id='owned-image',previous_exact=previous)
    assert result['title']=='修改标题' and result['scene']['title']=='修改标题' and result['selection']==proposal['selection']
    assert result['scene']['objects']==proposal['scene']['objects'] and result['scene']['interactions']==proposal['scene']['interactions']
    calls=qwen_offline[1]
    assert len(calls)==3 and all(call['body']['model']=='qwen3-vl-plus' for call in calls)
    assert any(item.get('type')=='image_url' and item['image_url']['url'].startswith('data:image/') for item in embedded_objects(calls[0]['body']))
    assert 'previous_exact' not in json.dumps(calls[0]['body'])
    raw=''.join(path.read_text(encoding='utf-8') for path in (tmp_path/'home'/'audit').glob('*.jsonl'))
    assert encoded not in raw and SECRET not in raw


def test_qwen_loader_failure_is_safe_and_never_calls_model(qwen_offline,qwen_local):
    qwen_local[1].write_text("throw 'private loader diagnostic " + SECRET + "'",encoding='utf-8')
    with pytest.raises(planner.PlannerError) as error:invoke_qwen(qwen_offline)
    assert error.value.code=='QWEN_NOT_CONFIGURED' and SECRET not in str(error.value)
    assert qwen_offline[1]==[]


@pytest.mark.parametrize('behavior,code',[({'status':401},'AUTH'),({'loop':True},'REQUEST_LIMIT')])
def test_qwen_errors_are_bounded_and_sanitized(qwen_offline,behavior,code,tmp_path):
    qwen_offline[2].update(behavior)
    with pytest.raises(planner.PlannerError) as error:invoke_qwen(qwen_offline)
    assert error.value.code==code and len(qwen_offline[1])==(1 if code=='AUTH' else 3)
    raw=''.join(path.read_text(encoding='utf-8') for path in (tmp_path/'home'/'audit').glob('*.jsonl'))
    assert SECRET not in raw and 'raw private diagnostic' not in raw and SECRET not in str(error.value)


def test_qwen_cancel_terminates_powershell_and_node(qwen_offline):
    cancelled=threading.Event();qwen_offline[2]['cancel']=cancelled
    with pytest.raises(planner.PlannerError) as error:invoke_qwen(qwen_offline,cancelled=cancelled)
    assert error.value.code=='CANCELLED' and len(qwen_offline[1])==1


def test_qwen_host_deadline_terminates_powershell_and_node(qwen_offline,monkeypatch):
    qwen_offline[2]['stall']=True
    monkeypatch.setattr(planner,'DEADLINE_SECONDS',1.5)
    with pytest.raises(planner.PlannerError) as error:invoke_qwen(qwen_offline)
    assert error.value.code=='TIMEOUT' and len(qwen_offline[1])<=1
