import asyncio
import json
import shutil
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse, Response
import math
import subprocess
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from PIL import Image, ImageOps
from . import store, worker
from .config import ROOT, settings
from .media import probe
from .providers import connection_checks, search_photos, download_photo
from .timeline import validate_plan, keep_spans
from .matting_schema import BackgroundRemoval, validate_duration

class Options(BaseModel):
    model_config=ConfigDict(extra='ignore',allow_inf_nan=False)
    ratio: Literal['9:16','16:9','original']='9:16'
    style: Literal['auto','energetic','education']='auto'
    density: float=Field(default=1,ge=.3,le=1.7)
    subtitles: Literal['bilingual','vi','off']='bilingual'
    language: Literal['vi','en','auto']='auto'
    sfx: bool=True
    zoom: bool=True
    fit: Literal['contain','cover']='contain'
    focus_x: float=Field(default=.5,ge=0,le=1)
    layout_mode: Literal['legacy','lesson']='legacy'
    speaker_x: float | None=Field(default=None,ge=0,le=1)
    speaker_y: float | None=Field(default=None,ge=0,le=1)
    speaker_scale: float=Field(default=1,ge=.65,le=1.5)
    background_removal: BackgroundRemoval=Field(default_factory=BackgroundRemoval)

class SampleBody(BaseModel):
    filename: str
    title: str='Bài học mới'
    options: Options=Field(default_factory=Options)

class SavePlan(BaseModel):
    revision: int
    plan: dict
    options: Options

class RevisionBody(BaseModel):
    prompt: str=Field(min_length=3,max_length=2000)

class PhotoBody(BaseModel):
    query: str=Field(min_length=1,max_length=200)
    photo_id: str=Field(pattern=r'^\d+$')

class RestoreBody(BaseModel):
    revision: int=Field(ge=1)

@asynccontextmanager
async def lifespan(app):
    store.init()
    worker.start()
    yield

app=FastAPI(title='VietCut Studio',version='1.2.0',lifespan=lifespan)

@app.middleware('http')
async def local_access(request:Request,call_next):
    # Reject cross-origin writes and unexpected Host headers, even on a local server.
    host=request.headers.get('host','').split(':')[0]
    if host not in ['127.0.0.1','localhost','testserver','[']:
        return JSONResponse({'detail':'App chỉ phục vụ trên máy này.'},403)
    origin=request.headers.get('origin')
    if origin and origin not in ['http://127.0.0.1:8765','http://localhost:8765','http://127.0.0.1:5173','http://localhost:5173',f"http://127.0.0.1:{settings().get('APP_PORT','8765')}"]:
        return JSONResponse({'detail':'Nguồn truy cập không hợp lệ.'},403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    return response

@app.exception_handler(ValueError)
async def value_error(request,exc):
    return JSONResponse({'detail':str(exc)[:1500]},400)

@app.exception_handler(KeyError)
async def key_error(request,exc):
    return JSONResponse({'detail':'Không tìm thấy tài nguyên.'},404)

def project_read(project_id):
    project=store.read(project_id)
    project['options']=Options.model_validate(project['options']).model_dump()
    project['jobs']=store.jobs(project_id)
    if project.get('plan'):
        project['time_map']=keep_spans(project['metadata']['duration'],project['plan']['cuts'])
    return project

def idle(project_id):
    if any(j['status'] in ['queued','running','cancelling'] for j in store.jobs(project_id)):
        raise HTTPException(409,'Dự án đang xử lý. Hãy đợi hoặc hủy tác vụ trước khi chỉnh sửa.')

def create(source:Path,title,options,project_id=None,move=False):
    metadata=probe(source)
    project_id=project_id or store.uid()
    folder=store.folder(project_id)
    target=folder/('source'+source.suffix.lower())
    if move:
        source.replace(target)
    elif source.resolve()!=target.resolve():
        shutil.copy2(source,target)
    values=options.model_dump()
    # Missing fields in OLD projects mean legacy; missing fields on NEW creation mean lesson.
    if 'layout_mode' not in options.model_fields_set:
        values['layout_mode']='lesson'
    if 'background_removal' not in options.model_fields_set:
        values['background_removal']['enabled']=True
    validate_duration(values,metadata['duration'])
    if values['style']=='auto':
        portrait=values['ratio']=='9:16' or values['ratio']=='original' and metadata['height']>metadata['width']
        values['style']='energetic' if portrait else 'education'
    project={'id':project_id,'title':title[:120] or 'Bài học mới','source_file':target.name,'original_name':source.name,'metadata':metadata,'options':values,'status':'new','revision':0,'plan':None,'transcript':None,'assets':{},'frames':[],'warnings':[],'preview':None,'export':None,'music_file':None,'created_at':store.now()}
    store.save(project)
    store.job_create(project_id,'pipeline')
    return project_read(project_id)

@app.get('/api/health')
def health():
    return {'ok':True,'app':'vietcut','version':'1.2.0'}

@app.get('/api/matting/status')
def matting_status():
    from .matting import runtime_status
    return runtime_status()

@app.get('/api/settings')
def get_settings():
    config=settings()
    return {'configured':{name:bool(config.get(key)) for name,key in [('groq','GROQ_API_KEY'),('vilao','VILAO_API_KEY'),('pexels','PEXELS_API_KEY')]},'model':config.get('VILAO_MODEL'),'groq_model':config.get('GROQ_MODEL'),'base_url':config.get('VILAO_BASE_URL')}

@app.post('/api/settings/check')
def check():
    return connection_checks()

@app.get('/api/samples')
def samples():
    return [{'filename':p.name,'bytes':p.stat().st_size} for p in ROOT.glob('*.mp4')]

@app.get('/api/projects')
def projects():
    return [{k:p.get(k) for k in ['id','title','metadata','options','status','revision','updated_at','created_at','preview','export']} for p in store.listing() if not p.get('diagnostic')]

@app.post('/api/projects/sample')
def from_sample(body:SampleBody):
    source=ROOT/body.filename
    if source.parent.resolve()!=ROOT.resolve() or source.suffix.lower()!='.mp4' or not source.is_file():
        raise HTTPException(404,'Không tìm thấy video mẫu.')
    return create(source,body.title,body.options)

@app.post('/api/projects')
def upload(file:UploadFile=File(...),title:str=Form('Bài học mới'),options:str=Form('{}')):
    option_values=Options.model_validate_json(options)
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in ['.mp4','.mov','.mkv','.webm','.m4v']:
        raise ValueError('Hỗ trợ MP4, MOV, MKV, WEBM và M4V.')
    project_id=store.uid()
    path=store.folder(project_id)/('upload'+suffix)
    try:
        with path.open('wb') as out:
            shutil.copyfileobj(file.file,out,length=1024*1024)
        project=create(path,title,option_values,project_id,True)
        store.update(project_id,original_name=file.filename or 'video')
        return project
    except Exception:
        path.unlink(missing_ok=True)
        raise

@app.get('/api/projects/{project_id}')
def get_project(project_id:str):
    return project_read(project_id)

@app.post('/api/projects/{project_id}/jobs/{kind}')
def create_job(project_id:str,kind:Literal['pipeline','preview','export']):
    project=store.read(project_id)
    if kind!='pipeline' and not project.get('plan'):
        raise ValueError('Cần tạo phương án dựng trước.')
    return store.job_create(project_id,kind)

@app.get('/api/jobs/{job_id}')
def get_job(job_id:str):
    result=store.job_read(job_id)
    if not result:
        raise HTTPException(404,'Không có tác vụ này.')
    return result

@app.post('/api/jobs/{job_id}/cancel')
def cancel(job_id:str):
    job=store.job_read(job_id)
    if not job:
        raise HTTPException(404,'Không có tác vụ này.')
    if job['status'] in ['queued','running']:
        store.job_update(job_id,status='cancelled' if job['status']=='queued' else 'cancelling',message='Đang dừng xử lý')
    return store.job_read(job_id)

@app.get('/api/projects/{project_id}/events')
async def events(project_id:str,request:Request):
    store.read(project_id)
    async def stream():
        previous=''
        while not await request.is_disconnected():
            project=store.read(project_id)
            snapshot={'jobs':store.jobs(project_id),'revision':project['revision'],'status':project['status'],'preview':project.get('preview'),'export':project.get('export')}
            payload=json.dumps(snapshot,ensure_ascii=False)
            if payload!=previous:
                yield 'data: '+payload+'\n\n'
                previous=payload
            else:
                yield ': heartbeat\n\n'
            await asyncio.sleep(1)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.put('/api/projects/{project_id}/plan')
def save_plan(project_id:str,body:SavePlan):
    with store.LOCK:
        idle(project_id)
        project=store.read(project_id)
        if body.revision!=project['revision']:
            raise HTTPException(409,'Dự án đã đổi ở cửa sổ khác. Hãy tải lại trước khi lưu.')
        plan=validate_plan(body.plan,project['metadata']['duration'])
        for visual in [*plan['visuals'],*plan['lessons']]:
            if visual.get('asset_id') and visual['asset_id'] not in project['assets']:
                raise ValueError('Ảnh chưa được tải vào dự án.')
        worker.version(project)
        options=body.options.model_dump()
        validate_duration(options,project['metadata']['duration'])
        if options['style']=='auto':
            portrait=options['ratio']=='9:16' or options['ratio']=='original' and project['metadata']['height']>project['metadata']['width']
            options['style']='energetic' if portrait else 'education'
        if options['layout_mode']=='lesson':
            if plan['schema_version']!=2:
                raise ValueError('Hãy dùng nút Chuyển sang khung bài học trước.')
            from .templates import validate_text_layout
            validate_text_layout({**project,'options':options},plan)
        store.update(project_id,plan=plan,options=options,revision=project['revision']+1)
        store.job_create(project_id,'preview')
    return project_read(project_id)

@app.post('/api/projects/{project_id}/revise')
def revise(project_id:str,body:RevisionBody):
    project=store.read(project_id)
    if not project.get('plan'):
        raise ValueError('Cần có bản dựng trước khi yêu cầu chỉnh lại.')
    return store.job_create(project_id,'revise',body.model_dump())

@app.post('/api/projects/{project_id}/reframe')
def reframe(project_id:str):
    project=store.read(project_id)
    if not project.get('plan'):
        raise ValueError('Cần có bản nhận diện và phương án dựng trước khi chuyển khung.')
    if project['options'].get('layout_mode')=='lesson':
        # A render may fail after the converted plan was committed. Retry without billing AI again.
        return store.job_create(project_id,'preview')
    return store.job_create(project_id,'reframe')

@app.get('/api/projects/{project_id}/versions')
def versions(project_id:str):
    project=store.read(project_id)
    files=sorted((store.folder(project_id)/'versions').glob('v*.json'),reverse=True)
    return [{'revision':project['revision'],'current':True}]+[{'revision':int(p.stem[1:]),'current':False} for p in files]

@app.post('/api/projects/{project_id}/restore')
def restore(project_id:str,body:RestoreBody):
    with store.LOCK:
        idle(project_id)
        project=store.read(project_id)
        path=store.folder(project_id)/'versions'/f'v{body.revision:05}.json'
        if not path.exists():
            raise HTTPException(404,'Không tìm thấy phiên bản.')
        old=json.loads(path.read_text(encoding='utf-8'))
        worker.version(project)
        restored=validate_plan(old['plan'],project['metadata']['duration'])
        restored_options=Options.model_validate(old['options']).model_dump()
        validate_duration(restored_options,project['metadata']['duration'])
        store.update(project_id,plan=restored,options=restored_options,revision=project['revision']+1)
        store.job_create(project_id,'preview')
    return project_read(project_id)

@app.get('/api/photos/search')
def photos(query:str):
    if not query.strip() or len(query)>200:
        raise ValueError('Từ khóa cần từ 1 đến 200 ký tự.')
    return search_photos(query)

@app.post('/api/projects/{project_id}/photos')
def choose_photo(project_id:str,body:PhotoBody):
    with store.LOCK:
        idle(project_id)
        project=store.read(project_id)
        candidates=search_photos(body.query)
        photo=next((p for p in candidates if p['id']==body.photo_id),None)
        if not photo:
            raise ValueError('Ảnh không còn trong kết quả. Hãy tìm lại.')
        asset=download_photo(photo,store.folder(project_id))
        assets={**project['assets'],asset['id']:asset}
        store.update(project_id,assets=assets)
    return asset

@app.post('/api/projects/{project_id}/image')
def upload_image(project_id:str,file:UploadFile=File(...)):
    idle(project_id)
    project=store.read(project_id)
    folder=store.folder(project_id)/'assets'
    folder.mkdir(exist_ok=True)
    asset_id='upload-'+store.uid()
    path=folder/(asset_id+'.jpg')
    try:
        with Image.open(file.file) as im:
            if im.width*im.height>50_000_000:
                raise ValueError('Ảnh quá lớn. Tối đa 50 megapixel.')
            image=ImageOps.exif_transpose(im).convert('RGB')
            image.thumbnail((2560,2560))
            image.save(path,quality=94)
    except (OSError,Image.DecompressionBombError):
        raise ValueError('Không đọc được ảnh. Hãy chọn JPG, PNG hoặc WEBP.')
    asset={'id':asset_id,'file':path.name,'provider':'upload','photographer':'Bạn cung cấp','url':'','photographer_url':'','alt':file.filename or 'Ảnh tải lên'}
    with store.LOCK:
        project=store.read(project_id)
        store.update(project_id,assets={**project['assets'],asset_id:asset})
    return asset

@app.post('/api/projects/{project_id}/music')
def upload_music(project_id:str,file:UploadFile=File(...)):
    idle(project_id)
    project=store.read(project_id)
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in ['.mp3','.wav','.m4a','.aac','.ogg','.flac']:
        raise ValueError('Chọn nhạc MP3, WAV, M4A, AAC, OGG hoặc FLAC.')
    filename='music-'+store.uid()+suffix
    path=store.folder(project_id)/filename
    with path.open('wb') as out:
        shutil.copyfileobj(file.file,out,length=1024*1024)
    worker.version(project)
    store.update(project_id,music_file=filename,revision=project['revision']+1)
    if project.get('plan'):
        store.job_create(project_id,'preview')
    return project_read(project_id)

@app.delete('/api/projects/{project_id}/music')
def remove_music(project_id:str):
    idle(project_id)
    project=store.read(project_id)
    worker.version(project)
    store.update(project_id,music_file=None,revision=project['revision']+1)
    if project.get('plan'):
        store.job_create(project_id,'preview')
    return project_read(project_id)

@app.get('/api/projects/{project_id}/media/{relative:path}')
def media(project_id:str,relative:str):
    store.read(project_id)
    folder=store.folder(project_id).resolve()
    path=(folder/relative).resolve()
    if not path.is_relative_to(folder) or not path.is_file() or path.suffix.lower() not in ['.mp4','.mov','.mkv','.webm','.m4v','.jpg','.png','.srt','.wav','.mp3','.json']:
        raise HTTPException(404,'Không tìm thấy tệp.')
    return FileResponse(path)

@app.get('/api/projects/{project_id}/matting/frame')
def matting_frame(project_id:str,time:float=0,background:Literal['cream','black','white']='cream',before:bool=False):
    from .config import binary
    if not math.isfinite(time):raise ValueError('Mốc thời gian không hợp lệ.')
    project=store.read(project_id);folder=store.folder(project_id)
    at=max(0,min(time,project['metadata']['duration']-1/30))
    frame=max(0,min(math.ceil(project['metadata']['duration']*30)-1,round(at*30)))
    args=[binary('ffmpeg'),'-hide_banner','-loglevel','error','-threads','2','-filter_complex_threads','1']
    if before:
        args+=['-ss',str(at),'-i',str(folder/project['source_file']),'-vf','scale=640:640:force_original_aspect_ratio=decrease']
    else:
        result=project.get('matting')
        if not result:raise HTTPException(404,'Chưa có kết quả xóa phông. Lưu và dựng xem trước trước khi so sánh.')
        # Never trust a saved path from an imported project. Import drops generated result metadata.
        code=result.get('code','')
        import re
        if not re.fullmatch(r'[a-f0-9]{24}',code):raise ValueError('Bộ nhớ đệm không hợp lệ.')
        part=folder/'matting'/code/f'{frame//600:05}'
        if not (part/'complete.json').is_file():raise HTTPException(404,'Đoạn xóa phông này chưa hoàn tất.')
        local=frame%600;w,h=result['identity']['size'];color={'cream':result['identity']['paper'],'black':'#000000','white':'#ffffff'}[background]
        # H.264 and FFV1 have different time bases. Exact frame trims avoid a blank
        # overlay when timestamp seeking skips the last alpha or offsets the streams.
        trim=f'trim=start_frame={local}:end_frame={local+1},setpts=PTS-STARTPTS'
        args+=['-i',str(part/'foreground.mp4'),'-i',str(part/'alpha.mkv'),'-f','lavfi','-i',f'color=c={color}:s={w}x{h}:r=30','-filter_complex',f'[0:v]{trim}[f];[1:v]{trim}[a];[f][a]alphamerge[fg];[2:v][fg]overlay=shortest=1,scale=640:640:force_original_aspect_ratio=decrease[out]','-map','[out]']
    args+=['-frames:v','1','-f','image2pipe','-c:v','png','pipe:1']
    output=subprocess.run(args,capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if output.returncode:raise ValueError('Chưa đọc được khung hình; thử một mốc gần đó.')
    return Response(output.stdout,media_type='image/png',headers={'Cache-Control':'no-store'})

@app.get('/api/projects/{project_id}/download/{kind}')
def download(project_id:str,kind:Literal['video','vi','en','project','credits']):
    project=store.read(project_id)
    result=project.get('export') or project.get('preview')
    if not result:
        raise HTTPException(404,'Chưa có bản dựng để tải.')
    folder=store.folder(project_id)
    if kind=='project':
        target=folder/'project-backup.zip'
        portable={k:v for k,v in project.items() if k!='matting'}
        store.atomic_json(folder/'project.json',portable)
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
            for p in [folder/'project.json',folder/project['source_file']]:
                archive.write(p,p.relative_to(folder))
            transcript_path=folder/'transcript.json'
            if transcript_path.exists():
                archive.write(transcript_path,'transcript.json')
            for directory in ['assets','versions','frames']:
                for p in (folder/directory).glob('*'):
                    if p.is_file():
                        archive.write(p,p.relative_to(folder))
            if project.get('music_file'):
                archive.write(folder/project['music_file'],project['music_file'])
        return FileResponse(target,filename='VietCut-project.zip')
    relative=result['file'] if kind=='video' else result['folder']+'/'+('subtitles.'+kind+'.srt' if kind in ['vi','en'] else 'credits.json')
    path=folder/relative
    if not path.exists():
        raise HTTPException(404,'Không tìm thấy bản xuất.')
    return FileResponse(path,filename=('VietCut-'+project['id']+'.mp4') if kind=='video' else path.name)

@app.post('/api/projects/import')
def import_project(file:UploadFile=File(...)):
    project_id=store.uid()
    folder=store.folder(project_id)
    temp=folder/'incoming.zip'
    with temp.open('wb') as out:
        shutil.copyfileobj(file.file,out,length=1024*1024)
    try:
        with zipfile.ZipFile(temp) as archive:
            if sum(i.file_size for i in archive.infolist())>15_000_000_000:
                raise ValueError('Dự án quá lớn.')
            for info in archive.infolist():
                target=(folder/info.filename).resolve()
                if not target.is_relative_to(folder.resolve()) or info.is_dir():
                    if info.is_dir() and target.is_relative_to(folder.resolve()):
                        continue
                    raise ValueError('Tệp dự án có đường dẫn không hợp lệ.')
                if not (info.filename in ['project.json','transcript.json'] or info.filename.startswith(('source.','music-','assets/','versions/','frames/'))):
                    raise ValueError('Tệp dự án chứa dữ liệu không hỗ trợ.')
                target.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(info) as source,target.open('wb') as dest:
                    shutil.copyfileobj(source,dest,length=1024*1024)
        project=json.loads((folder/'project.json').read_text(encoding='utf-8'))
        source=(folder/project['source_file']).resolve()
        if not source.is_relative_to(folder.resolve()) or not source.name.startswith('source.'):
            raise ValueError('Đường dẫn video nguồn không hợp lệ.')
        metadata=probe(source)
        project.update(id=project_id,metadata=metadata,status='ready',preview=None,export=None,jobs=[],frames=[],options=Options.model_validate(project['options']).model_dump())
        project.pop('matting',None)
        validate_duration(project['options'],metadata['duration'])
        if project.get('plan'):
            project['plan']=validate_plan(project['plan'],metadata['duration'])
        for asset in project.get('assets',{}).values():
            if Path(asset['file']).name!=asset['file']:
                raise ValueError('Đường dẫn ảnh không hợp lệ.')
        if project.get('music_file') and Path(project['music_file']).name!=project['music_file']:
            raise ValueError('Đường dẫn nhạc không hợp lệ.')
        store.save(project)
        store.job_create(project_id,'preview' if project.get('plan') else 'pipeline')
        return project_read(project_id)
    except (zipfile.BadZipFile,KeyError,json.JSONDecodeError):
        raise ValueError('Không đọc được dự án VietCut.')
    finally:
        temp.unlink(missing_ok=True)

if (ROOT/'dist').exists():
    app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='frontend')
