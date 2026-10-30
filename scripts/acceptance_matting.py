"""Opt-in GPU acceptance on a separate copy of a saved lesson project.

No provider calls: reuse the saved transcript/lessons/assets. Runtime and private
outputs remain under data/ and OUTPUT/. Run: python -m scripts.acceptance_matting
"""
import hashlib
import io
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path
import httpx
from PIL import Image,ImageDraw
from backend import store
from backend.config import ROOT,settings
from backend.media import ffmpeg,probe
from backend.templates import font

OUT=ROOT/'OUTPUT/matting';OUT.mkdir(parents=True,exist_ok=True)
BASE=f"http://127.0.0.1:{settings().get('APP_PORT') or 8876}/api"
client=httpx.Client(timeout=150)


def call(method,path,**kwargs):
    response=client.request(method,BASE+path,**kwargs);response.raise_for_status();return response.json()


def wait(pid):
    last='';deadline=time.monotonic()+7200
    while time.monotonic()<deadline:
        p=call('GET',f'/projects/{pid}');j=p['jobs'][0]
        if j['status'] in ['failed','cancelled']:raise RuntimeError(j.get('error') or j['status'])
        if j['status']=='succeeded':return p
        if j['message']!=last:print(j['message'],flush=True);last=j['message']
        time.sleep(1)
    raise TimeoutError('Acceptance timeout')


def create_demo():
    existing={p['id']:store.read(p['id']) for p in store.listing() if not p.get('diagnostic')}
    source=next((p for p in existing.values() if p['options'].get('layout_mode')=='lesson' and p.get('plan',{}).get('lessons')),None)
    if not source:raise RuntimeError('Create a lesson project before running this opt-in check.')
    project=json.loads(json.dumps(source));pid=store.uid();folder=store.folder(pid);origin=store.folder(source['id'])
    shutil.copy2(origin/source['source_file'],folder/source['source_file'])
    for name in ['assets','frames']:
        if (origin/name).is_dir():shutil.copytree(origin/name,folder/name)
    if (origin/'transcript.json').exists():shutil.copy2(origin/'transcript.json',folder/'transcript.json')
    project.update(id=pid,title='Xóa phông · Duyệt chất lượng',revision=1,status='ready',preview=None,export=None,created_at=store.now())
    project.pop('matting',None)
    project['options'].update(ratio='9:16',background_removal={'enabled':True,'device':'cuda','soften':.6,'contract':0,'strokes':[]})
    store.save(project)
    state={'project_id':pid,'originals':existing};store.atomic_json(OUT/'state.json',state)
    return state


def run():
    state=json.loads((OUT/'state.json').read_text(encoding='utf-8')) if '--resume' in sys.argv else create_demo()
    pid=state['project_id'];folder=store.folder(pid);started=time.perf_counter()
    if '--resume' not in sys.argv:
        job=call('POST',f'/projects/{pid}/jobs/preview');deadline=time.monotonic()+1800
        # Exercise actual cancellation after the first durable segment, then resume.
        while not list((folder/'matting').glob('*/00000/complete.json')):
            j=call('GET',f"/jobs/{job['id']}")
            if j['status']=='failed':raise RuntimeError(j['error'])
            print(j['message'],flush=True)
            if time.monotonic()>deadline:raise TimeoutError('First matting segment timed out')
            time.sleep(3)
        first=next((folder/'matting').glob('*/00000/complete.json'))
        checksum=hashlib.sha256((first.parent/'alpha.mkv').read_bytes()).hexdigest()
        call('POST',f"/jobs/{job['id']}/cancel")
        while call('GET',f"/jobs/{job['id']}")['status'] in ['queued','running','cancelling']:time.sleep(.5)
        call('POST',f'/projects/{pid}/jobs/preview');project=wait(pid)
        assert hashlib.sha256((first.parent/'alpha.mkv').read_bytes()).hexdigest()==checksum
        assert project['matting']['stats']['resumed_frames']>=600
        state['cancel_resume_passed']=True
    else:
        p=call('GET',f'/projects/{pid}')
        if not any(j['status'] in ['running','queued','cancelling'] for j in p['jobs']):call('POST',f'/projects/{pid}/jobs/preview')
        project=wait(pid)
    code=project['matting']['code'];stats=project['matting']['stats'];state['stats']=stats
    for ratio,label in [('9:16','9x16'),('16:9','16x9')]:
        if project['options']['ratio']!=ratio:
            call('PUT',f'/projects/{pid}/plan',json={'revision':project['revision'],'plan':project['plan'],'options':{**project['options'],'ratio':ratio}});project=wait(pid)
        call('POST',f'/projects/{pid}/jobs/export');project=wait(pid)
        assert project['matting']['code']==code
        target=OUT/f'Vietnamese_with_Vinh_xoa_phong_{label}.mp4';shutil.copy2(folder/project['export']['file'],target)
        ffmpeg(['-i',target,'-f','null','-']);state[label]={'file':target.name,**probe(target)}
        ffmpeg(['-ss',12,'-i',target,'-frames:v',1,'-vf','scale=540:-2',OUT/f'{label}.jpg'])
    # Hair/ears/collar/hands and boundaries; save all three backgrounds for visual inspection.
    times=[.2,5,12,19.9667,20.0333,30,39.9667,40.0333,50,project['metadata']['duration']-.15]
    thumbs=[]
    for t in times:
        for bg in ['cream','black','white']:
            r=client.get(BASE+f'/projects/{pid}/matting/frame',params={'time':t,'background':bg});r.raise_for_status()
            path=OUT/f'frame-{t:.2f}-{bg}.png';path.write_bytes(r.content)
            image=Image.open(path).convert('RGB')
            # A successful HTTP response must still contain the person, including segment ends.
            import numpy as np
            assert np.asarray(image).std()>15,('Blank comparison frame',t,bg)
            image.thumbnail((180,310));thumbs.append((t,bg,image.copy()))
    sheet=Image.new('RGB',(180*6,345*5),'#dededb');draw=ImageDraw.Draw(sheet)
    for i,(t,bg,im) in enumerate(thumbs):
        x=i%6*180;y=i//6*345;sheet.paste(im,(x,y+30));draw.text((x+4,y+4),f'{t:.2f}s · {bg}',font=font(14),fill='#063c40')
    sheet.save(OUT/'kiem_tra_vien.jpg',quality=94)
    for oldid,original in state['originals'].items():assert store.read(oldid)==original,'Existing project changed: '+oldid
    backup=client.get(BASE+f'/projects/{pid}/download/project');backup.raise_for_status();(OUT/'VietCut_xoa_phong.zip').write_bytes(backup.content)
    with zipfile.ZipFile(io.BytesIO(backup.content)) as archive:
        assert not any(n.startswith('matting/') for n in archive.namelist())
        assert json.loads(archive.read('project.json'))['options']['background_removal']['enabled']
    state.update(originals_unchanged=True,full_decode=True,matting_cache_reused_both_ratios=True,wall_seconds_including_cancel_resume_and_exports=time.perf_counter()-started,quality_approval='pending user review')
    store.atomic_json(OUT/'acceptance.json',{k:v for k,v in state.items() if k!='originals'})
    print(json.dumps({k:v for k,v in state.items() if k not in ['originals']},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':run()
