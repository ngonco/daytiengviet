// Drive real App timeline callbacks across native/live view changes without real projects.
import test from 'node:test';import assert from 'node:assert/strict';import {registerHooks} from 'node:module';import {readFileSync,existsSync} from 'node:fs';import {fileURLToPath} from 'node:url';import ts from 'typescript';
const fakeReact='data:text/javascript,'+encodeURIComponent(`export default {};export const useState=(v)=>globalThis.__appHooks.state(v),useRef=(v)=>globalThis.__appHooks.ref(v),useEffect=(fn,deps)=>globalThis.__appHooks.effect(fn,deps),useLayoutEffect=()=>{},useMemo=(fn)=>fn(),useCallback=(fn)=>fn;`);
const namedStates=context=>root=>{
 function visit(node){
  if(ts.isVariableDeclaration(node)&&ts.isArrayBindingPattern(node.name)&&ts.isCallExpression(node.initializer)&&ts.isIdentifier(node.initializer.expression)&&node.initializer.expression.text==='useState'){
   const name=node.name.elements[0].name.text;
   return ts.factory.updateVariableDeclaration(node,node.name,node.exclamationToken,node.type,ts.factory.createCallExpression(ts.factory.createPropertyAccessExpression(ts.factory.createPropertyAccessExpression(ts.factory.createIdentifier('globalThis'),'__appHooks'),'namedState'),undefined,[ts.factory.createStringLiteral(name),...node.initializer.arguments]));
  }
  return ts.visitEachChild(node,visit,context);
 }return ts.visitNode(root,visit);
};
registerHooks({resolve(specifier,context,next){
 if(specifier==='react'&&context.parentURL?.includes('/frontend/'))return {url:fakeReact,shortCircuit:true};
 if(specifier.endsWith('.css'))return {url:'data:text/javascript,export default {}',shortCircuit:true};
 if(specifier.startsWith('./')&&context.parentURL?.includes('/frontend/'))for(const suffix of ['.ts','.tsx']){const url=new URL(specifier+suffix,context.parentURL);if(existsSync(fileURLToPath(url)))return {url:url.href,shortCircuit:true}}return next(specifier,context);
},load(url,context,next){
 if(url.includes('/frontend/')&&url.endsWith('.tsx')){
  let source=readFileSync(fileURLToPath(url),'utf8');const app=url.endsWith('/src.tsx');if(app)source=source.replace('function App(){','export function App(){').replace(/createRoot\(document\.getElementById\('root'\)!\)\.render\(<App\/>\);/,'');
  return {format:'module',source:ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022},transformers:app?{before:[namedStates]}:undefined}).outputText,shortCircuit:true};
 }return next(url,context);
}});
const {App}=await import('../frontend/src.tsx');const {keepSpans}=await import('../frontend/output_timeline.ts');
function nodes(tree){return Array.isArray(tree)?tree.flatMap(nodes):tree&&typeof tree==='object'&&tree.props?[tree,...nodes(tree.props.children),...nodes(tree.props.actions)]:[]}
function text(node){const v=node?.props?.children;return Array.isArray(v)?v.map(x=>typeof x==='object'?text(x):String(x??'')).join(''):typeof v==='object'?text(v):String(v??'')}
function setup({pauses=[],cuts=[],cursor=2,current=2}={}){
 let index=0,values=[],effects=[];const plan={schema_version:2,summary:'',glossary:[],cuts,pauses,lessons:[{id:'l',start:0,end:8,vi:'Xin chao',en:'Hello',chunks:[],photo_query:'',asset_id:null}],captions:[],visuals:[]};
 const options={layout_mode:'lesson',landscape_layout:'circle',ratio:'16:9',style:'auto',background_removal:{enabled:false},video_frames:{}};
 const project={id:'synthetic',title:'Test',source_file:'source.mp4',metadata:{duration:8,width:320,height:180},revision:1,options,plan,assets:{},jobs:[],status:'ready',warnings:[],time_map:keepSpans(8,cuts,pauses),preview:null,export:{file:'export.mp4',duration:8+pauses.reduce((n,p)=>n+p.duration,0),width:320,height:180,revision:1,digest:'saved'}};
 const state={project,projects:[project],draft:structuredClone(plan),options,assemblyCursor:cursor,current};
 const hooks={effect(fn,deps){effects.push({fn,deps})},namedState(name,v){if(!(name in state))state[name]=typeof v==='function'?v():v;return [state[name],next=>state[name]=typeof next==='function'?next(state[name]):next]},state(v){return hooks.namedState('generic-'+index++,v)},ref(v){const at=index++;return values[at]??(values[at]={current:v})}};
 return {state,eventListener(){const effect=effects.find(e=>e.fn.toString().includes('new EventSource'));assert.ok(effect);let source;const original=globalThis.EventSource;globalThis.EventSource=class{constructor(){source=this}close(){}};try{effect.fn()}finally{if(original===undefined)delete globalThis.EventSource;else globalThis.EventSource=original}return source.onmessage},render(){index=0;effects=[];globalThis.__appHooks=hooks;const tree=nodes(App());for(const {fn} of effects)if(/(?:projectRef\.current\s*=\s*project|dirtyRef\.current\s*=\s*dirty)/.test(fn.toString()))fn();return tree},autoTimer(){const effect=effects.find(e=>e.fn.toString().includes('setInterval'));assert.ok(effect);const previous=globalThis.setInterval;let tick,delay;globalThis.setInterval=(fn,ms)=>{tick=fn;delay=ms;return {}};try{effect.fn()}finally{globalThis.setInterval=previous}return {tick,delay}}};
}
const timeline=tree=>tree.find(n=>typeof n.props.onCutOutput==='function').props;
const live=tree=>tree.find(n=>n.props.controllerRef&&n.props.onOutputTime)?.props;
test('cut from saved MP4 switches to live at the new join and undo/redo restores matching timeline state',()=>{
 const m=setup();assert.equal(live(m.render()),undefined);
 assert.equal(timeline(m.render()).onCutOutput(1,3),true);let tree=m.render();assert.equal(m.state.dirty,true);assert.equal(live(tree).initialOutput,1);assert.equal(m.state.current,3);assert.equal(m.state.sourceSeek,null);assert.equal(m.state.seekRequest.time,1);
 timeline(tree).onUndo();tree=m.render();assert.equal(m.state.draft.cuts.length,0);assert.equal(m.state.current,3);assert.equal(live(tree).initialOutput,3);
 timeline(tree).onRedo();tree=m.render();assert.equal(m.state.current,3);assert.equal(live(tree).initialOutput,1);
});
test('native/live toggles retain an exact position inside a hold and native metadata restores output seconds',()=>{
 const m=setup({pauses:[{id:'p',at:1,duration:2}],cursor:2,current:29/30});let tree=m.render();
 tree.find(n=>n.type==='button'&&text(n)==='Ch\u1ec9nh tr\u1ef1c ti\u1ebfp').props.onClick();tree=m.render();assert.equal(live(tree).initialOutput,2);
 tree.find(n=>n.type==='button'&&text(n)==='Xem MP4 \u0111\u00e3 l\u01b0u').props.onClick();tree=m.render();const media={currentTime:-1};tree.find(n=>n.type==='video').props.onLoadedMetadata({currentTarget:media});assert.equal(media.currentTime,2);
});
test('insertion snaps playhead to the new hold, repeats accumulate, then removing the final hold clamps playback',()=>{
 const m=setup({cursor:2.012,current:2.012});timeline(m.render()).onInsertSilence(2);let tree=m.render();assert.equal(m.state.draft.pauses.length,1);assert.equal(live(tree).initialOutput,2);
 timeline(tree).onInsertSilence(2);tree=m.render();assert.equal(m.state.draft.pauses.length,1);assert.equal(m.state.draft.pauses[0].duration,4);
 timeline(tree).onSeekOutput(11);tree=m.render();timeline(tree).onRemovePause(m.state.draft.pauses[0].id);tree=m.render();assert.equal(m.state.current,7);assert.equal(live(tree).initialOutput,7);
});
test('rejected full-source removal leaves draft/history intact and displays a recoverable error',()=>{
 const m=setup();assert.equal(timeline(m.render()).onCutOutput(0,8),false);const props=timeline(m.render());assert.equal(m.state.draft.cuts.length,0);assert.equal(props.canUndo,false);assert.equal(m.state.dirty,false);assert.ok(m.state.error);
});

test('opening a saved cut video seeks to output zero even when source zero has been removed',()=>{
 const m=setup({cuts:[{id:'head',start:0,end:1,enabled:true,locked:true,reason:'test'}],cursor:null,current:0});const media={currentTime:-1};
 m.render().find(n=>n.type==='video').props.onLoadedMetadata({currentTarget:media});assert.equal(media.currentTime,0);
});
test('save in progress blocks edits so its response cannot silently overwrite a new insertion',()=>{
 const m=setup();m.state.pending='save';const props=timeline(m.render());assert.equal(props.disabled,true);props.onInsertSilence(2);assert.equal(m.state.draft.pauses.length,0);assert.equal(props.canUndo,false);
});

test('detaching a native MP4 pauses its owned media so switching view cannot leave hidden audio playing',()=>{
 const m=setup(),native=m.render().find(n=>n.type==='video');let paused=0;const media={pause(){paused++}};
 native.props.ref(media);native.props.ref(null);assert.equal(paused,1);
});

test('a new insertion next to an existing anchor selects the newly inserted hold',()=>{
 const m=setup({pauses:[{id:'nearby',at:1,duration:2}],cursor:3+1/30,current:1+1/30});timeline(m.render()).onInsertSilence(2);const tree=m.render();
 assert.equal(m.state.draft.pauses.length,2);assert.ok(Math.abs(live(tree).initialOutput-(3+1/30))<1e-8);
});

function pendingApi(t){
 const original=globalThis.fetch,requests=[];globalThis.fetch=(url,init)=>new Promise(resolve=>requests.push({url,body:JSON.parse(init.body),resolve}));t.after(()=>globalThis.fetch=original);
 return {requests,complete(index,project,status=200){const request=requests[index],result={...project,revision:request.body.revision+1,plan:request.body.plan,options:request.body.options,time_map:keepSpans(project.metadata.duration,request.body.plan.cuts,request.body.plan.pauses||[]),updated_at:'synthetic'};request.resolve({ok:status===200,status,json:async()=>status===200?result:{detail:'Synthetic conflict'}})}};
}
test('autosave defaults to 10 seconds, saves in background, and retains edits made while a request is pending',async t=>{
 const api=pendingApi(t),m=setup();timeline(m.render()).onCutOutput(1,3);m.render();const timer=m.autoTimer();assert.equal(timer.delay,10000);
 const first=timer.tick();assert.equal(api.requests.length,1);assert.equal(api.requests[0].body.render_preview,false);assert.equal(m.state.pending,'');assert.equal(m.state.autoSaving,true);
 timeline(m.render()).onInsertSilence(2);m.render();await timer.tick();assert.equal(api.requests.length,1);
 const snapshot=structuredClone(m.state.draft),cursor=m.state.assemblyCursor;api.complete(0,m.state.project);await first;
 assert.equal(m.state.dirty,true);assert.deepEqual(m.state.draft,snapshot);assert.equal(m.state.project.revision,2);assert.equal(m.state.assemblyCursor,cursor);
 m.render();const second=m.autoTimer().tick();assert.equal(api.requests[1].body.revision,2);assert.equal(api.requests[1].body.plan.pauses.length,1);api.complete(1,m.state.project);await second;
 assert.equal(m.state.dirty,false);assert.deepEqual(m.state.draft,snapshot);assert.equal(m.state.project.revision,3);assert.ok(m.state.lastSaved);
});
test('autosave during playback does not pause or seek the preview and does not save again when clean',async t=>{
 const api=pendingApi(t),m=setup();timeline(m.render()).onCutOutput(1,3);m.state.playing=true;m.render();const cursor=m.state.assemblyCursor,seek=m.state.seekRequest;
 const pending=m.autoTimer().tick();api.complete(0,m.state.project);await pending;m.render();assert.equal(m.state.playing,true);assert.equal(m.state.assemblyCursor,cursor);assert.deepEqual(m.state.seekRequest,seek);
 await m.autoTimer().tick();assert.equal(api.requests.length,1);
});
test('autosave conflict retains draft and stops automatic retries until explicit resolution',async t=>{
 const api=pendingApi(t),m=setup();timeline(m.render()).onCutOutput(1,3);m.render();const snapshot=structuredClone(m.state.draft),timer=m.autoTimer();const pending=timer.tick();api.complete(0,m.state.project,409);await pending;m.render();
 assert.equal(m.state.dirty,true);assert.deepEqual(m.state.draft,snapshot);assert.ok(m.state.saveError);await m.autoTimer().tick();assert.equal(api.requests.length,1);
});
test('late autosave responses cannot replace a different project',async t=>{
 const api=pendingApi(t),m=setup();timeline(m.render()).onCutOutput(1,3);m.render();const original=m.state.project,pending=m.autoTimer().tick();
 m.state.project={...m.state.project,id:'other',revision:9};m.render();api.complete(0,original);await pending;assert.equal(m.state.project.id,'other');assert.equal(m.state.project.revision,9);assert.equal(m.state.dirty,true);
});
test('autosave interval offers every second from 5 to 20 and remembers the choice',()=>{
 const original=globalThis.localStorage,data=new Map();globalThis.localStorage={getItem:key=>data.get(key)??null,setItem:(key,value)=>data.set(key,value)};
 try{const m=setup();let tree=m.render(),select=tree.find(n=>n.type==='select'&&n.props['aria-label']==='Chu k\u1ef3 t\u1ef1 \u0111\u1ed9ng l\u01b0u');assert.equal(select.props.value,10);assert.equal(nodes(select.props.children).filter(n=>n.type==='option').length,16);
 select.props.onChange({target:{value:'5'}});m.render();assert.equal(m.autoTimer().delay,5000);assert.equal(data.get('vietcut-autosave-seconds'),'5');assert.equal(setup().render().find(n=>n.type==='select'&&n.props['aria-label']==='Chu k\u1ef3 t\u1ef1 \u0111\u1ed9ng l\u01b0u').props.value,5);
 }finally{if(original===undefined)delete globalThis.localStorage;else globalThis.localStorage=original}
});

test('an external revision cannot silently become the base of a newer unsaved draft',async t=>{
 const api=pendingApi(t),m=setup();timeline(m.render()).onCutOutput(1,3);m.render();const first=m.autoTimer().tick();api.complete(0,m.state.project);await first;
 timeline(m.render()).onInsertSilence(2);m.state.project={...m.state.project,revision:9};m.render();const second=m.autoTimer().tick();assert.equal(api.requests[1].body.revision,2);api.complete(1,m.state.project,409);await second;assert.equal(m.state.dirty,true);assert.equal(m.state.draft.pauses.length,1);
});
test('manual and automatic saves share one in-flight request',async t=>{
 const api=pendingApi(t),m=setup();timeline(m.render()).onCutOutput(1,3);let tree=m.render();const pending=m.autoTimer().tick();tree=m.render();const button=tree.find(n=>n.type==='button'&&n.props.onClick?.name==='save');assert.equal(button.props.disabled,true);await button.props.onClick();assert.equal(api.requests.length,1);api.complete(0,m.state.project);await pending;
});

test('temporary autosave failures preserve the draft and can retry at the next interval',async t=>{
 const original=globalThis.fetch,m=setup();let requests=0;globalThis.fetch=async()=>{requests++;throw new Error('Synthetic offline')};t.after(()=>globalThis.fetch=original);
 timeline(m.render()).onCutOutput(1,3);m.render();await m.autoTimer().tick();assert.equal(m.state.dirty,true);assert.equal(m.state.autoSaving,false);assert.equal(m.state.saveError,'Synthetic offline');
 m.render();await m.autoTimer().tick();assert.equal(requests,2);assert.equal(m.state.draft.cuts.length,1);
});
test('autosave waits while a project has a queued/running render job',async t=>{
 const api=pendingApi(t),m=setup();timeline(m.render()).onCutOutput(1,3);m.state.project={...m.state.project,jobs:[{id:'job',kind:'export',status:'queued',progress:0,message:'Synthetic'}]};m.render();await m.autoTimer().tick();assert.equal(api.requests.length,0);assert.equal(m.state.dirty,true);
});

test('the SSE acknowledgement of an in-flight autosave never reloads the draft or disturbs playback',async t=>{
 const api=pendingApi(t),m=setup();timeline(m.render()).onCutOutput(1,3);m.state.playing=true;m.render();const events=m.eventListener(),pending=m.autoTimer().tick(),draft=m.state.draft,seek=m.state.seekRequest;
 events({data:JSON.stringify({revision:2,status:'ready',jobs:[],preview:null,export:m.state.project.export})});m.render();assert.equal(api.requests.length,1);assert.equal(m.state.draft,draft);assert.equal(m.state.playing,true);assert.deepEqual(m.state.seekRequest,seek);
 api.complete(0,m.state.project);await pending;m.render();assert.equal(m.state.draft,draft);assert.equal(m.state.playing,true);assert.equal(m.state.dirty,false);
});
