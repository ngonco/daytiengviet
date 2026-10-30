"""Install the pinned, isolated runtime and verify official model release bytes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import venv

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.matting import MODELS, runtime_root, python_path


def main():
    started=time.perf_counter();runtime=runtime_root();runtime.mkdir(parents=True,exist_ok=True)
    if not python_path().exists():venv.create(runtime/'matting',with_pip=True)
    subprocess.run([str(python_path()),'-m','pip','install','torch==2.8.0','--index-url','https://download.pytorch.org/whl/cu128'],check=True)
    subprocess.run([str(python_path()),'-m','pip','install','numpy==2.2.6','opencv-python-headless==4.12.0.88'],check=True)
    models=runtime/'models';models.mkdir(exist_ok=True)
    for item in MODELS.values():
        path=models/item['file']
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']:continue
        temp=path.with_suffix('.download')
        url='https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/'+item['file']
        print('Downloading official model:',item['file'],flush=True)
        with urllib.request.urlopen(url,timeout=120) as response,temp.open('wb') as out:
            while block:=response.read(1024*1024):out.write(block)
        if hashlib.sha256(temp.read_bytes()).hexdigest()!=item['sha256']:
            temp.unlink(missing_ok=True);raise RuntimeError('Model checksum mismatch. Installation stopped.')
        temp.replace(path)
    status=subprocess.run([str(python_path()),str(ROOT/'scripts/matting_runner.py'),'--status'],capture_output=True,check=True,text=True)
    print(status.stdout.strip());report={'install_seconds':time.perf_counter()-started,'status':json.loads(status.stdout)}
    (runtime/'setup-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Background-removal runtime ready. Existing Python libraries unchanged.')


if __name__=='__main__':main()
