import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createTaskStore,applyProgressEvent} from '../static/js/task-progress.js';

test('concurrent tasks finish independently and preserve the remaining task',()=>{
    const store=createTaskStore();
    store.set('a',{status:'running'});store.set('b',{status:'running'});
    store.set('a',{status:'done'});store.remove('a');
    assert.deepEqual(store.all(),[{id:'b',status:'running'}]);
});
test('percentages use actual steps and rendering chapters, never a time estimate',()=>{
    let task={progress:null};
    task={...task,...applyProgressEvent(task,{type:'plan',total:4})};
    task={...task,...applyProgressEvent(task,{type:'step',index:1})};
    assert.equal(task.progress,50);
    assert.equal(applyProgressEvent(task,{type:'progress',chapter:2,total:4}).progress,50);
    assert.equal(applyProgressEvent(task,{type:'repair'}).progress,null);
    assert.equal(applyProgressEvent(task,{type:'complete'}).progress,100);
});
test('legacy two-phase completion is not overall completion',()=>{
    assert.equal(applyProgressEvent({}, {step:'complete',part:'calc'}).status,undefined);
    assert.equal(applyProgressEvent({}, {type:'error',message:'failed'}).status,'error');
});
