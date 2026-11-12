import test from 'node:test';import assert from 'node:assert/strict';import {spaceAction} from '../frontend/playback_shortcuts.ts';
const event={code:'Space',defaultPrevented:false,altKey:false,ctrlKey:false,metaKey:false,repeat:false};
test('Space toggles playback while repeat suppresses scrolling without retoggling',()=>{assert.equal(spaceAction(event,null),'toggle');assert.equal(spaceAction({...event,repeat:true},null),'suppress')});
test('Space stays available to typing fields, editable areas and modified shortcuts',()=>{
 assert.equal(spaceAction(event,{closest:()=>true}),'ignore');assert.equal(spaceAction(event,{closest:()=>false,isContentEditable:true}),'ignore');
 for(const field of ['altKey','ctrlKey','metaKey','defaultPrevented'])assert.equal(spaceAction({...event,[field]:true},null),'ignore');
 assert.equal(spaceAction({...event,code:'KeyA'},null),'ignore');
});
