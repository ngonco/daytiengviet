"""YouTube Studio browser automation, 1/day scheduling, and permanent duplicate memory."""
from datetime import date, datetime, timedelta
from pathlib import Path
import threading
from . import store

UPLOAD_HOOK = None


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


def next_available_slot(start_date=None, today=None):
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


def upload_and_schedule(mp4_path, title, description, scheduled_date, publish_hour='19:00', context=None):
    if UPLOAD_HOOK is not None:
        return UPLOAD_HOOK(mp4_path=mp4_path, title=title, description=description, scheduled_date=scheduled_date, publish_hour=publish_hour, context=context)
    from playwright.sync_api import sync_playwright
    if context:
        context.progress(85, f'Đang mở YouTube Studio để lên lịch {scheduled_date} {publish_hour}')
    with sync_playwright() as p:
        browser = _launch_persistent(p, headless=False)
        try:
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto('https://studio.youtube.com', wait_until='domcontentloaded', timeout=45_000)
            if 'accounts.google.com' in page.url:
                raise RuntimeError('Chưa đăng nhập YouTube Studio. Hãy bấm "Đăng nhập YouTube Studio" trước.')
            create_btn = page.locator('#create-icon, ytcp-button#create-icon, [aria-label*="Create" i], [aria-label*="Tạo" i]').first
            create_btn.wait_for(state='visible', timeout=25_000)
            create_btn.click()
            upload_item = page.locator('#text-item-0, tp-yt-paper-item:has-text("Upload"), tp-yt-paper-item:has-text("Tải video")').first
            upload_item.click()
            file_input = page.locator('input[type="file"]').first
            file_input.set_input_files(str(Path(mp4_path).resolve()))
            if context:
                context.progress(90, 'Đang tải video và điền thông tin trên YouTube Studio')
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
                page.wait_for_timeout(400)
            schedule_radio = page.locator('#schedule-radio-button, tp-yt-paper-radio-button[name="SCHEDULE"]').first
            schedule_radio.wait_for(state='visible', timeout=15_000)
            schedule_radio.click()
            date_input = page.locator('#datepicker-trigger input, ytcp-date-picker input').first
            if date_input.count():
                date_input.click()
                page.keyboard.press('Control+A')
                date_input.fill(scheduled_date)
                page.keyboard.press('Enter')
            time_input = page.locator('#time-of-day-container input, ytcp-form-input-container input[aria-label*="time" i]').first
            if time_input.count():
                time_input.click()
                page.keyboard.press('Control+A')
                time_input.fill(publish_hour)
                page.keyboard.press('Enter')
            done_btn = page.locator('#done-button').first
            done_btn.wait_for(state='enabled', timeout=120_000)
            done_btn.click()
            page.wait_for_timeout(2000)
            link = page.locator('a[href*="youtu.be/"], a[href*="youtube.com/watch"]').first
            video_url = link.get_attribute('href') if link.count() else ''
            return {'video_url': video_url or ''}
        finally:
            browser.close()
