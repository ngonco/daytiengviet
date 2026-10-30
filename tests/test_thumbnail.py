import copy
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from PIL import Image
from fastapi.testclient import TestClient
from backend.app import app
from backend import store
from backend.thumbnail import render_thumbnail


class ThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.mock=patch('backend.store.data_root',return_value=Path(self.tmp.name));self.mock.start();store.init()
        self.id='6123456789abcdef';self.folder=store.folder(self.id);(self.folder/'assets').mkdir()
        for name,size in [('wide',(900,300)),('tall',(300,900))]:
            image=Image.new('RGB',size,'orange');image.paste('blue',(0,0,size[0]//2,size[1]));image.save(self.folder/'assets'/f'{name}.png')
        self.project={'id':self.id,'title':'Thumbnail test','revision':1,'plan':{'lessons':[{'id':'first','vi':'Xin chào!','en':'Hello!','asset_id':'wide'},{'id':'second','vi':'Cảm ơn','en':'Thank you','asset_id':'tall'}]},'assets':{k:{'file':k+'.png'} for k in ['wide','tall']}}
        store.save(self.project);self.client=TestClient(app);self.url=f'/api/projects/{self.id}/thumbnail'
    def tearDown(self):
        self.mock.stop();self.tmp.cleanup()
    def body(self,**changes):
        return {'lesson_id':'second','en':'Thank you','vi':'Cảm ơn','asset_id':'tall','crop':{'x':.5,'y':.5,'zoom':1},**changes}
    def test_routes_preview_download_and_no_mutation(self):
        before=copy.deepcopy(store.read(self.id))
        with patch('backend.providers.chat',side_effect=AssertionError('No providers')):
            response=self.client.post(self.url,json=self.body())
            self.assertEqual(response.status_code,200,response.text[:200] if response.status_code!=200 else '')
            self.assertEqual(response.content,render_thumbnail(before,self.folder,self.body()))
            self.assertEqual(Image.open(io.BytesIO(response.content)).size,(1280,720))
            self.assertEqual(self.client.get(self.url).content,render_thumbnail(before,self.folder))
        self.assertEqual(store.read(self.id),before);self.assertEqual(store.jobs(self.id),[])
    def test_crop_both_aspects_and_fixed_frame(self):
        for asset in ['wide','tall']:
            a=Image.open(io.BytesIO(render_thumbnail(self.project,self.folder,self.body(asset_id=asset,crop={'x':0,'y':0,'zoom':2}))))
            b=Image.open(io.BytesIO(render_thumbnail(self.project,self.folder,self.body(asset_id=asset,crop={'x':1,'y':1,'zoom':2}))))
            self.assertNotEqual(a.crop((710,112,1240,674)).tobytes(),b.crop((710,112,1240,674)).tobytes())
            self.assertEqual(a.getpixel((0,0)),b.getpixel((0,0)))
    def test_invalid_inputs_and_missing_lessons(self):
        for body in [self.body(en=''),self.body(asset_id='foreign'),self.body(lesson_id='missing'),self.body(en='a'*1000),self.body(crop={'zoom':4}),self.body(en='Long sentence '*60)]:
            self.assertEqual(self.client.post(self.url,json=body).status_code,422)
        self.project['plan']['lessons']=[];store.save(self.project)
        self.assertEqual(self.client.get(self.url).status_code,422)
    def test_path_escape_and_missing_file(self):
        for filename in ['../../outside.png','missing.png']:
            self.project['assets']['tall']['file']=filename;store.save(self.project)
            self.assertEqual(self.client.post(self.url,json=self.body()).status_code,422)

if __name__=='__main__':unittest.main()
