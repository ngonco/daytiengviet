import unittest,copy
from backend.recut import propose
from backend.timeline import keep_spans

def plan():return {'schema_version':2,'summary':'','glossary':[],'lessons':[{'id':'l','start':0,'end':12,'vi':'Xin chào','en':'Hello','chunks':[],'photo_query':'','asset_id':None,'locked':True}],'cuts':[],'captions':[],'visuals':[]}
class RecutTests(unittest.TestCase):
 def test_strength_changes_silence_but_not_lesson(self):
  p=plan();strong=propose(p,{},12,[(1,1.8),(3,5)],'strong');light=propose(p,{},12,[(1,1.8),(3,5)],'light')
  self.assertEqual(len(strong['cuts']),2);self.assertEqual(len(light['cuts']),1);self.assertEqual(strong['lessons'],p['lessons']);self.assertEqual(p['cuts'],[])
 def test_practice_and_restored_manual_spans_survive(self):
  p=plan();p['cuts']=[{'id':'manual','start':7,'end':9,'enabled':False,'locked':True}]
  t={'words':[{'word':'Your turn, repeat after me.','start':.5,'end':1}]}
  r=propose(p,t,12,[(1.2,3),(7,8.5)],'strong');self.assertEqual(r['cuts'],p['cuts'])
 def test_long_retakes_removed_but_practice_and_teaching_targets_retained(self):
  phrase=['This','is','the','first','complete','English','sentence.'];words=[{'word':w,'start':i*.3+1,'end':i*.3+1.2} for i,w in enumerate(phrase+phrase)]
  p=plan();r=propose(p,{'words':words},12,[]);self.assertEqual(len(r['cuts']),1)
  protected=[{'word':'Repeat after me','start':0,'end':.5}]+words
  self.assertEqual(propose(p,{'words':protected},12,[])['cuts'],[])
 def test_rerun_is_idempotent_and_keeps_half_second(self):
  p=plan();r=propose(p,{},12,[(1,3),(5,8)]);self.assertEqual(propose(r,{},12,[(1,3),(5,8)]),r)
  r=propose(p,{},12,[(0,12)]);self.assertGreaterEqual(sum(s['end']-s['start'] for s in keep_spans(12,r['cuts'])),.5)

 def test_audio_detects_silence_inside_overlong_stt_word(self):
  from tempfile import TemporaryDirectory
  from pathlib import Path
  from backend.media import ffmpeg
  from backend.recut import quiet_intervals
  with TemporaryDirectory() as tmp:
   source=Path(tmp)/'source.wav'
   ffmpeg(['-f','lavfi','-i','sine=frequency=440:duration=3','-af',"volume=volume=0:enable='between(t,1,2)'",source])
   spans=quiet_intervals(source,None)
   self.assertTrue(any(a>=.9 and b<=2.1 and b-a>.8 for a,b in spans))
   p=plan();p['lessons'][0]['end']=3
   r=propose(p,{'words':[{'word':'Hello','start':0,'end':3}]},3,spans)
   self.assertEqual(len(r['cuts']),1)

 def test_duplicate_suffix_removes_first_sentence_prefix_too(self):
  first=['Next,',"we'll",'say','thank','you','and','sorry.'];second=['In','the','next','lesson,',"we'll",'say','thank','you','and','sorry.']
  words=[{'word':w,'start':1+i*.3,'end':1.2+i*.3} for i,w in enumerate(first+second)]
  r=propose(plan(),{'words':words},12,[])
  self.assertEqual(len(r['cuts']),1);self.assertLess(r['cuts'][0]['start'],1)

 def test_none_restores_all_cuts_without_mutating_other_content_or_decoding(self):
  from backend.recut import recut
  from unittest.mock import patch,Mock
  p=plan();p['pauses']=[{'id':'hold','at':5,'duration':2}]
  p['cuts']=[{'id':'manual','start':1,'end':3,'enabled':True,'locked':True},
             {'id':'tighten-auto','start':4,'end':6,'enabled':True,'locked':False},
             {'id':'restored','start':8,'end':9,'enabled':False,'locked':True}]
  before=copy.deepcopy(p)
  with patch('backend.recut.quiet_intervals') as decode:
   result=recut({'plan':p,'options':{'cut_strength':'none'}},Mock())
   decode.assert_not_called()
  self.assertFalse(any(c['enabled'] for c in result['cuts']))
  self.assertEqual(sum(s['end']-s['start'] for s in keep_spans(12,result['cuts'])),12)
  self.assertEqual({k:v for k,v in result.items() if k!='cuts'},{k:v for k,v in p.items() if k!='cuts'})
  self.assertEqual(p,before)
  self.assertEqual(propose(result,{},12,[(0,12)],'none'),result)

 def test_save_none_restores_locked_cuts_and_preserves_version(self):
  from pathlib import Path
  from tempfile import TemporaryDirectory
  from unittest.mock import patch
  from backend import store
  from backend.app import save_plan,SavePlan,Options
  with TemporaryDirectory() as tmp,patch('backend.store.data_root',return_value=Path(tmp)):
   store.init();pid='a123456789abcdef';p=plan()
   p['cuts']=[{'id':'manual','start':1,'end':3,'enabled':True,'locked':True}]
   store.save({'id':pid,'title':'Synthetic','source_file':'source.mp4','options':Options(layout_mode='lesson').model_dump(),
               'metadata':{'duration':12,'width':320,'height':180},'plan':p,'assets':{},'revision':1})
   result=save_plan(pid,SavePlan(revision=1,plan=p,options=Options(layout_mode='lesson',cut_strength='none'),render_preview=False))
   self.assertFalse(result['plan']['cuts'][0]['enabled'])
   self.assertEqual(result['options']['cut_strength'],'none')
   import json
   old=json.loads((store.folder(pid)/'versions/v00001.json').read_text(encoding='utf-8'))
   self.assertTrue(old['plan']['cuts'][0]['enabled'])
   self.assertEqual(store.jobs(),[])
