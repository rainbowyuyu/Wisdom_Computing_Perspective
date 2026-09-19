import { test } from 'node:test';
import assert from 'node:assert/strict';
import { recoverRequest, requestFailure, recoveryDelay } from '../static/js/automatic-recovery.js';

test('recovers automatically with a bounded budget and reports progress',async()=>{
    const calls=[],updates=[];
    const value=await recoverRequest(async attempt=>{calls.push(attempt);if(attempt<2)throw new Error('temporary failure');return 42;},
        {onRetry:n=>updates.push(n),delay:async()=>{}});
    assert.equal(value,42);assert.deepEqual(calls,[0,1,2]);assert.deepEqual(updates,[1,2]);
    let count=0;
    await assert.rejects(recoverRequest(async()=>{count++;throw new Error('persistent failure');},{delay:async()=>{}}),/persistent failure/);
    assert.equal(count,3);
});

test('does not retry permissions, quotas, missing conditions or explicit stops',async()=>{
    for(const error of [requestFailure('auth',{},403),requestFailure('quota',{},429),requestFailure('input',{},422),
        requestFailure('missing information',{retryable:false}),new DOMException('stop','AbortError')]){
        let calls=0;
        await assert.rejects(recoverRequest(async()=>{calls++;throw error;},{delay:async()=>{}}));
        assert.equal(calls,1);
    }
});

test('cancelling during recovery prevents another request and clears the wait',async()=>{
    const controller=new AbortController();let calls=0;
    const result=recoverRequest(async()=>{calls++;throw new Error('temporary failure');},
        {signal:controller.signal,onRetry:()=>controller.abort()});
    await assert.rejects(result,{name:'AbortError'});assert.equal(calls,1);
    const pending=new AbortController();const wait=recoveryDelay(60000,pending.signal);
    pending.abort();await assert.rejects(wait,{name:'AbortError'});
});
