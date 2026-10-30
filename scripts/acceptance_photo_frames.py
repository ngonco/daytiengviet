"""Opt-in live Pexels/Vilao acceptance on a separate saved-project clone.

Reuses source transcript and committed matting. Never modifies the user's projects.
Run: python -X utf8 -m scripts.acceptance_photo_frames [--resume]
"""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import time
import zipfile
import httpx
from PIL import Image,ImageDraw
from backend import store
from backend.config import ROOT,settings
from backend.media import ffmpeg,probe
from backend.templates import font

OUT=ROOT/'OUTPUT/photo_frames';OUT.mkdir(parents=True,exist_ok=True)
BASE=f"http://127.0.0.1:{settings().get('APP_PORT') or 8876}/api"
client=httpx.Client(timeout=150)


def call(method,path,**kwargs):
    r=client.request(method,BASE+path,**kwargs);r.raise_for_status();return r.json()


def wait(pid):
    last='';deadline=time.monotonic()+3600
    while time.monotonic()<deadline:
        p=call('GET',f'/projects/{pid}');job=p['jobs'][0]
        if job['status'] in ['failed','cancelled']:raise RuntimeError(job.get('error') or job['status'])
        if job['message']!=last:print(job['message'],flush=True);last=job['message']
        if job['status']=='succeeded':return p
        time.sleep(1)
    raise TimeoutError('Photo acceptance timeout')


def clone():
    originals={p['id']:store.read(p['id']) for p in store.listing() if not p.get('diagnostic')}
    source=next(p for p in originals.values() if p.get('matting') and p['options'].get('layout_mode')=='lesson')
    project=copy.deepcopy(source);pid=store.uid();folder=store.folder(pid);origin=store.folder(source['id'])
    shutil.copy2(origin/source['source_file'],folder/source['source_file'])
    for name in ['assets','frames']:
        if (origin/name).is_dir():shutil.copytree(origin/name,folder/name)
    if (origin/'transcript.json').is_file():shutil.copy2(origin/'transcript.json',folder/'transcript.json')
    code=source['matting']['code'];destination=folder/'matting'/code
    # Immutable complete cache only. Hardlinks avoid another large private-data copy.
    shutil.copytree(origin/'matting'/code,destination,copy_function=os.link)
    project.update(id=pid,title='Khung sạch · 10 ảnh mỗi bài',revision=1,status='ready',preview=None,export=None,created_at=store.now())
    project['options']['ratio']='9:16'
    for l in project['plan']['lessons']:
        l.update(asset_id=None,photo_candidates=[],photo_crops={},locked=False,photo_query='friends waving hello greeting')
    store.save(project)
    state={'project_id':pid,'originals':originals,'matting_code':code,'matting_stamp':(destination/'manifest.json').stat().st_mtime_ns}
    store.atomic_json(OUT/'state.json',state);return state


def save(p,plan=None,options=None):
    call('PUT',f"/projects/{p['id']}/plan",json={'revision':p['revision'],'plan':plan or p['plan'],'options':options or p['options']})
    return wait(p['id'])


def run():
    state=json.loads((OUT/'state.json').read_text(encoding='utf-8')) if '--resume' in sys.argv else clone()
    pid=state['project_id'];folder=store.folder(pid);p=call('GET',f'/projects/{pid}');lid=p['plan']['lessons'][0]['id']
    if not p['plan']['lessons'][0].get('photo_candidates'):
        call('POST',f'/projects/{pid}/lessons/{lid}/photo-candidates',json={'revision':p['revision']});p=wait(pid)
    first=p['plan']['lessons'][0];ids=first['photo_candidates']
    assert len(ids)==len(set(ids))==10
    if not state.get('initial_pool'):assert first['asset_id']==ids[0]
    for ident in ids:
        with Image.open(folder/'assets'/p['assets'][ident]['file']) as image:image.verify()
    initial=state.get('initial_pool') or list(ids)
    state['initial_pool']=initial;store.atomic_json(OUT/'state.json',state)
    if not state.get('refreshed'):
        selected=first['asset_id'];call('POST',f'/projects/{pid}/lessons/{lid}/photo-candidates',json={'revision':p['revision'],'refresh':True});p=wait(pid)
        refreshed=p['plan']['lessons'][0]
        assert len(refreshed['photo_candidates'])==10 and not set(refreshed['photo_candidates'])&set(initial)
        assert refreshed['asset_id']==selected
        state['refreshed']=True;state['refreshed_pool']=refreshed['photo_candidates'];store.atomic_json(OUT/'state.json',state)
    # Choose a cached image, separate per-ratio crops and source locks; no Pexels selection call.
    plan=copy.deepcopy(p['plan']);l=plan['lessons'][0]
    l.update(asset_id=l['photo_candidates'][0],locked=True,photo_crops={'9:16':{'x':.5,'y':.45,'zoom':1},'16:9':{'x':.5,'y':.4,'zoom':1.1}})
    p=save(p,plan)
    for ratio,label in [('9:16','9x16'),('16:9','16x9')]:
        if p['options']['ratio']!=ratio:p=save(p,options={**p['options'],'ratio':ratio})
        call('POST',f'/projects/{pid}/jobs/export');p=wait(pid)
        assert p['matting']['code']==state['matting_code']
        assert (folder/'matting'/state['matting_code']/'manifest.json').stat().st_mtime_ns==state['matting_stamp']
        target=OUT/f'Vietnamese_with_Vinh_khung_sach_{label}.mp4';shutil.copy2(folder/p['export']['file'],target)
        ffmpeg(['-i',target,'-f','null','-'])
        for t in [2,12,30,59]:ffmpeg(['-ss',t,'-i',target,'-frames:v',1,'-vf','scale=540:-2',OUT/f'{label}-{t}.jpg'])
        state[label]={'file':target.name,**probe(target)}
    backup=client.get(BASE+f'/projects/{pid}/download/project');backup.raise_for_status();(OUT/'VietCut_khung_sach_10_anh.zip').write_bytes(backup.content)
    with zipfile.ZipFile(io.BytesIO(backup.content)) as archive:
        assert archive.testzip() is None and not any(n.startswith('matting/') for n in archive.namelist())
        portable=json.loads(archive.read('project.json'))
        assert portable['plan']['lessons'][0]==p['plan']['lessons'][0]
        for ident in p['plan']['lessons'][0]['photo_candidates']:
            name='assets/'+p['assets'][ident]['file']
            assert hashlib.sha256(archive.read(name)).digest()==hashlib.sha256((folder/name).read_bytes()).digest()
    for oldid,old in state['originals'].items():assert store.read(oldid)==old,'Existing project changed: '+oldid
    a=Image.open(OUT/'9x16-12.jpg').convert('RGB');b=Image.open(OUT/'16x9-12.jpg').convert('RGB');b.thumbnail((900,700))
    sheet=Image.new('RGB',(a.width+b.width+50,max(a.height,b.height)+60),'#18211a');d=ImageDraw.Draw(sheet)
    d.text((15,12),'9:16 · nền kem, ảnh phủ kín',font=font(20,True),fill='#e9e9df');d.text((a.width+35,12),'16:9 · không blur',font=font(20,True),fill='#c7ed9a')
    sheet.paste(a,(15,50));sheet.paste(b,(a.width+35,50));sheet.save(OUT/'hai_khung_khong_blur.jpg',quality=94)
    state.update(full_decode=True,matting_reused=True,originals_unchanged=True,local_image_selection=True,ten_distinct_downloaded=True,refresh_preserves_selection=True)
    store.atomic_json(OUT/'acceptance.json',{k:v for k,v in state.items() if k!='originals'})
    print(json.dumps({k:v for k,v in state.items() if k!='originals'},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':run()
