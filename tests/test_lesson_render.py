import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image,ImageChops,ImageStat
from backend.media import ffmpeg
from backend.render import render
from backend.config import binary
from backend.templates import geometry

class Context:
    kind='preview'
    def __init__(self,folder):self.folder=folder
    def check(self):pass
    def progress(self,*args):pass

class LessonRenderTests(unittest.TestCase):
    def test_static_content_across_20_second_chunks_with_cut_and_captions(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'assets').mkdir()
            Image.new('RGB',(400,300),'#88aa77').save(folder/'assets/p.jpg')
            ffmpeg(['-f','lavfi','-i','testsrc2=size=320x180:rate=30','-f','lavfi','-i','sine=frequency=330:sample_rate=48000','-t','24','-c:v','libx264','-c:a','aac',folder/'source.mp4'])
            project={'metadata':{'duration':24,'width':320,'height':180},'options':{'ratio':'16:9','layout_mode':'lesson','subtitles':'bilingual','sfx':False},'source_file':'source.mp4','assets':{'p':{'file':'p.jpg'}},'revision':1,'frames':[]}
            plan={'schema_version':2,'lessons':[{'id':'l','start':0,'end':24,'vi':'Xin chào!','en':'Hello!','chunks':[],'asset_id':'p'}],'captions':[{'id':'a','start':0,'end':3,'vi':'Lặp lại theo mình','en':'Repeat after me'},{'id':'b','start':21,'end':24,'vi':'Đến lượt bạn','en':'Your turn'}],'cuts':[{'id':'cut','start':10,'end':12,'enabled':True}],'visuals':[]}
            result=render(project,plan,{},Context(folder),True)
            output=folder/result['file']
            data=json.loads(subprocess.run([binary('ffprobe'),'-v','error','-show_format','-show_streams','-of','json',str(output)],check=True,capture_output=True).stdout)
            self.assertAlmostEqual(float(data['format']['duration']),22,delta=.1)
            self.assertEqual(next(s for s in data['streams'] if s['codec_type']=='audio')['channels'],2)
            for i,at in enumerate([1,21]):ffmpeg(['-ss',at,'-i',output,'-frames:v','1',folder/f'f{i}.png'])
            x,y,w,h=geometry(result['width'],result['height'])['photo']
            with Image.open(folder/'f0.png') as a,Image.open(folder/'f1.png') as b:
                diff=ImageChops.difference(a.crop((x+10,y+10,x+w-10,y+h-10)),b.crop((x+10,y+10,x+w-10,y+h-10)))
                self.assertLess(sum(ImageStat.Stat(diff).mean)/3,2.5)
            self.assertEqual(result['layout_mode'],'lesson')

if __name__=='__main__':unittest.main()
