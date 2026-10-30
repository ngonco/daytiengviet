import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
from backend.timeline import keep_spans,map_interval,source_to_output,output_to_source,validate_plan,cue_words
from backend.render import write_srt,write_ass,card_image
from backend.providers import parse_json
from backend.app import app

class TimelineTests(unittest.TestCase):
    def test_merge_cuts_and_restore_translation_timing(self):
        cuts=[{'start':2,'end':4,'enabled':True},{'start':3,'end':5,'enabled':True},{'start':7,'end':8,'enabled':False}]
        spans=keep_spans(10,cuts)
        self.assertEqual([(s['start'],s['end']) for s in spans],[(0,2),(5,10)])
        self.assertEqual(map_interval(1,6,spans),[(1,2),(2,3)])
        for time in [0,.2,1.9,5.1,7,9.9]:
            self.assertAlmostEqual(output_to_source(source_to_output(time,spans),spans),time)
        cuts[0]['enabled']=False;cuts[1]['enabled']=False
        self.assertEqual(map_interval(1,6,keep_spans(10,cuts)),[(1,6)])

    def test_reject_invalid_ai_plan(self):
        for plan in [{'cuts':[{'id':'x','start':0,'end':12}]},{'cuts':[{'id':'x','start':0,'end':10}]},{'captions':[{'id':'x','start':3,'end':2,'vi':'x'}]},{'visuals':[{'id':'x','start':0,'end':3,'x':float('nan')}]}]:
            with self.assertRaises(ValueError):validate_plan(plan,10)

    def test_repetition_is_not_removed_by_cue_creation(self):
        words=[{'word':'ma','start':i*.5,'end':i*.5+.4} for i in range(5)]
        self.assertEqual(' '.join(c['vi'] for c in cue_words(words)),'ma ma ma ma ma')

    def test_json_fences(self):
        self.assertEqual(parse_json('```json\n{"cuts": []}\n```'),{'cuts':[]})

    def test_srt_and_visual_text_handle_vietnamese(self):
        p={'metadata':{'duration':10,'width':720,'height':1280},'options':{'subtitles':'bilingual'},'assets':{}}
        plan={'cuts':[{'id':'cut','start':2,'end':4,'enabled':True}],'captions':[{'id':'c','start':5,'end':6,'vi':'Xin chào Việt Nam!','en':'Hello, Vietnam!'}]}
        with TemporaryDirectory() as tmp:
            folder=Path(tmp)
            write_srt(p,plan,folder)
            self.assertIn('00:00:03,000 --> 00:00:04,000',(folder/'subtitles.vi.srt').read_text(encoding='utf-8-sig'))
            write_ass(p,plan,{},keep_spans(10,plan['cuts']),0,8,540,960,folder/'test.ass')
            self.assertIn('Xin chào',(folder/'test.ass').read_text(encoding='utf-8-sig'))
            result=card_image(p,{'kind':'vocab','layout':'card','start':0,'text':'Dấu hỏi, dấu ngã','translation':'Vietnamese tones','scale':1,'x':None,'y':None},folder,540,960,folder/'card.png')
            self.assertTrue((folder/'card.png').stat().st_size>1000)
            self.assertGreater(result[0],100)

class ApiTests(unittest.TestCase):
    def setUp(self):self.client=TestClient(app)
    def test_settings_never_exposes_keys(self):
        data=self.client.get('/api/settings').json()
        self.assertNotIn('API_KEY',str(data))
        self.assertTrue(all(isinstance(v,bool) for v in data['configured'].values()))
    def test_origin_rejected(self):
        self.assertEqual(self.client.post('/api/settings/check',headers={'Origin':'https://example.com'}).status_code,403)
    def test_host_rejected(self):
        self.assertEqual(self.client.get('/api/health',headers={'Host':'evil.example'}).status_code,403)
    def test_sample_cannot_escape_workspace(self):
        response=self.client.post('/api/projects/sample',json={'filename':'../secret.mp4'})
        self.assertEqual(response.status_code,404)

if __name__=='__main__':unittest.main()
