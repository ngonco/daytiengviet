import React, {useEffect,useState} from 'react';
import {FolderOpen,Play,Pause,RefreshCw} from 'lucide-react';

type Item={hash:string;source:string;state:string;project_id?:string;output?:string;error?:string;message?:string;progress?:number;duplicate_paths?:string[]};
type Snapshot={config:{folder:string;enabled:boolean;remove_background?:boolean;message:string};items:Item[];counts:Record<string,number>};
const labels:Record<string,string>={waiting:'Đang chờ',running:'Đang dựng',retry_wait:'Chờ thử lại',done:'Đã hoàn tất',failed:'Chưa hoàn tất',needs_attention:'Cần kiểm tra cấu hình',cancelled:'Đã dừng'};
async function request(path:string,body?:unknown,method='POST'){
 const response=await fetch('/api/automation'+path,body===undefined?{method}:{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(!response.ok){const error=await response.json();throw new Error(typeof error.detail==='string'?error.detail:'Chưa hoàn tất thao tác.')}
 return response.json();
}
export default function AutomationPanel({onOpen}:{onOpen:(id:string)=>void}){
 const [data,setData]=useState<Snapshot|null>(null),[folder,setFolder]=useState(''),[edited,setEdited]=useState(false),[pending,setPending]=useState(false),[error,setError]=useState('');
 useEffect(()=>{let disposed=false;const controller=new AbortController();async function refresh(){try{const response=await fetch('/api/automation',{signal:controller.signal});if(!response.ok)throw new Error('Không đọc được trạng thái tự động dựng. Hãy khởi động lại VietCut sau cập nhật.');const value=await response.json();if(!disposed)setData(value)}catch(e){if(!disposed)setError((e as Error).message)}}refresh();const timer=setInterval(refresh,2000);return()=>{disposed=true;controller.abort();clearInterval(timer)}},[]);
 useEffect(()=>{if(data&&!edited)setFolder(data.config.folder)},[data?.config.folder,edited]);
 async function act(fn:()=>Promise<void>){setPending(true);setError('');try{await fn();setData(await request('',undefined,'GET'))}catch(e){setError((e as Error).message)}finally{setPending(false)}}
 return <section className="automation-panel">
  <div className="eyebrow">TỪ SOURCE ĐẾN VIDEO HOÀN CHỈNH</div><h1>Tự động dựng</h1>
  <p>Chọn thư mục chứa video gốc. VietCut tìm cả thư mục con, dựng nguồn chưa xử lý và lưu video hoàn chỉnh cạnh source.</p>
  {error&&<div className="error-banner" role="alert">{error}</div>}
  <div className="panel automation-controls"><label>Thư mục nguồn<input value={folder} disabled={pending||data?.config.enabled} placeholder="Chọn thư mục hoặc nhập đường dẫn" onChange={e=>{setFolder(e.target.value);setEdited(true)}}/></label>
   <div className="field-row"><button className="secondary" disabled={pending||data?.config.enabled} onClick={()=>act(async()=>{const result=await request('/folder');if(result.folder){setFolder(result.folder);setEdited(false);await request('',{folder:result.folder},'PUT')}})}><FolderOpen size={16}/> Chọn thư mục</button>
   <button className="secondary" disabled={pending||!folder} onClick={()=>act(async()=>{await request('',{folder},'PUT');setEdited(false);await request('/scan')})}><RefreshCw size={16}/> Quét ngay</button>
   <button className="primary" disabled={pending||!folder} onClick={()=>act(async()=>{await request('',data?.config.enabled?{enabled:false}:{folder,enabled:true},'PUT');setEdited(false)})}>{data?.config.enabled?<><Pause size={16}/> Tạm dừng nhận nguồn</>:<><Play size={16}/> Bật tự động dựng</>}</button></div>
   <label className="check-label"><input type="checkbox" checked={!data?.config.remove_background} disabled={pending||!data} onChange={e=>act(async()=>{await request('',{remove_background:!e.target.checked},'PUT')})}/> Không xoá nền video</label>
   <p><b>Đến 90 giây: dọc 9:16 · Trên 90 giây: ngang 16:9</b><br/>Full HD · Phụ đề Việt-Anh · {data?.config.remove_background?'Xoá nền bằng GPU':'Giữ nền video gốc'} · Tự cân âm lượng giọng nói</p><small>Cài đặt nền áp dụng cho dự án tạo tiếp theo. Mở dự án đã hoàn tất để cắt thủ công, zoom video và xuất bản mới cạnh nguồn.</small>
   <small>Nhớ nguồn theo nội dung dù đổi tên hoặc chuyển thư mục. Chỉ nhận file đã chép ổn định. Tạm dừng vẫn để video đang dựng hoàn tất. Giữ VietCut chạy để tiếp tục theo dõi.</small>
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
 </section>
}
