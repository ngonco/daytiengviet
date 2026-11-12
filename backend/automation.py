"""Local folder ingestion. Content history intentionally outlives project retention."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import threading
import time

from . import store
from .config import binary
from .media import probe, ffmpeg
from .seo import video_filename

EXTENSIONS={'.mp4','.mov','.mkv','.webm','.m4v'}
ACTIVE={'queued','running','cancelling'}
SCAN_LOCK=threading.Lock()
OBSERVED={}
LAST_SCAN=0.0
SCAN_UNTIL=0.0


def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()


def signature(path):
    info=path.stat()
    return [info.st_size,info.st_mtime_ns]


def config():
    with store.connect() as db:row=db.execute('SELECT data FROM automation_settings WHERE id=1').fetchone()
    return json.loads(row[0]) if row else {'folder':'','enabled':False,'message':''}


def configure(folder=None,enabled=None,message=None,remove_background=None):
    with store.LOCK:
        value=config()
        if remove_background is not None:value['remove_background']=bool(remove_background)
        if folder is not None:
            root=Path(folder).expanduser().resolve()
            if not root.is_dir():raise ValueError('Hãy chọn thư mục nguồn đang tồn tại.')
            private=store.data_root().resolve()
            if root==private or private in root.parents:
                raise ValueError('Chọn thư mục nguồn bên ngoài dữ liệu nội bộ VietCut.')
            value['folder']=str(root)
            value['message']='Đã chọn thư mục nguồn.'
        if enabled is not None:
            if enabled and not value['folder']:raise ValueError('Chọn thư mục nguồn trước khi bật tự động dựng.')
            value['enabled']=enabled
            value['message']='Đang kiểm tra thư mục nguồn.' if enabled else 'Đã tạm dừng nhận nguồn; tác vụ đang dựng vẫn được hoàn tất.'
        if message is not None:value['message']=message
        with store.connect() as db:
            db.execute('INSERT INTO automation_settings VALUES (1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(json.dumps(value,ensure_ascii=False),))
        return value


def items():
    with store.connect() as db:rows=db.execute('SELECT data FROM automation_items ORDER BY updated DESC').fetchall()
    return [json.loads(row[0]) for row in rows]


def get(code):
    with store.connect() as db:row=db.execute('SELECT data FROM automation_items WHERE hash=?',(code,)).fetchone()
    if not row:raise KeyError(code)
    return json.loads(row[0])


def put(item):
    with store.connect() as db:
        db.execute('INSERT INTO automation_items VALUES (?,?,?) ON CONFLICT(hash) DO UPDATE SET data=excluded.data,updated=excluded.updated',(item['hash'],json.dumps(item,ensure_ascii=False),store.now()))
    return item


def output_record(path):
    with store.connect() as db:db.execute('INSERT OR IGNORE INTO automation_outputs VALUES (?,?)',(digest(path),str(Path(path).resolve())))


def is_output(code):
    with store.connect() as db:return db.execute('SELECT 1 FROM automation_outputs WHERE hash=? LIMIT 1',(code,)).fetchone() is not None


def snapshot():
    rows=items()
    for row in rows:
        if row.get('job_id'):
            job=store.job_read(row['job_id'])
            if job:row.update(progress=job['progress'],message=job['message'])
    cfg=config()
    return {'config':{key:cfg[key] for key in ['folder','enabled','message']},'items':rows[:300],'counts':{state:sum(r['state']==state for r in rows) for state in ['waiting','running','retry_wait','done','failed','needs_attention','cancelled']}}


def native_folder():
    # Separate hidden helper: Tk must own its main thread, never the web worker's.
    import sys
    code="import tkinter as t;from tkinter import filedialog;r=t.Tk();r.withdraw();r.attributes('-topmost',True);p=filedialog.askdirectory(title='Chọn thư mục source tự động dựng',mustexist=True);print(p);r.destroy()"
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,encoding='utf-8',errors='replace',env={**os.environ,'PYTHONIOENCODING':'utf-8'},creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise ValueError('Không mở được hộp chọn thư mục. Bạn có thể nhập đường dẫn thư mục.')
    return result.stdout.strip()


def _safe_files(root):
    private=store.data_root().resolve()
    for directory,dirs,files in os.walk(root,followlinks=False):
        def safe(path):
            try:
                info=path.lstat()
                return not path.is_symlink() and not getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024) and path.resolve()!=private and private not in path.resolve().parents
            except OSError:return False
        dirs[:]=sorted(d for d in dirs if safe(Path(directory)/d))
        for name in sorted(files):
            path=Path(directory)/name
            if path.suffix.lower() in EXTENSIONS and safe(path):yield path


def _backfill():
    """Index existing owned files once per signature without changing project JSON."""
    cfg=config();indexed=cfg.get('indexed',{})
    for project in store.listing(include_trashed=True):
        if project.get('diagnostic') or not project.get('source_file'):continue
        state=project.get('_retention',{}).get('state','active')
        folder=store.data_root()/('trash' if state=='trashed' else 'projects')/project['id']
        source=folder/project['source_file'];result=project.get('export')
        key=project['id']
        try:
            sig=[signature(source),result.get('digest') if result else None]
            previous=indexed.get(key,{})
            if isinstance(previous,dict) and previous.get('signature')==sig:continue
            code=digest(source)
            if result and (folder/result['file']).is_file():
                probe(folder/result['file']);output_record(folder/result['file'])
                try:get(code)
                except KeyError:
                    row={'hash':code,'source':str(source),'project_id':key,'attempts':0,'created_at':store.now()}
                    row.update(state='done',output=str(folder/result['file']),message='Đã xuất trong dự án có sẵn');put(row)
            indexed[key]={'signature':sig,'hash':code}
        except (OSError,ValueError,KeyError):continue
    with store.LOCK:
        current=config();current['indexed']=indexed
        with store.connect() as db:db.execute('INSERT INTO automation_settings VALUES (1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(json.dumps(current,ensure_ascii=False),))


def scan(force=False,at=None):
    global LAST_SCAN,SCAN_UNTIL
    if not SCAN_LOCK.acquire(blocking=False):return
    try:
        cfg=config();now=time.monotonic() if at is None else at
        if force:SCAN_UNTIL=now+15
        if not cfg['folder'] or (not force and ((not cfg['enabled'] and now>SCAN_UNTIL) or now-LAST_SCAN<5)):return
        LAST_SCAN=now
        root=Path(cfg['folder'])
        if not root.is_dir():configure(message='Không truy cập được thư mục nguồn; sẽ kiểm tra lại.');return
        _backfill();seen=set()
        known={r['hash']:r for r in items()}
        for path in _safe_files(root):
            name=str(path.resolve());seen.add(name)
            try:
                sig=signature(path);old=OBSERVED.get(name)
                if old is None or old['signature']!=sig:
                    OBSERVED[name]={'signature':sig,'since':now};continue
                if now-old['since']<10:continue
                if old.get('hash'):continue
                code=digest(path)
                if signature(path)!=sig:OBSERVED.pop(name,None);continue
                old['hash']=code
                if is_output(code):continue
                if code in known:
                    # A copied or moved unfinished input follows its latest live path.
                    row=known[code]
                    if row['state'] not in ['done','running'] and not Path(row['source']).is_file():row['source']=name;put(row)
                    elif row['source']!=name:
                        row['duplicate_paths']=list(dict.fromkeys(row.get('duplicate_paths',[])+[name]))[-20:];put(row)
                    continue
                row={'hash':code,'source':name,'signature':sig,'root':str(root.resolve()),'state':'waiting','attempts':0,'created_at':store.now()}
                put(row);known[code]=row
            except OSError:continue
        for name in list(OBSERVED):
            if name not in seen:OBSERVED.pop(name,None)
        configure(message='Đang theo dõi nguồn mới.' if cfg['enabled'] else 'Đã quét; bật tự động dựng để xử lý hàng đợi.')
    finally:SCAN_LOCK.release()


def retry(code):
    with store.LOCK:
        row=get(code)
        if row['state'] not in ['failed','needs_attention','cancelled']:raise ValueError('Nguồn này chưa cần thử lại.')
        row.update(state='waiting',attempts=0,error=None,retry_at=0)
        return put(row)


def dispatch():
    if not config()['enabled']:return
    with store.LOCK:
        if any(j['status'] in ACTIVE for j in store.jobs()):return
        pending=sorted([r for r in items() if r['state'] in ['waiting','retry_wait'] and r.get('retry_at',0)<=time.time()],key=lambda r:r['created_at'])
        if not pending:return
        row=pending[0]
        try:
            if is_output(row['hash']):
                row.update(state='done',message='Bỏ qua file do VietCut xuất.');put(row);return
            project=None
            if row.get('project_id'):
                try:project=store.read(row['project_id'])
                except (KeyError,store.TrashedProject):pass
            if not project:
                # A matching incomplete lesson project can resume its saved work.
                indexed=config().get('indexed',{})
                for candidate in store.listing():
                    opts=candidate.get('options',{});bg=opts.get('background_removal',{})
                    expected='9:16' if candidate['metadata']['duration']<=90 else '16:9'
                    if candidate.get('diagnostic') or opts.get('layout_mode')!='lesson' or opts.get('ratio')!=expected or opts.get('subtitles')!='bilingual' or bool(bg.get('enabled'))!=bool(config().get('remove_background',False)) or bg.get('enabled') and bg.get('device','cuda')!='cuda':continue
                    path=store.data_root()/'projects'/candidate['id']/candidate['source_file']
                    entry=indexed.get(candidate['id'],{})
                    if not path.is_file():continue
                    code=entry.get('hash') if isinstance(entry,dict) and entry.get('signature',[None])[0]==signature(path) else digest(path)
                    if code==row['hash']:project=candidate;break
            request={'automation_hash':row['hash']}
            if project:
                row['project_id']=project['id']
                job=store.job_create(project['id'],'auto_save' if project.get('export') else 'pipeline',request)
            else:
                from .app import create,Options
                source=Path(row['source']);before=signature(source)
                if digest(source)!=row['hash'] or signature(source)!=before:raise ValueError('Source đã thay đổi; chờ lần quét mới.')
                meta=probe(source);pid=store.uid();folder=store.folder(pid);copy=folder/('incoming'+source.suffix.lower())
                shutil.copy2(source,copy)
                if signature(source)!=before or digest(copy)!=row['hash']:
                    copy.unlink(missing_ok=True);raise ValueError('Source đang thay đổi; hãy thử lại khi chép xong.')
                # Persist ownership before creation so recovery cannot create duplicate projects.
                row['project_id']=pid;put(row)
                project=create(copy,'',Options(ratio='9:16' if meta['duration']<=90 else '16:9',layout_mode='lesson',landscape_layout='circle',subtitles='bilingual',background_removal={'enabled':bool(config().get('remove_background',False)),'device':'cuda'},video_frames={'9:16':{},'16:9':{}}),pid,True,request)
                store.update(pid,original_name=source.name,auto_created=True)
                job=store.jobs(pid)[0]
            row.update(state='running',job_id=job['id'],error=None);put(row)
        except Exception as exc:failure(row,exc)


def publish(project,context,code):
    """Retrying a publication never invokes providers, matting or rendering."""
    with store.LOCK:row=get(code)
    _publish(project,context,row,put,code)


def publish_edited(project,context):
    """Manual exports reuse saved analysis and publish with an independent retry journal."""
    row=next((r for r in items() if r.get('project_id')==project['id']),None)
    if not row:return
    if Path(row['source']).resolve().is_relative_to(store.data_root().resolve()):return
    key=project['export']['digest']
    journal=store.folder(project['id'])/'analysis'/'manual-publications'/f'{key}.json'
    journal.parent.mkdir(parents=True,exist_ok=True)
    saved=json.loads(journal.read_text(encoding='utf-8')) if journal.exists() else {'source':row['source']}
    def save(value):store.atomic_json(journal,value)
    _publish(project,context,saved,save,'manual-'+project['id']+'-'+key)
    return saved.get('output')


def _publish(project,context,row,save,code):
    source=store.folder(project['id'])/project['export']['file']
    parent=Path(row['source']).parent
    if not parent.is_dir():raise OSError('Thư mục source không còn truy cập được; chưa lưu video cạnh source.')
    target=Path(row['output']) if row.get('output') else parent/video_filename(project)
    expected=digest(source)
    if not row.get('verified_export')==expected:
        context.progress(99,'Kiểm tra toàn bộ video trước khi lưu')
        ffmpeg(['-xerror','-err_detect','explode','-i',source,'-f','null','-'],context)
        meta=probe(source)
        if abs(meta['duration']-project['export']['duration'])>.15:raise ValueError('Video xuất chưa đủ thời lượng; chưa đánh dấu hoàn tất.')
        row['verified_export']=expected;save(row)
    if target.exists() and digest(target)==expected:
        output_record(target);row.update(state='done',output=str(target),error=None);save(row);return
    if not row.get('output') or target.exists():
        stem=parent/Path(video_filename(project)).stem;index=1
        # Construct literally so a dotted lesson name is never truncated.
        target=parent/(stem.name+'.mp4')
        while target.exists():index+=1;target=parent/(stem.name+f' ({index}).mp4')
        row['output']=str(target);save(row)
    temporary=parent/f'.vietcut-{code}.partial'
    context.check()
    with source.open('rb') as inp,temporary.open('wb') as out:
        while chunk:=inp.read(1024*1024):context.check();out.write(chunk)
        out.flush();os.fsync(out.fileno())
    if digest(temporary)!=expected:raise OSError('Lưu video chưa đầy đủ; hãy thử lại bước lưu.')
    # Windows rename refuses to replace an existing file. Keep that guarantee on POSIX too.
    if os.name=='nt':os.rename(temporary,target)
    else:
        os.link(temporary,target)
        temporary.unlink()
    output_record(target);row.update(state='done',output=str(target),error=None,message='Đã xuất cạnh source');save(row)


def failure(row,exc):
    from .providers import ProviderError
    from .media import Cancelled
    attempts=row.get('attempts',0)
    transient=isinstance(exc,(OSError,TimeoutError)) or isinstance(exc,ProviderError) and exc.status in [None,408,429,500,502,503,504]
    attention=isinstance(exc,ProviderError) and not transient or any(word in str(exc).lower() for word in ['gpu','mô hình','chưa điền','chưa sẵn sàng'])
    state='cancelled' if isinstance(exc,Cancelled) else 'needs_attention' if attention else 'retry_wait' if transient and attempts<2 else 'failed'
    row.update(state=state,error=str(exc)[:1000],attempts=attempts+1,retry_at=time.time()+(30 if attempts==0 else 120))
    put(row)


def job_failed(job,exc):
    code=json.loads(job['request']).get('automation_hash')
    if code:failure(get(code),exc)


def reconcile():
    for row in items():
        if row['state']!='running':continue
        job=store.job_read(row.get('job_id',''))
        if job and job['status'] in ACTIVE:continue
        if job and job['status']=='succeeded' and row.get('output'):
            row['state']='done';put(row)
        elif job and job['status'] in ['failed','cancelled']:
            from .media import Cancelled
            failure(row,Cancelled('Đã dừng tự động dựng.') if job['status']=='cancelled' else RuntimeError(job.get('error') or 'Tác vụ chưa hoàn tất.'))
        else:row.update(state='waiting');put(row)


def start():
    stop=threading.Event()
    def loop():
        while not stop.is_set():
            try:reconcile();scan();dispatch()
            except Exception:
                # Never emit provider responses, project data or paths to process logs.
                configure(message='Chưa hoàn tất kiểm tra thư mục; sẽ thử lại.')
            stop.wait(1)
    thread=threading.Thread(target=loop,name='vietcut-folder',daemon=True);thread.start()
    return stop
