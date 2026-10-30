"""Prepare a fresh demo using the real Groq English response already obtained."""
import json
import shutil
from pathlib import Path
from backend import store
from backend.app import create, Options
from backend.config import ROOT

store.init()
old='89eb517a77d34f8b'
store.update(old,diagnostic=True,title='Chẩn đoán nhận diện ban đầu')
source=next(ROOT.glob('*.mp4'))
project=create(source,'Bài 01 · Xin chào!',Options(ratio='9:16',language='en'))
folder=store.folder(project['id'])/'audio'
folder.mkdir(exist_ok=True)
shutil.copy2(ROOT/'data/diagnostics/english-stt.json',folder/'000.json')
print(json.dumps({'id':project['id'],'job_id':project['jobs'][0]['id']}))
