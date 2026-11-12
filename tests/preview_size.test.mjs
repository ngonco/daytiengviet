import test from 'node:test';
import assert from 'node:assert/strict';
import {fitPreview} from '../frontend/preview_size.ts';
test('wide short dock keeps landscape scene and circular face proportional',()=>{
 const size=fitPreview(1386,267,1920,1080);
 assert.deepEqual(size,{width:1920*(267/1080),height:267});
 assert.ok(Math.abs(size.width/size.height-16/9)<1e-12);
 assert.ok(Math.abs(270/1920*size.width-270/1080*size.height)<1e-9);
});
test('landscape, portrait and original scene fit both available dimensions on resize',()=>{
 for(const [sw,sh] of [[1920,1080],[1080,1920],[1440,1080]])for(const [w,h] of [[1386,267],[320,200],[800,600],[600,900]]){
  const s=fitPreview(w,h,sw,sh);
  assert.ok(s.width<=w+1e-9&&s.height<=h+1e-9);
  assert.ok(Math.abs(s.width/s.height-sw/sh)<1e-12);
 }
});
test('unmeasured, hidden or invalid stages do not create a stretched scene',()=>{
 for(const args of [[0,200,1920,1080],[300,0,1920,1080],[NaN,200,1920,1080],[300,200,0,1080]])assert.deepEqual(fitPreview(...args),{width:0,height:0});
});
