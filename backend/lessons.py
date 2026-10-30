"""Semantic lesson blocks. Times are always source seconds, independent of render chunks."""
import copy
import hashlib
import json
import math
import re
import unicodedata
from .timeline import Lesson, validate_plan
from .store import atomic_json

def lesson_key(text):
    # Do not remove Vietnamese diacritics: ma, má and mà are different lessons.
    return re.sub(r'[^\w\s]','',unicodedata.normalize('NFC',text).casefold()).strip()

def normalize_lessons(proposals,duration,locked=None):
    items=[]
    for raw in sorted(proposals,key=lambda item:item['start']):
        item={**raw,'id':raw.get('id') or 'lesson-'+hashlib.sha256((str(raw['start'])+raw['vi']).encode()).hexdigest()[:12]}
        item['start']=max(0,min(duration,float(item['start'])))
        item['end']=max(0,min(duration,float(item['end'])))
        if item['end']<=item['start']:
            continue
        item=Lesson.model_validate(item).model_dump()
        if items and lesson_key(items[-1]['vi'])==lesson_key(item['vi']):
            items[-1]['end']=max(items[-1]['end'],item['end'])
        else:
            items.append(item)
    if not items:
        raise ValueError('AI chưa xác định được mục bài học. Hãy thử lại hoặc thêm mục thủ công.')
    items[0]['start']=0
    for a,b in zip(items,items[1:]):
        a['end']=b['start']
    items[-1]['end']=duration
    # Locked intervals take precedence; AI may only fill their complement.
    for saved in sorted(locked or [],key=lambda item:item['start']):
        kept=[]
        for item in items:
            if item['end']<=saved['start'] or item['start']>=saved['end']:
                kept.append(item);continue
            if item['start']<saved['start']:
                kept.append({**item,'end':saved['start'],'id':item['id']+'-before'})
            if item['end']>saved['end']:
                kept.append({**item,'start':saved['end'],'id':item['id']+'-after'})
        items=sorted([*kept,copy.deepcopy(saved)],key=lambda item:item['start'])
    return items

def analyze_lessons(project,base_plan,transcript,context,old_plan=None,edit_request=''):
    from .providers import chat,parse_json,SYSTEM
    duration=project['metadata']['duration']
    old_plan=old_plan or {}
    locked=[item for item in old_plan.get('lessons',[]) if item.get('locked')]
    if locked and len(locked)==len(old_plan.get('lessons',[])):
        return validate_plan({**base_plan,'schema_version':2,'visuals':[],'lessons':copy.deepcopy(locked)},duration)
    signature=hashlib.sha256(json.dumps({'version':1,'captions':transcript['captions'],'base':base_plan['summary'],'old_lessons':old_plan.get('lessons',[]),'request':edit_request},sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
    cache_dir=context.folder/'analysis'/'lessons'/signature
    cache_dir.mkdir(parents=True,exist_ok=True)
    proposals=[]
    count=max(1,math.ceil(duration/120))
    for index in range(count):
        context.progress(55+10*index/count,f'Chia mục bài học · phần {index+1}/{count}')
        start,end=index*120,min(duration,(index+1)*120)
        captions=[c for c in transcript['captions'] if c['end']>max(0,start-15) and c['start']<end]
        previous=proposals[-1] if proposals else None
        packet={'window':[start,end],'summary':base_plan['summary'],'glossary':base_plan.get('glossary',[]),'source_captions':captions,'previous_lesson':previous,'current_lessons':old_plan.get('lessons',[]),'EDIT_REQUEST':edit_request}
        instruction='''Xác định các MỤC KIẾN THỨC đang được dạy. Một mục là một từ/câu MỤC TIÊU (ví dụ Xin chào = Hello), KHÔNG phải từng câu chỉ dẫn như Ready?, Repeat after me, Your turn. Giữ cùng mục từ giới thiệu, giải nghĩa, đọc chậm, nhắc lại đến hết khoảng nghỉ luyện nói. Không đổi mục chỉ vì đổi phụ đề hoặc tới mốc 120 giây. Nếu phần này tiếp tục previous_lesson, dùng CHÍNH XÁC vi/en của mục trước. Toàn bài có thể chỉ có MỘT mục, hãy giữ xuyên suốt. Với câu mới thực sự, tạo mục mới. Thời gian nguồn là giây, trong window. Đầu/cuối bài tiếp tục dùng mục gần nhất. Không bịa ví dụ hoặc cách giải thích chưa có trong bài.
Trả JSON {"lessons":[{"start":0,"end":120,"vi":"từ hoặc câu tiếng Việt cần học","en":"nghĩa tiếng Anh","chunks":[{"vi":"cụm tiếng Việt","en":"nghĩa"}],"photo_query":"specific English Pexels search"}]}. chunks tối đa 3, chỉ cần khi giúp giải thích một CÂU, từ đơn để []. Ảnh phải đúng tình huống/sự vật bài học, chọn bối cảnh thực tế tìm được trên Pexels. Bản tiếng Việt và tiếng Anh là NỘI DUNG BÀI HỌC, không chép lại cả lời giảng. Trong EDIT_REQUEST chỉ sửa yêu cầu được nêu; giữ các mục đã chỉnh tay trong current_lessons khi không liên quan. Các mục locked sẽ được hệ thống giữ nguyên.'''
        messages=[{'role':'system','content':SYSTEM},{'role':'user','content':instruction+'\nDATA: '+json.dumps(packet,ensure_ascii=False)}]
        path=cache_dir/f'{index:03}.json'
        part=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        for attempt in range(3):
            try:
                if part is None:
                    raw,_=chat(messages,context,5000)
                    part=parse_json(raw)
                rows=part['lessons']
                if not rows:
                    raise ValueError('Thiếu mục bài học cho phần này')
                cleaned=[]
                for i,row in enumerate(rows):
                    item=Lesson.model_validate({**row,'id':f'lesson-{index}-{i}'}).model_dump()
                    if item['start']<start-.05 or item['end']>end+.05:
                        raise ValueError('Mốc mục bài học phải nằm trong window')
                    cleaned.append(item)
                atomic_json(path,part)
                proposals.extend(cleaned)
                break
            except (ValueError,TypeError,KeyError) as exc:
                if attempt==2:
                    raise ValueError('Chưa chia được mục bài học hợp lệ sau ba lần. Tiến độ đã được lưu.') from exc
                messages.append({'role':'user','content':'Sửa JSON đầy đủ: '+str(exc)[:300]})
                part=None
    plan={**base_plan,'schema_version':2,'visuals':[],'lessons':normalize_lessons(proposals,duration,locked)}
    # Reuse the illustration for the same learning target, including a later recurrence.
    previous_assets={lesson_key(item['vi']):item.get('asset_id') for item in old_plan.get('lessons',[]) if item.get('asset_id')}
    for item in plan['lessons']:
        item['asset_id']=item.get('asset_id') or previous_assets.get(lesson_key(item['vi']))
    return validate_plan(plan,duration)

def fetch_lesson_assets(project,plan,context,vision):
    from .providers import fetch_assets
    assets=dict(project.get('assets',{}));warnings=[];targets={}
    for index,item in enumerate(plan['lessons']):
        key=lesson_key(item['vi'])
        if item.get('asset_id') in assets:
            targets[key]=item['asset_id'];continue
        if key in targets:
            item['asset_id']=targets[key];continue
        if not item['photo_query'].strip():
            warnings.append('Chưa có từ khóa ảnh cho mục: '+item['vi']);continue
        visual={'id':item['id'],'start':item['start'],'end':item['end'],'kind':'photo','layout':'card','text':item['vi'],'translation':item['en'],'query':item['photo_query'],'asset_id':None,'enabled':True}
        proxy={**project,'assets':assets}
        assets,notes=fetch_assets(proxy,{'visuals':[visual]},context,vision)
        item['asset_id']=visual.get('asset_id')
        if item['asset_id']:
            targets[key]=item['asset_id']
        warnings.extend(notes)
    return assets,warnings
