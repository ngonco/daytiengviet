import json
import threading
import time
from . import store
from .media import Cancelled, extract_frames
from .providers import transcribe, analyze, fetch_assets
from .render import render
from .lessons import analyze_lessons,fetch_lesson_assets

class Context:
    def __init__(self, job):
        self.job_id=job['id']
        self.project_id=job['project_id']
        self.kind=job['kind']
        self.folder=store.folder(self.project_id)

    def check(self):
        job=store.job_read(self.job_id)
        if not job or job['status'] in ['cancelled','cancelling']:
            raise Cancelled('Đã hủy tác vụ')

    def progress(self, value, message):
        self.check()
        previous=store.job_read(self.job_id)['progress']
        store.job_update(self.job_id,progress=max(previous,max(0,min(100,value))),message=message)

def version(project):
    if project.get('plan'):
        path=store.folder(project['id'])/'versions'
        path.mkdir(exist_ok=True)
        store.atomic_json(path/f"v{project['revision']:05}.json",{'plan':project['plan'],'options':project['options'],'revision':project['revision']})

def execute(job):
    context=Context(job)
    project=store.read(job['project_id'])
    request=json.loads(job['request'])
    store.update(project['id'],status='working')
    if job['kind'] in ['pipeline','revise','reframe']:
        context.progress(3,'Chuẩn bị âm thanh và khung hình')
        frames=extract_frames(context.folder/project['source_file'],context.folder,project['metadata'],context)
        project=store.update(project['id'],frames=frames)
        transcript=transcribe(project,context)
        project=store.update(project['id'],transcript=transcript)
        if job['kind'] in ['revise','reframe'] or not project.get('plan'):
            if job['kind']=='reframe':
                project={**project,'options':{**project['options'],'layout_mode':'lesson'}}
                plan=project['plan'];warnings=[];vision=project.get('vision_supported',False)
            else:
                plan,warnings,vision=analyze(project,transcript,frames,context,request.get('prompt',''),project.get('plan') if job['kind']=='revise' else None)
            if project['options'].get('layout_mode')=='lesson':
                plan=analyze_lessons(project,plan,transcript,context,project.get('plan'),request.get('prompt',''))
                assets,photo_warnings=fetch_lesson_assets(project,plan,context,vision)
                from .templates import validate_text_layout
                validate_text_layout({**project,'assets':assets},plan)
            else:
                assets,photo_warnings=fetch_assets(project,plan,context,vision)
            # For a conversion, save the previous layout before changing options.
            version(store.read(project['id']) if job['kind']=='reframe' else project)
            project=store.update(project['id'],plan=plan,options=project['options'],assets=assets,warnings=warnings+photo_warnings,vision_supported=vision,revision=project['revision']+1)
        else:
            plan=project['plan']
        result=render(project,plan,transcript,context,True)
        store.update(project['id'],preview=result,status='ready')
    elif job['kind'] in ['preview','export']:
        if not project.get('plan'):
            raise ValueError('Dự án chưa có phương án dựng.')
        context.progress(1,'Chuẩn bị khung hình dự án')
        frames=extract_frames(context.folder/project['source_file'],context.folder,project['metadata'],context)
        project=store.update(project['id'],frames=frames)
        preview=job['kind']=='preview'
        result=render(project,project['plan'],project.get('transcript',{}),context,preview)
        store.update(project['id'],**{'preview' if preview else 'export':result,'status':'ready'})
    else:
        raise ValueError('Tác vụ không hợp lệ')

def loop():
    while True:
        queued=sorted([j for j in store.jobs() if j['status']=='queued'],key=lambda j:j['created'])
        if not queued:
            time.sleep(.5)
            continue
        job=queued[0]
        if store.job_read(job['id'])['status']!='queued':
            continue
        store.job_update(job['id'],status='running',message='Bắt đầu xử lý',error=None)
        try:
            execute(job)
            # A late cancellation cannot turn a cancelled job into success.
            if store.job_read(job['id'])['status'] in ['cancelled','cancelling']:
                raise Cancelled()
            store.job_update(job['id'],status='succeeded',progress=100,message='Hoàn tất')
        except Cancelled:
            store.job_update(job['id'],status='cancelled',message='Đã hủy; kết quả từng bước vẫn được giữ')
            store.update(job['project_id'],status='ready' if store.read(job['project_id']).get('plan') else 'new')
        except Exception as exc:
            # Provider exceptions are sanitized; never log request headers or .env.
            message=str(exc)[:2500]
            store.job_update(job['id'],status='failed',message='Chưa hoàn tất',error=message)
            store.update(job['project_id'],status='error')

def start():
    thread=threading.Thread(target=loop,name='vietcut-worker',daemon=True)
    thread.start()
    return thread
