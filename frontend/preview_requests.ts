/** Coalesce edits and ignore obsolete responses, including servers that finish after abort. */
export class PreviewRequests<T>{
 private version=0;
 private timer:ReturnType<typeof setTimeout>|undefined;
 private controller:AbortController|undefined;
 private send:(body:unknown,signal:AbortSignal)=>Promise<T>;
 private accept:(result:T)=>void;
 private reject:(error:unknown)=>void;
 constructor(send:(body:unknown,signal:AbortSignal)=>Promise<T>,accept:(result:T)=>void,reject:(error:unknown)=>void){this.send=send;this.accept=accept;this.reject=reject}
 update(body:Record<string,unknown>,delay=100){
  const id=++this.version;
  if(this.timer)clearTimeout(this.timer);
  this.controller?.abort();const controller=new AbortController();this.controller=controller;
  this.timer=setTimeout(async()=>{
   try{const result=await this.send({...body,sequence:id},controller.signal);if(id===this.version&&!controller.signal.aborted)this.accept(result)}
   catch(error){if(id===this.version&&!controller.signal.aborted)this.reject(error)}
  },delay);
 }
 dispose(){++this.version;if(this.timer)clearTimeout(this.timer);this.controller?.abort()}
}
