import test from 'node:test';import assert from 'node:assert/strict';import {currentPreview} from '../frontend/current_preview.ts';
test('matching exported assembly plays directly; dirty or outdated files never replace live edits',()=>{
 const exported={revision:4,file:'final.mp4'},preview={revision:4,file:'preview.mp4'};
 assert.equal(currentPreview(4,false,exported,preview),exported);
 assert.equal(currentPreview(4,true,exported,preview),null);
 assert.equal(currentPreview(5,false,exported,preview),null);
 assert.equal(currentPreview(4,false,{revision:3,file:'old.mp4'},preview),preview);
 assert.equal(currentPreview(undefined,false,exported,preview),null);
});
