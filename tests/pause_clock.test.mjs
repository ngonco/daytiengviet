import test from 'node:test';import assert from 'node:assert/strict';
import {registerHooks} from 'node:module';
registerHooks({resolve(specifier,context,next){if(specifier==='./output_timeline'&&context.parentURL?.endsWith('/pause_clock.ts'))specifier='./output_timeline.ts';return next(specifier,context)}});
const {createPausePlayback}=await import('../frontend/pause_clock.ts');import {keepSpans} from '../frontend/output_timeline.ts';
function setup(){let now=0,next=0,queue=new Map(),out=0;const video={currentTime:0,paused:true,muted:false,play(){this.paused=false;return Promise.resolve()},pause(){this.paused=true}};
 const engine=createPausePlayback(video,keepSpans(3,[],[{id:'p',at:1,duration:2}]),{onOutput:t=>out=t,onSource(){},onPlaying(){},onError:s=>assert.fail(s)},{raf:fn=>{queue.set(++next,fn);return next},caf:id=>queue.delete(id),now:()=>now});
 return {video,engine,output:()=>out,async advance(n){for(let i=0;i<n;i++){await Promise.resolve();await Promise.resolve();now+=50;if(!video.paused)video.currentTime+=.05;const callbacks=[...queue.values()];queue.clear();callbacks.forEach(fn=>fn(now))}}};}
test('playback freezes face and mutes inserted silence then resumes source after it',async()=>{const s=setup();s.engine.toggle();await s.advance(30);assert.ok(Math.abs(s.output()-1.5)<1e-8);assert.equal(s.video.paused,true);assert.equal(s.video.muted,true);assert.ok(Math.abs(s.video.currentTime-29/30)<1e-9);await s.advance(32);assert.equal(s.video.paused,false);assert.equal(s.video.muted,false);assert.ok(s.video.currentTime>=1);s.engine.dispose()});
test('toggle during silence pauses clock, seek inside silence stays frozen, end stops and toggle restarts',async()=>{const s=setup();s.engine.seek(2);s.engine.toggle();await s.advance(3);s.engine.toggle();const t=s.output();await s.advance(10);assert.equal(s.output(),t);assert.equal(s.video.paused,true);s.engine.seek(5);s.engine.toggle();assert.equal(s.output(),0);s.engine.dispose();assert.equal(s.video.muted,false)});

test('cut waits for one pending decoder seek without retargeting or stopping play intent',()=>{
 let now=0,next=0,output=0,writes=0,position=0;const queue=new Map();const flags=[];
 const video={paused:true,muted:false,seeking:false,readyState:4,get currentTime(){return position},set currentTime(t){position=t;writes++;this.seeking=true},play(){this.paused=false;return Promise.resolve()},pause(){this.paused=true}};
 const engine=createPausePlayback(video,keepSpans(8,[{start:1,end:5,enabled:true}]),{onOutput:t=>output=t,onSource(){},onPlaying:p=>flags.push(p),onError:s=>assert.fail(s)},{raf:fn=>{queue.set(++next,fn);return next},caf:id=>queue.delete(id),now:()=>now});
 function advance(n){for(let i=0;i<n;i++){now+=50;if(!video.paused&&!video.seeking)position+=.05;const batch=[...queue.values()];queue.clear();batch.forEach(fn=>fn(now))}}
 engine.toggle();advance(21);assert.equal(writes,1);assert.equal(video.seeking,true);assert.ok(Math.abs(output-1)<1e-8);
 advance(20);assert.equal(writes,1);assert.ok(Math.abs(output-1)<1e-8);assert.deepEqual(flags,[true]);
 video.seeking=false;advance(4);assert.ok(output>1);assert.deepEqual(flags,[true]);engine.dispose();
});
test('interrupted play promise during seek does not turn playback off',async()=>{
 let now=0,next=0,calls=0;const queue=new Map(),flags=[],errors=[];
 const video={currentTime:0,paused:true,muted:false,play(){calls++;if(calls===1)return Promise.reject({name:'AbortError',message:'seek interrupted play'});this.paused=false;return Promise.resolve()},pause(){this.paused=true}};
 const engine=createPausePlayback(video,keepSpans(3,[]),{onOutput(){},onSource(){},onPlaying:p=>flags.push(p),onError:s=>errors.push(s)},{raf:fn=>{queue.set(++next,fn);return next},caf:id=>queue.delete(id),now:()=>now});
 engine.toggle();await Promise.resolve();await Promise.resolve();now+=50;const batch=[...queue.values()];queue.clear();batch.forEach(fn=>fn(now));
 assert.equal(calls,2);assert.deepEqual(flags,[true]);assert.deepEqual(errors,[]);assert.equal(video.paused,false);engine.dispose();
});

test('browser clock keeps Window animation functions out of the controller receiver during insertion, play and cleanup',async()=>{
 const {browserPlaybackClock}=await import('../frontend/pause_clock.ts');
 const previousRaf=globalThis.requestAnimationFrame,previousCaf=globalThis.cancelAnimationFrame;
 let requests=0,cancellations=0;const pending=new Map();
 function checkReceiver(receiver){if(receiver!==undefined&&receiver!==globalThis)throw new TypeError('Illegal invocation')}
 globalThis.requestAnimationFrame=function(fn){checkReceiver(this);pending.set(++requests,fn);return requests};
 globalThis.cancelAnimationFrame=function(id){checkReceiver(this);cancellations++;pending.delete(id)};
 const video={currentTime:1,paused:true,muted:false,play(){this.paused=false;return Promise.resolve()},pause(){this.paused=true}};
 try{
  assert.throws(()=>({caf:globalThis.cancelAnimationFrame}).caf(0),/Illegal invocation/);
  const spans=keepSpans(3,[],[{id:'inserted',at:1,duration:2}]);let output;
  const engine=createPausePlayback(video,spans,{onOutput:t=>output=t,onSource(){},onPlaying(){},onError:s=>assert.fail(s)},browserPlaybackClock,1);
  // The insert button requests a seek immediately after mounting live preview.
  engine.seek(1);assert.equal(output,1);assert.equal(video.muted,true);assert.ok(Math.abs(video.currentTime-29/30)<1e-9);
  engine.toggle();assert.equal(pending.size,1);assert.equal(video.paused,true);
  engine.toggle();assert.equal(pending.size,0);
  engine.seek(3);assert.equal(output,3);assert.equal(video.muted,false);assert.equal(video.currentTime,1);
  engine.toggle();assert.equal(video.paused,false);
  engine.dispose();assert.equal(pending.size,0);assert.ok(requests>=2&&cancellations>=4);
 }finally{
  if(previousRaf===undefined)delete globalThis.requestAnimationFrame;else globalThis.requestAnimationFrame=previousRaf;
  if(previousCaf===undefined)delete globalThis.cancelAnimationFrame;else globalThis.cancelAnimationFrame=previousCaf;
 }
});

test('a pending play promise cannot restart media after pause or disposal',async()=>{
 let resolvePlay,paused=true;const queue=new Map();let next=0;
 const video={currentTime:0,muted:false,get paused(){return paused},pause(){paused=true},play(){return new Promise(resolve=>{resolvePlay=()=>{paused=false;resolve()}})}};
 const engine=createPausePlayback(video,keepSpans(3,[]),{onOutput(){},onSource(){},onPlaying(){},onError:s=>assert.fail(s)},{raf:fn=>{queue.set(++next,fn);return next},caf:id=>queue.delete(id),now:()=>0});
 engine.toggle();engine.pause();resolvePlay();await Promise.resolve();assert.equal(video.paused,true);assert.equal(queue.size,0);
 engine.toggle();engine.dispose();resolvePlay();await Promise.resolve();assert.equal(video.paused,true);assert.equal(queue.size,0);
});
test('decoder exceptions and failed play promises report errors and stop the animation loop',async()=>{
 let next=0;const queue=new Map(),errors=[];const video={currentTime:0,muted:false,paused:true,pause(){this.paused=true},play(){return Promise.reject(new Error('decode failed'))}};
 const engine=createPausePlayback(video,keepSpans(3,[]),{onOutput(){},onSource(){},onPlaying(){},onError:s=>errors.push(s)},{raf:fn=>{queue.set(++next,fn);return next},caf:id=>queue.delete(id),now:()=>0});
 engine.toggle();await Promise.resolve();await Promise.resolve();assert.deepEqual(errors,['decode failed']);assert.equal(queue.size,0);
 Object.defineProperty(video,'currentTime',{get:()=>0,set:()=>{throw new Error('seek failed')}});assert.doesNotThrow(()=>engine.seek(1));assert.equal(errors.at(-1),'seek failed');engine.dispose();
});
test('inserted hold waits for its frozen frame to decode and invalid seeks remain finite',()=>{
 let now=0,next=0,out=0;const queue=new Map();const video={currentTime:0,paused:true,muted:false,seeking:false,readyState:0,play(){this.paused=false;return Promise.resolve()},pause(){this.paused=true}};
 const engine=createPausePlayback(video,keepSpans(3,[],[{id:'p',at:0,duration:2}]),{onOutput:t=>out=t,onSource(){},onPlaying(){},onError:s=>assert.fail(s)},{raf:fn=>{queue.set(++next,fn);return next},caf:id=>queue.delete(id),now:()=>now},NaN);
 function tick(){now+=50;const batch=[...queue.values()];queue.clear();batch.forEach(fn=>fn(now))}
 engine.toggle();tick();tick();assert.equal(out,0);video.readyState=4;video.seeking=true;tick();assert.equal(out,0);video.seeking=false;tick();assert.equal(out,.05);
 engine.seek(NaN);assert.equal(out,0);engine.dispose();
});

test('dense fractional cuts plus inserted silence never jump to source tail at a floating-point join',()=>{
 const cuts=Array.from({length:58},(_,i)=>({start:(i*100+13)/30,end:(i*100+52)/30,enabled:true}));
 const spans=keepSpans(205.252729,cuts,[{id:'p',at:337/30,duration:2}]);
 const queue=new Map();let next=0,output=0;
 const video={currentTime:0,paused:true,muted:false,play(){this.paused=false;return Promise.resolve()},pause(){this.paused=true}};
 // Run each exact join as the decoded media would report its source end.
 for(let i=0;i<spans.length-1;i++){
  const span=spans[i];if(span.kind==='pause')continue;
  const engine=createPausePlayback(video,spans,{onOutput:t=>output=t,onSource(){},onPlaying(){},onError:s=>assert.fail(s)},{raf:fn=>{queue.set(++next,fn);return next},caf:id=>queue.delete(id),now:()=>0},span.output_start);
  engine.toggle();video.currentTime=span.end;const batch=[...queue.values()];queue.clear();batch.forEach(fn=>fn(16));
  assert.ok(video.currentTime<spans.at(-1).end-1,`join ${i} jumped to tail ${video.currentTime}`);
  assert.ok(output>=span.output_start&&output<=spans[i+1].output_end);
  engine.dispose();
 }
});

test('continuous playback crosses every dense cut and repeated hold without jumping or stopping early',async()=>{
 const cuts=Array.from({length:58},(_,i)=>({start:(i*100+13)/30,end:(i*100+52)/30,enabled:true}));
 const pauses=[{id:'first',at:0,duration:2},{id:'middle',at:337/30,duration:6},{id:'late',at:150,duration:2},{id:'tail',at:205.252729,duration:2}];
 const spans=keepSpans(205.252729,cuts,pauses),end=spans.at(-1).output_end,queue=new Map(),states=[];let now=0,next=0,output=0,previous=0;
 const video={currentTime:0,paused:true,muted:false,play(){this.paused=false;return Promise.resolve()},pause(){this.paused=true}};
 const engine=createPausePlayback(video,spans,{onOutput:t=>{assert.ok(t>=previous-1e-7);assert.ok(t-previous<.1,`unexpected output jump ${previous} -> ${t}`);previous=t;output=t},onSource(){},onPlaying:p=>states.push(p),onError:s=>assert.fail(s)},{raf:fn=>{queue.set(++next,fn);return next},caf:id=>queue.delete(id),now:()=>now});
 engine.toggle();
 for(let i=0;i<Math.ceil((end+10)*30)&&queue.size;i++){
  await Promise.resolve();await Promise.resolve();now+=1000/30;if(!video.paused)video.currentTime+=1/30;
  const batch=[...queue.values()];queue.clear();batch.forEach(fn=>fn(now));
 }
 assert.equal(output,end);assert.deepEqual(states,[true,false]);assert.equal(queue.size,0);engine.dispose();
});
test('playback of an older map crosses a tiny gap without seeking the source tail',()=>{
 const eps=Number.EPSILON*8,spans=[{start:0,end:1,output_start:0,output_end:1},{start:5,end:6,output_start:1+eps,output_end:2+eps},{start:10,end:20,output_start:2+eps,output_end:12+eps}];
 let tick;const video={currentTime:0,paused:true,muted:false,play(){this.paused=false;return Promise.resolve()},pause(){this.paused=true}};
 const engine=createPausePlayback(video,spans,{onOutput(){},onSource(){},onPlaying(){},onError:s=>assert.fail(s)},{raf:fn=>{tick=fn;return 1},caf(){},now:()=>0});
 engine.toggle();video.currentTime=1;tick(16);assert.equal(video.currentTime,5);video.currentTime=5.033333;tick(50);assert.ok(engine.position()>1);engine.dispose();
});
