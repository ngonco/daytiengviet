import copy,json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock,patch
from backend.recut import recut,candidates
from backend.cut_policy import review
from backend.providers import ProviderError

def fixture():
    plan={'schema_version':2,'summary':'','glossary':[],'cuts':[],'captions':[],'visuals':[],
          'lessons':[{'id':'l','start':0,'end':12,'vi':'Danh từ','en':'Nouns','chunks':[],'photo_query':'','asset_id':None}]}
    words=[{'word':w,'start':i*.3,'end':i*.3+.2} for i,w in enumerate('We we use this form because'.split())]
    words += [{'word':w,'start':6+i*.3,'end':6.2+i*.3} for i,w in enumerate('the subject is plural here.'.split())]
    return {'plan':plan,'transcript':{'words':words},'metadata':{'duration':12},'options':{'cut_strength':'strong'},'source_file':'source.wav'}

def answer(messages,context,tokens):
    batch=json.loads(messages[-1]['content'])['candidates']
    return json.dumps({'decisions':[{'id':c['id'],'decision':'explanation_hesitation' if c['kind']=='silence' else 'accidental_stutter','context':'explanation'} for c in batch]}),{}

class CutPolicyTests(unittest.TestCase):
    def test_measured_silence_and_true_stutter_cut_with_cached_semantic_confirmation(self):
        p=fixture();before=copy.deepcopy(p)
        with TemporaryDirectory() as tmp:
            context=Mock(folder=Path(tmp))
            with patch('backend.recut.quiet_intervals',return_value=[(2,6)]),patch('backend.providers.chat',side_effect=answer) as chat:
                result=recut(p,context)
                self.assertEqual(len(result['cuts']),2);self.assertEqual(chat.call_count,1)
                self.assertEqual(recut(p,context),result);self.assertEqual(chat.call_count,1)
                p['plan']['lessons'][0]['en']='Different target'
                recut(p,context);self.assertEqual(chat.call_count,2)
            self.assertEqual({k:v for k,v in result.items() if k!='cuts'},{k:v for k,v in before['plan'].items() if k!='cuts'})
            self.assertEqual(before['plan']['cuts'],[])

    def test_teaching_uncertain_missing_duplicate_wrong_kind_and_unknown_ids_never_cut(self):
        p=fixture();proposed=candidates(p['plan'],p['transcript'],12,[(2,6)])
        gap=next(c for c in proposed if c['kind']=='silence')
        bad=[
            {'decisions':[{'id':gap['id'],'decision':'explanation_hesitation','context':'teaching'}]},
            {'decisions':[{'id':gap['id'],'decision':'explanation_hesitation','context':'uncertain'}]},
            {'decisions':[{'id':gap['id'],'decision':'accidental_stutter','context':'explanation'}]},
            {'decisions':[{'id':'invented','decision':'explanation_hesitation','context':'explanation'}]},
            {'decisions':[]},
            {'decisions':[{'id':gap['id'],'decision':'explanation_hesitation','context':'explanation'}]*2}]
        for response in bad:
            with self.subTest(response=response),TemporaryDirectory() as tmp:
                with patch('backend.providers.chat',return_value=(json.dumps(response),{})):
                    self.assertEqual(review([gap],Mock(folder=Path(tmp))),set())

    def test_teacher_turns_in_both_languages_kept_even_if_not_literal_lesson_targets(self):
        for left,right in [('Good morning','Chào buổi sáng'),('Chào buổi sáng','Chào buổi sáng'),('Chào buổi sáng','Good morning')]:
            p=fixture()
            p['transcript']['words']=[{'word':left,'start':0,'end':1},{'word':right,'start':9,'end':10}]
            def teaching(messages,context,tokens):
                batch=json.loads(messages[-1]['content'])['candidates']
                self.assertEqual(batch[0]['before'][0]['word'],left)
                self.assertEqual(batch[0]['after'][0]['word'],right)
                return json.dumps({'decisions':[{'id':c['id'],'decision':'keep','context':'teaching'} for c in batch]}),{}
            with TemporaryDirectory() as tmp,patch('backend.recut.quiet_intervals',return_value=[(1.1,8.9)]),patch('backend.providers.chat',side_effect=teaching):
                self.assertEqual(recut(p,Mock(folder=Path(tmp)))['cuts'],[])

    def test_empty_candidates_skip_provider_and_failed_review_preserves_input(self):
        p=fixture();before=copy.deepcopy(p)
        with TemporaryDirectory() as tmp:
            context=Mock(folder=Path(tmp))
            with patch('backend.providers.chat') as chat:
                self.assertEqual(review([],context),set());chat.assert_not_called()
            with patch('backend.recut.quiet_intervals',return_value=[(2,6)]),patch('backend.providers.chat',side_effect=ProviderError('Vilao',503)):
                with self.assertRaises(ProviderError):recut(p,context)
            self.assertEqual(p,before)
            self.assertFalse((Path(tmp)/'analysis/cut-policy').exists())

    def test_batched_review_resumes_completed_batches_after_provider_failure(self):
        proposed=[{'id':str(i),'kind':'silence','start':i*5,'end':i*5+4,'before':[],'after':[],'targets':[]} for i in range(25)]
        with TemporaryDirectory() as tmp:
            context=Mock(folder=Path(tmp))
            with patch('backend.providers.chat',side_effect=[answer([{'content':json.dumps({'candidates':proposed[:24]})}],context,4000),ProviderError('Vilao',503)]):
                with self.assertRaises(ProviderError):review(proposed,context)
            with patch('backend.providers.chat',side_effect=answer) as chat:
                self.assertEqual(len(review(proposed,context)),25);self.assertEqual(chat.call_count,1)

    def test_existing_pipeline_retry_and_revision_do_not_recut_saved_project(self):
        from backend import store
        from backend.worker import execute
        from backend.app import Options
        for kind in ['pipeline','revise']:
            with self.subTest(kind=kind),TemporaryDirectory() as tmp,patch('backend.store.data_root',return_value=Path(tmp)):
                store.init();p=fixture();pid='a123456789abcdef'
                p.update(id=pid,title='Synthetic',revision=1,status='ready',assets={})
                p['options']=Options(layout_mode='legacy').model_dump()
                p['plan']['cuts']=[{'id':'cut-0-0','start':2,'end':5,'reason':'Old automatic','enabled':True,'locked':False}]
                store.save(p);job=store.job_create(pid,kind)
                with patch('backend.worker.extract_frames',return_value=[]),patch('backend.worker.transcribe',return_value=p['transcript']),patch('backend.worker.analyze',return_value=(copy.deepcopy(p['plan']),[],False)),patch('backend.worker.fetch_assets',return_value=({},[])),patch('backend.worker.prepared_render',return_value={}),patch('backend.recut.recut') as cut:
                    execute(job);cut.assert_not_called()
                self.assertEqual(store.read(pid)['plan']['cuts'],p['plan']['cuts'])

    def test_new_pipeline_uses_shared_policy_and_explicit_recut_versions_old_plan(self):
        from backend import store
        from backend.worker import execute
        from backend.app import Options
        with TemporaryDirectory() as tmp,patch('backend.store.data_root',return_value=Path(tmp)):
            store.init();p=fixture();pid='a123456789abcdef';new_plan=p['plan']
            p.update(id=pid,title='Synthetic',revision=0,status='new',assets={},plan=None)
            p['options']=Options(layout_mode='legacy').model_dump();store.save(p)
            with patch('backend.worker.extract_frames',return_value=[]),patch('backend.worker.transcribe',return_value=p['transcript']),patch('backend.worker.analyze',return_value=(new_plan,[],False)),patch('backend.worker.fetch_assets',return_value=({},[])),patch('backend.worker.prepared_render',return_value={}),patch('backend.recut.quiet_intervals',return_value=[(2,6)]),patch('backend.providers.chat',side_effect=answer):
                job=store.job_create(pid,'pipeline');execute(job);store.job_update(job['id'],status='succeeded')
                self.assertEqual(len(store.read(pid)['plan']['cuts']),2)
                old=store.read(pid);job=store.job_create(pid,'recut');execute(job)
                saved=json.loads((store.folder(pid)/f"versions/v{old['revision']:05}.json").read_text(encoding='utf-8'))
                self.assertEqual(saved['plan'],old['plan'])
                self.assertEqual(store.read(pid)['revision'],old['revision']+1)
