import test from 'node:test';import assert from 'node:assert/strict';import {registerHooks} from 'node:module';
registerHooks({resolve(specifier,context,next){if(specifier==='./output_timeline'&&context.parentURL?.endsWith('/timeline_state.ts'))specifier='./output_timeline.ts';return next(specifier,context)}});
const {clampOutput,rebaseOutput,timelinePosition,resizePause}=await import('../frontend/timeline_state.ts');
import {keepSpans,removeOutputRange,insertPause} from '../frontend/output_timeline.ts';
const cut=(start,end)=>({id:`cut-${start}`,start,end,enabled:true,reason:'test',locked:true});
test('cut transaction uses the new assembly at a join, clamps tail deletion and rejects removal of all source',()=>{
 const initial=[cut(2,5)],edit=removeOutputRange(12,initial,[],1,4);
 assert.deepEqual(timelinePosition(12,edit,1),{output:1,source:7});
 const tail=removeOutputRange(12,initial,[],5,9);assert.deepEqual(timelinePosition(12,tail,9),{output:5,source:8});
 assert.throws(()=>timelinePosition(12,{cuts:[cut(0,12)],pauses:[]},0));
 assert.equal(clampOutput(NaN,keepSpans(12,[])),0);
});
test('undo/redo and earlier edits preserve source frame and exact offset inside an existing hold',()=>{
 const pause={id:'p',at:4,duration:4},before=keepSpans(10,[],[pause]),after=keepSpans(10,[cut(1,3)],[pause]);
 assert.equal(rebaseOutput(6,before,after),4);assert.equal(rebaseOutput(4,after,before),6);
 assert.equal(rebaseOutput(11,before,after),9);
 const shortened=keepSpans(10,[cut(1,3)],[{...pause,duration:1}]);assert.equal(rebaseOutput(5,after,shortened),3);
 assert.equal(rebaseOutput(14,before,after),12);
});
test('removing or resizing a hold cannot leave the playhead outside the new timeline or create zero-duration holds',()=>{
 const pauses=[{id:'p',at:4,duration:4}],before=keepSpans(10,[],pauses),after=keepSpans(10,[]);
 assert.equal(rebaseOutput(6,before,after),4);
 const resized=resizePause(pauses,'p',.001);assert.equal(resized[0].duration,1/30);
 assert.throws(()=>resizePause(pauses,'p',NaN));assert.throws(()=>resizePause(pauses,'p',601));
 const excessive=Array.from({length:7},(_,i)=>({id:`p${i}`,at:i,duration:600}));assert.throws(()=>timelinePosition(10,{cuts:[],pauses:excessive},0));
});
test('mixed source/hold removal, cumulative insertion and history snapshots preserve original source fields',()=>{
 const original={cuts:[cut(2,3)],pauses:insertPause([],4)},snapshot=structuredClone(original),before=keepSpans(10,original.cuts,original.pauses);
 const edit=removeOutputRange(10,original.cuts,original.pauses,2.5,4);
 assert.equal(edit.pauses[0].duration,1);assert.ok(Math.abs(keepSpans(10,edit.cuts,edit.pauses).at(-1).output_end-(before.at(-1).output_end-1.5))<1e-8);
 assert.deepEqual(original,snapshot);assert.equal(insertPause(original.pauses,4)[0].duration,4);
});
