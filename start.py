"""Start VietCut locally, opening a browser only after the server is ready."""
import threading
import time
import urllib.request
import webbrowser
import json
import uvicorn
from backend.config import settings

if __name__=='__main__':
    config=settings()
    host='127.0.0.1'
    port=int(config.get('APP_PORT') or 8876)
    try:
        with urllib.request.urlopen(f'http://{host}:{port}/api/health',timeout=2) as response:
            running=json.load(response)
        if running.get('app')=='vietcut':
            webbrowser.open(f'http://{host}:{port}')
            raise SystemExit(0)
    except (OSError,ValueError):
        pass
    def browse():
        for _ in range(60):
            try:
                with urllib.request.urlopen(f'http://{host}:{port}/api/health',timeout=1):
                    webbrowser.open(f'http://{host}:{port}')
                    return
            except Exception:
                time.sleep(.5)
    threading.Thread(target=browse,daemon=True).start()
    uvicorn.run('backend.app:app',host=host,port=port,log_level='warning',access_log=False)
