"""Read-only draft scene rendering. Bounded RAM cache; no project writes/jobs/providers."""
import base64
from collections import OrderedDict
import hashlib
import io
import json
import threading
from pathlib import Path
from .templates import geometry,signature,make_frame,speaker_focus,subtitle_position,brand
from .lesson_render import subtitle_image
from .render import dimensions
from .matting_schema import BackgroundRemoval

_cache=OrderedDict()
_lock=threading.RLock()
MAX_ENTRIES=64
MAX_BYTES=24*1024*1024


def png_cached(key,draw):
    key=hashlib.sha256(json.dumps(key,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    with _lock:
        if key in _cache:
            _cache.move_to_end(key);return _cache[key]
    image=draw();stream=io.BytesIO();image.save(stream,format='PNG',compress_level=1)
    raw=stream.getvalue()
    with _lock:
        _cache[key]=raw;_cache.move_to_end(key)
        while len(_cache)>MAX_ENTRIES or sum(map(len,_cache.values()))>MAX_BYTES:_cache.popitem(last=False)
    return raw


def data_url(raw):return 'data:image/png;base64,'+base64.b64encode(raw).decode('ascii')


def source_info(project,folder):
    cfg=BackgroundRemoval.model_validate(project['options'].get('background_removal',{})).model_dump()
    result=project.get('matting') or {}
    if not cfg['enabled']:return {'file':project['source_file'],'state':'original'}
    identity=result.get('identity',{})
    path=folder/result.get('file','not-ready')
    valid=path.resolve().is_relative_to(folder.resolve()) and path.is_file()
    if valid and identity.get('config')==cfg and identity.get('paper')==brand()['paper']:
        return {'file':result['file'],'state':'ready'}
    return {'file':project['source_file'],'state':'pending','message':'Lớp người nói/nền chưa cập nhật. Đang hiển thị video gốc.'}


def scene(project,folder,lesson,caption,sequence=0):
    w,h=dimensions(project,True);g=geometry(w,h);theme=signature()
    asset_id=lesson.get('asset_id');fingerprint=None
    if asset_id:
        asset=project.get('assets',{}).get(asset_id)
        if not asset or Path(asset['file']).name!=asset['file']:raise ValueError('Ảnh chưa có trong dự án.')
        path=folder/'assets'/asset['file']
        try:st=path.stat()
        except OSError:raise ValueError('Tệp ảnh không còn trong dự án. Hãy chọn ảnh khác.') from None
        fingerprint=[asset_id,st.st_size,st.st_mtime_ns]
    visual={k:lesson.get(k) for k in ['vi','en','chunks','asset_id','photo_crops']}
    page=png_cached({'kind':'page','theme':theme,'size':[w,h],'lesson':visual,'asset':fingerprint,'project':project['id']},lambda:make_frame(project,lesson,folder,w,h))
    sub=None;position=None
    if caption and caption.get('vi','').strip() and project['options'].get('subtitles')!='off':
        caption={**caption,'en':caption.get('en','') if project['options'].get('subtitles')=='bilingual' else ''}
        sub=png_cached({'kind':'subtitle','size':[w,h],'theme':theme,'vi':caption['vi'],'en':caption['en']},lambda:subtitle_image(caption,w,h))
        with ImageReader(sub) as image:tw,th=image.size
        x,y=subtitle_position(w,h,tw,th);position=[x,y,tw,th]
    fx,fy,fw,fh=speaker_focus(project,w,h);sx,sy,cw,ch=g['speaker']
    cropw,croph=min(fw,cw),min(fh,ch)
    left=(cw-cropw)/2-max(0,min(fw-cropw,fw*fx-cropw*.5))
    top=(ch-croph)/2-max(0,min(fh-croph,fh*fy-croph*.42))
    return {'sequence':sequence,'width':w,'height':h,'geometry':g,'speaker_transform':{'left':left,'top':top,'width':fw,'height':fh},'page':data_url(page),'subtitle':data_url(sub) if sub else None,'subtitle_rect':position,'source':source_info(project,folder)}


def ImageReader(raw):
    from PIL import Image
    return Image.open(io.BytesIO(raw))
