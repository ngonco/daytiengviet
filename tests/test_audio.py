import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch,Mock

from fastapi.testclient import TestClient
from backend import store
from backend.app import app,Options
from backend.audio import measure,voice_filter,preview_level
from backend.media import ffmpeg,Cancelled,probe
from backend.render import render


class Context:
    kind='export'
    def __init__(self,folder):self.folder=folder
    def progress(self,*args):pass
    def check(self):pass


class AudioTests(unittest.TestCase):
    def tone(self,folder,seconds=5,volume=-25,name='voice.wav'):
        path=folder/name
        ffmpeg(['-f','lavfi','-i',f'sine=frequency=330:sample_rate=48000:duration={seconds}','-af',f'volume={volume}dB','-ac','2',path])
        return path
    def normalize(self,source,target,context,enabled=True):
        filters,details=voice_filter(['-i',source],context,enabled)
        ffmpeg(['-i',source,'-af',filters,'-c:a','pcm_s16le','-ar','48000','-ac','2',target],context)
        return details
    def test_quiet_and_loud_voices_reach_target_without_rewriting_source(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);ctx=Context(folder)
            for volume in [-28,12]:
                with self.subTest(volume=volume):
                    source=self.tone(folder,volume=volume);before=hashlib.sha256(source.read_bytes()).hexdigest()
                    raw=measure(['-i',source]);target=folder/'normalized.wav';details=self.normalize(source,target,ctx)
                    actual=measure(['-i',target])
                    self.assertAlmostEqual(actual['input_lufs'],-16,delta=.5)
                    self.assertLessEqual(actual['input_peak_db'],-1.4)
                    self.assertGreater(details['gain_db'],15) if volume<0 else self.assertLess(details['gain_db'],0)
                    self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)
                    self.assertAlmostEqual(probe_audio_duration(source),probe_audio_duration(target),delta=.002)
    def test_silence_and_very_short_audio_are_finite_and_safe(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);ctx=Context(folder);source=folder/'silence.wav'
            ffmpeg(['-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','2',source])
            details=self.normalize(source,folder/'silent-output.wav',ctx)
            self.assertTrue(details['silent']);self.assertEqual(details['gain_db'],0)
            result=measure(['-i',folder/'silent-output.wav']);self.assertTrue(result['silent'])
            short=self.tone(folder,seconds=.2,volume=-20)
            details=self.normalize(short,folder/'short-output.wav',ctx)
            self.assertFalse(details['silent']);self.assertGreater(details['gain_db'],0)
            self.assertAlmostEqual(probe_audio_duration(folder/'short-output.wav'),.2,delta=.01)
            json.dumps(details,allow_nan=False)
    def test_disable_and_cached_measurement_do_not_run_analysis(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);source=self.tone(folder);cache=folder/'level.json';ctx=Context(folder)
            first=measure(['-i',source],ctx,cache)
            with patch('backend.audio.subprocess.Popen',side_effect=AssertionError('cached analysis must not run')):
                self.assertEqual(measure(['-i',source],ctx,cache),first)
            with patch('backend.audio.measure',side_effect=AssertionError('disabled must not analyze')):
                filters,details=voice_filter(['-i',source],ctx,False)
                self.assertNotIn('loudnorm',filters);self.assertFalse(details['enabled'])
    def test_measurement_cancellation_terminates_process(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);source=self.tone(folder,seconds=20);ctx=Context(folder)
            ctx.check=Mock(side_effect=Cancelled('cancelled'))
            with self.assertRaises(Cancelled):measure(['-i',source],ctx)
    def test_preview_api_is_read_only_cached_and_rejects_trashed_project(self):
        with TemporaryDirectory() as tmp,patch('backend.store.data_root',return_value=Path(tmp)):
            store.init();pid='a'*16;folder=store.folder(pid);source=self.tone(folder)
            store.save({'id':pid,'source_file':source.name,'options':Options().model_dump()})
            project_before=store.read(pid);files={p.relative_to(folder) for p in folder.rglob('*')};client=TestClient(app)
            response=client.get(f'/api/projects/{pid}/audio-level');self.assertEqual(response.status_code,200)
            self.assertGreater(response.json()['gain_db'],15)
            with patch('backend.audio.measure',side_effect=AssertionError('warm source should not be remeasured')):
                self.assertEqual(client.get(f'/api/projects/{pid}/audio-level').json(),response.json())
            self.assertEqual(store.read(pid),project_before);self.assertEqual(store.jobs(),[])
            self.assertEqual({p.relative_to(folder) for p in folder.rglob('*')},files)
            store.update(pid,_retention={'state':'trashed'})
            self.assertEqual(client.get(f'/api/projects/{pid}/audio-level').status_code,410)
    def test_both_renderers_boost_quiet_voice_after_cuts_and_reuse_video_chunks(self):
        for layout in ['legacy','lesson']:
            with self.subTest(layout=layout),TemporaryDirectory() as tmp:
                folder=Path(tmp);source=folder/'source.mp4'
                ffmpeg(['-f','lavfi','-i','color=s=320x180:r=30:c=blue','-f','lavfi','-i','sine=frequency=330:sample_rate=48000','-t','4','-af','volume=-28dB','-c:v','libx264','-c:a','aac',source])
                p={'source_file':'source.mp4','metadata':{'width':320,'height':180,'duration':4},'options':{'ratio':'original','layout_mode':layout,'style':'education','fit':'cover','subtitles':'off','sfx':False,'auto_volume':True},'assets':{},'revision':1,'frames':[]}
                plan={'schema_version':2,'lessons':[{'id':'lesson','start':0,'end':4,'vi':'Có','en':'Yes','chunks':[]}],'cuts':[{'id':'c','start':1,'end':2,'enabled':True}],'captions':[],'visuals':[]}
                result=render(p,plan,{},Context(folder),False);output=folder/result['file']
                level=measure(['-i',output]);self.assertAlmostEqual(level['input_lufs'],-16,delta=.7)
                self.assertAlmostEqual(probe(output)['duration'],3,delta=.1)
                chunks={str(path):path.stat().st_mtime_ns for path in (folder/'render-cache').rglob('*.mkv')}
                # Include all chunk formats used by either renderer.
                chunks.update({str(path):path.stat().st_mtime_ns for path in (folder/'render-cache').rglob('*.mp4')})
                self.assertTrue(chunks)
                p['options']['auto_volume']=False;off=render(p,plan,{},Context(folder),False)
                self.assertNotEqual(result['digest'],off['digest']);self.assertFalse(off['audio']['enabled'])
                quiet=measure(['-i',folder/off['file']]);self.assertLess(quiet['input_lufs'],-35)
                self.assertEqual(chunks,{name:Path(name).stat().st_mtime_ns for name in chunks})


def probe_audio_duration(path):
    import subprocess
    from backend.config import binary
    result=subprocess.run([binary('ffprobe'),'-v','error','-show_entries','format=duration','-of','json',str(path)],capture_output=True,check=True)
    return float(json.loads(result.stdout)['format']['duration'])
