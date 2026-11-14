"""User-invoked restart of the verified workspace server; never stop busy/other apps."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.config import settings
from backend import store

LOOKUP=r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$cfg=$env:VIETCUT_RESTART_CONFIG | ConvertFrom-Json
$listeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object {$_.LocalPort -eq $cfg.port})
$rows=@(foreach ($owner in @($listeners.OwningProcess | Where-Object {$_ -gt 0} | Select-Object -Unique)) {
 $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$owner) -ErrorAction Stop
 [pscustomobject]@{pid=$p.ProcessId;name=$p.Name;command=$p.CommandLine;created=$p.CreationDate.ToFileTimeUtc().ToString()}
})
ConvertTo-Json -InputObject $rows -Compress
'''

def busy():
    return any(j['status'] in ['running','cancelling'] for j in store.jobs())

def owners(port):
    env={**os.environ,'VIETCUT_RESTART_CONFIG':json.dumps({'port':port})}
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',LOOKUP],env=env,capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('Khong xac minh duoc may chu; khong dung tien trinh nao.')
    try:rows=json.loads(result.stdout.decode('utf-8-sig'))
    except (ValueError,UnicodeError):raise RuntimeError('Khong doc duoc thong tin may chu; khong dung tien trinh nao.') from None
    if not isinstance(rows,list):raise RuntimeError('Thong tin may chu khong hop le.')
    return rows

def owned(row):
    if str(row.get('name','')).casefold() not in ['python.exe','pythonw.exe']:return False
    if not row.get('pid') or not row.get('created'):return False
    command=str(row.get('command','')).replace('/','\\')
    arguments=[part.strip('"') for part in re.findall(r'"[^"]*"|\S+',command)]
    scripts={str(ROOT/name).replace('/','\\').casefold() for name in ['launch_vietcut.pyw','start.py']}
    for argument in arguments[1:]:
        if argument in ['-u','-B','-E','-I','-O','-OO','-s','-S','-q']:continue
        return argument.casefold() in scripts
    return False

def stop_verified(row):
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)];kernel.GetProcessTimes.restype=wintypes.BOOL
    kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT];kernel.TerminateProcess.restype=wintypes.BOOL
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
    handle=kernel.OpenProcess(0x00100000|0x1000|0x0001,False,int(row['pid']))
    if not handle:raise RuntimeError('Khong co quyen khoi dong lai may chu da xac minh.')
    try:
        created,exited,system,user=(wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle,ctypes.byref(created),ctypes.byref(exited),ctypes.byref(system),ctypes.byref(user)):raise RuntimeError('Khong xac minh duoc thoi diem tao tien trinh.')
        actual=(created.dwHighDateTime<<32)|created.dwLowDateTime
        if actual//10!=int(row['created'])//10:raise RuntimeError('Tien trinh da thay doi; khong dung.')
        if busy():raise RuntimeError('Dang co tac vu chay; chua khoi dong lai. Hay cho hoan tat hoac Dung trong app.')
        if not kernel.TerminateProcess(handle,0):raise RuntimeError('Khong dung duoc may chu da xac minh.')
        if kernel.WaitForSingleObject(handle,10000)!=0:raise RuntimeError('May chu cu chua dung xong; chua mo ban thu hai.')
    finally:kernel.CloseHandle(handle)

def launch():
    pythonw=Path(sys.executable).with_name('pythonw.exe')
    executable=pythonw if pythonw.is_file() else Path(sys.executable)
    subprocess.Popen([str(executable),str(ROOT/'launch_vietcut.pyw')],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def ready(port):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        try:
            with opener.open(f'http://127.0.0.1:{port}/api/health',timeout=1) as response:result=json.load(response)
            if result.get('app')=='vietcut' and result.get('version')=='1.5.3' and result.get('provider_retry_version')==1 and result.get('assembly_editor_version')==4:return True
        except (OSError,ValueError):pass
        time.sleep(.25)
    return False

def restart():
    if busy():raise RuntimeError('Dang co tac vu chay; hay cho hoan tat hoac Dung trong app truoc khi khoi dong lai.')
    port=int(settings().get('APP_PORT') or 8876)
    if not 1<=port<=65535:raise RuntimeError('APP_PORT khong hop le.')
    rows=owners(port)
    if any(not owned(row) for row in rows):raise RuntimeError('Cong dang do chuong trinh khac hoac may chu khong xac minh duoc su dung. Khong dung tien trinh nao.')
    if busy():raise RuntimeError('Tac vu vua bat dau; chua khoi dong lai.')
    for row in rows:stop_verified(row)
    launch()
    if not ready(port):raise RuntimeError('Da gui lenh mo VietCut nhung chua xac nhan duoc ban 1.5.3. Kiem tra data/logs/launcher.log.')
    print('VietCut 1.5.3 da san sang. Cac tac vu trong hang doi se tiep tuc; video goc va cache duoc giu nguyen.')

def main(sync_github=False):
    synced=True
    if sync_github:
        from scripts.sync_github import safe_sync
        synced=safe_sync(ROOT)
    try:restart()
    except Exception as exc:
        print(str(exc) if isinstance(exc,RuntimeError) else 'Chua khoi dong lai duoc. Khong thay doi video goc.')
        return 1
    return 0 if synced else 1

if __name__=='__main__':raise SystemExit(main('--sync-github' in sys.argv[1:]))
