import React, {useEffect, useState} from 'react';
import {Download, X} from 'lucide-react';
type Lesson={id:string;vi:string;en:string;asset_id:string|null};
type Asset={file:string;alt?:string};
export default function ThumbnailEditor({projectId,lessons,assets,selected,onClose}:{projectId:string;lessons:Lesson[];assets:Record<string,Asset>;selected:string;onClose:()=>void}){
 const initial=lessons.find(l=>l.id===selected)||lessons[0];
 const [lessonId,setLessonId]=useState(initial.id),[en,setEn]=useState(initial.en),[vi,setVi]=useState(initial.vi),[assetId,setAssetId]=useState(initial.asset_id||'');
 const [x,setX]=useState(.5),[y,setY]=useState(.5),[zoom,setZoom]=useState(1);
 const [preview,setPreview]=useState(''),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 function choose(id:string){const l=lessons.find(l=>l.id===id)!;setLessonId(id);setEn(l.en);setVi(l.vi);setAssetId(l.asset_id||'');setX(.5);setY(.5);setZoom(1)}
 useEffect(()=>{
  const controller=new AbortController();let url='';setLoading(true);setPreview('');setError('');
  const timer=setTimeout(async()=>{try{
   const response=await fetch(`/api/projects/${projectId}/thumbnail`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lesson_id:lessonId,en,vi,asset_id:assetId||null,crop:{x,y,zoom}}),signal:controller.signal});
   if(response.status===404||response.status===405)throw new Error('Máy chủ VietCut đang dùng phiên bản cũ. Hãy khởi động lại ứng dụng rồi tải lại trang (Ctrl + F5).');
   if(!response.ok){const data=await response.json();throw new Error(typeof data.detail==='string'?data.detail:'Nội dung không hợp lệ. Hãy kiểm tra chữ và ảnh.')}
   const blob=await response.blob();if(controller.signal.aborted)return;url=URL.createObjectURL(blob);setPreview(url);
  }catch(e){if(!controller.signal.aborted)setError((e as Error).message)}finally{if(!controller.signal.aborted)setLoading(false)}},200);
  return()=>{clearTimeout(timer);controller.abort();if(url)URL.revokeObjectURL(url)};
 },[projectId,lessonId,en,vi,assetId,x,y,zoom]);
 useEffect(()=>{const listener=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose()};window.addEventListener('keydown',listener);return()=>window.removeEventListener('keydown',listener)},[onClose]);
 return <div className="modal-backdrop"><section className="modal thumbnail-modal" role="dialog" aria-modal="true" aria-label="Xuất thumbnail"><div className="modal-heading"><div><h2>Xuất thumbnail</h2><p>Khung cố định · 1280 × 720 · Chỉ thay chữ và ảnh</p></div><button className="icon-button" onClick={onClose} aria-label="Đóng"><X/></button></div>
 <div className="thumbnail-preview" aria-live="polite">{preview?<img src={preview} alt="Xem trước thumbnail"/>:<p>{loading?'Đang tạo bản xem trước…':error}</p>}</div>
 <div className="thumbnail-fields"><label>Bài học<select value={lessonId} onChange={e=>choose(e.target.value)}>{lessons.map(l=><option key={l.id} value={l.id}>{l.vi}</option>)}</select></label><label>Ảnh minh hoạ<select value={assetId} onChange={e=>{setAssetId(e.target.value);setX(.5);setY(.5);setZoom(1)}}><option value="">Chọn ảnh trong dự án</option>{Object.entries(assets).map(([id,a])=><option key={id} value={id}>{a.alt||a.file}</option>)}</select></label><label>Tiếng Anh · chữ lớn<textarea value={en} maxLength={1000} onChange={e=>setEn(e.target.value)}/></label><label>Tiếng Việt · chữ nhỏ<textarea value={vi} maxLength={800} onChange={e=>setVi(e.target.value)}/></label></div>
 <div className="thumbnail-crop">{[['Ngang',x,setX,0,1],['Dọc',y,setY,0,1],['Phóng ảnh',zoom,setZoom,1,3]].map(([label,value,setter,min,max])=><label key={label as string}>{label as string}<input type="range" min={min as number} max={max as number} step="0.01" value={value as number} onChange={e=>(setter as (v:number)=>void)(Number(e.target.value))}/></label>)}<button className="secondary" onClick={()=>{setX(.5);setY(.5);setZoom(1)}}>Đặt lại ảnh</button></div>
 {error&&<p role="alert" className="thumbnail-error">{error}</p>}<div className="thumbnail-footer"><small>Chỉnh ở đây không thay đổi bài học hoặc video. Khung xanh pastel được dùng chung cho mọi video.</small>{preview&&!loading&&!error?<a className="primary" href={preview} download="vietnamese-with-vinh-thumbnail.png"><Download size={16}/> Tải PNG</a>:<button className="primary" disabled>Tải PNG</button>}</div></section></div>
}
