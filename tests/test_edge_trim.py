import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock,patch

from backend import store,worker
from backend.app import Options,frame_geometry
from backend.media import ffmpeg
from backend.recut import trim_edge_plan,trim_edges,recut,quiet_intervals
from backend.timeline import keep_spans


def plan(duration=12):
    return {'schema_version':2,'summary':'Synthetic','glossary':[],'cuts':[],
            'lessons':[{'id':'l','start':0,'end':duration,'vi':'Xin chào','en':'Hello','chunks':[],'photo_query':'greeting','asset_id':None}],
            'captions':[{'id':'c','start':2,'end':3,'vi':'Xin chào','en':'Hello'}],'visuals':[],
            'pauses':[{'id':'hold','at':6,'duration':2}]}


class EdgeTrimTests(unittest.TestCase):
    def test_inclusive_half_second_threshold_margin_and_interior_pause_preservation(self):
        p=plan()
        p['cuts']=[{'id':'manual','start':4,'end':5,'enabled':True,'locked':True}]
        before=copy.deepcopy(p)
        for strength in ['light','medium','strong']:
            self.assertEqual(trim_edge_plan(p,12,[(0,.499),(11.501,12)],strength),p)
            result=trim_edge_plan(p,12,[(0,.5),(3,9),(11.5,12)],strength)
            edges=[c for c in result['cuts'] if c['id'].startswith('edge-trim-')]
            self.assertEqual([(c['start'],c['end']) for c in edges],[(0,.3),(11.7,12)])
            self.assertEqual([c for c in result['cuts'] if c['id']=='manual'],p['cuts'])
            self.assertEqual({k:v for k,v in result.items() if k!='cuts'},{k:v for k,v in p.items() if k!='cuts'})
            self.assertEqual(trim_edge_plan(result,12,[(0,.5),(3,9),(11.5,12)],strength),result)
        self.assertEqual(p,before)

    def test_silent_source_none_and_restored_manual_edits_are_preserved(self):
        p=plan()
        self.assertEqual(trim_edge_plan(p,12,[(0,12)]),p)
        self.assertEqual(trim_edge_plan(p,12,[(0,2),(10,12)],'none'),p)
        p['cuts']=[{'id':'restored','start':0,'end':2,'enabled':False,'locked':True}]
        self.assertEqual(trim_edge_plan(p,12,[(0,2)]),p)
        p['cuts'][0]['enabled']=True
        result=trim_edge_plan(p,12,[(0,3)])
        self.assertEqual(result['cuts'][0],p['cuts'][0])
        self.assertAlmostEqual(keep_spans(12,result['cuts'])[0]['start'],2.8)

    def test_edge_only_job_versions_changes_and_never_calls_providers_or_renderers(self):
        with TemporaryDirectory() as tmp,patch.object(store,'data_root',return_value=Path(tmp)):
            store.init();pid=store.uid();p=plan()
            project={'id':pid,'title':'Synthetic','options':Options(layout_mode='lesson').model_dump(),'metadata':{'duration':12,'width':320,'height':180},'plan':p,'source_file':'source.wav','revision':3,'assets':{},'export':{'file':'old.mp4','revision':3}}
            store.save(project);before=store.read(pid)
            with patch('backend.recut.quiet_intervals',return_value=[(0,2),(4,8),(10,12)]),patch('backend.providers.chat',side_effect=AssertionError('No provider')),patch('backend.worker.prepared_render',side_effect=AssertionError('No render')):
                job=store.job_create(pid,'trim_edges');worker.execute(job);store.job_update(job['id'],status='succeeded')
                current=store.read(pid)
                self.assertEqual(current['revision'],4)
                self.assertEqual(current['export'],before['export'])
                self.assertEqual(current['options'],before['options'])
                self.assertEqual({k:v for k,v in current['plan'].items() if k!='cuts'},{k:v for k,v in before['plan'].items() if k!='cuts'})
                self.assertEqual(json.loads((store.folder(pid)/'versions/v00003.json').read_text(encoding='utf-8'))['plan'],p)
                report=json.loads((store.folder(pid)/'analysis/edge-trim/v00003-policy1.json').read_text(encoding='utf-8'))
                self.assertEqual(report['minimum'],.5);self.assertEqual(len(report['edge_cuts']),2)
                retry=store.job_create(pid,'trim_edges');worker.execute(retry)
                self.assertEqual(store.read(pid)['revision'],4)

    def test_initial_recut_uses_measured_edges_despite_coarse_stt_without_ai(self):
        with TemporaryDirectory() as tmp:
            p={'plan':plan(),'options':{'cut_strength':'strong'},'metadata':{'duration':12},'source_file':'source.wav',
               'transcript':{'words':[{'word':'Xin chào','start':0,'end':12}]}}
            context=Mock(folder=Path(tmp))
            with patch('backend.recut.quiet_intervals',return_value=[(0,2),(4,8),(10,12)]),patch('backend.providers.chat',side_effect=AssertionError('No semantic review for edges')):
                result=recut(p,context)
            self.assertEqual([(c['start'],c['end']) for c in result['cuts']],[(0,1.8),(10.2,12)])

    def test_real_audio_measurement_and_render_share_edge_map_and_original_is_unchanged(self):
        import hashlib
        from backend.render import render,write_srt
        from backend.media import probe
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);source=folder/'source.mp4'
            ffmpeg(['-f','lavfi','-i','color=c=blue:s=160x90:r=30:d=4','-f','lavfi','-i','sine=frequency=440:duration=4',
                    '-af',"volume=volume=0:enable='lt(t,1)+gte(t,3)'",'-c:v','libx264','-c:a','aac','-shortest',source])
            original=hashlib.sha256(source.read_bytes()).hexdigest()
            p=plan(4);p['pauses']=[];p['captions'][0].update(start=1,end=2)
            intervals=quiet_intervals(source,None);trimmed=trim_edge_plan(p,4,intervals)
            self.assertEqual(len(trimmed['cuts']),2)
            spans=keep_spans(4,trimmed['cuts']);expected=sum(s['end']-s['start'] for s in spans)
            self.assertAlmostEqual(expected,2.4,delta=.1)
            project={'id':'synthetic','title':'Synthetic','metadata':{'duration':4,'width':160,'height':90},'source_file':'source.mp4','assets':{},'revision':2,
                     'options':Options(ratio='16:9',layout_mode='legacy',sfx=False,auto_volume=False).model_dump()}
            context=Mock(folder=folder,kind='export');result=render(project,trimmed,{},context,True)
            self.assertAlmostEqual(probe(folder/result['file'])['duration'],expected,delta=.1)
            ffmpeg(['-xerror','-i',folder/result['file'],'-f','null','-'])
            write_srt(project,trimmed,folder)
            self.assertIn('00:00:00,200',(folder/'subtitles.vi.srt').read_text(encoding='utf-8-sig'))
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),original)

    def test_saved_preview_geometry_matches_server_for_both_orientations_and_layouts(self):
        from backend.render import dimensions
        from backend.templates import geometry
        for ratio in ['9:16','16:9','original']:
            for layout in ['circle','classic']:
                p={'options':Options(ratio=ratio,portrait_layout=layout,landscape_layout=layout).model_dump(),'metadata':{'width':720,'height':1280}}
                with patch.object(store,'read',return_value=p):result=frame_geometry('synthetic')
                w,h=dimensions(p,True)
                self.assertEqual(result,{'width':w,'height':h,'geometry':geometry(w,h,p['options'])})


if __name__=='__main__':unittest.main()
