import test from 'node:test';
import assert from 'node:assert/strict';
import {watchProjectList} from '../frontend/project_list_polling.ts';

function clock(){
 const pending=new Map();let next=0;
 return {pending,set(fn,ms){assert.equal(ms,2000);const id=++next;pending.set(id,fn);return id},clear(id){pending.delete(id)},tick(){const [id,fn]=pending.entries().next().value;pending.delete(id);return fn()}};
}
test('sidebar receives newly completed projects without overlapping requests',async()=>{
 const c=clock();let finish,calls=0,items=[];
 const stop=watchProjectList(async()=>{calls++;items=await new Promise(resolve=>finish=resolve)},c);
 const pending=c.tick();assert.equal(calls,1);assert.equal(c.pending.size,0);
 finish([{id:'new',title:'Cảm ơn',status:'ready'}]);await pending;
 assert.equal(items[0].title,'Cảm ơn');assert.equal(c.pending.size,1);stop();assert.equal(c.pending.size,0);
});
test('failed polling retries, cleanup aborts outstanding work and never reschedules',async()=>{
 const c=clock();let calls=0,signal,finish;
 const stop=watchProjectList(async s=>{signal=s;if(++calls===1)throw new Error('offline');await new Promise(resolve=>finish=resolve)},c);
 await c.tick();assert.equal(c.pending.size,1);
 const pending=c.tick();stop();assert.equal(signal.aborted,true);finish();await pending;assert.equal(c.pending.size,0);
});
