"""Migrate saved scripted comics from narrator output without redrawing images."""
import copy,json
from pathlib import Path

def dialogue_story(c,data):
    if any(p.get('dialogue') for p in data['panels']):return copy.deepcopy(data)
    from scripted import parse_script
    upgraded=parse_script(dict(c,prompt=data.get('request_prompt') or c.get('prompt',''),panels=len(data['panels'])))
    if upgraded is None:raise ValueError('This saved comic has no exact speaker dialogue. Add Speaker: dialogue lines in its script before upgrading voices.')
    # Keep image-specific poses and approved mouth locations from this project.
    for before,after in zip(data['panels'],upgraded['panels']):
        after['scene']=before['scene']
        if before.get('speaker_positions'):after['speaker_positions']=before['speaker_positions']
    upgraded['seed']=data['seed'];upgraded['storyboard_reviewed']=data.get('storyboard_reviewed',False)
    return upgraded

def rebuild(c,folder):
    import factory
    from project import archive_files
    folder=Path(folder);data=json.loads((folder/'story.json').read_text(encoding='utf-8'))
    if data.get('format')=='comic-book-v1':raise ValueError('Voice upgrade currently supports single-page comics. Choose a single-page comic folder.')
    saved=json.loads((folder/'settings.json').read_text(encoding='utf-8')) if (folder/'settings.json').exists() else {}
    c=dict(c,**{k:v for k,v in saved.items() if k not in ('prompt','character_voices')})
    upgraded=dialogue_story(c,data)
    for i,_ in enumerate(upgraded['panels'],1):
        if not (folder/f'art_{i:02}.png').exists():raise ValueError('Finish drawing all panels before upgrading the voices.')
    # Synthesize first; a failed voice job must preserve the playable old video.
    factory.log('Upgrading character voices; all existing artwork will be reused.')
    factory.release()
    durations=factory.narration(c,upgraded,folder)
    old=[folder/'story.json',folder/'comic.png',folder/'layout.json']
    archive_files(folder,old)
    factory.save_json(folder/'story.json',upgraded)
    if not factory.checked_cards(upgraded,folder,int(c.get('output_width',1024))):return
    archive_files(folder,[folder/'comic.mp4',folder/'comic_narration.mp4',folder/'subtitles.srt'])
    factory.video(upgraded,folder,durations,c.get('background_music',True),c)
    factory.save_json(folder/'render_status.json',{'state':'complete','comic':'comic.png','video':'comic.mp4','voice_engine':'Qwen3-TTS-1.7B-CustomVoice'})
    factory.log(f'Finished: {folder}')
