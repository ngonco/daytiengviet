import React,{useEffect,useMemo,useRef,useState} from 'react';
import {PreviewRequests} from './preview_requests';
type Scene={sequence:number;width:number;height:number;geometry:{speaker:number[];radius:number};speaker_transform:{left:number;top:number;width:number;height:number};page:string;subtitle:string|null;subtitle_rect:number[]|null;source:{file:string;state:string;message?:string}};
type Props={project:any;plan:any;options:any;videoRef:React.RefObject<HTMLVideoElement|null>;busy:boolean;dirty:boolean;onTime:(time:number)=>void;onPlay:(playing:boolean)=>void;onPrepare:()=>void};
const media=(id:string,path:string)=>`/api/projects/${id}/media/${path.split('/').map(encodeURIComponent).join('/')}`;
const at=(items:any[],time:number)=>items.find(i=>i.start<=time&&i.end>time);

export default function LivePreview({project,plan,options,videoRef,busy,dirty,onTime,onPlay,onPrepare}:Props){
 const [scene,setScene]=useState<Scene|null>(null),[error,setError]=useState(''),[time,setTime]=useState(0),[playing,setPlaying]=useState(false);
 const timeRef=useRef(0),autoAttempt=useRef(''),cueRef=useRef(''),lastRequestCue=useRef('');
 const lesson=at(plan.lessons,time)||plan.lessons.at(-1),caption=at(plan.captions,time);
 const packet=JSON.stringify({lesson:lesson||{vi:'',en:'',chunks:[]},caption:caption?{vi:caption.vi,en:caption.en}:null,options});
 const requests=useMemo(()=>new PreviewRequests<Scene>(async(body,signal)=>{
  const r=await fetch(`/api/projects/${project.id}/preview-scene`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
  const result=await r.json();if(!r.ok)throw new Error(typeof result.detail==='string'?result.detail:'Nội dung chưa hợp lệ để xem trước.');return result;
 },result=>{setScene(result);setError('')},e=>setError((e as Error).message)),[project.id]);
 const cuts=useMemo(()=>plan.cuts.filter((c:any)=>c.enabled).sort((a:any,b:any)=>a.start-b.start),[plan.cuts]);
 useEffect(()=>{setTime(0);timeRef.current=0;setScene(null);autoAttempt.current=''},[project.id]);
 useEffect(()=>{
  const cue=(lesson?.id||'')+'/'+(caption?.id||'');
  requests.update(JSON.parse(packet),cue!==lastRequestCue.current?0:100);lastRequestCue.current=cue;
 },[packet,project.id,project.matting?.code]);
 useEffect(()=>()=>requests.dispose(),[requests]);
 useEffect(()=>{
  const key=project.id+'-'+project.revision;
  if(scene?.source.state==='pending'&&!busy&&!dirty&&autoAttempt.current!==key){autoAttempt.current=key;onPrepare()}
 },[scene?.source.state,busy,dirty,project.id,project.revision]);
 useEffect(()=>{
  const video=videoRef.current;if(!video||!scene)return;
  let cancelled=false,handle:number;
  function check(t:number){
   let next=t;
   for(const c of cuts){if(next>=c.start&&next<c.end)next=c.end}
   if(next!==t){video!.currentTime=Math.min(next,project.metadata.duration);t=next}
   timeRef.current=t;
   const cue=(at(plan.lessons,t)?.id||'')+'/'+(at(plan.captions,t)?.id||'');
   if(cue!==cueRef.current){cueRef.current=cue;setTime(t)}
  }
  function frame(){if(cancelled)return;check(video!.currentTime);handle=requestAnimationFrame(frame)}
  handle=requestAnimationFrame(frame);return()=>{cancelled=true;cancelAnimationFrame(handle)}
 },[scene?.source.file,project.id,plan.lessons,plan.captions,cuts]);
 function seek(value:number){if(videoRef.current){videoRef.current.currentTime=value;timeRef.current=value;setTime(value);onTime(value)}}
 const g=scene?.geometry,s=g?.speaker,tr=scene?.speaker_transform;
 return <>
  <div className="live-stage">
   {scene&&g&&s&&tr?<div className="live-surface" style={{aspectRatio:`${scene.width}/${scene.height}`,width:scene.width>scene.height?'100%':'auto',height:scene.width>scene.height?'auto':'100%'}}>
    <img className="live-page" src={scene.page} alt="Khung bài học đang chỉnh sửa"/>
    <div className="live-speaker" style={{left:`${s[0]/scene.width*100}%`,top:`${s[1]/scene.height*100}%`,width:`${s[2]/scene.width*100}%`,height:`${s[3]/scene.height*100}%`,borderRadius:`${g.radius/s[2]*100}% / ${g.radius/s[3]*100}%`,background: '#F7F3EB'}}>
     <video ref={videoRef} playsInline preload="auto" src={media(project.id,scene.source.file)} style={{left:`${tr.left/s[2]*100}%`,top:`${tr.top/s[3]*100}%`,width:`${tr.width/s[2]*100}%`,height:`${tr.height/s[3]*100}%`}} onLoadedMetadata={e=>{e.currentTarget.currentTime=Math.min(timeRef.current,project.metadata.duration)}} onTimeUpdate={e=>{const t=e.currentTarget.currentTime;timeRef.current=t;setTime(t);onTime(t)}} onPlay={()=>{setPlaying(true);onPlay(true)}} onPause={()=>{setPlaying(false);onPlay(false)}}/>
    </div>
    {scene.subtitle&&scene.subtitle_rect&&<img className="live-subtitle" alt="Phụ đề đang chỉnh sửa" src={scene.subtitle} style={{left:`${scene.subtitle_rect[0]/scene.width*100}%`,top:`${scene.subtitle_rect[1]/scene.height*100}%`,width:`${scene.subtitle_rect[2]/scene.width*100}%`,height:`${scene.subtitle_rect[3]/scene.height*100}%`}}/>}
   </div>:<span>Đang chuẩn bị khung xem trực tiếp…</span>}
  </div>
  <div className="live-controls"><button className="secondary" disabled={!scene} onClick={()=>{const v=videoRef.current;if(v){if(v.paused)v.play().catch(e=>setError(e.message));else v.pause()}}}>{playing?'Tạm dừng':'Phát'}</button><input aria-label="Tua bản xem trực tiếp" type="range" min="0" max={project.metadata.duration} step=".033333" value={Math.min(time,project.metadata.duration)} onChange={e=>seek(Number(e.target.value))}/></div>
  {error&&<p className="live-warning" role="alert">{error} Khung đang giữ trạng thái hợp lệ gần nhất.</p>}
  {scene?.source.state==='pending'&&<p className="live-warning">{scene.source.message} <button className="text-button" disabled={busy||dirty} onClick={onPrepare}>{busy?'Đang cập nhật…':'Cập nhật người nói'}</button></p>}
 </>
}
