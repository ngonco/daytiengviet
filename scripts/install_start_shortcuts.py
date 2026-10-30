"""Install/verify personal Start Menu and workspace shortcuts with Windows COM.

No admin rights, startup registration, registry pinning or execution-policy changes.
The generated .lnk files contain machine-specific paths and are never tracked.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
NAME='Vietnamese with Vinh'
SCRIPT=r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$cfg = $env:VIETCUT_SHORTCUT_CONFIG | ConvertFrom-Json
$programs = [Environment]::GetFolderPath([Environment+SpecialFolder]::Programs)
if ([string]::IsNullOrWhiteSpace($programs)) { throw 'Cannot locate personal Start Menu.' }
$paths = @((Join-Path $cfg.root ($cfg.name + '.lnk')), (Join-Path $programs ($cfg.name + '.lnk')))
$shell = New-Object -ComObject WScript.Shell
$arguments = '"' + $cfg.entry + '"'
$result = @()
foreach ($path in $paths) {
    if ($cfg.verify -and -not (Test-Path -LiteralPath $path)) { throw ('Missing shortcut: ' + $path) }
    if (-not $cfg.verify) {
        $parent = Split-Path -Parent $path
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        $link = $shell.CreateShortcut($path)
        $link.TargetPath = $cfg.pythonw
        $link.Arguments = $arguments
        $link.WorkingDirectory = $cfg.root
        $link.IconLocation = $cfg.icon + ',0'
        $link.Description = 'Vietnamese with Vinh - local video lesson editor'
        $link.WindowStyle = 1
        $link.Save()
    }
    $read = $shell.CreateShortcut($path)
    if ($read.TargetPath -ine $cfg.pythonw -or $read.Arguments -cne $arguments -or $read.WorkingDirectory -ine $cfg.root -or $read.IconLocation -ine ($cfg.icon + ',0')) {
        throw ('Shortcut verification failed: ' + $path)
    }
    $result += [pscustomobject]@{path=$path;target=$read.TargetPath;arguments=$read.Arguments;working_directory=$read.WorkingDirectory;icon=$read.IconLocation}
}
ConvertTo-Json -InputObject $result -Depth 3 -Compress
'''


def main():
    if os.name!='nt':raise SystemExit('This installer is for Windows.')
    pythonw=Path(sys.executable).with_name('pythonw.exe')
    entry=ROOT/'launch_vietcut.pyw';icon=ROOT/'assets/vietcut.ico'
    for path in [pythonw,entry,icon]:
        if not path.is_file():raise SystemExit('Missing required file: '+str(path))
    powershell=shutil.which('powershell.exe') or shutil.which('pwsh.exe')
    if not powershell:raise SystemExit('PowerShell is required to create Windows shortcuts.')
    config={'root':str(ROOT),'name':NAME,'pythonw':str(pythonw),'entry':str(entry),'icon':str(icon),'verify':'--verify' in sys.argv}
    env={**os.environ,'VIETCUT_SHORTCUT_CONFIG':json.dumps(config,ensure_ascii=False)}
    result=subprocess.run([powershell,'-NoLogo','-NoProfile','-NonInteractive','-Command',SCRIPT],env=env,capture_output=True,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise SystemExit(result.stderr.strip() or 'Shortcut installation did not finish.')
    links=json.loads(result.stdout)
    for link in links:print(('Verified: ' if config['verify'] else 'Created: ')+link['path'])
    print('Start > Vietnamese with Vinh > right-click > Pin to Start.')


if __name__=='__main__':main()
