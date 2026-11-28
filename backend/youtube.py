"""YouTube Studio Camoufox browser automation, human-like interaction, 1/day scheduling, and duplicate memory."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import random
import re
import threading
import time
from . import store

UPLOAD_HOOK = None
_BROWSER_LOCK = threading.Lock()
_MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def parse_studio_dates(texts):
    """Extract YYYY-MM-DD dates from English/Vietnamese YouTube Studio schedule labels."""
    found = set()
    for raw in texts or []:
        text = str(raw or '')
        for m in re.finditer(r'\b(20\d{2})-(\d{1,2})-(\d{1,2})\b', text):
            try:
                found.add(date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat())
            except ValueError:
                pass
        for m in re.finditer(r'\b([A-Za-z]{3})\s+(\d{1,2}),\s*(20\d{2})\b', text):
            month = _MONTHS.get(m.group(1).lower())
            if month:
                try:
                    found.add(date(int(m.group(3)), month, int(m.group(2))).isoformat())
                except ValueError:
                    pass
        for m in re.finditer(r'\b(\d{1,2})\s+thg\s+(\d{1,2}),?\s*(20\d{2})\b', text, re.I):
            try:
                found.add(date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat())
            except ValueError:
                pass
        for m in re.finditer(r'\b(\d{1,2})/(\d{1,2})/(20\d{2})\b', text):
            try:
                found.add(date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat())
            except ValueError:
                pass
    return found


def build_youtube_metadata(project):
    """Build YouTube title ('Learn vietnamese: <lesson> #learnvietnamese') and lesson description."""
    from .seo import title as seo_title
    plan = project.get('plan') or {}
    lessons = plan.get('lessons') or []
    opts = project.get('options') or {}
    meta = project.get('metadata') or {}
    is_short = opts.get('ratio') == '9:16' or (opts.get('ratio') == 'original' and meta.get('height', 0) > meta.get('width', 0))
    prefix = 'Learn vietnamese: '
    tags = '#learnvietnamese #shorts' if is_short else '#learnvietnamese'
    budget = 100 - len(prefix) - len(tags) - 1
    en_targets = []
    for item in lessons:
        val = re.sub(r'\s+', ' ', str(item.get('en') or '')).strip()
        if val and val not in en_targets:
            en_targets.append(val)
    if en_targets:
        chosen = en_targets[0]
        for nxt in en_targets[1:]:
            if len(chosen) + 3 + len(nxt) <= budget:
                chosen = f'{chosen} · {nxt}'
            else:
                break
    else:
        chosen = seo_title(project)
    if len(chosen) > budget:
        words = chosen[:budget].rsplit(' ', 1)[0].strip()
        chosen = words or chosen[:budget].strip()
    video_title = f'{prefix}{chosen} {tags}'[:100]

    lines = []
    summary = re.sub(r'\s+', ' ', str(plan.get('summary') or '')).strip()
    if summary:
        lines.append(f'Topic: {summary}')
        lines.append('')
    for item in lessons:
        vi = re.sub(r'\s+', ' ', str(item.get('vi') or '')).strip()
        en = re.sub(r'\s+', ' ', str(item.get('en') or '')).strip()
        if vi or en:
            lines.append(f'- {vi} — {en}' if vi and en else f'- {vi or en}')
        for ch in item.get('chunks') or []:
            cvi = re.sub(r'\s+', ' ', str(ch.get('vi') or '')).strip()
            cen = re.sub(r'\s+', ' ', str(ch.get('en') or '')).strip()
            if cvi or cen:
                lines.append(f'  • {cvi}: {cen}')
    if not lines:
        lines.append(seo_title(project))
    lines.append('')
    desc_tags = '#learnvietnamese #vietnamese #hoctiengviet' + (' #shorts' if is_short else '')
    lines.append(desc_tags)
    return video_title, '\n'.join(lines)[:5000]


def profile_dir():
    path = store.data_root().resolve() / 'runtime' / 'youtube-camoufox-profile'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _fingerprint_path():
    return profile_dir() / 'camoufox-fingerprint.json'


def _load_or_create_fingerprint_preset():
    fp_file = _fingerprint_path()
    if fp_file.is_file():
        try:
            saved = json.loads(fp_file.read_text(encoding='utf-8'))
            if isinstance(saved, dict) and saved:
                return saved
        except Exception:
            pass
    from camoufox.fingerprints import get_random_preset, load_presets
    from camoufox.pkgman import installed_verstr

    try:
        ff_ver = installed_verstr().split('.', 1)[0]
    except Exception:
        ff_ver = None
    preset = None
    try:
        all_presets = load_presets(ff_ver) or {}
        win_presets = (all_presets.get('presets') or {}).get('windows') or []
        desktop = [
            p for p in win_presets
            if isinstance(p, dict)
            and 1280 <= ((p.get('screen') or {}).get('width') or 0) <= 1920
            and 720 <= ((p.get('screen') or {}).get('height') or 0) <= 1080
        ]
        if desktop:
            preset = random.choice(desktop)
    except Exception:
        preset = None
    if preset is None:
        preset = get_random_preset(os='windows', ff_version=ff_ver)
    if isinstance(preset, dict) and preset:
        store.atomic_json(fp_file, preset)
        return preset
    return None


def _ensure_camoufox_ready():
    try:
        from camoufox import pkgman
        from camoufox.sync_api import Camoufox  # noqa: F401
    except ImportError as exc:
        raise RuntimeError('Chưa cài thư viện Camoufox. Hãy chạy `pip install camoufox` trước khi đăng YouTube.') from exc
    try:
        exe = pkgman.camoufox_path(download_if_missing=False)
    except Exception as exc:
        raise RuntimeError('Chưa tải trình duyệt Camoufox. Hãy chạy `python -m camoufox fetch` để cài đặt Camoufox trước khi đăng YouTube.') from exc
    if not exe or not Path(exe).exists():
        raise RuntimeError('Không tìm thấy file chạy Camoufox. Hãy chạy `python -m camoufox fetch` để cài đặt Camoufox.')
    return exe


@contextmanager
def _launch_persistent(headless=False):
    _ensure_camoufox_ready()
    from camoufox.sync_api import Camoufox

    preset = _load_or_create_fingerprint_preset()
    kwargs = {
        'persistent_context': True,
        'user_data_dir': str(profile_dir()),
        'os': 'windows',
        'humanize': 1.2,
        'locale': ['en-US', 'vi-VN'],
        'enable_cache': True,
        'headless': headless,
    }
    if preset:
        kwargs['fingerprint_preset'] = preset
    try:
        with Camoufox(**kwargs) as ctx:
            yield ctx
    except Exception as exc:
        raise RuntimeError(f'Không mở được trình duyệt Camoufox cho YouTube Studio: {exc}') from exc


def list_uploads(limit=200):
    with store.connect() as conn:
        rows = conn.execute(
            'SELECT id,source_hash,export_hash,project_id,scheduled_date,publish_hour,title,status,video_url,created '
            'FROM youtube_uploads ORDER BY scheduled_date DESC, created DESC LIMIT ?',
            (limit,),
        ).fetchall()
    return [
        {
            'id': r[0], 'source_hash': r[1], 'export_hash': r[2], 'project_id': r[3],
            'scheduled_date': r[4], 'publish_hour': r[5], 'title': r[6], 'status': r[7],
            'video_url': r[8], 'created': r[9],
        }
        for r in rows
    ]


def normalize_title(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip().casefold()


def _strip_tags(text):
    return normalize_title(re.sub(r'#\S+', '', str(text or '')))


def check_duplicate(source_hash, export_hash, title=''):
    with store.connect() as conn:
        row = conn.execute(
            "SELECT scheduled_date,title,video_url FROM youtube_uploads "
            "WHERE (source_hash=? OR (export_hash!='' AND export_hash=?)) AND status IN ('scheduled','uploaded') LIMIT 1",
            (source_hash, export_hash),
        ).fetchone()
        if not row and title:
            want = _strip_tags(title)
            for r in conn.execute("SELECT scheduled_date,title,video_url FROM youtube_uploads WHERE status IN ('scheduled','uploaded')").fetchall():
                if want and _strip_tags(r[1]) == want:
                    row = r
                    break
    if row:
        raise ValueError(f'Video này đã được đăng/lên lịch lên YouTube (ngày {row[0]}: {row[1]}). Hệ thống chặn đăng trùng.')


def next_available_slot(start_date=None, today=None, extra_taken=None):
    base = today or datetime.now().date()
    if start_date:
        try:
            requested = date.fromisoformat(str(start_date))
            if requested > base:
                base = requested
        except ValueError as exc:
            raise ValueError('Ngày bắt đầu lịch đăng không hợp lệ (YYYY-MM-DD).') from exc
    with store.connect() as conn:
        taken = {
            r[0]
            for r in conn.execute(
                "SELECT scheduled_date FROM youtube_uploads WHERE status IN ('scheduled','uploaded')"
            ).fetchall()
        }
    if extra_taken:
        taken |= set(extra_taken)
    cursor = base
    while cursor.isoformat() in taken:
        cursor += timedelta(days=1)
    return cursor.isoformat()


def record_upload(project_id, source_hash, export_hash, scheduled_date, publish_hour, title, status='scheduled', video_url=''):
    uid = store.uid()
    created = store.now()
    with store.connect() as conn:
        conn.execute(
            'INSERT INTO youtube_uploads (id,source_hash,export_hash,project_id,scheduled_date,publish_hour,title,status,video_url,created) '
            'VALUES (?,?,?,?,?,?,?,?,?,?)',
            (uid, source_hash, export_hash, project_id, scheduled_date, publish_hour, title, status, video_url, created),
        )
    return {
        'id': uid, 'source_hash': source_hash, 'export_hash': export_hash, 'project_id': project_id,
        'scheduled_date': scheduled_date, 'publish_hour': publish_hour, 'title': title,
        'status': status, 'video_url': video_url, 'created': created,
    }


def clear_project_upload(project_id):
    with store.connect() as conn:
        conn.execute('DELETE FROM youtube_uploads WHERE project_id=?', (project_id,))
    project = store.read(project_id)
    if 'youtube' in project:
        project.pop('youtube', None)
        store.save(project)
    return project


def open_login_session():
    """Launch Camoufox persistent profile so the user can sign into YouTube Studio once."""
    try:
        _ensure_camoufox_ready()
    except RuntimeError as exc:
        raise ValueError(str(exc)) from exc
    if not _BROWSER_LOCK.acquire(blocking=False):
        raise ValueError('Trình duyệt Camoufox YouTube Studio đang mở. Hãy đóng cửa sổ hiện tại trước khi mở lại.')

    def run():
        try:
            with _launch_persistent(headless=False) as ctx:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto('https://studio.youtube.com', wait_until='domcontentloaded', timeout=45_000)
                try:
                    page.wait_for_event('close', timeout=300_000)
                except Exception:
                    pass
        finally:
            _BROWSER_LOCK.release()

    threading.Thread(target=run, name='vietcut-yt-login', daemon=True).start()
    return {'ok': True, 'message': 'Đã mở cửa sổ Camoufox YouTube Studio. Hãy đăng nhập kênh của bạn rồi đóng cửa sổ trình duyệt.'}


def _format_studio_date(iso_date):
    d = date.fromisoformat(iso_date)
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    return f'{months[d.month - 1]} {d.day}, {d.year}'


def _format_studio_time(hhmm, sample=''):
    hh, mm = [int(x) for x in str(hhmm or '19:00').split(':')[:2]]
    if re.search(r'\b(AM|PM)\b', str(sample or ''), re.I):
        ampm = 'PM' if hh >= 12 else 'AM'
        h12 = hh % 12 or 12
        return f'{h12}:{mm:02d} {ampm}'
    return f'{hh:02d}:{mm:02d}'


def _human_wait(page, min_ms=450, max_ms=1200, context=None):
    """Wait a randomized human-like duration while staying responsive to job cancellation."""
    remaining = max(0, int(random.uniform(min_ms, max_ms)))
    while remaining > 0:
        if context:
            context.check()
        step = min(250, remaining)
        page.wait_for_timeout(step)
        remaining -= step


def _human_idle_drift(page, context=None):
    """Move the pointer casually inside a safe viewport area after navigation."""
    try:
        vp = page.viewport_size or {'width': 1280, 'height': 720}
        x = random.randint(int(vp['width'] * 0.25), int(vp['width'] * 0.72))
        y = random.randint(int(vp['height'] * 0.2), int(vp['height'] * 0.65))
        page.mouse.move(x, y, steps=random.randint(8, 18))
        _human_wait(page, 180, 450, context)
    except Exception:
        pass


def _human_move_and_click(page, locator, timeout=15_000, context=None):
    """Scroll into view, hover naturally (Camoufox humanized cursor), pause, and click."""
    locator.wait_for(state='visible', timeout=timeout)
    try:
        locator.scroll_into_view_if_needed(timeout=timeout)
    except Exception:
        pass
    _human_wait(page, 140, 340, context)
    try:
        locator.hover(timeout=timeout)
    except Exception:
        pass
    _human_wait(page, 110, 280, context)
    locator.click(delay=random.randint(45, 130), timeout=timeout)


def _human_scroll(page, container_selectors, context=None):
    """Scroll dialog content with mouse-wheel increments instead of instant JS scrollTop jumps."""
    scrolled = False
    for sel in container_selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                box = loc.bounding_box()
                if box and box['width'] > 20 and box['height'] > 20:
                    cx = box['x'] + box['width'] * random.uniform(0.35, 0.65)
                    cy = box['y'] + box['height'] * random.uniform(0.35, 0.65)
                    page.mouse.move(cx, cy, steps=random.randint(6, 12))
                    for _ in range(random.randint(3, 5)):
                        page.mouse.wheel(0, random.randint(180, 320))
                        _human_wait(page, 130, 290, context)
                    scrolled = True
                    break
        except Exception:
            continue
    if not scrolled:
        try:
            for _ in range(3):
                page.mouse.wheel(0, random.randint(200, 340))
                _human_wait(page, 130, 260, context)
        except Exception:
            pass


def _human_type_text(page, text, context=None):
    """Type text character-by-character with natural variable keystroke cadence."""
    for idx, ch in enumerate(text):
        if context and idx % 10 == 0:
            context.check()
        if ch == '\n':
            page.keyboard.press('Enter')
            _human_wait(page, 120, 280, context)
            continue
        delay = random.randint(35, 92)
        page.keyboard.type(ch, delay=delay)
        if ch in (' ', ',', '.', '—', ':'):
            _human_wait(page, 40, 125, context)


def _human_type_input(page, locator, value, context=None):
    """Clear and type a short single-line input field like date or time."""
    _human_move_and_click(page, locator, timeout=8000, context=context)
    _human_wait(page, 120, 260, context)
    page.keyboard.press('Control+a')
    _human_wait(page, 90, 200, context)
    page.keyboard.press('Backspace')
    _human_wait(page, 140, 300, context)
    _human_type_text(page, value, context)
    _human_wait(page, 180, 360, context)
    page.keyboard.press('Enter')


def _read_editable(locator):
    return re.sub(r'\s+', ' ', locator.inner_text() or '').strip()


def _read_studio_state(page, include_tabs=True, context=None):
    scheduled_dates = set()
    titles = set()
    row_entries = []
    today_iso = datetime.now().date().isoformat()

    def scan_current():
        try:
            rows = page.locator('ytcp-video-row').all_inner_texts()
            for t in rows:
                is_draft = bool(re.search(r'\bDraft\b|Bản nháp', t, re.I))
                is_scheduled = bool(re.search(r'\bScheduled\b|Đã lên lịch|Lên lịch', t, re.I))
                is_published = bool(re.search(r'\bPublished\b|\bPublic\b|Công khai', t, re.I))
                row_dates = parse_studio_dates([t])
                if is_scheduled:
                    scheduled_dates.update(row_dates)
                elif is_published and today_iso in row_dates:
                    scheduled_dates.add(today_iso)
                lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
                row_title = ''
                for ln in lines:
                    if re.match(r'^\d+:\d+$', ln):
                        continue
                    row_title = ln
                    break
                norm = _strip_tags(row_title)
                row_entries.append({'text': t, 'title': norm, 'draft': is_draft, 'scheduled': is_scheduled, 'dates': row_dates})
                if norm and not is_draft and norm != 'final':
                    titles.add(norm)
        except Exception:
            pass

    if not include_tabs:
        scan_current()
        return scheduled_dates, titles, row_entries

    visited = False
    for tab_sel in (
        'tp-yt-paper-tab:has-text("Videos")',
        'tp-yt-paper-tab:has-text("Shorts")',
        'tp-yt-paper-tab:has-text("Video ngắn")',
    ):
        try:
            loc = page.locator(tab_sel).first
            if loc.count() and loc.is_visible():
                _human_move_and_click(page, loc, timeout=8000, context=context)
                _human_wait(page, 1300, 2200, context)
                scan_current()
                visited = True
        except Exception:
            continue
    if not visited:
        scan_current()
    return scheduled_dates, titles, row_entries


def _fill_editable(page, locator, text, context=None, chunked=False):
    """Focus a YouTube Studio contenteditable box and enter text with human-like pacing."""
    locator.wait_for(state='visible', timeout=45_000)
    want = re.sub(r'\s+', ' ', text).strip()
    if want and _read_editable(locator) == want:
        return True
    for _ in range(3):
        _human_move_and_click(page, locator, timeout=15_000, context=context)
        _human_wait(page, 140, 300, context)
        page.keyboard.press('Control+a')
        _human_wait(page, 100, 220, context)
        page.keyboard.press('Backspace')
        _human_wait(page, 200, 420, context)
        if not chunked or len(text) <= 140:
            _human_type_text(page, text, context)
        else:
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if context:
                    context.check()
                is_last_tags = i == len(lines) - 1 and line.strip().startswith('#')
                if is_last_tags:
                    _human_type_text(page, line, context)
                elif line:
                    page.keyboard.insert_text(line)
                if i < len(lines) - 1:
                    _human_wait(page, 110, 260, context)
                    page.keyboard.press('Enter')
                    _human_wait(page, 120, 280, context)
        _human_wait(page, 350, 750, context)
        current = _read_editable(locator)
        if current == want or (want and want[:20] in current):
            return True
    return False


def _advance_to_visibility(page, context=None):
    for _ in range(5):
        vis = page.locator('ytcp-video-visibility-select, #done-button').first
        try:
            if vis.count() and vis.is_visible():
                return True
        except Exception:
            pass
        next_btn = page.locator('#next-button').first
        try:
            next_btn.wait_for(state='visible', timeout=8000)
            if next_btn.is_disabled():
                _human_wait(page, 700, 1200, context)
            _human_move_and_click(page, next_btn, timeout=8000, context=context)
            _human_wait(page, 900, 1750, context)
        except Exception:
            break
    return False


def _fill_schedule_fields(page, scheduled_date, publish_hour, context=None):
    _human_scroll(
        page,
        ['ytcp-uploads-dialog #scrollable-content', 'ytcp-uploads-dialog tp-yt-iron-pages', 'ytcp-video-visibility-select'],
        context=context,
    )
    _human_wait(page, 300, 650, context)

    # Click Schedule expand button if datepicker is not visible yet.
    date_trigger = page.locator('#datepicker-trigger').first
    if not (date_trigger.count() and date_trigger.is_visible()):
        for selector in (
            '#second-container-expand-button',
            '#schedule-radio-button',
            'tp-yt-paper-radio-button[name="SCHEDULE"]',
        ):
            try:
                loc = page.locator(selector).first
                if loc.count() and loc.is_visible():
                    _human_move_and_click(page, loc, timeout=5000, context=context)
                    _human_wait(page, 500, 950, context)
                    if date_trigger.count() and date_trigger.is_visible():
                        break
            except Exception:
                continue

    # Set date via #datepicker-trigger popup -> ytcp-date-picker input.
    try:
        if date_trigger.count() and date_trigger.is_visible():
            _human_move_and_click(page, date_trigger, timeout=5000, context=context)
            _human_wait(page, 400, 800, context)
            dp_input = page.locator('ytcp-date-picker input').first
            dp_input.wait_for(state='visible', timeout=4000)
            existing = dp_input.input_value()
            date_str = scheduled_date if re.match(r'^\d{4}-\d{2}-\d{2}$', existing.strip()) else _format_studio_date(scheduled_date)
            _human_type_input(page, dp_input, date_str, context=context)
            _human_wait(page, 400, 800, context)
    except Exception:
        pass

    # Set time via #time-of-day-container input.
    try:
        time_input = page.locator('#time-of-day-container input, ytcp-form-input-container input[aria-label*="time" i], ytcp-form-input-container input[aria-label*="giờ" i]').first
        if time_input.count() and time_input.is_visible():
            existing_time = time_input.input_value()
            time_str = _format_studio_time(publish_hour, existing_time)
            _human_type_input(page, time_input, time_str, context=context)
            _human_wait(page, 350, 700, context)
    except Exception:
        pass


def upload_and_schedule(mp4_path, title, description, scheduled_date, publish_hour='19:00', context=None, start_date=None):
    if UPLOAD_HOOK is not None:
        return UPLOAD_HOOK(mp4_path=mp4_path, title=title, description=description, scheduled_date=scheduled_date, publish_hour=publish_hour, context=context)
    from .media import Cancelled

    _ensure_camoufox_ready()
    if not _BROWSER_LOCK.acquire(blocking=False):
        raise RuntimeError('Trình duyệt Camoufox YouTube Studio đang mở. Hãy đóng cửa sổ đang mở rồi thử lại.')

    if context:
        context.progress(85, 'Đang mở Camoufox YouTube Studio kiểm tra lịch và video trùng...')
    try:
        with _launch_persistent(headless=False) as browser:
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto('https://studio.youtube.com', wait_until='domcontentloaded', timeout=45_000)
            _human_wait(page, 1300, 2400, context)
            _human_idle_drift(page, context)
            if 'accounts.google.com' in page.url:
                raise RuntimeError('Chưa đăng nhập YouTube Studio. Hãy bấm "Đăng nhập YouTube Studio" trước.')
            create_btn = page.locator('#create-icon, ytcp-button#create-icon, [aria-label*="Create" i], [aria-label*="Tạo" i]').first
            create_btn.wait_for(state='visible', timeout=25_000)

            studio_taken = set()
            studio_titles = set()
            try:
                content_nav = page.locator('#menu-item-1, a[href*="/videos"]').first
                if content_nav.count() and content_nav.is_visible():
                    _human_move_and_click(page, content_nav, timeout=10_000, context=context)
                    _human_wait(page, 1400, 2400, context)
                studio_taken, studio_titles, _ = _read_studio_state(page, include_tabs=True, context=context)
            except Exception:
                pass

            if _strip_tags(title) and _strip_tags(title) in studio_titles:
                raise ValueError(f'Video "{title}" đã có sẵn trên kênh YouTube Studio. Hệ thống chặn đăng trùng.')

            scheduled_date = next_available_slot(start_date, extra_taken=studio_taken)

            _human_move_and_click(page, create_btn, timeout=15_000, context=context)
            _human_wait(page, 450, 950, context)
            upload_item = page.locator('#text-item-0, tp-yt-paper-item:has-text("Upload"), tp-yt-paper-item:has-text("Tải video")').first
            _human_move_and_click(page, upload_item, timeout=15_000, context=context)
            _human_wait(page, 500, 1000, context)
            file_input = page.locator('input[type="file"]').first
            file_input.set_input_files(str(Path(mp4_path).resolve()))
            if context:
                context.progress(90, f'Đang tải video và nhập liệu tự nhiên cho lịch {scheduled_date} {publish_hour}')

            title_box = page.locator('ytcp-video-title #textbox').first
            title_box.wait_for(state='visible', timeout=45_000)
            # Wait for YouTube Studio to hydrate initial filename ("final") and upload defaults before overwriting.
            _human_wait(page, 2100, 3200, context)
            _fill_editable(page, title_box, title[:100], context=context, chunked=False)
            _human_wait(page, 550, 1150, context)
            desc_box = page.locator('ytcp-video-description #textbox').first
            if desc_box.count():
                _fill_editable(page, desc_box, description[:5000], context=context, chunked=True)
                _human_wait(page, 550, 1100, context)
            not_kids = page.locator('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]').first
            if not_kids.count():
                _human_scroll(
                    page,
                    ['ytcp-uploads-dialog #scrollable-content', 'ytcp-uploads-dialog tp-yt-iron-pages'],
                    context=context,
                )
                _human_move_and_click(page, not_kids, timeout=10_000, context=context)
                _human_wait(page, 450, 950, context)

            # Re-verify title only if YouTube Studio's late hydration overwrote it.
            expected_title = re.sub(r'\s+', ' ', title[:100]).strip()
            current_title = _read_editable(title_box)
            if current_title != expected_title and expected_title[:20] not in current_title:
                _fill_editable(page, title_box, title[:100], context=context, chunked=False)
                _human_wait(page, 400, 800, context)

            _advance_to_visibility(page, context=context)
            _fill_schedule_fields(page, scheduled_date, publish_hour, context=context)

            # Never auto-click #done-button: let the user inspect and click Schedule themselves.
            if context:
                context.progress(95, f'Đã điền Tiêu đề, Mô tả và lịch {scheduled_date} {publish_hour}. Hãy kiểm tra và tự bấm nút Lên lịch (Schedule) trên YouTube Studio.')
            closed = False
            confirmed = False
            video_url = ''
            final_date = scheduled_date
            saw_dialog = False
            for _ in range(600):
                if context:
                    context.check()
                if page.is_closed():
                    closed = True
                    break
                try:
                    upload_dialog = page.locator('ytcp-uploads-dialog').first
                    if upload_dialog.count() and upload_dialog.is_visible():
                        saw_dialog = True
                    share_dialog = page.locator('ytcp-video-share-dialog, #share-url').first
                    if share_dialog.count() and share_dialog.is_visible():
                        confirmed = True
                        try:
                            parsed = parse_studio_dates([share_dialog.inner_text()])
                            if parsed:
                                final_date = sorted(parsed)[0]
                        except Exception:
                            pass
                        link = page.locator('a[href*="youtu.be/"], a[href*="youtube.com/watch"]').first
                        if link.count():
                            video_url = link.get_attribute('href') or ''
                        break
                    if saw_dialog and (not upload_dialog.count() or not upload_dialog.is_visible()):
                        # Dialog closed: verify in Content list that video is genuinely Scheduled, NOT Draft.
                        _human_wait(page, 1400, 2000, context)
                        _, _, rows = _read_studio_state(page, include_tabs=True, context=context)
                        want = _strip_tags(title)
                        matched = [r for r in rows if want and want in r['title']]
                        if matched and any(r['scheduled'] for r in matched):
                            confirmed = True
                            sched = next(r for r in matched if r['scheduled'])
                            if sched['dates']:
                                final_date = sorted(sched['dates'])[0]
                        else:
                            raise Cancelled('Video mới chỉ được lưu ở trạng thái Nháp (Draft), chưa bấm Lên lịch.')
                        break
                except Cancelled:
                    raise
                except Exception:
                    pass
                page.wait_for_timeout(1000)
            if confirmed:
                return {'video_url': video_url, 'scheduled_date': final_date}
            if closed:
                raise Cancelled('Bạn đã đóng YouTube Studio trước khi bấm Lên lịch.')
            raise TimeoutError('Hết thời gian chờ bạn bấm nút Lên lịch trên YouTube Studio.')
    finally:
        _BROWSER_LOCK.release()
