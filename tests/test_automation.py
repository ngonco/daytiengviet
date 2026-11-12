import copy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch,Mock

from fastapi.testclient import TestClient
from backend import store,automation,worker
from backend.app import app,Options,create
from backend.seo import lesson_title,video_filename
from backend.providers import ProviderError
from scripts.matting_runner import read_exact,validate_eof,BufferedFrames,BufferedWriter,source_video_end


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.data=self.root/'private';self.data.mkdir()
        self.source=self.root/'sources';self.source.mkdir()
        self.patch=patch('backend.store.data_root',return_value=self.data);self.patch.start();self.addCleanup(self.patch.stop)
        store.init();automation.OBSERVED.clear();automation.LAST_SCAN=0;automation.SCAN_UNTIL=0
        automation.configure(str(self.source),False)
    def input(self,name='a.mp4',content=b'unique source'):
        p=self.source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content);return p
    def scan(self):
        automation.scan(force=True,at=100);automation.scan(force=True,at=111)
    def test_stability_recursive_content_dedup_and_outputs(self):
        self.input('nested/a.mp4');automation.scan(force=True,at=100)
        self.assertEqual(automation.items(),[])
        automation.scan(force=True,at=109);self.assertEqual(automation.items(),[])
        automation.scan(force=True,at=110);self.assertEqual(len(automation.items()),1)
        self.input('renamed.mp4');out=self.input('export.mp4',b'output');automation.output_record(out)
        automation.scan(force=True,at=111);automation.scan(force=True,at=122)
        self.assertEqual(len(automation.items()),1)
        self.assertEqual(len(automation.items()[0]['duplicate_paths']),1)
    def test_changed_source_gets_new_content_identity(self):
        p=self.input();self.scan();p.write_bytes(b'changed source')
        automation.scan(force=True,at=120);automation.scan(force=True,at=131)
        self.assertEqual(len(automation.items()),2)
    def test_private_data_excluded(self):
        with self.assertRaises(ValueError):automation.configure(str(self.data),True)
        (self.data/'secret.mp4').write_bytes(b'private')
        automation.configure(str(self.root),False);self.scan();self.assertEqual(automation.items(),[])
    def test_pause_and_restart_history(self):
        self.input();self.scan();before=automation.items()
        automation.dispatch();self.assertEqual(store.jobs(),[])
        store.init();automation.OBSERVED.clear();self.scan()
        self.assertEqual(automation.items(),before)
    def test_ratio_boundaries_and_direct_export_request(self):
        for duration,ratio in [(89.99,'9:16'),(90,'9:16'),(90.01,'16:9')]:
            with self.subTest(duration=duration):
                source=self.input(str(duration)+'.mp4',str(duration).encode());code=automation.digest(source)
                automation.put({'hash':code,'source':str(source),'state':'waiting','attempts':0,'created_at':str(duration)})
                automation.configure(enabled=True)
                with patch('backend.automation.probe',return_value={'duration':duration}),patch('backend.app.probe',return_value={'duration':duration,'width':320,'height':180,'fps':'30/1'}):automation.dispatch()
                row=automation.get(code);project=store.read(row['project_id'])
                self.assertEqual(project['options']['ratio'],ratio)
                self.assertFalse(project['options']['background_removal']['enabled'])
                self.assertEqual(project['options']['video_frames']['9:16']['zoom'],1)
                self.assertEqual(project['title_mode'],'auto')
                job=store.job_read(row['job_id']);self.assertEqual(json.loads(job['request'])['automation_hash'],code)
                store.job_update(job['id'],status='succeeded');row['state']='done';automation.put(row)
    def test_failed_source_does_not_block_the_next_source(self):
        self.input('a.mp4',b'bad');self.input('b.mp4',b'good');self.scan();automation.configure(enabled=True)
        with patch('backend.automation.probe',side_effect=[ValueError('Invalid video'),{'duration':10}]),patch('backend.app.probe',return_value={'duration':10,'width':320,'height':180}):
            automation.dispatch();self.assertEqual(store.jobs(),[])
            automation.dispatch();self.assertEqual(len(store.jobs()),1)
        self.assertEqual(sorted(r['state'] for r in automation.items()),['failed','running'])

    def test_background_setting_applies_to_new_automatic_projects_only(self):
        old,_=self.project();before=copy.deepcopy(store.read(old['id']))
        self.input('new.mp4',b'new source');self.scan();automation.configure(enabled=True,remove_background=True)
        with patch('backend.automation.probe',return_value={'duration':10}),patch('backend.app.probe',return_value={'duration':10,'width':320,'height':180}):automation.dispatch()
        created=next(p for p in store.listing() if p['id']!=old['id'])
        self.assertTrue(created['options']['background_removal']['enabled'])
        self.assertEqual(store.read(old['id']),before)
    def test_retry_schedule_configuration_and_cancellation(self):
        row={'hash':'a'*64,'source':str(self.input()),'state':'running','created_at':store.now()}
        with patch('backend.automation.time.time',return_value=100):
            automation.failure(row,OSError('disk'));self.assertEqual(row['retry_at'],130);self.assertEqual(row['state'],'retry_wait')
            automation.failure(row,OSError('disk'));self.assertEqual(row['retry_at'],220)
            automation.failure(row,OSError('disk'));self.assertEqual(row['state'],'failed')
        automation.retry(row['hash']);self.assertEqual(automation.get(row['hash'])['attempts'],0)
        automation.failure(row,ProviderError('Vilao',401));self.assertEqual(row['state'],'needs_attention')
        from backend.media import Cancelled
        automation.failure(row,Cancelled());self.assertEqual(row['state'],'cancelled')
    def project(self):
        pid='a'*16;folder=store.folder(pid);(folder/'source.mp4').write_bytes(b'original');(folder/'result.mp4').write_bytes(b'finished')
        p={'id':pid,'source_file':'source.mp4','title':'Bài học tiếng Việt','options':Options(layout_mode='lesson').model_dump(),'metadata':{'duration':10},'plan':{'lessons':[{'vi':'Có'}],'cuts':[]},'revision':1,'export':{'file':'result.mp4','duration':10,'digest':'cached'},'created_at':store.now()}
        store.save(p);return p,folder
    def test_publish_collision_crash_resume_and_retry_without_render(self):
        project,folder=self.project();src=self.input();code=automation.digest(src)
        (self.source/'Có - learn vietnamese.mp4').write_bytes(b'keep')
        row={'hash':code,'source':str(src),'state':'running','project_id':project['id'],'created_at':store.now()};automation.put(row)
        context=Mock();context.folder=folder
        with patch('backend.automation.ffmpeg') as validate,patch('backend.automation.probe',return_value={'duration':10}):
            automation.publish(project,context,code)
            self.assertEqual(validate.call_count,1)
            item=automation.get(code);target=Path(item['output'])
            self.assertEqual(target.name,'Có - learn vietnamese (2).mp4');self.assertEqual(target.read_bytes(),b'finished')
            item.update(state='running');automation.put(item)
            automation.publish(project,context,code);self.assertEqual(validate.call_count,1)
        self.assertEqual((self.source/'Có - learn vietnamese.mp4').read_bytes(),b'keep')
        job=store.job_create(project['id'],'auto_save',{'automation_hash':code})
        with patch('backend.automation.publish') as publish,patch('backend.worker.prepared_render',side_effect=AssertionError('must not render')),patch('backend.worker.transcribe',side_effect=AssertionError('must not transcribe')):
            worker.execute(job);publish.assert_called_once()
    def test_invalid_export_never_marks_done(self):
        # Publication must validate bytes before exposing the edited output too.
        project,folder=self.project();src=self.input();code=automation.digest(src)
        automation.put({'hash':code,'source':str(src),'state':'running'})
        with patch('backend.automation.ffmpeg',side_effect=RuntimeError('corrupt')):
            with self.assertRaises(RuntimeError):automation.publish(project,Mock(),code)
        self.assertNotEqual(automation.get(code)['state'],'done');self.assertFalse((self.source/'Có - learn vietnamese.mp4').exists())
    def test_backfill_does_not_change_existing_projects_or_finish_failed_copy(self):
        p,folder=self.project();before=copy.deepcopy(store.read(p['id']))
        with patch('backend.automation.probe',return_value={'duration':10}):automation._backfill()
        code=automation.digest(folder/'source.mp4');self.assertEqual(automation.get(code)['state'],'done')
        self.assertEqual(store.read(p['id']),before)
        row=automation.get(code);row['state']='failed';automation.put(row)
        cfg=automation.config();cfg['indexed']={}
        with store.connect() as db:db.execute('UPDATE automation_settings SET data=?',(json.dumps(cfg),))
        with patch('backend.automation.probe',return_value={'duration':10}):automation._backfill()
        self.assertEqual(automation.get(code)['state'],'failed')
        with store.connect() as db:db.execute('DELETE FROM projects WHERE id=?',(p['id'],))
        self.assertEqual(automation.get(code)['state'],'failed')
    def test_api_config_title_and_manual_override(self):
        p,_=self.project();client=TestClient(app)
        self.assertEqual(client.get('/api/automation').status_code,200)
        self.assertEqual(client.put('/api/automation',json={'enabled':True}).status_code,200)
        response=client.patch(f'/api/projects/{p["id"]}/title',json={'title':'Tên tự đặt'})
        self.assertEqual(response.status_code,200);self.assertEqual(store.read(p['id'])['title_mode'],'manual')
        self.assertEqual(client.patch(f'/api/projects/{p["id"]}/title',json={'title':'   '}).status_code,400)
    def test_automatic_pipeline_exports_without_preview_or_changing_old_titles(self):
        p,folder=self.project();p.pop('export');p['title_mode']='auto';store.save(p)
        source=self.input();code=automation.digest(source)
        job=store.job_create(p['id'],'pipeline',{'automation_hash':code})
        with patch('backend.recut.recut',side_effect=lambda project,context: project['plan']),patch('backend.worker.extract_frames',return_value=[]),patch('backend.worker.transcribe',return_value={}),patch('backend.worker.prepared_render',return_value={'file':'result.mp4','duration':10}) as render,patch('backend.automation.publish'):
            worker.execute(job);self.assertFalse(render.call_args.args[-1]);self.assertEqual(store.read(p['id'])['title'],'Có')
        store.job_update(job['id'],status='succeeded');p=store.read(p['id']);p.pop('title_mode');p['title']='Old title';store.save(p)
        job=store.job_create(p['id'],'pipeline')
        with patch('backend.recut.recut',side_effect=lambda project,context: project['plan']),patch('backend.worker.extract_frames',return_value=[]),patch('backend.worker.transcribe',return_value={}),patch('backend.worker.prepared_render',return_value={}) as render:
            worker.execute(job);self.assertTrue(render.call_args.args[-1]);self.assertEqual(store.read(p['id'])['title'],'Old title')

    def test_real_folder_pipeline_publishes_decodable_full_hd_once(self):
        from backend.media import ffmpeg,probe
        source=self.source/'lesson.mp4'
        ffmpeg(['-f','lavfi','-i','testsrc2=s=160x90:r=30','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','1','-c:v','libx264','-c:a','aac',source])
        self.scan();automation.configure(enabled=True);automation.dispatch()
        row=automation.items()[0];p=store.read(row['project_id'])
        options=p['options'];options['background_removal']['enabled']=False;options['sfx']=False
        store.update(p['id'],options=options)
        duration=p['metadata']['duration']
        plan={'schema_version':2,'summary':'Có','glossary':[],'cuts':[],'captions':[],'visuals':[],'lessons':[{'id':'lesson-0','start':0,'end':duration,'vi':'Có','en':'Yes','chunks':[],'photo_query':'','asset_id':None,'locked':False}]}
        job=store.job_read(row['job_id'])
        with patch('backend.worker.transcribe',return_value={}),patch('backend.worker.analyze',return_value=(plan,[],False)),patch('backend.worker.analyze_lessons',return_value=plan),patch('backend.worker.fetch_lesson_assets',return_value=({},[])):
            worker.execute(job)
        store.job_update(job['id'],status='succeeded')
        done=automation.get(row['hash']);self.assertEqual(done['state'],'done')
        target=Path(done['output']);self.assertEqual(target.name,'Có - learn vietnamese.mp4')
        self.assertEqual((probe(target)['width'],probe(target)['height']),(1080,1920))
        ffmpeg(['-xerror','-i',target,'-f','null','-'])
        automation.scan(force=True,at=150);automation.scan(force=True,at=161);automation.dispatch()
        self.assertEqual(len(store.jobs()),1);self.assertEqual(len(automation.items()),1)
        first_bytes=target.read_bytes();source_bytes=source.read_bytes()
        saved=store.read(p['id']);saved['plan']['cuts']=[{'id':'manual','start':.2,'end':.5,'enabled':True,'locked':True}]
        saved['options']['video_frames']['9:16']={'zoom':1.7,'x':.1,'y':-.1}
        store.update(p['id'],plan=saved['plan'],options=saved['options'],revision=saved['revision']+1)
        manual=store.job_create(p['id'],'export')
        with patch('backend.worker.transcribe',side_effect=AssertionError('manual export must not run STT')),patch('backend.worker.analyze',side_effect=AssertionError('manual export must not run AI')):
            worker.execute(manual)
        edited=store.read(p['id'])['export'];published=Path(edited['published_file'])
        self.assertNotEqual(published,target);self.assertEqual(published.parent,source.parent)
        self.assertEqual(target.read_bytes(),first_bytes);self.assertEqual(source.read_bytes(),source_bytes)
        self.assertAlmostEqual(probe(published)['duration'],duration-.3,delta=.1)
        ffmpeg(['-xerror','-i',published,'-f','null','-'])
        self.assertEqual(automation.get(row['hash'])['state'],'done')
        store.job_update(manual['id'],status='succeeded')
        automation.scan(force=True,at=180);automation.scan(force=True,at=191);automation.dispatch()
        self.assertEqual(len(automation.items()),1)



class NamingAndFramesTests(unittest.TestCase):
    def test_vfr_normalization_resume_and_decode_failure(self):
        import subprocess
        from backend.media import ffmpeg
        from backend.config import binary
        with TemporaryDirectory() as tmp:
            source=Path(tmp)/'vfr.mp4'
            ffmpeg(['-f','lavfi','-i','testsrc2=s=64x64:r=30','-t','2.2','-vf',"select=not(mod(n\\,2))+not(mod(n\\,5))",'-fps_mode','vfr','-c:v','libx264',source])
            def decode(first):
                return subprocess.run([binary('ffmpeg'),'-v','error','-xerror','-err_detect','explode','-i',str(source),'-an','-vf',f'fps=30:start_time=0,scale=64:64,trim=start_frame={first}','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True).stdout
            full=decode(0);resumed=decode(30)
            self.assertGreater(len(resumed),0);self.assertEqual(full[30*64*64*3:],resumed)
            self.assertGreater(source_video_end({'source':str(source),'ffprobe':binary('ffprobe')}),2)
            source.write_bytes(source.read_bytes()[:100])
            with self.assertRaises(RuntimeError):source_video_end({'source':str(source),'ffprobe':binary('ffprobe')})
    def test_unicode_names_and_multi_lesson_summary(self):
        p={'title':'Old title','plan':{'summary':'Chào hỏi','lessons':[{'vi':'Có'}]}}
        self.assertEqual(video_filename(p),'Có - learn vietnamese.mp4')
        p['plan']['lessons'].append({'vi':'Xin chào'});self.assertEqual(lesson_title(p),'Chào hỏi')
        p.update(title_mode='manual',title='CON');self.assertTrue(video_filename(p).startswith('_CON'))
        p['title']='a:b/c\\d?';self.assertEqual(video_filename(p),'a b c d - learn vietnamese.mp4')
    def test_clean_verified_tail_vs_missing_frames(self):
        validate_eof(1898,1900,63.281733,b'last')
        validate_eof(599,601,20,b'last')
        with self.assertRaises(RuntimeError):validate_eof(1800,1900,63.281733,b'last')
        with self.assertRaises(RuntimeError):validate_eof(0,10,.3,None)
        with self.assertRaises(RuntimeError):read_exact(io.BytesIO(b'bad'),4)
    def test_bounded_buffers_preserve_all_bytes(self):
        with TemporaryDirectory() as tmp:
            cancel=Path(tmp)/'cancel';reader=BufferedFrames(io.BytesIO(b'abcdefghijkl'),4)
            self.assertEqual([reader.next(cancel) for _ in range(4)],[b'abcd',b'efgh',b'ijkl',None])
            self.assertIsNone(reader.next(cancel));reader.stop.set()
            class Partial(io.BytesIO):
                def write(self,data):return super().write(data[:2])
            output=Partial();writer=BufferedWriter(output,cancel);writer.submit(b'abcdefgh');writer.finish()
            self.assertEqual(output.getvalue(),b'abcdefgh')
