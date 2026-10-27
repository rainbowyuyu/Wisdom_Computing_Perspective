/** Explicit native DSH composition. No profile loader, shell/files/MCP tools,
 * title/compaction LLMs, telemetry, provider fallback, or network retries.
 * JSONL stdout is a private protocol; audit is a sanitized native-event copy,
 * intentionally not an automatic replay log or independent execution authority.
 */
import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdirSync, openSync, writeSync, closeSync, fsyncSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { CATALOG, CATEGORIES, NUMERICAL_RECIPES, PARAMETER_BOUNDS, SPATIAL_GUIDE, INTERACTION_GUIDE, SYSTEM_PROMPT, selectVisualTool, createProposalValidator } from './contracts.mjs';
import {createEditResolver,EDIT_GUIDE} from './edit-proposal.mjs';
import {officialQwenEndpoint,QWEN_COMPAT,guardQwenTransport} from './qwen-profile.mjs';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const require = createRequire(join(ROOT, 'package.json'));
const VERSION = '0.2.0-rc.2';
const MAX_STEPS = 3;
const TOOL_NAMES = new Set(['select_visual_tool', 'check_proposal']);
const emit = value => process.stdout.write(JSON.stringify(value) + '\n');
class SafeError extends Error { constructor(code) { super(code); this.code = code; } }
export function failureCode(error) {
  const code = String(error?.code || 'PROVIDER_ERROR');
  if (/AUTH|CREDENTIAL/.test(code)) return 'AUTH';
  if (/RATE_LIMIT/.test(code)) return 'RATE_LIMIT';
  if (/QUOTA/.test(code)) return 'QUOTA';
  if (/TIMEOUT/.test(code)) return 'TIMEOUT';
  if (/NETWORK|CONNECTION|TRANSPORT/.test(code)) return 'NETWORK';
  if (/SERVER|OVERLOAD/.test(code)) return 'SERVER_ERROR';
  if (/IMAGE|ATTACHMENT/.test(code)) return 'INVALID_IMAGE';
  return ['INVALID_INPUT','INVALID_OUTPUT','MAX_TOKENS','REQUEST_LIMIT','TOOL_LIMIT','RUNTIME_UNAVAILABLE','CANCELLED'].includes(code) ? code : 'PROVIDER_ERROR';
}

/** A successful check captures an immutable JSON snapshot. The model may finish
 * by acknowledging its content hash rather than emitting the scene twice.
 * Invalid checks clear the snapshot; failed or aborted turns never resolve it.
 */
export function createProposalCompletion(validate, secret = null, resolveCandidate = value=>value) {
  let checked=false,accepted=null;
  return {
    check(value) {
      checked=true;accepted=null;
      const submitted=JSON.stringify(value);
      if(typeof submitted!=='string' || Buffer.byteLength(submitted)>600_000)return {valid:false,issues:['proposal exceeds size limit or is missing']};
      let proposal;
      try{proposal=resolveCandidate(value);}catch(error){return {valid:false,issues:[String(error.message).slice(0,1000)]};}
      const encoded=JSON.stringify(proposal);
      if(typeof encoded!=='string' || Buffer.byteLength(encoded)>7_500_000)return {valid:false,issues:['merged proposal exceeds the bounded host output limit']};
      if(secret && encoded.includes(secret))return {valid:false,issues:['proposal contains unsupported private content']};
      const result=validate(proposal);
      if(!result.valid)return result;
      const id='sha256:'+createHash('sha256').update(encoded).digest('hex');
      accepted={id,proposal:JSON.parse(encoded)};
      return {...result,proposal_id:id,final_response:{accept_proposal:id}};
    },
    resolve(value) {
      if(!checked || !value || typeof value!=='object' || Array.isArray(value))throw new SafeError('INVALID_OUTPUT');
      let proposal=value,source='full',proposalId=null;
      if(Object.hasOwn(value,'accept_proposal')){
        if(Object.keys(value).length!==1 || !accepted || value.accept_proposal!==accepted.id)throw new SafeError('INVALID_OUTPUT');
        proposal=structuredClone(accepted.proposal);source='checked-reference';proposalId=accepted.id;
      } else {try{proposal=resolveCandidate(value);}catch{throw new SafeError('INVALID_OUTPUT');}}
      if((secret && JSON.stringify(proposal).includes(secret)) || !validate(proposal).valid)throw new SafeError('INVALID_OUTPUT');
      return {proposal,source,proposalId};
    },
  };
}

/** No raw provider error details or binary image data enter the audit. */
export function auditValue(value, secret, key = '', depth = 0) {
  if (depth > 35) return '[depth omitted]';
  if (/^(api[_-]?key|authorization|password|credential|headers|token)$/i.test(key)) return '[redacted]';
  if (['error','failure'].includes(key) && value && typeof value === 'object') return { code: failureCode(value) };
  if (typeof value === 'string') {
    let clean = secret ? value.split(secret).join('[redacted]') : value;
    clean = clean.replace(/data:image\/[^;]+;base64,[A-Za-z0-9+/=]+/g, '[image omitted]');
    if ((key === 'data' || clean.length > 512) && /^[A-Za-z0-9+/=\r\n]{256,}$/.test(clean)) return '[binary omitted]';
    return clean.length > 200_000 ? `[large content sha256:${createHash('sha256').update(clean).digest('hex')}]` : clean;
  }
  if (Array.isArray(value)) return value.slice(0, 1000).map(v => auditValue(v, secret, '', depth + 1));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k,v]) => [k, auditValue(v, secret, k, depth + 1)]));
  return value;
}

async function readInput() {
  let bytes = 0; const chunks = [];
  for await (const chunk of process.stdin) {
    bytes += chunk.length;
    if (bytes > 8_000_000) throw new SafeError('INVALID_INPUT');
    chunks.push(chunk);
  }
  let input;
  try { input = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { throw new SafeError('INVALID_INPUT'); }
  if (typeof input.prompt !== 'string' || input.prompt.length > 6000 || !input.schema
      || ![12,20,30].includes(input.duration) || !Number.isInteger(input.max_tokens)
      || input.max_tokens < 1 || input.max_tokens > 8192 || input.max_steps !== MAX_STEPS
      || !Number.isInteger(input.deadline_ms) || input.deadline_ms < 100 || input.deadline_ms > 120_000) throw new SafeError('INVALID_INPUT');
  return input;
}

async function main() {
  const input = await readInput();
  if (require('@deepseek-ai/dsh/package.json').version !== VERSION) throw new SafeError('RUNTIME_UNAVAILABLE');
  const secret = process.env.DSH_VISUALIZATION_API_KEY;
  const taskId = process.env.DSH_VISUALIZATION_TASK_ID;
  const dshHome = process.env.DSH_HOME;
  if (!secret || !dshHome || !/^visual-[a-f0-9]{32}$/.test(taskId || '')) throw new SafeError('RUNTIME_UNAVAILABLE');
  const isQwen=process.env.DSH_VISUALIZATION_PROVIDER==='qwen';
  if(isQwen){
    try{
      if(process.env.DSH_VISUALIZATION_API!=='openai-completions')throw new Error();
      process.env.DSH_VISUALIZATION_BASE_URL=officialQwenEndpoint(process.env.DSH_VISUALIZATION_BASE_URL);
      globalThis.fetch=guardQwenTransport(process.env.DSH_VISUALIZATION_BASE_URL);
    }catch{throw new SafeError('INVALID_INPUT');}
  }
  const auditRoot = join(dshHome, 'audit');
  mkdirSync(auditRoot, { recursive: true, mode: 0o700 });
  const audit = openSync(join(auditRoot, taskId + '.jsonl'), 'wx', 0o600);
  let auditBytes = 0;
  const record = event => {
    const line = JSON.stringify(auditValue(event, secret)) + '\n';
    auditBytes += Buffer.byteLength(line);
    if (auditBytes > 4_000_000) throw new SafeError('INVALID_OUTPUT');
    writeSync(audit, line);
  };
  record({ auditVersion:1, kind:'native-session-audit', automaticReplay:false, harness:VERSION, sessionId:taskId, maxSteps:MAX_STEPS, time:Date.now() });
  const load = async name => import(pathToFileURL(require.resolve(`@deepseek-ai/${name}`)).href);
  const { Context } = await load('cordis');
  const { createUserMessage } = await load('dsh-llm');
  const { defineTool } = await load('dsh-tools');
  const ctx = new Context();
  let selectedRoute=null;
  const validate = createProposalValidator(input.schema, input.asset_id, input.duration, {getRoute:()=>selectedRoute});
  const edits=createEditResolver(input.schema,input.previous_exact??null,input.duration);
  const completion=createProposalCompletion(validate,secret,value=>edits.resolve(value,selectedRoute));
  let handle, terminal, finish, observedFailure, finalText = '';
  let requests = 0, toolCalls = 0, streamBytes = 0;
  const cancel = code => { observedFailure ||= new SafeError(code); handle?.agent.cancel({ kind:'user', reason:code }); };
  const timer = setTimeout(() => cancel('TIMEOUT'), Math.max(100, input.deadline_ms - 750));
  const onSignal = () => cancel('CANCELLED');
  process.once('SIGTERM', onSignal); process.once('SIGINT', onSignal);
  try {
    for (const name of ['dsh-llm','dsh-session','dsh-session-projection','dsh-agent']) await ctx.plugin((await load(name)).default);
    await ctx.plugin((await load('dsh-system-prompt')).default, {
      includeHarnessIdentity:false, includeRuntimeContext:false,
      personaPrefix: SYSTEM_PROMPT + '\nAuthoritative Proposal JSON Schema:\n' + JSON.stringify(input.schema)
        +(edits.baseId?'\nAuthoritative edit envelope schema:\n'+JSON.stringify(edits.schema):''),
    });
    await ctx.plugin((await load('dsh-tools')).default, { mode:'native' });
    const output = { schema:{ type:'json' }, render:(_args,value) => [{type:'text', text:JSON.stringify(value)}] };
    ctx.tools.register(defineTool({ name:'select_visual_tool',
      description:'REQUIRED first step. Semantically identify the user goal and choose the actual visual tool. Mechanical/spatial tasks default to Three.js 3D, formulas to Manim 2D, numerical tasks to trusted recipes, and processes/images to Canvas. An explicit user 2D/3D preference wins. Returns a binding selection, allowed recipes and capabilities. No code execution or external changes.',
      parameters:{
        category:{type:'string',enum:CATEGORIES,required:true,description:'What must be understood: machine assembly/operation, spatial geometry, symbolic formula, computed quantities, relationships/process, or the uploaded image itself.'},
        goal:{type:'string',required:true,description:'Concise semantic visualization goal, max240 characters; no chain of thought.'},
        subject:{type:'string',enum:['axial_fan','electric_motor','other'],required:true,description:'Actual object identity. Use other for unrelated machines; fan means an axial fan only.'},
        dimension_preference:{type:'string',enum:['auto','2d','3d'],required:true,description:'auto unless the current user explicitly requested 2D or 3D.'},
        preference_quote:{type:'string',description:'For explicit 2d/3d, exact relevant quote from current request, max160 characters. Omit for auto.'},
        numerical_recipe:{type:'string',enum:NUMERICAL_RECIPES,description:'For numerical tasks, pick the matching trusted computation only when it fits the actual goal.'},
        edit_strategy:{type:'string',enum:['preserve','rebuild'],description:'For an existing project, preserve its category, engine and recipe by default. Choose rebuild only for an intentional reconstruction/recipe change requested by the user.'},
      }, output,
      async execute(args,exec) {
        exec.signal.throwIfAborted();
        if(selectedRoute) return {ok:false,issues:['The first accepted selection is locked for this task. Continue with check_proposal.'],...selectedRoute};
        if(requests!==1) return {ok:false,issues:['Select the visual tool in the first model step.']};
        try{selectedRoute=selectVisualTool(args,{prompt:input.prompt,assetId:input.asset_id,previous:edits.previous});}
        catch(error){return {ok:false,issues:[error.message]};}
        record({kind:'visual-tool-selection',...selectedRoute,time:Date.now()});
        return {ok:true,...selectedRoute,recipes:CATALOG,parameter_bounds:PARAMETER_BOUNDS,spatial_modeling:SPATIAL_GUIDE,interaction_modeling:INTERACTION_GUIDE,
          asset_id:input.asset_id,requested_duration:input.duration,
          ...(edits.baseId?{edit_base_id:edits.baseId,editing:EDIT_GUIDE}:{}),
          coordinates:{width:16,height:9,y:'up',angles:'radians'},modification:!!input.previous};
      },
    }));
    ctx.tools.register(defineTool({ name:'check_proposal',
      description:'REQUIRED second step after select_visual_tool. New tasks supply a complete Proposal; edits supply the typed {edit:{...}} envelope. The host merges edits onto the exact original and validates the complete result against selection, geometry, interactions, schema and image ownership. On valid=true return exactly final_response to adopt the checked snapshot. On valid=false repair the Proposal or edit envelope in the final response.',
      parameters:{ proposal:{type:'json',required:true} }, output,
      async execute(args,exec) { exec.signal.throwIfAborted();
        const result=completion.check(args.proposal);
        if(result.valid)record({kind:'proposal-checked',proposalId:result.proposal_id,bytes:Buffer.byteLength(JSON.stringify(args.proposal)),edit:!!args.proposal?.edit,time:Date.now()});
        return result;
      },
    }));
    ctx.on('tools/pre-execute', async (exec,next) => {
      if (!TOOL_NAMES.has(exec.name) || ++toolCalls > 8) { cancel('TOOL_LIMIT'); throw new SafeError('TOOL_LIMIT'); }
      emit({type:'event',stage:exec.name === 'check_proposal' ? 'checking' : 'planning'});
      return next();
    });
    if (input.image_data_url) {
      await ctx.plugin((await load('dsh-attachment-local')).default, { dshHome,
        maxImageBytes:5_242_880,maxImagesPerMessage:1,maxMessageImageBytes:5_242_880,maxImagePixels:20_000_000,
        maxImageDimension:8192,normalizedImageMaxPixels:4_194_304,normalizedImageMaxDimension:2048,
        normalizedImageMaxBytes:2_097_152,imageCompressionConcurrency:1 });
    }
    const model = process.env.DSH_VISUALIZATION_MODEL, api = process.env.DSH_VISUALIZATION_API;
    if (!['openai-responses','openai-completions','anthropic-messages'].includes(api)) throw new SafeError('INVALID_INPUT');
    const configuredEffort = process.env.DSH_VISUALIZATION_EFFORT || 'low';
    // Per-task latency policy. Read current model preference, cap reasoning locally
    // to low for this bounded visual planner; never modify CC Switch settings.
    const effort = isQwen || configuredEffort === 'off' ? 'off' : configuredEffort === 'minimal' ? 'minimal' : 'low';
    const profile = { apiKeyEnv:'DSH_VISUALIZATION_API_KEY',api,baseURL:process.env.DSH_VISUALIZATION_BASE_URL,
      timeoutMs:Math.min(110_000,input.deadline_ms),streamIdleTimeoutMs:Math.min(55_000,input.deadline_ms),
      retryPolicy:{mode:'normal',maxRetries:0},defaultMaxTokens:input.max_tokens,
      requestImageMaxBytes:2_097_152,maxRequestImageBytes:8_000_000,
      models:[{id:model,contextWindow:131072,maxTokens:input.max_tokens,input:['text','image'],
        reasoningEfforts:{off:null,minimal:'minimal',low:'low'}}] };
    if(isQwen){
      profile.compat=QWEN_COMPAT;
      profile.models[0].input=input.image_data_url?['text','image']:['text'];
    }
    if (api === 'anthropic-messages' && process.env.DSH_VISUALIZATION_BEARER === '1') profile.headers={Authorization:`Bearer ${secret}`};
    await ctx.plugin(await load('dsh-llm-pi-ai'), {providers:{'visualization-provider':profile}});
    await ctx.plugin((await load('dsh-agent-loop')).default, {agents:[],maxParallelToolCalls:1});
    ctx.on('agent/request', async (_payload,next) => {
      if (++requests > MAX_STEPS) { observedFailure = new SafeError('REQUEST_LIMIT'); throw observedFailure; }
      finish = null;
      emit({type:'event',stage:requests === 3 ? 'finalizing' : 'planning'});
      return next();
    });
    ctx.on('agent/error', ({error}) => { observedFailure ||= error; });
    ctx.on('agent/request-error', async ({failure}) => { observedFailure ||= new SafeError(failureCode(failure)); return undefined; });
    ctx.on('agent/assistant-stream', ({frame}) => {
      if (frame.type !== 'chunk') return;
      streamBytes += Buffer.byteLength(JSON.stringify(frame.chunk));
      if (streamBytes > 2_000_000) cancel('INVALID_OUTPUT');
      if (frame.chunk.type === 'finish') finish=frame.chunk.reason;
    });
    ctx.on('session/event', (_session,event) => {
      try { record(event); } catch { cancel('INVALID_OUTPUT'); }
      if (event.type === 'assistant/message') finalText=event.data.message.content.filter(b=>b.type==='text').map(b=>b.text).join('');
      if (event.type === 'turn/end') terminal=event.data.reason;
    });
    const content = [{type:'text', text:JSON.stringify({request:input.prompt,requested_duration:input.duration,
      asset_id:input.asset_id,previous:input.previous ?? null,...(edits.baseId?{edit_base_id:edits.baseId}:{})})}];
    if (input.image_data_url) {
      const match = /^data:(image\/(?:png|jpeg|webp));base64,([A-Za-z0-9+/]+={0,2})$/.exec(input.image_data_url);
      if (!match) throw new SafeError('INVALID_IMAGE');
      try { const [image] = await ctx.attachments.admitPromptContent([{type:'image',mediaType:match[1],data:match[2],name:'uploaded-image'}]); content.push(image); }
      catch { throw new SafeError('INVALID_IMAGE'); }
    }
    handle = await ctx.agents.create({sessionId:taskId,
      agentOptions:{provider:'visualization-provider',model,maxTokens:input.max_tokens,reasoningEffort:effort}});
    if (observedFailure) throw observedFailure;
    handle.agent.followup(createUserMessage({content,source:{kind:'user'}}));
    await handle.agent.whenIdle();
    if (observedFailure) throw observedFailure;
    if (finish?.kind === 'max-tokens') throw new SafeError('MAX_TOKENS');
    if (finish?.kind === 'error' || finish?.kind === 'aborted') throw new SafeError(failureCode(finish.failure));
    if (requests < 1 || requests > MAX_STEPS || terminal?.kind !== 'completed' || finish?.kind !== 'stop') throw new SafeError('PROVIDER_ERROR');
    let finalValue;
    try { finalValue=JSON.parse(finalText.trim()); } catch { throw new SafeError('INVALID_OUTPUT'); }
    if (!selectedRoute || finalText.includes(secret)) throw new SafeError('INVALID_OUTPUT');
    const {proposal,source,proposalId}=completion.resolve(finalValue);
    record({kind:'proposal-finalization',source,proposalId,finalBytes:Buffer.byteLength(finalText),time:Date.now()});
    record({kind:'audit-outcome',ok:true,requests,toolCalls,time:Date.now()});
    return {type:'result',ok:true,proposal,harness:VERSION,requests,toolCalls,sessionId:taskId};
  } catch (error) {
    record({kind:'audit-outcome',ok:false,code:failureCode(error),requests:Math.min(requests,MAX_STEPS),toolCalls,time:Date.now()});
    throw error;
  } finally {
    clearTimeout(timer); process.off('SIGTERM',onSignal); process.off('SIGINT',onSignal);
    await handle?.dispose(); await ctx.fiber.dispose(); fsyncSync(audit); closeSync(audit);
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === fileURLToPath(pathToFileURL(process.argv[1]))) {
  try { emit(await main()); }
  catch (error) { emit({type:'result',ok:false,code:failureCode(error)}); process.exitCode=1; }
}
