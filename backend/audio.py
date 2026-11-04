"""Measured voice normalization shared by both renderers and the live monitor.

Audio is measured after source cuts for export, before mixing music/effects.
No recordings are rewritten and no provider or matting runtime is involved.
"""
from collections import OrderedDict
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import threading

from .config import binary
from .store import atomic_json

AUDIO_VERSION=1
TARGET_I=-16
TARGET_TP=-1.5
BASE='aformat=channel_layouts=stereo'
TARGET=f'loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA=11'
_CACHE=OrderedDict()
_LOCK=threading.Lock()


def number(value):
    try:
        result=float(value)
        return result if math.isfinite(result) else None
    except (ValueError,TypeError):return None


def measure(input_args,context=None,cache=None):
    if cache is not None and Path(cache).is_file():
        try:
            saved=json.loads(Path(cache).read_text(encoding='utf-8'))
            if saved.get('version')==AUDIO_VERSION:return saved
        except (OSError,ValueError):pass
    if context:context.progress(96,'Đo âm lượng giọng nói để tự cân bằng')
    # volumedetect measures the unnormalized input as a fallback for very short
    # (<400ms) audible clips that have no finite integrated R128 measurement.
    with tempfile.TemporaryFile() as diagnostics:
        args=[binary('ffmpeg'),'-hide_banner','-nostats','-loglevel','info','-threads','2',*map(str,input_args),'-map','0:a:0','-vn','-af',f'{BASE},volumedetect,{TARGET}:print_format=json','-f','null','-']
        process=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=diagnostics,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            while process.poll() is None:
                if context:context.check()
                try:process.wait(timeout=.15)
                except subprocess.TimeoutExpired:pass
        except BaseException:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            raise
        if process.returncode:raise RuntimeError('Chưa đo được âm lượng giọng nói. Hãy kiểm tra âm thanh nguồn rồi thử lại.')
        diagnostics.seek(0,2);size=diagnostics.tell();diagnostics.seek(max(0,size-12000))
        text=diagnostics.read().decode('utf-8','replace')
    packets=re.findall(r'\{\s*"input_i"[\s\S]*?\}',text)
    if not packets:raise RuntimeError('Chưa nhận được kết quả đo âm lượng giọng nói.')
    stats=json.loads(packets[-1])
    means=re.findall(r'mean_volume:\s*([-\w.]+)\s*dB',text)
    peaks=re.findall(r'max_volume:\s*([-\w.]+)\s*dB',text)
    integrated=number(stats.get('input_i'));peak=number(stats.get('input_tp'))
    mean=number(means[-1]) if means else None
    if peak is None:peak=number(peaks[-1]) if peaks else None
    silent=integrated is None and (peak is None or peak<=-85)
    desired=TARGET_I-integrated if integrated is not None else -20-mean if mean is not None else 0
    gain=0 if silent else max(-60,min(48,desired,TARGET_TP-peak if peak is not None else 0))
    result={'version':AUDIO_VERSION,'target_lufs':TARGET_I,'target_peak_db':TARGET_TP,'input_lufs':integrated,'input_peak_db':peak,'gain_db':gain,'silent':silent,'measurements':stats}
    if cache is not None:atomic_json(Path(cache),result)
    return result


def voice_filter(input_args,context,enabled=True,cache=None):
    if not enabled:return BASE+',aresample=48000',{'enabled':False,'version':AUDIO_VERSION}
    result=measure(input_args,context,cache)
    stats=result['measurements']
    keys={'measured_I':'input_i','measured_TP':'input_tp','measured_LRA':'input_lra','measured_thresh':'input_thresh','offset':'target_offset'}
    if not result['silent'] and all(number(stats.get(value)) is not None for value in keys.values()):
        params=':'.join(f'{key}={float(stats[value]):.6f}' for key,value in keys.items())
        filters=f'{BASE},{TARGET}:{params}:linear=true,aresample=48000'
    else:
        filters=f"{BASE},volume={result['gain_db']:.6f}dB,aresample=48000"
    return filters,{'enabled':True,**result}


def preview_level(path):
    path=Path(path);info=path.stat();key=(str(path.resolve()),info.st_size,info.st_mtime_ns,AUDIO_VERSION)
    # Only tiny numeric summaries are cached. Serialize first-time measurements
    # so multiple open preview requests cannot repeatedly decode the same source.
    with _LOCK:
        if key not in _CACHE:
            _CACHE[key]=measure(['-i',path])
            while len(_CACHE)>64:_CACHE.popitem(last=False)
        _CACHE.move_to_end(key);value=_CACHE[key]
        return {k:value[k] for k in ['gain_db','silent','target_lufs','input_lufs','input_peak_db']}
