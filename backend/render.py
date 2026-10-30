import hashlib
import json
import math
import re
import shutil
import struct
import wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
from .media import ffmpeg, font_path
from .store import atomic_json
from .timeline import keep_spans, map_interval

RENDER_VERSION = 7

def dimensions(project, preview=False):
    ratio = project['options']['ratio']
    if ratio == '9:16':
        w, h = 1080, 1920
    elif ratio == '16:9':
        w, h = 1920, 1080
    else:
        w, h = project['metadata']['width'], project['metadata']['height']
    if preview:
        scale = min(1, 540 / min(w, h), 960 / max(w, h))
        w, h = round(w*scale), round(h*scale)
    return max(2, w//2*2), max(2, h//2*2)

def wrap_text(text, font, width, max_lines=2):
    lines, current = [], ''
    for word in text.split():
        candidate = (current + ' ' + word).strip()
        if current and font.getlength(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and font.getlength(lines[-1] + '…') > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += '…'
    return lines

def ass_time(seconds):
    cs = max(0, round(seconds*100))
    return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'

def srt_time(seconds):
    ms = max(0, round(seconds*1000))
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'

def escape_ass(text):
    return text.replace('\\', '／').replace('{', '(').replace('}', ')').replace('\r', '').replace('\n', r'\N')

def mapped_captions(project, plan):
    spans = keep_spans(project['metadata']['duration'], plan['cuts'])
    return [{**c, 'output_start': a, 'output_end': b} for c in plan['captions'] for a,b in map_interval(c['start'],c['end'],spans)]

def write_srt(project, plan, folder):
    captions = mapped_captions(project, plan)
    for language in ['vi','en']:
        body = '\n\n'.join(f"{i+1}\n{srt_time(c['output_start'])} --> {srt_time(c['output_end'])}\n{c[language]}" for i,c in enumerate(captions) if c.get(language))
        (folder / f'subtitles.{language}.srt').write_text(body+'\n', encoding='utf-8-sig')

def write_ass(project, plan, transcript, spans, start, end, w, h, path):
    portrait = h > w
    size = max(17, round(w*0.054 if portrait else h*0.049))
    en_size = round(size*0.70)
    name = 'Arial'
    vi_font, en_font = ImageFont.truetype(str(font_path(True)),size), ImageFont.truetype(str(font_path()),en_size)
    header = f'''[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: VI,{name},{size},&H005FF2DE,&H00FFFFFF,&H00201611,&H99000000,-1,0,0,0,100,100,0,0,1,{max(1,round(size*.075))},1,8,20,20,20,1
Style: EN,{name},{en_size},&H00FFFFFF,&H00FFFFFF,&H00201611,&H99000000,0,0,0,0,100,100,0,0,1,1.5,1,8,20,20,20,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    events = []
    subtitle_mode = project['options'].get('subtitles','bilingual')
    if subtitle_mode == 'off':
        path.write_text(header,encoding='utf-8-sig')
        return
    for caption in plan['captions']:
        for a,b in map_interval(caption['start'],caption['end'],spans):
            left,right = max(a,start),min(b,end)
            if right <= left:
                continue
            vi_lines = wrap_text(caption['vi'],vi_font,w*.88)
            vi_text = escape_ass('\n'.join(vi_lines))
            # Highlight original words only when transcript text has not been edited.
            words = [word for word in transcript.get('words',[]) if word['start'] >= caption['start']-.02 and word['start'] < caption['end']-.01]
            if words and caption['vi'] == caption.get('original_vi') and len(vi_lines) == 1 and abs(left-a)<.01:
                pieces, previous = [], left
                for word in words:
                    mapped = map_interval(word['start'],word['end'],spans)
                    if not mapped:
                        continue
                    wa,wb = mapped[0]
                    if wb <= left or wa >= right:
                        continue
                    if wa > previous+.01:
                        pieces.append(r'{\k'+str(max(0,round((wa-previous)*100)))+'}')
                    pieces.append(r'{\kf'+str(max(1,round((min(wb,right)-max(wa,left))*100)))+'}'+escape_ass(word['word'])+' ')
                    previous = wb
                if pieces:
                    vi_text=''.join(pieces).strip()
            y = round(h*.77 if portrait else h*.79)
            position = r'{\an8\pos('+str(w//2)+','+str(y)+r')\fad(70,70)}'
            events.append(f'Dialogue: 0,{ass_time(left-start)},{ass_time(right-start)},VI,,0,0,0,,{position}{vi_text}')
            if subtitle_mode == 'bilingual' and caption.get('en'):
                en_text=escape_ass('\n'.join(wrap_text(caption['en'],en_font,w*.88)))
                en_y=y+round(len(vi_lines)*size*1.2)+round(size*.25)
                position_en=r'{\an8\pos('+str(w//2)+','+str(en_y)+r')\fad(70,70)}'
                events.append(f'Dialogue: 0,{ass_time(left-start)},{ass_time(right-start)},EN,,0,0,0,,{position_en}{en_text}')
    path.write_text(header+'\n'.join(events)+'\n',encoding='utf-8-sig')

def card_image(project, visual, folder, w, h, target):
    portrait = h > w
    full = visual['kind']=='photo' and visual['layout']=='full'
    if full:
        cw,ch = w,h
    else:
        cw=round((w*.78 if portrait else w*.32)*visual.get('scale',1))
        cw=min(cw,round(w*.9))
        ch=round(cw*(.58 if visual['kind']=='photo' else .45))
        ch=min(ch,round(h*.34))
    image=Image.new('RGBA',(cw,ch),(0,0,0,0))
    draw=ImageDraw.Draw(image)
    radius=max(12,round(cw*.045))
    draw.rounded_rectangle((0,0,cw-1,ch-1),radius=radius,fill=(15,30,26,247),outline=(129,173,151,180),width=max(1,cw//220))
    asset=project.get('assets',{}).get(visual.get('asset_id'))
    if visual['kind']=='photo' and asset:
        with Image.open(folder/'assets'/asset['file']) as raw:
            raw=ImageOps.exif_transpose(raw).convert('RGB')
            photo=ImageOps.fit(raw,(cw,ch),method=Image.Resampling.LANCZOS)
            if full and abs(math.log((raw.width/raw.height)/(cw/ch)))>.25:
                # Preserve all people in a landscape photograph used in a portrait lesson.
                photo=photo.filter(ImageFilter.GaussianBlur(max(8,cw*.025)))
                foreground=ImageOps.contain(raw,(cw,ch),method=Image.Resampling.LANCZOS)
                photo.paste(foreground,((cw-foreground.width)//2,(ch-foreground.height)//2))
        mask=Image.new('L',(cw,ch),0)
        ImageDraw.Draw(mask).rounded_rectangle((0,0,cw-1,ch-1),radius=0 if full else radius,fill=255)
        image.paste(photo,(0,0),mask)
        draw=ImageDraw.Draw(image)
        # A dark strip makes the teaching label readable over any photograph.
        strip_h=round(ch*.3) if not full else round(h*.14)
        overlay=Image.new('RGBA',(cw,strip_h),(10,21,18,205))
        strip_y=round(h*.06) if full else ch-strip_h
        image.alpha_composite(overlay,(0,strip_y))
        size=max(15,round(cw*.065)) if not full else max(22,round(w*.05))
        font=ImageFont.truetype(str(font_path(True)),size)
        lines=wrap_text(visual.get('text') or visual.get('query',''),font,cw*.9,1)
        draw.text((cw*.05,strip_y+strip_h*.2),' '.join(lines),font=font,fill='#ffffff')
    else:
        size=max(18,round(cw*.085))
        font=ImageFont.truetype(str(font_path(True)),size)
        small=ImageFont.truetype(str(font_path()),max(13,round(size*.58)))
        label='TỪ VỰNG' if visual['kind']=='vocab' else 'GHI NHỚ'
        label_font=ImageFont.truetype(str(font_path(True)),max(10,round(size*.36)))
        draw.text((cw*.07,ch*.09),label,font=label_font,fill='#8fd4b2')
        text=visual.get('text') or visual.get('query') or 'Tiếng Việt'
        lines=wrap_text(text,font,cw*.86,2)
        y=ch*.27
        for line in lines:
            draw.text((cw*.07,y),line,font=font,fill='#f4eee1')
            y+=size*1.18
        translated=wrap_text(visual.get('translation',''),small,cw*.86,1)
        if translated:
            draw.text((cw*.07,min(y+size*.18,ch-small.size*1.6)),translated[0],font=small,fill='#b9c5bc')
    image.save(target)
    if full:
        return cw,ch,0,0
    x=round((w-cw)/2 if portrait else w*.65)
    y=round(h*.53 if portrait else h*.30)
    if portrait:
        # Avoid the mapped face region when a teacher leans into the card area.
        for frame in project.get('frames',[]):
            if abs(frame['time']-visual['start'])<20 and frame.get('face'):
                face=frame['face']
                source_ratio=project['metadata']['width']/project['metadata']['height']
                fit_h=min(h,w/source_ratio)
                face_bottom=(h-fit_h)/2+(face['y']+face['h'])*fit_h
                if face_bottom+10>y:
                    # A side card is preferable to covering a face or the subtitles.
                    if face_bottom+ch<h*.75:
                        y=round(face_bottom+10)
                break
    if visual.get('x') is not None:
        x=round(visual['x']*w)
    if visual.get('y') is not None:
        y=round(visual['y']*h)
    return cw,ch,max(0,min(x,w-cw)),max(0,min(y,round(h*.75)-ch))

def sound_effects(path,duration,events):
    rate=16000
    events=sorted(round(e*rate) for e in events)
    with wave.open(str(path),'wb') as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(rate)
        for start in range(0,math.ceil(duration*rate),rate):
            length=min(rate,math.ceil(duration*rate)-start)
            samples=[0.0]*length
            for event in events:
                a,b=max(start,event),min(start+length,event+round(.14*rate))
                for position in range(a,b):
                    t=(position-event)/rate
                    envelope=math.exp(-t*35)*min(1,t/.006)
                    samples[position-start]+=.13*envelope*math.sin(2*math.pi*(790*t-850*t*t))
            out.writeframesraw(b''.join(struct.pack('<h',round(max(-.8,min(.8,v))*32767)) for v in samples))

def render(project, plan, transcript, context, preview=True):
    if project['options'].get('layout_mode','legacy')=='lesson':
        from .lesson_render import render_lessons
        return render_lessons(project,plan,transcript,context,preview)
    folder=context.folder
    w,h=dimensions(project,preview)
    spans=keep_spans(project['metadata']['duration'],plan['cuts'])
    duration=spans[-1]['output_end']
    if duration<.1:
        raise ValueError('Không có đoạn giữ lại để dựng')
    # Every render has an immutable identity. A failed new render never overwrites a good one.
    identity={'renderer':RENDER_VERSION,'plan':plan,'options':project['options'],'assets':project.get('assets',{}),'preview':preview,'source':project['source_file'],'music':project.get('music_file')}
    digest=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:18]
    render_dir=folder/'renders'/digest
    render_dir.mkdir(parents=True,exist_ok=True)
    result=render_dir/('preview.mp4' if preview else 'final.mp4')
    manifest=render_dir/'manifest.json'
    if manifest.exists() and result.exists():
        return json.loads(manifest.read_text(encoding='utf-8'))
    source=folder/project['source_file']
    chunk_size=20
    count=math.ceil(duration/chunk_size)
    mapped_visuals=[{**v,'output_start':a,'output_end':b} for v in plan['visuals'] if v['enabled'] for a,b in map_interval(v['start'],v['end'],spans)]
    chunks=[]
    for index in range(count):
        context.progress((78 if preview and context.kind in ['pipeline','revise'] else 2)+(18 if preview and context.kind in ['pipeline','revise'] else 90)*index/count,f"{'Dựng bản nháp' if preview else 'Xuất video'} · đoạn {index+1}/{count}")
        context.check()
        start,end=index*chunk_size,min(duration,(index+1)*chunk_size)
        chunk_duration=end-start
        # Localized plan inputs make later edits invalidate only affected chunks.
        local_captions=[c for c in plan['captions'] if any(b>start and a<end for a,b in map_interval(c['start'],c['end'],spans))]
        local_visuals=[v for v in mapped_visuals if v['output_end']>start and v['output_start']<end]
        pieces=[]
        for span in spans:
            a,b=max(start,span['output_start']),min(end,span['output_end'])
            if b>a+.001:
                pieces.append({'start':span['start']+a-span['output_start'],'duration':b-a})
        chunk_hash=hashlib.sha256(json.dumps({'v':RENDER_VERSION,'size':[w,h],'pieces':pieces,'captions':local_captions,'visuals':local_visuals,'options':project['options'],'start':start},sort_keys=True).encode()).hexdigest()[:24]
        cache_dir=folder/'render-cache'/chunk_hash
        cache_dir.mkdir(parents=True,exist_ok=True)
        chunk=cache_dir/'chunk.mkv'
        chunks.append(chunk)
        if (cache_dir/'complete.json').exists() and chunk.exists():
            continue
        ass=cache_dir/'captions.ass'
        local_plan={**plan,'captions':local_captions}
        write_ass(project,local_plan,transcript,spans,start,end,w,h,ass)
        args=[]
        for piece in pieces:
            args+=['-ss',piece['start'],'-t',piece['duration'],'-i',source]
        filters=[]
        energetic=project['options']['style']=='energetic'
        fit=project['options'].get('fit','contain')
        focus_x=project['options'].get('focus_x',.5)
        for i,piece in enumerate(pieces):
            if fit=='cover':
                filters.append(f'[{i}:v]setpts=PTS-STARTPTS,scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}:x=(iw-ow)*{focus_x}:y=(ih-oh)/2,setsar=1,fps=30,format=yuv420p[v{i}]')
            else:
                filters.append(f'[{i}:v]setpts=PTS-STARTPTS,split=2[bg{i}][fg{i}]')
                filters.append(f'[bg{i}]scale={max(2,w//8//2*2)}:{max(2,h//8//2*2)}:force_original_aspect_ratio=increase,crop={max(2,w//8//2*2)}:{max(2,h//8//2*2)},boxblur=8:2,scale={w}:{h},setsar=1[b{i}]')
                filters.append(f'[fg{i}]scale={w}:{h}:force_original_aspect_ratio=decrease,setsar=1[f{i}]')
                filters.append(f'[b{i}][f{i}]overlay=(W-w)/2:(H-h)/2,fps=30,format=yuv420p[v{i}]')
            fade=max(0,piece['duration']-.008)
            filters.append(f'[{i}:a]atrim=duration={piece["duration"]},asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,afade=t=in:d=0.008,afade=t=out:st={fade}:d=0.008[a{i}]')
        filters.append(''.join(f'[v{i}][a{i}]' for i in range(len(pieces)))+f'concat=n={len(pieces)}:v=1:a=1[base][audio]')
        current='base'
        # Gentle movement on the teacher, below the amount that would hide gestures.
        if energetic and project['options'].get('zoom',True):
            filters.append(f"[{current}]scale={round(w*1.04)//2*2}:{round(h*1.04)//2*2},crop={w}:{h}:x='(iw-ow)/2+sin(t*.35)*{w*.005}':y=(ih-oh)/2[teacher]")
            current='teacher'
        for j,visual in enumerate(local_visuals):
            tile=cache_dir/f'card{j}.png'
            cw,ch,x,y=card_image(project,visual,folder,w,h,tile)
            input_index=len(pieces)+j
            args+=['-loop','1','-framerate','30','-i',tile]
            a,b=max(visual['output_start'],start)-start,min(visual['output_end'],end)-start
            name=f'ov{j}'
            tile_input=f'[{input_index}:v]'
            if energetic and visual['kind']=='photo' and cw>100 and ch>100:
                filters.append(f"{tile_input}zoompan=z='min(1.05,1+max(0,on-{a*30:.3f})*0.00035)':d=1:s={cw}x{ch}:fps=30,format=rgba[photo{j}]")
                tile_input=f'[photo{j}]'
            filters.append(f'{tile_input}format=rgba,fade=t=in:st={a:.4f}:d=0.12:alpha=1,fade=t=out:st={max(a,b-.12):.4f}:d=0.12:alpha=1[fade{j}]')
            tile_input=f'[fade{j}]'
            filters.append(f"[{current}]{tile_input}overlay=x={x}:y={y}:enable='gte(t,{a:.4f})*lt(t,{b:.4f})':eof_action=repeat[{name}]")
            current=name
        # Relative paths keep libass safe from Windows drive-colon escaping issues.
        filters.append(f'[{current}]subtitles=filename=captions.ass[outv]')
        ffmpeg(['-filter_complex_threads','1',*args,'-filter_complex',';'.join(filters),'-map','[outv]','-map','[audio]','-t',chunk_duration,'-c:v','libx264','-preset','veryfast' if preview else 'fast','-crf','25' if preview else '20','-pix_fmt','yuv420p','-c:a','pcm_s16le','-ar','48000',chunk],context,cwd=cache_dir)
        atomic_json(cache_dir/'complete.json',{'duration':chunk_duration})
    context.progress(96,'Ghép video và cân âm lượng')
    concat=render_dir/'concat.txt'
    concat.write_text('\n'.join("file '"+str(p.resolve()).replace('\\','/').replace("'", "'\\''")+"'" for p in chunks),encoding='utf-8')
    args=['-f','concat','-safe','0','-i',concat]
    audio_filters=['[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[voice]']
    mix=['voice']
    next_input=1
    music=project.get('music_file')
    if music:
        args+=['-stream_loop','-1','-i',folder/music]
        audio_filters[0]='[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,asplit=2[voice][sidechain]'
        audio_filters+=[f'[{next_input}:a]volume=0.16,aresample=48000[music]', '[music][sidechain]sidechaincompress=threshold=0.025:ratio=10:attack=20:release=250[duck]']
        mix.append('duck'); next_input+=1
    if project['options'].get('sfx',True):
        sfx=render_dir/'effects.wav'
        events=sorted({round(v['output_start'],2) for v in mapped_visuals})
        sound_effects(sfx,duration,events)
        args+=['-i',sfx]
        audio_filters.append(f'[{next_input}:a]volume=0.45[fx]')
        mix.append('fx')
    audio_filters.append(''.join('['+label+']' for label in mix)+f'amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.89:level=false[aout]')
    temp=render_dir/'assembling.mp4'
    ffmpeg([*args,'-filter_complex',';'.join(audio_filters),'-map','0:v:0','-map','[aout]','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',duration,'-movflags','+faststart',temp],context)
    temp.replace(result)
    write_srt(project,plan,render_dir)
    atomic_json(render_dir/'edit-plan.json',{'plan':plan,'options':project['options'],'source_file':project['source_file'],'time_map':spans})
    used_assets={v.get('asset_id') for v in plan['visuals'] if v['enabled']}
    credits=[{'photographer':a.get('photographer','Bạn cung cấp'),'url':a.get('url',''),'photographer_url':a.get('photographer_url','')} for asset_id,a in project.get('assets',{}).items() if asset_id in used_assets]
    atomic_json(render_dir/'credits.json',credits)
    details={'file':str(result.relative_to(folder)).replace('\\','/'),'folder':str(render_dir.relative_to(folder)).replace('\\','/'),'width':w,'height':h,'duration':duration,'revision':project['revision'],'digest':digest,'preview':preview,'renderer_version':RENDER_VERSION}
    atomic_json(manifest,details)
    return details
