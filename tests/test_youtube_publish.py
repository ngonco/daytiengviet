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


if __name__ == '__main__':
    unittest.main()
