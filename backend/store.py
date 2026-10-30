import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .config import data_root

LOCK = threading.RLock()

class TrashedProject(RuntimeError):
    pass

def now():
    return datetime.now(timezone.utc).isoformat()

def uid():
    return uuid.uuid4().hex[:16]

@contextmanager
def connect():
    connection = sqlite3.connect(data_root() / 'studio.sqlite', timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA journal_mode=WAL')
    try:
        with connection:
            yield connection
    finally:
        connection.close()

def init():
    with connect() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '', error TEXT, request TEXT NOT NULL DEFAULT '{}', created TEXT NOT NULL, updated TEXT NOT NULL);
        ''')
        conn.execute("UPDATE jobs SET status='queued', message='Tiếp tục sau khi khởi động lại', updated=? WHERE status='running'", (now(),))
        conn.execute("UPDATE jobs SET status='cancelled', message='Đã hủy trước khi khởi động lại', updated=? WHERE status='cancelling'", (now(),))

def folder(project_id):
    if not project_id.isalnum() or len(project_id) != 16:
        raise ValueError('Mã dự án không hợp lệ')
    try:read(project_id)
    except KeyError:pass
    path = data_root() / 'projects' / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path

def read(project_id,include_trashed=False):
    with connect() as conn:
        row = conn.execute('SELECT data FROM projects WHERE id=?', (project_id,)).fetchone()
    if not row:
        raise KeyError('Không tìm thấy dự án')
    project=json.loads(row['data'])
    if not include_trashed and project.get('_retention',{}).get('state','active')!='active':
        raise TrashedProject('Dự án đã được chuyển vào Thùng rác. Khôi phục để tiếp tục chỉnh sửa.')
    return project

def save(project):
    project['updated_at'] = now()
    with LOCK, connect() as conn:
        conn.execute('INSERT INTO projects VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated=excluded.updated', (project['id'], json.dumps(project, ensure_ascii=False), project['updated_at']))

def update(project_id, **changes):
    with LOCK:
        project = read(project_id)
        project.update(changes)
        save(project)
        return project

def listing(include_trashed=False):
    with connect() as conn:
        rows = conn.execute('SELECT data FROM projects ORDER BY updated DESC').fetchall()
    projects=[json.loads(row['data']) for row in rows]
    return projects if include_trashed else [p for p in projects if p.get('_retention',{}).get('state','active')=='active']

def jobs(project_id=None):
    with connect() as conn:
        rows = conn.execute('SELECT * FROM jobs ' + ('WHERE project_id=? ' if project_id else '') + 'ORDER BY created DESC', (project_id,) if project_id else ()).fetchall()
    return [dict(row) for row in rows]

def job_read(job_id):
    with connect() as conn:
        row = conn.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    return dict(row) if row else None

def job_update(job_id, **changes):
    allowed = {'status', 'progress', 'message', 'error'}
    assert set(changes) <= allowed
    changes['updated'] = now()
    with connect() as conn:
        conn.execute('UPDATE jobs SET ' + ','.join(k + '=?' for k in changes) + ' WHERE id=?', (*changes.values(), job_id))

def job_create(project_id, kind, request=None):
    with LOCK, connect() as conn:
        read(project_id)
        active = conn.execute("SELECT id FROM jobs WHERE project_id=? AND status IN ('queued','running','cancelling')", (project_id,)).fetchone()
        if active:
            raise ValueError('Dự án đang có tác vụ; hãy đợi hoặc hủy trước.')
        job_id = uid()
        conn.execute('INSERT INTO jobs (id,project_id,kind,status,request,created,updated) VALUES (?,?,?,?,?,?,?)', (job_id, project_id, kind, 'queued', json.dumps(request or {}), now(), now()))
    return job_read(job_id)

def atomic_json(path: Path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)
