"""Real native DSH lifecycle exercised only against local synthetic SSE endpoints."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import subprocess
import sqlite3
import threading
import time
from unittest.mock import Mock

import pytest
from PIL import Image

from runtime import planner
from server.schema import Proposal

PROCESS_SELECTION={'engine':'canvas2d','category':'process','reason':'对象关系与过程顺序适合清晰的二维节点、连线和时间轴。'}
MECHANISM_SELECTION={'engine':'threejs','category':'mechanism','reason':'机械结构需要实体部件、装配关系和运动方向，采用可旋转观察的三维表达。'}
SELECT_ARGS={'category':'process','goal':'解释输入与输出的关系','subject':'other','dimension_preference':'auto'}
PROPOSAL = {'title':'输入与输出','summary':'观察过程','recipe':'diagram','duration':12,'labels':['输入','输出'],'selection':PROCESS_SELECTION}
SECRET = 'synthetic-offline-secret'


def interactive_proposal():
    return {'title':'耦合齿轮示意','recipe':'custom','duration':12,'selection':MECHANISM_SELECTION,
        'scene':{'title':'耦合齿轮示意','duration':12,'mode':'3d','selection':MECHANISM_SELECTION,
            'objects':[{'id':'left','kind':'group','x':-1}, {'id':'right','kind':'group','x':1},
                {'id':'left-body','kind':'cylinder','radius':.8,'height':.3,'parent_id':'left'},
                {'id':'right-body','kind':'cylinder','radius':.8,'height':.3,'parent_id':'right'}],
            'interactions':[{'id':'angle','label':'驱动角度','value':0,'min':-180,'max':180,'step':1,'unit':'°',
                'description':'拖动左轮，同时观察右轮反向转动；简化运动示意。',
                'bindings':[{'target_id':'left','property':'rotation','multiplier':.01745329252},
                    {'target_id':'right','property':'rotation','multiplier':-.01745329252}],
                'drag':{'target_id':'left','axis':'horizontal','sensitivity':1}}]}}


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    env = {key:value for key,value in planner.os.environ.items() if not key.startswith(('VISUALIZATION_','CC_SWITCH_'))}
    monkeypatch.setattr(planner, '_settings', lambda: env.copy())
    original=planner._child_environment
    def child(config, task_id):
        result=original(config,task_id)
        result['DSH_HOME']=str(tmp_path / 'home')
        return result
    monkeypatch.setattr(planner,'_child_environment',child)


def test_active_selection_rotation_endpoint_pairing_and_safe_capabilities(tmp_path,monkeypatch):
    database=tmp_path/'cc-switch.db'
    settings=tmp_path/'settings.json'
    settings.write_text(json.dumps({'currentProviderCodex':'chosen'}))
    def config(model,url):
        return f'model_provider="gateway"\nmodel="{model}"\n[model_providers.gateway]\nbase_url="{url}"\nwire_api="responses"'
    stored={'auth':{'OPENAI_API_KEY':'private-first'},'config':config('stored-model','https://private.example/v1')}
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE providers(id TEXT,app_type TEXT,settings_config TEXT,is_current INTEGER)')
        db.execute('INSERT INTO providers VALUES (?,?,?,?)',('chosen','codex',json.dumps(stored),0))
        db.execute('INSERT INTO providers VALUES (?,?,?,?)',('other','codex',json.dumps(stored),1))
    live=tmp_path/'config.toml'
    live.write_text(config('live-model','https://private.example/v1'))
    env={'CC_SWITCH_DB_PATH':str(database),'CC_SWITCH_SETTINGS_PATH':str(settings),'CC_SWITCH_CODEX_CONFIG':str(live),
         'CC_SWITCH_CLAUDE_SETTINGS':str(tmp_path/'missing.json')}
    monkeypatch.setattr(planner,'_settings',lambda:env)
    assert planner._load_provider('chatgpt').model=='live-model'
    stored['auth']['OPENAI_API_KEY']='private-rotated'
    with sqlite3.connect(database) as db:
        db.execute('UPDATE providers SET settings_config=? WHERE id=?',(json.dumps(stored),'chosen'))
    assert planner._load_provider('chatgpt').api_key=='private-rotated'
    live.write_text(config('stale-model','https://different.example/v1'))
    assert planner._load_provider('chatgpt').model=='stored-model'
    public=json.dumps(planner.capabilities())
    assert 'private' not in public and 'model' not in public
    assert 'private-rotated' not in repr(planner._load_provider('chatgpt'))


def test_partial_override_and_blank_auth_token_fail_closed(tmp_path):
    with pytest.raises(planner.PlannerError) as error:
        planner._load_provider('chatgpt',{'VISUALIZATION_CHATGPT_MODEL':'test'})
    assert error.value.code=='NOT_CONFIGURED'
    path=tmp_path/'claude.json'
    path.write_text(json.dumps({'env':{'ANTHROPIC_BASE_URL':'https://example.test','ANTHROPIC_MODEL':'claude-test',
        'ANTHROPIC_AUTH_TOKEN':'','ANTHROPIC_API_KEY':'must-not-fallback'}}))
    with pytest.raises(planner.PlannerError):
        planner._load_provider('claude',{'CC_SWITCH_CLAUDE_SETTINGS':str(path)})


def test_child_environment_strips_inherited_auth_and_node_hooks(monkeypatch):
    for key in ['OPENAI_API_KEY','ANTHROPIC_AUTH_TOKEN','NODE_OPTIONS','DSH_TOOLS_MODE']:
        monkeypatch.setenv(key,'untrusted-inherited')
    config=planner.ProviderConfig('test','https://example.test','openai-responses',SECRET)
    env=planner._child_environment(config,'visual-'+'a'*32)
    assert env['DSH_VISUALIZATION_API_KEY']==SECRET
    assert not {'OPENAI_API_KEY','ANTHROPIC_AUTH_TOKEN','NODE_OPTIONS','DSH_TOOLS_MODE'} & env.keys()


def test_cancelled_before_configuration(monkeypatch):
    event=threading.Event();event.set()
    load=Mock();monkeypatch.setattr(planner,'_load_provider',load)
    with pytest.raises(planner.PlannerError) as error:
        planner.plan('解释过程','chatgpt',cancelled=event)
    assert error.value.code=='CANCELLED'
    load.assert_not_called()


def test_public_plan_passes_complete_schema_previous_and_owned_asset(tmp_path,monkeypatch):
    source=tmp_path/'asset-123.png'
    Image.new('RGB',(8,8),'green').save(source)
    captured=Mock(return_value=PROPOSAL)
    monkeypatch.setattr(planner,'_load_provider',lambda *args:planner.ProviderConfig('test','https://example.test','openai-responses',SECRET))
    monkeypatch.setattr(planner,'_runtime',lambda *args:'node')
    monkeypatch.setattr(planner,'_invoke',captured)
    previous={'title':'earlier','recipe':'diagram'}
    assert planner.plan('修改标注','chatgpt',asset_path=source,previous=previous)==PROPOSAL
    payload=captured.call_args.args[2]
    assert payload['asset_id']=='asset-123' and payload['previous']==previous
    assert set(payload['schema']['$defs'])>={'ModelScene','ModelVisualObject','Frame','Control'}
    assert payload['max_steps']==3 and payload['deadline_ms']==120000
    assert str(source) not in json.dumps(payload)


def test_previous_physics_samples_are_summarized_without_mutation():
    frames=[{'t':i/25,'x':i/100,'y':i/200,'z':None,'rotation':None,'opacity':None} for i in range(901)]
    original={'proposal':{'recipe':'wave','parameters':{'frequency':.6}},
        'scene':{'title':'波','duration':36,'controls':[{'id':'frequency','value':.6}],
            'objects':[{'id':f'particle-{i}','kind':'circle','x':i,'frames':frames,'points':[]} for i in range(55)]}}
    assert len(json.dumps(original).encode())>500_000
    summary=planner._previous_context(original)
    assert len(json.dumps(summary).encode())<100_000
    assert summary['proposal']==original['proposal']
    assert summary['scene']['controls']==original['scene']['controls']
    assert len(summary['scene']['objects'])==55
    assert len(summary['scene']['objects'][0]['frames'])==6
    assert summary['scene']['objects'][0]['frames'][-1]['t']==36
    assert summary['scene']['objects'][0]['_summary']['frames_original_count']==901
    assert '_context_summary' in summary['scene']
    assert len(original['scene']['objects'][0]['frames'])==901
    assert 'z' not in summary['scene']['objects'][0]['frames'][0]


def test_previous_interactions_preserve_coupling_and_current_neutral_state():
    original=interactive_proposal()
    original['scene']['interactions'][0]['value']=35
    original['scene']['objects'][0]['frames']=[{'t':i/25,'rotation':i/100} for i in range(301)]
    summary=planner._previous_context(original)
    assert summary['scene']['interactions']==original['scene']['interactions']
    assert len(summary['scene']['objects'][0]['frames'])==6
    assert len(original['scene']['objects'][0]['frames'])==301
    assert 'interaction bindings are retained' in summary['scene']['_context_summary']


def test_previous_sparse_frames_retain_inherited_values_in_sampled_context():
    frames=[{'t':i} for i in range(12)];frames[1]['x']=3
    original={'title':'sparse','objects':[{'id':'a','kind':'circle','x':0,'frames':frames}]}
    reduced=planner._previous_context(original)['objects'][0]['frames']
    assert reduced[1]=={'t':2,'x':3} and reduced[-1]=={'t':11,'x':3}
    assert original['objects'][0]['frames'][2]=={'t':2}


def embedded_objects(value):
    if isinstance(value,dict):
        yield value
        for item in value.values():yield from embedded_objects(item)
    elif isinstance(value,list):
        for item in value:yield from embedded_objects(item)
    elif isinstance(value,str):
        try:decoded=json.loads(value)
        except (ValueError,TypeError):return
        if isinstance(decoded,(dict,list)):yield from embedded_objects(decoded)


def response_events(answer, call_name=None, arguments=None, n=1):
    if call_name:
        item={'id':f'fc-{n}','type':'function_call','call_id':f'call-{n}','name':call_name,'arguments':json.dumps(arguments),'status':'completed'}
        delta=[{'type':'response.function_call_arguments.delta','item_id':item['id'],'output_index':0,'delta':item['arguments']},
               {'type':'response.function_call_arguments.done','item_id':item['id'],'output_index':0,'arguments':item['arguments']}]
        added={**item,'arguments':'','status':'in_progress'}
    else:
        item={'id':f'msg-{n}','type':'message','role':'assistant','content':[{'type':'output_text','text':answer,'annotations':[]}],'status':'completed'}
        delta=[{'type':'response.content_part.added','item_id':item['id'],'output_index':0,'content_index':0,'part':{'type':'output_text','text':'','annotations':[]}},
               {'type':'response.output_text.delta','item_id':item['id'],'output_index':0,'content_index':0,'delta':answer},
               {'type':'response.output_text.done','item_id':item['id'],'output_index':0,'content_index':0,'text':answer}]
        added={**item,'content':[],'status':'in_progress'}
    response={'id':f'resp-{n}','object':'response','model':'test-model','status':'completed','output':[item],
              'usage':{'input_tokens':20,'output_tokens':40,'total_tokens':60}}
    return [{'type':'response.created','response':{**response,'status':'in_progress','output':[]}},
            {'type':'response.output_item.added','output_index':0,'item':added},*delta,
            {'type':'response.output_item.done','output_index':0,'item':item},
            {'type':'response.completed','response':response}]


def anthropic_events(answer,call_name=None,arguments=None,n=1):
    block={'type':'tool_use','id':f'call-{n}','name':call_name,'input':{}} if call_name else {'type':'text','text':''}
    delta={'type':'input_json_delta','partial_json':json.dumps(arguments)} if call_name else {'type':'text_delta','text':answer}
    return [
        {'type':'message_start','message':{'id':f'msg-{n}','type':'message','role':'assistant','model':'test-model','content':[],
            'stop_reason':None,'usage':{'input_tokens':20,'output_tokens':0}}},
        {'type':'content_block_start','index':0,'content_block':block},
        {'type':'content_block_delta','index':0,'delta':delta},
        {'type':'content_block_stop','index':0},
        {'type':'message_delta','delta':{'stop_reason':'tool_use' if call_name else 'end_turn','stop_sequence':None},'usage':{'output_tokens':40}},
        {'type':'message_stop'},
    ]


@pytest.fixture
def endpoint():
    calls=[]
    behavior={'status':200,'loop':False}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append({'path':self.path,'body':body,'auth':self.headers.get('Authorization')})
            if len(calls)==3 and behavior.get('cancel_final') is not None:
                behavior['cancel_final'].set();time.sleep(2);self.close_connection=True;return
            if len(calls)==3 and behavior.get('stall_final'):
                time.sleep(3);self.close_connection=True;return
            if behavior.get('cancel') is not None:
                behavior['cancel'].set()
            if behavior.get('stall') or behavior.get('cancel') is not None:
                time.sleep(2);self.close_connection=True;return
            self.send_response(behavior['status'])
            self.send_header('Content-Type','text/event-stream' if behavior['status']==200 else 'application/json')
            self.end_headers()
            if behavior['status']!=200:
                self.wfile.write(json.dumps({'error':{'message':'raw private diagnostic '+SECRET,'type':'authentication_error'}}).encode());return
            n=len(calls)
            call_name='select_visual_tool' if n==1 else 'check_proposal' if n==2 or behavior['loop'] else None
            arguments=behavior.get('select_args',SELECT_ARGS) if n==1 else {'proposal':behavior.get('check_proposal',behavior.get('proposal',PROPOSAL))}
            if n==2 and behavior.get('edit') is not None:
                base=next(item['edit_base_id'] for item in embedded_objects(body) if 'edit_base_id' in item)
                arguments={'proposal':{'edit':{'base_id':base,**behavior['edit']}}}
            if behavior.get('skip_tools'):
                call_name=None
            if behavior.get('unknown'):
                call_name='bash';arguments={'command':'whoami'}
            if behavior.get('invalid_check') and n==2:
                arguments={'proposal':{**PROPOSAL,'duration':90}}
            answer=json.dumps(behavior.get('proposal',PROPOSAL),ensure_ascii=False)
            if n==3 and behavior.get('confirmation'):
                results=[item for item in embedded_objects(body) if item.get('valid') is True and 'proposal_id' in item]
                final_response=results[-1]['final_response'] if results else {'accept_proposal':'missing-check'}
                if behavior.get('bad_confirmation'):final_response={'accept_proposal':'sha256:'+'0'*64}
                if behavior.get('mixed_confirmation'):final_response={**final_response,'title':'injected mutation'}
                answer=json.dumps(final_response)
            if self.path.endswith('chat/completions'):
                delta={'content':answer} if not call_name else {'tool_calls':[{'index':0,'id':f'call-{n}','type':'function','function':{'name':call_name,'arguments':json.dumps(arguments)}}]}
                events=[{'id':f'chat-{n}','object':'chat.completion.chunk','model':'test-model','choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                    {'id':f'chat-{n}','object':'chat.completion.chunk','model':'test-model','choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if call_name else 'stop'}],
                     'usage':{'prompt_tokens':20,'completion_tokens':40,'total_tokens':60}}]
                if behavior.get('qwen_stream'):
                    if call_name:
                        arguments_json=json.dumps(arguments);split=len(arguments_json)//2
                        first=events[0]['choices'][0]['delta']['tool_calls'][0]
                        first['function']['arguments']=arguments_json[:split]
                        fragment={'index':0,'id':'','type':'function','function':{'name':None,'arguments':arguments_json[split:]}}
                        events.insert(1,{'id':f'chat-{n}','object':'chat.completion.chunk','model':'test-model',
                            'choices':[{'index':0,'delta':{'tool_calls':[fragment]},'finish_reason':None}]})
                    usage=events[-1].pop('usage')
                    events.append({'id':f'chat-{n}','object':'chat.completion.chunk','model':'test-model','choices':[],'usage':usage})
            elif self.path.split('?',1)[0].endswith('messages'):
                events=anthropic_events(answer,call_name,arguments,n)
            else:
                events=response_events(answer,call_name,arguments,n)
            for event in events:
                prefix=f"event: {event['type']}\n" if 'type' in event else ''
                try:
                    self.wfile.write((prefix+'data: '+json.dumps(event,ensure_ascii=False)+'\n\n').encode());self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError): break
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}',calls,behavior
    finally: server.shutdown();server.server_close();thread.join(timeout=2)


def invoke(endpoint,api='openai-responses',cancelled=None,on_event=None,**overrides):
    origin,_,_=endpoint
    config=planner.ProviderConfig('test-model',origin if api=='anthropic-messages' else origin+'/v1',api,SECRET,api=='anthropic-messages')
    payload={'prompt':'解释输入与输出','duration':12,'previous':None,'image_data_url':None,'asset_id':None,
             'schema':Proposal.model_json_schema(),'max_tokens':1000,'max_steps':3,'deadline_ms':120_000,**overrides}
    if payload.get('previous_exact') is not None and 'previous' not in overrides:payload['previous']=planner._previous_context(payload['previous_exact'])
    return planner._invoke(config,planner._runtime(),payload,cancelled,on_event)


@pytest.mark.parametrize('api',['openai-responses','anthropic-messages','openai-completions'])
def test_real_native_agent_tool_loop_and_audit(endpoint,api,tmp_path):
    events=[]
    assert invoke(endpoint,api,on_event=events.append)==PROPOSAL
    _,calls,_=endpoint
    assert len(calls)==3
    for call in calls:
        names={tool.get('name',tool.get('function',{}).get('name')) for tool in call['body']['tools']}
        assert names=={'select_visual_tool','check_proposal'}
        assert SECRET not in json.dumps(call['body'])
        assert call['auth']=='Bearer '+SECRET
    assert 'select_visual_tool' in json.dumps(calls[1]['body'])
    assert 'candidate_recipes' in json.dumps(calls[1]['body'])
    assert 'valid' in json.dumps(calls[2]['body'])
    assert any(e['stage']=='checking' for e in events)
    logs=list((tmp_path/'home'/'audit').glob('*.jsonl'))
    assert len(logs)==1
    raw=logs[0].read_text(encoding='utf-8')
    assert SECRET not in raw
    audit=[json.loads(line) for line in raw.splitlines()]
    types=[e.get('type') for e in audit]
    assert 'tool/result' in types and 'turn/end' in types and 'assistant/message' in types
    assert audit[-1]['requests']==3 and audit[-1]['toolCalls']==2
    selection_event=next(e for e in audit if e.get('kind')=='visual-tool-selection')
    assert selection_event['selection']==PROCESS_SELECTION


def test_native_custom_interactions_keep_three_step_tool_flow(endpoint):
    proposal=interactive_proposal()
    Proposal.model_validate(proposal)
    endpoint[2].update(select_args={'category':'mechanism','goal':'理解两轮反向耦合运动','subject':'other','dimension_preference':'auto'},proposal=proposal)
    assert invoke(endpoint,prompt='展示两个齿轮，允许我拖动观察转动关系')==proposal
    assert len(endpoint[1])==3
    assert 'interaction_modeling' in json.dumps(endpoint[1][1]['body'])
    assert '\\"valid\\":true' in json.dumps(endpoint[1][2]['body'])


def test_native_custom_patch_retains_exact_180_frames_geometry_and_interactions(endpoint):
    proposal=interactive_proposal();scene=proposal['scene']
    scene['objects'][0]['frames']=[{'t':12*i/179,'rotation':i/100} for i in range(180)]
    scene['objects'].append({'id':'unchanged-path','kind':'path','points':[[i/10,i%3] for i in range(60)]})
    scene['steps']=[{'title':'观察','start':0,'end':12,'focus':['left','right']}]
    previous={'proposal':proposal,'scene':scene,'exploration':{'values':{'angle':35},'camera':None}}
    endpoint[2].update(edit={'mode':'patch','object_updates':[{'id':'left-body','set':{'color':'#ff0000'}}]},confirmation=True)
    result=invoke(endpoint,previous_exact=previous,prompt='只把左轮改成红色')
    assert len(endpoint[1])==3 and result['selection']==MECHANISM_SELECTION
    actual={o['id']:o for o in result['scene']['objects']}
    assert actual['left']['frames']==scene['objects'][0]['frames']
    assert actual['unchanged-path']['points']==scene['objects'][-1]['points']
    assert actual['left-body']['color']=='#ff0000'
    assert result['scene']['interactions']==scene['interactions'] and result['scene']['steps']==scene['steps']
    assert actual['left'].get('rotation',0)==0,'saved exploration was not baked twice'
    contexts=[o for o in embedded_objects(endpoint[1][0]['body']) if 'previous' in o]
    assert len(contexts[0]['previous']['scene']['objects'][0]['frames'])==6
    assert 'previous_exact' not in json.dumps(endpoint[1][0]['body'])
    Proposal.model_validate(result)


def test_native_trusted_partial_parameter_patch_preserves_other_parameters(endpoint):
    proposal={'title':'单摆','recipe':'pendulum','duration':12,'parameters':{'length':1.7,'angle':32,'damping':.07},
        'selection':{'engine':'canvas2d','category':'numerical','reason':'可信单摆计算'}}
    previous={'proposal':proposal,'scene':{'mode':'2d','selection':proposal['selection']}}
    endpoint[2].update(edit={'mode':'patch','parameters':{'angle':45}},confirmation=True)
    result=invoke(endpoint,previous_exact=previous,prompt='把初始角度调到45度')
    assert result['parameters']=={'length':1.7,'angle':45,'damping':.07}
    assert result['recipe']=='pendulum' and result['selection']==proposal['selection']
    assert len(endpoint[1])==3


def test_native_edit_can_ask_for_clarification_without_rebuilding(endpoint):
    proposal=interactive_proposal()
    clarification={'title':'需要补充','recipe':'custom','duration':12,'needs_clarification':True,
        'question':'请说明希望修改哪个构件。','selection':MECHANISM_SELECTION}
    endpoint[2].update(proposal=clarification,confirmation=True)
    assert invoke(endpoint,previous_exact={'proposal':proposal,'scene':proposal['scene']})==clarification


def test_native_full_replacement_of_existing_project_requires_explicit_rebuild(endpoint):
    proposal=interactive_proposal()
    endpoint[2].update(proposal=proposal)
    with pytest.raises(planner.PlannerError) as error:
        invoke(endpoint,previous_exact={'proposal':proposal,'scene':proposal['scene']})
    assert error.value.code=='INVALID_OUTPUT' and len(endpoint[1])==3


def test_exact_edit_input_is_bounded_before_spawning_runtime(monkeypatch):
    spawn=Mock();monkeypatch.setattr(planner.subprocess,'Popen',spawn)
    with pytest.raises(planner.PlannerError) as error:
        planner._invoke(None,'node',{'previous_exact':'x'*8_000_000},None,None)
    assert error.value.code=='INVALID_INPUT';spawn.assert_not_called()


@pytest.mark.parametrize('api',['openai-responses','anthropic-messages','openai-completions'])
def test_native_short_confirmation_adopts_checked_interactive_scene(endpoint,api,tmp_path):
    proposal=interactive_proposal()
    endpoint[2].update(select_args={'category':'mechanism','goal':'探索耦合转动','subject':'other','dimension_preference':'auto'},
        proposal=proposal,confirmation=True)
    assert invoke(endpoint,api)==proposal
    assert len(endpoint[1])==3
    audit=[json.loads(line) for path in (tmp_path/'home'/'audit').glob('*.jsonl') for line in path.read_text(encoding='utf-8').splitlines()]
    checked=next(e for e in audit if e.get('kind')=='proposal-checked')
    final=next(e for e in audit if e.get('kind')=='proposal-finalization')
    assert final['source']=='checked-reference' and final['proposalId']==checked['proposalId']
    assert final['finalBytes']<128 and checked['bytes']>1000
    assert audit[-1]['ok'] is True and audit[-1]['requests']==3 and audit[-1]['toolCalls']==2


@pytest.mark.parametrize('option',['bad_confirmation','mixed_confirmation'])
def test_native_unknown_or_mixed_confirmation_cannot_adopt_candidate(endpoint,option):
    endpoint[2].update(confirmation=True,**{option:True})
    with pytest.raises(planner.PlannerError) as error:invoke(endpoint)
    assert error.value.code=='INVALID_OUTPUT' and len(endpoint[1])==3


def test_native_confirmation_after_failed_check_cannot_recover_cached_data(endpoint):
    endpoint[2].update(confirmation=True,invalid_check=True)
    with pytest.raises(planner.PlannerError) as error:invoke(endpoint)
    assert error.value.code=='INVALID_OUTPUT' and len(endpoint[1])==3


def test_native_cancel_after_valid_check_never_returns_unconfirmed_candidate(endpoint,tmp_path):
    cancelled=threading.Event();endpoint[2]['cancel_final']=cancelled
    with pytest.raises(planner.PlannerError) as error:invoke(endpoint,cancelled=cancelled)
    assert error.value.code=='CANCELLED' and len(endpoint[1])==3
    audit=[json.loads(line) for path in (tmp_path/'home'/'audit').glob('*.jsonl') for line in path.read_text(encoding='utf-8').splitlines()]
    assert any(e.get('kind')=='proposal-checked' for e in audit)
    assert not any(e.get('kind')=='audit-outcome' and e.get('ok') for e in audit)


def test_native_timeout_after_valid_check_never_returns_unconfirmed_candidate(endpoint,tmp_path):
    endpoint[2]['stall_final']=True
    with pytest.raises(planner.PlannerError) as error:invoke(endpoint,deadline_ms=2500)
    assert error.value.code=='TIMEOUT' and len(endpoint[1])==3
    audit=[json.loads(line) for path in (tmp_path/'home'/'audit').glob('*.jsonl') for line in path.read_text(encoding='utf-8').splitlines()]
    assert any(e.get('kind')=='proposal-checked' for e in audit)
    assert not any(e.get('kind')=='audit-outcome' and e.get('ok') for e in audit)


def test_native_interaction_extra_code_is_rejected_then_repaired_without_extra_step(endpoint):
    proposal=interactive_proposal()
    invalid=json.loads(json.dumps(proposal))
    invalid['scene']['interactions'][0]['bindings'][0]['expression']='globalThis.run()'
    endpoint[2].update(select_args={'category':'mechanism','goal':'观察耦合转动','subject':'other','dimension_preference':'auto'},
        proposal=proposal,check_proposal=invalid)
    assert invoke(endpoint)==proposal
    assert len(endpoint[1])==3
    final_context=json.dumps(endpoint[1][2]['body'])
    assert 'false' in final_context and 'additionalProperties' in final_context


def test_interaction_semantics_match_authoritative_python_schema():
    cases=[interactive_proposal()]
    def changed(edit):
        value=interactive_proposal();edit(value,value['scene']['interactions'][0]);cases.append(value)
    changed(lambda p,c:c['bindings'][0].update(target_id='missing'))
    changed(lambda p,c:c['bindings'][0].update(property='latex'))
    changed(lambda p,c:c['bindings'][0].update(multiplier=0))
    changed(lambda p,c:c['bindings'][0].update(multiplier=101))
    changed(lambda p,c:c.update(min=c['max']))
    changed(lambda p,c:c.update(step=999))
    changed(lambda p,c:c['bindings'].append(dict(c['bindings'][0])))
    changed(lambda p,c:c['drag'].update(target_id='left-body'))
    changed(lambda p,c:p['scene']['interactions'].append({**c,'id':'other'}))
    changed(lambda p,c:p['scene']['objects'][2].update(parent_id=None))
    changed(lambda p,c:c.update(kind='toggle',min=0,max=1,value=0,step=1))
    changed(lambda p,c:c['bindings'][0].update(expression='execute()'))
    changed(lambda p,c:p['scene'].update(evidence='computed'))
    def clipped(p,c):
        p['scene']['objects'][0]['scale']=20
        c.update(min=0,max=1,value=0,step=.1)
        c['bindings'][0].update(property='scale',multiplier=1)
    changed(clipped)
    def animated_range(p,c):
        clipped(p,c);p['scene']['objects'][0]['frames']=[{'t':0,'scale':20},{'t':6,'scale':19},{'t':12,'rotation':1}]
    changed(animated_range)
    expected=[]
    for value in cases:
        try:Proposal.model_validate(value);expected.append(True)
        except ValueError:expected.append(False)
    script="""import {createProposalValidator} from './runtime/contracts.mjs';
      let input='';for await(const chunk of process.stdin)input+=chunk;
      const {schema,cases}=JSON.parse(input),validate=createProposalValidator(schema);
      process.stdout.write(JSON.stringify(cases.map(value=>validate(value).valid)));"""
    result=subprocess.run([planner._runtime(),'--input-type=module','-e',script],cwd=planner.ROOT,
        input=json.dumps({'schema':Proposal.model_json_schema(),'cases':cases}),text=True,capture_output=True,check=True)
    assert json.loads(result.stdout)==expected
    assert expected==[True]+[False]*14+[True]


@pytest.mark.parametrize('api',['openai-responses','anthropic-messages'])
@pytest.mark.parametrize('status,code',[(401,'AUTH'),(429,'RATE_LIMIT'),(500,'SERVER_ERROR')])
def test_no_network_retry_and_private_error_redaction(endpoint,api,status,code,tmp_path):
    endpoint[2]['status']=status
    with pytest.raises(planner.PlannerError) as error: invoke(endpoint,api)
    assert error.value.code==code
    assert len(endpoint[1])==1
    raw=''.join(p.read_text(encoding='utf-8') for p in (tmp_path/'home'/'audit').glob('*.jsonl'))
    assert SECRET not in raw and 'raw private diagnostic' not in raw
    assert SECRET not in str(error.value)


def test_schema_failure_tool_result_can_be_repaired(endpoint):
    endpoint[2]['invalid_check']=True
    assert invoke(endpoint)==PROPOSAL
    third=json.dumps(endpoint[1][2]['body'])
    assert 'false' in third and 'maximum' in third


def test_three_request_hard_limit(endpoint):
    endpoint[2]['loop']=True
    with pytest.raises(planner.PlannerError) as error: invoke(endpoint)
    assert error.value.code=='REQUEST_LIMIT'
    assert len(endpoint[1])==3


def test_unregistered_tool_cannot_execute(endpoint):
    endpoint[2]['unknown']=True
    with pytest.raises(planner.PlannerError) as error: invoke(endpoint)
    assert error.value.code in {'TOOL_LIMIT','REQUEST_LIMIT'}
    assert len(endpoint[1])<=3


def test_active_cancel_and_deadline_kill_runner(endpoint,monkeypatch):
    event=threading.Event();endpoint[2]['cancel']=event
    start=time.monotonic()
    with pytest.raises(planner.PlannerError) as error: invoke(endpoint,cancelled=event)
    assert error.value.code=='CANCELLED' and time.monotonic()-start<8
    assert len(endpoint[1])==1


def test_deadline_cannot_hang(endpoint,monkeypatch):
    endpoint[2]['stall']=True
    monkeypatch.setattr(planner,'DEADLINE_SECONDS',1.5)
    start=time.monotonic()
    with pytest.raises(planner.PlannerError) as error: invoke(endpoint)
    assert error.value.code=='TIMEOUT' and time.monotonic()-start<8
    assert len(endpoint[1])<=1


def test_image_and_previous_context_without_base64_audit(endpoint,tmp_path):
    data=io.BytesIO();Image.new('RGB',(32,32),'blue').save(data,format='PNG')
    encoded=base64.b64encode(data.getvalue()).decode()
    assert invoke(endpoint,image_data_url='data:image/png;base64,'+encoded,asset_id='asset-one',previous=PROPOSAL)==PROPOSAL
    body=json.dumps(endpoint[1][0]['body'])
    assert 'input_image' in body and 'previous' in body and 'asset-one' in body
    raw=''.join(p.read_text(encoding='utf-8') for p in (tmp_path/'home'/'audit').glob('*.jsonl'))
    assert encoded not in raw


@pytest.mark.parametrize('api',['openai-responses','anthropic-messages'])
def test_axial_fan_tool_route_produces_only_matching_trusted_3d_recipe(endpoint,api):
    proposal={'title':'轴流风机','summary':'叶片转动推动轴向气流','recipe':'fan','duration':12,
              'parameters':{'speed':.5,'pitch':25,'explode':1},'selection':MECHANISM_SELECTION}
    endpoint[2].update(select_args={'category':'mechanism','goal':'理解叶片与机壳装配和轴向运动','subject':'axial_fan','dimension_preference':'auto'},proposal=proposal)
    assert invoke(endpoint,api,prompt='展示轴流风机结构与转动')==proposal
    third=json.dumps(endpoint[1][2]['body'])
    assert 'true' in third and len(endpoint[1])==3


def test_threejs_selection_cannot_finish_with_two_dimensional_diagram(endpoint):
    endpoint[2].update(select_args={'category':'mechanism','goal':'解释机械装配与运动','subject':'axial_fan','dimension_preference':'auto'},
                       proposal={**PROPOSAL,'selection':MECHANISM_SELECTION})
    with pytest.raises(planner.PlannerError) as error:invoke(endpoint)
    assert error.value.code=='INVALID_OUTPUT'
    assert len(endpoint[1])==3
    assert 'requires scene.mode=3d' in json.dumps(endpoint[1][2]['body'])


def test_unrelated_mechanism_cannot_use_axial_fan_recipe(endpoint):
    endpoint[2].update(select_args={'category':'mechanism','goal':'解释齿轮箱啮合','subject':'other','dimension_preference':'auto'},
                       proposal={'title':'错误风机','recipe':'fan','duration':12,'selection':MECHANISM_SELECTION})
    with pytest.raises(planner.PlannerError) as error:invoke(endpoint,prompt='展示齿轮箱的啮合')
    assert error.value.code=='INVALID_OUTPUT' and len(endpoint[1])==3


def test_explicit_flat_preference_overrides_mechanical_default(endpoint):
    selection={'engine':'canvas2d','category':'mechanism','reason':'遵照用户明确的平面要求，采用二维表达。'}
    proposal={**PROPOSAL,'selection':selection}
    endpoint[2].update(select_args={'category':'mechanism','goal':'解释风机部件','subject':'axial_fan','dimension_preference':'2d','preference_quote':'只用二维示意图'},proposal=proposal)
    assert invoke(endpoint,prompt='解释轴流风机，只用二维示意图')==proposal


def test_final_output_cannot_bypass_required_tool_selection(endpoint):
    endpoint[2]['skip_tools']=True
    with pytest.raises(planner.PlannerError) as error:invoke(endpoint)
    assert error.value.code=='INVALID_OUTPUT' and len(endpoint[1])==1
