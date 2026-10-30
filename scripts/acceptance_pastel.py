"""Opt-in local acceptance: no provider calls and no retention deletion on real projects."""
import base64
import copy
import io
import json
import os
from pathlib import Path
import shutil
import statistics
import sys
import time
import httpx
from PIL import Image,ImageChops,ImageStat,ImageDraw
from backend import store
from backend.config import ROOT,settings
from backend.media import ffmpeg,probe
from backend.templates import rounded_mask,font,brand
from backend.timeline import source_to_output,keep_spans

OUT=ROOT/'OUTPUT/pastel';OUT.mkdir(parents=True,exist_ok=True)
BASE=f"http://127.0.0.1:{settings().get('APP_PORT') or 8876}/api"
client=httpx.Client(timeout=150)


def call(method,path,**kwargs):
    r=client.request(method,BASE+path,**kwargs);r.raise_for_status();return r.json()


def wait(pid):
    previous=''
    for _ in range(2000):
        p=call('GET',f'/projects/{pid}');j=p['jobs'][0]
        if j['message']!=previous:print(j['message'],flush=True);previous=j['message']
        if j['status']=='succeeded':return p
        if j['status'] in ['failed','cancelled']:raise RuntimeError(j.get('error') or j['status'])
        time.sleep(.5)
    raise TimeoutError('Pastel acceptance timed out')


def create():
    originals={p['id']:copy.deepcopy(p) for p in store.listing() if not p.get('diagnostic')}
    p=copy.deepcopy(store.read('88308cdfcbfe4f5d'));origin=store.folder(p['id']);pid=store.uid();folder=store.folder(pid)
    shutil.copy2(origin/p['source_file'],folder/p['source_file'])
    for name in ['assets','frames']:
        if (origin/name).is_dir():shutil.copytree(origin/name,folder/name)
    if (origin/'transcript.json').is_file():shutil.copy2(origin/'transcript.json',folder/'transcript.json')
    code=p['matting'].get('layer_code',p['matting']['code']);shutil.copytree(origin/'matting'/code,folder/'matting'/code,copy_function=os.link)
    p.update(id=pid,title='Pastel · Xem trực tiếp',revision=1,created_at=store.now(),preview=None,export=None,status='ready')
    p['options']['ratio']='9:16';store.save(p)
    state={'project_id':pid,'originals':originals,'layer_code':code,'alpha_stamp':(folder/'matting'/code/'00000/alpha.mkv').stat().st_mtime_ns}
    store.atomic_json(OUT/'state.json',state);return state


def compose_scene(p,scene,at,target):
    folder=store.folder(p['id']);raw=OUT/'source-frame.png'
    ffmpeg(['-ss',at,'-i',folder/scene['source']['file'],'-frames:v',1,raw])
    base=Image.open(io.BytesIO(base64.b64decode(scene['page'].split(',')[1]))).convert('RGBA')
    tr=scene['speaker_transform'];sx,sy,sw,sh=scene['geometry']['speaker']
    tile=Image.new('RGBA',(sw,sh),brand()['paper']);im=Image.open(raw).convert('RGBA').resize((tr['width'],tr['height']),Image.Resampling.BICUBIC)
    tile.alpha_composite(im,(round(tr['left']),round(tr['top'])))
    base.paste(tile,(sx,sy),rounded_mask((sw,sh),scene['geometry']['radius']))
    if scene['subtitle']:
        sub=Image.open(io.BytesIO(base64.b64decode(scene['subtitle'].split(',')[1]))).convert('RGBA');x,y,_,_=scene['subtitle_rect'];base.alpha_composite(sub,(x,y))
    base.convert('RGB').save(target)


def run():
    state=json.loads((OUT/'state.json').read_text(encoding='utf-8')) if '--resume' in sys.argv else create();pid=state['project_id'];folder=store.folder(pid)
    p=call('GET',f'/projects/{pid}')
    if not p.get('matting',{}).get('reused_layers') or p['matting'].get('paper')!=brand()['paper']:
        call('POST',f'/projects/{pid}/jobs/prepare_speaker');p=wait(pid)
    assert p['matting']['reused_layers'] and p['matting']['layer_code']==state['layer_code']
    assert (folder/'matting'/state['layer_code']/'00000/alpha.mkv').stat().st_mtime_ns==state['alpha_stamp']
    timings=[]
    for ratio,label in [('9:16','9x16'),('16:9','16x9')]:
        options={**p['options'],'ratio':ratio}
        saved=call('PUT',f'/projects/{pid}/plan',json={'revision':p['revision'],'plan':p['plan'],'options':options,'render_preview':False})
        assert len(saved['jobs'])==len(p['jobs']);p=saved
        source_at=1.5;lesson=next(l for l in p['plan']['lessons'] if l['start']<=source_at<l['end']);caption=next((c for c in p['plan']['captions'] if c['start']<=source_at<c['end']),None)
        packet={'sequence':1,'lesson':lesson,'caption':caption,'options':options}
        scene=call('POST',f'/projects/{pid}/preview-scene',json=packet)
        for i in range(10):
            started=time.perf_counter();scene=call('POST',f'/projects/{pid}/preview-scene',json={**packet,'sequence':i+2});timings.append((time.perf_counter()-started)*1000)
        # Draft changes are rendered without writing a revision or generating a job.
        revision=p['revision'];draft=call('POST',f'/projects/{pid}/preview-scene',json={**packet,'lesson':{**lesson,'vi':'Cảm ơn!','en':'Thank you!'},'sequence':99})
        assert draft['page']!=scene['page'];assert call('GET',f'/projects/{pid}')['revision']==revision
        compose_scene(p,scene,source_at,OUT/f'live-{label}.png')
        call('POST',f'/projects/{pid}/jobs/export');p=wait(pid)
        target=OUT/f'Vietnamese_with_Vinh_pastel_{label}.mp4';shutil.copy2(folder/p['export']['file'],target);ffmpeg(['-i',target,'-f','null','-'])
        output_at=source_to_output(source_at,keep_spans(p['metadata']['duration'],p['plan']['cuts']))
        ffmpeg(['-ss',output_at,'-i',target,'-frames:v',1,'-vf',f"scale={scene['width']}:{scene['height']}",OUT/f'export-{label}.png'])
        with Image.open(OUT/f'live-{label}.png') as a,Image.open(OUT/f'export-{label}.png') as b:
            errors={}
            for region in ['photo','content','speaker']:
                x,y,w,h=scene['geometry'][region];inset=8
                diff=ImageChops.difference(a.convert('RGB').crop((x+inset,y+inset,x+w-inset,y+h-inset)),b.convert('RGB').crop((x+inset,y+inset,x+w-inset,y+h-inset)))
                errors[region]=sum(ImageStat.Stat(diff).mean)/3
            assert max(errors.values())<14,errors
        state[label]={'file':target.name,**probe(target),'preview_vs_export_mean_error':errors}
    assert (folder/'matting'/state['layer_code']/'00000/alpha.mkv').stat().st_mtime_ns==state['alpha_stamp']
    for oldid,old in state['originals'].items():
        current=store.read(oldid)
        for key in ['plan','options','revision','source_file','assets','created_at']:assert current.get(key)==old.get(key),('Original changed',oldid,key)
    a=Image.open(OUT/'export-9x16.png').convert('RGB');b=Image.open(OUT/'export-16x9.png').convert('RGB')
    sheet=Image.new('RGB',(a.width+b.width+50,max(a.height,b.height)+70),'#F7F3EB');d=ImageDraw.Draw(sheet)
    d.text((15,14),'9:16 · ảnh trên, người nói dưới',font=font(20,True),fill='#163247');d.text((a.width+35,14),'16:9 · pastel',font=font(20,True),fill='#163247');sheet.paste(a,(15,55));sheet.paste(b,(a.width+35,55));sheet.save(OUT/'pastel_hai_khung.jpg',quality=94)
    state.update(reused_layers_without_model=True,originals_preserved=True,full_decode=True,api_preview_ms={'median':statistics.median(timings),'max':max(timings),'samples':timings},browser_ui_test='unavailable: local browser use disabled in Work settings')
    store.atomic_json(OUT/'acceptance.json',{k:v for k,v in state.items() if k!='originals'})
    print(json.dumps({k:v for k,v in state.items() if k!='originals'},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':run()
