import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from backend.lessons import normalize_lessons,analyze_lessons,fetch_lesson_assets,lesson_key
from backend.timeline import validate_plan,keep_spans
from backend.lesson_render import mapped_lessons,subtitle_image
from backend.templates import geometry,make_frame,fit_text
from backend.app import Options

def lesson(start=0,end=180,vi='Xin chào',id='l1',**extra):
    return {'id':id,'start':start,'end':end,'vi':vi,'en':'Hello','chunks':[],'photo_query':'people greeting Vietnam','asset_id':None,'locked':False,'photo_candidates':[],'photo_crops':{},**extra}

class Context:
    job_id='test-lessons'
    def __init__(self,folder):self.folder=folder
    def check(self):pass
    def progress(self,*args):pass

class LessonTests(unittest.TestCase):
    def test_same_target_merges_across_120_seconds(self):
        items=normalize_lessons([lesson(5,120),lesson(120,180,id='l2')],180)
        self.assertEqual(len(items),1)
        self.assertEqual((items[0]['start'],items[0]['end']),(0,180))
        self.assertNotEqual(lesson_key('ma'),lesson_key('má'))
    def test_locked_content_and_boundaries_win(self):
        locked=lesson(40,100,'Cảm ơn','locked',en='Thank you',locked=True)
        items=normalize_lessons([lesson()],180,[locked])
        self.assertEqual(next(i for i in items if i['id']=='locked'),locked)
        self.assertEqual([(i['start'],i['end']) for i in items],[(0,40),(40,100),(100,180)])
    def test_reject_gaps_overlaps_or_missing_coverage(self):
        for items in [[lesson(5,180)],[lesson(0,50),lesson(60,180,id='l2')],[lesson(0,80),lesson(60,180,id='l2')]]:
            with self.assertRaises(ValueError):validate_plan({'schema_version':2,'lessons':items},180)
    def test_cuts_keep_one_continuous_lesson(self):
        plan={'lessons':[lesson()], 'cuts':[{'start':50,'end':70,'enabled':True}]}
        mapped=mapped_lessons(plan,keep_spans(180,plan['cuts']))
        self.assertEqual(len(mapped),1)
        self.assertEqual((mapped[0]['output_start'],mapped[0]['output_end']),(0,160))
    def test_window_context_prevents_artificial_lesson_change(self):
        with TemporaryDirectory() as tmp:
            ctx=Context(Path(tmp));p={'metadata':{'duration':180}};base={'summary':'Chào hỏi','captions':[],'cuts':[],'visuals':[]}
            transcript={'captions':[{'id':'c','start':0,'end':180,'vi':'Xin chào'}]}
            responses=[(json.dumps({'lessons':[lesson(0,120)]}),{}),(json.dumps({'lessons':[lesson(120,180,id='l2')]}),{})]
            with patch('backend.providers.chat',side_effect=responses) as call:
                plan=analyze_lessons(p,base,transcript,ctx)
            self.assertEqual(len(plan['lessons']),1)
            packet=call.call_args_list[1].args[0][1]['content']
            self.assertIn('previous_lesson',packet)
            self.assertIn('Xin chào',packet)
    def test_repeat_target_reuses_image(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'assets').mkdir();known={str(i):{'file':f'{i}.jpg'} for i in range(10)}
            for asset in known.values():(folder/'assets'/asset['file']).write_bytes(b'cached')
            plan={'lessons':[lesson(0,10,asset_id='0',photo_candidates=list(known)),lesson(10,20,id='l2')]}
            with patch('backend.providers.search_photos',side_effect=AssertionError('Must reuse saved set')):
                assets,warnings=fetch_lesson_assets({'assets':known},plan,Context(folder),False)
            self.assertEqual(plan['lessons'][1]['asset_id'],'0')
    def test_template_and_subtitle_regions_in_both_ratios(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp)
            p={'assets':{}}
            for w,h in [(1080,1920),(1920,1080)]:
                g=make_frame(p,lesson(end=5,vi='Cho tôi một ly cà phê.',en="I'd like a cup of coffee, please.",chunks=[{'vi':'một ly','en':'a cup'}]),folder,w,h,folder/f'frame-{w}.png')
                sw,sh=subtitle_image({'vi':'Lặp lại theo mình','en':'Repeat after me'},w,h,folder/f'sub-{w}.png')
                sx,sy,cw,ch=g['speaker']
                self.assertLess(sw,cw);self.assertLess(sh,ch*.34+1)
                self.assertLessEqual(sy+ch,h)
    def test_long_text_fails_instead_of_ellipsis(self):
        with self.assertRaises(ValueError):fit_text('rất dài '*300,300,100,60,30,max_lines=2)
    def test_old_options_remain_legacy(self):
        self.assertEqual(Options.model_validate({'ratio':'9:16'}).layout_mode,'legacy')
    def test_fully_locked_lesson_never_calls_ai_again(self):
        with TemporaryDirectory() as tmp:
            saved=lesson(locked=True)
            with patch('backend.providers.chat',side_effect=AssertionError('Locked lessons must be reused')):
                result=analyze_lessons({'metadata':{'duration':180}},{'summary':'Bài học','cuts':[],'captions':[],'visuals':[]},{},Context(Path(tmp)),{'lessons':[saved]},'Giữ nội dung')
            self.assertEqual(result['lessons'][0],saved)
    def test_ai_revision_preserves_selected_photo_pool_and_ratio_crops(self):
        with TemporaryDirectory() as tmp:
            saved=lesson(0,2,asset_id='user-choice',photo_candidates=['user-choice','alternative'],photo_crops={'9:16':{'x':.2,'y':.7,'zoom':1.5}})
            proposal=lesson(0,2,asset_id='ai-choice')
            base={'summary':'Chào hỏi','captions':[],'cuts':[],'visuals':[]}
            with patch('backend.providers.chat',return_value=(json.dumps({'lessons':[proposal]}),{})):
                result=analyze_lessons({'metadata':{'duration':2}},base,{'captions':[]},Context(Path(tmp)),{'lessons':[saved]},'Giữ bài học')
            row=result['lessons'][0]
            for key in ['asset_id','photo_candidates','photo_crops']:self.assertEqual(row[key],saved[key])
    def test_whitespace_lesson_text_is_rejected(self):
        with self.assertRaises(ValueError):validate_plan({'schema_version':2,'lessons':[lesson(0,180,vi='   ')]},180)

if __name__=='__main__':unittest.main()
