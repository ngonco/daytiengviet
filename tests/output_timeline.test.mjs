import test from 'node:test';
import assert from 'node:assert/strict';
import {keepSpans,sourceTime,outputTime,mapRange} from '../frontend/output_timeline.ts';
import {manualCut} from '../frontend/editing.ts';
test('assembly mapping merges cuts, ignores disabled cuts, keeps subtitle and lesson positions',()=>{
 const spans=keepSpans(12,[{start:2,end:4,enabled:true},{start:3,end:5,enabled:true},{start:9,end:10,enabled:true},{start:6,end:7,enabled:false}]);
 assert.deepEqual(spans,[{start:0,end:2,output_start:0,output_end:2},{start:5,end:9,output_start:2,output_end:6},{start:10,end:12,output_start:6,output_end:8}]);
 assert.equal(sourceTime(2,spans),5);assert.equal(outputTime(3,spans),2);assert.equal(sourceTime(8,spans),12);
 assert.deepEqual(mapRange(1,11,spans),[{start:1,end:2,sourceStart:1,sourceEnd:2},{start:2,end:6,sourceStart:5,sourceEnd:9},{start:6,end:7,sourceStart:10,sourceEnd:11}]);
});
test('successive ripple deletions crossing old joins preserve exactly the selected output duration',()=>{
 let cuts=[{start:2,end:5,enabled:true}];let spans=keepSpans(12,cuts);
 const a=sourceTime(1,spans),b=sourceTime(4-1e-8,spans);cuts.push({...manualCut(a,b,12,cuts),enabled:true});
 spans=keepSpans(12,cuts);assert.equal(spans.at(-1).output_end,6);assert.equal(sourceTime(1,spans),7);
 assert.throws(()=>manualCut(0,6,6,[]));
});
test('source/output roundtrip at retained frames agrees after overlapping source cuts',()=>{
 const spans=keepSpans(15,[{start:0,end:1,enabled:true},{start:3,end:5,enabled:true},{start:12,end:15,enabled:true}]);
 for(let frame=0;frame<9*30;frame++){const output=frame/30;assert.ok(Math.abs(outputTime(sourceTime(output,spans),spans)-output)<1e-8);}
});
