import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend import store
from backend.seo import lesson_title, repaired_title, title, video_filename


class ProjectTitlesTests(unittest.TestCase):
    def project(self, **changes):
        return {'id': store.uid(), 'title': 'Bài học luyện số 1 qua ví dụ đếm một quả cam và một quả táo. Người dạy đọc mẫu chậm, hướng dẫn người học nói theo.',
                'title_mode': 'auto', 'revision': 4, 'created_at': '2026-01-01T00:00:00+00:00', 'updated_at': 'unchanged',
                'plan': {'summary': 'Bài học luyện số 1 qua ví dụ đếm một quả cam và một quả táo. Người dạy đọc mẫu chậm, hướng dẫn người học nói theo.',
                         'lessons': [{'vi': 'Một quả cam'}, {'vi': 'Một quả táo'}]},
                'options': {'layout_mode': 'lesson'}, 'export': {'file': 'old.mp4'}, **changes}

    def test_long_summary_uses_short_targets_and_same_export_name(self):
        p = self.project()
        self.assertEqual(lesson_title(p), 'Một quả cam · Một quả táo')
        self.assertEqual(video_filename(p), 'Một quả cam · Một quả táo - learn vietnamese.mp4')
        self.assertEqual(repaired_title(p), title(p))
        p['plan']['summary'] = 'Đếm trái cây'
        self.assertEqual(lesson_title(p), 'Đếm trái cây')
        p['plan']['lessons'] = [{'vi': 'Cảm ơn'}, {'vi': 'Cảm ơn'}]
        self.assertEqual(lesson_title(p), 'Cảm ơn')
        p['plan']['lessons'] = [{'vi': 'Người dạy'}]
        self.assertEqual(lesson_title(p), 'Người dạy')

    def test_bounds_diacritics_and_instruction_rejection(self):
        p = self.project()
        p['plan'].update(summary='Người dạy đọc mẫu chậm', lessons=[{'vi': s} for s in ['ma', 'má', 'mà', 'mả']])
        self.assertEqual(lesson_title(p), 'ma · má · mà')
        p['plan']['lessons'] = [{'vi': 'một câu quá dài ' * 15, 'chunks': [{'vi': 'Một quả cam'}]}]
        self.assertEqual(lesson_title(p), 'Một quả cam')
        p['plan']['lessons'][0]['chunks'] = []
        self.assertEqual(lesson_title(p), 'Luyện câu tiếng Việt')
        self.assertLessEqual(len(lesson_title(p)), 60)

    def test_manual_and_unrecognized_legacy_titles_are_preserved(self):
        p = self.project(title_mode='manual')
        self.assertIsNone(repaired_title(p))
        self.assertEqual(title(p), p['title'])
        p.pop('title_mode')
        self.assertIsNotNone(repaired_title(p))
        p['title'] = 'Tên do tôi đặt ' * 8
        self.assertIsNone(repaired_title(p))
        p['plan'] = None
        self.assertIsNone(repaired_title(p))

    def test_migration_and_future_saves_preserve_everything_except_name(self):
        with TemporaryDirectory() as tmp, patch.object(store, 'data_root', return_value=Path(tmp)):
            store.init()
            original = self.project()
            # Seed old data directly; the new save path already normalizes titles.
            others = [self.project(title_mode='manual'), self.project(diagnostic=True),
                      self.project(_retention={'state': 'trashed'}), self.project()]
            with store.connect() as db:
                for p in [original, *others]:
                    db.execute('INSERT INTO projects VALUES (?,?,?)', (p['id'], json.dumps(p), 'db-timestamp'))
            job = store.job_create(others[-1]['id'], 'pipeline')
            self.assertEqual(store.repair_project_titles(), 1)
            expected = {**original, 'title': 'Một quả cam · Một quả táo'}
            self.assertEqual(store.read(original['id']), expected)
            for p in others:
                self.assertEqual(store.read(p['id'], True), p)
            self.assertEqual(store.repair_project_titles(), 0)
            with store.connect() as db:
                self.assertEqual(db.execute('SELECT updated FROM projects WHERE id=?', (original['id'],)).fetchone()[0], 'db-timestamp')
            store.job_update(job['id'], status='succeeded')
            self.assertEqual(store.repair_project_titles(), 1)
            p = copy.deepcopy(original)
            store.save(p)
            self.assertEqual(p['title'], expected['title'])
            self.assertEqual(p['revision'], original['revision'])
            self.assertEqual(p['plan'], original['plan'])


if __name__ == '__main__':
    unittest.main()
