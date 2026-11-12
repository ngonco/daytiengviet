import test from 'node:test';import assert from 'node:assert/strict';
import {keepSpans,sourceTime,mapRange,insertPause,removeOutputRange} from '../frontend/output_timeline.ts';
test('repeated insertions accumulate and distinct positions remain separate',()=>{
 let pauses=insertPause([],1);pauses=insertPause(pauses,1);pauses=insertPause(pauses,1);
 assert.equal(pauses.length,1);assert.equal(pauses[0].duration,6);pauses=insertPause(pauses,2);assert.equal(pauses.length,2);
 assert.throws(()=>insertPause(pauses,1,600));
 assert.equal(insertPause([],3.012,2,3.012)[0].at,3.012);
});
test('pause mapping matches export, hides subtitle intervals, and freezes the retained previous frame',()=>{
 const spans=keepSpans(3,[{start:1,end:1.5,enabled:true}],[{id:'a',at:0,duration:1},{id:'b',at:1.5,duration:2},{id:'c',at:3,duration:.5}]);
 assert.equal(spans.at(-1).output_end,6);assert.ok(Math.abs(sourceTime(2.5,spans)-29/30)<1e-9);
 assert.deepEqual(mapRange(0,3,spans).map(s=>[s.start,s.end]),[[1,2],[4,5.5]]);
});
test('deleting only inserted silence shortens it without touching source cuts',()=>{
 const result=removeOutputRange(3,[],[{id:'a',at:1,duration:4}],2,4);
 assert.equal(result.pauses[0].duration,2);assert.deepEqual(result.cuts,[]);
 const removed=removeOutputRange(3,[],[{id:'a',at:1,duration:2}],1,3);assert.deepEqual(removed.pauses,[]);
 assert.throws(()=>removeOutputRange(3,[],[],0,3));
});
