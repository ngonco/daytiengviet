import copy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from PIL import Image
from fastapi.testclient import TestClient
from backend import store
from backend.app import app,Options
from backend.photo_layout import cover,layout
from backend.photo_pools import prepare_pool,prepare_all,apply_pool,ranked_candidates
from backend.timeline import Lesson,validate_plan
from backend.media import Cancelled


def lesson(**fields):return Lesson(id='l',start=0,end=2,vi='Xin chào',en='Hello',photo_query='people greeting',**fields).model_dump()
def candidates(n=16):return [{'id':str(i),'alt':'people waving hello','width':1600,'height':1200,'preview':'https://example.test/thumb','download':'https://example.test/full'} for i in range(n)]


class Context:
    def __init__(self,folder):self.folder=folder
    def check(self):pass
    def progress(self,*args):pass


def downloader(p,folder,context=None):
    path=folder/'assets';path.mkdir(exist_ok=True)
    Image.new('RGB',(200,120),(int(p['id'])%255,80,40)).save(path/(p['id']+'.jpg'))
    return {**p,'id':'pexels-'+p['id'],'file':p['id']+'.jpg','provider':'pexels','photographer':'Test'}


class PhotoPoolTests(unittest.TestCase):
    def test_template_honors_crop_in_both_ratios_without_blurred_edges(self):
        from backend.templates import make_frame,geometry
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'assets').mkdir();im=Image.new('RGB',(800,200),'blue');im.paste('red',(0,0,400,200));im.save(folder/'assets/stripes.png')
            p={'assets':{'p':{'file':'stripes.png'}}}
            for w,h,key in [(540,960,'9:16'),(960,540,'16:9')]:
                x,y,pw,ph=geometry(w,h)['photo']
                for position,color in [(0,(255,0,0)),(1,(0,0,255))]:
                    l=lesson(asset_id='p',photo_crops={key:{'x':position,'y':.5,'zoom':3}})
                    make_frame(p,l,folder,w,h,folder/'frame.png')
                    with Image.open(folder/'frame.png') as output:
                        for xx,yy in [(x+pw//2,y+ph//2),(x+pw//5,y+ph//2),(x+pw*4//5,y+ph//2)]:self.assertEqual(output.getpixel((xx,yy)),color)

    def test_cover_geometry_for_all_aspects_and_zoom(self):
        for source in [(320,800),(800,320),(400,400)]:
            im=Image.new('RGB',source,'#0a8c46')
            for size in [(988,580),(1180,448)]:
                for crop in [{},{'x':0,'y':1,'zoom':3},{'x':1,'y':0,'zoom':1}]:
                    output=cover(im,size,crop)
                    self.assertEqual(output.size,size)
                    self.assertEqual(output.getextrema(),((10,10),(140,140),(70,70)))
                    g=layout(*source,*size,crop.get('zoom',1))
                    self.assertGreaterEqual(g['scaled_width'],size[0]);self.assertGreaterEqual(g['scaled_height'],size[1])
                    self.assertAlmostEqual(g['scaled_width']/source[0],g['scaled_height']/source[1],delta=.004)
        im=Image.new('RGB',(800,200),'blue');im.paste('red',(0,0,400,200))
        self.assertEqual(cover(im,(100,200),{'x':0}).getpixel((50,100)),(255,0,0))
        self.assertEqual(cover(im,(100,200),{'x':1}).getpixel((50,100)),(0,0,255))

    def test_schema_defaults_and_invalid_crop_pool(self):
        self.assertEqual(lesson()['photo_candidates'],[])
        for extra in [{'photo_candidates':['x']*2},{'photo_candidates':[str(i) for i in range(11)]},{'photo_crops':{'9:16':{'zoom':.5}}},{'photo_crops':{'16:9':{'x':float('nan')}}},{'photo_crops':{'bad':{}}}]:
            with self.assertRaises(ValueError):lesson(**extra)

    def test_cancel_resume_keeps_downloads_and_ranking(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);ctx=Context(folder);l=lesson();done=[]
            def download(p,*args,**kwargs):
                if len(done)==3:raise Cancelled()
                done.append(p['id']);return downloader(p,*args,**kwargs)
            with patch('backend.providers.search_photos',return_value=candidates()),patch('backend.photo_pools.ranked_candidates',side_effect=lambda l,c,*args:c) as rank,patch('backend.providers.download_photo',side_effect=download):
                with self.assertRaises(Cancelled):prepare_pool({'assets':{}},l,ctx)
                self.assertEqual(rank.call_count,1)
            with patch('backend.providers.search_photos',side_effect=AssertionError('Cached query')),patch('backend.photo_pools.ranked_candidates',side_effect=AssertionError('Cached ranking')),patch('backend.providers.download_photo',side_effect=downloader) as download:
                assets,ids,notes=prepare_pool({'assets':{}},l,ctx)
                self.assertEqual(len(ids),10);self.assertEqual(download.call_count,7)
                self.assertTrue(all(i in assets for i in ids))

    def test_partial_failure_deduplicates_and_preserves_selection(self):
        with TemporaryDirectory() as tmp:
            ctx=Context(Path(tmp));l=lesson(asset_id='custom',locked=True);assets={'custom':{'file':'mine.jpg'}}
            with patch('backend.providers.search_photos',return_value=candidates(2)*2),patch('backend.photo_pools.ranked_candidates',side_effect=ValueError()),patch('backend.providers.download_photo',side_effect=downloader):
                found,ids,notes=prepare_pool({'assets':assets},l,ctx)
            self.assertEqual(len(ids),2);self.assertTrue(any('2/10' in n for n in notes))
            apply_pool(l,ids,found);self.assertEqual(l['asset_id'],'custom');self.assertTrue(l['locked'])
            apply_pool(l,[],found);self.assertEqual(l['photo_candidates'],ids)

    def test_refresh_excludes_current_set(self):
        with TemporaryDirectory() as tmp:
            ctx=Context(Path(tmp));l=lesson(photo_candidates=['pexels-'+str(i) for i in range(10)])
            with patch('backend.providers.search_photos',return_value=candidates(30)),patch('backend.photo_pools.ranked_candidates',side_effect=lambda l,c,*args:c),patch('backend.providers.download_photo',side_effect=downloader):
                _,ids,_=prepare_pool({'assets':{}},l,ctx,'refresh-test',True)
            self.assertEqual(len(ids),10);self.assertFalse(set(ids)&set(l['photo_candidates']))

    def test_recurring_target_reuses_set_but_keeps_manual_selection(self):
        with TemporaryDirectory() as tmp:
            ctx=Context(Path(tmp));rows=[lesson(),{**lesson(asset_id='custom',locked=True),'id':'repeat'}]
            with patch('backend.providers.search_photos',return_value=candidates()),patch('backend.photo_pools.ranked_candidates',side_effect=lambda l,c,*args:c),patch('backend.providers.download_photo',side_effect=downloader) as download:
                prepare_all({'assets':{'custom':{'file':'mine.jpg'}}},{'lessons':rows},ctx)
            self.assertEqual(download.call_count,10);self.assertEqual(rows[0]['photo_candidates'],rows[1]['photo_candidates']);self.assertEqual(rows[1]['asset_id'],'custom')

    def test_ranking_uses_only_known_unique_ids(self):
        with TemporaryDirectory() as tmp,patch('backend.providers.chat',return_value=(json.dumps({'ordered_ids':['2','unknown','2','1']}),{})):
            result=ranked_candidates(lesson(),candidates(4),Context(Path(tmp)),False)
            self.assertEqual([p['id'] for p in result],['2','1','0','3'])

    def test_network_failure_keeps_existing_selection_and_pool(self):
        with TemporaryDirectory() as tmp:
            l=lesson(asset_id='old',photo_candidates=['old'],photo_crops={'9:16':{'zoom':1.5}});original=copy.deepcopy(l)
            with patch('backend.providers.search_photos',side_effect=__import__('backend.providers',fromlist=['ProviderError']).ProviderError('Pexels',429)):
                with self.assertRaises(RuntimeError):prepare_pool({'assets':{'old':{'file':'old.jpg'}}},l,Context(Path(tmp)),'retry',True)
            self.assertEqual(l,original)

    def test_local_selection_and_zip_keep_pool_crops_and_versions(self):
        import zipfile
        from backend.media import ffmpeg
        with TemporaryDirectory() as tmp,patch('backend.store.data_root',return_value=Path(tmp)):
            store.init();pid='4123456789abcdef';folder=store.folder(pid);assets={}
            for c in candidates(10):
                a=downloader(c,folder);assets[a['id']]=a
            ffmpeg(['-f','lavfi','-i','color=c=blue:s=64x64:r=30','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',2,'-c:v','libx264','-c:a','aac',folder/'source.mp4'])
            plan=validate_plan({'schema_version':2,'lessons':[lesson(asset_id='pexels-0',photo_candidates=list(assets))]},2)
            options=Options(layout_mode='lesson').model_dump()
            store.save({'id':pid,'title':'Portable pool','created_at':'2000-01-01T00:00:00Z','metadata':{'duration':2,'width':64,'height':64},'source_file':'source.mp4','options':options,'revision':1,'plan':plan,'assets':assets,'preview':{'file':'placeholder.mp4'}})
            client=TestClient(app);plan=copy.deepcopy(plan);l=plan['lessons'][0]
            l.update(asset_id='pexels-3',locked=True,photo_crops={'9:16':{'x':.2,'y':.8,'zoom':2},'16:9':{'x':.7,'y':.3,'zoom':1.2}})
            with patch('backend.providers.search_photos',side_effect=AssertionError('Offline selection')),patch('backend.providers.chat',side_effect=AssertionError('Offline selection')):
                r=client.put(f'/api/projects/{pid}/plan',json={'revision':1,'plan':plan,'options':options});self.assertEqual(r.status_code,200,r.text)
                for job in store.jobs(pid):store.job_update(job['id'],status='succeeded')
                archive=client.get(f'/api/projects/{pid}/download/project');self.assertEqual(archive.status_code,200)
                imported=client.post('/api/projects/import',files={'file':('p.zip',archive.content,'application/zip')});self.assertEqual(imported.status_code,200,imported.text)
            self.assertEqual(imported.json()['plan']['lessons'][0],l)
            self.assertEqual(imported.json()['origin_created_at'],'2000-01-01T00:00:00Z')
            self.assertNotEqual(imported.json()['created_at'],'2000-01-01T00:00:00Z')
            with zipfile.ZipFile(io.BytesIO(archive.content)) as zip:
                self.assertEqual(len([n for n in zip.namelist() if n.startswith('assets/')]),10)
                self.assertIn('versions/v00001.json',zip.namelist())
            r=client.post(f'/api/projects/{pid}/restore',json={'revision':1});self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(r.json()['plan']['lessons'][0]['asset_id'],'pexels-0')
            self.assertEqual(r.json()['plan']['lessons'][0]['photo_candidates'],list(assets))

    def test_api_pool_revision_crop_and_old_project_read_no_provider(self):
        with TemporaryDirectory() as tmp,patch('backend.store.data_root',return_value=Path(tmp)):
            store.init();pid='3123456789abcdef';folder=store.folder(pid);(folder/'assets').mkdir();Image.new('RGB',(320,800),'red').save(folder/'assets/p.jpg')
            plan=validate_plan({'schema_version':2,'lessons':[lesson(asset_id='p')]},2)
            store.save({'id':pid,'metadata':{'duration':2,'width':720,'height':1290},'options':Options(layout_mode='lesson').model_dump(),'revision':1,'plan':plan,'assets':{'p':{'file':'p.jpg'}}})
            client=TestClient(app)
            with patch('backend.providers.search_photos',side_effect=AssertionError('Reading must not fetch photos')):
                self.assertEqual(client.get(f'/api/projects/{pid}').status_code,200)
                geometry=client.get(f'/api/projects/{pid}/photo-layout',params={'asset_id':'p','ratio':'9:16','zoom':2}).json()
            self.assertEqual(geometry,dict(layout(320,800,988,566,2),crop_key='9:16'))
            self.assertEqual(client.post(f'/api/projects/{pid}/lessons/l/photo-candidates',json={'revision':0}).status_code,422)
            self.assertEqual(client.post(f'/api/projects/{pid}/lessons/l/photo-candidates',json={'revision':2}).status_code,409)
            job=client.post(f'/api/projects/{pid}/lessons/l/photo-candidates',json={'revision':1,'refresh':True}).json()
            self.assertEqual(job['kind'],'lesson_photos');req=json.loads(job['request']);store.job_update(job['id'],status='cancelled')
            retry=client.post(f"/api/jobs/{job['id']}/retry").json();self.assertEqual(json.loads(retry['request']),req)


if __name__=='__main__':unittest.main()
