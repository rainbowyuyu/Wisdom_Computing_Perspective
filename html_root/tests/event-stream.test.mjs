import { test } from 'node:test';
import assert from 'node:assert/strict';
import { consumeEvents, requestEvents } from '../static/js/event-stream.js';

test('SSE preserves UTF-8 across byte boundaries, CRLF and multiline payloads', async () => {
  const bytes = new TextEncoder().encode('data: {"type":"step",\r\ndata: "text":"求导"}\r\n\r\ndata: {"type":"complete"}\r\n\r\n');
  const response = new Response(new ReadableStream({start(controller) {for(const byte of bytes) controller.enqueue(Uint8Array.of(byte));controller.close();}}));
  const events=[];await consumeEvents(response,e=>events.push(e));
  assert.deepEqual(events,[{type:'step',text:'求导'},{type:'complete'}]);
});
test('truncated responses cannot masquerade as completion', async()=>{
  await assert.rejects(consumeEvents(new Response('data: {"type":"step"}\n\n'),()=>{}), /连接提前结束/);
});

test('agent handoff terminates the original stream', {timeout:1000}, async()=>{
  let cancelled=false;const events=[];
  const response=new Response(new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('data: {"type":"handoff"}\n\n'));},cancel(){cancelled=true;}}));
  await consumeEvents(response,e=>events.push(e));
  assert.equal(events[0].type,'handoff');assert.equal(cancelled,true);
});
test('abort closes the reader and does not report success', async()=>{
  let cancelled=false;const controller=new AbortController();
  const response=new Response(new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('data: {"type":"step"}\n\n'));},cancel(){cancelled=true;}}));
  await assert.rejects(consumeEvents(response,()=>controller.abort(),controller.signal),{name:'AbortError'});
  assert.equal(cancelled,true);
});

test('completion releases a stream even when transport and cancellation stay open', {timeout:1000}, async()=>{
  let cancelled=false;
  const response=new Response(new ReadableStream({
    start(c){c.enqueue(new TextEncoder().encode('data: {"type":"complete"}\n\n'));},
    cancel(){cancelled=true;return new Promise(()=>{});}
  }));
  await consumeEvents(response,()=>{});
  assert.equal(cancelled,true);
});

test('errors release a stream without waiting for transport cleanup', {timeout:1000}, async()=>{
  const response=new Response(new ReadableStream({
    start(c){c.enqueue(new TextEncoder().encode('data: {"type":"error","message":"failed"}\n\n'));},
    cancel(){return new Promise(()=>{});}
  }));
  await assert.rejects(consumeEvents(response,e=>{throw new Error(e.message);}),/failed/);
});

test('request timeout includes waiting for response headers', {timeout:1000}, async(t)=>{
  let aborted=false;
  t.mock.method(globalThis,'fetch',async(url,{signal})=>new Promise((resolve,reject)=>{
    signal.addEventListener('abort',()=>{aborted=true;reject(signal.reason);});
  }));
  await assert.rejects(requestEvents('/solve',{},()=>{}, {idleTimeoutMs:20}),/没有响应/);
  assert.equal(aborted,true);
});

test('idle connection retains delivered steps and cancels the reader', {timeout:1000}, async(t)=>{
  let cancelled=false;const received=[];
  t.mock.method(globalThis,'fetch',async()=>new Response(new ReadableStream({
    start(c){c.enqueue(new TextEncoder().encode('data: {"type":"step","index":0}\n\n'));},
    cancel(){cancelled=true;}
  })));
  await assert.rejects(requestEvents('/solve',{},e=>received.push(e),{idleTimeoutMs:20}),/没有响应/);
  assert.equal(received[0].index,0);assert.equal(cancelled,true);
});

test('heartbeats cannot extend the total task deadline', {timeout:1000}, async(t)=>{
  let pulse;let cancelled=false;
  t.after(()=>clearInterval(pulse));
  t.mock.method(globalThis,'fetch',async()=>new Response(new ReadableStream({
    start(c){pulse=setInterval(()=>c.enqueue(new TextEncoder().encode('data: {"type":"heartbeat"}\n\n')),5);},
    cancel(){clearInterval(pulse);cancelled=true;}
  })));
  await assert.rejects(requestEvents('/solve',{},()=>{}, {idleTimeoutMs:100,totalTimeoutMs:35}),/等待结果超时/);
  assert.equal(cancelled,true);
});

test('an already cancelled request never starts fetch', async(t)=>{
  const fetch=t.mock.method(globalThis,'fetch',async()=>{throw new Error('must not run');});
  const controller=new AbortController();controller.abort();
  await assert.rejects(requestEvents('/solve',{signal:controller.signal},()=>{}),{name:'AbortError'});
  assert.equal(fetch.mock.callCount(),0);
});
