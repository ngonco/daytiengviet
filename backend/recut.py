"""Source-timed recutting: audio/word evidence, then conservative semantic review."""
import copy,hashlib,math,re
from tempfile import TemporaryDirectory
from pathlib import Path
import numpy as np
from .media import ffmpeg
from .timeline import validate_plan,keep_spans

VERSION=4
# All levels obey >3s; strength changes only the breathing space left behind.
LEVELS={'light':.45,'medium':.35,'strong':.25}
PRACTICE=re.compile(r'repeat|your turn|say it|say after|try it|practi[cs]e|listen and|read aloud|nhắc lại|đọc theo|lặp lại|luyện|đến lượt',re.I)

def text(value):return ' '.join(re.findall(r'\w+',value.lower(),re.UNICODE))

def quiet_intervals(source,context):
    with TemporaryDirectory() as tmp:
        raw=Path(tmp)/'audio.pcm'
        ffmpeg(['-i',source,'-vn','-ac','1','-ar','16000','-f','s16le',raw],context)
        levels=[]
        with raw.open('rb') as stream:
            while block:=stream.read(640):
                a=np.frombuffer(block,dtype='<i2').astype(np.float32)/32768
                levels.append((float(np.sqrt(np.mean(a*a))),float(np.max(np.abs(a)))))
                if context and len(levels)%500==0:context.check()
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

def restore_all_cuts(plan):
    result=copy.deepcopy(plan)
    for cut in result.get('cuts',[]):cut['enabled']=False
    return result

def automatic(cut):
    return cut['id'].startswith('tighten-') or bool(re.fullmatch(r'cut-\d+-\d+',cut['id']))

def candidates(plan,transcript,duration,silences,strength='strong'):
    """Only propose measured gaps and immediate short duplicates, never whole retakes."""
    if strength=='none':return []
    words=sorted(transcript.get('words',[]),key=lambda w:w['start'])
    tokens=[text(w['word']) for w in words]
    targets=set()
    for item in [*plan.get('lessons',[]),*plan.get('glossary',[])]:
        for part in [item,*item.get('chunks',[])]:
            targets.update(text(part.get(lang,'')) for lang in ['vi','en'])
    targets.discard('')
    # Exact spoken target matches protect BOTH languages, including adjacent repetitions.
    protected=set()
    for target in targets:
        phrase=target.split();n=len(phrase)
        for i in range(len(tokens)-n+1):
            if tokens[i:i+n]==phrase:protected.update(range(i,i+n))
    original=[c for c in plan.get('cuts',[]) if c.get('locked') or not automatic(c)]
    result=[]
    def add(a,b,kind,left,right):
        a=math.ceil(max(0,a)*30-1e-6)/30;b=math.floor(min(duration,b)*30+1e-6)/30
        if b-a<.12 or any(c.get('locked') and a<c['end'] and b>c['start'] for c in original):return
        # Word-index context survives arbitrarily long learner waits; no eight-second expiry.
        before=words[max(0,left-35):left+1];after=words[right:right+36]
        if not before or not after:return
        if PRACTICE.search(' '.join(w['word'] for w in before[-16:])):return
        if any(w.get('start',0)<b and w.get('end',w.get('start',0))>a for w in transcript.get('warnings',[])):return
        relevant=[{k:l.get(k) for k in ['vi','en','chunks']} for l in plan.get('lessons',[]) if l['start']<=b and l['end']>=a]
        identity=hashlib.sha256(f'{VERSION}:{kind}:{a:.6f}:{b:.6f}'.encode()).hexdigest()[:14]
        result.append({'id':'tighten-'+identity,'start':a,'end':b,'kind':kind,
                       'before':before,'after':after,'targets':relevant})
    for a,b in silences:
        # Missing/coarse timestamps and overlapping speech are uncertainty, not permission.
        if b-a<=3+1e-6 or any(w['start']<b-.08 and w['end']>a+.08 for w in words):continue
        left=next((i for i in range(len(words)-1,-1,-1) if words[i]['end']<=a+.08),None)
        right=next((i for i,w in enumerate(words) if w['start']>=b-.08),None)
        if left is None or right is None or left in protected or right in protected:continue
        keep=LEVELS[strength]
        add(a+keep/2,b-keep/2,'silence',left,right)
    for i in range(len(words)):
        for n in range(1,4):
            j=i+n
            if j+n>len(words) or not all(tokens[i:j]) or tokens[i:j]!=tokens[j:j+n]:continue
            # Keep whole sample repetitions; a false start before the complete target
            # ("hôm hôm nay") may still be reviewed without removing that target.
            if any(k in protected for k in range(i,j)):continue
            if any(re.search(r'[.!?…。！？]$',w['word']) for w in words[i:j]):continue
            if any(words[k+1]['start']-words[k]['end']>.4 for k in range(i,j+n-1)):continue
            if words[j+n-1]['end']-words[i]['start']>4:continue
            a=max(words[i-1]['end'] if i else 0,words[i]['start']-.04)
            b=min(words[j-1]['end']+.04,words[j]['start'])
            add(a,b,'stutter',j-1,j)
    return result

def propose(plan,transcript,duration,silences,strength='strong',approved=()):
    if strength=='none':return restore_all_cuts(plan)
    result=copy.deepcopy(plan)
    original=[c for c in result.get('cuts',[]) if c.get('locked') or not automatic(c)]
    cuts=original[:];approved=set(approved)
    for candidate in candidates(plan,transcript,duration,silences,strength):
        if candidate['id'] not in approved:continue
        a,b=candidate['start'],candidate['end']
        if any(a<c['end'] and b>c['start'] for c in cuts):continue
        cut={k:candidate[k] for k in ['id','start','end']}
        cut.update(reason='Rút ngập ngừng trên 3 giây trong phần giải thích' if candidate['kind']=='silence' else 'Bỏ từ lặp do nói vấp; giữ lượt nói sau',enabled=True,locked=False)
        if sum(s['end']-s['start'] for s in keep_spans(duration,cuts+[cut]))>=min(.5,duration):cuts.append(cut)
    result['cuts']=cuts
    validated=validate_plan(result,duration)
    preserved={c['id']:c for c in original}
    result['cuts']=[copy.deepcopy(preserved.get(c['id'],c)) for c in validated['cuts']]
    return result

def recut(project,context):
    strength=project['options'].get('cut_strength','strong')
    if strength=='none':
        context.progress(4,'Giữ nguyên toàn bộ video · khôi phục mọi đoạn cắt')
        return restore_all_cuts(project['plan'])
    from .cut_policy import review
    context.progress(4,'Đo khoảng ngập ngừng trên 3 giây và kiểm tra từ nói vấp')
    intervals=quiet_intervals(context.folder/project['source_file'],context)
    plan=project['plan'];transcript=project.get('transcript') or {};duration=project['metadata']['duration']
    proposed=candidates(plan,transcript,duration,intervals,strength)
    approved=review(proposed,context)
    return propose(plan,transcript,duration,intervals,strength,approved)
