import {keepSpans,sourceTime,outputTime,type Span,type Pause,type Range} from './output_timeline';

export type TimelineEdit={cuts:(Range&{id:string;reason:string;locked:boolean})[];pauses:Pause[]};
// Match backend cut validation before the draft reaches preview or autosave.
export function normalizeTimelineEdit(edit:TimelineEdit):TimelineEdit{
 return {...edit,cuts:edit.cuts.map(c=>{const start=Math.ceil(c.start*30-1e-6)/30+0,end=Math.floor(c.end*30+1e-6)/30+0;if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start)throw new Error('\u0110o\u1ea1n c\u1eaft ph\u1ea3i d\u00e0i \u00edt nh\u1ea5t m\u1ed9t khung h\u00ecnh.');return {...c,start,end}})};
}
export function clampOutput(time:number,spans:Span[]){return Math.max(0,Math.min(spans.at(-1)?.output_end||0,Number.isFinite(time)?time:0))}
// Preserve a source frame, or the exact offset within the same inserted hold.
export function rebaseOutput(time:number,before:Span[],after:Span[]){
 const cursor=clampOutput(time,before),hold=before.find(s=>s.kind==='pause'&&cursor>=s.output_start&&cursor<s.output_end);
 if(hold){
  const next=after.find(s=>s.pause_id===hold.pause_id&&s.kind==='pause');
  if(next)return clampOutput(next.output_start+Math.min(cursor-hold.output_start,next.output_end-next.output_start),after);
  const following=before.find(s=>s.kind!=='pause'&&s.output_start>=hold.output_end-1e-8);
  return following?clampOutput(outputTime(following.start,after),after):after.at(-1)?.output_end||0;
 }
 if(cursor>0&&cursor>=(before.at(-1)?.output_end||0))return after.at(-1)?.output_end||0;
 return clampOutput(outputTime(sourceTime(cursor,before),after),after);
}
export function timelinePosition(duration:number,edit:TimelineEdit,position:number){
 const base=keepSpans(duration,edit.cuts);
 if(base.reduce((sum,s)=>sum+s.end-s.start,0)<Math.min(.5,duration)-1e-6)throw new Error('C\u1ea7n gi\u1eef l\u1ea1i \u00edt nh\u1ea5t n\u1eeda gi\u00e2y video.');
 if(edit.pauses.length>1000||edit.pauses.some(p=>!Number.isFinite(p.duration)||p.duration<1/30-1e-8||p.duration>600||!Number.isFinite(p.at)||p.at<0||p.at>duration)||edit.pauses.reduce((n,p)=>n+p.duration,0)>3600+1e-8)throw new Error('Kho\u1ea3ng im l\u1eb7ng v\u01b0\u1ee3t gi\u1edbi h\u1ea1n cho ph\u00e9p.');
 const spans=keepSpans(duration,edit.cuts,edit.pauses),output=clampOutput(position,spans);
 return {output,source:sourceTime(output,spans)};
}
export function resizePause(pauses:Pause[],id:string,seconds:number){
 if(!Number.isFinite(seconds)||seconds<=0||seconds>600)throw new Error('Th\u1eddi gian im l\u1eb7ng kh\u00f4ng h\u1ee3p l\u1ec7.');
 return pauses.map(p=>p.id===id?{...p,duration:Math.max(1/30,Math.round(seconds*30)/30)}:p);
}
