"""YouTube Studio browser automation, 1/day scheduling, and permanent duplicate memory."""
from datetime import date, datetime, timedelta
from pathlib import Path
import re
import threading
from . import store

UPLOAD_HOOK = None
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
    path = store.data_root().resolve() / 'runtime' / 'youtube-profile'
    path.mkdir(parents=True, exist_ok=True)
    return path


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


def _launch_persistent(playwright, headless=False):
    user_dir = str(profile_dir())
    for channel in ('msedge', 'chrome', None):
        try:
            kwargs = {'user_data_dir': user_dir, 'headless': headless, 'args': ['--disable-blink-features=AutomationControlled']}
            if channel:
                kwargs['channel'] = channel
            return playwright.chromium.launch_persistent_context(**kwargs)
        except Exception:
            continue
    raise RuntimeError('Không mở được trình duyệt Chrome/Edge/Chromium để đăng nhập YouTube Studio.')


def open_login_session():
    def run():
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ctx = _launch_persistent(p, headless=False)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto('https://studio.youtube.com', wait_until='domcontentloaded')
            try:
                page.wait_for_event('close', timeout=300_000)
            except Exception:
                pass
            ctx.close()
    threading.Thread(target=run, name='vietcut-yt-login', daemon=True).start()
    return {'ok': True, 'message': 'Đã mở cửa sổ YouTube Studio. Hãy đăng nhập kênh của bạn rồi đóng cửa sổ trình duyệt.'}


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


def _read_studio_state(page, include_tabs=True):
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
                loc.click()
                page.wait_for_timeout(1500)
                scan_current()
                visited = True
        except Exception:
            continue
    if not visited:
        scan_current()
    return scheduled_dates, titles, row_entries


def _fill_editable(page, locator, text):
    locator.wait_for(state='visible', timeout=45_000)
    for _ in range(3):
        locator.click()
        page.wait_for_timeout(150)
        page.keyboard.press('Control+A')
        page.keyboard.press('Backspace')
        locator.fill(text)
        page.wait_for_timeout(300)
        current = re.sub(r'\s+', ' ', locator.inner_text() or '').strip()
        want = re.sub(r'\s+', ' ', text).strip()
        if current == want or (want and want[:20] in current):
            return True
    return False


def _advance_to_visibility(page):
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
                page.wait_for_timeout(800)
            next_btn.click()
            page.wait_for_timeout(800)
        except Exception:
            break
    return False


def _fill_schedule_fields(page, scheduled_date, publish_hour):
    try:
        page.evaluate("""() => {
            for (const sel of ['ytcp-uploads-dialog #scrollable-content', 'ytcp-uploads-dialog tp-yt-iron-pages', 'ytcp-video-visibility-select']) {
                const el = document.querySelector(sel);
                if (el) el.scrollTop = el.scrollHeight;
            }
        }""")
        page.wait_for_timeout(300)
    except Exception:
        pass

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
                    loc.click(timeout=3000)
                    page.wait_for_timeout(500)
                    if date_trigger.count() and date_trigger.is_visible():
                        break
            except Exception:
                continue

    # Set date via #datepicker-trigger popup -> ytcp-date-picker input.
    try:
        if date_trigger.count() and date_trigger.is_visible():
            date_trigger.click(timeout=3000)
            page.wait_for_timeout(400)
            dp_input = page.locator('ytcp-date-picker input').first
            dp_input.wait_for(state='visible', timeout=4000)
            existing = dp_input.input_value()
            date_str = scheduled_date if re.match(r'^\d{4}-\d{2}-\d{2}$', existing.strip()) else _format_studio_date(scheduled_date)
            dp_input.click()
            page.keyboard.press('Control+A')
            dp_input.fill(date_str)
            page.keyboard.press('Enter')
            page.wait_for_timeout(400)
    except Exception:
        pass

    # Set time via #time-of-day-container input.
    try:
        time_input = page.locator('#time-of-day-container input, ytcp-form-input-container input[aria-label*="time" i], ytcp-form-input-container input[aria-label*="giờ" i]').first
        if time_input.count() and time_input.is_visible():
            existing_time = time_input.input_value()
            time_str = _format_studio_time(publish_hour, existing_time)
            time_input.click(timeout=3000)
            page.keyboard.press('Control+A')
            time_input.fill(time_str)
            page.keyboard.press('Enter')
            page.wait_for_timeout(300)
    except Exception:
        pass


def upload_and_schedule(mp4_path, title, description, scheduled_date, publish_hour='19:00', context=None, start_date=None):
    if UPLOAD_HOOK is not None:
        return UPLOAD_HOOK(mp4_path=mp4_path, title=title, description=description, scheduled_date=scheduled_date, publish_hour=publish_hour, context=context)
    from playwright.sync_api import sync_playwright
    from .media import Cancelled
    if context:
        context.progress(85, 'Đang mở YouTube Studio kiểm tra lịch và video trùng...')
    with sync_playwright() as p:
        browser = _launch_persistent(p, headless=False)
        try:
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto('https://studio.youtube.com', wait_until='domcontentloaded', timeout=45_000)
            if 'accounts.google.com' in page.url:
                raise RuntimeError('Chưa đăng nhập YouTube Studio. Hãy bấm "Đăng nhập YouTube Studio" trước.')
            create_btn = page.locator('#create-icon, ytcp-button#create-icon, [aria-label*="Create" i], [aria-label*="Tạo" i]').first
            create_btn.wait_for(state='visible', timeout=25_000)

            studio_taken = set()
            studio_titles = set()
            try:
                content_nav = page.locator('#menu-item-1, a[href*="/videos"]').first
                if content_nav.count():
                    content_nav.click()
                    page.wait_for_timeout(1500)
                studio_taken, studio_titles, _ = _read_studio_state(page, include_tabs=True)
            except Exception:
                pass

            if _strip_tags(title) and _strip_tags(title) in studio_titles:
                raise ValueError(f'Video "{title}" đã có sẵn trên kênh YouTube Studio. Hệ thống chặn đăng trùng.')

            scheduled_date = next_available_slot(start_date, extra_taken=studio_taken)

            create_btn.click()
            upload_item = page.locator('#text-item-0, tp-yt-paper-item:has-text("Upload"), tp-yt-paper-item:has-text("Tải video")').first
            upload_item.click()
            file_input = page.locator('input[type="file"]').first
            file_input.set_input_files(str(Path(mp4_path).resolve()))
            if context:
                context.progress(90, f'Đang tải video và điền lịch {scheduled_date} {publish_hour} trên YouTube Studio')

            title_box = page.locator('ytcp-video-title #textbox').first
            title_box.wait_for(state='visible', timeout=45_000)
            # Wait for YouTube Studio to hydrate initial filename ("final") and upload defaults before overwriting.
            page.wait_for_timeout(2000)
            _fill_editable(page, title_box, title[:100])
            desc_box = page.locator('ytcp-video-description #textbox').first
            if desc_box.count():
                _fill_editable(page, desc_box, description[:5000])
            not_kids = page.locator('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]').first
            if not_kids.count():
                not_kids.click()
            # Re-verify title did not get reset by late hydration.
            _fill_editable(page, title_box, title[:100])

            _advance_to_visibility(page)
            _fill_schedule_fields(page, scheduled_date, publish_hour)

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
                        page.wait_for_timeout(1500)
                        _, _, rows = _read_studio_state(page, include_tabs=True)
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
            browser.close()
