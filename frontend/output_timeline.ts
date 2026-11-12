export type Span={start:number;end:number;output_start:number;output_end:number;kind?:'pause';pause_id?:string};
export type Range={start:number;end:number;enabled:boolean};
// Mirror backend.timeline.keep_spans. Source times remain the persisted contract.
export type Pause={id:string;at:number;duration:number};
export function keepSpans(duration:number,cuts:Range[],pauses:Pause[]=[]):Span[]{
 const merged:{start:number;end:number}[]=[];
 for(const c of cuts.filter(c=>c.enabled).map(c=>({start:Math.max(0,c.start),end:Math.min(duration,c.end)})).sort((a,b)=>a.start-b.start)){
  if(c.end<=c.start)continue;const last=merged.at(-1);
  if(last&&c.start<=last.end)last.end=Math.max(last.end,c.end);else merged.push({...c});
 }
 const spans:Span[]=[];let cursor=0,out=0;
 for(const c of [...merged,{start:duration,end:duration}]){
  if(c.start>cursor+.001){const end=out+(c.start-cursor);spans.push({start:cursor,end:c.start,output_start:out,output_end:end});out=end;}
  cursor=Math.max(cursor,c.end);
 }
 if(!pauses.length)return spans;
 const total=spans.at(-1)?.output_end||0,events=new Map<number,Pause[]>();
 for(const p of pauses){const t=outputTime(p.at,spans);events.set(t,[...(events.get(t)||[]),p])}
 const points=[...new Set([0,total,...events.keys(),...spans.flatMap(s=>[s.output_start,s.output_end])])].sort((a,b)=>a-b);
 const result:Span[]=[];let cursorOut=0;
 for(let i=0;i<points.length;i++){
  const point=points[i];
  for(const p of (events.get(point)||[]).sort((a,b)=>a.id<b.id?-1:a.id>b.id?1:0)){const freeze=sourceTime(Math.max(0,point-1/30),spans);result.push({start:freeze,end:freeze,output_start:cursorOut,output_end:cursorOut+p.duration,kind:'pause',pause_id:p.id});cursorOut+=p.duration}
  const next=points[i+1];if(next!==undefined&&next-point>1e-8){const source=sourceTime(point,spans),length=next-point,end=cursorOut+length;result.push({start:source,end:source+length,output_start:cursorOut,output_end:end});cursorOut=end}
 }return result;
}
// Older saved/server maps may contain sub-frame holes. An internal hole belongs
// to the following span; only an actual output end maps to the source tail.
export function spanAt(output:number,spans:Span[]){
 const time=Number.isFinite(output)?output:0;
 return spans.find(s=>time<s.output_end);
}
export function sourceTime(output:number,spans:Span[]){const time=Number.isFinite(output)?output:0,s=spanAt(time,spans);return s?(s.kind==='pause'?s.start:s.start+Math.max(0,time-s.output_start)):spans.at(-1)?.end||0;}
export function outputTime(source:number,spans:Span[]){const s=spans.find(s=>source>=s.start&&source<=s.end);return s?s.output_start+(source-s.start):spans.find(s=>s.start>source)?.output_start??spans.at(-1)?.output_end??0;}
export function mapRange(start:number,end:number,spans:Span[]){return spans.flatMap(s=>{const a=Math.max(start,s.start),b=Math.min(end,s.end);return b>a+.005?[{start:s.output_start+(a-s.start),end:s.output_start+(b-s.start),sourceStart:a,sourceEnd:b}]:[];});}

export function insertPause(pauses:Pause[],at:number,seconds=2,sourceDuration=Infinity):Pause[]{
 if(!Number.isFinite(at)||at<0||!Number.isFinite(seconds)||seconds<=0)throw new Error('Thời gian chèn không hợp lệ.');
 const anchor=at>=sourceDuration-1e-6?sourceDuration:Math.min(sourceDuration,Math.round(at*30)/30),amount=Math.max(1/30,Math.round(seconds*30)/30);
 const found=pauses.find(p=>Math.abs(p.at-anchor)<1/60);
 if((found?.duration||0)+amount>600||pauses.reduce((s,p)=>s+p.duration,0)+amount>3600)throw new Error('Tối đa 600 giây mỗi vị trí và 60 phút tổng thời gian chèn.');
 return found?pauses.map(p=>p.id===found.id?{...p,duration:Math.round((p.duration+amount)*30)/30}:p):[...pauses,{id:'pause-'+crypto.randomUUID(),at:anchor,duration:amount}];
}
export function removeOutputRange(duration:number,cuts:(Range&{id:string;reason:string;locked:boolean})[],pauses:Pause[],a:number,b:number){
 if(!Number.isFinite(a)||!Number.isFinite(b)||b<=a)throw new Error('Chọn đoạn cần bỏ.');
 const spans=keepSpans(duration,cuts,pauses),removed=new Map<string,number>(),additions:typeof cuts=[];
 for(const s of spans){const left=Math.max(a,s.output_start),right=Math.min(b,s.output_end);if(right<=left)continue;
  if(s.kind==='pause')removed.set(s.pause_id!,right-left);
  else additions.push({id:'manual-'+crypto.randomUUID(),start:Math.ceil((s.start+left-s.output_start)*30-1e-6)/30,end:Math.floor((s.start+right-s.output_start)*30+1e-6)/30,enabled:true,locked:true,reason:'Đoạn cắt thủ công'});
 }
 const nextCuts=[...cuts,...additions.filter(c=>c.end>c.start)];
 if(keepSpans(duration,nextCuts).reduce((n,s)=>n+s.end-s.start,0)<Math.min(.5,duration)-1e-6)throw new Error('Cần giữ ít nhất nửa giây video nguồn.');
 return {cuts:nextCuts,pauses:pauses.map(p=>({...p,duration:Math.round((p.duration-(removed.get(p.id)||0))*30)/30})).filter(p=>p.duration>0)};
}
