"""Start the local editor once, then open the default browser when it is ready."""
from contextlib import contextmanager
import json
import os
import threading
import time
import urllib.request
import webbrowser
from backend.config import ROOT, data_root, settings


def is_running(url):
    try:
        # Local health checks must not be sent to a configured network proxy.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url+'/api/health',timeout=1) as response:
            return json.load(response).get('app')=='vietcut'
    except (OSError,ValueError,AttributeError):
        return False


def wait_ready(url,seconds=30):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if is_running(url):return True
        time.sleep(.25)
    return False


@contextmanager
def instance_lock(port):
    """Serialize rapid clicks and hold the lock for the server's entire lifetime."""
    path=data_root()/f'launcher-{port}.lock'
    stream=path.open('a+b');owned=False
    try:
        stream.seek(0,2)
        if not stream.tell():stream.write(b'0');stream.flush()
        stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            owned=True
        except OSError:pass
        yield owned
    finally:
        if owned:
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
        stream.close()


def main():
    port=int(settings().get('APP_PORT') or 8876)
    if not 1<=port<=65535:raise ValueError('APP_PORT phải nằm trong khoảng 1–65535.')
    url=f'http://127.0.0.1:{port}'
    if is_running(url):
        webbrowser.open(url);return
    if not (ROOT/'dist/index.html').is_file():
        raise RuntimeError('Chưa có giao diện. Hãy chạy CAI_DAT.cmd trước.')
    with instance_lock(port) as owned:
        if not owned:
            if wait_ready(url):webbrowser.open(url);return
            raise RuntimeError('App đang khởi động nhưng chưa sẵn sàng. Hãy thử mở lại.')
        # A manually launched server can become ready between the first probe and lock.
        if is_running(url):webbrowser.open(url);return
        def browse():
            if wait_ready(url):webbrowser.open(url)
        threading.Thread(target=browse,name='vietcut-browser',daemon=True).start()
        import uvicorn
        uvicorn.run('backend.app:app',host='127.0.0.1',port=port,log_level='warning',access_log=False)


if __name__=='__main__':main()
