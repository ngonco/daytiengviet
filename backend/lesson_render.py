import hashlib
import json
import math
from PIL import Image,ImageDraw
from .timeline import keep_spans,map_interval
from .media import ffmpeg
from .store import atomic_json
from .templates import geometry,signature,make_frame,rounded_mask,speaker_focus,font,fit_text

LESSON_RENDER_VERSION=3

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:24]

def mapped_lessons(plan,spans):
    result=[]
    for lesson in plan['lessons']:
        for a,b in map_interval(lesson['start'],lesson['end'],spans):
            if result and result[-1]['id']==lesson['id'] and abs(result[-1]['output_end']-a)<.005:
                result[-1]['output_end']=b
            else:
                result.append({**lesson,'output_start':a,'output_end':b})
    return result

def subtitle_image(caption,w,h,target):
    g=geometry(w,h);_,_,sw,sh=g['speaker'];s=g['scale']
    width=sw-round(40*s);padding=max(4,round(12*s))
    max_height=sh*.34
    vi_font,vi_lines,vi_lh=fit_text(caption['vi'],width-2*padding,max_height*.53-2*padding,32*s,24*s,True,max_lines=2)
    en_text=caption.get('en','')
    if en_text:
        en_font,en_lines,en_lh=fit_text(en_text,width-2*padding,max_height*.47-padding,26*s,20*s,max_lines=2)
    else:
        en_lines=[];en_lh=0;en_font=font(20*s)
    height=round(len(vi_lines)*vi_lh+len(en_lines)*en_lh+padding*2+4*s)
    image=Image.new('RGBA',(width,height),(0,0,0,0));draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((0,0,width-1,height-1),radius=max(4,round(18*s)),fill=(20,27,25,185))
    y=padding
    for line in vi_lines:
        draw.text((width/2,y),line,font=vi_font,fill='white',anchor='mt');y+=vi_lh
    y+=round(4*s)
    for line in en_lines:
        draw.text((width/2,y),line,font=en_font,fill='#f4f2ed',anchor='mt');y+=en_lh
    image.save(target)
    return width,height

def render_lessons(project,plan,transcript,context,preview=True):
    from .render import dimensions,write_srt,sound_effects,RENDER_VERSION
    from .templates import validate_text_layout
    if not plan.get('lessons'):
        raise ValueError('Dự án cần có ít nhất một mục bài học. Hãy chọn Chuyển sang khung bài học.')
    folder=context.folder;w,h=dimensions(project,preview);g=geometry(w,h)
    spans=keep_spans(project['metadata']['duration'],plan['cuts']);duration=spans[-1]['output_end']
    used={l.get('asset_id') for l in plan['lessons'] if l.get('asset_id')}
    hashes={key:hashlib.sha256((folder/'assets'/asset['file']).read_bytes()).hexdigest() for key,asset in project.get('assets',{}).items() if key in used}
    theme=signature();focus=speaker_focus(project,w,h)
    identity={'renderer':RENDER_VERSION,'lesson_renderer':LESSON_RENDER_VERSION,'plan':plan,'options':project['options'],'assets':hashes,'template':theme,'preview':preview,'focus':focus,'music':project.get('music_file'),'matting':project.get('matting',{}).get('code') if project['options'].get('background_removal',{}).get('enabled') else None}
    code=digest(identity);render_dir=folder/'renders'/code;render_dir.mkdir(parents=True,exist_ok=True)
    result=render_dir/('preview.mp4' if preview else 'final.mp4');manifest=render_dir/'manifest.json'
    if result.exists() and manifest.exists():return {**json.loads(manifest.read_text(encoding='utf-8')),'revision':project['revision']}
    validate_text_layout(project,plan)
    lessons=mapped_lessons(plan,spans)
    captions=[]
    if project['options'].get('subtitles','bilingual')!='off':
        for caption in plan['captions']:
            item={**caption,'en':caption.get('en','') if project['options'].get('subtitles')=='bilingual' else ''}
            for a,b in map_interval(caption['start'],caption['end'],spans):
                if caption['vi'].strip():captions.append({**item,'output_start':a,'output_end':b})
    tile_dir=folder/'lesson-tiles';tile_dir.mkdir(exist_ok=True)
    page_paths={}
    for lesson in lessons:
        key=digest({'lesson':{k:lesson.get(k) for k in ['vi','en','chunks','asset_id']},'asset':hashes.get(lesson.get('asset_id')),'size':[w,h],'theme':theme})
        path=tile_dir/(key+'.png')
        if not path.exists():make_frame(project,lesson,folder,w,h,path)
        page_paths[lesson['id']]=path
    sx,sy,cw,ch=g['speaker'];mask_path=tile_dir/f'mask-{cw}-{ch}-{g["radius"]}.png'
    if not mask_path.exists():rounded_mask((cw,ch),g['radius']).save(mask_path)
    source=folder/project.get('render_source_file',project['source_file']);count=math.ceil(duration/20);chunks=[]
    for index in range(count):
        context.progress((78 if context.kind in ['pipeline','revise','reframe'] else 2)+(18 if context.kind in ['pipeline','revise','reframe'] else 90)*index/count,f"{'Dựng khung bài học' if preview else 'Xuất khung bài học'} · đoạn {index+1}/{count}")
        context.check();start=index*20;end=min(duration,start+20);length=end-start
        local_lessons=[l for l in lessons if l['output_end']>start and l['output_start']<end]
        local_captions=[c for c in captions if c['output_end']>start and c['output_start']<end]
        pieces=[]
        for span in spans:
            a,b=max(start,span['output_start']),min(end,span['output_end'])
            if b>a+.001:pieces.append({'start':span['start']+a-span['output_start'],'duration':b-a})
        chunk_key=digest({'v':LESSON_RENDER_VERSION,'renderer':RENDER_VERSION,'theme':theme,'size':[w,h],'pieces':pieces,'lessons':local_lessons,'captions':local_captions,'assets':hashes,'focus':focus,'start':start,'matting':identity['matting']})
        cache=folder/'render-cache'/chunk_key;cache.mkdir(parents=True,exist_ok=True)
        chunk=cache/'chunk.mkv';chunks.append(chunk)
        if chunk.exists() and (cache/'complete.json').exists():continue
        args=[];filters=[]
        for i,piece in enumerate(pieces):
            args+=['-ss',piece['start'],'-t',piece['duration'],'-i',source]
            filters.append(f'[{i}:v]setpts=PTS-STARTPTS,fps=30,setsar=1,format=yuv420p[v{i}]')
            filters.append(f'[{i}:a]atrim=duration={piece["duration"]},asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,afade=t=in:d=0.008,afade=t=out:st={max(0,piece["duration"]-.008)}:d=0.008[a{i}]')
        filters.append(''.join(f'[v{i}][a{i}]' for i in range(len(pieces)))+f'concat=n={len(pieces)}:v=1:a=1[raw][audio]')
        fx,fy,fw,fh=focus
        bw=max(2,cw//6//2*2);bh=max(2,ch//6//2*2)
        filters+=['[raw]split=2[bg][fg]',f'[bg]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},gblur=sigma=4,scale={cw}:{ch}[blur]',
                  f"[fg]scale={fw}:{fh},format=rgba,crop={min(fw,cw)}:{min(fh,ch)}:x='min(max(iw*{fx}-ow*.5,0),iw-ow)':y='min(max(ih*{fy}-oh*.42,0),ih-oh)',pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2:color=black@0[front]",
                  '[blur][front]overlay=0:0,format=rgba[actor]']
        next_input=len(pieces)
        page_labels=[]
        for j,lesson in enumerate(local_lessons):
            args+=['-loop','1','-framerate','30','-i',page_paths[lesson['id']]]
            a=max(0,lesson['output_start']-start)
            if j==0:
                filters.append(f'[{next_input}:v]format=rgba[page0]')
            else:
                filters.append(f'[{next_input}:v]format=rgba,fade=t=in:st={a}:d=0.15:alpha=1[pagein{j}]')
                filters.append(f"[page{j-1}][pagein{j}]overlay=0:0:enable='gte(t,{a})'[page{j}]")
            page_labels.append(f'page{j}');next_input+=1
        args+=['-loop','1','-framerate','30','-i',mask_path]
        filters+=[f'[{next_input}:v]format=gray[mask]','[actor][mask]alphamerge[speaker]',f'[{page_labels[-1]}][speaker]overlay={sx}:{sy}:eof_action=pass[composed]']
        next_input+=1;current='composed'
        for j,caption in enumerate(local_captions):
            key=digest({'vi':caption['vi'],'en':caption['en'],'size':[w,h],'theme':theme})
            path=tile_dir/(key+'-sub.png')
            if not path.exists():subtitle_image(caption,w,h,path)
            with Image.open(path) as im:tw,th=im.size
            args+=['-loop','1','-framerate','30','-i',path]
            a=max(0,caption['output_start']-start);b=min(end,caption['output_end'])-start
            filters.append(f"[{current}][{next_input}:v]overlay={sx+(cw-tw)//2}:{sy+ch-th-round(20*g['scale'])}:enable='gte(t,{a})*lt(t,{b})'[sub{j}]")
            current=f'sub{j}';next_input+=1
        ffmpeg(['-filter_complex_threads','1',*args,'-filter_complex',';'.join(filters),'-map',f'[{current}]','-map','[audio]','-t',length,'-c:v','libx264','-preset','veryfast' if preview else 'fast','-crf','25' if preview else '20','-pix_fmt','yuv420p','-c:a','pcm_s16le','-ar','48000',chunk],context)
        atomic_json(cache/'complete.json',{'duration':length})
    context.progress(96,'Ghép khung bài học và cân âm lượng')
    concat=render_dir/'concat.txt'
    concat.write_text('\n'.join("file '"+str(p.resolve()).replace('\\','/').replace("'","'\\''")+"'" for p in chunks),encoding='utf-8')
    args=['-f','concat','-safe','0','-i',concat]
    af=['[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[voice]'];mix=['voice'];n=1
    if project.get('music_file'):
        args+=['-stream_loop','-1','-i',folder/project['music_file']]
        af[0]='[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,asplit=2[voice][sidechain]'
        af += [f'[{n}:a]volume=0.16,aresample=48000[music]','[music][sidechain]sidechaincompress=threshold=0.025:ratio=10:attack=20:release=250[duck]'];mix.append('duck');n+=1
    if project['options'].get('sfx',True):
        sfx=render_dir/'effects.wav';sound_effects(sfx,duration,[l['output_start'] for l in lessons[1:]])
        args+=['-i',sfx];af.append(f'[{n}:a]volume=0.35[fx]');mix.append('fx')
    af.append(''.join('['+label+']' for label in mix)+f'amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.89:level=false[aout]')
    temp=render_dir/'assembling.mp4'
    ffmpeg([*args,'-filter_complex',';'.join(af),'-map','0:v:0','-map','[aout]','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',duration,'-movflags','+faststart',temp],context)
    temp.replace(result);write_srt(project,plan,render_dir)
    atomic_json(render_dir/'edit-plan.json',{'plan':plan,'options':project['options'],'source_file':project['source_file'],'time_map':spans})
    atomic_json(render_dir/'credits.json',[{'photographer':a.get('photographer','Bạn cung cấp'),'url':a.get('url',''),'photographer_url':a.get('photographer_url','')} for key,a in project.get('assets',{}).items() if key in used])
    details={'file':result.relative_to(folder).as_posix(),'folder':render_dir.relative_to(folder).as_posix(),'width':w,'height':h,'duration':duration,'revision':project['revision'],'digest':code,'preview':preview,'renderer_version':RENDER_VERSION,'lesson_renderer_version':LESSON_RENDER_VERSION,'template_signature':theme,'layout_mode':'lesson'}
    atomic_json(manifest,details)
    return details
