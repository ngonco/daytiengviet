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

if __name__=='__main__':unittest.main()
