import {useEffect,useRef} from 'react';
import type {Span} from './output_timeline';
import {browserPlaybackClock,createPausePlayback,type PlaybackController} from './pause_clock';
export type {PlaybackController} from './pause_clock';
export function usePausePlayback(videoRef:React.RefObject<HTMLVideoElement|null>,controllerRef:React.RefObject<PlaybackController|null>,spans:Span[],enabled:boolean,mediaKey:string|undefined,onOutput:(t:number)=>void,onSource:(t:number)=>void,onPlaying:(p:boolean)=>void,onError:(s:string)=>void,initialOutput=0){
 const cursor=useRef(initialOutput),callbacks=useRef({onOutput,onSource,onPlaying,onError});callbacks.current={onOutput,onSource,onPlaying,onError};
 useEffect(()=>{
  const video=videoRef.current;if(!video||!mediaKey||!enabled)return;
  const engine=createPausePlayback(video,spans,{onOutput:t=>callbacks.current.onOutput(t),onSource:t=>callbacks.current.onSource(t),onPlaying:p=>callbacks.current.onPlaying(p),onError:s=>callbacks.current.onError(s)},browserPlaybackClock,cursor.current);
  controllerRef.current=engine;
  const mediaError=()=>{engine.pause();callbacks.current.onError(video.error?.message||'Kh\u00f4ng \u0111\u1ecdc \u0111\u01b0\u1ee3c video xem tr\u01b0\u1edbc. H\u00e3y tua l\u1ea1i ho\u1eb7c t\u1ea3i l\u1ea1i trang.')};
  video.addEventListener('error',mediaError);
  return()=>{video.removeEventListener('error',mediaError);cursor.current=engine.position();engine.dispose();if(controllerRef.current===engine)controllerRef.current=null};
 },[enabled,mediaKey,JSON.stringify(spans)]);
}
