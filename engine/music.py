"""Local instrumental music and narration-aware audio mixing; no AI service."""
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import wave

MUSIC_KEYS=('background_music','music_mode','music_style','music_volume','music_file','duck_music')

def instrumental(path,duration,style='Heroic',seed=0):
    import numpy as np
    styles={
        'Heroic':(108,[(48,52,55),(43,47,50),(45,48,52),(41,45,48)]),
        'Calm':(72,[(48,52,55),(45,48,52),(41,45,48),(43,47,50)]),
        'Mystery':(84,[(45,48,52),(41,45,48),(38,41,45),(40,44,47)])}
    tempo,chords=styles.get(style,styles['Heroic'])
    rate=44100
    total=math.ceil(duration*rate)
    samples=np.zeros(total,dtype=np.float32)
    beat=60/tempo
    rng=np.random.default_rng(seed)
    def tone(start,length,midi,level,bell=False):
        a=int(start*rate); b=min(total,a+int(length*rate))
        if b<=a: return
        t=np.arange(b-a,dtype=np.float32)/rate
        frequency=440*2**((midi-69)/12)
        envelope=np.minimum(t/0.03,1)*np.minimum((length-t)/0.12,1)
        envelope=np.clip(envelope,0,1)
        if bell: envelope*=np.exp(-t*3/max(length,0.1))
        sound=np.sin(2*np.pi*frequency*t)+0.18*np.sin(4*np.pi*frequency*t)
        samples[a:b]+=level*envelope*sound
    for bar in range(math.ceil(duration/(4*beat))):
        start=bar*4*beat
        chord=chords[bar%len(chords)]
        for note in chord: tone(start,4*beat,note+12,0.055)
        for n in range(8):
            tone(start+n*beat/2,beat*0.9,chord[n%3]+24,0.06 if style=='Calm' else 0.075,True)
        for n in range(4):
            tone(start+n*beat,beat*0.8,chord[0]-12,0.08)
        if style!='Calm':
            for n in range(4):
                a=int((start+n*beat)*rate); b=min(total,a+int(0.18*rate))
                if b>a:
                    t=np.arange(b-a)/rate
                    samples[a:b]+=0.055*np.sin(2*np.pi*(48*t+3*(1-np.exp(-18*t))))*np.exp(-24*t)
            for n in range(8):
                a=int((start+n*beat/2)*rate); b=min(total,a+int(0.045*rate))
                if b>a: samples[a:b]+=rng.normal(0,0.008,b-a)*np.exp(-np.arange(b-a)/(rate*0.01))
    samples=np.tanh(samples)*0.8
    with wave.open(str(path),'wb') as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(rate)
        output.writeframes((samples*32767).astype('<i2').tobytes())

def _digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source,'sha256').digest()

def clean_narration(folder,ffmpeg):
    base=folder/'comic_narration.mp4'
    if base.exists(): return base
    # Older comics retain clean voice-only panel clips. Rebuild from these,
    # never from a previously mixed comic, so music cannot accumulate.
    story=json.loads((folder/'story.json').read_text(encoding='utf-8'))
    clips=[folder/f'clip_{i:02}.mp4' for i in range(1,len(story['panels'])+1)]
    if not clips or not all(p.exists() for p in clips):
        raise ValueError('Clean narration clips are missing. Render this comic once before updating its music.')
    listing=folder/'music_clips.txt'
    listing.write_text('\n'.join(f"file '{p.name}'" for p in clips),encoding='utf-8')
    subprocess.run([ffmpeg,'-y','-loglevel','error','-f','concat','-safe','0','-i',str(listing),
                    '-c','copy','-movflags','+faststart',str(base)],check=True)
    return base

def apply_music(folder,settings,duration=None):
    import imageio_ffmpeg
    from project import archive_files
    folder=Path(folder).resolve()
    options=dict(background_music=True,music_mode='generated',music_style='Heroic',music_volume=0.22,
                 music_file='',duck_music=True)
    options.update({key:value for key,value in settings.items() if value is not None})
    settings=options
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    enabled=bool(settings.get('background_music',True))
    mode=settings.get('music_mode','generated')
    style=settings.get('music_style','Heroic')
    if style not in ('Heroic','Calm','Mystery'): raise ValueError('Choose Heroic, Calm or Mystery music.')
    volume=float(settings.get('music_volume',0.22))
    if not 0<=volume<=1: raise ValueError('Music volume must be between 0 and 1.')
    if mode not in ('generated','file'): raise ValueError('Choose built-in music or a local audio file.')
    source=Path(settings.get('music_file','')) if mode=='file' else folder/'music_source.wav'
    if enabled and mode=='file' and not source.is_file():
        raise ValueError('Choose an existing local music file.')
    base=clean_narration(folder,ffmpeg)
    if duration is None: duration=imageio_ffmpeg.count_frames_and_secs(str(base))[1]
    destination=folder/'comic.mp4'
    pending=folder/'comic_music_pending.mp4'
    if not enabled:
        shutil.copy2(base,pending)
    else:
        print('Adding background music beneath the narration...',flush=True)
        if mode=='generated':
            story=json.loads((folder/'story.json').read_text(encoding='utf-8'))
            instrumental(source,duration,style,story.get('seed',0))
        bed=folder/'music_bed.wav'
        fade=min(1.2,duration/3)
        filters=(f'loudnorm=I=-16:TP=-1.5:LRA=9,volume={volume},'
                 f'afade=t=in:st=0:d={fade},afade=t=out:st={max(0,duration-fade)}:d={fade}')
        subprocess.run([ffmpeg,'-y','-loglevel','error','-stream_loop','-1','-i',str(source),
            '-map','0:a:0','-vn','-t',str(duration),'-af',filters,'-ar','44100','-ac','2',
            '-c:a','pcm_s16le',str(bed)],check=True)
        if settings.get('duck_music',True):
            graph=('[0:a]asplit=2[voice][side];[1:a][side]sidechaincompress='
                   'threshold=0.05:ratio=4:attack=15:release=350[bed];'
                   '[voice][bed]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=false[a]')
        else:
            graph='[0:a][1:a]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=false[a]'
        subprocess.run([ffmpeg,'-y','-loglevel','error','-filter_complex_threads','1','-i',str(base),'-i',str(bed),
            '-filter_complex',graph,'-map','0:v','-map','[a]','-c:v','copy','-c:a','aac',
            '-b:a','192k','-ac','2','-t',str(duration),'-movflags','+faststart',str(pending)],check=True)
    metadata={key:settings.get(key) for key in MUSIC_KEYS}
    metadata.update(duration_seconds=duration,updated=dt.datetime.now().isoformat())
    if destination.exists() and _digest(destination)==_digest(pending):
        pending.unlink()
    else:
        archive_files(folder,[destination,folder/'music_settings.json'])
        pending.replace(destination)
    (folder/'music_settings.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    path=folder/'settings.json'
    saved=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    saved.update({key:settings.get(key) for key in MUSIC_KEYS})
    path.write_text(json.dumps(saved,indent=2,ensure_ascii=False),encoding='utf-8')
    return destination
