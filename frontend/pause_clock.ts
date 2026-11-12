import {sourceTime,spanAt,type Span} from './output_timeline';
export type PlaybackController={toggle:()=>void;pause:()=>void;seek:(output:number)=>void};
type Video=Pick<HTMLVideoElement,'currentTime'|'paused'|'muted'|'play'|'pause'>&Partial<Pick<HTMLVideoElement,'seeking'|'readyState'|'ended'>>;
type Notify={onOutput:(t:number)=>void;onSource:(t:number)=>void;onPlaying:(p:boolean)=>void;onError:(s:string)=>void};
type Clock={raf:(fn:(now:number)=>void)=>number;caf:(id:number)=>void;now:()=>number};
// Browser animation functions require the Window receiver, never the clock object.
export const browserPlaybackClock:Clock={raf:fn=>requestAnimationFrame(fn),caf:id=>cancelAnimationFrame(id),now:()=>performance.now()};
export function createPausePlayback(video:Video,spans:Span[],notify:Notify,clock:Clock,startAt=0){
 const end=spans.at(-1)?.output_end||0;let cursor=Math.max(0,Math.min(Number.isFinite(startAt)?startAt:0,end)),playing=false,handle=0,last=0,disposed=false,lastSpan:string|undefined,playPending=false;const originalMute=video.muted;
 const active=()=>spanAt(cursor,spans);
 function publish(){notify.onOutput(cursor);notify.onSource(sourceTime(cursor,spans))}
 function stop(){playing=false;clock.caf(handle);video.pause();notify.onPlaying(false)}
 function fail(error:unknown){stop();notify.onError(error instanceof Error?error.message:String((error as {message?:string})?.message||error))}
 function safely(action:()=>void){try{action()}catch(error){fail(error)}}
 function ensurePlaying(){if(!playing||!video.paused||playPending)return;playPending=true;video.play().then(()=>{playPending=false;if(disposed||!playing||active()?.kind==='pause')video.pause()}).catch(e=>{playPending=false;if(disposed||!playing||e.name==='AbortError')return;fail(e)})}

 function sync(force=false){
  const span=active(),hold=span?.kind==='pause',key=span?(hold?'pause:'+span.pause_id:'source:'+span.output_start):undefined,transition=lastSpan!==key;lastSpan=key;
  const source=sourceTime(cursor,spans);video.muted=hold||originalMute;
  // Do not chase a wall clock while a seek/decode is pending. Each join seeks once.
  if((force||transition)&&Math.abs(video.currentTime-source)>1e-5)video.currentTime=source;
  else if(hold&&!video.seeking&&Math.abs(video.currentTime-source)>1/120)video.currentTime=source;
  if(hold||!playing){if(!video.paused)video.pause()}else ensurePlaying();
  publish();
 }
 function tick(now:number){
  if(disposed||!playing)return;const span=active(),elapsed=Math.max(0,(now-last)/1000);last=now;
  if(span?.kind==='pause'&&!video.seeking&&(video.readyState===undefined||video.readyState>=2)){cursor=Math.min(span.output_end,cursor+Math.min(.1,elapsed))}
  else if(span&&span.kind!=='pause'&&!video.seeking&&(video.readyState===undefined||video.readyState>=2)){
   // Advance ordinary playback from decoded media, not elapsed wall time.
   if(video.currentTime>=span.end-1e-6||(video.ended&&video.currentTime>=span.end-1/30-.005))cursor=span.output_end;
   else if(video.currentTime>=span.start)cursor=Math.max(cursor,span.output_start+video.currentTime-span.start);
  }
  safely(()=>{sync();if(cursor>=end)stop();else if(playing)handle=clock.raf(tick)});
 }
 const engine={toggle(){if(disposed)return;safely(()=>{playing=!playing;if(playing&&cursor>=end){cursor=0;lastSpan=undefined}notify.onPlaying(playing);last=clock.now();sync();clock.caf(handle);if(playing)handle=clock.raf(tick)})},pause(){if(!disposed)safely(stop)},seek(output:number){if(disposed)return;safely(()=>{stop();cursor=Math.max(0,Math.min(end,Number.isFinite(output)?output:0));sync(true)})},position:()=>cursor,dispose(){if(disposed)return;disposed=true;stop();video.muted=originalMute}};
 safely(()=>sync(true));return engine;
}
