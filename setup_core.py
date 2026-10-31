"""First-run setup. No hosted inference, global Python changes or admin rights."""
import ctypes,hashlib,json,os,platform,shutil,subprocess,tarfile,threading,time,urllib.request,zipfile
from pathlib import Path

class SetupCancelled(Exception):pass

def sha256(path):
    with open(path,'rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def safe_target(root,name):
    root=Path(root).resolve();target=(root/name).resolve()
    if not target.is_relative_to(root):raise ValueError('Archive path escapes the installation folder.')
    return target

def extract_archive(path,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                safe_target(destination,item.filename)
                if (item.external_attr>>16)&0o170000==0o120000:raise ValueError('Archive links are not supported.')
            archive.extractall(destination)
    else:
        with tarfile.open(path) as archive:
            for item in archive.getmembers():
                safe_target(destination,item.name)
                if item.issym() or item.islnk():raise ValueError('Archive links are not supported.')
            archive.extractall(destination,filter='data')

def download(asset,target,report,cancel=None,allow_http=False):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and target.stat().st_size==asset['size'] and sha256(target)==asset['sha256']:return
    if not asset['url'].startswith('https://') and not allow_http:raise ValueError('Downloads require HTTPS.')
    partial=target.with_name(target.name+'.partial')
    for attempt in range(3):
        if cancel and cancel.is_set():raise SetupCancelled()
        offset=partial.stat().st_size if partial.exists() else 0
        if offset>asset['size']:partial.unlink();offset=0
        if offset==asset['size']:
            if sha256(partial)==asset['sha256']:partial.replace(target);return
            partial.unlink();offset=0
        headers={'User-Agent':'ComicFactory-Setup/0.1','Accept-Encoding':'identity'}
        if offset:headers['Range']=f'bytes={offset}-'
        try:
            with urllib.request.urlopen(urllib.request.Request(asset['url'],headers=headers),timeout=30) as response:
                if not allow_http and not response.geturl().startswith('https://'):raise ValueError('Insecure download redirect refused.')
                status=response.status
                if offset and status==206:
                    if not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):raise ValueError('The download server returned an incorrect resume offset.')
                    mode='ab'
                else:offset=0;mode='wb'
                done=offset;last=time.monotonic()
                with open(partial,mode) as stream:
                    while True:
                        if cancel and cancel.is_set():raise SetupCancelled()
                        chunk=response.read(1024*1024)
                        if not chunk:break
                        stream.write(chunk);done+=len(chunk)
                        if done>asset['size']:raise ValueError('Downloaded file exceeded its expected size.')
                        if time.monotonic()-last>.5:report(f'Downloading {target.name}: {done*100/asset["size"]:.0f}%');last=time.monotonic()
            if partial.stat().st_size!=asset['size']:raise OSError('Download was interrupted; progress is saved.')
            if sha256(partial)!=asset['sha256']:
                partial.unlink();raise ValueError('Downloaded file failed its SHA-256 integrity check.')
            partial.replace(target);return
        except SetupCancelled:raise
        except Exception:
            if attempt==2:raise
            report('Retrying download; completed data will be reused.');time.sleep(1)

def hardware(home,product):
    issues=[];info={'system':platform.system(),'architecture':platform.machine()}
    if info['system']!='Windows' or info['architecture'].lower() not in ('amd64','x86_64'):issues.append('This beta requires 64-bit Windows on an Intel/AMD PC.')
    try:
        result=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,driver_version,compute_cap','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=True)
        rows=[r.rsplit(',',3) for r in result.stdout.strip().splitlines()]
        info['gpus']=[{'name':r[0].strip(),'vram_mib':int(r[1]),'driver':r[2].strip(),'compute':float(r[3])} for r in rows]
        if not any(g['vram_mib']>=product['minimum_vram_mib'] and g['compute']>=8 for g in info['gpus']):issues.append('This beta needs an NVIDIA Ampere-or-newer GPU (for example RTX 30/40/50 series) with at least 8 GB video memory.')
    except Exception:issues.append('A supported NVIDIA GPU and working NVIDIA driver were not detected. Install the driver, then retry setup.')
    if os.name=='nt':
        try:
            ctypes.WinDLL('msvcp140.dll');ctypes.WinDLL('vcruntime140_1.dll')
        except OSError:issues.append('The Microsoft Visual C++ x64 runtime is missing. Install it from https://aka.ms/vc14/vc_redist.x64.exe, then retry. Its Microsoft installer may require administrator approval.')
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
        memory=Memory();memory.length=ctypes.sizeof(memory);ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
        info['ram_gib']=round(memory.total/1024**3,1)
        if info['ram_gib']<product['minimum_ram_gib']-1:issues.append('At least 24 GB system RAM is required; 32 GB is recommended.')
    home=Path(home);home.mkdir(parents=True,exist_ok=True)
    probe=home/'.write-check';probe.write_text('ok');probe.unlink()
    info['free_gib']=round(shutil.disk_usage(home).free/1024**3,1)
    if info['free_gib']<product['required_free_gib']:issues.append(f'Keep at least {product["required_free_gib"]} GB free for models, runtimes and generated comics.')
    return info,issues

class Setup:
    def __init__(self,bundle,home,report,cancel=None):
        self.bundle=Path(bundle);self.home=Path(home);self.report=report;self.cancel=cancel or threading.Event()
        self.product=json.loads((self.bundle/'product.json').read_text())
        self.manifest=json.loads((self.bundle/'model-manifest.json').read_text())
        self.env=dict(os.environ,PYTHONUTF8='1',COMIC_FACTORY_HOME=str(self.home),HF_HOME=str(self.home/'models'),HF_HUB_DISABLE_XET='1',
            TEMP=str(self.home/'runtime-tmp'),TMP=str(self.home/'runtime-tmp'),PIP_CACHE_DIR=str(self.home/'runtime-tmp/pip-cache'),NUMBA_CACHE_DIR=str(self.home/'runtime-tmp/numba'))
        for key in ('PYTHONPATH','PYTHONHOME','PYTHONUSERBASE','VIRTUAL_ENV'):self.env.pop(key,None)
        self.env['PYTHONNOUSERSITE']='1'
    def run_command(self,args):
        if self.cancel.is_set():raise SetupCancelled()
        with open(self.home/'logs/setup.log','a',encoding='utf-8') as log:
            process=subprocess.Popen([str(x) for x in args],env=self.env,cwd=self.home,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            def stop_if_cancelled():
                while process.poll() is None:
                    if self.cancel.wait(.5):
                        if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
                        else:process.terminate()
                        return
            threading.Thread(target=stop_if_cancelled,daemon=True).start()
            for line in process.stdout:
                log.write(line);log.flush()
                if line.startswith(('Collecting ','Downloading ','Successfully installed','ERROR:')):self.report(line.strip()[:180])
            code=process.wait()
            if self.cancel.is_set():raise SetupCancelled()
            if code:raise RuntimeError('A setup step failed. Open setup.log for the details, then use Retry.')
    def run(self):
        self.home.mkdir(parents=True,exist_ok=True)
        handle=open(self.home/'setup.lock','a+b')
        try:
            if os.name=='nt':
                import msvcrt
                handle.seek(0);handle.write(b'0');handle.flush();handle.seek(0)
                try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                except OSError:raise RuntimeError('Another Comic Factory setup is already running. Close it before retrying.')
            self._run()
        finally:handle.close()
    def _run(self):
        product=dict(self.product)
        if (self.home/'runtime-tmp').exists():
            remaining=sum(max(0,a['size']-((self.home/a['path']).stat().st_size if (self.home/a['path']).exists() else 0)) for m in self.manifest['models'] for a in m['files'])
            product['required_free_gib']=max(20,round(remaining/1024**3)+20)
        info,issues=hardware(self.home,product)
        if issues:raise RuntimeError('\n'.join(issues))
        for folder in ('logs','runtime-tmp','runtime','local_models','library','models'):(self.home/folder).mkdir(parents=True,exist_ok=True)
        (self.home/'setup-state.json').write_text(json.dumps({'ready':False,'setup_in_progress':True}))
        (self.home/'hardware.json').write_text(json.dumps(info,indent=2))
        runtime=self.manifest['python'];archive=self.home/'runtime-tmp/python.tar.gz'
        py=self.home/'runtime/python/python.exe'
        python_marker=py.parent/'.comic-runtime.json'
        if not py.exists() or not python_marker.exists():
            self.report('Installing a private Python runtime. Your system Python will not be changed.')
            download(runtime,archive,self.report,self.cancel);extract_archive(archive,self.home/'runtime')
            self.run_command([py,'-c',"import tkinter,venv,ssl; print('Private Python runtime verified')"])
            python_marker.write_text(json.dumps({'sha256':runtime['sha256']}))
        engine=self.home/'.venv/Scripts/python.exe';voice=self.home/'.voice-venv/Scripts/python.exe'
        if not engine.exists():self.run_command([py,'-m','venv',self.home/'.venv'])
        self.report('Installing the pinned NVIDIA drawing runtime. This may take several minutes.')
        self.run_command([engine,'-m','pip','--isolated','install','--index-url','https://pypi.org/simple','--cache-dir',self.home/'runtime-tmp/pip-cache','--extra-index-url','https://download.pytorch.org/whl/cu128','--no-deps','-r',self.bundle/'constraints-engine.txt','setuptools'])
        if not voice.exists():self.run_command([py,'-m','venv',self.home/'.voice-venv'])
        pth=self.home/'.voice-venv/Lib/site-packages/comic_shared_runtime.pth'
        pth.write_text(str(self.home/'.venv/Lib/site-packages')+'\n',encoding='utf-8')
        self.report('Installing the separate emotional speech runtime.')
        self.run_command([voice,'-m','pip','--isolated','install','--index-url','https://pypi.org/simple','--cache-dir',self.home/'runtime-tmp/pip-cache','--no-deps','-r',self.bundle/'constraints-voice.txt'])
        for model in self.manifest['models']:
            self.report('Preparing '+model['name']+'...')
            for asset in model['files']:download(asset,self.home/asset['path'],self.report,self.cancel)
            if model.get('marker'):
                marker=self.home/model['marker'];marker.parent.mkdir(parents=True,exist_ok=True)
                marker.write_text(json.dumps({'repo':model['repo'],'revision':model['revision'],'files':[{'rfilename':a.get('relative',a['path']),'size':a['size'],'sha256':a['sha256']} for a in model['files']]},indent=2))
        reviewer=self.home/self.manifest['reviewer_manifest_path'];reviewer.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(self.bundle/'reviewer-manifest.json',reviewer)
        ollama=self.manifest['ollama'];binary=self.home/'runtime/ollama/ollama.exe'
        if not binary.exists() or not (binary.parent/'.comic-runtime.json').exists():
            self.report('Installing the local artwork-checking runtime.')
            path=self.home/'runtime-tmp/ollama.zip';download(ollama,path,self.report,self.cancel);extract_archive(path,binary.parent)
            (binary.parent/'.comic-runtime.json').write_text(json.dumps({'sha256':ollama['sha256']}))
        defaults=self.home/'config.json'
        if not defaults.exists():shutil.copy2(self.bundle/'engine/defaults.json',defaults)
        self.report('Checking GPU execution and both speech/drawing environments...')
        self.run_command([engine,'-c',"import torch,tkinter,diffusers,transformers,bitsandbytes,lmformatenforcer,imageio_ffmpeg; assert torch.cuda.is_available(),'CUDA GPU is unavailable'; x=torch.ones((8,8),device='cuda'); assert (x@x).sum().item()==512; print('GPU readiness check passed')"])
        self.run_command([voice,'-c',"from qwen_tts import Qwen3TTSModel; import soundfile; print('Speech runtime readiness check passed')"])
        state={'version':self.product['version'],'manifest_sha256':sha256(self.bundle/'model-manifest.json'),'ready':True}
        (self.home/'setup-state.json').write_text(json.dumps(state,indent=2))
        self.report('Ready. Your models and comic projects stay on this PC.')

def ready(bundle,home):
    bundle=Path(bundle);home=Path(home)
    try:
        state=json.loads((home/'setup-state.json').read_text());product=json.loads((bundle/'product.json').read_text())
        manifest=json.loads((bundle/'model-manifest.json').read_text())
        files_present=all((home/a['path']).is_file() and (home/a['path']).stat().st_size==a['size'] for m in manifest['models'] for a in m['files'])
        return state.get('ready') is True and state.get('version')==product['version'] and state.get('manifest_sha256')==sha256(bundle/'model-manifest.json') and (home/'.venv/Scripts/python.exe').exists() and (home/'.voice-venv/Scripts/python.exe').exists() and (home/'runtime/ollama/ollama.exe').exists() and files_present
    except (OSError,ValueError):return False
