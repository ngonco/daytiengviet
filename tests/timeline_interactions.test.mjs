// Exercise the actual TSX event handlers with deterministic hook state; no DOM emulation.
import test from 'node:test';import assert from 'node:assert/strict';import {registerHooks} from 'node:module';import {readFileSync,existsSync} from 'node:fs';import {fileURLToPath} from 'node:url';import ts from 'typescript';
const fakeReact='data:text/javascript,'+encodeURIComponent(`export default {};export const useState=(v)=>globalThis.__cutTimelineHooks.state(v),useRef=(v)=>globalThis.__cutTimelineHooks.ref(v),useEffect=(fn,deps)=>globalThis.__cutTimelineHooks.effect(fn,deps),useLayoutEffect=()=>{};`);
registerHooks({resolve(specifier,context,next){if(specifier==='react'&&context.parentURL?.endsWith('/CutTimeline.tsx'))return {url:fakeReact,shortCircuit:true};if(specifier.startsWith('./')&&context.parentURL?.includes('/frontend/')){for(const suffix of ['.ts','.tsx']){const url=new URL(specifier+suffix,context.parentURL);if(existsSync(fileURLToPath(url)))return {url:url.href,shortCircuit:true}}}return next(specifier,context)},load(url,context,next){if(url.endsWith('/CutTimeline.tsx'))return {format:'module',source:ts.transpileModule(readFileSync(fileURLToPath(url),'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText,shortCircuit:true};return next(url,context)}});
const {default:CutTimeline}=await import('../frontend/CutTimeline.tsx');
function nodes(tree){return Array.isArray(tree)?tree.flatMap(nodes):tree&&typeof tree==='object'&&tree.props?[tree,...nodes(tree.props.children)]:[]}
function text(node){const value=node?.props?.children;return Array.isArray(value)?value.map(v=>typeof v==='object'?text(v):String(v??'')).join(''):typeof value==='object'?text(value):String(value??'')}
function mount(extra={}){
 let index=0,values=[],effects=[];const seeks=[],cuts=[];
 const hooks={effect(fn,deps){effects.push({fn,deps})},state(v){const at=index++;if(!(at in values))values[at]=typeof v==='function'?v():v;return [values[at],next=>values[at]=typeof next==='function'?next(values[at]):next]},ref(v){const at=index++;return values[at]??(values[at]={current:v})}};
 const props={pauses:[],assemblyTime:2,onSeekOutput:t=>seeks.push(t),onInsertSilence(){},onChangePause(){},onRemovePause(){},onCutOutput:(a,b)=>{cuts.push([a,b]);return true},silenceEnabled:true,duration:8,time:2,cuts:[],clips:[],disabled:false,playing:false,onSelect(){},onPlay(){},onPreview(){},onHistory(){},onToggle(){},onUndo(){},onRedo(){},canUndo:false,canRedo:false,frames:[],waveform:[],...extra};
 return {seeks,cuts,props,render(){index=0;effects=[];globalThis.__cutTimelineHooks=hooks;return nodes(CutTimeline(props))},deleteListener(){const effect=effects.find(e=>e.fn.toString().includes('deleteAction'));assert.ok(effect);let handler;const previous=globalThis.window;globalThis.window={addEventListener(name,fn){if(name==='keydown')handler=fn},removeEventListener(){}};try{effect.fn()}finally{if(previous===undefined)delete globalThis.window;else globalThis.window=previous}return handler}};
}
test('split inside inserted silence retains its output position, then deleting selects only that hold portion',()=>{
 const m=mount({pauses:[{id:'p',at:1,duration:2}],assemblyTime:2,time:29/30});let tree=m.render();
 tree.find(n=>n.type==='button'&&text(n)==='T\u00e1ch t\u1ea1i \u0111\u1ea7u ph\u00e1t').props.onClick();tree=m.render();
 const clips=tree.filter(n=>n.props.className==='assembly-clip');assert.equal(clips.length,4);assert.equal(clips[2].props.style.left,'20%');
 clips[2].props.onClick({detail:0});tree=m.render();tree.find(n=>n.type==='button'&&text(n)==='C\u1eaft b\u1ecf \u0111o\u1ea1n').props.onClick();assert.deepEqual(m.cuts,[[2,3]]);assert.deepEqual(m.seeks,[2]);
});
test('pointer scrubbing on a clip reaches the clicked frame instead of jumping to its start',()=>{
 const m=mount(),tree=m.render(),clip=tree.find(n=>n.props.className==='assembly-clip'),canvas=tree.find(n=>n.props.className==='cut-timeline-canvas');let stopped=false,focused=false;
 clip.props.onPointerDown({button:0,stopPropagation(){stopped=true}});assert.equal(stopped,false);
 canvas.props.onPointerDown({button:0,pointerId:1,clientX:75,currentTarget:{focus(){focused=true},setPointerCapture(){},getBoundingClientRect:()=>({left:0,width:100})}});
 clip.props.onClick({detail:1});assert.equal(focused,true);assert.deepEqual(m.seeks,[6]);
});
test('frame steps and keyboard seeks keep precise output seconds inside silence',()=>{
 const m=mount({pauses:[{id:'p',at:1,duration:2}],assemblyTime:2,time:29/30}),tree=m.render();
 tree.find(n=>n.type==='button'&&text(n)==='+1 khung').props.onClick();assert.ok(Math.abs(m.seeks.at(-1)-(2+1/30))<1e-8);
 tree.find(n=>n.props.className==='cut-timeline-canvas').props.onKeyDown({key:'ArrowLeft',shiftKey:true,preventDefault(){}});assert.equal(m.seeks.at(-1),1);
});

test('Delete removes the selected timeline range even after focus moves to preview, while typing and repeat stay safe',()=>{
 const m=mount({cuts:[{id:'c',start:2,end:3,enabled:true,reason:'test'}]}),tree=m.render();tree.find(n=>n.props.className==='assembly-clip').props.onClick({detail:0});m.render();const key=m.deleteListener();let prevented=0;
 const event={key:'Delete',defaultPrevented:false,repeat:false,preventDefault(){prevented++},target:{closest:()=>false}};
 key({...event,target:{closest:()=>true}});assert.equal(m.cuts.length,0);
 key({...event,repeat:true});assert.equal(m.cuts.length,0);
 key(event);assert.deepEqual(m.cuts,[[0,2]]);assert.equal(prevented,2);
});
test('Delete is inactive when the editor is blocked by a modal or a busy job',()=>{
 for(const props of [{shortcutsEnabled:false},{disabled:true}]){const m=mount(props);m.render();assert.equal(m.deleteListener(),undefined);assert.deepEqual(m.cuts,[])}
});

test('I uses the selected silence duration, repeated separate presses accumulate, and held/typing keys do not insert',()=>{
 const inserted=[],m=mount({onInsertSilence:seconds=>inserted.push(seconds)});let tree=m.render(),key=m.deleteListener(),prevented=0;
 const event={key:'i',code:'KeyI',defaultPrevented:false,repeat:false,target:{closest:()=>false},preventDefault(){prevented++}};
 key(event);key(event);assert.deepEqual(inserted,[2,2]);key({...event,repeat:true});key({...event,target:{closest:()=>true}});assert.deepEqual(inserted,[2,2]);assert.equal(prevented,3);
 tree.find(n=>n.type==='input'&&n.props.type==='number'&&n.props.value===2).props.onChange({target:{value:'3.5'}});tree=m.render();key=m.deleteListener();key(event);assert.deepEqual(inserted,[2,2,3.5]);assert.equal(tree.find(n=>n.props['aria-keyshortcuts']==='I').type,'button');
});
test('I respects unavailable lesson mode, busy/modal states, and invalid insertion duration',()=>{
 const inserted=[],event={key:'i',code:'KeyI',defaultPrevented:false,target:{closest:()=>false},preventDefault(){assert.fail('inactive shortcut consumed I')}};
 for(const extra of [{silenceEnabled:false},{disabled:true},{shortcutsEnabled:false}]){const m=mount({...extra,onInsertSilence:seconds=>inserted.push(seconds)});m.render();m.deleteListener()?.(event)}
 const m=mount({onInsertSilence:seconds=>inserted.push(seconds)}),tree=m.render();tree.find(n=>n.type==='input'&&n.props.type==='number'&&n.props.value===2).props.onChange({target:{value:'0'}});m.render();m.deleteListener()(event);assert.deepEqual(inserted,[]);
});
