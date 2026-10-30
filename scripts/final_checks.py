import hashlib
import io
import json
import time
import zipfile
from pathlib import Path
import httpx
from backend import store
from backend.config import ROOT,settings
from backend.media import ffmpeg

base=f"http://127.0.0.1:{settings().get('APP_PORT') or 8876}/api"
client=httpx.Client(timeout=120)
out=ROOT/'OUTPUT'
results=json.loads((out/'acceptance.json').read_text(encoding='utf-8'))

def call(method,path,**kwargs):
    response=client.request(method,base+path,**kwargs)
    response.raise_for_status()
    return response.json()

def wait(project_id):
    for _ in range(300):
        project=call('GET',f'/projects/{project_id}')
        if not any(j['status'] in ['queued','running','cancelling'] for j in project['jobs']):
            assert project['jobs'][0]['status']=='succeeded',project['jobs'][0].get('error')
            return project
        time.sleep(1)
    raise RuntimeError('Timed out')

primary_id=results['Bai_01_Xin_chao_9x16']['project_id']
secondary_id=results['Bai_01_Xin_chao_16x9']['project_id']
for project_id in [primary_id,secondary_id]:
    call('POST',f'/projects/{project_id}/jobs/preview')
for project_id in [primary_id,secondary_id]:
    project=wait(project_id)
    assert len(project['frames'])>0
    for frame in project['frames']:
        response=client.get(base+f"/projects/{project_id}/media/frames/"+frame['file'])
        assert response.status_code==200
    assert project['preview']['renderer_version']==7
    assert project['export']['renderer_version']==7
print('Preview, exports and timeline thumbnails verified',flush=True)

backup=client.get(base+f'/projects/{primary_id}/download/project')
backup.raise_for_status()
(out/'Bai_01_Xin_chao_Du_an.zip').write_bytes(backup.content)
with zipfile.ZipFile(io.BytesIO(backup.content)) as archive:
    assert archive.testzip() is None
    assert '.env' not in archive.namelist()
    assert 'transcript.json' in archive.namelist()
    assert 'frames/manifest.json' in archive.namelist()
imported=call('POST','/projects/import',files={'file':('roundtrip.zip',backup.content,'application/zip')})
restored=wait(imported['id'])
assert restored['plan']['captions'][0]['locked']
assert restored['transcript']['captions']
assert restored['frames']
source=store.folder(primary_id)/store.read(primary_id)['source_file']
other=store.folder(restored['id'])/restored['source_file']
assert hashlib.file_digest(source.open('rb'),'sha256').hexdigest()==hashlib.file_digest(other.open('rb'),'sha256').hexdigest()
store.update(restored['id'],diagnostic=True,title='Kiểm thử mở lại dự án cuối cùng')
print('Project ZIP restores source, captions, lock, images and thumbnails',flush=True)

for name in ['Bai_01_Xin_chao_9x16','Bai_01_Xin_chao_16x9']:
    ffmpeg(['-i',out/(name+'.mp4'),'-f','null','-'])
    print('Full video/audio decode passed:',name,flush=True)

assert all(p['status']!='working' for p in call('GET','/projects'))
results.update(thumbnails=True,backup_integrity=True,full_decode=True,stereo_audio=True,renderer_version=7)
(out/'final-verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('ALL FINAL CHECKS PASSED',flush=True)
