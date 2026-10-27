import test from 'node:test';
import assert from 'node:assert/strict';
import { auditValue, failureCode } from './bridge.mjs';
import { createProposalValidator, selectVisualTool } from './contracts.mjs';

test('audit removes credentials, binary input and raw provider diagnostics', () => {
  const value = auditValue({prompt:'hi synthetic-secret', image:{data:'A'.repeat(1024)},
    url:'data:image/png;base64,'+'B'.repeat(1024),headers:{Authorization:'Bearer synthetic-secret'},
    failure:{code:'AUTH',message:'raw upstream diagnostic'},error:{code:'SERVER',reason:'endpoint secret'}}, 'synthetic-secret');
  const text=JSON.stringify(value);
  for (const forbidden of ['synthetic-secret','AAAA','BBBB','raw upstream','endpoint secret']) assert.ok(!text.includes(forbidden));
  assert.equal(value.failure.code,'AUTH');
  assert.equal(failureCode({code:'TRANSPORT'}),'NETWORK');
});

const semantic = (category, options={}) => ({category,goal:'说明实际对象与关系',subject:'other',dimension_preference:'auto',...options});

test('tool routing uses semantic category, honoring explicit user dimensions', () => {
  assert.equal(selectVisualTool(semantic('mechanism')).selection.engine,'threejs');
  assert.equal(selectVisualTool(semantic('spatial')).selection.engine,'threejs');
  assert.equal(selectVisualTool(semantic('formula')).selection.engine,'manim');
  assert.equal(selectVisualTool(semantic('process'),{prompt:'包含风机的制造流程'}).selection.engine,'canvas2d');
  assert.equal(selectVisualTool(semantic('mechanism',{subject:'axial_fan',dimension_preference:'2d',preference_quote:'只画平面'}),{prompt:'风机只画平面'}).selection.engine,'canvas2d');
  assert.throws(()=>selectVisualTool(semantic('mechanism',{dimension_preference:'2d',preference_quote:'只画平面'}),{prompt:'解释风机运行'}));
  assert.deepEqual(selectVisualTool(semantic('numerical',{numerical_recipe:'pendulum'})).candidate_recipes,['pendulum']);
  assert.deepEqual(selectVisualTool(semantic('mechanism',{subject:'axial_fan'})).candidate_recipes,['fan','custom']);
  assert.deepEqual(selectVisualTool(semantic('mechanism',{subject:'other'})).candidate_recipes,['custom']);
});

function machineProposal(route){return {title:'机器',recipe:'custom',duration:12,selection:route.selection,
  scene:{duration:12,mode:'3d',selection:route.selection,objects:[
    {id:'rotor',kind:'group',frames:[{t:0,rotation:0},{t:12,rotation:6.28}]},
    {id:'hub',kind:'cylinder',radius:.5,height:1,parent_id:'rotor'},
    {id:'body',kind:'box',width:2,height:2,depth:1},
  ]}};}

test('accepted 3D tool choice binds recipe, mode, entity volume and animation', () => {
  const route=selectVisualTool(semantic('mechanism'));
  const check=createProposalValidator({type:'object'},null,12,{getRoute:()=>route});
  const valid=machineProposal(route);
  assert.equal(check(valid).valid,true);
  assert.equal(check({...valid,recipe:'fan'}).valid,false);
  assert.equal(check({...valid,selection:{...route.selection,engine:'canvas2d'}}).valid,false);
  assert.equal(check({...valid,scene:{...valid.scene,mode:'2d'}}).valid,false);
  assert.equal(check({...valid,scene:{...valid.scene,objects:[{id:'a',kind:'circle'},{id:'b',kind:'rect'}]}}).valid,false);
  const noMotion=structuredClone(valid);noMotion.scene.objects[0].frames=[];
  assert.equal(check(noMotion).valid,false);
  const initialPoseOnly=structuredClone(valid);initialPoseOnly.scene.objects[0].frames=[{t:0,rotation:1}];
  assert.equal(check(initialPoseOnly).valid,false,'a single t=0 pose is not a moving mechanism');
  const textMotion=structuredClone(noMotion);textMotion.scene.objects.push({id:'label',kind:'text',frames:[{t:0,x:0},{t:12,x:2}]});
  assert.equal(check(textMotion).valid,false);
});

test('hierarchy validation rejects cycles and invalid primitive geometry', () => {
  const route=selectVisualTool(semantic('mechanism'));
  const check=createProposalValidator({type:'object'},null,12,{getRoute:()=>route});
  const cyclic=machineProposal(route);cyclic.scene.objects[0].parent_id='rotor';
  assert.equal(check(cyclic).valid,false);
  const wrongParent=machineProposal(route);wrongParent.scene.objects[1].parent_id='body';
  assert.equal(check(wrongParent).valid,false);
  const invalidRing=machineProposal(route);invalidRing.scene.objects.push({id:'ring',kind:'torus',radius:1,tube_radius:2});
  assert.equal(check(invalidRing).valid,false);
  const invalidPrism=machineProposal(route);invalidPrism.scene.objects.push({id:'blade',kind:'prism',points:[[0,0],[1,1]]});
  assert.equal(check(invalidPrism).valid,false);
  invalidPrism.scene.objects.at(-1).points=[[0,0],[1,1],[2,2]];
  assert.equal(check(invalidPrism).valid,false);
  invalidPrism.scene.objects.at(-1).points=Array.from({length:65},(_,i)=>[Math.cos(i),Math.sin(i)]);
  assert.equal(check(invalidPrism).valid,false);
});

test('solid visibility includes animated alpha and multiplies parent opacity', () => {
  const route=selectVisualTool(semantic('mechanism'));
  const check=createProposalValidator({type:'object'},null,12,{getRoute:()=>route});
  const hidden=machineProposal(route);hidden.scene.objects[0].opacity=0;
  assert.equal(check(hidden).valid,false,'invisible parent cannot supply a solid part');
  hidden.scene.objects[0].frames.push({t:6,opacity:1});hidden.scene.objects[0].frames.sort((a,b)=>a.t-b.t);
  assert.equal(check(hidden).valid,true,'parent group fading into view is allowed');
  const fade=machineProposal(route);fade.scene.objects[1].opacity=0;fade.scene.objects[1].frames=[{t:0,opacity:0},{t:6,opacity:1}];
  assert.equal(check(fade).valid,true,'child opacity=0 at base may become visible later');
  const inherited=machineProposal(route);inherited.scene.objects[0].opacity=.1;inherited.scene.objects[1].opacity=.1;
  assert.equal(check(inherited).valid,false,'two small opacities multiply, not merely pass individually');
  const overlap=machineProposal(route);overlap.scene.objects[0].opacity=0;overlap.scene.objects[0].frames=[{t:0,opacity:0,rotation:0},{t:12,opacity:1,rotation:6.28}];
  overlap.scene.objects[1].frames=[{t:0,opacity:1},{t:12,opacity:0}];
  assert.equal(check(overlap).valid,true,'opposite fades have a visible interior despite zero opacity at both endpoints');
});

test('final checks require actual tool selection and honor fan parameter bounds', () => {
  const check=createProposalValidator({type:'object'},null,12,{getRoute:()=>null});
  assert.equal(check({title:'x',recipe:'diagram',duration:12}).valid,false);
  const route=selectVisualTool(semantic('mechanism',{subject:'axial_fan'}));
  const fanCheck=createProposalValidator({type:'object'},null,12,{getRoute:()=>route});
  assert.equal(fanCheck({recipe:'fan',duration:12,selection:route.selection,parameters:{speed:.5,pitch:20,explode:1}}).valid,true);
  assert.equal(fanCheck({recipe:'fan',duration:12,selection:route.selection,parameters:{speed:10}}).valid,false);
});

test('generic scene validator enforces geometry and image ownership beyond JSON Schema', () => {
  const check=createProposalValidator({type:'object'}, 'asset-one');
  const value={recipe:'custom',duration:12,scene:{duration:12,objects:[
    {id:'path',kind:'path',points:[[0,0],[1,1]],frames:[{t:1},{t:2}]},
    {id:'image',kind:'image',asset_id:'asset-one'},
  ],steps:[{start:0,end:12,focus:['path']}]}};
  assert.equal(check(value).valid,true);
  value.scene.objects[1].asset_id='asset-other';
  assert.equal(check(value).valid,false);
  value.scene.objects[1].asset_id='asset-one';
  value.scene.objects[0].frames[1].t=1;
  assert.equal(check(value).valid,false);
});

function interactiveMachine(route){
  const proposal=machineProposal(route);
  proposal.scene.objects[0].frames=[];
  proposal.scene.interactions=[{id:'angle',label:'驱动角度',value:0,min:-3.14,max:3.14,step:.01,
    description:'拖动转子观察装配方向；这是结构示意。',
    bindings:[{target_id:'rotor',property:'rotation',multiplier:1},{target_id:'body',property:'rotation',multiplier:-1}],
    drag:{target_id:'rotor',axis:'horizontal',sensitivity:.01}}];
  return proposal;
}

test('content interactions move solid assemblies without forced video keyframes', () => {
  const route=selectVisualTool(semantic('mechanism'));
  const check=createProposalValidator({type:'object'},null,12,{getRoute:()=>route});
  const valid=interactiveMachine(route);
  assert.deepEqual(check(valid),{valid:true,issues:[]});
  const textOnly=structuredClone(valid);
  textOnly.scene.objects.push({id:'caption',kind:'text',text:'转向'});
  textOnly.scene.interactions[0].bindings=[{target_id:'caption',property:'rotation',multiplier:1}];
  delete textOnly.scene.interactions[0].drag;
  assert.equal(check(textOnly).valid,false,'moving a caption cannot replace a mechanical degree of freedom');
  const fadeOnly=structuredClone(valid);
  fadeOnly.scene.interactions[0].bindings=[{target_id:'rotor',property:'opacity',multiplier:1}];
  assert.equal(check(fadeOnly).valid,false,'visibility alone is not mechanical transform motion');
  const computed=structuredClone(valid);computed.scene.evidence='computed';
  assert.equal(check(computed).valid,false,'generic changes cannot invalidate computed numeric data');
});

test('interaction references, dimensions, ranges and bindings reject ineffective or unsafe freedom', () => {
  const route=selectVisualTool(semantic('mechanism'));
  const check=createProposalValidator({type:'object'},null,12,{getRoute:()=>route});
  for(const change of [
    c=>{c.bindings[0].target_id='missing';},
    c=>{c.bindings[0].property='latex';},
    c=>{c.bindings[0].multiplier=0;},
    c=>{c.bindings[0].multiplier=101;},
    c=>{c.bindings.push({...c.bindings[0],multiplier:-1});},
    c=>{c.min=c.max;},
    c=>{c.value=10;},
    c=>{c.step=100;},
  ]){
    const invalid=interactiveMachine(route);change(invalid.scene.interactions[0]);
    assert.equal(check(invalid).valid,false);
  }
  const twoD={recipe:'custom',duration:12,scene:{mode:'2d',duration:12,objects:[{id:'point',kind:'circle'}],
    interactions:[{id:'move',label:'位置',value:0,min:-1,max:1,step:.1,bindings:[{target_id:'point',property:'z',multiplier:1}]}]}};
  assert.equal(createProposalValidator({type:'object'})(twoD).valid,false);
  const clipped=interactiveMachine(route),control=clipped.scene.interactions[0];
  control.min=0;control.max=1;control.value=0;
  control.bindings=[{target_id:'rotor',property:'scale',multiplier:1}];clipped.scene.objects[0].scale=20;
  assert.equal(check(clipped).valid,false,'always-clipped bounds are not a useful binding');
  clipped.scene.objects[0].frames=[{t:0,scale:20},{t:6,scale:19}];
  assert.equal(check(clipped).valid,true,'a binding can have effective range during the timeline');
});

test('drag declarations target their own rendered assembly and cannot conflict', () => {
  const route=selectVisualTool(semantic('mechanism'));
  const check=createProposalValidator({type:'object'},null,12,{getRoute:()=>route});
  for(const change of [
    p=>{p.scene.interactions[0].drag.target_id='hub';},
    p=>{p.scene.interactions[0].drag.sensitivity=0;},
    p=>{p.scene.objects[1].parent_id=null;},
    p=>{p.scene.interactions.push({...structuredClone(p.scene.interactions[0]),id:'second'});},
    p=>{p.scene.interactions.push({...structuredClone(p.scene.interactions[0]),drag:undefined});},
  ]){
    const invalid=interactiveMachine(route);change(invalid);
    assert.equal(check(invalid).valid,false);
  }
  const text=interactiveMachine(route);
  text.scene.objects.push({id:'caption',kind:'text'});
  text.scene.interactions[0].bindings.push({target_id:'caption',property:'x',multiplier:1});
  text.scene.interactions[0].drag.target_id='caption';
  assert.equal(check(text).valid,false,'text is not an object manipulation handle');
});

test('toggle represents bounded visibility without a continuous drag handle', () => {
  const check=createProposalValidator({type:'object'});
  const value={recipe:'custom',scene:{objects:[{id:'feature',kind:'circle'}],
    interactions:[{id:'visible',label:'显示细节',kind:'toggle',value:1,min:0,max:1,step:1,
      bindings:[{target_id:'feature',property:'opacity',multiplier:1}]}]}};
  assert.equal(check(value).valid,true);
  value.scene.interactions[0].drag={target_id:'feature',axis:'horizontal',sensitivity:.01};
  assert.equal(check(value).valid,false);
  delete value.scene.interactions[0].drag;value.scene.interactions[0].value=.5;
  assert.equal(check(value).valid,false);
});
