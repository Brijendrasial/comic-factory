"""Per-user installation and uninstall ownership; never removes model/project data."""
import hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path
from setup_core import extract_archive,safe_target
MARKER='ComicFactory.install.json'

def shortcuts(root,remove=False):
    env=dict(os.environ,CF_INSTALL_ROOT=str(root),CF_REMOVE_SHORTCUTS='1' if remove else '0')
    script=r'''
$ErrorActionPreference='Stop'
$root=$env:CF_INSTALL_ROOT
$programs=[Environment]::GetFolderPath('Programs')
$desktop=[Environment]::GetFolderPath('Desktop')
$menu=Join-Path $programs 'Comic Factory'
if ($env:CF_REMOVE_SHORTCUTS -eq '1') {
    foreach ($item in @((Join-Path $menu 'Comic Factory.lnk'),(Join-Path $menu 'Repair setup.lnk'),(Join-Path $desktop 'Comic Factory.lnk'))) {
        if (Test-Path -LiteralPath $item) { Remove-Item -LiteralPath $item -Force }
    }
    if ((Test-Path -LiteralPath $menu) -and -not (Get-ChildItem -LiteralPath $menu)) { Remove-Item -LiteralPath $menu }
} else {
    New-Item -ItemType Directory -Force -Path $menu | Out-Null
    $shell=New-Object -ComObject WScript.Shell
    foreach ($item in @((Join-Path $menu 'Comic Factory.lnk'),(Join-Path $desktop 'Comic Factory.lnk'))) {
        $link=$shell.CreateShortcut($item);$link.TargetPath=Join-Path $root 'ComicFactory.exe';$link.WorkingDirectory=$root;$link.Save()
    }
    $link=$shell.CreateShortcut((Join-Path $menu 'Repair setup.lnk'));$link.TargetPath=Join-Path $root 'ComicFactory.exe';$link.Arguments='--setup';$link.WorkingDirectory=$root;$link.Save()
}
'''
    result=subprocess.run([str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'),'-NoProfile','-NonInteractive','-Command',script],env=env,capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise RuntimeError('Windows could not create the app shortcuts. '+result.stderr[-500:])

def register(root,version):
    import winreg
    keypath=r'Software\Microsoft\Windows\CurrentVersion\Uninstall\ComicFactory'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,keypath) as key:
        for name,value in {'DisplayName':'Comic Factory (Beta)','DisplayVersion':version,'Publisher':'Comic Factory contributors',
            'InstallLocation':str(root),'DisplayIcon':str(root/'ComicFactory.exe'),'UninstallString':f'"{root/"ComicFactory.exe"}" --uninstall'}.items():winreg.SetValueEx(key,name,0,winreg.REG_SZ,value)
        for name in ('NoModify','NoRepair'):winreg.SetValueEx(key,name,0,winreg.REG_DWORD,1)

def install(payload,expected,root,version,portable=False):
    root=Path(root).expanduser().resolve()
    if root==Path(root.anchor):raise ValueError('Choose a named app folder, not a drive root.')
    receipt=root/MARKER
    if root.exists() and any(root.iterdir()) and not receipt.exists():raise ValueError('Choose an empty folder or an existing Comic Factory installation.')
    if receipt.exists() and json.loads(receipt.read_text()).get('product')!='ComicFactory':raise ValueError('The folder belongs to another application.')
    if hashlib.sha256(Path(payload).read_bytes()).hexdigest()!=expected:raise ValueError('The installer payload checksum did not match.')
    root.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.comicfactory-stage-',dir=root.parent) as tmp:
        stage=Path(tmp);extract_archive(payload,stage)
        if not (stage/'ComicFactory.exe').exists() or not (stage/'_internal/product.json').exists():raise ValueError('The installer payload is incomplete.')
        files=[p for p in stage.rglob('*') if p.is_file()]
        files.sort(key=lambda p:(p.name!='ComicFactory.exe',str(p)))
        root.mkdir(exist_ok=True)
        receipt.write_text(json.dumps({'product':'ComicFactory','version':version,'files':[],'portable':portable}))
        for source in files:
            relative=source.relative_to(stage);target=safe_target(root,relative);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        receipt.write_text(json.dumps({'product':'ComicFactory','version':version,'files':[str(p.relative_to(stage)) for p in files],'portable':portable},indent=2))
    if not portable:shortcuts(root);register(root,version)
    return root

def uninstall(root,parent_pid):
    root=Path(root).resolve();receipt=root/MARKER
    if not receipt.exists():raise ValueError('The Comic Factory installation receipt is missing; no files were removed.')
    data=json.loads(receipt.read_text())
    if data.get('product')!='ComicFactory':raise ValueError('This is not a Comic Factory installation.')
    files=[str(safe_target(root,name)) for name in data['files']]+[str(receipt)]
    if not data.get('portable'):
        import winreg
        keypath=r'Software\Microsoft\Windows\CurrentVersion\Uninstall\ComicFactory'
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,keypath) as key:location=winreg.QueryValueEx(key,'InstallLocation')[0]
            if Path(location).resolve()==root:shortcuts(root,remove=True);winreg.DeleteKey(winreg.HKEY_CURRENT_USER,keypath)
        except FileNotFoundError:pass
    fd,job=tempfile.mkstemp(prefix='comicfactory-uninstall-',suffix='.json');os.close(fd)
    Path(job).write_text(json.dumps({'root':str(root),'files':files,'pid':parent_pid}),encoding='utf-8')
    env=dict(os.environ,CF_UNINSTALL_JOB=job)
    # Only receipt-owned files are deleted after this executable exits. Custom
    # files, model folders and generated comics are never recursively purged.
    script=r'''
$ErrorActionPreference='Stop'
$jobPath=$env:CF_UNINSTALL_JOB
$job=Get-Content -LiteralPath $jobPath -Raw -Encoding UTF8 | ConvertFrom-Json
Wait-Process -Id $job.pid -ErrorAction SilentlyContinue
$root=[IO.Path]::GetFullPath($job.root).TrimEnd([IO.Path]::DirectorySeparatorChar)
$prefix=$root+[IO.Path]::DirectorySeparatorChar
if ($root -eq [IO.Path]::GetPathRoot($root).TrimEnd([IO.Path]::DirectorySeparatorChar)) { throw 'Unsafe uninstall root.' }
$dirs=New-Object 'System.Collections.Generic.HashSet[string]'
foreach ($item in $job.files) {
    $target=[IO.Path]::GetFullPath($item)
    if (-not $target.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe uninstall path.' }
    $parent=[IO.Path]::GetDirectoryName($target);$blocked=$false
    while ($parent -and $parent.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) {
        if ((Test-Path -LiteralPath $parent) -and ((Get-Item -LiteralPath $parent -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { $blocked=$true;break }
        [void]$dirs.Add($parent);$parent=[IO.Path]::GetDirectoryName($parent)
    }
    if (-not $blocked -and (Test-Path -LiteralPath $target)) { Remove-Item -LiteralPath $target -Force }
}
foreach ($dir in ($dirs | Sort-Object Length -Descending)) {
    if ((Test-Path -LiteralPath $dir) -and -not (Get-ChildItem -LiteralPath $dir -Force)) { Remove-Item -LiteralPath $dir }
}
if ((Test-Path -LiteralPath $root) -and -not (Get-ChildItem -LiteralPath $root -Force)) { Remove-Item -LiteralPath $root }
Remove-Item -LiteralPath $jobPath -Force
'''
    subprocess.Popen([str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'),'-NoProfile','-NonInteractive','-Command',script],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
