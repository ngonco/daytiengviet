import React,{useEffect,useRef,useState} from 'react';
import {keepSpans,sourceTime,outputTime,mapRange} from './output_timeline';
import {frameTime,manualCut,timelineTime} from './editing';
type Cut={id:string;start:number;end:number;enabled:boolean;reason:string};
type Clip={id:string;start:number;end:number;text:string;kind:'captions'|'visuals'|'lessons'};
type Props={duration:number;time:number;cuts:Cut[];clips:Clip[];disabled:boolean;playing:boolean;onSeek:(t:number)=>void;onSelect:(clip:Clip)=>void;onPlay:()=>void;onPreview:()=>void;onHistory:()=>void;onCut:(start:number,end:number)=>void;onToggle:(id:string,enabled:boolean)=>void;onUndo:()=>void;onRedo:()=>void;canUndo:boolean;canRedo:boolean;frames:{time:number;url:string}[];waveform:number[]};
const stamp=(t:number)=>`${Math.floor(t/60).toString().padStart(2,'0')}:${(t%60).toFixed(3).padStart(6,'0')}`;
export default function CutTimeline({duration:sourceDuration,time:sourceCurrent,cuts,clips:sourceClips,disabled,playing,onSeek:seekSource,onSelect:selectSource,onPlay,onPreview,onHistory,onCut:cutSource,onToggle,onUndo,onRedo,canUndo,canRedo,frames,waveform}:Props){
 const spans=keepSpans(sourceDuration,cuts),duration=spans.at(-1)?.output_end||sourceDuration,time=outputTime(sourceCurrent,spans);
 const clips=sourceClips.flatMap(c=>mapRange(c.start,c.end,spans).map((r,i)=>({...c,...r,id:c.id+'@'+i,sourceId:c.id})));
 const onSeek=(t:number)=>seekSource(sourceTime(t,spans));
 const onSelect=(c:typeof clips[number])=>selectSource({...c,id:c.sourceId,start:c.sourceStart,end:c.sourceEnd});
 const [splits,setSplits]=useState<number[]>([]);
 const onCut=(a:number,b:number)=>{const range=manualCut(a,b,duration,[]);cutSource(sourceTime(range.start,spans),sourceTime(range.end-1e-8,spans));setSplits([])};
 const boundaries=[0,...spans.slice(1).map(s=>s.output_start),...splits.map(t=>outputTime(t,spans)),duration].sort((a,b)=>a-b).filter((v,i,a)=>i===0||v-a[i-1]>1/60);

 const [zoom,setZoom]=useState(1),[start,setStart]=useState<number|null>(null),[end,setEnd]=useState<number|null>(null),[error,setError]=useState(''),[width,setWidth]=useState(900);
 const barCount=Math.min(1600,Math.max(40,Math.round(width*zoom/5)));
 const waveformBars=Array.from({length:barCount},(_,i)=>{const t=sourceTime(i/(barCount-1)*duration,spans);return waveform[Math.min(waveform.length-1,Math.floor(t/sourceDuration*waveform.length))]||0});
 useEffect(()=>{setStart(null);setEnd(null);setError('')},[JSON.stringify(cuts)]);
 const viewport=useRef<HTMLDivElement>(null),dragging=useRef(false);
 useEffect(()=>{const el=viewport.current;if(!el)return;const observer=new ResizeObserver(()=>setWidth(el.clientWidth));observer.observe(el);return()=>observer.disconnect()},[]);
 useEffect(()=>{const el=viewport.current;if(el)el.scrollLeft=Math.max(0,time/duration*el.clientWidth*zoom-el.clientWidth/2)},[zoom]);
 const secondsPerTick=duration/Math.max(1,width*zoom/100);
 const step=[1/30,.1,.25,.5,1,2,5,10,15,30,60,120,300,600].find(v=>v>=secondsPerTick)||900;
 const ticks=Array.from({length:Math.floor(duration/step)+1},(_,i)=>i*step);
 const tracks=([['captions','Lời thoại'],['visuals','Minh hoạ'],['lessons','Bài học']] as const).filter(([kind])=>clips.some(c=>c.kind===kind));
 function seek(e:React.PointerEvent<HTMLDivElement>){const rect=e.currentTarget.getBoundingClientRect();onSeek(timelineTime(e.clientX,rect.left,rect.width,duration))}
 function cut(){if(start===null||end===null)return;try{const c=manualCut(start,end,duration,[]);onCut(c.start,c.end);setStart(null);setEnd(null);setError('')}catch(e){setError((e as Error).message)}}
 return <section className="timeline-panel panel manual-timeline">
  <div className="cut-timeline-heading"><b>Timeline bản dựng</b><span className="mono">{stamp(time)} / {stamp(duration)}</span></div>
  <div className="cut-tools">
   <button className="secondary" disabled={disabled} onClick={onPlay}>{playing?'Tạm dừng':'Phát'}</button>
   <button className="secondary" disabled={disabled||!canUndo} onClick={onUndo}>Hoàn tác</button><button className="secondary" disabled={disabled||!canRedo} onClick={onRedo}>Làm lại</button>
   <button className="secondary" disabled={disabled||time<=0||time>=duration} onClick={()=>setSplits(v=>[...v,sourceTime(frameTime(time,duration),spans)])}>Tách tại đầu phát</button>
   <button className="secondary" onClick={()=>onSeek(frameTime(time-1/30,duration))}>−1 khung</button><button className="secondary" onClick={()=>onSeek(frameTime(time+1/30,duration))}>+1 khung</button>
   <label>Zoom {zoom.toFixed(1)}×<input aria-label="Zoom timeline" type="range" min="0" max="8" step=".1" value={Math.log2(zoom)} onChange={e=>setZoom(2**Number(e.target.value))}/></label>
   <button className="secondary" onClick={()=>setZoom(1)}>Vừa toàn bộ</button><button className="secondary" onClick={onHistory}>Phiên bản</button><button className="secondary" onClick={onPreview}>Xem từ đầu</button>
  </div>
  <div className="cut-timeline-scroll" ref={viewport}>
   <div className="cut-timeline-canvas" style={{width:`${zoom*100}%`,height:202+tracks.length*38}} role="slider" tabIndex={0} aria-label="Vị trí trên timeline nguồn" aria-valuemin={0} aria-valuemax={duration} aria-valuenow={time} aria-valuetext={stamp(time)} onKeyDown={e=>{if((e.key==='Delete'||e.key==='Backspace')&&!disabled){e.preventDefault();cut();return}if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();onSeek(frameTime(time+(e.key==='ArrowRight'?1:-1)*(e.shiftKey?1:1/30),duration))}}} onPointerDown={e=>{if(e.button!==0)return;e.currentTarget.setPointerCapture(e.pointerId);dragging.current=true;seek(e)}} onPointerMove={e=>{if(dragging.current)seek(e)}} onPointerUp={()=>{dragging.current=false}} onPointerCancel={()=>{dragging.current=false}}>
    <div className="cut-ruler">{ticks.map(t=><span key={t} style={{left:`${t/duration*100}%`}}>{stamp(t)}</span>)}</div>
    <div className="cut-source-track assembly-track">{boundaries.slice(0,-1).map((a,i)=>{const b=boundaries[i+1],source=sourceTime((a+b)/2,spans),thumb=frames.length?frames.reduce((best,f)=>Math.abs(f.time-source)<Math.abs(best.time-source)?f:best):null;return <button key={i} className="assembly-clip" style={{left:`${a/duration*100}%`,width:`${(b-a)/duration*100}%`,backgroundImage:thumb?`url("${thumb.url}")`:undefined}} title="Chọn đoạn để bỏ" onPointerDown={e=>e.stopPropagation()} onClick={()=>{setStart(a);setEnd(b);onSeek(a)}}><span>Đoạn {i+1}</span></button>})}</div>
    <div className="assembly-waveform" aria-label="Sóng âm bản dựng">{waveformBars.map((v,i)=><i key={i} style={{height:`${Math.max(3,v*100)}%`}}/>)}</div>
    {tracks.map(([kind,label])=><div className={`cut-cue-track ${kind}`} key={kind} aria-label={label}><span>{label}</span>{clips.filter(c=>c.kind===kind).map(c=><button key={c.id} title={c.text} style={{left:`${c.start/duration*100}%`,width:`${(c.end-c.start)/duration*100}%`}} onPointerDown={e=>e.stopPropagation()} onClick={()=>onSelect(c)}>{c.text}</button>)}</div>)}
    {start!==null&&end!==null&&end>start&&<div className="cut-selection" style={{left:`${start/duration*100}%`,width:`${(end-start)/duration*100}%`}}>{(['start','end'] as const).map(edge=><button key={edge} className={`selection-handle ${edge}`} aria-label={edge==='start'?'Kéo đầu đoạn':'Kéo cuối đoạn'} onPointerDown={e=>{e.stopPropagation();e.currentTarget.setPointerCapture(e.pointerId)}} onPointerMove={e=>{if(!e.currentTarget.hasPointerCapture(e.pointerId))return;const r=e.currentTarget.closest('.cut-timeline-canvas')!.getBoundingClientRect();const t=timelineTime(e.clientX,r.left,r.width,duration);if(edge==='start')setStart(Math.min(t,end-1/30));else setEnd(Math.max(t,start+1/30))}} onPointerUp={e=>{e.stopPropagation();e.currentTarget.releasePointerCapture(e.pointerId)}}/>)}</div>}
    {[['Đầu',start],['Cuối',end]].map(([label,t])=>t!==null&&<span className="cut-boundary" key={label} style={{left:`${Number(t)/duration*100}%`}}>{label}</span>)}
    <div className="playhead" style={{left:`${Math.min(100,time/duration*100)}%`}}/>
   </div>
  </div>
  <fieldset disabled={disabled} className="cut-markers"><label>Đầu (giây)<input aria-label="Điểm đầu cắt" type="number" min="0" max={duration} step=".033333333" value={start===null?'':Number(start.toFixed(6))} onChange={e=>setStart(e.target.value===''?null:Number(e.target.value))}/><button className="secondary" onClick={()=>{setStart(frameTime(time,duration));setError('')}}>Đánh dấu đầu</button></label><label>Cuối (giây)<input aria-label="Điểm cuối cắt" type="number" min="0" max={duration} step=".033333333" value={end===null?'':Number(end.toFixed(6))} onChange={e=>setEnd(e.target.value===''?null:Number(e.target.value))}/><button className="secondary" onClick={()=>{setEnd(frameTime(time,duration));setError('')}}>Đánh dấu cuối</button></label><button className="primary" disabled={disabled||start===null||end===null} onClick={cut}>Cắt bỏ đoạn</button><button className="secondary" onClick={()=>{setStart(null);setEnd(null);setError('')}}>Bỏ đánh dấu</button></fieldset>
  {error&&<p role="alert" className="warning-note">{error}</p>}
  <p className="cut-help">Tách tại đầu phát rồi chọn đoạn để bỏ, hoặc đánh dấu đầu/cuối. Các đoạn còn lại tự nối liền. Phím ← →: từng khung hình; Shift + ← →: một giây. Kéo mép vùng chọn để chỉnh điểm cắt. Lưu trước khi xuất.</p>
  <div className="manual-cut-list">{cuts.map(c=><label className="check-label" key={c.id}><input type="checkbox" disabled={disabled} checked={c.enabled} onChange={e=>onToggle(c.id,e.target.checked)}/><span>{stamp(c.start)} – {stamp(c.end)} · {c.enabled?'Bỏ đoạn':'Đã khôi phục'}</span></label>)}</div>
 </section>
}
