export type Span={start:number;end:number;output_start:number;output_end:number};
export type Range={start:number;end:number;enabled:boolean};
// Mirror backend.timeline.keep_spans. Source times remain the persisted contract.
export function keepSpans(duration:number,cuts:Range[]):Span[]{
 const merged:{start:number;end:number}[]=[];
 for(const c of cuts.filter(c=>c.enabled).map(c=>({start:Math.max(0,c.start),end:Math.min(duration,c.end)})).sort((a,b)=>a.start-b.start)){
  if(c.end<=c.start)continue;const last=merged.at(-1);
  if(last&&c.start<=last.end)last.end=Math.max(last.end,c.end);else merged.push({...c});
 }
 const spans:Span[]=[];let cursor=0,out=0;
 for(const c of [...merged,{start:duration,end:duration}]){
  if(c.start>cursor+.001){spans.push({start:cursor,end:c.start,output_start:out,output_end:out+c.start-cursor});out+=c.start-cursor;}
  cursor=Math.max(cursor,c.end);
 }return spans;
}
export function sourceTime(output:number,spans:Span[]){const s=spans.find(s=>output>=s.output_start&&output<s.output_end);return s?s.start+output-s.output_start:spans.at(-1)?.end||0;}
export function outputTime(source:number,spans:Span[]){const s=spans.find(s=>source>=s.start&&source<=s.end);return s?s.output_start+source-s.start:spans.find(s=>s.start>source)?.output_start??spans.at(-1)?.output_end??0;}
export function mapRange(start:number,end:number,spans:Span[]){return spans.flatMap(s=>{const a=Math.max(start,s.start),b=Math.min(end,s.end);return b>a+.005?[{start:s.output_start+a-s.start,end:s.output_start+b-s.start,sourceStart:a,sourceEnd:b}]:[];});}
