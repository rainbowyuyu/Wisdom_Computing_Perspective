/** Official Qwen Chat Completions route. Never handles key material or overrides
 * model output; native DSH/pi-ai retains the entire model/tool lifecycle. */
const HOSTS=new Set(['dashscope.aliyuncs.com','dashscope-intl.aliyuncs.com','dashscope-us.aliyuncs.com']);
export function officialQwenEndpoint(value) {
  if(typeof value!=='string' || /[\r\n\0\\]/.test(value))throw new Error('INVALID_INPUT');
  const url=new URL(value);
  if(url.protocol!=='https:' || !HOSTS.has(url.hostname) || url.port || url.username || url.password
    || url.search || url.hash || url.pathname.replace(/\/+$/,'')!=='/compatible-mode/v1')throw new Error('INVALID_INPUT');
  return url.origin+'/compatible-mode/v1';
}

export const QWEN_COMPAT=Object.freeze({supportsStore:false,supportsDeveloperRole:false,
  supportsReasoningEffort:false,supportsUsageInStreaming:true,supportsFinishReason:true,
  supportsStrictMode:false,maxTokensField:'max_tokens',thinkingFormat:'qwen'});

/** Disable redirects as well as rejecting every non-official request target.
 * This is scoped to the private one-task Qwen process and leaves payloads intact. */
export function guardQwenTransport(base,fetchImpl=globalThis.fetch) {
  const target=officialQwenEndpoint(base)+'/chat/completions';
  return (input,init)=>{
    const url=typeof input==='string'?input:input instanceof URL?input.href:input?.url;
    if(url!==target)throw Object.assign(new Error('INVALID_INPUT'),{code:'INVALID_INPUT'});
    return fetchImpl(input,{...init,redirect:'error'});
  };
}
