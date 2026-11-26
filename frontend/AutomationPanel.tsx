import React, {useEffect,useState} from 'react';
import {FolderOpen,Play,Pause,RefreshCw,Youtube} from 'lucide-react';

type Item={hash:string;source:string;state:string;project_id?:string;output?:string;error?:string;message?:string;progress?:number;duplicate_paths?:string[]};
type Upload={id:string;scheduled_date:string;publish_hour:string;title:string;status:string;video_url?:string;project_id:string};
type Snapshot={config:{folder:string;enabled:boolean;remove_background?:boolean;auto_delete_days?:number;youtube_publish_hour?:string;message:string};items:Item[];counts:Record<string,number>};
const labels:Record<string,string>={waiting:'Đang chờ',running:'Đang dựng',retry_wait:'Chờ thử lại',done:'Đã dựng bản nháp',failed:'Chưa hoàn tất',needs_attention:'Cần kiểm tra cấu hình',cancelled:'Đã dừng'};
async function request(path:string,body?:unknown,method='POST'){
 const response=await fetch('/api/automation'+path,body===undefined?{method}:{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(!response.ok){const error=await response.json();throw new Error(typeof error.detail==='string'?error.detail:'Chưa hoàn tất thao tác.')}
 return response.json();
}
export default function AutomationPanel({onOpen}:{onOpen:(id:string)=>void}){
 const [data,setData]=useState<Snapshot|null>(null),[uploads,setUploads]=useState<Upload[]>([]),[folder,setFolder]=useState(''),[edited,setEdited]=useState(false),[pending,setPending]=useState(false),[error,setError]=useState(''),[ytNote,setYtNote]=useState('');
 useEffect(()=>{let disposed=false;const controller=new AbortController();async function refresh(){try{const [resAuto,resYt]=await Promise.all([fetch('/api/automation',{signal:controller.signal}),fetch('/api/youtube/uploads',{signal:controller.signal})]);if(!resAuto.ok)throw new Error('Không đọc được trạng thái tự động dựng. Hãy khởi động lại VietCut sau cập nhật.');const value=await resAuto.json();const yt=resYt.ok?await resYt.json():{uploads:[]};if(!disposed){setData(value);setUploads(yt.uploads||[])}}catch(e){if(!disposed)setError((e as Error).message)}}refresh();const timer=setInterval(refresh,2000);return()=>{disposed=true;controller.abort();clearInterval(timer)}},[]);
 useEffect(()=>{if(data&&!edited)setFolder(data.config.folder)},[data?.config.folder,edited]);
 async function act(fn:()=>Promise<void>){setPending(true);setError('');try{await fn();setData(await request('',undefined,'GET'))}catch(e){setError((e as Error).message)}finally{setPending(false)}}
 return <section className="automation-panel">
  <div className="eyebrow">TỪ SOURCE ĐẾN BẢN NHÁP · DUYỆT &amp; ĐĂNG YOUTUBE</div><h1>Tự động dựng</h1>
  <p>Chọn thư mục chứa video gốc. VietCut chỉ dựng bản nháp để bạn kiểm tra, chỉnh sửa rồi bấm <b>Duyệt &amp; Đăng</b> lên YouTube (mỗi ngày 1 video, chống đăng trùng).</p>
  {error&&<div className="error-banner" role="alert">{error}</div>}
  {ytNote&&<p role="status">{ytNote}</p>}
  <div className="panel automation-controls"><label>Thư mục nguồn<input value={folder} disabled={pending||data?.config.enabled} placeholder="Chọn thư mục hoặc nhập đường dẫn" onChange={e=>{setFolder(e.target.value);setEdited(true)}}/></label>
   <div className="field-row"><button className="secondary" disabled={pending||data?.config.enabled} onClick={()=>act(async()=>{const result=await request('/folder');if(result.folder){setFolder(result.folder);setEdited(false);await request('',{folder:result.folder},'PUT')}})}><FolderOpen size={16}/> Chọn thư mục</button>
   <button className="secondary" disabled={pending||!folder} onClick={()=>act(async()=>{await request('',{folder},'PUT');setEdited(false);await request('/scan')})}><RefreshCw size={16}/> Quét ngay</button>
   <button className="primary" disabled={pending||!folder} onClick={()=>act(async()=>{await request('',data?.config.enabled?{enabled:false}:{folder,enabled:true},'PUT');setEdited(false)})}>{data?.config.enabled?<><Pause size={16}/> Tạm dừng nhận nguồn</>:<><Play size={16}/> Bật tự động dựng</>}</button></div>
   <div className="field-row">
    <label>Giờ đăng YouTube (1 video/ngày)<input type="time" value={data?.config.youtube_publish_hour||'19:00'} disabled={pending||!data} onChange={e=>act(async()=>{await request('',{youtube_publish_hour:e.target.value},'PUT')})}/></label>
    <label>Tự động xoá dự án &amp; video gốc (ngày, 0 = tắt)<input type="number" min={0} max={365} value={data?.config.auto_delete_days??0} disabled={pending||!data} onChange={e=>act(async()=>{await request('',{auto_delete_days:Math.max(0,Math.min(365,Number(e.target.value)||0))},'PUT')})}/></label>
    <button className="secondary" disabled={pending} onClick={()=>act(async()=>{const r=await fetch('/api/youtube/login',{method:'POST'});const j=await r.json();setYtNote(j.message||'Đã mở YouTube Studio.')})}><Youtube size={16}/> Đăng nhập YouTube Studio</button>
   </div>
   <label className="check-label"><input type="checkbox" checked={!data?.config.remove_background} disabled={pending||!data} onChange={e=>act(async()=>{await request('',{remove_background:!e.target.checked},'PUT')})}/> Không xoá nền video</label>
   <p><b>Đến 90 giây: dọc 9:16 · Trên 90 giây: ngang 16:9</b><br/>Bản nháp sẵn sàng chỉnh sửa · Phụ đề Việt-Anh · {data?.config.remove_background?'Xoá nền bằng GPU':'Giữ nền video gốc'} · Tự cân âm lượng giọng nói</p>
   <small>Nhớ nguồn và lịch sử đã đăng YouTube theo hash nội dung kể cả khi dự án/video gốc đã bị xoá theo hạn ngày.</small>
   <p role="status">{pending?'Đang xử lý…':data?.config.message||'Chưa bật theo dõi.'}</p>
  </div>
  <div className="automation-counts">{['waiting','running','retry_wait','done','failed','needs_attention'].map(state=><span key={state}>{labels[state]} <b>{data?.counts[state]||0}</b></span>)}</div>
  <div className="panel automation-list">{!data?.items.length?<p>Nguồn mới xuất hiện tại đây sau khi file ổn định ít nhất 10 giây.</p>:data.items.map(item=><article key={item.hash}>
   <div className="automation-item-heading"><b>{item.source.split(/[\\/]/).pop()}</b><span>{labels[item.state]||item.state}</span></div><small className="automation-path">{item.source}</small>
   {item.state==='running'&&<><p>{item.message}</p><progress max={100} value={item.progress||0}/></>}
   {item.output&&<p className="automation-path">Lưu tại: {item.output}</p>}{!!item.duplicate_paths?.length&&<small>Đã bỏ qua {item.duplicate_paths.length} bản sao trùng nội dung.</small>}
   {item.error&&<p className="warning-note">{item.error}</p>}
   <div className="field-row">{item.project_id&&<button className="text-button" onClick={()=>onOpen(item.project_id!)}>Mở dự án</button>}{['failed','needs_attention','cancelled'].includes(item.state)&&<button className="secondary" disabled={pending} onClick={()=>act(async()=>{await request(`/items/${item.hash}/retry`)})}><RefreshCw size={14}/> Thử lại</button>}</div>
  </article>)}</div>
  {!!uploads.length&&<div className="panel automation-list"><h3>Lịch sử đã lên lịch / đăng YouTube ({uploads.length})</h3>{uploads.map(u=><article key={u.id}><div className="automation-item-heading"><b>{u.title}</b><span>Lịch: {u.scheduled_date} {u.publish_hour}</span></div><small>{u.status==='scheduled'?'Đã lên lịch':'Đã đăng'}{u.video_url?` · ${u.video_url}`:''}</small></article>)}</div>}
 </section>
}
