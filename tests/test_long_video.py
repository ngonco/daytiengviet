import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from backend.providers import transcribe
from backend.timeline import keep_spans,map_interval

class Context:
    def __init__(self,folder):self.folder=folder
    def check(self):pass
    def progress(self,*args):pass

class LongVideoTests(unittest.TestCase):
    def test_hour_audio_chunk_ownership_and_resume(self):
        # 12 cached provider-shaped responses exercise 60-minute orchestration without billable requests.
        with TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/'audio').mkdir()
            for i in range(12):
                start=max(0,i*300-1)
                global_times=[max(0,i*300-.4),i*300+.5,min(3599.5,(i+1)*300-.4)]
                response={'words':[{'word':f'w{round(t*10)}','start':max(0,t-start),'end':max(0,t-start)+.2} for t in global_times], 'segments':[]}
                (folder/'audio'/f'{i:03}.json').write_text(json.dumps(response),encoding='utf-8')
            project={'metadata':{'duration':3600},'source_file':'source.mp4','options':{'language':'auto'}}
            with patch('backend.providers.settings',return_value={'GROQ_API_KEY':'unit-test-placeholder'}),patch('backend.providers.request',side_effect=AssertionError('Must not repeat cached API calls')):
                transcript=transcribe(project,Context(folder))
                words=transcript['words']
                self.assertTrue(all(words[i]['start']<=words[i+1]['start'] for i in range(len(words)-1)))
                self.assertEqual(len({w['word'] for w in words}),len(words))
                self.assertGreater(words[-1]['end'],3599)
                self.assertEqual(transcribe(project,Context(folder)),transcript)
            spans=keep_spans(3600,[{'start':299.8,'end':300.4,'enabled':True},{'start':1799,'end':1802,'enabled':True}])
            mapped=map_interval(3590,3598,spans)
            self.assertAlmostEqual(mapped[0][0],3586.4)
            self.assertAlmostEqual(mapped[0][1],3594.4)

if __name__=='__main__':unittest.main()
