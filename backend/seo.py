"""Shared download naming and MP4 discovery metadata."""
import re
import unicodedata


def title(project):
    return str(project.get('title') or (project.get('plan') or {}).get('summary') or 'Bài học tiếng Việt')[:160]


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
