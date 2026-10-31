"""Save storyboard edits and preserve previous generated assets."""
import copy
import datetime as dt
import json
from pathlib import Path
import random
import shutil
import uuid

def archive_files(folder,files):
    folder=Path(folder).resolve()
    existing=[Path(p) for p in files if Path(p).exists()]
    if not existing:
        return
    target=folder/'history'/f'{dt.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}'
    target.mkdir(parents=True,exist_ok=True)
    for path in existing:
        if path.resolve().parent!=folder:
            raise ValueError('Only generated files inside this comic can be archived.')
        shutil.move(str(path),str(target/path.name))

def update_storyboard(folder,data,reroll=None):
    from filelock import FileLock,Timeout
    try:
        with FileLock(str(__import__('runtime_paths').DATA_HOME/'factory.lock'),timeout=0):
            return _update_storyboard(folder,data,reroll)
    except Timeout:
        raise RuntimeError('Wait for the running comic to finish before changing its storyboard.')

def _update_storyboard(folder,data,reroll=None):
    from factory import validate_story,save_json
    folder=Path(folder).resolve()
    old=json.loads((folder/'story.json').read_text(encoding='utf-8'))
    validate_story(data,len(old['panels']))
    changed=old!=data or reroll is not None
    if not changed:
        return
    files=[folder/'story.json']
    cast_changed=old['characters']!=data['characters']
    continuity_changed=old.get('visual_continuity','')!=data.get('visual_continuity','')
    for i,(before,after) in enumerate(zip(old['panels'],data['panels']),1):
        if cast_changed or continuity_changed or before['scene']!=after['scene'] or reroll in ('all',i):
            after.pop('art_approved_sha256',None)
            after['seed']=random.SystemRandom().randrange(2**31)
            files.append(folder/f'art_{i:02}.png')
        if before['narration']!=after['narration']:
            files.append(folder/f'voice_{i:02}.wav')
    if cast_changed:
        files.extend(folder.glob('character_reference*.png'))
    for pattern in ['comic.mp4','comic_narration.mp4','comic.png','cover.jpg','complete.json','panel_*.png','overlay_*.png','clip_*.mp4',
                    'subtitles.srt','music.wav','music_bed.wav','music_source.wav','music_settings.json','layout.json',
                    'page_*.png','comic-book.pdf','SCRIPT.md','LETTERING.md','render_progress.json']:
        files.extend(folder.glob(pattern))
    archive_files(folder,list(dict.fromkeys(files)))
    save_json(folder/'story.json',data)
    if data.get('format')=='comic-book-v1':
        from book import write_script
        write_script(data,folder)
        return
    (folder/'story.txt').write_text(data['title']+'\n\n'+'\n\n'.join(p['narration'] for p in data['panels']),encoding='utf-8')

