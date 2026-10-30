import unittest
import subprocess
import json
from tempfile import TemporaryDirectory
from pathlib import Path
from PIL import Image
from backend.media import ffmpeg
from backend.render import render
from backend.config import binary

class Context:
    kind='preview'
    def __init__(self,folder):self.folder=folder
    def check(self):pass
    def progress(self,*args):pass

class RenderIntegration(unittest.TestCase):
    def test_cut_bilingual_photo_music_and_audio_survive_export(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp)
            ffmpeg(['-f','lavfi','-i','testsrc2=size=320x180:rate=30','-f','lavfi','-i','sine=frequency=330:sample_rate=48000','-t','4','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',folder/'source.mp4'])
            ffmpeg(['-f','lavfi','-i','sine=frequency=220:sample_rate=48000','-t','2',folder/'music.wav'])
            (folder/'assets').mkdir()
            Image.new('RGB',(400,300),'#436f58').save(folder/'assets'/'photo.jpg')
            project={'metadata':{'duration':4,'width':320,'height':180},'source_file':'source.mp4','revision':1,'options':{'ratio':'16:9','style':'energetic','subtitles':'bilingual','sfx':True,'fit':'contain','zoom':True},'assets':{'photo':{'file':'photo.jpg','photographer':'Test'}},'music_file':'music.wav'}
            plan={'cuts':[{'id':'cut','start':1,'end':2,'enabled':True}],'captions':[{'id':'c','start':2,'end':3.5,'vi':'Dấu hỏi và dấu ngã','en':'Vietnamese tones'}],'visuals':[{'id':'v','start':2,'end':3.5,'kind':'photo','layout':'card','text':'Việt Nam','asset_id':'photo','enabled':True,'scale':1}]}
            result=render(project,plan,{},Context(folder),True)
            output=folder/result['file']
            self.assertTrue(output.stat().st_size>10000)
            raw=subprocess.run([binary('ffprobe'),'-v','error','-show_streams','-show_format','-of','json',str(output)],capture_output=True,check=True)
            probe=json.loads(raw.stdout)
            self.assertAlmostEqual(float(probe['format']['duration']),3,delta=.15)
            self.assertEqual({s['codec_type'] for s in probe['streams']},{'video','audio'})
            self.assertEqual(next(s for s in probe['streams'] if s['codec_type']=='audio')['channels'],2)
            self.assertTrue((folder/result['folder']/'subtitles.en.srt').exists())
            self.assertEqual(render(project,plan,{},Context(folder),True)['digest'],result['digest'])
            project['revision']=2
            self.assertEqual(render(project,plan,{},Context(folder),True)['revision'],2)

if __name__=='__main__':unittest.main()
