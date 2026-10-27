import Ajv from 'ajv';
import {createHash} from 'node:crypto';

export const EDIT_GUIDE = Object.freeze({
  output:'When previous content exists, check_proposal.proposal must be {edit:{mode:"patch",base_id,...changes}}. A plain full Proposal is only for a new scene or needs_clarification=true. To rebuild explicitly use {edit:{mode:"rebuild",base_id,reason,proposal:<complete Proposal>}}. A patch never silently replaces existing objects.',
  fields:'patch supports proposal_updates (title,summary,expression,formula,formula_next,labels,assumptions), parameters (partial trusted recipe parameter updates), scene_updates (title,summary,background,camera,assumptions), object_updates [{id,set:{allowed object fields except id/kind}}], object_additions [complete objects with new IDs], object_removals [explicit IDs], interactions [complete replacement list], steps [complete replacement list]. Omitted fields preserve the original exactly.',
  identity:'Keep existing IDs for the same physical or conceptual object. Unknown update/removal IDs, duplicate IDs and update/remove conflicts are rejected. Removing a group never silently removes its children or references; explicitly repair all references. Do not copy sampled frames/points from context as replacements.',
  timing:'The host uniformly rescales retained custom-scene frame/step times to the requested duration. New or explicitly replaced frames/steps use the new duration. Objects, geometry and keyframe values otherwise remain unchanged.',
  trusted:'Trusted recipes accept partial proposal_updates and parameters only; they recompute using their original recipe. Changing geometry/steps/interactions of a trusted recipe requires an explicit rebuild to custom and honest schematic evidence.',
  exploration:'previous.exploration contains saved interactive values/camera for context. Original scene defaults remain the merge base. Do not bake the saved offsets into objects while retaining the same interactions; that would apply them twice. Omitted objects/controls retain their defaults.',
  routing:'For ordinary edits preserve the previous engine, category and recipe. Use edit_strategy=rebuild on select_visual_tool for an intentional reconstruction or recipe change; explicit current dimension requests may change the route. Missing essential content should return needs_clarification instead of inventing measurements or scientific results.',
});

const own=(value,key)=>Object.prototype.hasOwnProperty.call(value,key);
const pick=(properties,names)=>Object.fromEntries(names.filter(name=>own(properties,name)).map(name=>[name,properties[name]]));
const strict=(properties,required=[])=>({type:'object',properties,required,additionalProperties:false});
const array=(items,maxItems)=>({type:'array',items,maxItems});

/** The exact base stays in host memory. Only its identifier and compact model
 * context enter the prompt. This reducer never executes generated expressions.
 */
export function createEditResolver(proposalSchema, previous, requestedDuration) {
  let prior=previous ? structuredClone(previous) : null;
  if(prior && !prior.proposal && prior.recipe)prior={proposal:prior,...(prior.scene?{scene:prior.scene}:{})};
  else if(prior && !prior.proposal && Array.isArray(prior.objects))prior={proposal:{title:prior.title,recipe:'custom',duration:prior.duration??12,scene:prior,...(prior.selection?{selection:prior.selection}:{})},scene:prior};
  if(prior && (!prior.proposal || typeof prior.proposal!=='object' || Array.isArray(prior.proposal)))throw new Error('Exact previous proposal is required for editing.');
  const baseId=prior?'sha256:'+createHash('sha256').update(JSON.stringify(prior)).digest('hex'):null;
  const definitions=proposalSchema.$defs||{};
  const objectProperties=definitions.ModelVisualObject?.properties||{};
  const sceneProperties=definitions.ModelScene?.properties||{};
  const proposalProperties=proposalSchema.properties||{};
  const ident={type:'string',pattern:'^[a-zA-Z0-9_-]{1,64}$'};
  const objectChanges=strict(Object.fromEntries(Object.entries(objectProperties).filter(([name])=>!['id','kind'].includes(name))));
  objectChanges.minProperties=1;
  const patch=strict({
    mode:{const:'patch'},base_id:{type:'string',const:baseId},
    proposal_updates:strict(pick(proposalProperties,['title','summary','expression','formula','formula_next','labels','assumptions'])),
    parameters:proposalProperties.parameters||{type:'object'},
    scene_updates:strict(pick(sceneProperties,['title','summary','background','camera','assumptions'])),
    object_updates:array(strict({id:ident,set:objectChanges},['id','set']),180),
    object_additions:array({$ref:'#/$defs/ModelVisualObject'},180),
    object_removals:array(ident,180),
    interactions:sceneProperties.interactions||array({type:'object'},8),
    steps:sceneProperties.steps||array({type:'object'},12),
  },['mode','base_id']);
  const rebuild=strict({mode:{const:'rebuild'},base_id:{type:'string',const:baseId},
    reason:{type:'string',minLength:1,maxLength:240},proposal:{$ref:'#/$defs/EditFullProposal'}},['mode','base_id','reason','proposal']);
  const schema={...strict({edit:{oneOf:[patch,rebuild]}},['edit']),$defs:{...definitions,EditFullProposal:{...proposalSchema,$defs:undefined}}};
  const validate=new Ajv({allErrors:true,strict:false,ownProperties:true}).compile(schema);
  function unique(items,label){if(new Set(items).size!==items.length)throw new Error(`${label} IDs must be unique.`);}
  function resolve(value,route=null){
    if(value?.needs_clarification===true)return structuredClone(value);
    if(!prior){if(value && own(value,'edit'))throw new Error('An edit requires an existing project.');return value;}
    if(!validate(value)){
      const errors=validate.errors.slice(0,6).map(e=>`${e.instancePath||'/'}: ${e.keyword} ${e.message}`);
      throw new Error('Use the typed edit envelope and exact base_id for an existing project. '+errors.join('; '));
    }
    const edit=value.edit;
    if(edit.base_id!==baseId)throw new Error('Edit base_id does not match the current project snapshot.');
    if(edit.mode==='rebuild'){
      if(!edit.reason.trim())throw new Error('Rebuilding requires a concise reason.');
      return structuredClone(edit.proposal);
    }
    const result=structuredClone(prior.proposal);
    const recipe=result.recipe;
    if(route && (!route.candidate_recipes.includes(recipe) || (prior.scene?.mode||result.scene?.mode||(['fan','model3d'].includes(recipe)?'3d':'2d'))!==route.required_mode))throw new Error('The selected route changes the existing recipe or dimension; use an explicit rebuild.');
    Object.assign(result,edit.proposal_updates||{});
    result.parameters={...(result.parameters||{}),...(edit.parameters||{})};
    result.duration=requestedDuration;
    if(route)result.selection=structuredClone(route.selection);
    const customFields=['scene_updates','object_updates','object_additions','object_removals','interactions','steps'];
    if(recipe!=='custom'){
      if(customFields.some(name=>own(edit,name)))throw new Error('Trusted recipe edits accept proposal_updates and parameters only; rebuild explicitly for custom geometry.');
      return result;
    }
    const source=prior.scene||result.scene;
    if(!source)throw new Error('The previous custom scene is missing.');
    const scene=structuredClone(source);
    const duration=scene.duration??result.duration;
    if(duration!==requestedDuration){
      const scale=requestedDuration/duration;
      for(const object of scene.objects)for(const frame of object.frames||[])frame.t*=scale;
      for(const step of scene.steps||[]){step.start*=scale;step.end*=scale;}
    }
    scene.duration=requestedDuration;
    if(route)scene.selection=structuredClone(route.selection);
    for(const key of ['title','summary','assumptions'])if(own(edit.proposal_updates||{},key))scene[key]=structuredClone(edit.proposal_updates[key]);
    Object.assign(scene,edit.scene_updates||{});
    const updates=edit.object_updates||[], additions=edit.object_additions||[], removals=edit.object_removals||[];
    unique(updates.map(o=>o.id),'Object update');unique(additions.map(o=>o.id),'Object addition');unique(removals,'Object removal');
    const byId=new Map(scene.objects.map(o=>[o.id,o])),removed=new Set(removals);
    for(const id of removals)if(!byId.has(id))throw new Error(`Cannot remove unknown object ${id}.`);
    for(const update of updates){
      if(!byId.has(update.id))throw new Error(`Cannot update unknown object ${update.id}.`);
      if(removed.has(update.id))throw new Error(`Object ${update.id} cannot be updated and removed together.`);
      Object.assign(byId.get(update.id),structuredClone(update.set));
    }
    for(const object of additions)if(byId.has(object.id))throw new Error(`New object ${object.id} already exists; update its stable ID instead.`);
    scene.objects=scene.objects.filter(o=>!removed.has(o.id)).concat(structuredClone(additions));
    if(own(edit,'interactions'))scene.interactions=structuredClone(edit.interactions);
    if(own(edit,'steps'))scene.steps=structuredClone(edit.steps);
    result.scene=scene;
    return result;
  }
  return {baseId,schema,resolve,previous:prior};
}
