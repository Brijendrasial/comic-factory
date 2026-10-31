"""Installed code is read-only; models, environments and projects are per-user."""
import json,os,sys
from pathlib import Path
CODE_HOME=Path(__file__).resolve().parent
PRODUCT_HOME=CODE_HOME.parent
DATA_HOME=Path(os.environ.get('COMIC_FACTORY_HOME') or (Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local/share')/'ComicFactory')).expanduser().resolve()

def ensure_data():
    DATA_HOME.mkdir(parents=True,exist_ok=True)
    config=DATA_HOME/'config.json'
    if not config.exists():
        defaults=json.loads((CODE_HOME/'defaults.json').read_text(encoding='utf-8'))
        config.write_text(json.dumps(defaults,indent=2),encoding='utf-8')
    for name in ('library','logs','models','local_models','runtime-tmp','voices'):(DATA_HOME/name).mkdir(exist_ok=True)
    return DATA_HOME

def engine_python():
    return Path(os.environ.get('COMIC_FACTORY_ENGINE_PYTHON') or DATA_HOME/'.venv/Scripts/python.exe')

def voice_python():return DATA_HOME/'.voice-venv/Scripts/python.exe'
