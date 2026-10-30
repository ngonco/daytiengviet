import json
from backend import store
from backend.timeline import cue_words

project_id='05beded14c204c1f'
project=store.read(project_id)
worker_active=[j for j in store.jobs(project_id) if j['status'] in ['queued','running','cancelling']]
if worker_active:
    raise SystemExit('Wait until current job is complete before refreshing.')
folder=store.folder(project_id)
transcript=json.loads((folder/'transcript.json').read_text(encoding='utf-8'))
for i in range(len(transcript['words'])-1):
    a,b=transcript['words'][i],transcript['words'][i+1]
    if a['end']>b['start']>a['start']:
        a['end']=b['start']
transcript['captions']=cue_words(transcript['words'])
store.atomic_json(folder/'transcript.json',transcript)
from backend.worker import version
version(project)
store.update(project_id,plan=None,transcript=transcript,preview=None,revision=project['revision']+1)
store.job_create(project_id,'pipeline')
print('Refreshed demo cues:',len(transcript['captions']))
