"""Real local acceptance run. Does not print keys or issue extra STT calls."""
from pathlib import Path
import io
import json
import shutil
import time
import zipfile
import httpx
from backend.config import ROOT,settings
from backend.media import probe,ffmpeg
from backend.render import RENDER_VERSION

base='http://127.0.0.1:'+str(settings().get('APP_PORT') or 8876)+'/api'
client=httpx.Client(timeout=120)
out=ROOT/'OUTPUT'
out.mkdir(exist_ok=True)
results={}

def call(method,path,**kwargs):
    r=client.request(method,base+path,**kwargs)
    if not r.is_success:
        raise RuntimeError(f'{method} {path}: {r.status_code} '+r.text[:400])
    return r.json()

def wait(project_id):
    deadline=time.monotonic()+1500
    previous=''
    while time.monotonic()<deadline:
        p=call('GET',f'/projects/{project_id}')
        jobs=p['jobs']
        active=next((j for j in jobs if j['status'] in ['queued','running','cancelling']),None)
        if not active:
            if jobs and jobs[0]['status']=='failed':
                raise RuntimeError(jobs[0]['error'])
            return p
        label=active['message']
        if label!=previous:
            print(label,flush=True);previous=label
        time.sleep(2)
    raise RuntimeError('Timed out waiting for video render')

def export_copy(project_id,name):
    p=wait(project_id)
    if not p.get('export') or p['export']['revision']!=p['revision'] or p['export'].get('renderer_version')!=RENDER_VERSION:
        call('POST',f'/projects/{project_id}/jobs/export')
        p=wait(project_id)
    source=ROOT/'data/projects'/project_id/p['export']['file']
    target=out/(name+'.mp4')
    shutil.copy2(source,target)
    metadata=probe(target)
    assert abs(metadata['duration']-p['export']['duration'])<.15
    assert metadata['width']==p['export']['width'] and metadata['height']==p['export']['height']
    folder=source.parent
    for language in ['vi','en']:
        shutil.copy2(folder/f'subtitles.{language}.srt',out/f'{name}.{language}.srt')
    shutil.copy2(folder/'credits.json',out/f'{name}.credits.json')
    results[name]={'project_id':project_id,'file':target.name,'duration':metadata['duration'],'width':metadata['width'],'height':metadata['height'],'revision':p['revision'],'audio_channels':metadata['audio_channels']}
    return p

primary_id='05beded14c204c1f'
primary=export_copy(primary_id,'Bai_01_Xin_chao_9x16')
url=base+f"/projects/{primary_id}/media/"+primary['export']['file']
stream=client.get(url,headers={'Range':'bytes=0-1023'})
assert stream.status_code==206 and len(stream.content)==1024
results['range_streaming']=True

backup=client.get(base+f'/projects/{primary_id}/download/project')
backup.raise_for_status()
backup_path=out/'Bai_01_Xin_chao_Du_an.zip'
backup_path.write_bytes(backup.content)
with zipfile.ZipFile(io.BytesIO(backup.content)) as archive:
    assert '.env' not in archive.namelist()
    document=json.loads(archive.read('project.json'))
    assert document['plan']['captions'][0]['locked']
    memory=io.BytesIO()
    with zipfile.ZipFile(memory,'w',zipfile.ZIP_DEFLATED) as modified:
        for name in archive.namelist():
            payload=archive.read(name)
            if name=='project.json':
                document['title']='Bài 01 · Xin chào! · Bản ngang'
                document['options'].update(ratio='16:9',style='education')
                document['export']=None
                payload=json.dumps(document,ensure_ascii=False).encode()
            modified.writestr(name,payload)
    imported=call('POST','/projects/import',files={'file':('horizontal.zip',memory.getvalue(),'application/zip')})
secondary=wait(imported['id'])
assert secondary['options']['ratio']=='16:9'
assert secondary['plan']['captions'][0]['locked']
assert secondary['plan']['captions'][0]['vi']==primary['plan']['captions'][0]['vi']
results['project_roundtrip']=True
secondary=export_copy(secondary['id'],'Bai_01_Xin_chao_16x9')

# Extract frames for visual inspection, using local render artifacts only.
for name in ['Bai_01_Xin_chao_9x16','Bai_01_Xin_chao_16x9']:
    frames=[]
    for i,at in enumerate([1.5,8.5,15.5,30,53]):
        path=out/f'{name}_frame{i}.jpg'
        ffmpeg(['-ss',at,'-i',out/(name+'.mp4'),'-frames:v','1','-vf','scale=360:-2',path])
        frames.append(path)
    from PIL import Image,ImageDraw
    images=[Image.open(p).convert('RGB') for p in frames]
    height=max(im.height for im in images)
    sheet=Image.new('RGB',(sum(im.width for im in images),height),'#101614')
    x=0
    for image in images:
        sheet.paste(image,(x,0));x+=image.width
    sheet.save(out/f'{name}_contact.jpg',quality=94)
    for image in images:image.close()

(out/'acceptance.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False),flush=True)
