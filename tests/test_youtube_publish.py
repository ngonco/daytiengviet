from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image
from backend import automation, retention, store, worker, youtube
from backend.media import ffmpeg


class YouTubeAndAutoDeleteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = self.root / 'data'
        self.data.mkdir(parents=True)
        self.watch = self.root / 'watch'
        self.watch.mkdir(parents=True)
        self.mock = patch('backend.store.data_root', return_value=self.data)
        self.mock.start()
        store.init()

    def tearDown(self):
        youtube.UPLOAD_HOOK = None
        self.mock.stop()
        self.tmp.cleanup()

    def _make_project(self, pid, created_at, source_name='clip.mp4', freq=330, vi='Xin chào', en='Hello'):
        folder = store.folder(pid)
        (folder / 'assets').mkdir(exist_ok=True)
        Image.new('RGB', (400, 300), '#4a7c59').save(folder / 'assets/p.jpg')
        ffmpeg([
            '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30',
            '-f', 'lavfi', '-i', f'sine=frequency={freq}:sample_rate=48000',
            '-t', '2', '-c:v', 'libx264', '-c:a', 'aac', folder / source_name,
        ])
        project = {
            'id': pid, 'title': vi, 'title_mode': 'auto',
            'source_file': source_name, 'original_name': source_name,
            'metadata': {'duration': 2.0, 'width': 320, 'height': 180},
            'options': {'ratio': '16:9', 'layout_mode': 'lesson', 'subtitles': 'bilingual', 'sfx': False, 'auto_volume': False},
            'status': 'ready', 'revision': 1, 'created_at': created_at,
            'plan': {
                'schema_version': 2, 'summary': vi, 'glossary': [], 'cuts': [], 'pauses': [], 'visuals': [],
                'captions': [{'id': 'c1', 'start': 0, 'end': 2, 'vi': vi, 'en': en}],
                'lessons': [{'id': 'l1', 'start': 0, 'end': 2, 'vi': vi, 'en': en, 'chunks': [], 'asset_id': 'p'}],
            },
            'transcript': {'captions': []},
            'assets': {'p': {'file': 'p.jpg'}}, 'frames': [], 'warnings': [],
            'preview': None, 'export': None, 'music_file': None,
        }
        store.save(project)
        return project

    def test_approve_publish_schedules_one_per_day_and_blocks_duplicates(self):
        calls = []
        youtube.UPLOAD_HOOK = lambda **kw: calls.append(kw) or {'video_url': f'https://youtu.be/test{len(calls)}'}
        automation.configure(youtube_publish_hour='19:00')
        p1 = self._make_project('aaaaaaaaaaaaaaaa', datetime.now(timezone.utc).isoformat(), 'a.mp4', 330, 'Xin chào', 'Hello')
        p2 = self._make_project('bbbbbbbbbbbbbbbb', datetime.now(timezone.utc).isoformat(), 'b.mp4', 440, 'Tạm biệt', 'Goodbye')

        j1 = store.job_create(p1['id'], 'approve_publish', {})
        worker.execute(j1)
        j2 = store.job_create(p2['id'], 'approve_publish', {})
        worker.execute(j2)

        self.assertEqual(len(calls), 2)
        d1 = date.fromisoformat(calls[0]['scheduled_date'])
        d2 = date.fromisoformat(calls[1]['scheduled_date'])
        self.assertEqual((d2 - d1).days, 1)
        self.assertEqual(calls[0]['publish_hour'], '19:00')

        # Duplicate upload attempt with same source video must be rejected even on a new project ID.
        p1_dup = self._make_project('cccccccccccccccc', datetime.now(timezone.utc).isoformat(), 'a.mp4')
        (store.folder(p1['id']) / p1['source_file']).replace(store.folder(p1_dup['id']) / 'a.mp4')
        src_hash = automation.digest(store.folder(p1_dup['id']) / 'a.mp4')
        with self.assertRaises(ValueError):
            youtube.check_duplicate(src_hash, '')

    def test_auto_delete_days_removes_project_and_external_source_preserving_youtube_memory(self):
        old_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        fresh_time = datetime.now(timezone.utc).isoformat()
        p_old = self._make_project('1111111111111111', old_time)
        p_new = self._make_project('2222222222222222', fresh_time)

        ext_old = self.watch / 'old_source.mp4'
        ext_old.write_bytes(b'old-video-bytes')
        automation.put({'hash': 'h_old', 'source': str(ext_old), 'project_id': p_old['id'], 'state': 'done'})
        youtube.record_upload(p_old['id'], 'h_old', 'exp_old', '2026-11-26', '19:00', 'Old lesson')

        automation.configure(auto_delete_days=7)
        result = retention.sweep()

        self.assertIn(p_old['id'], result['purged'])
        self.assertFalse(ext_old.exists())
        self.assertFalse((self.data / 'projects' / p_old['id']).exists())
        self.assertTrue((self.data / 'projects' / p_new['id']).exists())
        # Permanent duplicate memory survives project + source deletion.
        with self.assertRaises(ValueError):
            youtube.check_duplicate('h_old', '')

    def test_parse_studio_dates_and_avoid_collision(self):
        parsed = youtube.parse_studio_dates([
            'Video A\nScheduled\nNov 26, 2026',
            'Video B\nĐã lên lịch\n27 thg 11, 2026',
            'Video C\n28/11/2026',
        ])
        self.assertEqual(parsed, {'2026-11-26', '2026-11-27', '2026-11-28'})
        slot = youtube.next_available_slot(today=date(2026, 11, 26), extra_taken=parsed)
        self.assertEqual(slot, '2026-11-29')

    def test_youtube_metadata_formula_title_and_lesson_description(self):
        p = {
            'title': 'Gọi nước',
            'options': {'ratio': '9:16'},
            'metadata': {'width': 1080, 'height': 1920},
            'plan': {
                'summary': 'Ordering drinks',
                'lessons': [{
                    'vi': 'Cho tôi nước lọc',
                    'en': 'I would like water',
                    'chunks': [{'vi': 'Cho tôi', 'en': 'I would like'}, {'vi': 'nước lọc', 'en': 'water'}],
                }],
            },
        }
        title, desc = youtube.build_youtube_metadata(p)
        self.assertEqual(title, 'Learn vietnamese: I would like water #learnvietnamese #shorts')
        self.assertIn('Cho tôi nước lọc — I would like water', desc)
        self.assertIn('Cho tôi: I would like', desc)
        self.assertIn('#learnvietnamese', desc)

    def test_manual_mark_scheduled_and_title_duplicate_protection(self):
        from backend.app import youtube_mark_scheduled, MarkScheduledBody
        p = self._make_project('dddddddddddddddd', datetime.now(timezone.utc).isoformat(), 'd.mp4', 550, 'Tính tiền', 'Could I have the bill')
        job = store.job_create(p['id'], 'approve_publish', {})
        store.job_update(job['id'], status='failed', error='Timeout')
        updated = youtube_mark_scheduled(p['id'], MarkScheduledBody(scheduled_date='2026-11-28', publish_hour='19:00'))
        self.assertEqual(updated['youtube']['scheduled_date'], '2026-11-28')
        self.assertEqual(store.job_read(job['id'])['status'], 'succeeded')
        # Even a different file with the same lesson title is blocked as duplicate.
        with self.assertRaises(ValueError):
            youtube.check_duplicate('brand_new_hash', '', title='Learn vietnamese: Could I have the bill #learnvietnamese')

    def test_studio_date_and_time_formatting_and_clear_status(self):
        self.assertEqual(youtube._format_studio_date('2026-11-29'), 'Nov 29, 2026')
        self.assertEqual(youtube._format_studio_time('19:00', '12:00 AM'), '7:00 PM')
        self.assertEqual(youtube._format_studio_time('09:05', '12:00 PM'), '9:05 AM')
        self.assertEqual(youtube._format_studio_time('19:00', '19:00'), '19:00')
        p = self._make_project('eeeeeeeeeeeeeeee', datetime.now(timezone.utc).isoformat(), 'e.mp4', 660, 'Cảm ơn', 'Thank you')
        rec = youtube.record_upload(p['id'], 'h_e', 'exp_e', '2026-11-29', '19:00', 'Learn vietnamese: Thank you')
        store.update(p['id'], youtube=rec)
        cleared = youtube.clear_project_upload(p['id'])
        self.assertNotIn('youtube', cleared)
        self.assertEqual(youtube.list_uploads(), [])

    def test_camoufox_profile_and_sticky_fingerprint_persistence(self):
        pdir = youtube.profile_dir()
        self.assertEqual(pdir.name, 'youtube-camoufox-profile')
        preset = youtube._load_or_create_fingerprint_preset()
        self.assertIsInstance(preset, dict)
        self.assertTrue((pdir / 'camoufox-fingerprint.json').is_file())
        screen = preset.get('screen') or {}
        if screen:
            self.assertGreaterEqual(screen.get('width', 0), 1280)
            self.assertGreaterEqual(screen.get('height', 0), 720)
        # Subsequent call reuses the exact persisted preset rather than randomizing.
        preset2 = youtube._load_or_create_fingerprint_preset()
        self.assertEqual(preset, preset2)

    def test_camoufox_no_chromium_fallback_and_lock_guard(self):
        with patch('camoufox.pkgman.camoufox_path', side_effect=FileNotFoundError('missing')):
            with self.assertRaises(RuntimeError) as ctx:
                with youtube._launch_persistent(headless=True):
                    pass
            self.assertIn('Camoufox', str(ctx.exception))
            with self.assertRaises(ValueError):
                youtube.open_login_session()

        # Concurrent session lock rejects overlapping login or upload cleanly.
        self.assertTrue(youtube._BROWSER_LOCK.acquire(blocking=False))
        try:
            with patch.object(youtube, '_ensure_camoufox_ready', return_value='camoufox.exe'):
                with self.assertRaises(ValueError):
                    youtube.open_login_session()
                with self.assertRaises(RuntimeError):
                    youtube.upload_and_schedule('clip.mp4', 'Title', 'Desc', '2026-12-01')
        finally:
            youtube._BROWSER_LOCK.release()

    def test_human_like_typing_clicking_scrolling_and_launch_options(self):
        captured = {}

        class FakeCtx:
            pages = []
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        def fake_camoufox(**kwargs):
            captured.update(kwargs)
            return FakeCtx()

        with patch.object(youtube, '_ensure_camoufox_ready', return_value='camoufox.exe'), \
             patch('camoufox.sync_api.Camoufox', side_effect=fake_camoufox):
            with youtube._launch_persistent(headless=False):
                pass
        self.assertTrue(captured['persistent_context'])
        self.assertEqual(captured['os'], 'windows')
        self.assertEqual(captured['humanize'], 1.2)
        self.assertEqual(captured['locale'], ['en-US', 'vi-VN'])
        self.assertTrue(captured['enable_cache'])
        self.assertIn('fingerprint_preset', captured)

        # Verify human typing, chunked description, hover-before-click, and mouse wheel scrolling.
        events = []

        class FakeKeyboard:
            def press(self, key):
                events.append(('press', key))
            def type(self, ch, delay=0):
                events.append(('type', ch, delay))
            def insert_text(self, txt):
                events.append(('insert_text', txt))

        class FakeMouse:
            def move(self, x, y, steps=1):
                events.append(('move', steps))
            def wheel(self, dx, dy):
                events.append(('wheel', dy))

        class FakeLocator:
            def __init__(self, text_value='', box=None):
                self._text = text_value
                self._box = box or {'x': 100, 'y': 100, 'width': 400, 'height': 300}
            @property
            def first(self):
                return self
            def count(self):
                return 1
            def is_visible(self):
                return True
            def wait_for(self, **kw):
                pass
            def scroll_into_view_if_needed(self, **kw):
                events.append(('scroll_into_view',))
            def hover(self, **kw):
                events.append(('hover',))
            def click(self, **kw):
                events.append(('click', kw.get('delay', 0)))
            def bounding_box(self):
                return self._box
            def inner_text(self):
                return self._text

        class FakePage:
            viewport_size = {'width': 1280, 'height': 720}
            keyboard = FakeKeyboard()
            mouse = FakeMouse()
            def wait_for_timeout(self, ms):
                pass
            def locator(self, sel):
                return FakeLocator()

        page = FakePage()
        youtube._human_move_and_click(page, FakeLocator(), context=None)
        self.assertIn(('hover',), events)
        click_delays = [e[1] for e in events if e[0] == 'click']
        self.assertTrue(click_delays and click_delays[0] >= 45)

        youtube._human_scroll(page, ['#scroll'])
        self.assertTrue(any(e[0] == 'wheel' and e[1] > 0 for e in events))

        # Short title uses char-by-char keyboard.type; already-matching text skips re-typing.
        events.clear()
        loc_title = FakeLocator(text_value='Learn vietnamese: Hello')
        self.assertTrue(youtube._fill_editable(page, loc_title, 'Learn vietnamese: Hello'))
        self.assertEqual(events, [])

        loc_empty = FakeLocator(text_value='Learn vietnamese: Hi')
        youtube._fill_editable(page, loc_empty, 'Learn vietnamese: Hi', chunked=False)
        # Returns immediately because normalized text matches; test non-matching target:
        events.clear()
        loc_old = FakeLocator(text_value='final')
        # FakeLocator returns 'final' on inner_text, so _fill_editable retries up to 3 times; verify char typing happened.
        youtube._fill_editable(page, loc_old, 'Xin chào', chunked=False)
        typed_chars = ''.join(e[1] for e in events if e[0] == 'type')
        self.assertTrue(typed_chars.startswith('Xin chào'))
        self.assertTrue(all(e[2] >= 35 for e in events if e[0] == 'type'))

        # Long multi-line description uses insert_text per line + char-by-char hashtags.
        events.clear()
        long_desc = 'Topic: Greetings\n\n' + ('- Xin chào — Hello\n' * 10) + '#learnvietnamese'
        youtube._fill_editable(page, FakeLocator(text_value=''), long_desc, chunked=True)
        self.assertTrue(any(e[0] == 'insert_text' and 'Topic: Greetings' in e[1] for e in events))
        self.assertTrue(any(e[0] == 'type' and e[1] == '#' for e in events))


if __name__ == '__main__':
    unittest.main()
