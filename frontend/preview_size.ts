export function fitPreview(width:number,height:number,sceneWidth:number,sceneHeight:number){
 if(![width,height,sceneWidth,sceneHeight].every(v=>Number.isFinite(v)&&v>0))return {width:0,height:0};
 const scale=Math.min(width/sceneWidth,height/sceneHeight);
 return {width:sceneWidth*scale,height:sceneHeight*scale};
}
