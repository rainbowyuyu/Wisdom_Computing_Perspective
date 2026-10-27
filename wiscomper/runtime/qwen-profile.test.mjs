import test from 'node:test';
import assert from 'node:assert/strict';
import {officialQwenEndpoint,guardQwenTransport} from './qwen-profile.mjs';

test('Qwen transport restricts exact official chat endpoint and disables redirects',async()=>{
  const calls=[];
  const guard=guardQwenTransport('https://dashscope.aliyuncs.com/compatible-mode/v1/',async(...args)=>{calls.push(args);return 'ok';});
  assert.equal(await guard('https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',{method:'POST',body:'unchanged',redirect:'follow'}),'ok');
  assert.deepEqual(calls[0][1],{method:'POST',body:'unchanged',redirect:'error'});
  for(const url of ['https://evil.test/chat/completions','https://dashscope.aliyuncs.com/compatible-mode/v1/models']){
    assert.throws(()=>guard(url,{}),/INVALID_INPUT/);
  }
  assert.equal(calls.length,1);
});

test('Qwen endpoint rejects credential, path, query, port and host confusion',()=>{
  for(const value of ['http://127.0.0.1:8080/v1','https://dashscope.aliyuncs.com.evil.test/compatible-mode/v1',
    'https://user:secret@dashscope.aliyuncs.com/compatible-mode/v1','https://dashscope.aliyuncs.com:444/compatible-mode/v1',
    'https://dashscope.aliyuncs.com/compatible-mode/v1?redirect=elsewhere','https://dashscope.aliyuncs.com/compatible-mode/v1#fragment',
    'https://dashscope.aliyuncs.com/other','https://dashscope.aliyuncs.com\\@evil.test/compatible-mode/v1']){
    assert.throws(()=>officialQwenEndpoint(value));
  }
  assert.equal(officialQwenEndpoint('https://dashscope-intl.aliyuncs.com/compatible-mode/v1'),'https://dashscope-intl.aliyuncs.com/compatible-mode/v1');
});
