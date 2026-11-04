import test from 'node:test';
import assert from 'node:assert/strict';
import {gainValue,configurePreviewAudio,resumePreviewAudio,releasePreviewAudio} from '../frontend/audio_volume.ts';

function fake(){
 const values=[];let sources=0,resumes=0,closes=0;
 const context={currentTime:0,state:'suspended',destination:{},createGain:()=>({gain:{cancelScheduledValues(){},setTargetAtTime(v){values.push(v)}},connect(){}}),createMediaElementSource(){sources++;return {connect(){}}},async resume(){resumes++;this.state='running'},async close(){closes++;this.state='closed'}};
 return {context,values,get sources(){return sources},get resumes(){return resumes},get closes(){return closes}};
}
test('gain is finite, bounded and can amplify quiet input above native volume=1',()=>{
 assert.equal(gainValue(20),10);assert.equal(gainValue(NaN),1);assert.equal(gainValue(Infinity),1);assert.equal(gainValue(100),gainValue(48));
});
test('play creates one media source and option changes never multiply processing',async()=>{
 const video={isConnected:true},f=fake();configurePreviewAudio(video,true,20);
 assert.equal(f.sources,0);await resumePreviewAudio(video,()=>f.context);assert.equal(f.sources,1);assert.equal(f.resumes,1);assert.equal(f.values.at(-1),10);
 configurePreviewAudio(video,false);await resumePreviewAudio(video,()=>f.context);assert.equal(f.values.at(-1),1);
 configurePreviewAudio(video,true,6);await resumePreviewAudio(video,()=>f.context);assert.equal(f.sources,1);assert.ok(f.values.at(-1)>1.99);
 releasePreviewAudio(video);await Promise.resolve();assert.equal(f.closes,0);assert.equal(f.values.at(-1),1);
 video.isConnected=false;releasePreviewAudio(video);await Promise.resolve();assert.equal(f.closes,1);
});
test('disabled live monitoring leaves native audio intact without opening a context',async()=>{
 const video={isConnected:true};configurePreviewAudio(video,false);await resumePreviewAudio(video,()=>{throw new Error('should not create a context')});
});
