"""Opt-in same-machine cold/warm matting benchmark, using disposable file copies.

No providers or live project writes. Pass the saved pre-change runner explicitly.
Private videos, requests and comparison frames stay under ignored OUTPUT/.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time
from unittest.mock import patch

from backend import matting
from backend.config import ROOT
from backend.media import probe,ffmpeg
from backend.matting_schema import BackgroundRemoval


def run(source,baseline):
    out=ROOT/'OUTPUT'/'matting-speed'/str(time.time_ns());out.mkdir(parents=True)
    meta=probe(source);reports={};results={}
    original_popen=subprocess.Popen
    original_read=Path.read_text
    def read(path,*a,**kw):
        if path.name=='progress.json':raise OSError('Benchmark does not poll advisory progress files.')
        return original_read(path,*a,**kw)
    class Context:
        kind='preview'
        def __init__(self,folder):self.folder=folder
        def check(self):pass
        def progress(self,*args):pass
    for label in ['before','after']:
        folder=out/label;folder.mkdir();shutil.copy2(source,folder/'source.mp4')
        project={'source_file':'source.mp4','metadata':meta,'options':{'background_removal':BackgroundRemoval(enabled=True,device='cuda').model_dump()}}
        def launch(args,*a,**kw):
            if label=='before' and isinstance(args,(list,tuple)):
                args=[str(baseline) if str(v)==str(ROOT/'scripts/matting_runner.py') else v for v in args]
            return original_popen(args,*a,**kw)
        started=time.perf_counter()
        with patch('subprocess.Popen',launch),patch('pathlib.Path.read_text',read),patch('backend.matting.MATTING_VERSION',2 if label=='before' else 3):
            result=matting.ensure_matting(project,Context(folder))
            cold=time.perf_counter()-started
            started=time.perf_counter();matting.ensure_matting(project,Context(folder));warm=time.perf_counter()-started
        reports[label]={'cold_seconds':cold,'warm_seconds':warm,'composition_seconds':result['composition_seconds'],'stats':result['stats']}
        results[label]=(folder,result)
        ffmpeg(['-xerror','-i',folder/result['file'],'-f','null','-'])
        print(label,round(cold,3),'seconds',flush=True)
    import numpy as np
    from PIL import Image
    comparisons=[]
    from backend.config import binary
    for at in [.2,5,min(meta['duration']-.1,19.9)]:
        frames=[]
        for label in ['before','after']:
            folder,result=results[label];segment=int(at//20);local=round(at*30)%600
            part=folder/'matting'/result['layer_code']/f'{segment:05}'
            for bg in ['black','white','#F7F3EB']:
                trim=f'trim=start_frame={local}:end_frame={local+1},setpts=PTS-STARTPTS'
                path=out/f'{label}-{at:.2f}-{bg.replace("#","")}.png'
                ffmpeg(['-i',part/'foreground.mp4','-i',part/'alpha.mkv','-f','lavfi','-i',f'color=c={bg}:s={meta["width"]}x{meta["height"]}:r=30','-filter_complex',f'[0:v]{trim}[f];[1:v]{trim}[a];[f][a]alphamerge[p];[2:v][p]overlay=shortest=1[o]','-map','[o]','-frames:v','1',path])
            alpha=subprocess.run([binary('ffmpeg'),'-v','error','-i',str(part/'alpha.mkv'),'-vf',f'trim=start_frame={local}:end_frame={local+1}','-frames:v','1','-f','rawvideo','-pix_fmt','gray','-'],capture_output=True,check=True).stdout
            frames.append(np.frombuffer(alpha,np.uint8).astype(float))
        comparisons.append({'time':at,'alpha_mean_absolute_difference':float(np.abs(frames[0]-frames[1]).mean()),'alpha_max_difference':float(np.abs(frames[0]-frames[1]).max())})
    reports['quality']=comparisons
    reports['improvement_percent']=(1-reports['after']['cold_seconds']/reports['before']['cold_seconds'])*100
    reports['source_seconds']=meta['duration']
    (out/'report.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
    # A compact contact sheet for actual visual review on three backgrounds.
    images=[]
    for path in sorted(out.glob('*.png')):
        im=Image.open(path).convert('RGB');im.thumbnail((240,420));images.append(im.copy())
    sheet=Image.new('RGB',(240*6,440*3),'#ddd')
    for i,im in enumerate(images):sheet.paste(im,(i%6*240,i//6*440))
    sheet.save(out/'comparison.jpg')
    print(json.dumps({'report':str(out/'report.json'),'improvement_percent':reports['improvement_percent'],'quality':comparisons}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--baseline',type=Path,required=True)
    args=parser.parse_args();run(args.source.resolve(),args.baseline.resolve())
