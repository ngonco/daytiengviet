export const AUTOSAVE_KEY='vietcut-autosave-seconds';
export function autosaveInterval(value:unknown){const n=Number(value);return Number.isFinite(n)&&n>=5&&n<=20?Math.round(n):10}
export function readAutosaveInterval(){try{return autosaveInterval(localStorage.getItem(AUTOSAVE_KEY))}catch{return 10}}
export function storeAutosaveInterval(value:number){const seconds=autosaveInterval(value);try{localStorage.setItem(AUTOSAVE_KEY,String(seconds))}catch{}return seconds}
export type SaveStamp={projectId:string;session:number;edit:number};
export function savedDraftState(sent:SaveStamp,current:SaveStamp):'ignore'|'dirty'|'clean'{
 if(sent.projectId!==current.projectId||sent.session!==current.session)return 'ignore';
 return sent.edit===current.edit?'clean':'dirty';
}
