from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend import store,retention
from backend.app import app


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name)
        self.mock=patch('backend.store.data_root',return_value=self.root);self.mock.start();store.init()
        self.now=datetime.now(timezone.utc)
    def tearDown(self):self.mock.stop();self.tmp.cleanup()
    def add(self,i,diagnostic=False):
        pid=f'{i:016x}';folder=store.folder(pid);(folder/'source.mp4').write_bytes(b'private source');(folder/'renders').mkdir();(folder/'renders/export.mp4').write_bytes(b'private export')
        store.save({'id':pid,'title':str(i),'created_at':(self.now-timedelta(days=100-i)).isoformat(),'diagnostic':diagnostic,'status':'ready','revision':1,'plan':None,'options':{}})
        return pid
    def test_29_30_31_and_creation_date_not_last_edit(self):
        ids=[self.add(i) for i in range(1,30)]
        self.assertEqual(retention.sweep()['moved'],[])
        ids.append(self.add(30));self.assertEqual(retention.sweep()['moved'],[])
        store.update(ids[0],title='Edited most recently')
        ids.append(self.add(31));result=retention.sweep(at=self.now)
        self.assertEqual(result['moved'],[ids[0]]);self.assertEqual(len(store.listing()),30)
        self.assertEqual((self.root/'trash'/ids[0]/'source.mp4').read_bytes(),b'private source')
        self.assertTrue((self.root/'trash'/ids[0]/'renders/export.mp4').is_file())
        with self.assertRaises(store.TrashedProject):store.read(ids[0])
        with self.assertRaises(store.TrashedProject):store.folder(ids[0])
        with self.assertRaises(store.TrashedProject):store.job_create(ids[0],'preview')
        self.assertFalse((self.root/'projects'/ids[0]).exists())
    def test_busy_and_diagnostic_projects_are_protected(self):
        ids=[self.add(i) for i in range(1,32)];diag=self.add(999,True)
        job=store.job_create(ids[0],'export')
        result=retention.sweep();self.assertEqual(result['moved'],[ids[1]])
        self.assertEqual(store.read(diag)['id'],diag);store.job_update(job['id'],status='succeeded')
        self.add(32);self.assertEqual(retention.sweep()['moved'],[ids[0]])
    def test_windows_rename_failure_keeps_unmoved_project_active(self):
        ids=[self.add(i) for i in range(1,32)];real_rename=Path.rename
        def rename(path,target):
            if path.name==ids[0]:raise PermissionError('File is in use')
            return real_rename(path,target)
        with patch('pathlib.Path.rename',rename):result=retention.sweep()
        self.assertTrue(result['warnings']);self.assertEqual(result['moved'],[ids[1]])
        self.assertEqual(store.read(ids[0])['id'],ids[0]);self.assertTrue(store.folder(ids[0]).is_dir())
    def test_all_busy_can_temporarily_exceed_limit_then_clean(self):
        ids=[self.add(i) for i in range(1,32)];jobs=[store.job_create(p,'preview') for p in ids]
        self.assertEqual(retention.sweep()['moved'],[]);self.assertEqual(len(store.listing()),31)
        store.job_update(jobs[0]['id'],status='succeeded');self.assertEqual(retention.sweep()['moved'],[ids[0]])
    def test_restore_when_full_keeps_created_date_and_swaps_another(self):
        ids=[self.add(i) for i in range(1,32)];created=store.read(ids[0])['created_at'];retention.sweep()
        p=retention.restore(ids[0]);self.assertEqual(p['created_at'],created)
        self.assertEqual(len(store.listing()),30);self.assertEqual(retention.trash_list()[0]['id'],ids[1])
        self.assertEqual((store.folder(ids[0])/'source.mp4').read_bytes(),b'private source')
    def test_purge_after_seven_days_only_never_touches_external_files(self):
        ids=[self.add(i) for i in range(1,32)];external=self.root/'external-original.mp4';external.write_bytes(b'original')
        retention.sweep(at=self.now)
        retention.sweep(at=self.now+timedelta(days=7)-timedelta(seconds=1));self.assertTrue((self.root/'trash'/ids[0]).exists())
        result=retention.sweep(at=self.now+timedelta(days=7));self.assertEqual(result['purged'],[ids[0]])
        with self.assertRaises(KeyError):store.read(ids[0],True)
        self.assertEqual(external.read_bytes(),b'original')
    def test_interrupted_archive_restore_and_purge_recover(self):
        pid=self.add(1);p=store.read(pid);info={'state':'archiving','deleted_at':self.now.isoformat(),'purge_after':(self.now+timedelta(days=7)).isoformat()}
        p['_retention']=info;store.save(p);retention.sweep();self.assertTrue((self.root/'trash'/pid).is_dir())
        p=store.read(pid,True);p['_retention']['state']='restoring';store.save(p);retention.sweep();self.assertTrue(store.folder(pid).is_dir())
        p=store.read(pid);p['_retention']=info;store.save(p);retention.sweep()
        p=store.read(pid,True);p['_retention']['state']='purging';store.save(p)
        self.assertTrue(retention.sweep(at=self.now)['warnings'])
        self.assertTrue((self.root/'trash'/pid).is_dir())
        retention.sweep(at=self.now+timedelta(days=8))
        with self.assertRaises(KeyError):store.read(pid,True)
    def test_bad_paths_and_reparse_points_are_rejected(self):
        for pid in ['../external','x'*15,'x'*17,'a'*15+'/']:
            with self.assertRaises(ValueError):retention.safe_path(pid,'trash')
        pid=self.add(1);outside=self.root/'outside';outside.mkdir()
        trash=self.root/'trash';trash.mkdir();target=trash/pid
        try:os.symlink(outside,target,target_is_directory=True)
        except OSError:
            import subprocess
            created=subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(target),str(outside)],capture_output=True)
            self.assertEqual(created.returncode,0,created.stderr.decode(errors='replace'))
        try:
            with self.assertRaises(ValueError):retention.safe_path(pid,'trash')
        finally:os.rmdir(target)

    def test_nested_junction_blocks_purge_without_touching_target(self):
        import subprocess
        ids=[self.add(i) for i in range(1,32)];retention.sweep(at=self.now)
        outside=self.root/'external';outside.mkdir();(outside/'keep.txt').write_text('keep')
        link=self.root/'trash'/ids[0]/'linked'
        created=subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(link),str(outside)],capture_output=True)
        self.assertEqual(created.returncode,0)
        try:
            result=retention.sweep(at=self.now+timedelta(days=8))
            self.assertEqual(result['purged'],[]);self.assertTrue(result['warnings'])
            self.assertEqual((outside/'keep.txt').read_text(),'keep')
        finally:os.rmdir(link)
    def test_api_trash_blocks_reads_and_jobs_then_restores(self):
        ids=[self.add(i) for i in range(1,32)];retention.sweep();client=TestClient(app)
        self.assertEqual(client.get(f'/api/projects/{ids[0]}').status_code,410)
        self.assertEqual(client.post(f'/api/projects/{ids[0]}/jobs/pipeline').status_code,410)
        self.assertEqual(client.get('/api/trash').json()[0]['id'],ids[0])
        restored=client.post(f'/api/trash/{ids[0]}/restore');self.assertEqual(restored.status_code,200,restored.text)
        self.assertEqual(restored.json()['id'],ids[0])


if __name__=='__main__':unittest.main()
