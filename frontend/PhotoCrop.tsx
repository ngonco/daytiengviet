import React,{useEffect,useRef,useState} from 'react';
export type Crop={x:number;y:number;zoom:number};
export const centerCrop:Crop={x:.5,y:.5,zoom:1};
type Geometry={frame_width:number;frame_height:number;scaled_width:number;scaled_height:number;overflow_x:number;overflow_y:number;crop_key:string};
type Props={projectId:string;assetId:string;file:string;ratio:string;value:Crop;disabled:boolean;onChange:(crop:Crop)=>void};

export default function PhotoCrop({projectId,assetId,file,ratio,value,disabled,onChange}:Props){
 const [geometry,setGeometry]=useState<Geometry|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 const drag=useRef<{x:number;y:number;crop:Crop;w:number;h:number}|null>(null);
 useEffect(()=>{const abort=new AbortController();setLoading(true);setError('');fetch(`/api/projects/${projectId}/photo-layout?asset_id=${encodeURIComponent(assetId)}&ratio=${encodeURIComponent(ratio)}&zoom=${value.zoom}`,{signal:abort.signal}).then(async r=>{if(!r.ok)throw new Error('Chưa đọc được ảnh để căn khung.');return r.json()}).then(g=>{setGeometry(g);setLoading(false)}).catch(e=>{if(e.name!=='AbortError'){setError(e.message);setLoading(false)}});return()=>abort.abort()},[projectId,assetId,ratio,value.zoom]);
 const g=geometry;
 return <div className="photo-crop"><div className="inspector-title"><b>Căn ảnh · {ratio==='original'?'tỷ lệ gốc':ratio}</b><button className="text-button" disabled={disabled} onClick={()=>onChange({...centerCrop})}>Đặt lại</button></div>
 {error&&<p role="alert" className="warning-note">{error}</p>}
 {g&&<div className={`photo-crop-stage ${loading?'loading':''}`} aria-label="Kéo ảnh để căn khung" style={{aspectRatio:`${g.frame_width}/${g.frame_height}`}} onPointerDown={e=>{if(disabled||loading)return;const r=e.currentTarget.getBoundingClientRect();drag.current={x:e.clientX,y:e.clientY,crop:{...value},w:r.width,h:r.height};e.currentTarget.setPointerCapture(e.pointerId)}} onPointerMove={e=>{const d=drag.current;if(!d||disabled)return;const clamp=(n:number)=>Math.max(0,Math.min(1,n));onChange({...value,x:g.overflow_x?clamp(d.crop.x-(e.clientX-d.x)/d.w*g.frame_width/g.overflow_x):value.x,y:g.overflow_y?clamp(d.crop.y-(e.clientY-d.y)/d.h*g.frame_height/g.overflow_y):value.y})}} onPointerUp={()=>{drag.current=null}} onPointerCancel={()=>{drag.current=null}}><img draggable={false} alt="Ảnh minh họa phủ kín vùng xuất" src={`/api/projects/${projectId}/media/assets/${encodeURIComponent(file)}`} style={{position:'absolute',maxWidth:'none',width:`${g.scaled_width/g.frame_width*100}%`,height:`${g.scaled_height/g.frame_height*100}%`,left:`${-g.overflow_x*value.x/g.frame_width*100}%`,top:`${-g.overflow_y*value.y/g.frame_height*100}%`}}/></div>}
 <small>{loading?'Đang cập nhật khung ảnh…':'Kéo ảnh để giữ phần quan trọng trong khung.'}</small>
 <label>Phóng ảnh · {value.zoom.toFixed(2)}×<input aria-label="Phóng ảnh minh họa" disabled={disabled} type="range" min="1" max="3" step=".05" value={value.zoom} onChange={e=>onChange({...value,zoom:Number(e.target.value)})}/></label>
 <div className="field-row"><label>Vị trí ngang<input aria-label="Vị trí ảnh ngang" type="range" min="0" max="1" step=".01" value={value.x} disabled={disabled||!g?.overflow_x} onChange={e=>onChange({...value,x:Number(e.target.value)})}/></label><label>Vị trí dọc<input aria-label="Vị trí ảnh dọc" type="range" min="0" max="1" step=".01" value={value.y} disabled={disabled||!g?.overflow_y} onChange={e=>onChange({...value,y:Number(e.target.value)})}/></label></div>
 </div>
}
