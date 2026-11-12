import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock,patch
from PIL import Image,ImageChops
from pydantic import ValidationError
from backend.app import Options
from backend import automation,store,worker
from backend.media import ffmpeg
from backend.templates import geometry,speaker_filter,speaker_transform
from backend.live_preview import source_info


class VideoFramingTests(unittest.TestCase):
    def test_bounds_ratio_independence_and_old_options(self):
        self.assertEqual(Options().video_frames,{})
        opts=Options(video_frames={'9:16':{'zoom':3,'x':-.3,'y':.2},'16:9':{'zoom':.5}}).model_dump()
        self.assertEqual(Options.model_validate(opts).model_dump(),opts)
        for frames in [{'bad':{}},{'9:16':{'zoom':4.1}},{'16:9':{'x':float('nan')}},{'9:16':{'y':-1.1}}]:
            with self.assertRaises(ValidationError):Options(video_frames=frames)
        p={'metadata':{'width':160,'height':90},'options':opts}
        portrait=speaker_transform(p,540,960)
        p['options']['video_frames']['16:9']['zoom']=2
        self.assertEqual(speaker_transform(p,540,960),portrait)

    def test_original_bypasses_old_matting_without_changing_it(self):
        p={'source_file':'source.mp4','options':{'background_removal':{'enabled':False}},'matting':{'file':'old.mp4'}}
        before=copy.deepcopy(p)
        with TemporaryDirectory() as tmp:
            self.assertEqual(source_info(p,Path(tmp)),{'file':'source.mp4','state':'original'})
        self.assertEqual(p,before)

    def test_browser_geometry_matches_actual_ffmpeg_crop_pad_for_zoom_and_drag(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);Image.new('RGB',(160,90),'blue').save(root/'source.png')
            for w,h in [(540,960),(960,540)]:
                for zoom,x,y in [(.25,0,0),(1,.2,-.15),(4,-1,1),(4,1,-1)]:
                    with self.subTest(size=(w,h),frame=(zoom,x,y)):
                        p={'metadata':{'width':160,'height':90},'options':{'video_frames':{'9:16' if h>w else '16:9':{'zoom':zoom,'x':x,'y':y}}}}
                        tr=speaker_transform(p,w,h);_,_,cw,ch=geometry(w,h)['speaker']
                        expected=Image.new('RGB',(cw,ch),'#F7F3EB')
                        expected.paste(Image.new('RGB',(tr['width'],tr['height']),'blue'),(tr['left'],tr['top']))
                        ffmpeg(['-i',root/'source.png','-vf',speaker_filter(p,w,h)+',format=rgb24','-frames:v','1',root/'actual.png'])
                        with Image.open(root/'actual.png') as actual:
                            self.assertEqual(actual.size,expected.size)
                            self.assertIsNone(ImageChops.difference(actual.convert('RGB'),expected).getbbox())


class ManualPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);(self.root/'private').mkdir()
        self.mock=patch('backend.store.data_root',return_value=self.root/'private');self.mock.start();self.addCleanup(self.mock.stop);store.init()
        self.pid='e123456789abcdef';self.folder=store.folder(self.pid)
        (self.folder/'source.mp4').write_bytes(b'unchanged original')
        self.source=self.root/'lesson.mp4';self.source.write_bytes(b'unchanged external original')
        (self.folder/'result.mp4').write_bytes(b'new edited export')
        self.p={'id':self.pid,'source_file':'source.mp4','title':'Lesson','title_mode':'manual','revision':2,'options':Options(layout_mode='lesson').model_dump(),'metadata':{'duration':10},'plan':{'lessons':[],'cuts':[]},'export':{'file':'result.mp4','duration':8,'digest':'d'*24}}
        store.save(self.p)
        self.row={'hash':'a'*64,'source':str(self.source),'project_id':self.pid,'state':'done','created_at':store.now()};automation.put(self.row)

    def test_collision_retry_independence_and_originals_preserved(self):
        target=self.root/'Lesson - learn vietnamese.mp4';target.write_bytes(b'first export')
        before=automation.get(self.row['hash'])
        with patch('backend.automation.ffmpeg'),patch('backend.automation.probe',return_value={'duration':8}):
            automation.publish_edited(self.p,Mock())
            automation.publish_edited(self.p,Mock())
        self.assertEqual(target.read_bytes(),b'first export')
        self.assertEqual((self.root/'Lesson - learn vietnamese (2).mp4').read_bytes(),b'new edited export')
        self.assertFalse((self.root/'Lesson - learn vietnamese (3).mp4').exists())
        self.assertEqual(automation.get(self.row['hash']),before)
        self.assertEqual(self.source.read_bytes(),b'unchanged external original')
        self.assertEqual((self.folder/'source.mp4').read_bytes(),b'unchanged original')
        self.assertTrue(automation.is_output(automation.digest(self.folder/'result.mp4')))

    def test_export_worker_uses_saved_plan_without_ai_and_publishes_manual_result(self):
        job=store.job_create(self.pid,'export')
        with patch('backend.worker.extract_frames',return_value=[]),patch('backend.worker.prepared_render',return_value=self.p['export']) as render,patch('backend.worker.transcribe',side_effect=AssertionError('no STT')),patch('backend.worker.analyze',side_effect=AssertionError('no AI')),patch('backend.automation.publish_edited',return_value=None) as publish:
            worker.execute(job)
        self.assertFalse(render.call_args.args[-1]);publish.assert_called_once()

    def test_publication_failure_can_retry_and_does_not_restart_automatic_pipeline(self):
        before=automation.get(self.row['hash'])
        with patch('backend.automation.ffmpeg',side_effect=RuntimeError('invalid edited file')):
            with self.assertRaises(RuntimeError):automation.publish_edited(self.p,Mock())
        self.assertEqual(automation.get(self.row['hash']),before)
        self.assertFalse((self.root/'Lesson - learn vietnamese.mp4').exists())
        with patch('backend.automation.ffmpeg'),patch('backend.automation.probe',return_value={'duration':8}):automation.publish_edited(self.p,Mock())
        self.assertTrue((self.root/'Lesson - learn vietnamese.mp4').is_file())

    def test_backfilled_manual_project_never_publishes_into_internal_data(self):
        row=automation.get(self.row['hash']);row['source']=str(self.folder/'source.mp4');automation.put(row)
        with patch('backend.automation._publish',side_effect=AssertionError('must stay download-only')):automation.publish_edited(self.p,Mock())


if __name__=='__main__':unittest.main()
