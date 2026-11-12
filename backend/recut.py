"""Local, source-timed recutting. Audio evidence wins over coarse STT word durations."""
import copy,hashlib,math,re
from tempfile import TemporaryDirectory
from pathlib import Path
import numpy as np
from .media import ffmpeg
from .timeline import validate_plan,keep_spans

VERSION=2
LEVELS={'light':(1.2,.45),'medium':(.85,.35),'strong':(.6,.25)}
PRACTICE=re.compile(r'repeat|your turn|say it|say after|try it|practice|practise|listen and|read aloud|nhắc lại|đọc theo|lặp lại|luyện|đến lượt',re.I)
def text(value):return ' '.join(re.findall(r'\w+',value.lower(),re.UNICODE))
def practice_at(words,point):
    return bool(PRACTICE.search(' '.join(w['word'] for w in words if point-8<=w['start']<=point)))
def quiet_intervals(source,context):
    with TemporaryDirectory() as tmp:
        raw=Path(tmp)/'audio.pcm'
        ffmpeg(['-i',source,'-vn','-ac','1','-ar','16000','-f','s16le',raw],context)
        # Streaming 20ms windows; only scalar levels are retained.
        levels=[]
        with raw.open('rb') as stream:
            while block:=stream.read(640):
                a=np.frombuffer(block,dtype='<i2').astype(np.float32)/32768
                levels.append((float(np.sqrt(np.mean(a*a))),float(np.max(np.abs(a)))))
        if not levels:return []
        threshold=min(10**(-34/20),max(10**(-44/20),float(np.percentile([v[0] for v in levels],15))*1.8))
        spans=[];start=None
        for i,(rms,peak) in enumerate(levels+[(1,1)]):
            silent=rms<threshold and peak<threshold*3
            if silent and start is None:start=i*.02
            if not silent and start is not None:
                if i*.02-start>=.3:spans.append((start,i*.02))
                start=None
        return spans

def propose(plan,transcript,duration,silences,strength='strong'):
    result=copy.deepcopy(plan);words=sorted(transcript.get('words',[]),key=lambda w:w['start'])
    minimum,keep=LEVELS[strength];candidates=[]
    # Respect enabled AND restored manual cuts; regeneration replaces only our unlocked cuts.
    original=[c for c in result.get('cuts',[]) if c.get('locked') or not c['id'].startswith('tighten-')]
    def add(a,b,reason):
        a=math.ceil(max(0,a)*30-1e-6)/30;b=math.floor(min(duration,b)*30+1e-6)/30
        if b-a<.12:return
        if any(c.get('locked') and a<c['end'] and b>c['start'] for c in original):return
        candidate={'id':'tighten-'+hashlib.sha256(f'{a:.6f}:{b:.6f}'.encode()).hexdigest()[:14],'start':a,'end':b,'reason':reason,'enabled':True,'locked':False}
        if keep_spans(duration,original+candidates+[candidate]) and sum(s['end']-s['start'] for s in keep_spans(duration,original+candidates+[candidate]))>=min(.5,duration):candidates.append(candidate)
    for a,b in silences:
        if b-a<minimum or practice_at(words,a):continue
        add(a+keep/2,b-keep/2,'Rút khoảng dừng thừa · '+strength)
    # Exact nearby retakes of long clauses. Short teaching targets and practice remain protected.
    tokens=[text(w['word']) for w in words]
    targets=[text(l['vi']).split() for l in plan.get('lessons',[])]
    occupied=-1
    for i in range(len(words)):
        if i<occupied or practice_at(words,words[i]['start']):continue
        for j in range(i+6,min(len(words),i+70)):
            if words[j]['start']-words[i]['end']>22:break
            n=0
            while i+n<j and j+n<len(words) and tokens[i+n] and tokens[i+n]==tokens[j+n]:n+=1
            if n<6:continue
            phrase=tokens[i:i+n]
            if any(t and ' '.join(t) in ' '.join(phrase) for t in targets):continue
            # Require a complete sentence or a clear restart marker after the first take.
            following=' '.join(tokens[i+n:j])
            complete=words[i+n-1]['word'].endswith(('.', '!', '?'))
            if not complete and not re.search(r'\b(sorry|no|oops|xin lỗi)\b',following):continue
            if practice_at(words,words[j]['start']):continue
            begin=i
            while begin>0 and i-begin<6 and words[i]['start']-words[begin-1]['start']<5 and not words[begin-1]['word'].endswith(('.', '!', '?')):
                begin-=1
            if practice_at(words,words[begin]['start']):continue
            a=max(0,words[begin]['start']-.08);b=min(words[i+n-1]['end']+.08,words[j]['start']-.08)
            add(a,b,'Bỏ lượt nói lại trùng câu; giữ lượt sau hoàn chỉnh')
            occupied=i+n;break
    result['cuts']=original+candidates
    validated=validate_plan(result,duration)
    locked={c['id']:c for c in original if c.get('locked')}
    result['cuts']=[copy.deepcopy(locked.get(c['id'],c)) for c in validated['cuts']]
    return result

def recut(project,context):
    context.progress(4,'Đo khoảng dừng và kiểm tra lượt nói lại')
    intervals=quiet_intervals(context.folder/project['source_file'],context)
    plan=propose(project['plan'],project.get('transcript') or {},project['metadata']['duration'],intervals,project['options'].get('cut_strength','strong'))
    return plan
