"""Opt-in cut/restore validation on the acceptance clone, without repeating matting."""
import copy
import json
from pathlib import Path
import subprocess
import numpy as np
import cv2
from backend import store
from backend.config import binary
from backend.media import ffmpeg
from scripts.acceptance_matting import call,wait,OUT


def pcm(path,at=0,duration=None):
    args=[binary('ffmpeg'),'-v','error','-ss',str(at),'-i',str(path),'-vn','-ac','1','-ar','16000']
    if duration is not None:args+=['-t',str(duration)]
    return np.frombuffer(subprocess.run([*args,'-f','f32le','pipe:1'],check=True,capture_output=True).stdout,dtype=np.float32)


def run():
    state=json.loads((OUT/'state.json').read_text(encoding='utf-8'));pid=state['project_id'];p=call('GET',f'/projects/{pid}');folder=store.folder(pid)
    original=copy.deepcopy(p['plan']);code=p['matting']['code']
    source=folder/p['source_file'];composition=folder/p['matting']['file']
    a,b=pcm(source,duration=58),pcm(composition,duration=58)
    np.testing.assert_array_equal(a,b) # Original source audio is copied, never run through the model.
    plan=copy.deepcopy(original);plan['cuts'].append({'id':'matting-cross-20','start':19.8,'end':20.2,'reason':'Acceptance only','enabled':True,'locked':True})
    call('PUT',f'/projects/{pid}/plan',json={'revision':p['revision'],'options':p['options'],'plan':plan});p=wait(pid)
    assert p['matting']['code']==code
    result=folder/p['preview']['file'];ffmpeg(['-i',result,'-f','null','-'])
    expected=p['metadata']['duration']-.4
    assert abs(p['preview']['duration']-expected)<.04
    # Compare a spoken audio window after the cut. Loudness processing may change amplitude.
    ref=pcm(source,21.4,1.5);actual=pcm(result,20.8,1.9)
    match=cv2.matchTemplate(actual.reshape(1,-1),ref.reshape(1,-1),cv2.TM_CCOEFF_NORMED)
    _,score,_,peak=cv2.minMaxLoc(match);offset=peak[0]/16000-.2
    assert score>.85 and abs(offset)<1/30,(score,offset)
    call('PUT',f'/projects/{pid}/plan',json={'revision':p['revision'],'options':p['options'],'plan':original});p=wait(pid)
    assert p['matting']['code']==code and p['plan']==original
    # Final export metadata matches the restored version; the identical export itself is reused.
    call('POST',f'/projects/{pid}/jobs/export');p=wait(pid)
    report={'source_audio_pcm_identical':True,'cut_crossing_20_seconds':True,'audio_correlation':score,'audio_offset_seconds':offset,'duration_after_cut':expected,'restore_passed':True,'matting_cache_unchanged':True}
    store.atomic_json(OUT/'cuts-verification.json',report);print(json.dumps(report,indent=2))


if __name__=='__main__':run()
