import unittest,copy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch,Mock
from PIL import Image,ImageChops
from backend import store,retention
from backend.app import Options
from backend.templates import geometry,make_frame,rounded_mask,speaker_transform,subtitle_position
from backend.lesson_render import subtitle_image,render_lessons
from backend.media import ffmpeg,probe
from backend.live_preview import scene

class AssemblyEditorTests(unittest.TestCase):
    def test_new_projects_use_circle_even_with_stale_client_defaults(self):
        from backend.app import create
        for supplied in [{}, {'landscape_layout':'classic'}, {'landscape_layout':'circle'}]:
            with self.subTest(supplied=supplied),TemporaryDirectory() as tmp,patch('backend.store.data_root',return_value=Path(tmp)):
                store.init();source=Path(tmp)/'input.mp4';source.write_bytes(b'test source')
                with patch('backend.app.probe',return_value={'duration':10,'width':1920,'height':1080}):
                    created=create(source,'Test',Options(ratio='16:9',layout_mode='lesson',**supplied))
                self.assertEqual(created['options']['landscape_layout'],'circle')
                self.assertEqual(created['options']['portrait_layout'],'circle')
                self.assertFalse(created['options']['background_removal']['enabled'])
                self.assertEqual(source.read_bytes(),b'test source')
        self.assertEqual(Options.model_validate({'layout_mode':'lesson'}).landscape_layout,'classic')

    def test_circle_size_and_non_overlapping_teaching_regions(self):
        for size in [.15,.25,.4]:
            opts=Options(ratio='16:9',landscape_layout='circle',speaker_size=size).model_dump()
            self.assertEqual(Options.model_validate(opts).model_dump(),opts)
            for w,h in [(1920,1080),(960,540)]:
                g=geometry(w,h,opts);x,y,d,dh=g['speaker'];cx,cy,cw,ch=g['content']
                self.assertEqual(d,dh);self.assertAlmostEqual(d/h,size,delta=.002)
                self.assertLessEqual(cy+ch,y);self.assertLessEqual(g['photo'][0]+g['photo'][2],cx)
                mask=rounded_mask((d,d),g['speaker_radius']);self.assertEqual(mask.getpixel((0,0)),0);self.assertEqual(mask.getpixel((d//2,d//2)),255)
                sub=subtitle_image({'vi':'Xin chào','en':'Hello'},w,h,options=opts)
                sx,sy=subtitle_position(w,h,*sub.size,opts);self.assertLess(sx+sub.width,x)
        self.assertEqual(geometry(1080,1920,opts),geometry(1080,1920))
        self.assertNotIn('circle',geometry(1920,1080))

    def test_actual_circle_export_after_cut_and_waveform_preserve_source(self):
        from backend.edit_media import waveform
        import hashlib
        with TemporaryDirectory() as tmp:
            folder=Path(tmp)
            ffmpeg(['-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=2','-f','lavfi','-i','sine=frequency=400:duration=2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',folder/'source.mp4'])
            before=hashlib.sha256((folder/'source.mp4').read_bytes()).hexdigest()
            lesson={'id':'l','start':0,'end':2,'vi':'Xin chào','en':'Hello','chunks':[],'asset_id':None}
            plan={'schema_version':2,'lessons':[lesson],'cuts':[{'id':'cut','start':.5,'end':1,'enabled':True}],'captions':[{'id':'c','start':0,'end':2,'vi':'Xin chào','en':'Hello'}],'visuals':[]}
            p={'id':'123456789abcdef0','title':'Synthetic','source_file':'source.mp4','metadata':{'duration':2,'width':320,'height':180},'revision':1,'assets':{},'frames':[],'options':Options(ratio='16:9',layout_mode='lesson',landscape_layout='circle',auto_volume=False,video_frames={'16:9':{}},background_removal={'enabled':False}).model_dump()}
            ctx=Mock();ctx.folder=folder;ctx.kind='export'
            result=render_lessons(p,plan,{},ctx,True)
            self.assertAlmostEqual(result['duration'],1.5,delta=.04)
            ffmpeg(['-i',folder/result['file'],'-f','null','-'])
            ffmpeg(['-i',folder/result['file'],'-frames:v','1',folder/'actual.png'])
            with Image.open(folder/'actual.png') as actual:
                w,h=actual.size;g=geometry(w,h,p['options']);x,y,d,_=g['speaker'];outside=actual.getpixel((x+2,y+2));inside=actual.getpixel((x+d//2,y+d//2))
                self.assertGreater(outside[0],180);self.assertGreater(inside[2],inside[0]+100)
            peaks=waveform(p,folder)['peaks'];self.assertTrue(peaks);self.assertGreater(max(peaks),.05)
            p2=copy.deepcopy(p);p2['options']['speaker_size']=.4
            first=scene(p,folder,lesson,plan['captions'][0]);second=scene(p2,folder,lesson,plan['captions'][0]);self.assertNotEqual(first['page'],second['page']);self.assertNotEqual(first['geometry'],second['geometry'])
            self.assertEqual(hashlib.sha256((folder/'source.mp4').read_bytes()).hexdigest(),before)

    def test_photo_crop_geometry_uses_saved_and_unsaved_layout(self):
        from backend.app import photo_layout
        with TemporaryDirectory() as tmp,patch('backend.store.data_root',return_value=Path(tmp)):
            store.init();pid='123456789abcdef0';folder=store.folder(pid);(folder/'assets').mkdir()
            Image.new('RGB',(800,600),'blue').save(folder/'assets'/'p.jpg')
            store.save({'id':pid,'options':Options(ratio='16:9',landscape_layout='circle').model_dump(),'assets':{'p':{'file':'p.jpg'}},'metadata':{'width':1920,'height':1080}})
            saved=photo_layout(pid,'p','16:9');draft=photo_layout(pid,'p','16:9',landscape_layout='classic')
            self.assertEqual((saved['frame_width'],saved['frame_height']),(920,800))
            self.assertEqual((draft['frame_width'],draft['frame_height']),(1180,448))
            self.assertEqual(store.read(pid)['options']['landscape_layout'],'circle')

    def test_explicit_trash_is_recoverable_and_refuses_busy_projects(self):
        with TemporaryDirectory() as tmp,patch('backend.store.data_root',return_value=Path(tmp)):
            store.init();pid='123456789abcdef0';folder=store.folder(pid);(folder/'source.mp4').write_bytes(b'original')
            store.save({'id':pid,'title':'Temporary test','created_at':store.now()})
            job=store.job_create(pid,'export')
            with self.assertRaises(ValueError):retention.archive(pid)
            store.job_update(job['id'],status='cancelled')
            with patch('backend.retention._finish',side_effect=OSError('locked')):
                with self.assertRaises(OSError):retention.archive(pid)
            self.assertNotIn('_retention',store.read(pid));self.assertTrue(folder.exists())
            retention.archive(pid)
            self.assertEqual(store.listing(),[]);self.assertEqual((Path(tmp)/'trash'/pid/'source.mp4').read_bytes(),b'original')
            retention.restore(pid);self.assertEqual((folder/'source.mp4').read_bytes(),b'original')


    def test_portrait_circle_is_opt_in_for_old_projects_and_centered_at_all_sizes(self):
        from backend.templates import subtitle_region,speaker_filter
        self.assertEqual(Options(layout_mode='lesson').portrait_layout,'classic')
        old={'landscape_layout':'circle'}
        self.assertEqual(geometry(1080,1920,old),geometry(1080,1920))
        for size in [.15,.25,.4]:
            opts=Options(layout_mode='lesson',portrait_layout='circle',speaker_size=size,video_frames={'9:16':{}}).model_dump()
            for w,h in [(1080,1920),(540,960)]:
                g=geometry(w,h,opts);x,y,d,dh=g['speaker'];cx,cy,cw,ch=g['content']
                self.assertTrue(g['portrait']);self.assertTrue(g['circle']);self.assertEqual(d,dh)
                self.assertAlmostEqual(x+d/2,w/2,delta=.5);self.assertAlmostEqual(d/h,size,delta=.002)
                self.assertLessEqual(cy+ch,y-10);self.assertLessEqual(y+d,h)
                self.assertEqual(subtitle_region(w,h,opts),g['photo'])
                sub=subtitle_image({'vi':'Xin chào','en':'Hello'},w,h,options=opts)
                _,sy=subtitle_position(w,h,*sub.size,opts);self.assertLess(sy+sub.height,cy)
                with TemporaryDirectory() as tmp:make_frame({'options':opts,'assets':{}},{'vi':'Xin chào','en':'Hello','chunks':[]},Path(tmp),w,h)
        # Browser transform and FFmpeg crop/pad must stay identical at zoom/drag extremes.
        with TemporaryDirectory() as tmp:
            root=Path(tmp);Image.new('RGB',(160,90),'blue').save(root/'source.png')
            for zoom,x,y in [(.25,0,0),(1,.2,-.15),(4,-1,1),(4,1,-1)]:
                opts['video_frames']['9:16']={'zoom':zoom,'x':x,'y':y}
                p={'metadata':{'width':160,'height':90},'options':opts};tr=speaker_transform(p,540,960)
                _,_,cw,ch=geometry(540,960,opts)['speaker'];expected=Image.new('RGB',(cw,ch),'#F7F3EB')
                expected.paste(Image.new('RGB',(tr['width'],tr['height']),'blue'),(tr['left'],tr['top']))
                ffmpeg(['-i',root/'source.png','-vf',speaker_filter(p,540,960)+',format=rgb24','-frames:v','1',root/'actual.png'])
                with Image.open(root/'actual.png') as actual:self.assertIsNone(ImageChops.difference(actual.convert('RGB'),expected).getbbox())

    def test_actual_portrait_circle_export_and_live_scene_agree(self):
        import hashlib
        with TemporaryDirectory() as tmp:
            folder=Path(tmp)
            ffmpeg(['-f','lavfi','-i','color=c=blue:s=160x90:r=30:d=1','-f','lavfi','-i','sine=frequency=400:duration=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',folder/'source.mp4'])
            before=hashlib.sha256((folder/'source.mp4').read_bytes()).hexdigest()
            lesson={'id':'l','start':0,'end':1,'vi':'Xin chào','en':'Hello','chunks':[],'asset_id':None}
            plan={'schema_version':2,'lessons':[lesson],'cuts':[],'captions':[{'id':'c','start':0,'end':1,'vi':'Xin chào','en':'Hello'}],'visuals':[]}
            p={'id':'123456789abcdef0','title':'Synthetic','source_file':'source.mp4','metadata':{'duration':1,'width':160,'height':90},'revision':1,'assets':{},'frames':[],'options':Options(ratio='9:16',layout_mode='lesson',portrait_layout='circle',auto_volume=False,video_frames={'9:16':{}},background_removal={'enabled':False}).model_dump()}
            ctx=Mock();ctx.folder=folder;ctx.kind='export'
            result=render_lessons(p,plan,{},ctx,True)
            self.assertAlmostEqual(result['duration'],1,delta=.04)
            ffmpeg(['-i',folder/result['file'],'-f','null','-'])
            ffmpeg(['-i',folder/result['file'],'-frames:v','1',folder/'actual.png'])
            live=scene(p,folder,lesson,plan['captions'][0]);g=live['geometry'];x,y,d,_=g['speaker']
            with Image.open(folder/'actual.png') as actual:
                self.assertEqual(actual.size,(live['width'],live['height']))
                outside=actual.getpixel((x+2,y+2));inside=actual.getpixel((x+d//2,y+d//2))
                self.assertGreater(outside[0],180);self.assertGreater(inside[2],inside[0]+100)
            self.assertEqual(hashlib.sha256((folder/'source.mp4').read_bytes()).hexdigest(),before)

if __name__=='__main__':unittest.main()
