// A media element may be connected to Web Audio only once, including across
// option changes and React effect replays. Never amplify an exported MP4 twice.
type Route={context:AudioContext;gain:GainNode;source:MediaElementAudioSourceNode};
type State={enabled:boolean;db:number;route?:Route};
const states=new WeakMap<HTMLMediaElement,State>();

export function gainValue(db:number){return 10**(Math.max(-60,Math.min(48,Number.isFinite(db)?db:0))/20)}

function apply(state:State){
 const route=state.route;if(!route)return;
 route.gain.gain.cancelScheduledValues(route.context.currentTime);
 route.gain.gain.setTargetAtTime(gainValue(state.enabled?state.db:0),route.context.currentTime,.03);
}

export function configurePreviewAudio(video:HTMLMediaElement,enabled:boolean,db=0){
 const state=states.get(video)||{enabled,db};state.enabled=enabled;state.db=db;states.set(video,state);apply(state);
}

export async function resumePreviewAudio(video:HTMLMediaElement,create=()=>new AudioContext()){
 const state=states.get(video);if(!state)return;
 if(!state.route&&state.enabled){
  const context=create();const gain=context.createGain();const source=context.createMediaElementSource(video);
  source.connect(gain);gain.connect(context.destination);state.route={context,gain,source};apply(state);
 }
 if(state.route&&state.route.context.state!=='running')await state.route.context.resume();
}

export function releasePreviewAudio(video:HTMLMediaElement){
 const state=states.get(video);if(!state)return;
 state.enabled=false;state.db=0;apply(state);
 queueMicrotask(()=>{
  // Strict Mode and source switches keep the same attached DOM node; retain its
  // source binding. A truly removed element can release its audio device.
  if(!video.isConnected&&state.route){void state.route.context.close().catch(()=>{});states.delete(video)}
 });
}
