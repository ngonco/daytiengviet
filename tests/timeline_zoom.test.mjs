import test from 'node:test';import assert from 'node:assert/strict';import {wheelTimelineZoom,anchoredScroll} from '../frontend/timeline_zoom.ts';
test('Ctrl wheel zoom direction, line/pixel normalization and boundaries',()=>{
 assert.ok(wheelTimelineZoom(4,-100)>4);assert.ok(wheelTimelineZoom(4,100)<4);
 assert.equal(wheelTimelineZoom(1,100),1);assert.equal(wheelTimelineZoom(256,-100),256);
 assert.equal(wheelTimelineZoom(4,3,1),wheelTimelineZoom(4,48,0));assert.equal(wheelTimelineZoom(4,NaN),4);
});
test('time under pointer remains anchored on a horizontally scrolled timeline',()=>{
 const width=800,oldZoom=4,scroll=950,pointer=250,ratio=(scroll+pointer)/(width*oldZoom),zoom=wheelTimelineZoom(oldZoom,-100);
 const next=anchoredScroll(ratio,pointer,width,zoom);assert.ok(Math.abs((next+pointer)/(width*zoom)-ratio)<1e-10);
 assert.equal(anchoredScroll(0,250,width,2),0);assert.equal(anchoredScroll(1,0,width,2),800);
});
