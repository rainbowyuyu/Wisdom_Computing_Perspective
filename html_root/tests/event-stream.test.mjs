import { test } from 'node:test';
import assert from 'node:assert/strict';
import { consumeEvents } from '../static/js/event-stream.js';

test('SSE preserves UTF-8 across byte boundaries, CRLF and multiline payloads', async () => {
  const bytes = new TextEncoder().encode('data: {"type":"step",\r\ndata: "text":"求导"}\r\n\r\ndata: {"type":"complete"}\r\n\r\n');
  const response = new Response(new ReadableStream({start(controller) {for(const byte of bytes) controller.enqueue(Uint8Array.of(byte));controller.close();}}));
  const events=[];await consumeEvents(response,e=>events.push(e));
  assert.deepEqual(events,[{type:'step',text:'求导'},{type:'complete'}]);
});
test('truncated responses cannot masquerade as completion', async()=>{
  await assert.rejects(consumeEvents(new Response('data: {"type":"step"}\n\n'),()=>{}), /连接提前结束/);
});
test('abort closes the reader and does not report success', async()=>{
  let cancelled=false;const controller=new AbortController();
  const response=new Response(new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('data: {"type":"step"}\n\n'));},cancel(){cancelled=true;}}));
  await assert.rejects(consumeEvents(response,()=>controller.abort(),controller.signal),{name:'AbortError'});
  assert.equal(cancelled,true);
});
