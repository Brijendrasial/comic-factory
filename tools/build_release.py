"""Build the native Windows/x64 launcher and single-file installer."""
import argparse,hashlib,json,os,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run(args,env):subprocess.run([str(x) for x in args],cwd=ROOT,env=env,check=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--inner',action='store_true');args=parser.parse_args()
    temp=ROOT/'build/tmp';temp.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TEMP=str(temp),TMP=str(temp))
    if not args.inner:
        venv=ROOT/'.build-venv';python=venv/'Scripts/python.exe'
        if not python.exists():run([sys.executable,'-m','venv',venv],env)
        run([python,'-m','pip','install','-r',ROOT/'requirements-build.txt'],env)
        run([python,__file__,'--inner'],env);return
    run([sys.executable,'-m','unittest','discover','-s','tests','-v'],env)
    run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','comic_factory.spec'],env)
    payload=ROOT/'build/payload.zip';folder=ROOT/'dist/ComicFactory'
    with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(folder.rglob('*')):
            if path.is_file():archive.write(path,path.relative_to(folder))
    (ROOT/'build/payload.sha256').write_text(hashlib.sha256(payload.read_bytes()).hexdigest(),encoding='ascii')
    version=json.loads((ROOT/'product.json').read_text())['version'];name='ComicFactory-Setup-'+version
    run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--name',name,'--icon',str(ROOT/'assets/comic-factory.ico'),
        '--distpath','release','--workpath','build/installer','--specpath','build',
        '--add-data',str(payload)+';.', '--add-data',str(ROOT/'build/payload.sha256')+';.',
        '--add-data',str(ROOT/'product.json')+';.', '--add-data',str(ROOT/'LICENSE')+';.',str(ROOT/'installer_main.py')],env)
    target=ROOT/'release'/(name+'.exe');digest=hashlib.sha256(target.read_bytes()).hexdigest()
    (ROOT/'release/SHA256SUMS.txt').write_text(digest+'  '+target.name+'\n',encoding='ascii')
    print('Installer built:',target,flush=True)
if __name__=='__main__':main()
