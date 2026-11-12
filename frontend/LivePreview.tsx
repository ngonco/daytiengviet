import React,{useEffect,useMemo,useRef,useState} from 'react';
import {PreviewRequests} from './preview_requests';
import {configurePreviewAudio,resumePreviewAudio,releasePreviewAudio} from './audio_volume';
import {keepSpans,sourceTime,outputTime} from './output_timeline';
import {defaultFrame,type VideoFrame} from './editing';
type Scene={sequence:number;width:number;height:number;geometry:{speaker:number[];radius:number;speaker_radius?:number;circle?:boolean};speaker_transform:{left:number;top:number;width:number;height:number};page:string;subtitle:string|null;subtitle_rect:number[]|null;source:{file:string;state:string;message?:string}};
type Props={initialTime:number;project:any;plan:any;options:any;videoRef:React.RefObject<HTMLVideoElement|null>;busy:boolean;dirty:boolean;onTime:(time:number)=>void;onPlay:(playing:boolean)=>void;onPrepare:()=>void;onSizeChange:(size:number)=>void;onLayoutChange:(layout:'classic'|'circle')=>void;onFrameChange:(key:string,frame:VideoFrame)=>void};
const media=(id:string,path:string)=>`/api/projects/${id}/media/${path.split('/').map(encodeURIComponent).join('/')}`;
const at=(items:any[],time:number)=>items.find(i=>i.start<=time&&i.end>time);

export default function LivePreview({initialTime,project,plan,options,videoRef,busy,dirty,onTime,onPlay,onPrepare,onFrameChange,onSizeChange,onLayoutChange}:Props){
 const initialSpans=keepSpans(project.metadata.duration,plan.cuts);
 const initialSource=sourceTime(outputTime(initialTime,initialSpans),initialSpans);
 const [scene,setScene]=useState<Scene|null>(null),[error,setError]=useState(''),[time,setTime]=useState(initialSource),[playing,setPlaying]=useState(false);
 const [audioStatus,setAudioStatus]=useState(''),[audioError,setAudioError]=useState('');
 const timeRef=useRef(initialSource),autoAttempt=useRef(''),cueRef=useRef(''),lastRequestCue=useRef('');
 const drag=useRef<{px:number;py:number;width:number;height:number;frame:VideoFrame}|null>(null);
 const lesson=at(plan.lessons,time)||plan.lessons.at(-1),caption=at(plan.captions,time);
 const packet=JSON.stringify({lesson:lesson||{vi:'',en:'',chunks:[]},caption:caption?{vi:caption.vi,en:caption.en}:null,options});
 const requests=useMemo(()=>new PreviewRequests<Scene>(async(body,signal)=>{
  const r=await fetch(`/api/projects/${project.id}/preview-scene`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
  const result=await r.json();if(!r.ok)throw new Error(typeof result.detail==='string'?result.detail:'Nội dung chưa hợp lệ để xem trước.');return result;
 },result=>{setScene(result);setError('')},e=>setError((e as Error).message)),[project.id]);
 const cuts=useMemo(()=>plan.cuts.filter((c:any)=>c.enabled).sort((a:any,b:any)=>a.start-b.start),[plan.cuts]);
 useEffect(()=>{setTime(initialSource);timeRef.current=initialSource;setScene(null);autoAttempt.current=''},[project.id]);
 useEffect(()=>{
  const cue=(lesson?.id||'')+'/'+(caption?.id||'');
  requests.update(JSON.parse(packet),cue!==lastRequestCue.current?0:100);lastRequestCue.current=cue;
 },[packet,project.id,project.matting?.code]);
 useEffect(()=>()=>requests.dispose(),[requests]);
 useEffect(()=>{
  const video=videoRef.current;if(!video||!scene)return;
  const enabled=options.auto_volume!==false;let disposed=false;const controller=new AbortController();
  configurePreviewAudio(video,enabled);setAudioError('');setAudioStatus(enabled?'Đang tự cân âm lượng giọng nói…':'Đang nghe âm lượng gốc.');
  const play=()=>{resumePreviewAudio(video).catch(()=>{if(!disposed)setAudioError('Chưa tăng được âm lượng trong trình duyệt. File xuất vẫn được cân âm tự động.')})};
  video.addEventListener('play',play);
  if(enabled)fetch(`/api/projects/${project.id}/audio-level`,{signal:controller.signal}).then(async response=>{
   if(!response.ok)throw new Error('Chưa đo được âm lượng. Thử tải lại trang; file xuất vẫn được cân âm tự động.');
   return response.json();
  }).then(level=>{if(!disposed){configurePreviewAudio(video,true,level.gain_db);setAudioStatus(level.silent?'Nguồn hiện không có tiếng nói rõ để tăng âm.':'Đã tự cân âm lượng giọng nói khi xem trực tiếp.');if(!video.paused)play()}}).catch(e=>{if(!disposed)setAudioError((e as Error).message)});
  return()=>{disposed=true;controller.abort();video.removeEventListener('play',play);releasePreviewAudio(video)};
 },[scene?.source.file,project.id,options.auto_volume]);
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
   if(next!==t&&!video!.paused){video!.currentTime=Math.min(next,project.metadata.duration);t=next}
   timeRef.current=t;
   const cue=(at(plan.lessons,t)?.id||'')+'/'+(at(plan.captions,t)?.id||'');
   if(cue!==cueRef.current){cueRef.current=cue;setTime(t)}
  }
  function frame(){if(cancelled)return;check(video!.currentTime);handle=requestAnimationFrame(frame)}
  handle=requestAnimationFrame(frame);return()=>{cancelled=true;cancelAnimationFrame(handle)}
 },[scene?.source.file,project.id,plan.lessons,plan.captions,cuts]);
 function seek(value:number){if(videoRef.current){videoRef.current.currentTime=value;timeRef.current=value;setTime(value);onTime(value)}}
 const assembly=keepSpans(project.metadata.duration,plan.cuts),assemblyDuration=assembly.at(-1)?.output_end||project.metadata.duration;
 const g=scene?.geometry,s=g?.speaker,tr=scene?.speaker_transform;
 const frameKey=scene&&scene.height>scene.width?'9:16':'16:9';
 const contain=s?Math.min(s[2]/project.metadata.width,s[3]/project.metadata.height):1;
 const frame:VideoFrame=options.video_frames?.[frameKey]||(s&&tr?{zoom:tr.width/(project.metadata.width*contain),x:(tr.left-(s[2]-tr.width)/2)/s[2],y:(tr.top-(s[3]-tr.height)/2)/s[3]}:defaultFrame);
 function changeFrame(change:Partial<VideoFrame>){const next={...frame,...change};onFrameChange(frameKey,{zoom:Math.max(.25,Math.min(4,next.zoom)),x:Math.max(-1,Math.min(1,next.x)),y:Math.max(-1,Math.min(1,next.y))})}
 return <>
  <div className="live-stage">
   {scene&&g&&s&&tr?<div className="live-surface" style={{aspectRatio:`${scene.width}/${scene.height}`,width:scene.width>scene.height?'100%':'auto',height:scene.width>scene.height?'auto':'100%'}}>
    <img className="live-page" src={scene.page} alt="Khung bài học đang chỉnh sửa"/>
    <div className="live-speaker draggable-video" title="Kéo để chỉnh vị trí video trong khung" onPointerDown={e=>{if(busy)return;e.currentTarget.setPointerCapture(e.pointerId);const r=e.currentTarget.getBoundingClientRect();drag.current={px:e.clientX,py:e.clientY,width:r.width,height:r.height,frame:{...frame}}}} onPointerMove={e=>{const d=drag.current;if(!d||busy)return;changeFrame({zoom:d.frame.zoom,x:Math.max(-1,Math.min(1,d.frame.x+(e.clientX-d.px)/d.width)),y:Math.max(-1,Math.min(1,d.frame.y+(e.clientY-d.py)/d.height))})}} onPointerUp={()=>{drag.current=null}} onPointerCancel={()=>{drag.current=null}} style={{left:`${s[0]/scene.width*100}%`,top:`${s[1]/scene.height*100}%`,width:`${s[2]/scene.width*100}%`,height:`${s[3]/scene.height*100}%`,borderRadius:`${(g.speaker_radius??g.radius)/s[2]*100}% / ${(g.speaker_radius??g.radius)/s[3]*100}%`,background: '#F7F3EB'}}>
     <video ref={videoRef} playsInline preload="auto" src={media(project.id,scene.source.file)} style={{left:`${tr.left/s[2]*100}%`,top:`${tr.top/s[3]*100}%`,width:`${tr.width/s[2]*100}%`,height:`${tr.height/s[3]*100}%`}} onLoadedMetadata={e=>{e.currentTarget.currentTime=Math.min(timeRef.current,project.metadata.duration)}} onTimeUpdate={e=>{const t=e.currentTarget.currentTime;timeRef.current=t;setTime(t);onTime(t)}} onPlay={()=>{setPlaying(true);onPlay(true)}} onPause={()=>{setPlaying(false);onPlay(false)}}/>
    </div>
    {scene.subtitle&&scene.subtitle_rect&&<img className="live-subtitle" alt="Phụ đề đang chỉnh sửa" src={scene.subtitle} style={{left:`${scene.subtitle_rect[0]/scene.width*100}%`,top:`${scene.subtitle_rect[1]/scene.height*100}%`,width:`${scene.subtitle_rect[2]/scene.width*100}%`,height:`${scene.subtitle_rect[3]/scene.height*100}%`}}/>}
   </div>:<span>Đang chuẩn bị khung xem trực tiếp…</span>}
  </div>
  <fieldset disabled={busy||!scene} className="video-frame-controls">{frameKey==='16:9'&&<><label>Bố cục ngang<select value={options.landscape_layout||'classic'} onChange={e=>onLayoutChange(e.target.value as 'classic'|'circle')}><option value="circle">Ảnh trái · chữ phải · mặt tròn</option><option value="classic">Bố cục cũ</option></select></label>{g?.circle&&<label>Kích thước vòng tròn · {Math.round((options.speaker_size??.25)*100)}% chiều cao<input aria-label="Kích thước vòng tròn" type="range" min=".15" max=".4" step=".01" value={options.speaker_size??.25} onChange={e=>onSizeChange(Number(e.target.value))}/></label>}</>}<label>Zoom video trong khung · {Math.round(frame.zoom*100)}%<input aria-label="Zoom video trong khung" type="range" min=".25" max="4" step=".01" value={frame.zoom} onChange={e=>changeFrame({zoom:Number(e.target.value)})}/></label><label>Vị trí ngang<input aria-label="Vị trí video ngang" type="range" min="-1" max="1" step=".01" value={frame.x} onChange={e=>changeFrame({x:Number(e.target.value)})}/></label><label>Vị trí dọc<input aria-label="Vị trí video dọc" type="range" min="-1" max="1" step=".01" value={frame.y} onChange={e=>changeFrame({y:Number(e.target.value)})}/></label><button className="secondary" onClick={()=>onFrameChange(frameKey,{...defaultFrame})}>Đặt lại video</button><small>Kéo video để can vị trí · Toàn video · Lưu riêng khung {frameKey}</small></fieldset>
  <div className="live-controls"><button className="secondary" disabled={!scene} onClick={()=>{const v=videoRef.current;if(v){if(v.paused)v.play().catch(e=>setError(e.message));else v.pause()}}}>{playing?'Tạm dừng':'Phát'}</button><input aria-label="Tua bản xem trực tiếp" type="range" min="0" max={assemblyDuration} step=".033333" value={Math.min(outputTime(time,assembly),assemblyDuration)} onChange={e=>seek(sourceTime(Number(e.target.value),assembly))}/></div>
  {audioStatus&&<p className="audio-status" role="status">{audioStatus}</p>}
  {audioError&&<p className="live-warning" role="alert">{audioError}</p>}
  {error&&<p className="live-warning" role="alert">{error} Khung đang giữ trạng thái hợp lệ gần nhất.</p>}
  {scene?.source.state==='pending'&&<p className="live-warning">{scene.source.message} <button className="text-button" disabled={busy||dirty} onClick={onPrepare}>{busy?'Đang cập nhật…':'Cập nhật người nói'}</button></p>}
 </>
}
