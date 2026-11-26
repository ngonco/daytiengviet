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


def check_duplicate(source_hash, export_hash):
    with store.connect() as conn:
        row = conn.execute(
            "SELECT scheduled_date,title,video_url FROM youtube_uploads "
            "WHERE (source_hash=? OR (export_hash!='' AND export_hash=?)) AND status IN ('scheduled','uploaded') LIMIT 1",
            (source_hash, export_hash),
        ).fetchone()
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


def _read_studio_scheduled_dates(page):
    try:
        rows = page.locator('ytcp-video-row').all_inner_texts()
        scheduled_texts = [t for t in rows if re.search(r'Scheduled|Đã lên lịch|Lên lịch', t, re.I)]
        return parse_studio_dates(scheduled_texts)
    except Exception:
        return set()


def upload_and_schedule(mp4_path, title, description, scheduled_date, publish_hour='19:00', context=None, start_date=None):
    if UPLOAD_HOOK is not None:
        return UPLOAD_HOOK(mp4_path=mp4_path, title=title, description=description, scheduled_date=scheduled_date, publish_hour=publish_hour, context=context)
    from playwright.sync_api import sync_playwright
    from .media import Cancelled
    if context:
        context.progress(85, 'Đang mở YouTube Studio kiểm tra lịch trống...')
    with sync_playwright() as p:
        browser = _launch_persistent(p, headless=False)
        try:
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto('https://studio.youtube.com', wait_until='domcontentloaded', timeout=45_000)
            if 'accounts.google.com' in page.url:
                raise RuntimeError('Chưa đăng nhập YouTube Studio. Hãy bấm "Đăng nhập YouTube Studio" trước.')
            create_btn = page.locator('#create-icon, ytcp-button#create-icon, [aria-label*="Create" i], [aria-label*="Tạo" i]').first
            create_btn.wait_for(state='visible', timeout=25_000)

            # Check existing scheduled videos on YouTube Studio so we never collide on the same date.
            studio_taken = set()
            try:
                content_nav = page.locator('#menu-item-1, a[href*="/videos"]').first
                if content_nav.count():
                    content_nav.click()
                    page.wait_for_timeout(1500)
                studio_taken = _read_studio_scheduled_dates(page)
            except Exception:
                pass
            scheduled_date = next_available_slot(start_date, extra_taken=studio_taken)

            create_btn.click()
            upload_item = page.locator('#text-item-0, tp-yt-paper-item:has-text("Upload"), tp-yt-paper-item:has-text("Tải video")').first
            upload_item.click()
            file_input = page.locator('input[type="file"]').first
            file_input.set_input_files(str(Path(mp4_path).resolve()))
            if context:
                context.progress(90, f'Đang tải video và điền lịch {scheduled_date} {publish_hour} trên YouTube Studio')
            title_box = page.locator('#textbox[aria-label*="title" i], #textbox[aria-label*="tiêu đề" i], ytcp-social-suggestions-textbox #textbox').first
            title_box.wait_for(state='visible', timeout=45_000)
            title_box.click()
            page.keyboard.press('Control+A')
            title_box.fill(title[:100])
            desc_boxes = page.locator('ytcp-social-suggestions-textbox #textbox')
            if desc_boxes.count() > 1:
                desc_boxes.nth(1).click()
                desc_boxes.nth(1).fill(description[:5000])
            not_kids = page.locator('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]').first
            if not_kids.count():
                not_kids.click()
            for _ in range(3):
                next_btn = page.locator('#next-button').first
                next_btn.wait_for(state='visible', timeout=15_000)
                next_btn.click()
                page.wait_for_timeout(500)

            # Expand Schedule accordion if present, then select Schedule radio button.
            expand_btn = page.locator('#second-container-expand-button').first
            if expand_btn.count():
                try:
                    expand_btn.scroll_into_view_if_needed()
                    expand_btn.click()
                    page.wait_for_timeout(400)
                except Exception:
                    pass
            schedule_radio = page.locator('#schedule-radio-button, tp-yt-paper-radio-button[name="SCHEDULE"], ytcp-video-visibility-select tp-yt-paper-radio-button:has-text("Schedule"), ytcp-video-visibility-select tp-yt-paper-radio-button:has-text("Lên lịch")').first
            schedule_radio.scroll_into_view_if_needed()
            schedule_radio.wait_for(state='visible', timeout=20_000)
            schedule_radio.click()

            date_input = page.locator('#datepicker-trigger input, ytcp-date-picker input').first
            if date_input.count():
                date_input.click()
                page.keyboard.press('Control+A')
                date_input.fill(scheduled_date)
                page.keyboard.press('Enter')
                page.wait_for_timeout(300)
            time_input = page.locator('#time-of-day-container input, ytcp-form-input-container input[aria-label*="time" i], ytcp-form-input-container input[aria-label*="giờ" i]').first
            if time_input.count():
                time_input.click()
                page.keyboard.press('Control+A')
                time_input.fill(publish_hour)
                page.keyboard.press('Enter')

            # Never auto-click #done-button: let the user inspect and click Schedule themselves.
            if context:
                context.progress(95, f'Đã điền lịch {scheduled_date} {publish_hour}. Hãy kiểm tra và tự bấm nút Lên lịch (Schedule) trên YouTube Studio.')
            done_btn = page.locator('#done-button').first
            done_btn.wait_for(state='visible', timeout=15_000)
            closed = False
            confirmed = False
            video_url = ''
            for _ in range(600):
                if context:
                    context.check()
                if page.is_closed():
                    closed = True
                    break
                share_dialog = page.locator('ytcp-video-share-dialog, #share-url').first
                if share_dialog.count() and share_dialog.is_visible():
                    confirmed = True
                    link = page.locator('a[href*="youtu.be/"], a[href*="youtube.com/watch"]').first
                    if link.count():
                        video_url = link.get_attribute('href') or ''
                    break
                if not done_btn.is_visible():
                    confirmed = True
                    break
                page.wait_for_timeout(1000)
            if closed and not confirmed:
                raise Cancelled('Bạn đã đóng YouTube Studio trước khi bấm Lên lịch.')
            if not confirmed:
                raise TimeoutError('Hết thời gian chờ bạn bấm nút Lên lịch trên YouTube Studio.')
            return {'video_url': video_url, 'scheduled_date': scheduled_date}
        finally:
            browser.close()
