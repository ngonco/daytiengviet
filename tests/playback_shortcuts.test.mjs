import test from 'node:test';import assert from 'node:assert/strict';import {spaceAction} from '../frontend/playback_shortcuts.ts';
const event={code:'Space',defaultPrevented:false,altKey:false,ctrlKey:false,metaKey:false,repeat:false};
test('Space toggles playback while repeat suppresses scrolling without retoggling',()=>{assert.equal(spaceAction(event,null),'toggle');assert.equal(spaceAction({...event,repeat:true},null),'suppress')});
test('Space stays available to typing fields, editable areas and modified shortcuts',()=>{
 assert.equal(spaceAction(event,{closest:()=>true}),'ignore');assert.equal(spaceAction(event,{closest:()=>false,isContentEditable:true}),'ignore');
 for(const field of ['altKey','ctrlKey','metaKey','defaultPrevented'])assert.equal(spaceAction({...event,[field]:true},null),'ignore');
 assert.equal(spaceAction({...event,code:'KeyA'},null),'ignore');
});

const {deleteAction}=await import('../frontend/playback_shortcuts.ts');
test('Delete requires a selection and preserves typing, dialogs, modified keys and consumed events',()=>{
 const event={key:'Delete',defaultPrevented:false,repeat:false};assert.equal(deleteAction(event,null,true),'delete');assert.equal(deleteAction(event,null,false),'ignore');assert.equal(deleteAction({...event,repeat:true},null,true),'suppress');assert.equal(deleteAction(event,{closest:()=>true},true),'ignore');assert.equal(deleteAction(event,{closest:()=>false,isContentEditable:true},true),'ignore');
 for(const key of ['defaultPrevented','ctrlKey','metaKey','altKey','shiftKey'])assert.equal(deleteAction({...event,[key]:true},null,true),'ignore');assert.equal(deleteAction({...event,key:'Backspace'},null,true),'ignore');
});

const {silenceAction}=await import('../frontend/playback_shortcuts.ts');
test('I inserts silence once per press, preserves typing/IME/dialogs and does not hijack modified keys',()=>{
 const key={key:'i',code:'KeyI',defaultPrevented:false,repeat:false};assert.equal(silenceAction(key,null),'insert');assert.equal(silenceAction({...key,key:'I'},null),'insert');assert.equal(silenceAction({key:'i',defaultPrevented:false},null),'insert');assert.equal(silenceAction({...key,repeat:true},null),'suppress');
 for(const field of ['defaultPrevented','altKey','ctrlKey','metaKey','shiftKey','isComposing'])assert.equal(silenceAction({...key,[field]:true},null),'ignore');
 assert.equal(silenceAction(key,{closest:()=>true}),'ignore');assert.equal(silenceAction(key,{closest:()=>false,isContentEditable:true}),'ignore');assert.equal(silenceAction({...key,key:'o',code:'KeyO'},null),'ignore');
});
