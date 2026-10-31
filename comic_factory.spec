# PyInstaller build: the engine stays as readable source, outside the launcher.
from pathlib import Path
root=Path(SPECPATH)
files=[(str(p),'engine') for p in (root/'engine').iterdir() if p.suffix in ('.py','.json')]
files += [(str(root/name),'.') for name in ('product.json','model-manifest.json','reviewer-manifest.json','constraints-engine.txt','constraints-voice.txt','LICENSE','THIRD_PARTY_NOTICES.md')]
files += [(str(p),'licenses') for p in (root/'licenses').glob('*') if p.is_file()]
a=Analysis([str(root/'launcher.py')],pathex=[str(root)],binaries=[],datas=files,hiddenimports=[],hookspath=[],hooksconfig={},runtime_hooks=[],excludes=[])
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='ComicFactory',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,icon=str(root/'assets/comic-factory.ico'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='ComicFactory')
