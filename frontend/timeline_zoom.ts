// Normalize mouse-wheel and trackpad deltas without changing the page zoom.
export function wheelTimelineZoom(zoom:number,delta:number,mode=0,pageHeight=800){
 if(!Number.isFinite(delta))return zoom;
 const pixels=delta*(mode===1?16:mode===2?pageHeight:1);
 return Math.max(1,Math.min(256,zoom*2**(-Math.max(-240,Math.min(240,pixels))/300)));
}
export function anchoredScroll(ratio:number,pointer:number,width:number,zoom:number){
 return Math.max(0,Math.min(width*(zoom-1),ratio*width*zoom-pointer));
}
