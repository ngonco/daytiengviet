"""Read-only fixed landscape thumbnail frame, shared by preview and download."""
from io import BytesIO
from PIL import Image, ImageDraw, ImageOps
from .templates import brand, draw_centered, rounded_mask
from .photo_layout import cover


def render_thumbnail(project, folder, draft=None):
    lessons = (project.get('plan') or {}).get('lessons') or []
    if not lessons:
        raise ValueError('Dự án chưa có bài học. Hãy tạo bài học trước.')
    draft = draft or {}
    lesson = next((item for item in lessons if item['id'] == draft.get('lesson_id')), None)
    if draft.get('lesson_id') and lesson is None:
        raise ValueError('Bài học không còn tồn tại. Hãy chọn lại.')
    lesson = lesson or lessons[0]
    en = draft.get('en', lesson.get('en', '')).strip()
    vi = draft.get('vi', lesson.get('vi', '')).strip()
    if not en or not vi:
        raise ValueError('Hãy nhập cả tiêu đề tiếng Anh và tiếng Việt.')
    asset_id = draft.get('asset_id', lesson.get('asset_id'))
    asset = project.get('assets', {}).get(asset_id)
    if not asset:
        raise ValueError('Hãy chọn ảnh minh hoạ có sẵn trong dự án.')
    path = (folder / 'assets' / asset['file']).resolve()
    if not path.is_relative_to((folder / 'assets').resolve()):
        raise ValueError('Ảnh minh hoạ không hợp lệ.')
    b = brand()
    image = Image.new('RGB', (1280, 720), b['pastel'])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, 1261, 701), radius=36, fill=b['card'])
    draw_centered(draw, (48, 30, 1184, 64), b['name'], 32, 24, b['ink'], True, max_lines=1)
    draw.rounded_rectangle((40, 112, 666, 674), radius=28, fill=b['pastel'])
    draw_centered(draw, (68, 140, 570, 340), en, 94, 34, b['ink'], True, max_lines=5)
    draw_centered(draw, (68, 510, 570, 132), vi, 40, 24, b['accent'], max_lines=3)
    with Image.open(path) as source:
        photo = cover(ImageOps.exif_transpose(source).convert('RGB'), (530, 562), draft.get('crop'))
    image.paste(photo, (710, 112), rounded_mask((530, 562), 28))
    output = BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()
