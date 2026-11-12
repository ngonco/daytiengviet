export function spaceAction(event:{code:string;defaultPrevented:boolean;altKey:boolean;ctrlKey:boolean;metaKey:boolean;repeat:boolean},target:{closest:(selector:string)=>unknown;isContentEditable?:boolean}|null):'ignore'|'suppress'|'toggle'{
 if(event.code!=='Space'||event.defaultPrevented||event.altKey||event.ctrlKey||event.metaKey)return 'ignore';
 if(target?.isContentEditable||target?.closest('input,textarea,select,[contenteditable="true"],[contenteditable=""],[contenteditable="plaintext-only"],[role="textbox"]'))return 'ignore';
 return event.repeat?'suppress':'toggle';
}

type DeleteEvent={key:string;defaultPrevented:boolean;altKey?:boolean;ctrlKey?:boolean;metaKey?:boolean;shiftKey?:boolean;repeat?:boolean};
type DeleteTarget={closest:(selector:string)=>unknown;isContentEditable?:boolean}|null;
export function deleteAction(event:DeleteEvent,target:DeleteTarget,hasSelection:boolean):'ignore'|'suppress'|'delete'{
 if(event.key!=='Delete'||event.defaultPrevented||event.altKey||event.ctrlKey||event.metaKey||event.shiftKey||!hasSelection)return 'ignore';
 if(target?.isContentEditable||target?.closest('input,textarea,select,[contenteditable="true"],[contenteditable=""],[contenteditable="plaintext-only"],[role="textbox"],[role="combobox"],dialog,[role="dialog"],.modal-backdrop'))return 'ignore';
 return event.repeat?'suppress':'delete';
}


type SilenceEvent=DeleteEvent&{code?:string;isComposing?:boolean};
export function silenceAction(event:SilenceEvent,target:DeleteTarget):'ignore'|'suppress'|'insert'{
 if(event.isComposing||(event.code?event.code!=='KeyI':event.key.toLowerCase()!=='i'))return 'ignore';
 // Share the same input/dialog/modifier/repeat protections as timeline deletion.
 const action=deleteAction({...event,key:'Delete'},target,true);
 return action==='delete'?'insert':action;
}
