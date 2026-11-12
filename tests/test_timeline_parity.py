"""Read-only cross-runtime parity for draft previews and exported timeline maps."""
import json,random,subprocess,unittest
from pathlib import Path
from backend.timeline import assembly_spans,keep_spans,output_to_source,source_to_output

class TimelineParityTests(unittest.TestCase):
 def test_frontend_and_backend_agree_across_cut_hold_and_tail_combinations(self):
  rng=random.Random(751);cases=[]
  for i in range(100):
   duration=10+(i%3)*.012
   cuts=[{'start':a/30,'end':(a+rng.randrange(1,20))/30,'enabled':rng.choice([True,True,False])} for a in [rng.randrange(0,250) for _ in range(8)]]
   pauses=[{'id':f'{prefix}{j}','at':rng.choice([0,duration,3,3,round(rng.uniform(0,9)*30)/30]),'duration':rng.randrange(1,90)/30} for j,prefix in enumerate(['a','B','C','d'])]
   cases.append({'duration':duration,'cuts':cuts,'pauses':pauses})
  root=Path(__file__).resolve().parents[1]
  script="""import fs from 'node:fs';import {keepSpans,sourceTime,outputTime} from './frontend/output_timeline.ts';const cases=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(cases.map(c=>{const spans=keepSpans(c.duration,c.cuts,c.pauses),end=spans.at(-1).output_end;return {spans,sources:Array.from({length:21},(_,i)=>sourceTime(i*end/20,spans)),outputs:Array.from({length:21},(_,i)=>outputTime(i*c.duration/20,spans))}})));"""
  completed=subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(cases),text=True,capture_output=True,cwd=root,check=True,timeout=30)
  for case,result in zip(cases,json.loads(completed.stdout)):
   spans=assembly_spans(case['duration'],case['cuts'],case['pauses'])
   self.assertEqual(len(spans),len(result['spans']))
   for mapping in [spans,result['spans']]:
    for previous,current in zip(mapping,mapping[1:]):self.assertEqual(previous['output_end'],current['output_start'])
   for expected,actual in zip(spans,result['spans']):
    self.assertEqual(set(expected),set(actual))
    for key,value in expected.items():
     if isinstance(value,(int,float)):self.assertAlmostEqual(value,actual[key],places=7)
     else:self.assertEqual(value,actual[key])
   end=spans[-1]['output_end']
   for i,value in enumerate(result['sources']):self.assertAlmostEqual(value,output_to_source(i*end/20,spans),places=7)
   for i,value in enumerate(result['outputs']):self.assertAlmostEqual(value,source_to_output(i*case['duration']/20,spans),places=7)

 def test_dense_cuts_and_cumulative_holds_have_exact_join_endpoints(self):
  cuts=[{'start':(i*100+13)/30,'end':(i*100+52)/30,'enabled':True} for i in range(58)]
  duration=205.252729
  for mapping in [keep_spans(duration,cuts),*[assembly_spans(duration,cuts,[{'id':'p','at':337/30,'duration':seconds}]) for seconds in [2,4,6]]]:
   for previous,current in zip(mapping,mapping[1:]):
    self.assertEqual(previous['output_end'],current['output_start'])
    self.assertLess(output_to_source(previous['output_end'],mapping),duration-1)
 def test_internal_holes_in_older_maps_do_not_resolve_to_source_tail(self):
  eps=2**-49
  mapping=[{'start':0,'end':1,'output_start':0,'output_end':1},{'start':5,'end':6,'output_start':1+eps,'output_end':2+eps},{'start':10,'end':20,'output_start':2+eps,'output_end':12+eps}]
  self.assertEqual(output_to_source(1,mapping),5)
  self.assertEqual(output_to_source(-1,mapping),0)
  self.assertEqual(output_to_source(100,mapping),20)
