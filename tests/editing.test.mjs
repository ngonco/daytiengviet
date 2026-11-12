import test from 'node:test';
import assert from 'node:assert/strict';
import {timelineTime,frameTime,manualCut} from '../frontend/editing.ts';

test('scrolled zoomed timeline uses actual canvas bounds and snaps to source frames',()=>{
 assert.equal(timelineTime(900,-1100,4000,120),60);
 assert.equal(timelineTime(-10,0,100,120),0);
 assert.equal(timelineTime(200,0,100,120),120);
 assert.equal(frameTime(1+1/30,120),31/30);
});
test('manual selection preserves source times and aligns inward to complete frames',()=>{
 assert.deepEqual(manualCut(1.01,2.99,10,[]),{start:31/30,end:89/30});
 assert.deepEqual(manualCut(31/30,32/30,10,[]),{start:31/30,end:32/30});
 for(const [a,b] of [[2,1],[1,1],[NaN,3],[-1,2],[0,11]])assert.throws(()=>manualCut(a,b,10,[]));
});
test('overlapping and disabled cuts cannot accidentally remove the entire video',()=>{
 assert.throws(()=>manualCut(4,10,10,[{start:0,end:5,enabled:true}]));
 assert.deepEqual(manualCut(4,9,10,[{start:0,end:5,enabled:true},{start:9,end:10,enabled:false}]),{start:4,end:9});
});
