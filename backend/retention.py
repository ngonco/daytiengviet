"""Recoverable 30-project retention. All filesystem mutations are root checked."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import os
import shutil
import stat
from . import store

LIMIT=30
DAYS=7
ACTIVE_JOBS={'queued','running','cancelling'}


def timestamp(value):
    try:
        result=datetime.fromisoformat(value.replace('Z','+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (ValueError,AttributeError,TypeError):return datetime.min.replace(tzinfo=timezone.utc)


def safe_path(project_id,location):
    if len(project_id)!=16 or not project_id.isalnum() or location not in ['projects','trash']:
        raise ValueError('Đường dẫn lưu dự án không hợp lệ.')
    root=store.data_root().resolve();parent=root/location;path=parent/project_id
    # Reject all reparse points (including Windows junctions), even ones that currently point inside root.
    for node in [parent,path]:
        if node.exists() or node.is_symlink():
            flags=node.lstat()
            if node.is_symlink() or getattr(flags,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024):
                raise ValueError('Không thao tác trên liên kết hoặc junction của dự án.')
    if parent.resolve()!=root/location or path.resolve().parent!=parent.resolve():
        raise ValueError('Đường dẫn vượt thư mục dữ liệu dự án.')
    return path


def busy(project_id):return any(j['status'] in ACTIVE_JOBS for j in store.jobs(project_id))


def _rollback_unmoved(project):
    """An open file can block a Windows rename. Keep that project active if nothing moved."""
    if project.get('_retention',{}).get('state')!='archiving':return
    source=safe_path(project['id'],'projects');trash=safe_path(project['id'],'trash')
    if source.exists() and not trash.exists():
        project.pop('_retention',None);store.save(project)


def _finish(project,at=None):
    """Idempotent completion of a journaled move/purge after interruption."""
    info=project.get('_retention',{});state=info.get('state','active');pid=project['id']
    source=safe_path(pid,'projects');trash=safe_path(pid,'trash')
    if state in ['archiving','restoring']:
        origin,target=(source,trash) if state=='archiving' else (trash,source)
        if origin.exists() and target.exists():raise ValueError('Có hai thư mục dự án; cần kiểm tra trước khi khôi phục.')
        if origin.exists():
            target.parent.mkdir(parents=True,exist_ok=True)
            origin.rename(target)
        if state=='archiving':project['_retention']={**info,'state':'trashed'}
        else:project.pop('_retention',None)
        store.save(project)
    elif state=='purging':
        deadline=timestamp(info.get('purge_after'))
        if deadline==datetime.min.replace(tzinfo=timezone.utc) or deadline>(at or datetime.now(timezone.utc)):
            raise ValueError('Chưa đủ thời hạn 7 ngày; chưa xóa dự án trong Thùng rác.')
        if source.exists():raise ValueError('Không xóa khi dự án vẫn có thư mục đang hoạt động.')
        if trash.exists():
            # Never traverse nested symlinks/junctions during a recursive delete.
            for directory,dirs,files in os.walk(trash,followlinks=False):
                for name in dirs+files:
                    node=Path(directory)/name;attributes=node.lstat()
                    if node.is_symlink() or getattr(attributes,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024):
                        raise ValueError('Thùng rác có liên kết; chưa xóa để bảo vệ tệp ngoài dự án.')
            # Recheck the resolved target immediately before recursive deletion.
            checked=safe_path(pid,'trash')
            if checked.resolve()!=trash.resolve():raise ValueError('Đường dẫn thùng rác đã đổi.')
            shutil.rmtree(checked)
        with store.connect() as conn:
            conn.execute('DELETE FROM jobs WHERE project_id=?',(pid,))
            conn.execute('DELETE FROM projects WHERE id=?',(pid,))


def sweep(protect=None,at=None):
    at=at or datetime.now(timezone.utc);notes=[];moved=[];purged=[];protected={protect}
    with store.LOCK:
        for project in store.listing(True):
            if project.get('diagnostic') or busy(project['id']):continue
            state=project.get('_retention',{}).get('state','active')
            if state in ['archiving','restoring','purging']:
                try:
                    _finish(project,at)
                    if state=='restoring':protected.add(project['id'])
                except (OSError,ValueError) as exc:
                    notes.append(str(exc))
                    try:_rollback_unmoved(project)
                    except (OSError,ValueError):pass
        for project in store.listing(True):
            info=project.get('_retention',{})
            if project.get('diagnostic') or info.get('state')!='trashed' or busy(project['id']):continue
            deadline=timestamp(info.get('purge_after'))
            if deadline==datetime.min.replace(tzinfo=timezone.utc):
                notes.append('Dự án trong Thùng rác thiếu hạn xóa; cần kiểm tra trước khi xóa.');continue
            if deadline<=at:
                try:
                    safe_path(project['id'],'trash');project['_retention']={**info,'state':'purging'};store.save(project);_finish(project,at);purged.append(project['id'])
                except (OSError,ValueError) as exc:notes.append(str(exc))
        active=[p for p in store.listing() if not p.get('diagnostic')]
        eligible=sorted([p for p in active if p['id'] not in protected and not busy(p['id'])],key=lambda p:(timestamp(p.get('created_at') or p.get('updated_at')),p['id']))
        for project in eligible:
            if len(active)-len(moved)<=LIMIT:break
            try:
                source=safe_path(project['id'],'projects');target=safe_path(project['id'],'trash')
                if target.exists():raise ValueError('Thư mục Thùng rác đã có dữ liệu; chưa chuyển dự án.')
                project['_retention']={'state':'archiving','deleted_at':at.isoformat(),'purge_after':(at+timedelta(days=DAYS)).isoformat()}
                store.save(project);_finish(project);moved.append(project['id'])
            except (OSError,ValueError) as exc:
                notes.append(str(exc))
                try:_rollback_unmoved(project)
                except (OSError,ValueError):pass
    return {'moved':moved,'purged':purged,'warnings':notes,'limit':LIMIT}


def trash_list():
    return [{'id':p['id'],'title':p.get('title','Bài học'),'created_at':p.get('created_at'),**p['_retention']} for p in store.listing(True) if p.get('_retention',{}).get('state') in ['trashed','archiving','purging'] and not p.get('diagnostic')]


def restore(project_id):
    with store.LOCK:
        project=store.read(project_id,True)
        info=project.get('_retention',{})
        if info.get('state')!='trashed':raise ValueError('Dự án không còn trong Thùng rác hoặc đang được dọn.')
        if timestamp(info.get('purge_after'))<=datetime.now(timezone.utc):raise ValueError('Dự án đã hết hạn khôi phục 7 ngày.')
        safe_path(project_id,'trash');target=safe_path(project_id,'projects')
        if target.exists():raise ValueError('Đã có thư mục dự án đang hoạt động; chưa khôi phục để tránh ghi đè.')
        project['_retention']={**info,'state':'restoring'};store.save(project)
        try:_finish(project)
        except OSError as exc:
            if safe_path(project_id,'trash').exists() and not target.exists():
                project['_retention']=info;store.save(project)
            raise ValueError('Tệp dự án đang được sử dụng. Hãy thử khôi phục lại sau.') from exc
        sweep(protect=project_id)
        return store.read(project_id)
