"""Real disposable Git staging/commits; remote transport is mocked (no network)."""
import contextlib
import io
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import sync_github as sync
from scripts import restart_vietcut as restart

class AutoSyncTests(unittest.TestCase):
 def setUp(self):
  self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)/'workspace';self.root.mkdir();self.remote=Path(self.tmp.name)/'remote.git'
  self.git('init','-b','main');self.git('config','user.name','VietCut test');self.git('config','user.email','test@example.invalid')
  (self.root/'.gitignore').write_text('data/\nOUTPUT/\n.env\n',encoding='utf-8')
  (self.root/'README.md').write_text('synthetic initial source',encoding='utf-8')
  self.git('add','.gitignore','README.md');self.git('commit','-m','initial');self.git('remote','add','origin',str(self.remote));self.remote_head=self.git('rev-parse','HEAD');self.offline=False;self.native_git=sync.git;self.transport_patch=patch.object(sync,'git',side_effect=self.transport);self.transport_patch.start();self.addCleanup(self.transport_patch.stop)
  self.expected=patch.object(sync,'EXPECTED_REMOTES',{str(self.remote)});self.expected.start();self.addCleanup(self.expected.stop)
 def git(self,*args):
  result=subprocess.run(['git',*args],cwd=self.root,capture_output=True)
  if result.returncode:raise AssertionError(result.stderr.decode('utf-8',errors='replace'))
  return result.stdout.decode('utf-8').strip()
 def transport(self,root,*args,**kwargs):
  if args[0] in {'ls-remote','push'}:
   if self.offline:raise sync.SyncError('Synthetic remote offline')
   if args[0]=='push':
    head=self.git('rev-parse','HEAD')
    result=subprocess.run(['git','merge-base','--is-ancestor',self.remote_head,head],cwd=self.root,capture_output=True)
    if result.returncode:raise sync.SyncError('Synthetic non-fast-forward rejection')
    self.remote_head=head
    return b''
   return (self.remote_head+'\trefs/heads/main\n').encode()
  return self.native_git(root,*args,**kwargs)
 def write(self,name,text='synthetic code'):
  path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8');return path
 def run_sync(self):
  out=io.StringIO()
  with contextlib.redirect_stdout(out):result=sync.safe_sync(self.root)
  return result,out.getvalue()
 def test_new_modified_deleted_source_pushed_without_runtime_or_internal_files(self):
  self.write('README.md','updated');self.write('frontend/editor.ts','export const value=1;');self.write('data/project.json');self.write('OUTPUT/movie.mp4');self.write('.env','TEST_API_KEY=synthetic-private-value-123456789');self.write('.codex/settings.json');self.write('unrelated-notes.txt')
  ok,output=self.run_sync();self.assertTrue(ok,output)
  files=self.git('ls-tree','-r','--name-only','HEAD').splitlines()
  self.assertIn('frontend/editor.ts',files);self.assertNotIn('data/project.json',files);self.assertNotIn('.env',files);self.assertNotIn('.codex/settings.json',files);self.assertNotIn('unrelated-notes.txt',files)
  self.assertEqual(self.git('rev-parse','HEAD'),self.remote_head)
  (self.root/'frontend/editor.ts').rename(self.root/'frontend/renamed.ts')
  ok,output=self.run_sync();self.assertTrue(ok,output);files=self.git('ls-tree','-r','--name-only','HEAD').splitlines();self.assertNotIn('frontend/editor.ts',files);self.assertIn('frontend/renamed.ts',files)
 def test_clean_run_does_not_create_a_commit(self):
  head=self.git('rev-parse','HEAD');ok,output=self.run_sync();self.assertTrue(ok,output);self.assertEqual(head,self.git('rev-parse','HEAD'))
 def test_configured_secret_in_source_blocks_commit_and_is_not_printed(self):
  head=self.git('rev-parse','HEAD');secret='synthetic-private-value-123456789';self.write('.env','TEST_API_KEY='+secret);self.write('frontend/editor.ts','export const key="'+secret+'";')
  ok,output=self.run_sync();self.assertFalse(ok);self.assertEqual(head,self.git('rev-parse','HEAD'));self.assertNotIn(secret,output);self.assertIn('frontend/editor.ts',self.git('diff','--cached','--name-only'))
 def test_pre_staged_private_file_blocks_all_commits_without_unstaging_user_files(self):
  head=self.git('rev-parse','HEAD');self.write('.env','TEST_API_KEY=synthetic-private-value-123456789');self.git('add','-f','.env');self.write('README.md','changed')
  ok,output=self.run_sync();self.assertFalse(ok);self.assertEqual(head,self.git('rev-parse','HEAD'));self.assertEqual('.env',self.git('diff','--cached','--name-only'))
 def test_non_main_and_wrong_remote_are_refused(self):
  head=self.git('rev-parse','HEAD');self.git('checkout','-b','other');self.write('README.md','changed');self.assertFalse(self.run_sync()[0]);self.assertEqual(head,self.git('rev-parse','HEAD'))
  self.git('checkout','main');self.git('remote','set-url','--push','origin','https://example.invalid/other.git');self.assertFalse(self.run_sync()[0]);self.assertEqual(head,self.git('rev-parse','HEAD'))
 def test_failed_network_keeps_commit_and_next_clean_run_retries_without_duplicate_commit(self):
  self.write('README.md','changed');head=self.git('rev-parse','HEAD');self.offline=True
  ok,output=self.run_sync();self.assertFalse(ok);committed=self.git('rev-parse','HEAD');self.assertNotEqual(head,committed)
  self.offline=False;ok,output=self.run_sync();self.assertTrue(ok,output);self.assertEqual(committed,self.git('rev-parse','HEAD'));self.assertEqual(committed,self.remote_head)
 def test_remote_ahead_is_not_pulled_or_force_pushed(self):
  head=self.git('rev-parse','HEAD');tree=self.git('rev-parse','HEAD^{tree}')
  self.remote_head=self.git('commit-tree',tree,'-p',head,'-m','Synthetic remote-only commit')
  remote=self.remote_head;ok,output=self.run_sync();self.assertFalse(ok);self.assertEqual(head,self.git('rev-parse','HEAD'));self.assertEqual(remote,self.remote_head)
 def test_restart_continues_when_sync_fails_and_preserves_error_exit(self):
  for synced in [False,True]:
   with patch.object(sync,'safe_sync',return_value=synced) as publish,patch.object(restart,'restart') as launch:
    self.assertEqual(restart.main(sync_github=True),0 if synced else 1);publish.assert_called_once_with(restart.ROOT);launch.assert_called_once()
  with patch.object(sync,'safe_sync') as publish,patch.object(restart,'restart') as launch:
   self.assertEqual(restart.main(),0);publish.assert_not_called();launch.assert_called_once()
 def test_concurrent_sync_is_refused_without_changing_head(self):
  head=self.git('rev-parse','HEAD')
  with sync.sync_lock(self.root):
   ok,output=self.run_sync();self.assertFalse(ok);self.assertEqual(head,self.git('rev-parse','HEAD'))
 def test_merge_in_progress_is_not_committed_or_pushed(self):
  head=self.git('rev-parse','HEAD');self.write('.git/MERGE_HEAD',head);self.write('README.md','changed')
  ok,output=self.run_sync();self.assertFalse(ok);self.assertEqual(head,self.git('rev-parse','HEAD'));self.assertEqual('',self.git('diff','--cached','--name-only'))
 def test_source_policy_excludes_runtime_secrets_unknown_files_and_unsafe_paths(self):
  for path in ['.env','data/p.json','backend/cache/p.py','.codex/config.json','frontend/projects/p.ts','tests/fixture.mp4','custom.json','../README.md','/README.md']:
   self.assertFalse(sync.eligible(path),path)
  for path in ['.env.example','frontend/example.ts','scripts/sync_github.py','KHOI_DONG_LAI_VIETCUT.cmd','assets/vietcut.ico']:
   self.assertTrue(sync.eligible(path),path)

if __name__=='__main__':unittest.main()
