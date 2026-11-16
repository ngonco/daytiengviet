import React,{useEffect,useRef,useState} from 'react';
import {fitPreview} from './preview_size';

export type FrameGeometry={width:number;height:number;geometry:{photo:number[]}};
export function PhotoHotspot({style,disabled,onClick}:{style:React.CSSProperties;disabled:boolean;onClick:()=>void}){
 return <button type="button" className="photo-hotspot" style={style} disabled={disabled} aria-label="Đổi ảnh minh họa đang xem" title="Bấm để tìm và đổi ảnh minh họa" onClick={onClick}><span>Tìm và đổi ảnh</span></button>;
}

// Fit the server's photo rectangle to the native MP4's contain letterboxing.
export default function SavedPhotoHotspot({projectId,revision,disabled,onClick}:{projectId:string;revision:number;disabled:boolean;onClick:()=>void}){
 const host=useRef<HTMLDivElement>(null),[size,setSize]=useState({width:0,height:0}),[scene,setScene]=useState<FrameGeometry|null>(null);
 useEffect(()=>{const node=host.current;if(!node)return;const observer=new ResizeObserver(entries=>{const r=entries[0].contentRect;setSize({width:r.width,height:r.height})});observer.observe(node);return()=>observer.disconnect()},[]);
 useEffect(()=>{let disposed=false;const controller=new AbortController();setScene(null);fetch(`/api/projects/${projectId}/frame-geometry`,{signal:controller.signal}).then(async r=>{if(!r.ok)throw new Error();return r.json()}).then(value=>{if(!disposed)setScene(value)}).catch(()=>{});return()=>{disposed=true;controller.abort()}},[projectId,revision]);
 const fitted=fitPreview(size.width,size.height,scene?.width||0,scene?.height||0),p=scene?.geometry.photo;
 return <div className="saved-photo-overlay" ref={host}>{scene&&p&&fitted.width>0&&<PhotoHotspot disabled={disabled} onClick={onClick} style={{left:(size.width-fitted.width)/2+p[0]/scene.width*fitted.width,top:(size.height-fitted.height)/2+p[1]/scene.height*fitted.height,width:p[2]/scene.width*fitted.width,height:p[3]/scene.height*fitted.height}}/>}</div>;
}
