// Exercise the actual TSX event handlers with deterministic hook state; no DOM emulation.
import test from 'node:test';import assert from 'node:assert/strict';import {registerHooks} from 'node:module';import {readFileSync,existsSync} from 'node:fs';import {fileURLToPath} from 'node:url';import ts from 'typescript';
const fakeReact='data:text/javascript,'+encodeURIComponent(`export default {};export const useState=(v)=>globalThis.__cutTimelineHooks.state(v),useRef=(v)=>globalThis.__cutTimelineHooks.ref(v),useEffect=()=>{},useLayoutEffect=()=>{};`);
registerHooks({resolve(specifier,context,next){if(specifier==='react'&&context.parentURL?.endsWith('/CutTimeline.tsx'))return {url:fakeReact,shortCircuit:true};if(specifier.startsWith('./')&&context.parentURL?.includes('/frontend/')){for(const suffix of ['.ts','.tsx']){const url=new URL(specifier+suffix,context.parentURL);if(existsSync(fileURLToPath(url)))return {url:url.href,shortCircuit:true}}}return next(specifier,context)},load(url,context,next){if(url.endsWith('/CutTimeline.tsx'))return {format:'module',source:ts.transpileModule(readFileSync(fileURLToPath(url),'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText,shortCircuit:true};return next(url,context)}});
const {default:CutTimeline}=await import('../frontend/CutTimeline.tsx');
function nodes(tree){return Array.isArray(tree)?tree.flatMap(nodes):tree&&typeof tree==='object'&&tree.props?[tree,...nodes(tree.props.children)]:[]}
function text(node){const value=node?.props?.children;return Array.isArray(value)?value.map(v=>typeof v==='object'?text(v):String(v??'')).join(''):typeof value==='object'?text(value):String(value??'')}
function mount(extra={}){
 let index=0,values=[];const seeks=[],cuts=[];
 const hooks={state(v){const at=index++;if(!(at in values))values[at]=typeof v==='function'?v():v;return [values[at],next=>values[at]=typeof next==='function'?next(values[at]):next]},ref(v){const at=index++;return values[at]??(values[at]={current:v})}};
 const props={pauses:[],assemblyTime:2,onSeekOutput:t=>seeks.push(t),onInsertSilence(){},onChangePause(){},onRemovePause(){},onCutOutput:(a,b)=>{cuts.push([a,b]);return true},silenceEnabled:true,duration:8,time:2,cuts:[],clips:[],disabled:false,playing:false,onSelect(){},onPlay(){},onPreview(){},onHistory(){},onToggle(){},onUndo(){},onRedo(){},canUndo:false,canRedo:false,frames:[],waveform:[],...extra};
 return {seeks,cuts,props,render(){index=0;globalThis.__cutTimelineHooks=hooks;return nodes(CutTimeline(props))}};
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
