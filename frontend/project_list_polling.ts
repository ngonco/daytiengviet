// Refresh the sidebar on every screen, without reopening the editor.
export function watchProjectList(load:(signal:AbortSignal)=>Promise<void>,clock={
 set:(fn:()=>void,ms:number)=>setTimeout(fn,ms),
 clear:(id:ReturnType<typeof setTimeout>)=>clearTimeout(id)
}){
 const controller=new AbortController();
 let timer:ReturnType<typeof setTimeout>;
 async function refresh(){
  try{await load(controller.signal)}catch{/* Keep the last successful list. */}
  finally{if(!controller.signal.aborted)timer=clock.set(refresh,2000)}
 }
 timer=clock.set(refresh,2000);
 return()=>{controller.abort();clock.clear(timer)};
}
