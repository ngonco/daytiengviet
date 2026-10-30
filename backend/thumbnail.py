"""Read-only, brand-synchronized landscape lesson thumbnails."""
from io import BytesIO
from PIL import Image, ImageDraw, ImageOps
from .templates import brand, draw_centered, rounded_mask


def render_thumbnail(project, folder):
    lessons = (project.get('plan') or {}).get('lessons') or []
    if not lessons:
        raise ValueError('Cần có bài học trước khi xuất thumbnail.')
    # Prefer an illustrated target that remains readable at small sizes.
    assets = project.get('assets', {})
    lesson = min(lessons, key=lambda item: (not bool(assets.get(item.get('asset_id'))), len(item.get('vi', ''))))
    b = brand()
    image = Image.new('RGB', (1280, 720), b['paper'])
    draw = ImageDraw.Draw(image)
    draw_centered(draw, (48, 24, 1184, 56), b['name'], 30, 24, b['ink'], True, max_lines=1)
    draw.rounded_rectangle((36, 108, 674, 672), radius=32, fill=b['card'])
    draw_centered(draw, (64, 132, 582, 64), 'HỌC TIẾNG VIỆT', 30, 24, b['accent'], True, max_lines=1)
    draw_centered(draw, (68, 216, 570, 300), lesson.get('vi', ''), 92, 28, b['ink'], True, max_lines=6)
    draw_centered(draw, (68, 540, 570, 100), lesson.get('en', ''), 36, 20, b['accent'], max_lines=3)
    asset = assets.get(lesson.get('asset_id'))
    if asset:
        path = (folder / 'assets' / asset['file']).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise ValueError('Ảnh minh hoạ không hợp lệ.')
        with Image.open(path) as source:
            photo = ImageOps.fit(ImageOps.exif_transpose(source).convert('RGB'), (530, 564))
        image.paste(photo, (710, 108), rounded_mask((530, 564), 32))
    else:
        draw.rounded_rectangle((710, 108, 1240, 672), radius=32, fill=b['pastel'])
        draw_centered(draw, (750, 220, 450, 320), lesson.get('vi', ''), 64, 24, b['ink'], True)
    output = BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()
