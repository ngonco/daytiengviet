"""Opt-in live acceptance for lesson frames. Uses configured provider quota."""
import json
import shutil
import time
import zipfile
import io
from pathlib import Path
import httpx
from backend import store
from backend.config import ROOT,settings
from backend.media import probe,ffmpeg

BASE=f"http://127.0.0.1:{settings().get('APP_PORT') or 8876}/api"
client=httpx.Client(timeout=150)
OUT=ROOT/'OUTPUT/frame_v2';OUT.mkdir(parents=True,exist_ok=True)

def call(method,path,**kwargs):
    response=client.request(method,BASE+path,**kwargs)
    if not response.is_success:raise RuntimeError(f'{response.status_code}: '+response.text[:1200])
    return response.json()

def wait(project_id):
    previous=''
    for _ in range(1500):
        project=call('GET',f'/projects/{project_id}')
        current=next((j for j in project['jobs'] if j['status'] in ['queued','running','cancelling']),None)
        if not current:
            if project['jobs'][0]['status']!='succeeded':raise RuntimeError(project['jobs'][0].get('error') or project['jobs'][0]['status'])
            return project
        if previous!=current['message']:
            print(current['message'],flush=True);previous=current['message']
        time.sleep(1)
    raise RuntimeError('Timeout')

if __name__=='__main__':
    originals={p['id']:store.read(p['id']) for p in call('GET','/projects')}
    sample=call('GET','/samples')[0]['filename']
    created=call('POST','/projects/sample',json={'filename':sample,'title':'Khung bài học · Xin chào!','options':{'ratio':'9:16','language':'en'}})
    state={'project_id':created['id'],'original_ids':list(originals)}
    store.atomic_json(OUT/'state.json',state)
    project=wait(created['id'])
    assert project['options']['layout_mode']=='lesson'
    assert project['plan']['schema_version']==2 and project['plan']['lessons']
    print(json.dumps({'lessons':project['plan']['lessons']},ensure_ascii=False),flush=True)
    for ratio,name in [('9:16','Vietnamese_with_Vinh_9x16'),('16:9','Vietnamese_with_Vinh_16x9')]:
        if project['options']['ratio']!=ratio:
            project=call('PUT',f"/projects/{project['id']}/plan",json={'revision':project['revision'],'plan':project['plan'],'options':{**project['options'],'ratio':ratio,'style':'education'}})
            project=wait(project['id'])
        call('POST',f"/projects/{project['id']}/jobs/export")
        project=wait(project['id'])
        result=project['export'];source=store.folder(project['id'])/result['file'];target=OUT/(name+'.mp4')
        shutil.copy2(source,target)
        metadata=probe(target)
        assert abs(metadata['duration']-result['duration'])<.1
        assert metadata['audio_channels']==2
        ffmpeg(['-i',target,'-f','null','-'])
        for lang in ['vi','en']:shutil.copy2(source.parent/f'subtitles.{lang}.srt',OUT/f'{name}.{lang}.srt')
        for i,at in enumerate([1.5,15.5,30,52]):ffmpeg(['-ss',at,'-i',target,'-frames:v','1','-vf','scale=540:-2',OUT/f'{name}_{i}.jpg'])
        state[name]={'file':target.name,**metadata}
        store.atomic_json(OUT/'state.json',state)
    backup=client.get(BASE+f"/projects/{project['id']}/download/project");backup.raise_for_status()
    (OUT/'Vietnamese_with_Vinh_project.zip').write_bytes(backup.content)
    clone=call('POST','/projects/import',files={'file':('frame.zip',backup.content,'application/zip')})
    restored=wait(clone['id'])
    assert restored['plan']['lessons']==project['plan']['lessons']
    assert restored['options']['layout_mode']=='lesson'
    store.update(clone['id'],diagnostic=True,title='Kiểm thử ZIP khung bài học')
    old_zip=ROOT/'OUTPUT/Bai_01_Xin_chao_Du_an.zip'
    legacy=call('POST','/projects/import',files={'file':('legacy.zip',old_zip.read_bytes(),'application/zip')})
    legacy=wait(legacy['id']);assert legacy['options']['layout_mode']=='legacy'
    previous_revision=legacy['revision'];before=legacy['plan']
    call('POST',f"/projects/{legacy['id']}/reframe")
    converted=wait(legacy['id'])
    assert converted['plan']['captions']==before['captions'] and converted['plan']['cuts']==before['cuts']
    saved=json.loads((store.folder(legacy['id'])/'versions'/f'v{previous_revision:05}.json').read_text(encoding='utf-8'))
    assert saved['options'].get('layout_mode','legacy')=='legacy'
    assert converted['options']['layout_mode']=='lesson'
    store.update(legacy['id'],diagnostic=True,title='Kiểm thử chuyển khung và khôi phục')
    for project_id,original in originals.items():assert store.read(project_id)==original,'An existing project was modified'
    state.update(passed=True,zip_roundtrip=True,conversion_preserved_edits=True,originals_unchanged=True)
    store.atomic_json(OUT/'acceptance.json',state)
    print('ALL LESSON ACCEPTANCE CHECKS PASSED',flush=True)
