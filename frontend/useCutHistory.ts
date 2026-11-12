import {useRef,useState} from 'react';
export function useCutHistory<T>(){
 const past=useRef<T[]>([]),future=useRef<T[]>([]);const [version,update]=useState(0);
 return {version,canUndo:past.current.length>0,canRedo:future.current.length>0,
 reset(){past.current=[];future.current=[];update(v=>v+1)},
 record(current:T){past.current=[...past.current.slice(-99),structuredClone(current)];future.current=[];update(v=>v+1)},
 undo(current:T){const next=past.current.pop();if(!next)return null;future.current.push(structuredClone(current));update(v=>v+1);return next},
 redo(current:T){const next=future.current.pop();if(!next)return null;past.current.push(structuredClone(current));update(v=>v+1);return next}};
}
