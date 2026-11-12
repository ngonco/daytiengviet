import unittest,copy,hashlib
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import Mock
import numpy as np
from PIL import Image
from pydantic import ValidationError
from backend.timeline import validate_plan,assembly_spans,map_interval,output_to_source
from backend.lesson_render import render_lessons
from backend.app import Options
from backend.media import ffmpeg,probe

def base():return {'schema_version':2,'summary':'','glossary':[],'cuts':[{'id':'c','start':1,'end':1.5,'enabled':True,'locked':True}],'pauses':[{'id':'start','at':0,'duration':1},{'id':'join','at':1.5,'duration':2},{'id':'end','at':3,'duration':.5}],'lessons':[{'id':'l','start':0,'end':3,'vi':'Xin chào','en':'Hello','chunks':[],'photo_query':'','asset_id':None,'locked':True}],'captions':[{'id':'cap','start':0,'end':3,'vi':'Xin chào','en':'Hello','locked':True}],'visuals':[]}
class SilenceTests(unittest.TestCase):
 def test_mapping_freezes_at_start_join_end_and_shifts_subtitles(self):
  p=validate_plan(base(),3);spans=assembly_spans(3,p['cuts'],p['pauses'])
  self.assertAlmostEqual(spans[-1]['output_end'],6)
  self.assertEqual(map_interval(0,3,spans),[(1,2),(4,5.5)])
  self.assertAlmostEqual(output_to_source(2.5,spans),29/30)
  self.assertEqual(output_to_source(.5,spans),0)
  self.assertAlmostEqual(output_to_source(5.8,spans),3-1/30)
 def test_invalid_pause_data_rejected_and_old_plan_defaults_empty(self):
  for pauses in [[{'id':'x','at':4,'duration':2}],[{'id':'x','at':0,'duration':float('nan')}],[{'id':'x','at':0,'duration':0}],[{'id':'x','at':0,'duration':2}]*2]:
   with self.assertRaises((ValueError,ValidationError)):validate_plan({**base(),'pauses':pauses},3)
  p=base();p.pop('pauses');self.assertEqual(validate_plan(p,3)['pauses'],[])
 def test_real_export_freezes_picture_mutes_music_and_keeps_subtitles_out(self):
  with TemporaryDirectory() as tmp:
   root=Path(tmp)
   ffmpeg(['-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=3','-f','lavfi','-i','sine=frequency=440:duration=3','-shortest','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',root/'source.mp4'])
   ffmpeg(['-f','lavfi','-i','sine=frequency=220:duration=3',root/'music.wav'])
   before=hashlib.sha256((root/'source.mp4').read_bytes()).hexdigest()
   p={'id':'synthetic','title':'Silence test','source_file':'source.mp4','metadata':{'duration':3,'width':320,'height':180},'revision':1,'assets':{},'frames':[],'music_file':'music.wav','options':Options(ratio='16:9',layout_mode='lesson',landscape_layout='circle',video_frames={'16:9':{}},auto_volume=False,sfx=True,background_removal={'enabled':False}).model_dump()}
   context=Mock();context.folder=root;context.kind='export';r=render_lessons(p,validate_plan(base(),3),{},context,True);path=root/r['file']
   self.assertAlmostEqual(probe(path)['duration'],6,delta=.08)
   ffmpeg(['-xerror','-i',path,'-f','null','-'])
   for i,t in enumerate([2.3,3.3]):ffmpeg(['-ss',t,'-i',path,'-frames:v',1,root/f'frame{i}.png'])
   with Image.open(root/'frame0.png') as a,Image.open(root/'frame1.png') as b:self.assertLess(np.abs(np.asarray(a,dtype=float)-np.asarray(b,dtype=float)).mean(),1)
   ffmpeg(['-ss','2.3','-t','1.3','-i',path,'-vn','-ac','1','-ar','16000','-f','s16le',root/'quiet.pcm'])
   self.assertLess(np.abs(np.frombuffer((root/'quiet.pcm').read_bytes(),dtype='<i2').astype(np.int32)).max(),10)
   srt=(root/r['folder']/'subtitles.vi.srt').read_text('utf-8-sig');self.assertIn('00:00:01,000 --> 00:00:02,000',srt);self.assertIn('00:00:04,000 --> 00:00:05,500',srt)
   self.assertEqual(hashlib.sha256((root/'source.mp4').read_bytes()).hexdigest(),before)
