import test from 'node:test';import assert from 'node:assert/strict';
import {autosaveInterval,savedDraftState} from '../frontend/autosave.ts';
test('autosave settings default to 10 and accept only the 5..20 second range',()=>{
 for(const value of [null,undefined,'',0,4,21,NaN,Infinity,'bad'])assert.equal(autosaveInterval(value),10);
 for(let value=5;value<=20;value++)assert.equal(autosaveInterval(String(value)),value);
});
test('save acknowledgements distinguish newer edits, project changes and forced reloads',()=>{
 const sent={projectId:'a',session:1,edit:3};assert.equal(savedDraftState(sent,{...sent}),'clean');assert.equal(savedDraftState(sent,{...sent,edit:4}),'dirty');assert.equal(savedDraftState(sent,{...sent,projectId:'b'}),'ignore');assert.equal(savedDraftState(sent,{...sent,session:2}),'ignore');
});
