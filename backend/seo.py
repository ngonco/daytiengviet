"""Shared download naming and MP4 discovery metadata."""
import re
import unicodedata


TITLE_LIMIT = 60


def _clean(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', str(text or ''))).strip()


def _topic(text, summary=False):
    text = _clean(text).strip(' .!?;')
    # Reject explanatory prose instead of truncating it mid-word.
    if not text or len(text) > TITLE_LIMIT or len(text.split()) > 10:
        return ''
    if summary and re.search(r'[.!?;]|\b(?:người dạy|người học|đọc mẫu|nhắc lại|nói theo|hướng dẫn|bài học luyện|bài học giới thiệu)\b', text, re.I):
        return ''
    return text


def lesson_title(project):
    plan = project.get('plan') or {}
    targets = list(dict.fromkeys(_clean(row.get('vi')) for row in plan.get('lessons', []) if _clean(row.get('vi'))))
    if len(targets) == 1 and _topic(targets[0]):
        return _topic(targets[0])
    summary = _topic(plan.get('summary'), summary=True)
    if summary:
        return summary
    candidates = [value for value in targets if _topic(value)]
    if not candidates:
        candidates = [_clean(row.get('vi')) for lesson in plan.get('lessons', []) for row in lesson.get('chunks', [])]
        candidates += [_clean(row.get('vi')) for row in plan.get('glossary', [])]
    chosen = []
    for value in dict.fromkeys(candidates):
        value = _topic(value)
        if value and len(chosen) < 3 and len(' · '.join([*chosen, value])) <= TITLE_LIMIT:
            chosen.append(value)
    if chosen:
        return ' · '.join(chosen)
    if targets:
        return 'Luyện câu tiếng Việt'
    return _topic(project.get('title')) or 'Bài học tiếng Việt'


def repaired_title(project):
    """Repair generated names only; explicit manual titles stay user-owned."""
    if not project.get('plan') or project.get('title_mode') == 'manual' or project.get('diagnostic') or project.get('_retention', {}).get('state', 'active') != 'active':
        return None
    old = _clean(project.get('title'))
    plan = project['plan']
    generated = [_clean(plan.get('summary'))[:120]]
    generated += [_clean(row.get('vi'))[:120] for row in plan.get('lessons', [])]
    # A legacy title without ownership is repaired only if it matches the old
    # generator's long output. Length alone cannot identify an automatic name.
    if project.get('title_mode') != 'auto' and not (len(old) > TITLE_LIMIT and old in generated):
        return None
    new = lesson_title(project)
    return new if new != project.get('title') else None


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
