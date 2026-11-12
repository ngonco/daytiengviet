import type {ReactNode} from 'react';
type Props={children:ReactNode;onInspectorHost:(node:HTMLElement|null)=>void;hasSelection:boolean};
export default function EditorWorkspace({children,onInspectorHost,hasSelection}:Props){
 return <div className="editor-grid assembly-workspace">{children}<aside className="properties-panel panel"><div className="panel-title">THUỘC TÍNH</div>{!hasSelection&&<p className="cut-help">Chọn bài học, phụ đề hoặc điểm cắt để chỉnh sửa.</p>}<div ref={onInspectorHost}/></aside></div>;
}
