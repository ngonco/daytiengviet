"""Shared deterministic template geometry and typography, in export coordinates."""
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from .photo_layout import cover
from .config import ROOT

TEMPLATE_VERSION=2
FONT_DIR=ROOT/'assets/fonts'

def brand():
    return json.loads((ROOT/'assets/frame_brand.json').read_text(encoding='utf-8'))

def signature():
    paths=[ROOT/'assets/frame_brand.json',FONT_DIR/'NotoSans.ttf',FONT_DIR/'NotoSerif.ttf']
    digest=hashlib.sha256(str(TEMPLATE_VERSION).encode())
    for path in paths:
        digest.update(path.read_bytes())
    return digest.hexdigest()

def font(size,bold=False,serif=False):
    result=ImageFont.truetype(str(FONT_DIR/('NotoSerif.ttf' if serif else 'NotoSans.ttf')),max(1,round(size)))
    axes=result.get_variation_axes()
    values=[700 if axis['name']==b'Weight' and bold else 400 if axis['name']==b'Weight' else axis['default'] for axis in axes]
    result.set_variation_by_axes(values)
    return result

def geometry(w,h):
    portrait=h>w
    ref_w,ref_h=(1080,1920) if portrait else (1920,1080)
    sx,sy=w/ref_w,h/ref_h
    def rect(x,y,rw,rh):
        return tuple(round(value*scale)//2*2 for value,scale in [(x,sx),(y,sy),(rw,sx),(rh,sy)])
    return {'portrait':portrait,'speaker':rect(46,108,988,570) if portrait else rect(28,32,604,1016),
            'content':rect(46,716,988,480) if portrait else rect(686,92,1180,466),
            'photo':rect(46,1234,988,580) if portrait else rect(686,600,1180,448),
            'brand':rect(46,26,988,52) if portrait else rect(686,28,1180,42),
            'radius':round(36*min(sx,sy)),'scale':min(sx,sy)}

def lines_for(text,face,width):
    lines=[]
    for paragraph in text.split('\n'):
        current=''
        for word in paragraph.split():
            if face.getlength(word)>width:
                return None
            candidate=(current+' '+word).strip()
            if current and face.getlength(candidate)>width:
                lines.append(current);current=word
            else:
                current=candidate
        if current:
            lines.append(current)
    return lines or ['']

def fit_text(text,width,height,max_size,min_size,bold=False,serif=False,max_lines=7):
    for size in range(max(1,round(max_size)),max(1,round(min_size))-1,-1):
        face=font(size,bold,serif)
        lines=lines_for(text,face,width)
        line_height=round(size*1.32)
        if lines and len(lines)<=max_lines and len(lines)*line_height<=height:
            return face,lines,line_height
    raise ValueError('Chữ quá dài để đọc rõ trong khung. Hãy rút gọn hoặc chia mục bài học: '+text[:80])

def draw_centered(draw,rect,text,max_size,min_size,color,bold=False,serif=False,max_lines=7):
    x,y,w,h=rect
    face,lines,lh=fit_text(text,w,h,max_size,min_size,bold,serif,max_lines)
    top=y+(h-len(lines)*lh)/2
    for i,line in enumerate(lines):
        draw.text((x+w/2,top+i*lh),line,font=face,fill=color,anchor='mt',stroke_width=0)
    return len(lines)*lh

@lru_cache(maxsize=6)
def paper(w,h,theme_signature):
    b=brand()
    base=np.array(Image.new('RGB',(w,h),b['paper']),dtype=np.int16)
    noise=np.random.default_rng(41).integers(-2,3,size=(h,w,1),dtype=np.int16)
    image=Image.fromarray(np.clip(base+noise,0,255).astype(np.uint8),'RGB').convert('RGBA')
    draw=ImageDraw.Draw(image)
    draw.ellipse((-w*.2,-h*.08,w*.21,h*.11),fill='#f6df9f')
    draw.ellipse((w*.93,h*.10,w*1.13,h*.30),fill='#efa38a')
    draw.ellipse((-w*.11,h*.91,w*.22,h*1.12),fill='#217776')
    draw.ellipse((w*.90,h*.95,w*1.18,h*1.15),fill='#df795c')
    return image

def rounded_mask(size,radius):
    image=Image.new('L',size,0)
    ImageDraw.Draw(image).rounded_rectangle((0,0,size[0]-1,size[1]-1),radius=radius,fill=255)
    return image

def make_frame(project,lesson,folder,w,h,target):
    g=geometry(w,h);b=brand();s=g['scale']
    image=paper(w,h,signature()).copy();draw=ImageDraw.Draw(image)
    bx,by,bw,bh=g['brand']
    draw_centered(draw,(bx,by,bw,bh),b['name'],29*s,21*s,b['ink'],bold=True,max_lines=1)
    x,y,sw,sh=g['speaker']
    pad=max(2,round(5*s))
    draw.rounded_rectangle((x-pad,y-pad,x+sw+pad,y+sh+pad),radius=g['radius']+pad,fill='#eadfce')
    draw.rounded_rectangle((x,y,x+sw,y+sh),radius=g['radius'],fill=b['paper'])
    cx,cy,cw,ch=g['content']
    draw.rounded_rectangle((cx,cy,cx+cw,cy+ch),radius=g['radius'],fill='#fffaf0')
    inset=round(30*s);iw=cw-2*inset
    chunks=lesson.get('chunks',[])
    chip_height=round(82*s) if chunks else 0
    gap=round(16*s)
    available=ch-2*inset-chip_height-(gap if chunks else 0)
    vi_height=available*.63;en_height=available-vi_height-gap
    vi_rect=(cx+inset,cy+inset,iw,vi_height)
    en_rect=(cx+inset,cy+inset+vi_height+gap,iw,en_height)
    max_vi=(176 if g['portrait'] else 158)*s
    draw_centered(draw,vi_rect,lesson['vi'],max_vi,44*s,b['ink'],True,not g['portrait'],5)
    # A small gold brush-like rule separates the target sentence from its meaning.
    line_y=round(cy+inset+vi_height+gap*.35)
    draw.rounded_rectangle((cx+cw*.22,line_y,cx+cw*.78,line_y+max(2,round(5*s))),radius=max(1,round(3*s)),fill=b['gold'])
    draw_centered(draw,en_rect,lesson['en'],(78 if g['portrait'] else 72)*s,28*s,b['accent'],True,not g['portrait'],4)
    if chunks:
        spacing=round(12*s);chip_w=(iw-(len(chunks)-1)*spacing)/len(chunks)
        colors=['#e2ead9','#f9e6b3','#f7d6c3']
        for i,chunk in enumerate(chunks):
            xx=cx+inset+i*(chip_w+spacing);yy=cy+ch-inset-chip_height
            draw.rounded_rectangle((xx,yy,xx+chip_w,yy+chip_height),radius=round(18*s),fill=colors[i])
            draw_centered(draw,(xx+8*s,yy+6*s,chip_w-16*s,chip_height*.49),chunk['vi'],31*s,22*s,b['ink'],True,max_lines=1)
            draw_centered(draw,(xx+8*s,yy+chip_height*.53,chip_w-16*s,chip_height*.40),chunk['en'],23*s,17*s,b['ink'],max_lines=1)
    px,py,pw,ph=g['photo']
    mask=rounded_mask((pw,ph),g['radius'])
    asset=project.get('assets',{}).get(lesson.get('asset_id'))
    if asset:
        with Image.open(folder/'assets'/asset['file']) as raw:
            raw=ImageOps.exif_transpose(raw).convert('RGB')
            ratio='9:16' if g['portrait'] else '16:9'
            photo=cover(raw,(pw,ph),lesson.get('photo_crops',{}).get(ratio))
        image.paste(photo,(px,py),mask)
    else:
        fill=Image.new('RGB',(pw,ph),'#e5ecdf');pd=ImageDraw.Draw(fill)
        pd.ellipse((pw*.2,ph*.12,pw*.8,ph*.9),fill='#d4e1d1')
        draw_centered(pd,(pw*.12,ph*.25,pw*.76,ph*.5),lesson['vi'],70*s,30*s,b['ink'],True,max_lines=4)
        image.paste(fill,(px,py),mask)
    image.convert('RGB').save(target)
    return g

def validate_text_layout(project,plan):
    # Validate in export geometry before queuing expensive media work.
    from .render import dimensions
    from tempfile import TemporaryDirectory
    from pathlib import Path
    w,h=dimensions(project,False)
    with TemporaryDirectory() as temp:
        for lesson in plan.get('lessons',[]):
            # Assets are not needed for text layout validation.
            make_frame({**project,'assets':{}},lesson,Path(temp),w,h,Path(temp)/'check.png')

def speaker_focus(project,w,h):
    from statistics import median
    g=geometry(w,h);_,_,cw,ch=g['speaker']
    faces=[f['face'] for f in project.get('frames',[]) if f.get('face')]
    fx=median([f['x']+f['w']/2 for f in faces]) if faces else .5
    fy=median([f['y']+f['h']/2 for f in faces]) if faces else .32
    face_h=median([f['h'] for f in faces]) if faces else .22
    options=project['options']
    if options.get('speaker_x') is not None:fx=options['speaker_x']
    if options.get('speaker_y') is not None:fy=options['speaker_y']
    mw,mh=project['metadata']['width'],project['metadata']['height']
    cover=max(cw/mw,ch/mh)
    # Face detections exclude hair: reserve headroom above the box and subtitle space below.
    scale=min(cover,ch*.48/max(1,face_h*mh))*options.get('speaker_scale',1)
    return fx,fy,max(2,round(mw*scale)//2*2),max(2,round(mh*scale)//2*2)
