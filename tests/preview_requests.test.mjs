import test from 'node:test';
import assert from 'node:assert/strict';
import {PreviewRequests} from '../frontend/preview_requests.ts';
const tick=ms=>new Promise(resolve=>setTimeout(resolve,ms));

test('rapid typing coalesces into one request with the latest text',async()=>{
 const sent=[],accepted=[];
 const queue=new PreviewRequests(async body=>{sent.push(body);return body},r=>accepted.push(r),e=>{throw e});
 for(let i=0;i<30;i++)queue.update({text:'latest-'+i},15);
 await tick(45);assert.equal(sent.length,1);assert.equal(accepted[0].text,'latest-29');queue.dispose();
});

test('an old response that ignores cancellation cannot overwrite a newer frame',async()=>{
 const pending=[],accepted=[];
 const queue=new PreviewRequests(body=>new Promise(resolve=>pending.push({body,resolve})),r=>accepted.push(r),e=>{throw e});
 queue.update({text:'old'},0);await tick(10);
 queue.update({text:'new'},0);await tick(10);
 pending[1].resolve(pending[1].body);await tick(0);pending[0].resolve(pending[0].body);await tick(0);
 assert.deepEqual(accepted.map(x=>x.text),['new']);queue.dispose();
});

test('unmount/dispose cancels pending edits and suppresses late errors',async()=>{
 let sent=0,errors=0;const queue=new PreviewRequests(async()=>{sent++;throw new Error('late')},()=>{},()=>{errors++});
 queue.update({text:'discard'},20);queue.dispose();await tick(35);assert.equal(sent,0);assert.equal(errors,0);
 let reject;const running=new PreviewRequests(()=>new Promise((a,b)=>{reject=b}),()=>{},()=>{errors++});
 running.update({},0);await tick(5);running.dispose();reject(new Error('late'));await tick(0);assert.equal(errors,0);
});
