"""Publish source changes on an explicitly user-invoked VietCut restart."""
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import verify_staged

EXPECTED_REMOTES={'https://github.com/ngonco/daytiengviet.git','git@github.com:ngonco/daytiengviet.git'}
ROOT_FILES={'.env.example','.gitignore','.gitattributes','AGENTS.md','README.md','BAO_CAO_KIEM_THU.md','HUONG_DAN_GPU.md','system_map_daytiengviet.md','requirements.txt','package.json','package-lock.json','tsconfig.json','vite.config.ts','start.py','launch_vietcut.pyw','CAI_DAT.cmd','CAI_DAT_XOA_PHONG.cmd','KHOI_DONG_LAI_VIETCUT.cmd','MO_VIETCUT.cmd','TAO_BIEU_TUONG_START.cmd'}
SOURCE_DIRS={'backend','frontend','scripts','tests'}
SOURCE_SUFFIXES={'.py','.pyw','.ts','.tsx','.mjs','.js','.css','.html','.md'}
PRIVATE_PARTS={'.git','.codex','.agents','.aws','.venv','node_modules','data','output','dist','__pycache__','.pytest_cache','cache','caches','exports','recordings','projects'}

class SyncError(RuntimeError):pass

def eligible(name):
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or any(p.casefold() in PRIVATE_PARTS for p in path.parts):return False
    if name in ROOT_FILES:return True
    if path.name.startswith('.env'):return False
    if path.parts[0] in SOURCE_DIRS:return path.suffix.lower() in SOURCE_SUFFIXES
    # Only the versioned app's static asset locations; never arbitrary user images.
    if path.parts[0]=='assets':return name in {'assets/vietcut.ico','assets/frame_brand.json'} or (len(path.parts)==3 and path.parts[1] in {'fonts','licenses'} and path.suffix.lower() in {'.ttf','.txt','.md'})
    return False

def git(root,*args,timeout=30):
    env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GCM_INTERACTIVE':'Never'}
    try:result=subprocess.run(['git',*args],cwd=root,env=env,capture_output=True,timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except (OSError,subprocess.TimeoutExpired):raise SyncError('Git khong san sang hoac het thoi gian cho; se thu lai lan khoi dong sau.') from None
    if result.returncode:raise SyncError('Lenh git '+args[0]+' that bai. Kiem tra quyen ghi, dang nhap GitHub va ket noi mang; khong force-push.')
    return result.stdout

def paths(raw):return [p for p in raw.decode('utf-8').split('\0') if p]

@contextmanager
def sync_lock(root):
    directory=root/'data';directory.mkdir(exist_ok=True)
    with (directory/'github-sync.lock').open('a+b') as handle:
        if handle.tell()==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:raise SyncError('Mot lan dong bo GitHub khac dang chay; lan nay se chi khoi dong lai VietCut.') from None
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle,fcntl.LOCK_UN)

def synchronize(root=ROOT):
    root=Path(root)
    with sync_lock(root):
        if git(root,'rev-parse','--show-toplevel').decode().strip().casefold()!=str(root.resolve()).replace('\\','/').casefold():raise SyncError('Thu muc Git khong trung thu muc VietCut; bo qua dong bo.')
        if git(root,'symbolic-ref','--short','HEAD').decode().strip()!='main':raise SyncError('Chi tu dong dong bo nhanh main; khong doi nhanh hien tai.')
        for args in [('remote','get-url','--all','origin'),('remote','get-url','--push','--all','origin')]:
            urls=git(root,*args).decode().splitlines()
            if len(urls)!=1 or urls[0] not in EXPECTED_REMOTES:raise SyncError('Origin khong phai kho GitHub VietCut da chi dinh; khong commit/push.')
        if git(root,'ls-files','-u','-z'):raise SyncError('Git dang co xung dot; can xu ly thu cong truoc khi dong bo.')
        for marker in ['MERGE_HEAD','CHERRY_PICK_HEAD','REVERT_HEAD','rebase-merge','rebase-apply']:
            path=Path(git(root,'rev-parse','--git-path',marker).decode().strip())
            if (path if path.is_absolute() else root/path).exists():raise SyncError('Git dang merge/rebase; khong tu dong commit/push.')
        staged=paths(git(root,'diff','--cached','--name-only','--no-renames','-z'))
        if any(not eligible(p) for p in staged):raise SyncError('Vung staged co tep ngoai ma nguon cho phep. Kiem tra git --no-pager diff --cached --name-only; khong commit/push.')
        changed=paths(git(root,'diff','HEAD','--name-only','--no-renames','-z'))+paths(git(root,'ls-files','--others','--exclude-standard','-z'))
        selected=sorted({p for p in changed if eligible(p)})
        if selected:git(root,'add','-A','--',*selected)
        staged=paths(git(root,'diff','--cached','--name-only','--no-renames','-z'))
        if staged:
            if any(not eligible(p) for p in staged) or verify_staged.verify(root)!=0:raise SyncError('Kiem tra du lieu rieng/khoa API khong dat; khong commit/push. Tep staged duoc giu de kiem tra.')
            git(root,'commit','-m','Auto-sync VietCut changes on restart')
            print(f'GitHub: da commit {len(staged)} tep ma nguon/tai lieu.')
        head=git(root,'rev-parse','HEAD').decode().strip()
        remote=git(root,'ls-remote','origin','refs/heads/main',timeout=45).decode().split()
        if not remote or remote[0]!=head:
            git(root,'push','origin','main',timeout=45)
            remote=git(root,'ls-remote','origin','refs/heads/main',timeout=45).decode().split()
            if not remote or remote[0]!=head:raise SyncError('Chua xac nhan duoc GitHub trung commit tren may; se thu lai lan sau.')
            print('GitHub: da push va xac nhan main = '+head[:8]+'.')
        else:print('GitHub: khong co thay doi can day; main da dong bo ('+head[:8]+').')
        return True

def safe_sync(root=ROOT):
    try:return synchronize(root)
    except (SyncError,OSError,ValueError,subprocess.SubprocessError) as exc:
        print('GitHub: '+(str(exc) if isinstance(exc,SyncError) else 'Dong bo chua hoan tat; kiem tra Git va thu lai lan sau.'))
        print('GitHub: van tiep tuc khoi dong lai VietCut; commit da tao (neu co) duoc giu nguyen.')
        return False

if __name__=='__main__':raise SystemExit(0 if safe_sync() else 1)
