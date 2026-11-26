from .audio import AUDIO_VERSION, voice_filter
from .seo import metadata_args, title
import hashlib
import json
import math
from PIL import Image,ImageDraw
from .timeline import keep_spans,map_interval,assembly_spans,lesson_photo_sequence
from .media import ffmpeg
from .store import atomic_json
from .templates import geometry,signature,make_frame,make_lesson_layers,make_photo_tile,rounded_mask,speaker_transform,speaker_filter,font,fit_text,subtitle_region,subtitle_position

LESSON_RENDER_VERSION=11

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

def subtitle_image(caption,w,h,target=None,options=None):
    g=geometry(w,h,options);_,_,sw,sh=subtitle_region(w,h,options);s=g['scale']
    width=sw-round(40*s);padding=max(4,round(12*s))
    max_height=sh*(.95 if g.get('circle') and not g['portrait'] else .34)
    vi_font,vi_lines,vi_lh=fit_text(caption['vi'],width-2*padding,max_height*.53-2*padding,32*s,24*s,True,max_lines=2)
    en_text=caption.get('en','')
    if en_text:
        en_font,en_lines,en_lh=fit_text(en_text,width-2*padding,max_height*.47-padding,26*s,20*s,max_lines=2)
    else:
        en_lines=[];en_lh=0;en_font=font(20*s)
    height=round(len(vi_lines)*vi_lh+len(en_lines)*en_lh+padding*2+4*s)
    image=Image.new('RGBA',(width,height),(0,0,0,0));draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((0,0,width-1,height-1),radius=max(4,round(18*s)),fill=(22,50,71,218))
    y=padding
    for line in vi_lines:
        draw.text((width/2,y),line,font=vi_font,fill='white',anchor='mt');y+=vi_lh
    y+=round(4*s)
    for line in en_lines:
        draw.text((width/2,y),line,font=en_font,fill='#F2F7FB',anchor='mt');y+=en_lh
    if target is None:return image
    image.save(target)
    return width,height

def render_lessons(project,plan,transcript,context,preview=True):
    from .render import dimensions,write_srt,sound_effects,RENDER_VERSION
    from .templates import validate_text_layout
    if not plan.get('lessons'):
        raise ValueError('Dự án cần có ít nhất một mục bài học. Hãy chọn Chuyển sang khung bài học.')
    folder=context.folder;w,h=dimensions(project,preview);g=geometry(w,h,project['options'])
    spans=assembly_spans(project['metadata']['duration'],plan['cuts'],plan.get('pauses',[]));duration=spans[-1]['output_end']
    used={l.get('asset_id') for l in plan['lessons'] if l.get('asset_id')}
    hashes={key:hashlib.sha256((folder/'assets'/asset['file']).read_bytes()).hexdigest() for key,asset in project.get('assets',{}).items() if key in used}
    theme=signature();focus=speaker_transform(project,w,h)
    identity={'audio_version':AUDIO_VERSION,'seo_title':title(project),'renderer':RENDER_VERSION,'lesson_renderer':LESSON_RENDER_VERSION,'plan':plan,'options':project['options'],'assets':hashes,'template':theme,'preview':preview,'focus':focus,'music':project.get('music_file'),'matting':project.get('matting',{}).get('code') if project['options'].get('background_removal',{}).get('enabled') else None}
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
    animate=bool(project['options'].get('animate_media'))
    photo_interval=max(3.0,min(12.0,float(project['options'].get('photo_interval',5.0))))
    page_paths={};layer_paths={};photo_slots=[]
    px,py,pw,ph=g['photo']
    if not animate:
        for lesson in lessons:
            key=digest({'lesson':{k:lesson.get(k) for k in ['vi','en','chunks','asset_id','photo_crops']},'asset':hashes.get(lesson.get('asset_id')),'size':[w,h],'geometry':g,'theme':theme})
            path=tile_dir/(key+'.png')
            if not path.exists():make_frame(project,lesson,folder,w,h,path)
            page_paths[lesson['id']]=path
    else:
        for lesson in lessons:
            lkey=digest({'v':LESSON_RENDER_VERSION,'lesson':{k:lesson.get(k) for k in ['vi','en','chunks']},'size':[w,h],'geometry':g,'theme':theme})
            paths={'base':tile_dir/(lkey+'-base.png'),'vi':tile_dir/(lkey+'-vi.png'),'en':tile_dir/(lkey+'-en.png'),'chunks':tile_dir/(lkey+'-chunks.png')}
            if not paths['base'].exists() or not paths['vi'].exists() or not paths['en'].exists():
                layers=make_lesson_layers(project,lesson,folder,w,h)
                layers['base'].save(paths['base'])
                layers['vi'].save(paths['vi'])
                layers['en'].save(paths['en'])
                if layers['chunks'] is not None:layers['chunks'].save(paths['chunks'])
            layer_paths[lesson['id']]={k:v for k,v in paths.items() if v.exists()}
            seq=lesson_photo_sequence(lesson,project.get('assets')) or [None]
            t_cur=lesson['output_start'];idx=0
            while t_cur<lesson['output_end']-0.001:
                t_nxt=min(lesson['output_end'],t_cur+photo_interval)
                aid=seq[idx%len(seq)]
                pkey=digest({'size':[pw,ph],'crops':lesson.get('photo_crops'),'asset':hashes.get(aid),'vi':'' if aid else lesson.get('vi','')})
                ppath=tile_dir/(pkey+'-kb.png')
                if not ppath.exists():make_photo_tile(project,lesson,aid,folder,pw,ph,1.12).save(ppath)
                photo_slots.append({'lesson_id':lesson['id'],'start':t_cur,'end':t_nxt,'path':ppath,'kb':idx%4})
                t_cur=t_nxt;idx+=1
    sx,sy,cw,ch=g['speaker'];mask_path=tile_dir/f'mask-{cw}-{ch}-{g.get("speaker_radius",g["radius"])}.png'
    if not mask_path.exists():rounded_mask((cw,ch),g.get('speaker_radius',g['radius'])).save(mask_path)
    source=folder/project.get('render_source_file',project['source_file'])
    # Bound decoder/filter fan-in when aggressive cuts create many short spans.
    chunk_seconds=5 if len(spans)>20 else 20
    count=math.ceil(duration/chunk_seconds);chunks=[]
    for index in range(count):
        context.progress((78 if context.kind in ['pipeline','revise','reframe'] else 2)+(18 if context.kind in ['pipeline','revise','reframe'] else 90)*index/count,f"{'Dựng khung bài học' if preview else 'Xuất khung bài học'} · đoạn {index+1}/{count}")
        context.check();start=index*chunk_seconds;end=min(duration,start+chunk_seconds);length=end-start
        local_lessons=[l for l in lessons if l['output_end']>start and l['output_start']<end]
        local_captions=[c for c in captions if c['output_end']>start and c['output_start']<end]
        pieces=[]
        for span in spans:
            a,b=max(start,span['output_start']),min(end,span['output_end'])
            if b>a+.001:pieces.append({'start':span['start'] if span.get('kind')=='pause' else span['start']+a-span['output_start'],'duration':b-a,'pause':span.get('kind')=='pause'})
        chunk_key=digest({'v':LESSON_RENDER_VERSION,'renderer':RENDER_VERSION,'theme':theme,'size':[w,h],'geometry':g,'pieces':pieces,'lessons':local_lessons,'captions':local_captions,'assets':hashes,'focus':focus,'start':start,'matting':identity['matting']})
        cache=folder/'render-cache'/chunk_key;cache.mkdir(parents=True,exist_ok=True)
        chunk=cache/'chunk.mkv';chunks.append(chunk)
        if chunk.exists() and (cache/'complete.json').exists():continue
        args=[];filters=[]
        for i,piece in enumerate(pieces):
            if piece.get('pause'):
                args+=['-ss',piece['start'],'-t',1/30,'-i',source]
                filters.append(f'[{i}:v]setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration={piece["duration"]},trim=duration={piece["duration"]},setsar=1,format=yuv420p[v{i}]')
                filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={piece["duration"]},asetpts=PTS-STARTPTS[a{i}]')
            else:
                args+=['-ss',piece['start'],'-t',piece['duration'],'-i',source]
                filters.append(f'[{i}:v]setpts=PTS-STARTPTS,fps=30,setsar=1,format=yuv420p[v{i}]')
                filters.append(f'[{i}:a]atrim=duration={piece["duration"]},asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,afade=t=in:d=0.008,afade=t=out:st={max(0,piece["duration"]-.008)}:d=0.008[a{i}]')
        filters.append(''.join(f'[v{i}][a{i}]' for i in range(len(pieces)))+f'concat=n={len(pieces)}:v=1:a=1[raw][audio]')
        filters.append('[raw]'+speaker_filter(project,w,h)+'[actor]')
        next_input=len(pieces)
        page_labels=[]
        if not animate:
            for j,lesson in enumerate(local_lessons):
                args+=['-loop','1','-framerate','30','-i',page_paths[lesson['id']]]
                a=max(0,lesson['output_start']-start)
                if j==0:
                    filters.append(f'[{next_input}:v]format=rgba[page0]')
                else:
                    filters.append(f'[{next_input}:v]format=rgba,fade=t=in:st={a}:d=0.15:alpha=1[pagein{j}]')
                    filters.append(f"[page{j-1}][pagein{j}]overlay=0:0:enable='gte(t,{a})'[page{j}]")
                page_labels.append(f'page{j}');next_input+=1
        else:
            local_slots=[s for s in photo_slots if s['end']>start and s['start']<end]
            filters.append(f'color=c=0xF7F3EB:s={pw}x{ph}:r=30:d={length},format=rgba[phbase]')
            ph_cur='phbase'
            for k,slot in enumerate(local_slots):
                sa=max(0,slot['start']-start);sb=min(end,slot['end'])-start
                sdur=max(1/30,sb-sa);fn=max(2,math.ceil(sdur*30)+1)
                args+=['-i',slot['path']]
                kb=slot['kb']
                if kb==0:zp=f"z='1+0.10*on/{fn}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                elif kb==1:zp=f"z='1.10-0.10*on/{fn}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                elif kb==2:zp=f"z='1.08':x='(iw-iw/zoom)*on/{fn}':y='ih/2-(ih/zoom/2)'"
                else:zp=f"z='1.08':x='(iw-iw/zoom)*(1-on/{fn})':y='ih/2-(ih/zoom/2)'"
                fade_expr=f',fade=t=in:st={sa}:d=0.4:alpha=1' if k>0 else ''
                filters.append(f"[{next_input}:v]zoompan={zp}:d={fn}:s={pw}x{ph}:fps=30,setpts=PTS-STARTPTS+{sa}/TB,format=rgba{fade_expr}[phclip{k}]")
                filters.append(f"[{ph_cur}][phclip{k}]overlay=0:0:enable='gte(t,{sa})'[ph{k}]")
                ph_cur=f'ph{k}';next_input+=1
            filters.append(f'color=c=0xF7F3EB:s={w}x{h}:r=30:d={length},format=rgba[bg0]')
            filters.append(f'[bg0][{ph_cur}]overlay={px}:{py}[bgph]')
            args+=['-loop','1','-framerate','30','-i',layer_paths[local_lessons[0]['id']]['base']]
            filters.append(f'[bgph][{next_input}:v]overlay=0:0[pagebase]')
            next_input+=1;cur_page='pagebase'
            slide_px=max(8,round(18*g['scale']))
            for j,lesson in enumerate(local_lessons):
                lp=layer_paths[lesson['id']]
                la=lesson['output_start']-start;lb=min(end,lesson['output_end'])-start
                en_expr=f"gte(t,{max(0,la)})*lt(t,{lb})"
                for idx_l,(lname,delay) in enumerate([('vi',0.0),('en',0.14),('chunks',0.28)]):
                    if lname not in lp:continue
                    args+=['-loop','1','-framerate','30','-i',lp[lname]]
                    if la>=0:
                        st=la+delay
                        filters.append(f"[{next_input}:v]format=rgba,fade=t=in:st={st}:d=0.28:alpha=1[txt_{j}_{idx_l}]")
                        filters.append(f"[{cur_page}][txt_{j}_{idx_l}]overlay=x=0:y='round({slide_px}*(1-min(1,max(0,(t-{st})/0.28))))':enable='{en_expr}'[pg_{j}_{idx_l}]")
                    else:
                        filters.append(f"[{cur_page}][{next_input}:v]overlay=0:0:enable='{en_expr}'[pg_{j}_{idx_l}]")
                    cur_page=f'pg_{j}_{idx_l}';next_input+=1
            page_labels.append(cur_page)
        args+=['-loop','1','-framerate','30','-i',mask_path]
        filters+=[f'[{next_input}:v]format=gray[mask]','[actor][mask]alphamerge[speaker]',f'[{page_labels[-1]}][speaker]overlay={sx}:{sy}:eof_action=pass[composed]']
        next_input+=1;current='composed'
        for j,caption in enumerate(local_captions):
            key=digest({'vi':caption['vi'],'en':caption['en'],'size':[w,h],'geometry':g,'theme':theme})
            path=tile_dir/(key+'-sub.png')
            if not path.exists():subtitle_image(caption,w,h,path,project['options'])
            with Image.open(path) as im:tw,th=im.size
            args+=['-loop','1','-framerate','30','-i',path]
            a=max(0,caption['output_start']-start);b=min(end,caption['output_end'])-start
            subx,suby=subtitle_position(w,h,tw,th,project['options'])
            if not animate:
                filters.append(f"[{current}][{next_input}:v]overlay={subx}:{suby}:enable='gte(t,{a})*lt(t,{b})'[sub{j}]")
            else:
                sub_slide=max(4,round(8*g['scale']))
                out_st=max(a,b-0.12)
                filters.append(f"[{next_input}:v]format=rgba,fade=t=in:st={a}:d=0.15:alpha=1,fade=t=out:st={out_st}:d=0.12:alpha=1[subin{j}]")
                filters.append(f"[{current}][subin{j}]overlay=x={subx}:y='{suby}+round({sub_slide}*(1-min(1,max(0,(t-{a})/0.15))))':enable='gte(t,{a})*lt(t,{b})'[sub{j}]")
            current=f'sub{j}';next_input+=1
        ffmpeg(['-filter_complex_threads','1',*args,'-filter_complex',';'.join(filters),'-map',f'[{current}]','-map','[audio]','-t',length,'-c:v','libx264','-preset','veryfast' if preview else 'fast','-crf','25' if preview else '20','-pix_fmt','yuv420p','-c:a','pcm_s16le','-ar','48000',chunk],context)
        atomic_json(cache/'complete.json',{'duration':length})
    context.progress(96,'Ghép khung bài học và cân âm lượng')
    concat=render_dir/'concat.txt'
    concat.write_text('\n'.join("file '"+str(p.resolve()).replace('\\','/').replace("'","'\\''")+"'" for p in chunks),encoding='utf-8')
    args=['-f','concat','-safe','0','-i',concat]
    voice,audio_details=voice_filter(args,context,project['options'].get('auto_volume',True),render_dir/'voice-level.json')
    af=[f'[0:a]{voice}[voice]'];mix=['voice'];n=1
    if project.get('music_file'):
        args+=['-stream_loop','-1','-i',folder/project['music_file']]
        af[0]=f'[0:a]{voice},asplit=2[voice][sidechain]'
        af += [f'[{n}:a]volume=0.16,aresample=48000[music]','[music][sidechain]sidechaincompress=threshold=0.025:ratio=10:attack=20:release=250[duck]'];mix.append('duck');n+=1
    if project['options'].get('sfx',True):
        sfx=render_dir/'effects.wav';sound_effects(sfx,duration,[l['output_start'] for l in lessons[1:]])
        args+=['-i',sfx];af.append(f'[{n}:a]volume=0.35[fx]');mix.append('fx')
    af.append(''.join('['+label+']' for label in mix)+f'amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.89:level=false'+''.join(f",volume=0:enable='gte(t,{s['output_start']})*lt(t,{s['output_end']})'" for s in spans if s.get('kind')=='pause')+'[aout]')
    temp=render_dir/'assembling.mp4'
    ffmpeg([*args,'-filter_complex',';'.join(af),'-map','0:v:0','-map','[aout]','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',duration,*metadata_args(project),'-movflags','+faststart',temp],context)
    temp.replace(result);write_srt(project,plan,render_dir)
    atomic_json(render_dir/'edit-plan.json',{'plan':plan,'options':project['options'],'source_file':project['source_file'],'time_map':spans})
    atomic_json(render_dir/'credits.json',[{'photographer':a.get('photographer','Bạn cung cấp'),'url':a.get('url',''),'photographer_url':a.get('photographer_url','')} for key,a in project.get('assets',{}).items() if key in used])
    details={'audio':audio_details,'file':result.relative_to(folder).as_posix(),'folder':render_dir.relative_to(folder).as_posix(),'width':w,'height':h,'duration':duration,'revision':project['revision'],'digest':code,'preview':preview,'renderer_version':RENDER_VERSION,'lesson_renderer_version':LESSON_RENDER_VERSION,'template_signature':theme,'layout_mode':'lesson'}
    atomic_json(manifest,details)
    return details
