"""Orchestrate the isolated RVM process without importing CUDA into the app."""
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from .config import ROOT, data_root, binary
from .store import atomic_json
from .media import ffmpeg
from .matting_schema import validate_duration

MATTING_VERSION = 2
MODEL_RELEASE = 'v1.0.0'
# Pinned official release bytes; filled and independently checked by setup.
MODELS = {
    'cuda': {'file': 'rvm_mobilenetv3_fp16.torchscript', 'sha256': '847a8b5139498afbf7abde9cc347b41030540f6498db593a0e3d9dde1eccdd96'},
    'cpu': {'file': 'rvm_mobilenetv3_fp32.torchscript', 'sha256': 'f01e0c9338b9a6a31b881ea6d4360d70c1e549701b3792e14c9ed88d6196c5a1'},
}


def runtime_root(): return data_root() / 'runtime'
def python_path(): return runtime_root() / 'matting' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
def model_path(device): return runtime_root() / 'models' / MODELS[device]['file']


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): digest.update(block)
    return digest.hexdigest()


def verified_model(device):
    path = model_path(device)
    return path.is_file() and file_hash(path) == MODELS[device]['sha256']


def runtime_status():
    result = {'installed': python_path().is_file(), 'cuda': False, 'gpu': None, 'models': {d: verified_model(d) for d in MODELS}}
    if result['installed']:
        try:
            probe = subprocess.run([str(python_path()), str(ROOT/'scripts/matting_runner.py'), '--status'], capture_output=True, timeout=45, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if probe.returncode == 0: result.update(json.loads(probe.stdout))
            else: result['message'] = 'Bộ GPU chưa chạy được. Hãy chạy CAI_DAT_XOA_PHONG.cmd.'
        except (OSError, subprocess.TimeoutExpired, ValueError): result['message'] = 'Chưa kiểm tra được bộ GPU; thử lại hoặc cài lại bộ xóa phông.'
    else: result['message'] = 'Chưa cài bộ xóa phông. Chạy CAI_DAT_XOA_PHONG.cmd trong thư mục app.'
    return result


def cache_identity(project, folder):
    cfg = validate_duration(project['options'], project['metadata']['duration'])
    # Full source bytes, not mtime/name; changing lesson/cut/aspect never invalidates matting.
    source = folder/project['source_file']
    w,h = project['metadata']['width'], project['metadata']['height']
    scale = min(1,1920/max(w,h)); w,h = max(2,round(w*scale)//2*2),max(2,round(h*scale)//2*2)
    identity = {'v':MATTING_VERSION,'source':file_hash(source),'model':MODELS[cfg.device], 'config':cfg.model_dump(), 'size':[w,h], 'fps':30, 'network_max':512}
    code = hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:24]
    return code,identity


def _run_layers(project,context,folder,identity,cfg):
    status = runtime_status()
    if not status['installed'] or not status['models'][cfg.device]:
        raise ValueError('Bộ xóa phông/mô hình chưa sẵn sàng. Chạy CAI_DAT_XOA_PHONG.cmd hoặc tắt Xóa phông rồi lưu lại.')
    if cfg.device == 'cuda' and not status['cuda']:
        raise ValueError('GPU chưa sẵn sàng. Chọn rõ Chạy CPU (chậm hơn) hoặc tắt Xóa phông; app không tự chuyển sang CPU.')
    request = {**identity,'paper':json.loads((ROOT/'assets/frame_brand.json').read_text(encoding='utf-8'))['paper'],'source':str((context.folder/project['source_file']).resolve()),'model':str(model_path(cfg.device).resolve()), 'model_sha256':MODELS[cfg.device]['sha256'], 'folder':str(folder.resolve()),'duration':project['metadata']['duration'],'ffmpeg':binary('ffmpeg')}
    atomic_json(folder/'request.json', request)
    progress_file = folder/'progress.json'
    # Allocate an explicit progress range even when AI planning has already advanced the job.
    from . import store
    prior=store.job_read(context.job_id)['progress'] if hasattr(context,'job_id') else 0
    ceiling=88 if prior>50 else 56
    context.progress(prior,'Nạp mô hình xóa phông trên GPU' if cfg.device=='cuda' else 'Nạp mô hình xóa phông trên CPU đã chọn')
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([str(python_path()),str(ROOT/'scripts/matting_runner.py'),str(folder/'request.json')],stdout=errors,stderr=errors,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            while process.poll() is None:
                context.check()
                try:
                    progress=json.loads(progress_file.read_text(encoding='utf-8'))
                    context.progress(prior+(ceiling-prior)*progress['frame']/max(1,progress['total']),f"Xóa phông · {progress['frame']}/{progress['total']} hình · {progress.get('fps',0):.1f} hình/giây")
                except (OSError,ValueError,KeyError): pass
                time.sleep(.3)
        except BaseException:
            # The runner checks this file between batches and terminates its FFmpeg children.
            (folder/'cancel').touch()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                if sys.platform=='win32':
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                else:process.kill()
                process.wait()
            raise
        if process.returncode:
            errors.seek(0,2);size=errors.tell();errors.seek(max(0,size-1800))
            raise RuntimeError('Xóa phông chưa hoàn tất: '+errors.read().decode('utf-8','replace')[-1500:])
    stats=json.loads((folder/'stats.json').read_text(encoding='utf-8'))
    return stats


def _complete_layers(folder,duration):
    total=math.ceil(duration*30)
    for index in range(math.ceil(total/600)):
        part=folder/f'{index:05}'
        if not all((part/n).is_file() for n in ['complete.json','foreground.mp4','alpha.mkv']):return False
        try:
            if json.loads((part/'complete.json').read_text())['frames']!=min(600,total-index*600):return False
        except (OSError,ValueError,KeyError):return False
    return True


def ensure_matting(project,context):
    cfg=validate_duration(project['options'],project['metadata']['duration'])
    if not cfg.enabled:return None
    layer_key,identity=cache_identity(project,context.folder)
    paper=json.loads((ROOT/'assets/frame_brand.json').read_text(encoding='utf-8'))['paper']
    code=hashlib.sha256(json.dumps({'layers':layer_key,'paper':paper,'composition':1},sort_keys=True).encode()).hexdigest()[:24]
    root=context.folder/'matting';folder=root/code;folder.mkdir(parents=True,exist_ok=True)
    manifest=folder/'manifest.json'
    if manifest.is_file() and (folder/'composition.mp4').is_file():return json.loads(manifest.read_text(encoding='utf-8'))
    duration=project['metadata']['duration'];layers=root/layer_key;stats=None;reused=False
    # Adopt completed v2 layer pairs without rewriting or rerunning their model.
    for path in sorted(root.glob('*/manifest.json')):
        context.check()
        try:
            saved=json.loads(path.read_text(encoding='utf-8'))
            old={k:v for k,v in saved['identity'].items() if k!='paper'}
            candidate=root/saved.get('layer_code',saved['code'])
            if candidate.parent.resolve()!=root.resolve():continue
            if old==identity and _complete_layers(candidate,duration):
                layers=candidate;stats=saved['stats'];reused=True;break
        except (OSError,ValueError,KeyError):continue
    if stats is None:
        layers.mkdir(parents=True,exist_ok=True)
        if _complete_layers(layers,duration) and (layers/'stats.json').is_file():
            stats=json.loads((layers/'stats.json').read_text(encoding='utf-8'));reused=True
        else:stats=_run_layers(project,context,layers,identity,cfg)
    started=time.perf_counter();total=math.ceil(duration*30);count=math.ceil(total/600);chunks=[]
    w,h=identity['size']
    for index in range(count):
        context.check();context.progress(55+20*index/count,f'Ghép nền pastel từ mặt nạ đã lưu · {index+1}/{count}')
        part=layers/f'{index:05}';frames=min(600,total-index*600)
        target=folder/f'part-{index:05}.mp4';chunks.append(target)
        if target.is_file() and target.with_suffix('.json').is_file():continue
        filters='[0:v]setpts=N/(30*TB),format=rgb24[f];[1:v]setpts=N/(30*TB),format=gray[a];[f][a]alphamerge[person];[2:v][person]overlay=shortest=1:format=auto,format=yuv420p[out]'
        ffmpeg(['-filter_complex_threads','1','-i',part/'foreground.mp4','-i',part/'alpha.mkv','-f','lavfi','-i',f'color=c={paper}:s={w}x{h}:r=30','-filter_complex',filters,'-map','[out]','-frames:v',frames,'-an','-c:v','libx264','-preset','veryfast','-crf','18',target],context)
        atomic_json(target.with_suffix('.json'),{'frames':frames})
    concat=folder/'concat.txt'
    concat.write_text('\n'.join("file '"+str(p.resolve()).replace('\\','/').replace("'","'\\''")+"'" for p in chunks),encoding='utf-8')
    ffmpeg(['-f','concat','-safe','0','-i',concat,'-i',context.folder/project['source_file'],'-map','0:v:0','-map','1:a:0','-c','copy','-t',duration,'-movflags','+faststart',folder/'composition.tmp.mp4'],context)
    (folder/'composition.tmp.mp4').replace(folder/'composition.mp4')
    result={'code':code,'layer_code':layers.name,'file':(folder/'composition.mp4').relative_to(context.folder).as_posix(),'identity':{**identity,'paper':paper},'stats':stats,'warnings':stats.get('warnings',[]),'paper':paper,'reused_layers':reused,'composition_seconds':time.perf_counter()-started}
    atomic_json(manifest,result);return result
