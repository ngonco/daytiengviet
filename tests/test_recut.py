import unittest,copy
from backend.recut import propose
from backend.timeline import keep_spans

def plan():return {'schema_version':2,'summary':'','glossary':[],'lessons':[{'id':'l','start':0,'end':12,'vi':'Xin chào','en':'Hello','chunks':[],'photo_query':'','asset_id':None,'locked':True}],'cuts':[],'captions':[],'visuals':[]}
class RecutTests(unittest.TestCase):
 def transcript(self,left='We use this form because',right='the subject is plural here.',start=6):
  first=[{'word':w,'start':.2+i*.25,'end':.4+i*.25} for i,w in enumerate(left.split())]
  second=[{'word':w,'start':start+i*.25,'end':start+.2+i*.25} for i,w in enumerate(right.split())]
  return {'words':first+second}
 def apply_all(self,p,t,gaps,strength='strong',duration=12):
  from backend.recut import candidates
  choices=candidates(p,t,duration,gaps,strength)
  return propose(p,t,duration,gaps,strength,[c['id'] for c in choices])
 def test_strict_three_second_threshold_for_every_strength(self):
  p=plan();t=self.transcript()
  for strength in ['light','medium','strong']:
   for seconds in [.8,2,3]:
    self.assertEqual(self.apply_all(p,t,[(2,2+seconds)],strength)['cuts'],[])
   result=self.apply_all(p,t,[(2,5.02)],strength)
   self.assertEqual(len(result['cuts']),1)
   self.assertEqual(result['lessons'],p['lessons']);self.assertEqual(p['cuts'],[])
  self.assertGreater(self.apply_all(p,t,[(2,6)],'strong')['cuts'][0]['end']-self.apply_all(p,t,[(2,6)],'strong')['cuts'][0]['start'],
                     self.apply_all(p,t,[(2,6)],'light')['cuts'][0]['end']-self.apply_all(p,t,[(2,6)],'light')['cuts'][0]['start'])
 def test_unreviewed_unknown_and_coarse_stt_never_cut(self):
  p=plan();t=self.transcript()
  self.assertEqual(propose(p,t,12,[(2,6)])['cuts'],[])
  self.assertEqual(self.apply_all(p,{},[(0,12)])['cuts'],[])
  self.assertEqual(self.apply_all(p,{'words':[{'word':'Hello','start':0,'end':12}]},[(2,6)])['cuts'],[])
 def test_practice_has_no_eight_second_expiry(self):
  p=plan();p['lessons'][0]['end']=40
  t=self.transcript('Your turn, repeat after me.','Say this sentence.',start=30)
  self.assertEqual(self.apply_all(p,t,[(2,30)],duration=40)['cuts'],[])
 def test_reading_translation_and_vietnamese_repetitions_are_protected(self):
  for left,right in [('Hello','Xin chào'),('Xin chào','Xin chào'),('Xin chào','Hello')]:
   t=self.transcript(left,right,start=9)
   self.assertEqual(self.apply_all(plan(),t,[(2,9)])['cuts'],[])
  p=plan();p['lessons'][0]['chunks']=[{'vi':'Cảm ơn','en':'Thank you'}]
  self.assertEqual(self.apply_all(p,self.transcript('Thank you','Cảm ơn'),[(2,6)])['cuts'],[])
 def test_only_immediate_short_stutters_are_candidates_not_full_retakes(self):
  t=self.transcript('We we use this form','because it refers to people.')
  result=self.apply_all(plan(),t,[])
  self.assertEqual(len(result['cuts']),1);self.assertIn('nói vấp',result['cuts'][0]['reason'])
  for left in ['This is the first complete English sentence. This is the first complete English sentence.',
               'Really. Really.', 'Xin chào Xin chào']:
   self.assertEqual(self.apply_all(plan(),self.transcript(left,'The next section starts.',start=10),[])['cuts'],[])
  self.assertEqual(self.apply_all(plan(),self.transcript('We','we continue explaining.',start=3),[])['cuts'],[])
 def test_contiguous_stutter_removes_whole_first_word_and_preserves_neighbors(self):
  t={'words':[{'word':w,'start':i*.3,'end':(i+1)*.3} for i,w in enumerate('Because we we use plural nouns.'.split())]}
  result=self.apply_all(plan(),t,[])
  self.assertEqual(len(result['cuts']),1)
  cut=result['cuts'][0]
  self.assertEqual(cut['start'],.3);self.assertEqual(cut['end'],.6)
 def test_false_start_before_a_complete_teaching_target_can_be_removed(self):
  p=plan();p['lessons'][0].update(vi='Hôm nay',en='Today')
  t={'words':[{'word':w,'start':i*.3,'end':(i+1)*.3} for i,w in enumerate('Hôm hôm nay chúng ta học.'.split())]}
  result=self.apply_all(p,t,[])
  self.assertEqual(len(result['cuts']),1)
  self.assertEqual(result['cuts'][0]['start'],0);self.assertEqual(result['cuts'][0]['end'],.3)
 def test_explicit_recut_replaces_old_auto_but_keeps_manual_and_disabled_locks(self):
  p=plan();p['pauses']=[{'id':'hold','at':8,'duration':2}]
  p['cuts']=[{'id':'cut-0-1','start':2,'end':3,'enabled':True,'locked':False},
             {'id':'tighten-old','start':4,'end':5,'enabled':True,'locked':False},
             {'id':'manual','start':7,'end':8,'enabled':True,'locked':True},
             {'id':'cut-0-2','start':9,'end':10,'enabled':False,'locked':True}]
  before=copy.deepcopy(p);r=self.apply_all(p,self.transcript(),[(2,6)])
  kept=[c for c in r['cuts'] if c['locked']]
  self.assertEqual(kept,p['cuts'][2:]);self.assertEqual(r['pauses'],p['pauses'])
  self.assertEqual(r['lessons'],p['lessons']);self.assertEqual(r['captions'],p['captions'])
  self.assertEqual(p,before);self.assertEqual(self.apply_all(r,self.transcript(),[(2,6)]),r)
  self.assertGreaterEqual(sum(s['end']-s['start'] for s in keep_spans(12,r['cuts'])),.5)
 def test_locked_restored_range_blocks_regeneration(self):
  p=plan();p['cuts']=[{'id':'manual','start':2,'end':6,'enabled':False,'locked':True}]
  self.assertEqual(self.apply_all(p,self.transcript(),[(2,6)])['cuts'],p['cuts'])
 def test_audio_evidence_detected_but_short_pause_preserved(self):
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
   self.assertEqual(self.apply_all(p,self.transcript(),spans,duration=3)['cuts'],[])

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
