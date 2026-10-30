"""Canonical cover geometry used by both the editor API and Pillow renderer."""
import math
from .timeline import PhotoCrop


def layout(source_width,source_height,width,height,zoom=1):
    zoom=PhotoCrop(zoom=zoom).zoom
    scale=max(width/source_width,height/source_height)*zoom
    sw=max(width,math.ceil(source_width*scale));sh=max(height,math.ceil(source_height*scale))
    return {'frame_width':width,'frame_height':height,'scaled_width':sw,'scaled_height':sh,'overflow_x':sw-width,'overflow_y':sh-height}


def cover(image,size,crop=None):
    from PIL import Image
    settings=PhotoCrop.model_validate(crop or {})
    w,h=size;g=layout(*image.size,w,h,settings.zoom)
    resized=image.resize((g['scaled_width'],g['scaled_height']),Image.Resampling.LANCZOS)
    left=round(g['overflow_x']*settings.x);top=round(g['overflow_y']*settings.y)
    return resized.crop((left,top,left+w,top+h))
