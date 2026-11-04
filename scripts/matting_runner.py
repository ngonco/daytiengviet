"""Isolated RVM worker. No app imports, provider keys, or network during inference.

Committed 600-frame segments include recurrent tensors + optical-flow state.
Uncommitted segments are overwritten on retry. NPZ is loaded with pickle disabled.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import queue
import threading


def atomic(path, value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    for attempt in range(10):
        try:tmp.replace(path);return
        except PermissionError:
            if attempt==9:raise
            time.sleep(.01*(attempt+1))


def status():
    import torch
    return {'torch':torch.__version__,'cuda':torch.cuda.is_available(),'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}


class Pipes:
    def __init__(self): self.items=[]
    def start(self,args,read=False):
        err=tempfile.TemporaryFile()
        parent=child=None
        if sys.platform=='win32':
            # Windows' default 4KB anonymous pipe is a severe bottleneck for RGB/alpha frames.
            # Give each bounded stream a 1MB kernel buffer; no full-video RAM allocation.
            import ctypes
            from ctypes import wintypes
            import msvcrt
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreatePipe.argtypes=[ctypes.POINTER(wintypes.HANDLE),ctypes.POINTER(wintypes.HANDLE),ctypes.c_void_p,wintypes.DWORD]
            kernel.CreatePipe.restype=wintypes.BOOL
            r,w=wintypes.HANDLE(),wintypes.HANDLE()
            if not kernel.CreatePipe(ctypes.byref(r),ctypes.byref(w),None,1024*1024):raise ctypes.WinError(ctypes.get_last_error())
            reader=os.fdopen(msvcrt.open_osfhandle(r.value,os.O_RDONLY|os.O_BINARY),'rb',buffering=0)
            writer=os.fdopen(msvcrt.open_osfhandle(w.value,os.O_WRONLY|os.O_BINARY),'wb',buffering=0)
            parent,child=(reader,writer) if read else (writer,reader)
        try:
            p=subprocess.Popen(args,stdin=subprocess.DEVNULL if read else child or subprocess.PIPE,stdout=child or subprocess.PIPE if read else subprocess.DEVNULL,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except BaseException:
            if parent:parent.close()
            err.close();raise
        finally:
            if child:child.close()
        if parent:
            if read:p.stdout=parent
            else:p.stdin=parent
        self.items.append((p,err));return p
    def finish(self,p):
        if p.stdin: p.stdin.close()
        if p.wait(timeout=90):
            err=next(e for q,e in self.items if q is p);err.seek(0,2);n=err.tell();err.seek(max(0,n-1500))
            raise RuntimeError('FFmpeg: '+err.read().decode('utf-8','replace'))

    def check_decoder(self,p):
        self.finish(p)
        err=next(e for q,e in self.items if q is p)
        err.seek(0,2)
        if err.tell():
            err.seek(0)
            raise RuntimeError('Không giải mã được đầy đủ video nguồn; hãy kiểm tra hoặc chuyển mã nguồn trước khi thử lại.')
    def close(self):
        for p,e in self.items:
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.wait()
            for stream in (p.stdin,p.stdout):
                if stream:
                    try:stream.close()
                    except OSError:pass
            e.close()


def read_exact(stream,n):
    chunks=[];remaining=n
    while remaining:
        block=stream.read(remaining)
        if not block:break
        chunks.append(block);remaining-=len(block)
    data=b''.join(chunks)
    if data and len(data)!=n:raise RuntimeError('Khung hình nguồn bị thiếu dữ liệu; chưa hoàn tất xóa phông.')
    return data if len(data)==n else None


class BufferedFrames:
    """Two raw frames of read-ahead, never an unbounded whole-video buffer."""
    def __init__(self,stream,size):
        self.queue=queue.Queue(2);self.stop=threading.Event();self.ended=False
        def read():
            try:
                while not self.stop.is_set():
                    value=read_exact(stream,size)
                    if not self.send(value):return
                    if value is None:return
            except Exception as exc:self.send(exc)
        self.thread=threading.Thread(target=read,daemon=True);self.thread.start()
    def send(self,value):
        while not self.stop.is_set():
            try:self.queue.put(value,timeout=.1);return True
            except queue.Full:pass
        return False
    def next(self,cancel):
        if self.ended:return None
        while True:
            if cancel.exists():raise RuntimeError('Đã dừng; tiếp tục từ đoạn hoàn tất gần nhất.')
            try:value=self.queue.get(timeout=.1);break
            except queue.Empty:pass
        if isinstance(value,Exception):raise value
        if value is None:self.ended=True
        return value


class BufferedWriter:
    """Bounded writes overlap encoder backpressure and the next inference batch."""
    def __init__(self,stream,cancel):
        self.stream=stream;self.cancel=cancel;self.queue=queue.Queue(2);self.error=None;self.seconds=0;self.stop=threading.Event()
        def write():
            try:
                while True:
                    if self.stop.is_set():return
                    try:data=self.queue.get(timeout=.1)
                    except queue.Empty:continue
                    if data is None:return
                    started=time.perf_counter();view=memoryview(data)
                    while view:
                        n=stream.write(view[:1024*1024])
                        if not n:raise RuntimeError('Bộ mã hóa ngừng nhận khung hình.')
                        view=view[n:]
                    self.seconds+=time.perf_counter()-started
            except Exception as exc:self.error=exc
        self.thread=threading.Thread(target=write,daemon=True);self.thread.start()
    def submit(self,value):
        while True:
            if self.error:raise self.error
            if self.cancel.exists():raise RuntimeError('Đã dừng; tiếp tục từ đoạn hoàn tất gần nhất.')
            try:self.queue.put(value,timeout=.1);return
            except queue.Full:pass
    def finish(self):
        self.submit(None)
        while self.thread.is_alive():
            self.thread.join(.1)
            if self.cancel.exists():raise RuntimeError('Đã dừng; tiếp tục từ đoạn hoàn tất gần nhất.')
        if self.error:raise self.error


def source_video_end(request):
    """Read video timing separately from the authoritative project/container duration."""
    probe=request.get('ffprobe','ffprobe')
    result=subprocess.run([probe,'-v','error','-show_streams','-show_format','-of','json',request['source']],capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('Không đọc được thời gian luồng hình của video nguồn.')
    data=json.loads(result.stdout)
    stream=next(s for s in data['streams'] if s['codec_type']=='video')
    try:
        end=float(stream['duration'])+float(stream.get('start_time',0))-float(data['format'].get('start_time',0))
        return end if math.isfinite(end) and end>0 else None
    except (KeyError,ValueError,TypeError):return None


def validate_eof(frame,total,video_end,last_frame):
    # A clean decoder must reach the declared video end. Only verified audio/container
    # tail and <=one CFR rounding frame can be filled; interior loss is never hidden.
    minimum=math.floor(video_end*30)-1 if video_end is not None else total-2
    if last_frame is None or frame<minimum:
        raise RuntimeError('Luồng hình kết thúc sớm bất thường; video có thể bị hỏng. Tiến độ đã được giữ.')


def infer_group(model,src,rec,ratio,device,torch):
    """Initialize once, then retain recurrence even when a four-frame group hits OOM."""
    try:
        if rec[0] is None:
            fgr,alpha,*next_rec=model(src[:,0],*rec,ratio);fgr=fgr.unsqueeze(1);alpha=alpha.unsqueeze(1)
        else:fgr,alpha,*next_rec=model(src,*rec,ratio)
        return fgr,alpha,next_rec,False
    except RuntimeError as exc:
        if device!='cuda' or 'out of memory' not in str(exc).lower():raise
        n=src.shape[1]
        if n==1:raise RuntimeError('GPU hết bộ nhớ; đóng ứng dụng GPU khác rồi thử lại.') from None
        torch.cuda.empty_cache();out_f=[];out_a=[];next_rec=rec
        for k in range(n):
            try:fg,al,*next_rec=model(src[:,k],*next_rec,ratio)
            except RuntimeError as error:
                if 'out of memory' in str(error).lower():raise RuntimeError('GPU hết bộ nhớ ngay cả khi xử lý từng hình; đóng ứng dụng GPU khác rồi thử lại.') from None
                raise
            out_f.append(fg.unsqueeze(1));out_a.append(al.unsqueeze(1))
        return torch.cat(out_f,1),torch.cat(out_a,1),next_rec,True


class Corrections:
    def __init__(self,config,w,h):
        self.cfg=config;self.w=w;self.h=h;self.active={};self.previous=None;self.warnings=[]
    def restore(self,folder):
        import numpy as np
        saved=json.loads((folder/'tracking.json').read_text(encoding='utf-8'))
        self.active={k:{**v,'points':np.array(v['points'],dtype=np.float32)} for k,v in saved['active'].items()}
        self.warnings=saved['warnings']
        with np.load(folder/'state.npz',allow_pickle=False) as state:
            self.previous=state['gray'] if state['gray'].size else None
    def save(self,folder):
        atomic(folder/'tracking.json',{'active':{k:{**v,'points':v['points'].tolist()} for k,v in self.active.items()},'warnings':self.warnings})
    def apply(self,source,fgr,alpha,frame):
        import cv2
        import numpy as np
        # Tracking at <=640px is sufficient for small gestures; forward/backward consistency gates all propagation.
        tw=max(32,round(self.w*min(1,640/max(self.w,self.h))));th=max(32,round(self.h*tw/self.w))
        gray=cv2.resize(cv2.cvtColor(source,cv2.COLOR_RGB2GRAY),(tw,th)) if self.cfg['strokes'] else None
        for stroke in self.cfg['strokes']:
            first=round(stroke['start']*30);last=math.ceil(stroke['end']*30)
            if frame<first or frame>=last:
                self.active.pop(stroke['id'],None);continue
            if frame==first:
                self.active[stroke['id']]={'points':np.array([[p['x']*(tw-1),p['y']*(th-1)] for p in stroke['points']],np.float32).reshape(-1,1,2),'valid':True}
            elif stroke['id'] in self.active and self.active[stroke['id']]['valid'] and self.previous is not None:
                item=self.active[stroke['id']];p=item['points']
                q,ok,err=cv2.calcOpticalFlowPyrLK(self.previous,gray,p,None,winSize=(25,25),maxLevel=3)
                back,back_ok,_=cv2.calcOpticalFlowPyrLK(gray,self.previous,q,None,winSize=(25,25),maxLevel=3)
                good=(ok[:,0]>0)&(back_ok[:,0]>0)&(np.linalg.norm(back-p,axis=2)[:,0]<1.8)&(err[:,0]<35)
                good &= (q[:,0,0]>=0)&(q[:,0,0]<tw)&(q[:,0,1]>=0)&(q[:,0,1]<th)
                hist_a=cv2.calcHist([self.previous],[0],None,[32],[0,256]);hist_b=cv2.calcHist([gray],[0],None,[32],[0,256])
                cv2.normalize(hist_a,hist_a);cv2.normalize(hist_b,hist_b)
                scene=float(np.mean(cv2.absdiff(self.previous,gray)))>45 and cv2.compareHist(hist_a,hist_b,cv2.HISTCMP_BHATTACHARYYA)>.5
                if good.mean()<.8 or scene:
                    item['valid']=False
                    self.warnings.append({'stroke':stroke['id'],'time':frame/30,'message':'Theo dõi vùng sửa không còn chắc chắn; hãy đánh dấu lại từ mốc này.'})
                else:item['points']=q
            item=self.active.get(stroke['id'])
            if not item or not item['valid']:continue
            points=item['points'].reshape(-1,2)*np.array([self.w/tw,self.h/th]);points=np.round(points).astype(np.int32)
            mask=np.zeros((self.h,self.w),np.uint8);radius=max(1,round(stroke['radius']*min(self.w,self.h)))
            for a,b in zip(points[:-1],points[1:]):cv2.line(mask,tuple(a),tuple(b),255,radius*2,cv2.LINE_AA)
            for p in points:cv2.circle(mask,tuple(p),radius,255,-1,cv2.LINE_AA)
            mask=cv2.GaussianBlur(mask,(0,0),max(.5,radius*.12)).astype(np.float32)/255
            if stroke['mode']=='keep':
                alpha=np.maximum(alpha,mask)
                fgr=fgr*(1-mask[:,:,None])+source.astype(np.float32)/255*mask[:,:,None]
            else:alpha=np.minimum(alpha,1-mask)
        self.previous=gray
        contract=self.cfg['contract']
        if contract:
            r=max(1,round(abs(contract)));kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(r*2+1,r*2+1))
            alpha=cv2.erode(alpha,kernel) if contract>0 else cv2.dilate(alpha,kernel)
        if self.cfg['soften']>0:alpha=cv2.GaussianBlur(alpha,(0,0),self.cfg['soften'])
        return fgr,np.clip(alpha,0,1)


def process(request):
    import numpy as np
    import torch
    torch.set_num_threads(2)
    folder=Path(request['folder']);cancel=folder/'cancel';cancel.unlink(missing_ok=True)
    if hashlib.sha256(Path(request['model']).read_bytes()).hexdigest()!=request['model_sha256']:
        raise RuntimeError('Mã kiểm tra mô hình không khớp. Chạy lại bộ cài xóa phông.')
    device=request['config']['device'];dtype=torch.float16 if device=='cuda' else torch.float32
    if device=='cuda' and not torch.cuda.is_available():raise RuntimeError('GPU không sẵn sàng; không tự chuyển sang CPU.')
    started=time.perf_counter();model=torch.jit.load(request['model'],map_location=device).eval()
    model=torch.jit.freeze(model)
    if device=='cuda':torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize()
    load_seconds=time.perf_counter()-started
    w,h=request['size'];total=math.ceil(request['duration']*30);count=math.ceil(total/600);rec=[None]*4
    video_end=source_video_end(request)
    tracker=Corrections(request['config'],w,h)
    # Only a contiguous prefix of verified completion records can be resumed.
    index=0;prior=[]
    while index<count:
        part=folder/f'{index:05}'
        if not all((part/n).is_file() for n in ['complete.json','foreground.mp4','alpha.mkv','composition.mp4','state.npz','tracking.json']):break
        entry=json.loads((part/'complete.json').read_text())
        if entry.get('frames')!=min(600,total-index*600):break
        prior.append(entry);index+=1
    resumed=min(total,index*600)
    if index:
        part=folder/f'{index-1:05}'
        with np.load(part/'state.npz',allow_pickle=False) as saved:
            rec=[torch.from_numpy(saved[f'r{i}']).to(device=device,dtype=dtype) for i in range(4)]
        tracker.restore(part)
    frame=resumed;batch_size=4 if device=='cuda' else 1;ratio=min(1,512/max(w,h));pipes=Pipes()
    base=[request['ffmpeg'],'-hide_banner','-loglevel','error','-y','-threads','2','-filter_threads','1','-filter_complex_threads','1']
    encoder='libx264'
    if device=='cuda':
        # NVENC avoids making two CPU encoders the bottleneck on the standing-talk profile.
        test=subprocess.run([*base,'-f','lavfi','-i','color=s=192x192:r=30','-frames:v','1','-c:v','h264_nvenc','-profile:v','high444p','-pix_fmt','yuv444p','-f','null','-'],capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if test.returncode==0:encoder='h264_nvenc'
    color_codec=['-c:v','h264_nvenc','-preset','p4','-rc','constqp','-qp','16'] if encoder=='h264_nvenc' else ['-c:v','libx264','-preset','veryfast','-crf','16','-threads','2']
    comp_codec=['-c:v','h264_nvenc','-preset','p4','-rc','constqp','-qp','18'] if encoder=='h264_nvenc' else ['-c:v','libx264','-preset','veryfast','-crf','18','-threads','2']
    work_start=time.perf_counter();infer_seconds=0;entries=prior[:];reader=None;writers=[];last_frame=None;decoder_checked=False
    timings={'read_decode_wait_seconds':0,'upload_seconds':0,'download_seconds':0,'corrections_seconds':0,'compose_pack_seconds':0,'encode_write_seconds':0,'encoder_finish_seconds':0}
    last_progress=0;paper=np.array([int(request['paper'][i:i+2],16) for i in (1,3,5)],np.float32)/255
    try:
        if index<count:
            # Normalize from source zero BEFORE trimming; seek+fps resets can drop or
            # repeat a frame when resuming a VFR source at a segment boundary.
            decoder=pipes.start([*base,'-xerror','-err_detect','explode','-i',request['source'],'-an','-vf',f'fps=30:start_time=0,scale={w}:{h},trim=start_frame={frame}','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],read=True)
            reader=BufferedFrames(decoder.stdout,w*h*3)
        for segment in range(index,count):
            part=folder/f'{segment:05}';part.mkdir(exist_ok=True);segment_frames=min(600,total-frame);chunk_start=time.perf_counter()
            (part/'complete.json').unlink(missing_ok=True)
            raw=[*base,'-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}','-r','30','-i','pipe:0','-an']
            fgr_pipe=pipes.start([*raw,*color_codec,'-profile:v','high444p' if encoder=='h264_nvenc' else 'high444','-pix_fmt','yuv444p',str(part/'foreground.mp4')])
            alpha_pipe=pipes.start([*base,'-f','rawvideo','-pix_fmt','gray','-s',f'{w}x{h}','-r','30','-i','pipe:0','-an','-c:v','ffv1','-level','3','-threads','2','-pix_fmt','gray',str(part/'alpha.mkv')])
            comp_pipe=pipes.start([*raw,*comp_codec,'-pix_fmt','yuv420p',str(part/'composition.mp4')])
            writers=[BufferedWriter(p.stdin,cancel) for p in [fgr_pipe,alpha_pipe,comp_pipe]]
            done=0
            while done<segment_frames:
                if cancel.exists():raise RuntimeError('Đã dừng; tiếp tục từ đoạn hoàn tất gần nhất.')
                # Official v1 TorchScript requires a 4D first frame to initialize recurrent tensors.
                n=min(batch_size if rec[0] is not None else 1,segment_frames-done);images=[]
                for _ in range(n):
                    t=time.perf_counter();data=reader.next(cancel);timings['read_decode_wait_seconds']+=time.perf_counter()-t
                    if data is None:
                        if not decoder_checked:
                            pipes.check_decoder(decoder);decoder_checked=True
                            validate_eof(frame+len(images),total,video_end,last_frame)
                        data=last_frame
                    last_frame=data;images.append(np.frombuffer(data,np.uint8).reshape(h,w,3))
                t=time.perf_counter()
                src=torch.from_numpy(np.stack(images)).permute(0,3,1,2).unsqueeze(0).to(device=device,dtype=dtype).div_(255)
                if device=='cuda':torch.cuda.synchronize()
                timings['upload_seconds']+=time.perf_counter()-t
                t=time.perf_counter()
                with torch.inference_mode():
                    fgr,alpha,next_rec,fallback=infer_group(model,src,rec,ratio,device,torch)
                    if fallback:batch_size=1
                    rec=next_rec
                    if device=='cuda':torch.cuda.synchronize()
                infer_seconds+=time.perf_counter()-t
                t=time.perf_counter()
                gpu_pack=device=='cuda' and not request['config']['strokes']
                if gpu_pack:
                    # Edge corrections only need alpha. Keep full-resolution RGB on
                    # GPU, compose/quantize there, then transfer compact byte images.
                    alpha_cpu=alpha[0,:,0].float().cpu().numpy()
                    fgr_cpu=None
                else:
                    fgr_cpu=fgr[0].permute(0,2,3,1).contiguous().float().cpu().numpy()
                    alpha_cpu=alpha[0,:,0].float().cpu().numpy()
                timings['download_seconds']+=time.perf_counter()-t
                corrected=[];corrected_fg=[]
                for k in range(n):
                    t=time.perf_counter()
                    fg,al=tracker.apply(images[k],None if gpu_pack else fgr_cpu[k],alpha_cpu[k],frame+k)
                    corrected.append(al)
                    if not gpu_pack:corrected_fg.append(fg)
                    timings['corrections_seconds']+=time.perf_counter()-t
                t=time.perf_counter()
                if gpu_pack:
                    al_np=np.stack(corrected)
                    al_gpu=torch.from_numpy(al_np).to(device=device).unsqueeze(-1)
                    fg_gpu=fgr[0].permute(0,2,3,1).float()
                    paper_gpu=torch.as_tensor(paper,device=device)
                    fg_bytes=fg_gpu.clamp(0,1).mul(255).to(torch.uint8).contiguous().cpu().numpy()
                    comp_bytes=(fg_gpu*al_gpu+paper_gpu*(1-al_gpu)).clamp_(0,1).mul_(255).to(torch.uint8).contiguous().cpu().numpy()
                    alpha_bytes=(al_np*255).astype(np.uint8)
                else:
                    fg_np=np.stack(corrected_fg);al_np=np.stack(corrected)
                    fg_bytes=(np.clip(fg_np,0,1)*255).astype(np.uint8)
                    alpha_bytes=(al_np*255).astype(np.uint8)
                    comp_bytes=(np.clip(fg_np*al_np[:,:,:,None]+paper*(1-al_np[:,:,:,None]),0,1)*255).astype(np.uint8)
                timings['compose_pack_seconds']+=time.perf_counter()-t
                for k in range(n):
                    buffers=[fg_bytes[k].tobytes(),alpha_bytes[k].tobytes(),comp_bytes[k].tobytes()]
                    for writer,data in zip(writers,buffers):writer.submit(data)
                    frame+=1;done+=1
                elapsed=time.perf_counter()-work_start
                if time.perf_counter()-last_progress>=.5:
                    try:atomic(folder/'progress.json',{'frame':frame,'total':total,'fps':(frame-resumed)/max(.01,elapsed)})
                    except PermissionError:pass  # Progress is advisory; durable segment commits are mandatory.
                    last_progress=time.perf_counter()
            t=time.perf_counter()
            if frame==total and not decoder_checked:
                while reader.next(cancel) is not None:pass
                pipes.check_decoder(decoder);decoder_checked=True
            for writer in writers:writer.finish()
            for p in [fgr_pipe,alpha_pipe,comp_pipe]:pipes.finish(p)
            timings['encoder_finish_seconds']+=time.perf_counter()-t
            timings['encode_write_seconds']+=sum(writer.seconds for writer in writers)
            tensors={f'r{i}':r.detach().cpu().numpy() for i,r in enumerate(rec)}
            tensors['gray']=tracker.previous if tracker.previous is not None else np.array([],np.uint8)
            np.savez_compressed(part/'state.npz',**tensors);tracker.save(part)
            entry={'frames':segment_frames,'seconds':time.perf_counter()-chunk_start,'peak_gpu_mb':torch.cuda.max_memory_allocated()/1024**2 if device=='cuda' else 0,'model_load_seconds':load_seconds,'paper':request['paper'],'composition_version':1}
            atomic(part/'complete.json',entry);entries.append(entry)
        if reader and not decoder_checked:
            # Drain/check even if metadata ended before the decoder. Never commit a
            # final successful stats file for an FFmpeg decoding failure.
            while reader.next(cancel) is not None:pass
            pipes.check_decoder(decoder)
        seconds=time.perf_counter()-work_start
        segment_seconds=sum(e['seconds'] for e in entries)
        stats={'device':device,'encoder':encoder,'gpu':torch.cuda.get_device_name(0) if device=='cuda' else None,'model_load_seconds':load_seconds,'first_model_load_seconds':entries[0]['model_load_seconds'],'processing_seconds_this_run':seconds,'inference_seconds_this_run':infer_seconds,'resumed_frames':resumed,'processed_frames_this_run':total-resumed,'total_frames':total,'fps_this_run':(total-resumed)/max(seconds,.001),'segment_processing_seconds':segment_seconds,'full_video_fps':total/max(.001,segment_seconds),'peak_gpu_mb':max(e['peak_gpu_mb'] for e in entries),'peak_gpu_reserved_mb':torch.cuda.max_memory_reserved()/1024**2 if device=='cuda' else 0,'batch_size':batch_size,'size':[w,h],'network_max':512,'warnings':tracker.warnings}
        stats['timings']=timings;stats['video_end']=video_end
        atomic(folder/'stats.json',stats)
    finally:
        if reader:reader.stop.set()
        for writer in writers:writer.stop.set()
        pipes.close()


if __name__=='__main__':
    if sys.argv[1]=='--status':print(json.dumps(status()))
    else:process(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
