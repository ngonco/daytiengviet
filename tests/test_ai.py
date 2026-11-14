import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
from backend.providers import analyze,ProviderError

class Context:
    job_id='testjob'
    def __init__(self,folder):self.folder=folder
    def check(self):pass
    def progress(self,*args):pass

class AiTests(unittest.TestCase):
    def test_vision_rejection_and_invalid_json_recover_without_losing_locked_caption(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'frames').mkdir();(folder/'frames'/'f001.jpg').write_bytes(b'test-image')
            cue={'id':'c0','start':0,'end':2,'vi':'Hello.','original_vi':'Hello.','en':'','locked':False}
            transcript={'text':'Hello.','captions':[cue],'words':[]}
            project={'metadata':{'duration':4},'options':{'ratio':'9:16','style':'energetic','density':1}}
            locked={**cue,'vi':'Xin chào bạn.','en':'Hello there.','locked':True}
            replies=[ProviderError('Vilao',400),(json.dumps({'summary':'Bài học','glossary':[]}),{}),('not JSON',{}),(json.dumps({'translations':[{'id':'c0','vi':'Xin chào.','en':'Hello.'}],'cuts':[],'visuals':[]}),{})]
            with patch('backend.providers.chat',side_effect=replies),patch('backend.providers.settings',return_value={'VILAO_VISION_MODE':'auto'}):
                plan,warnings,vision=analyze(project,transcript,[{'time':0,'file':'f001.jpg'}],Context(folder),'Giữ đoạn đã khóa',{'captions':[locked]})
            self.assertFalse(vision)
            self.assertTrue(warnings)
            self.assertEqual(plan['captions'][0]['vi'],'Xin chào bạn.')
            self.assertTrue(plan['captions'][0]['locked'])


    def test_none_ignores_provider_cuts_and_restores_old_locked_cuts_but_keeps_translations(self):
        with TemporaryDirectory() as tmp:
            cue={'id':'c0','start':0,'end':2,'vi':'Hello.','original_vi':'Hello.','en':'','locked':False}
            transcript={'text':'Hello.','captions':[cue],'words':[]}
            project={'metadata':{'duration':4},'options':{'ratio':'9:16','style':'energetic','density':1,'cut_strength':'none'}}
            locked={'id':'old','start':1,'end':3,'enabled':True,'locked':True,'reason':'manual'}
            # A provider proposing even a whole-video removal cannot override none.
            replies=[(json.dumps({'summary':'Greeting','glossary':[]}),{}),
                     (json.dumps({'translations':[{'id':'c0','vi':'Xin chào.','en':'Hello.'}],'cuts':[{'start':0,'end':4,'reason':'AI'}],'visuals':[]}),{})]
            with patch('backend.providers.chat',side_effect=replies) as chat,patch('backend.providers.settings',return_value={}):
                plan,_,_=analyze(project,transcript,[],Context(Path(tmp)),old_plan={'cuts':[locked]})
                self.assertEqual(chat.call_count,2)
            self.assertEqual(len(plan['cuts']),1);self.assertFalse(plan['cuts'][0]['enabled'])
            self.assertTrue(locked['enabled']);self.assertEqual(plan['captions'][0]['vi'],'Xin chào.')

if __name__=='__main__':unittest.main()
