import {useState,type ReactNode} from 'react';
type Props={actions?:ReactNode;children:ReactNode;onInspectorHost:(node:HTMLElement|null)=>void;hasSelection:boolean};
export default function EditorWorkspace({actions,children,onInspectorHost,hasSelection}:Props){
 const [list,setList]=useState(false),[properties,setProperties]=useState(false);
 return <div className={`editor-grid assembly-workspace compact-workspace ${list?'show-list':''} ${properties?'show-properties':''}`}><nav className="workspace-tools"><button className="secondary" onClick={()=>setList(v=>!v)}>{list?'Ẩn':'Mở'} bài học / phụ đề</button><button className="secondary" onClick={()=>setProperties(v=>!v)}>{properties?'Ẩn':'Mở'} thuộc tính</button>{actions}</nav>{children}<aside className="properties-panel panel"><div className="panel-title">THUỘC TÍNH</div>{!hasSelection&&<p className="cut-help">Chọn bài học, phụ đề hoặc điểm cắt để chỉnh sửa.</p>}<div ref={onInspectorHost}/></aside></div>;
}
