"""Bounded, read-only waveform for the assembly editor. No provider calls."""
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
from .media import ffmpeg

@lru_cache(maxsize=16)
def _peaks(path,size,mtime,duration):
    with TemporaryDirectory() as temp:
        raw=Path(temp)/'voice.pcm'
        ffmpeg(['-i',path,'-vn','-ac','1','-ar','8000','-f','s16le',raw])
        if not raw.stat().st_size:return []
        samples=raw.stat().st_size//2;count=min(1600,samples);result=[]
        with raw.open('rb') as stream:
            for i in range(count):
                length=((i+1)*samples//count-i*samples//count)*2
                part=np.frombuffer(stream.read(length),dtype='<i2').astype(np.int32)
                result.append(round(float(np.max(np.abs(part)))/32768,4))
        return result

def waveform(project,folder):
    path=(folder/project['source_file']).resolve()
    if not path.is_relative_to(folder.resolve()):raise ValueError('Invalid source path')
    stat=path.stat()
    return {'duration':project['metadata']['duration'],'peaks':_peaks(str(path),stat.st_size,stat.st_mtime_ns,project['metadata']['duration'])}
