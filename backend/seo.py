"""Shared download naming and MP4 discovery metadata."""
import re
import unicodedata


def lesson_title(project):
    plan = project.get('plan') or {}
    targets = list(dict.fromkeys(str(row.get('vi', '')).strip() for row in plan.get('lessons', []) if str(row.get('vi', '')).strip()))
    if len(targets) == 1:
        return targets[0][:120]
    return str(plan.get('summary') or ' · '.join(targets[:3]) or project.get('title') or 'Bài học tiếng Việt').strip()[:120]


def title(project):
    return str(project.get('title') if project.get('title_mode') == 'manual' else lesson_title(project))[:160]


def video_filename(project):
    name = unicodedata.normalize('NFC', title(project))
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip(' .')[:120].rstrip(' .') or 'Bài học tiếng Việt'
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
        name = '_' + name
    return name + ' - learn vietnamese.mp4'


def basename(project):
    text = unicodedata.normalize('NFKD', title(project).replace('đ', 'd').replace('Đ', 'D'))
    slug = re.sub(r'[^a-z0-9]+', '-', text.encode('ascii', 'ignore').decode().lower()).strip('-')[:100].rstrip('-')
    return 'vietnamese-learn-bai-hoc-' + (slug or 'tieng-viet')


def metadata_args(project):
    lesson = title(project)
    values = {'title': f'Vietnamese Learn | Bài học: {lesson}',
              'artist': 'Vietnamese with Vinh',
              'description': f'Vietnamese learn — Bài học tiếng Việt: {lesson}. Learn Vietnamese with Vietnamese with Vinh.',
              'comment': f'vietnamese learn, learn Vietnamese, bài học tiếng Việt, {lesson}',
              'genre': 'Education', 'language': 'vie'}
    return [item for key, value in values.items() for item in ('-metadata', f'{key}={value}')]
