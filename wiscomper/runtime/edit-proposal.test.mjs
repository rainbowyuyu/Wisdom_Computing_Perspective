import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {createEditResolver} from './edit-proposal.mjs';
import {createProposalValidator,selectVisualTool} from './contracts.mjs';

// Read the current authoritative schema, so edit validation cannot silently
// drift behind Python fields/bounds as new supported primitives are added.
const root=fileURLToPath(new URL('../',import.meta.url));
const python=join(root,process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
const schema=JSON.parse(execFileSync(python,['-c','import json;from server.schema import Proposal;print(json.dumps(Proposal.model_json_schema()))'],{cwd:root,encoding:'utf8'}));
const selection={engine:'canvas2d',category:'process',reason:'观察对象关系'};
const base=()=>({proposal:{title:'原场景',recipe:'custom',duration:12,selection},scene:{title:'原场景',duration:12,mode:'2d',selection,
  objects:[{id:'a',kind:'circle',x:0,frames:[{t:0,x:0},{t:12,x:3}]},{id:'b',kind:'circle',x:2}],
  steps:[{title:'观察',start:0,end:12,focus:['a']}],interactions:[{id:'move',label:'位置',value:0,min:-1,max:1,step:.1,bindings:[{target_id:'a',property:'x',multiplier:1}]}]}});
function setup(duration=12){
  const original=base(),resolver=createEditResolver(schema,original,duration);
  const patch=changes=>({edit:{mode:'patch',base_id:resolver.baseId,...changes}});
  return {original,resolver,patch};
}

test('edit merger retains untouched fields and time-scales retained tracks once',()=>{
  const {original,resolver,patch}=setup(20);
  const changed=resolver.resolve(patch({object_updates:[{id:'b',set:{color:'#ff0000'}}]}));
  assert.equal(changed.duration,20);assert.equal(changed.scene.duration,20);
  assert.deepEqual(changed.scene.objects[0].frames,[{t:0,x:0},{t:20,x:3}]);
  assert.equal(changed.scene.steps[0].end,20);
  assert.deepEqual(changed.scene.interactions,original.scene.interactions);
  assert.equal(original.scene.objects[0].frames.at(-1).t,12);
  assert.equal(createProposalValidator(schema,null,20)(changed).valid,true);
  const explicit=resolver.resolve(patch({object_updates:[{id:'a',set:{frames:[{t:0,x:0},{t:10,x:8},{t:20,x:9}]}}]}));
  assert.equal(explicit.scene.objects[0].frames[1].t,10,'replacement tracks already use the requested duration');
});

test('stable-ID edit operations reject unknown, duplicate, conflicting and executable fields',()=>{
  const {resolver,patch}=setup();
  for(const changes of [
    {object_updates:[{id:'missing',set:{x:1}}]},
    {object_updates:[{id:'a',set:{x:1}},{id:'a',set:{x:2}}]},
    {object_updates:[{id:'a',set:{kind:'text'}}]},
    {object_updates:[{id:'a',set:{script:'execute()'}}]},
    {object_updates:[{id:'a',set:{x:1}}],object_removals:['a']},
    {object_additions:[{id:'a',kind:'circle'}]},
    {object_additions:[{id:'c',kind:'circle'},{id:'c',kind:'circle'}]},
    {object_removals:['missing']},
    {object_removals:['a','a']},
    {scene_updates:{mode:'3d'}},
  ])assert.throws(()=>resolver.resolve(patch(changes)));
  assert.throws(()=>resolver.resolve({edit:{mode:'patch',base_id:'stale'}}));
});

test('custom title, summary and assumptions edits reach displayed scene metadata',()=>{
  const {resolver,patch}=setup();
  const result=resolver.resolve(patch({proposal_updates:{title:'新标题',summary:'新摘要',assumptions:['简化示意']}}));
  for(const key of ['title','summary','assumptions'])assert.deepEqual(result.scene[key],result[key]);
  const override=resolver.resolve(patch({proposal_updates:{title:'项目标题'},scene_updates:{title:'画布标题'}}));
  assert.equal(override.title,'项目标题');assert.equal(override.scene.title,'画布标题');
});

test('deletions are explicit and final validation catches dangling focus or bindings',()=>{
  const {resolver,patch}=setup();
  const dangling=resolver.resolve(patch({object_removals:['a']}));
  assert.equal(createProposalValidator(schema)(dangling).valid,false);
  const cleaned=resolver.resolve(patch({object_removals:['a'],steps:[],interactions:[],object_additions:[{id:'c',kind:'rect'}]}));
  assert.deepEqual(cleaned.scene.objects.map(o=>o.id),['b','c']);
  assert.equal(createProposalValidator(schema)(cleaned).valid,true);
});

test('existing scene requires an explicit rebuild while clarification stays available',()=>{
  const {resolver,original}=setup();
  const full={...original.proposal,scene:original.scene};
  assert.throws(()=>resolver.resolve(full));
  assert.deepEqual(resolver.resolve({edit:{mode:'rebuild',base_id:resolver.baseId,reason:'按新要求重新组织内容',proposal:full}}),full);
  const question={...full,needs_clarification:true,question:'需要改变哪个对象？'};
  assert.deepEqual(resolver.resolve(question),question);
});

test('ordinary edits inherit route, explicit reconstruction and dimension requests can change it',()=>{
  const previous=base(),args={category:'mechanism',goal:'新增构件关系',subject:'other',dimension_preference:'auto'};
  assert.deepEqual(selectVisualTool(args,{previous}).selection,selection);
  assert.equal(selectVisualTool({...args,edit_strategy:'rebuild'},{previous}).selection.engine,'threejs');
  assert.equal(selectVisualTool({...args,dimension_preference:'3d',preference_quote:'改成三维'},{previous,prompt:'改成三维'}).selection.engine,'threejs');
  const {resolver,patch}=setup();
  assert.throws(()=>resolver.resolve(patch({}),selectVisualTool({...args,edit_strategy:'rebuild'})));
});

test('new trusted numerical capabilities expose bounded parameters and integral rectangle counts',()=>{
  for(const [recipe,parameters] of [['riemann',{upper:2,count:8,sample_position:.5}],['refraction',{n1:1.5,n2:1,angle:60}],['queue',{arrival:1.2,service:1.8}]]){
    const route=selectVisualTool({category:'numerical',goal:'可信数值解释',subject:'other',dimension_preference:'auto',numerical_recipe:recipe});
    const validate=createProposalValidator(schema,null,12,{getRoute:()=>route});
    const value={title:recipe,recipe,duration:12,parameters,selection:route.selection};
    assert.equal(validate(value).valid,true);
    assert.equal(validate({...value,parameters:{...parameters,unknown:1}}).valid,false);
    if(recipe==='riemann')assert.equal(validate({...value,parameters:{...parameters,count:8.5}}).valid,false);
  }
});
