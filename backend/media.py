import json
import subprocess
import time
import re
import math
from pathlib import Path
from .config import binary, ROOT

class Cancelled(Exception):
    pass

def run(command, context=None, cwd=None):
    """Drain stderr to disk, keeping media jobs cancellable and memory bounded."""
    import tempfile
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors, cwd=cwd, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            while process.poll() is None:
                if context:
                    context.check()
                time.sleep(0.15)
        except BaseException:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise
        if process.returncode:
            errors.seek(0, 2)
            length = errors.tell()
            errors.seek(max(0, length - 3500))
            detail = errors.read().decode('utf-8', 'replace')
            # Local FFmpeg diagnostics contain no provider credentials.
            raise RuntimeError('FFmpeg không xử lý được video: ' + detail[-2000:])

def ffmpeg(arguments, context=None, cwd=None):
    return run([binary('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-y', '-threads', '2', *map(str, arguments)], context, cwd)

def probe(path):
    response = subprocess.run([binary('ffprobe'), '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)], capture_output=True, timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if response.returncode:
        raise ValueError('Không đọc được video. Hãy chọn tệp video hợp lệ.')
    raw = json.loads(response.stdout)
    video = next((s for s in raw['streams'] if s['codec_type'] == 'video'), None)
    audio = next((s for s in raw['streams'] if s['codec_type'] == 'audio'), None)
    if not video or not audio:
        raise ValueError('Video cần có cả hình ảnh và âm thanh.')
    duration = float(raw['format'].get('duration', 0))
    if not 0.5 <= duration <= 3600.1:
        raise ValueError('App hỗ trợ video từ 0,5 giây tới 60 phút.')
    width, height = video['width'], video['height']
    rotation = next((abs(int(s.get('rotation', 0))) for s in video.get('side_data_list', []) if 'rotation' in s), 0)
    if rotation % 180:
        width, height = height, width
    return {'duration': duration, 'width': width, 'height': height, 'fps': video.get('avg_frame_rate', '30/1'), 'audio_channels': audio.get('channels', 1)}

def extract_frames(source, folder, metadata, context):
    frames_dir = folder / 'frames'
    frames_dir.mkdir(exist_ok=True)
    manifest = frames_dir / 'manifest.json'
    if manifest.exists():
        try:
            cached=json.loads(manifest.read_text(encoding='utf-8'))
            if isinstance(cached,list) and 0<len(cached)<=120 and all(re.fullmatch(r'f\d{3}\.jpg',f['file']) and (frames_dir/f['file']).is_file() and math.isfinite(float(f['time'])) and 0<=float(f['time'])<=metadata['duration'] and (not f.get('face') or all(math.isfinite(float(f['face'][k])) and 0<=float(f['face'][k])<=1 for k in ['x','y','w','h'])) for f in cached):
                return cached
        except (ValueError,TypeError,KeyError):
            pass
    interval = max(15.0, metadata['duration'] / 119)
    ffmpeg(['-i', source, '-vf', f'fps=1/{interval},scale=480:-2', '-frames:v', '120', '-q:v', '4', frames_dir / 'f%03d.jpg'], context)
    files = sorted(frames_dir.glob('f*.jpg'))
    if not files:
        ffmpeg(['-ss', '0', '-i', source, '-frames:v', '1', '-vf', 'scale=480:-2', frames_dir / 'f001.jpg'], context)
        files = sorted(frames_dir.glob('f*.jpg'))
    frames = []
    try:
        import cv2
        detector = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    except Exception:
        detector = None
    for i, path in enumerate(files):
        face = None
        if detector is not None:
            image = cv2.imread(str(path))
            if image is not None:
                h, w = image.shape[:2]
                boxes = detector.detectMultiScale(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                if len(boxes):
                    x, y, fw, fh = max(boxes, key=lambda box: box[2] * box[3])
                    face = {'x': float(x/w), 'y': float(y/h), 'w': float(fw/w), 'h': float(fh/h)}
        frames.append({'file': path.name, 'time': min(metadata['duration'] - 0.01, (i + 0.5) * interval) if len(files) > 1 else 0, 'face': face})
    from .store import atomic_json
    atomic_json(manifest, frames)
    return frames

def font_path(bold=False):
    candidate = ROOT / 'assets' / ('NotoSans-Bold.ttf' if bold else 'NotoSans-Regular.ttf')
    if candidate.exists():
        return candidate
    return Path('C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf')
