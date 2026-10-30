import copy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np
import cv2
from fastapi.testclient import TestClient
from backend.app import Options,app,create
from backend.matting_schema import BackgroundRemoval,validate_duration
from backend.matting import cache_identity,verified_model,ensure_matting
from backend import store
from scripts.matting_runner import Corrections,Pipes,read_exact,infer_group


class MattingTests(unittest.TestCase):
    def test_legacy_layer_pairs_reused_for_new_palette_without_model(self):
        from backend.media import ffmpeg
        from backend import matting
        with TemporaryDirectory() as tmp:
            folder=Path(tmp)
            ffmpeg(['-f','lavfi','-i','color=c=red:s=64x64:r=30','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','0.5','-c:v','libx264','-c:a','aac',folder/'source.mp4'])
            p={'source_file':'source.mp4','metadata':{'width':64,'height':64,'duration':.5},'options':{'background_removal':{'enabled':True}}}
            key,identity=cache_identity(p,folder);legacy='b'*24;layer=folder/'matting'/legacy;part=layer/'00000';part.mkdir(parents=True)
            ffmpeg(['-f','lavfi','-i','color=c=red:s=64x64:r=30','-t','0.5','-c:v','libx264','-pix_fmt','yuv444p',part/'foreground.mp4'])
            ffmpeg(['-f','lavfi','-i','color=c=white:s=64x64:r=30','-t','0.5','-c:v','ffv1','-pix_fmt','gray',part/'alpha.mkv'])
            (part/'complete.json').write_text(json.dumps({'frames':15}))
            stats={'processing_seconds_this_run':0,'fps_this_run':0,'model_load_seconds':0,'peak_gpu_mb':0,'warnings':[]}
            (layer/'manifest.json').write_text(json.dumps({'code':legacy,'identity':{**identity,'paper':'#fbf5e9'},'stats':stats}))
            before=(part/'alpha.mkv').stat().st_mtime_ns
            class C:
                kind='preview'
                def __init__(self):self.folder=folder
                def check(self):pass
                def progress(self,*args):pass
            with patch('backend.matting.runtime_status',side_effect=AssertionError('Must not initialize GPU for palette change')):
                first=ensure_matting(p,C());self.assertTrue(first['reused_layers']);self.assertEqual(first['layer_code'],legacy)
                self.assertTrue((folder/first['file']).is_file())
                second_theme={'paper':'#FFFFFF'}
                real_read=Path.read_text
                def themed(path,*args,**kwargs):
                    if path==matting.ROOT/'assets/frame_brand.json':return json.dumps(second_theme)
                    return real_read(path,*args,**kwargs)
                with patch('pathlib.Path.read_text',themed):
                    second=ensure_matting(p,C());self.assertNotEqual(first['code'],second['code']);self.assertEqual(second['layer_code'],legacy)
            self.assertEqual((part/'alpha.mkv').stat().st_mtime_ns,before)

    def test_oom_retries_one_frame_without_resetting_recurrence(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        class Tensor(np.ndarray):
            def unsqueeze(self,axis):return np.expand_dims(self,axis).view(Tensor)
        src=np.zeros((1,4,3,8,8),np.float32).view(Tensor);states=[]
        def model(x,*args):
            rec=args[:-1]
            if x.ndim==5:raise RuntimeError('CUDA out of memory (TorchScript wrapper)')
            states.append(rec[0]);return [x,x[:,0:1],*[r+1 for r in rec]]
        torch=SimpleNamespace(cuda=SimpleNamespace(empty_cache=Mock()),cat=lambda xs,axis:np.concatenate(xs,axis).view(Tensor))
        fg,alpha,rec,fallback=infer_group(model,src,[7]*4,.5,'cuda',torch)
        self.assertTrue(fallback);self.assertEqual(fg.shape,src.shape);self.assertEqual(alpha.shape,(1,4,1,8,8));self.assertEqual(states,[7,8,9,10]);self.assertEqual(rec,[11]*4)
        with self.assertRaisesRegex(RuntimeError,'CUDA out of memory'):infer_group(model,src,[7]*4,.5,'cpu',torch)
        def broken(*args):raise RuntimeError('unrelated model failure')
        with self.assertRaisesRegex(RuntimeError,'unrelated'):infer_group(broken,src,[7]*4,.5,'cuda',torch)

    def test_bounded_video_pipes_transfer_complete_frames(self):
        import sys,hashlib
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'received.bin';data=bytes(range(256))*16384;pipes=Pipes()
            try:
                p=pipes.start([sys.executable,'-c','import sys,pathlib;pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())',str(path)])
                p.stdin.write(data);pipes.finish(p);self.assertEqual(hashlib.sha256(path.read_bytes()).digest(),hashlib.sha256(data).digest())
                p=pipes.start([sys.executable,'-c','import sys;sys.stdout.buffer.write(bytes(range(256))*16384)'],read=True)
                self.assertEqual(read_exact(p.stdout,len(data)),data);self.assertIsNone(read_exact(p.stdout,1));pipes.finish(p)
            finally:pipes.close()

    def test_old_off_new_on_explicit_off(self):
        self.assertFalse(Options().background_removal.enabled)
        with TemporaryDirectory() as tmp,patch('backend.store.data_root',return_value=Path(tmp)),patch('backend.app.probe',return_value={'duration':10,'width':320,'height':180}):
            store.init();source=Path(tmp)/'input.mp4';source.write_bytes(b'sample')
            self.assertTrue(create(source,'new',Options())['options']['background_removal']['enabled'])
            self.assertFalse(create(source,'off',Options(background_removal={'enabled':False}))['options']['background_removal']['enabled'])

    def test_validation_rejects_invalid_corrections(self):
        stroke={'id':'s','start':1,'end':3,'mode':'keep','points':[{'x':.5,'y':.5}]}
        options={'background_removal':{'strokes':[stroke]}}
        self.assertEqual(validate_duration(options,4).strokes[0].mode,'keep')
        for changes in [{'start':4},{'end':8},{'points':[{'x':2,'y':.5}]},{'radius':float('nan')},{'id':'../escape'}]:
            with self.assertRaises(ValueError):validate_duration({'background_removal':{'strokes':[{**stroke,**changes}]}},4)
        with self.assertRaises(ValueError):validate_duration({'background_removal':{'strokes':[stroke,stroke]}},4)

    def test_cache_ignores_aspect_lesson_cuts_but_changes_with_source_edges_and_strokes(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'source.mp4').write_bytes(b'original')
            p={'source_file':'source.mp4','metadata':{'width':3840,'height':2160,'duration':30},'options':{'ratio':'9:16','background_removal':{'enabled':True}},'plan':{'lessons':[]}}
            key,identity=cache_identity(p,folder);self.assertEqual(identity['size'],[1920,1080])
            changed=copy.deepcopy(p);changed['options']['ratio']='16:9';changed['plan']={'lessons':[{'vi':'Different'}],'cuts':[{'start':1,'end':2}]}
            self.assertEqual(cache_identity(changed,folder)[0],key)
            changed['options']['background_removal']['soften']=2
            self.assertNotEqual(cache_identity(changed,folder)[0],key)
            changed=copy.deepcopy(p);changed['options']['background_removal']['strokes']=[{'id':'s','start':1,'end':2,'mode':'remove','points':[{'x':.2,'y':.2}]}]
            self.assertNotEqual(cache_identity(changed,folder)[0],key)
            (folder/'source.mp4').write_bytes(b'changed');self.assertNotEqual(cache_identity(p,folder)[0],key)

    def test_unverified_model_and_gpu_do_not_silently_fallback(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'source.mp4').write_bytes(b'fake')
            p={'source_file':'source.mp4','metadata':{'width':64,'height':64,'duration':1},'options':{'background_removal':{'enabled':True}}}
            class C:
                def __init__(self):self.folder=folder
            with patch('backend.matting.runtime_status',return_value={'installed':True,'cuda':False,'models':{'cuda':True}}):
                with self.assertRaisesRegex(ValueError,'không tự chuyển'):ensure_matting(p,C())
            fake=folder/'model';fake.write_bytes(b'untrusted')
            with patch('backend.matting.model_path',return_value=fake):self.assertFalse(verified_model('cuda'))

    def test_keep_remove_and_optical_flow_confidence(self):
        cfg=BackgroundRemoval(soften=0,strokes=[{'id':'s','start':0,'end':2,'mode':'keep','radius':.08,'points':[{'x':.5,'y':.5}]}]).model_dump()
        rng=np.random.default_rng(4);source=rng.integers(0,255,(120,160,3),dtype=np.uint8);fg=np.zeros_like(source,dtype=np.float32);alpha=np.zeros((120,160),np.float32)
        tracker=Corrections(cfg,160,120);f,a=tracker.apply(source,fg,alpha,0)
        self.assertGreater(a[60,80],.95);self.assertGreater(f[60,80].sum(),0)
        moved=cv2.warpAffine(source,np.float32([[1,0,2],[0,1,0]]),(160,120))
        _,a=tracker.apply(moved,fg,alpha,1);self.assertGreater(a[60,82],.9)
        with patch('cv2.calcOpticalFlowPyrLK',side_effect=lambda a,b,p,*args,**kwargs:(p,np.zeros((len(p),1),np.uint8),np.ones((len(p),1),np.float32)*100)):
            _,a=tracker.apply(source,fg,alpha,2)
        self.assertEqual(float(a.max()),0);self.assertEqual(len(tracker.warnings),1)
        cfg['strokes'][0]['mode']='remove';tracker=Corrections(cfg,160,120)
        _,a=tracker.apply(source,fg,np.ones((120,160),np.float32),0);self.assertLess(a[60,80],.05)

    def test_tracking_checkpoint_does_not_reset_at_20_seconds(self):
        cfg=BackgroundRemoval(soften=0,strokes=[{'id':'s','start':19,'end':21,'mode':'keep','points':[{'x':.5,'y':.5}]}]).model_dump()
        tracker=Corrections(cfg,80,80);src=np.random.default_rng(2).integers(0,255,(80,80,3),dtype=np.uint8);fg=np.zeros_like(src,dtype=np.float32);alpha=np.zeros((80,80),np.float32)
        tracker.apply(src,fg,alpha,570)
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);np.savez_compressed(folder/'state.npz',gray=tracker.previous);tracker.save(folder)
            restored=Corrections(cfg,80,80);restored.restore(folder)
            _,a=tracker.apply(src,fg,alpha,600);_,b=restored.apply(src,fg,alpha,600)
            np.testing.assert_array_equal(a,b);self.assertGreater(b.max(),.9)

    def test_zip_preserves_config_but_excludes_caches(self):
        import zipfile
        from backend.media import ffmpeg
        with TemporaryDirectory() as tmp,patch('backend.store.data_root',return_value=Path(tmp)):
            store.init();pid='1123456789abcdef';folder=store.folder(pid)
            ffmpeg(['-f','lavfi','-i','color=c=blue:s=64x64:r=30','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',1,'-c:v','libx264','-c:a','aac',folder/'source.mp4'])
            options=Options(background_removal={'enabled':True,'strokes':[{'id':'s','start':0,'end':.5,'mode':'keep','points':[{'x':.5,'y':.5}]}]}).model_dump()
            project={'id':pid,'title':'portable','revision':1,'metadata':{'duration':1},'source_file':'source.mp4','options':options,'plan':None,'assets':{},'preview':{'file':'fake.mp4'},'matting':{'file':'bad','code':'bad'}}
            store.save(project);(folder/'matting').mkdir();(folder/'matting/private.cache').write_bytes(b'cache')
            client=TestClient(app);response=client.get(f'/api/projects/{pid}/download/project');self.assertEqual(response.status_code,200,response.text[:100])
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                self.assertFalse(any('matting/' in n for n in z.namelist()))
                self.assertTrue(json.loads(z.read('project.json'))['options']['background_removal']['enabled'])
            loaded=client.post('/api/projects/import',files={'file':('p.zip',response.content,'application/zip')});self.assertEqual(loaded.status_code,200,loaded.text)
            self.assertNotIn('matting',loaded.json());self.assertEqual(loaded.json()['options']['background_removal'],options['background_removal'])

    def test_comparison_at_segment_boundaries_is_not_blank(self):
        from backend.media import ffmpeg
        from PIL import Image
        with TemporaryDirectory() as tmp,patch('backend.store.data_root',return_value=Path(tmp)):
            store.init();pid='2123456789abcdef';folder=store.folder(pid);code='a'*24
            for i,seconds in [(0,20),(1,.2)]:
                part=folder/'matting'/code/f'{i:05}';part.mkdir(parents=True)
                ffmpeg(['-f','lavfi','-i','color=c=red:s=64x64:r=30','-t',seconds,'-c:v','libx264','-pix_fmt','yuv444p',part/'foreground.mp4'])
                ffmpeg(['-f','lavfi','-i','color=c=white:s=64x64:r=30','-t',seconds,'-c:v','ffv1','-pix_fmt','gray',part/'alpha.mkv'])
                (part/'complete.json').write_text('{}')
            store.save({'id':pid,'metadata':{'duration':20.2},'matting':{'code':code,'identity':{'size':[64,64],'paper':'#fbf5e9'}}})
            client=TestClient(app)
            for at in [0,19.9667,20.0333,20.15]:
                r=client.get(f'/api/projects/{pid}/matting/frame',params={'time':at,'background':'black'});self.assertEqual(r.status_code,200)
                im=Image.open(io.BytesIO(r.content)).convert('RGB');red,green,blue=im.getpixel((im.width//2,im.height//2))
                self.assertGreater(red,180);self.assertLess(green+blue,80)


if __name__=='__main__':unittest.main()
