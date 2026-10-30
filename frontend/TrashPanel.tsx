import React,{useEffect,useState} from 'react';
type Item={id:string;title:string;created_at?:string;deleted_at:string;purge_after:string;state:string};
export default function TrashPanel({onRestored}:{onRestored:(id:string)=>Promise<void>}){
 const [items,setItems]=useState<Item[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState('');
 async function load(){const r=await fetch('/api/trash');if(!r.ok)throw new Error('Chưa đọc được Thùng rác.');setItems(await r.json())}
 useEffect(()=>{load().catch(e=>setError(e.message))},[]);
 async function restore(id:string){setBusy(id);setError('');try{const r=await fetch(`/api/trash/${id}/restore`,{method:'POST'});const body=await r.json();if(!r.ok)throw new Error(body.detail);await onRestored(id);await load()}catch(e){setError((e as Error).message)}finally{setBusy('')}}
 const date=(s:string)=>new Date(s).toLocaleString('vi-VN');
 return <section className="trash-page"><div className="eyebrow">QUẢN LÝ DUNG LƯỢNG</div><h1>Thùng rác</h1><p>App giữ tối đa 30 dự án hoạt động. Dự án có ngày tạo cũ nhất được giữ ở đây 7 ngày trước khi xóa hẳn. Video gốc và bản xuất ở ngoài thư mục dự án được giữ nguyên.</p>{error&&<p role="alert" className="live-warning">{error}</p>}{!items.length&&<div className="panel trash-empty">Thùng rác đang trống.</div>}{items.map(p=><div className="panel trash-row" key={p.id}><div><b>{p.title}</b><small>Đã chuyển: {date(p.deleted_at)}<br/>Hạn khôi phục: {date(p.purge_after)}</small></div><button className="secondary" disabled={!!busy||p.state!=='trashed'} onClick={()=>restore(p.id)}>{busy===p.id?'Đang khôi phục…':'Khôi phục'}</button></div>)}</section>
}
