import React,{useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {usePausePlayback,type PlaybackController} from './pause_playback';
import {fitPreview} from './preview_size';
import {PreviewRequests} from './preview_requests';
import {configurePreviewAudio,resumePreviewAudio,releasePreviewAudio} from './audio_volume';
import {keepSpans,sourceTime} from './output_timeline';
import {defaultFrame,type VideoFrame} from './editing';
type Scene={sequence:number;width:number;height:number;geometry:{speaker:number[];radius:number;speaker_radius?:number;circle?:boolean};speaker_transform:{left:number;top:number;width:number;height:number};page:string;subtitle:string|null;subtitle_rect:number[]|null;source:{file:string;state:string;message?:string}};
type Props={controllerRef:React.RefObject<PlaybackController|null>;seekRequest:{time:number;seq:number}|null;onOutputTime:(t:number)=>void;initialOutput:number;project:any;plan:any;options:any;videoRef:React.RefObject<HTMLVideoElement|null>;busy:boolean;dirty:boolean;onTime:(time:number)=>void;onPlay:(playing:boolean)=>void;onPrepare:()=>void;onSizeChange:(size:number)=>void;onLayoutChange:(layout:'classic'|'circle')=>void;onFrameChange:(key:string,frame:VideoFrame)=>void};
const media=(id:string,path:string)=>`/api/projects/${id}/media/${path.split('/').map(encodeURIComponent).join('/')}`;
const at=(items:any[],time:number)=>items.find(i=>i.start<=time&&i.end>time);

export default function LivePreview({controllerRef,seekRequest,onOutputTime,initialOutput,project,plan,options,videoRef,busy,dirty,onTime,onPlay,onPrepare,onFrameChange,onSizeChange,onLayoutChange}:Props){
 const initialSpans=keepSpans(project.metadata.duration,plan.cuts,plan.pauses||[]);
 const initialSource=sourceTime(initialOutput,initialSpans);
 const stageRef=useRef<HTMLDivElement>(null);
 const [stageSize,setStageSize]=useState({width:0,height:0});
 useLayoutEffect(()=>{const el=stageRef.current;if(!el)return;const observer=new ResizeObserver(entries=>{const rect=entries[0].contentRect;setStageSize({width:rect.width,height:rect.height})});observer.observe(el);return()=>observer.disconnect()},[]);
 const [scene,setScene]=useState<Scene|null>(null),[error,setError]=useState(''),[time,setTime]=useState(initialSource),[playing,setPlaying]=useState(false);
 const [audioStatus,setAudioStatus]=useState(''),[audioError,setAudioError]=useState('');
 const timeRef=useRef(initialSource),autoAttempt=useRef(''),lastRequestCue=useRef(''),appliedSeek=useRef<number|null>(null);
 const drag=useRef<{px:number;py:number;width:number;height:number;frame:VideoFrame}|null>(null);
 const assembly=keepSpans(project.metadata.duration,plan.cuts,plan.pauses||[]),hasPauses=!!plan.pauses?.length;
 const [outCursor,setOutCursor]=useState(initialOutput);
 const activePause=hasPauses&&assembly.find(s=>s.kind==='pause'&&outCursor>=s.output_start&&outCursor<s.output_end);
 usePausePlayback(videoRef,controllerRef,assembly,true,scene?.source.file,t=>{setOutCursor(t);onOutputTime(t)},t=>{timeRef.current=t;setTime(t);onTime(t)},p=>{setPlaying(p);onPlay(p)},setError,initialOutput);
 useEffect(()=>{if(seekRequest&&controllerRef.current&&appliedSeek.current!==seekRequest.seq){controllerRef.current.seek(seekRequest.time);appliedSeek.current=seekRequest.seq}},[seekRequest,scene?.source.file,JSON.stringify(plan.pauses),JSON.stringify(plan.cuts)]);
 const lesson=at(plan.lessons,time)||plan.lessons.at(-1),caption=activePause?null:at(plan.captions,time);
 const packet=JSON.stringify({lesson:lesson||{vi:'',en:'',chunks:[]},caption:caption?{vi:caption.vi,en:caption.en}:null,options});
 const requests=useMemo(()=>new PreviewRequests<Scene>(async(body,signal)=>{
  const r=await fetch(`/api/projects/${project.id}/preview-scene`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
  const result=await r.json();if(!r.ok)throw new Error(typeof result.detail==='string'?result.detail:'Nội dung chưa hợp lệ để xem trước.');return result;
 },result=>{setScene(result);setError('')},e=>setError((e as Error).message)),[project.id]);
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
 const assemblyDuration=assembly.at(-1)?.output_end||project.metadata.duration;
 const fitted=fitPreview(stageSize.width,stageSize.height,scene?.width||0,scene?.height||0);
 const g=scene?.geometry,s=g?.speaker,tr=scene?.speaker_transform;
 const frameKey=scene&&scene.height>scene.width?'9:16':'16:9';
 const contain=s?Math.min(s[2]/project.metadata.width,s[3]/project.metadata.height):1;
 const frame:VideoFrame=options.video_frames?.[frameKey]||(s&&tr?{zoom:tr.width/(project.metadata.width*contain),x:(tr.left-(s[2]-tr.width)/2)/s[2],y:(tr.top-(s[3]-tr.height)/2)/s[3]}:defaultFrame);
 function changeFrame(change:Partial<VideoFrame>){const next={...frame,...change};onFrameChange(frameKey,{zoom:Math.max(.25,Math.min(4,next.zoom)),x:Math.max(-1,Math.min(1,next.x)),y:Math.max(-1,Math.min(1,next.y))})}
 return <>
  <div className="live-stage" ref={stageRef}>
   {scene&&g&&s&&tr?<div className="live-surface" style={{width:fitted.width,height:fitted.height,visibility:fitted.width?'visible':'hidden'}}>
    <img className="live-page" src={scene.page} alt="Khung bài học đang chỉnh sửa"/>
    <div className="live-speaker draggable-video" title="Kéo để chỉnh vị trí video trong khung" onPointerDown={e=>{if(busy)return;e.currentTarget.setPointerCapture(e.pointerId);const r=e.currentTarget.getBoundingClientRect();drag.current={px:e.clientX,py:e.clientY,width:r.width,height:r.height,frame:{...frame}}}} onPointerMove={e=>{const d=drag.current;if(!d||busy)return;changeFrame({zoom:d.frame.zoom,x:Math.max(-1,Math.min(1,d.frame.x+(e.clientX-d.px)/d.width)),y:Math.max(-1,Math.min(1,d.frame.y+(e.clientY-d.py)/d.height))})}} onPointerUp={()=>{drag.current=null}} onPointerCancel={()=>{drag.current=null}} style={{left:`${s[0]/scene.width*100}%`,top:`${s[1]/scene.height*100}%`,width:`${s[2]/scene.width*100}%`,height:`${s[3]/scene.height*100}%`,borderRadius:`${(g.speaker_radius??g.radius)/s[2]*100}% / ${(g.speaker_radius??g.radius)/s[3]*100}%`,background: '#F7F3EB'}}>
     <video ref={videoRef} playsInline preload="auto" src={media(project.id,scene.source.file)} style={{left:`${tr.left/s[2]*100}%`,top:`${tr.top/s[3]*100}%`,width:`${tr.width/s[2]*100}%`,height:`${tr.height/s[3]*100}%`}} onLoadedMetadata={e=>{e.currentTarget.currentTime=Math.min(timeRef.current,project.metadata.duration)}} />
    </div>
    {!activePause&&scene.subtitle&&scene.subtitle_rect&&<img className="live-subtitle" alt="Phụ đề đang chỉnh sửa" src={scene.subtitle} style={{left:`${scene.subtitle_rect[0]/scene.width*100}%`,top:`${scene.subtitle_rect[1]/scene.height*100}%`,width:`${scene.subtitle_rect[2]/scene.width*100}%`,height:`${scene.subtitle_rect[3]/scene.height*100}%`}}/>}
   </div>:<span>Đang chuẩn bị khung xem trực tiếp…</span>}
  </div>
  <details className="frame-settings"><summary>Chỉnh khung, zoom và vị trí nhân vật</summary><fieldset disabled={busy||!scene} className="video-frame-controls">{frameKey==='16:9'&&<><label>Bố cục ngang<select value={options.landscape_layout||'classic'} onChange={e=>onLayoutChange(e.target.value as 'classic'|'circle')}><option value="circle">Ảnh trái · chữ phải · mặt tròn</option><option value="classic">Bố cục cũ</option></select></label>{g?.circle&&<label>Kích thước vòng tròn · {Math.round((options.speaker_size??.25)*100)}% chiều cao<input aria-label="Kích thước vòng tròn" type="range" min=".15" max=".4" step=".01" value={options.speaker_size??.25} onChange={e=>onSizeChange(Number(e.target.value))}/></label>}</>}<label>Zoom video trong khung · {Math.round(frame.zoom*100)}%<input aria-label="Zoom video trong khung" type="range" min=".25" max="4" step=".01" value={frame.zoom} onChange={e=>changeFrame({zoom:Number(e.target.value)})}/></label><label>Vị trí ngang<input aria-label="Vị trí video ngang" type="range" min="-1" max="1" step=".01" value={frame.x} onChange={e=>changeFrame({x:Number(e.target.value)})}/></label><label>Vị trí dọc<input aria-label="Vị trí video dọc" type="range" min="-1" max="1" step=".01" value={frame.y} onChange={e=>changeFrame({y:Number(e.target.value)})}/></label><button className="secondary" onClick={()=>onFrameChange(frameKey,{...defaultFrame})}>Đặt lại video</button><small>Kéo video để can vị trí · Toàn video · Lưu riêng khung {frameKey}</small></fieldset></details>
  <div className="live-controls"><button className="secondary" disabled={!scene} onClick={()=>controllerRef.current?.toggle()}>{playing?'Tạm dừng':'Phát'}</button><input aria-label="Tua bản xem trực tiếp" type="range" min="0" max={assemblyDuration} step=".033333" value={Math.min(outCursor,assemblyDuration)} onChange={e=>controllerRef.current?.seek(Number(e.target.value))}/></div>
  {audioStatus&&<p className="audio-status" role="status">{audioStatus}</p>}
  {audioError&&<p className="live-warning" role="alert">{audioError}</p>}
  {error&&<p className="live-warning" role="alert">{error} Khung đang giữ trạng thái hợp lệ gần nhất.</p>}
  {scene?.source.state==='pending'&&<p className="live-warning">{scene.source.message} <button className="text-button" disabled={busy||dirty} onClick={onPrepare}>{busy?'Đang cập nhật…':'Cập nhật người nói'}</button></p>}
 </>
}
