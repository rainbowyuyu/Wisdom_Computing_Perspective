import test from 'node:test';
import assert from 'node:assert/strict';
import {createProposalCompletion} from './bridge.mjs';

const valid=value=>({valid:value?.title==='scene',issues:value?.title==='scene'?[]:['invalid title']});

test('short final acknowledgement adopts the exact checked JSON snapshot',()=>{
  const completion=createProposalCompletion(valid);
  const original={title:'scene',scene:{objects:[{id:'gear',rotation:0}],interactions:[{id:'angle',value:0}]}};
  const expected=structuredClone(original),result=completion.check(original);
  assert.equal(result.valid,true);
  assert.match(result.proposal_id,/^sha256:[a-f0-9]{64}$/);
  assert.deepEqual(result.final_response,{accept_proposal:result.proposal_id});
  original.scene.objects[0].rotation=5;
  const resolved=completion.resolve(result.final_response);
  assert.equal(resolved.source,'checked-reference');
  assert.deepEqual(resolved.proposal,expected);
  resolved.proposal.scene.interactions[0].value=99;
  assert.deepEqual(completion.resolve(result.final_response).proposal,expected);
});

test('unvalidated, stale and mixed acknowledgements fail closed',()=>{
  const completion=createProposalCompletion(valid);
  assert.throws(()=>completion.resolve({title:'scene'}),{code:'INVALID_OUTPUT'});
  assert.throws(()=>completion.resolve({accept_proposal:'invented'}),{code:'INVALID_OUTPUT'});
  const first=completion.check({title:'scene',revision:1});
  assert.throws(()=>completion.resolve({...first.final_response,title:'scene'}),{code:'INVALID_OUTPUT'});
  const second=completion.check({title:'scene',revision:2});
  assert.notEqual(first.proposal_id,second.proposal_id);
  assert.throws(()=>completion.resolve(first.final_response),{code:'INVALID_OUTPUT'});
  assert.equal(completion.resolve(second.final_response).proposal.revision,2);
  assert.equal(completion.check({title:'invalid'}).valid,false);
  assert.throws(()=>completion.resolve(second.final_response),{code:'INVALID_OUTPUT'});
});

test('complete repaired final JSON stays compatible and is revalidated',()=>{
  let allowed=true;
  const completion=createProposalCompletion(value=>allowed?valid(value):{valid:false,issues:['route changed']});
  completion.check({title:'invalid'});
  assert.equal(completion.resolve({title:'scene',revision:3}).source,'full');
  const accepted=completion.check({title:'scene'});
  allowed=false;
  assert.throws(()=>completion.resolve(accepted.final_response),{code:'INVALID_OUTPUT'});
  assert.throws(()=>completion.resolve({title:'scene'}),{code:'INVALID_OUTPUT'});
});

test('private content never becomes an adoptable checked snapshot',()=>{
  const completion=createProposalCompletion(valid,'synthetic-private-marker');
  const checked=completion.check({title:'scene',summary:'synthetic-private-marker'});
  assert.equal(checked.valid,false);
  assert.ok(!JSON.stringify(checked).includes('synthetic-private-marker'));
  assert.throws(()=>completion.resolve({title:'scene',summary:'synthetic-private-marker'}),{code:'INVALID_OUTPUT'});
});
