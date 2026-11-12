export function spaceAction(event:{code:string;defaultPrevented:boolean;altKey:boolean;ctrlKey:boolean;metaKey:boolean;repeat:boolean},target:{closest:(selector:string)=>unknown;isContentEditable?:boolean}|null):'ignore'|'suppress'|'toggle'{
 if(event.code!=='Space'||event.defaultPrevented||event.altKey||event.ctrlKey||event.metaKey)return 'ignore';
 if(target?.isContentEditable||target?.closest('input,textarea,select,[contenteditable="true"],[contenteditable=""],[contenteditable="plaintext-only"],[role="textbox"]'))return 'ignore';
 return event.repeat?'suppress':'toggle';
}
