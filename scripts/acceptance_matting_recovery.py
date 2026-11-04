"""Opt-in GPU cancellation/resume and EOF regression on an isolated source copy."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time

from backend.config import ROOT
from backend.media import Cancelled,probe,ffmpeg
from backend.matting import ensure_matting,file_hash
from backend.matting_schema import BackgroundRemoval


def run(source):
    folder=ROOT/'OUTPUT'/'matting-recovery'/str(time.time_ns());folder.mkdir(parents=True)
    before=file_hash(source);shutil.copy2(source,folder/'source.mp4')
    p={'source_file':'source.mp4','metadata':probe(folder/'source.mp4'),'options':{'background_removal':BackgroundRemoval(enabled=True,device='cuda').model_dump()}}
    class Context:
        kind='preview'
        def __init__(self):self.folder=folder;self.cancel=True
        def check(self):
            if self.cancel and list((folder/'matting').glob('*/00000/complete.json')):raise Cancelled('Disposable acceptance cancellation')
        def progress(self,*args):pass
    context=Context();cancelled=False
    try:ensure_matting(p,context)
    except Cancelled:cancelled=True
    assert cancelled,'Expected a real cancellation after the first durable segment'
    part=next((folder/'matting').glob('*/00000/complete.json')).parent
    saved={name:file_hash(part/name) for name in ['foreground.mp4','alpha.mkv','state.npz','tracking.json','complete.json']}
    context.cancel=False;result=ensure_matting(p,context)
    assert result['stats']['resumed_frames']>=600
    assert saved=={name:file_hash(part/name) for name in saved}
    ffmpeg(['-xerror','-err_detect','explode','-i',folder/result['file'],'-f','null','-'])
    assert before==file_hash(source)==file_hash(folder/'source.mp4')
    output=probe(folder/result['file'])
    assert abs(output['duration']-p['metadata']['duration'])<.15
    report={'source_preserved':True,'cancel_resume':True,'checkpoint_unchanged':True,'full_decode':True,'source_seconds':p['metadata']['duration'],'output_seconds':output['duration'],'stats':result['stats']}
    (folder/'acceptance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(folder/'acceptance.json'),**{k:v for k,v in report.items() if k!='stats'}},ensure_ascii=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    run(parser.parse_args().source.resolve())
