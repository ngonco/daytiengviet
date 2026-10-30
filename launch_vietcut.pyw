"""pythonw entry point: no terminal window; capture startup errors before imports."""
from pathlib import Path
import os
import sys
import traceback


def main():
    root=Path(__file__).resolve().parent
    os.chdir(root)
    log_path=root/'data/logs/launcher.log'
    previous=(sys.stdout,sys.stderr)
    try:
        log_path.parent.mkdir(parents=True,exist_ok=True)
        # pythonw supplies None for stdout/stderr. Uvicorn's logging setup needs streams.
        with log_path.open('a',encoding='utf-8',buffering=1) as stream:
            sys.stdout=sys.stderr=stream
            try:
                from start import main as start_editor
                start_editor()
                return 0
            except SystemExit as exc:
                if exc.code in (None,0):return 0
                traceback.print_exc()
            except Exception:
                traceback.print_exc()
    except Exception:
        pass
    finally:
        sys.stdout,sys.stderr=previous
    # Keep the popup generic: never include environment values/provider credentials.
    if os.name=='nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,'Chưa mở được ứng dụng. Hãy chạy CAI_DAT.cmd hoặc xem tệp:\n'+str(log_path),'Vietnamese with Vinh',0x10)
    return 1


if __name__=='__main__':raise SystemExit(main())
