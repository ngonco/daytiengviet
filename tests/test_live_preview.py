import base64
import copy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from PIL import Image,ImageChops
from fastapi.testclient import TestClient
from backend.app import app,Options
from backend import store
from backend.templates import geometry,make_frame,subtitle_region,subtitle_position,brand
from backend.lesson_render import subtitle_image


class LivePreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.mock=patch('backend.store.data_root',return_value=Path(self.tmp.name));self.mock.start();store.init()
        self.id='5123456789abcdef';self.folder=store.folder(self.id);(self.folder/'assets').mkdir()
        Image.new('RGB',(800,300),'#8BA9BA').save(self.folder/'assets/p.jpg')
        self.lesson={'id':'l','start':0,'end':10,'vi':'Xin chào!','en':'Hello!','chunks':[],'asset_id':'p','photo_query':'hello','locked':True}
        self.plan={'schema_version':2,'lessons':[self.lesson],'cuts':[],'captions':[{'id':'c','start':0,'end':5,'vi':'Lặp lại','en':'Repeat','locked':True}],'visuals':[]}
        self.options=Options(layout_mode='lesson',background_removal={'enabled':False}).model_dump()
        store.save({'id':self.id,'title':'Live test','metadata':{'width':720,'height':1290,'duration':10},'source_file':'source.mp4','revision':1,'options':self.options,'assets':{'p':{'file':'p.jpg'}},'plan':self.plan,'frames':[]})
        self.client=TestClient(app)
    def tearDown(self):self.mock.stop();self.tmp.cleanup()
    def request(self,**fields):
        return self.client.post(f'/api/projects/{self.id}/preview-scene',json={'sequence':1,'lesson':self.lesson,'caption':self.plan['captions'][0],'options':self.options,**fields})
    def test_scene_uses_export_template_and_correct_subtitle_region(self):
        for ratio in ['9:16','16:9']:
            result=self.request(options={**self.options,'ratio':ratio});self.assertEqual(result.status_code,200,result.text);scene=result.json();w,h=scene['width'],scene['height']
            expected=make_frame(store.read(self.id),self.lesson,self.folder,w,h)
            actual=Image.open(io.BytesIO(base64.b64decode(scene['page'].split(',')[1]))).convert('RGB')
            self.assertIsNone(ImageChops.difference(expected,actual).getbbox())
            rect=scene['subtitle_rect'];region=subtitle_region(w,h)
            self.assertGreaterEqual(rect[0],region[0]);self.assertGreaterEqual(rect[1],region[1]);self.assertLessEqual(rect[1]+rect[3],region[1]+region[3])
            g=geometry(w,h)
            if ratio=='9:16':self.assertLess(g['photo'][1],g['content'][1]);self.assertLess(g['content'][1],g['speaker'][1])
    def test_edits_are_read_only_do_not_bill_or_create_jobs_and_echo_sequence(self):
        before=store.read(self.id)
        with patch('backend.providers.chat',side_effect=AssertionError('No AI while editing')):
            first=self.request().json();changed=self.request(sequence=91,lesson={**self.lesson,'vi':'Cảm ơn!','en':'Thank you!','photo_crops':{'9:16':{'zoom':2}}}).json()
        self.assertNotEqual(first['page'],changed['page']);self.assertEqual(changed['sequence'],91)
        self.assertEqual(store.read(self.id),before);self.assertEqual(store.jobs(self.id),[]);self.assertFalse((self.folder/'versions').exists())
    def test_subtitle_changes_do_not_change_page_and_empty_draft_is_allowed(self):
        a=self.request().json();b=self.request(caption={'vi':'Xin chào','en':'Hello'}).json()
        self.assertEqual(a['page'],b['page']);self.assertNotEqual(a['subtitle'],b['subtitle'])
        r=self.request(lesson={**self.lesson,'vi':'','en':''},caption={'vi':'','en':''});self.assertEqual(r.status_code,200,r.text)
    def test_save_without_render_records_history_and_conflict_but_no_job(self):
        body={'revision':1,'plan':self.plan,'options':self.options,'render_preview':False}
        r=self.client.put(f'/api/projects/{self.id}/plan',json=body);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['revision'],2);self.assertEqual(store.jobs(self.id),[]);self.assertTrue((self.folder/'versions/v00001.json').exists())
        self.assertEqual(self.client.put(f'/api/projects/{self.id}/plan',json=body).status_code,409)
    def test_stale_matting_is_explicit_and_missing_assets_rejected(self):
        options={**self.options,'background_removal':{**self.options['background_removal'],'enabled':True}}
        r=self.request(options=options);self.assertEqual(r.json()['source']['state'],'pending')
        self.assertEqual(self.request(lesson={**self.lesson,'asset_id':'unknown'}).status_code,400)
    def test_warm_preview_typical_response_within_300ms(self):
        self.request();started=time.perf_counter();r=self.request(sequence=2)
        self.assertEqual(r.status_code,200);self.assertLess(time.perf_counter()-started,.3)

    def test_preview_boxes_are_exact_half_scale_of_export(self):
        for w,h in [(1080,1920),(1920,1080)]:
            full=geometry(w,h);small=geometry(w//2,h//2)
            for region in ['photo','content','speaker','brand']:
                self.assertEqual(small[region],tuple(v//2 for v in full[region]))

    def test_long_vietnamese_three_chunks_and_different_photo_aspects(self):
        lesson={**self.lesson,'vi':'Cho tôi một ly cà phê sữa đá, ít đường nhé.',
                'en':"I'd like an iced coffee with milk and less sugar, please.",
                'chunks':[{'vi':'Cho tôi','en':"I'd like"},{'vi':'một ly','en':'a cup'},{'vi':'cà phê','en':'coffee'}]}
        for size in [(300,800),(800,300),(400,400)]:
            Image.new('RGB',size,'#8BA9BA').save(self.folder/'assets/p.jpg')
            for ratio in ['9:16','16:9']:
                r=self.request(lesson=lesson,options={**self.options,'ratio':ratio})
                self.assertEqual(r.status_code,200,r.text)
        a=self.request().json()
        b=self.request(options={**self.options,'speaker_x':.9,'speaker_y':.9,'speaker_scale':1.4}).json()
        self.assertNotEqual(a['speaker_transform'],b['speaker_transform'])


if __name__=='__main__':unittest.main()
