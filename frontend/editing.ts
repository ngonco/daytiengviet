export type VideoFrame={zoom:number;x:number;y:number};
export type CutRange={start:number;end:number;enabled:boolean};
export const defaultFrame:VideoFrame={zoom:1,x:0,y:0};
export const frameTime=(time:number,duration:number)=>Math.max(0,Math.min(duration,Math.round(time*30)/30));
export function timelineTime(clientX:number,left:number,width:number,duration:number){
 return frameTime((clientX-left)/Math.max(1,width)*duration,duration);
}
export function manualCut(start:number,end:number,duration:number,cuts:CutRange[]){
 const a=Math.ceil(start*30-1e-6)/30+0,b=Math.floor(end*30+1e-6)/30+0;
 if(!Number.isFinite(a)||!Number.isFinite(b)||a<0||b>duration||b-a<1/30-1e-6)throw new Error('Chọn điểm cuối sau điểm đầu ít nhất một khung hình.');
 const intervals=[...cuts.filter(c=>c.enabled),{start:a,end:b}].sort((x,y)=>x.start-y.start);
 let cursor=0,removed=0;
 for(const c of intervals){const end=Math.min(duration,c.end);removed+=Math.max(0,end-Math.max(cursor,c.start));cursor=Math.max(cursor,end)}
 if(duration-removed<Math.min(.5,duration)-1e-6)throw new Error('Cần giữ lại ít nhất nửa giây video.');
 return {start:a,end:b};
}
