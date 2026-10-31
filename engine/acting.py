"""Local character casting, line direction, caching and expressive voice jobs."""
import hashlib,json,os,re,subprocess,wave
from pathlib import Path
from runtime_paths import DATA_HOME, CODE_HOME, ensure_data
ROOT=ensure_data()
MODEL=ROOT/'local_models'/'emotional_voice'
PYTHON=ROOT/'.voice-venv'/'Scripts'/'python.exe'
DIRECTIONS={
 'angry':'Speak with controlled anger: forceful emphasis, a tense edge and firm delivery. Do not scream or distort the words.',
 'fearful':'Speak with audible fear and urgent concern, a slightly trembling breath and natural stress. Keep every word clear.',
 'urgent':'Speak urgently with brisk clear pacing and focused intensity.',
 'reassuring':'Speak calmly and confidently to reassure someone who is frightened; steady, protective and warm.',
 'relieved':'Speak with an audible release of tension, relaxed breath and grateful warmth.',
 'sad':'Speak softly with sadness and a restrained, heavy emotional tone.',
 'happy':'Speak with natural happiness, warmth and a smile in the voice.',
 'dry':'Speak with gentle dry humor, understated warmth and a small conversational pause.',
 'calm':'Speak naturally in a calm, attentive conversational tone.'}
ALIASES={'anger':'angry','worried':'fearful','scared':'fearful','fear':'fearful','relief':'relieved','joy':'happy','neutral':'calm'}

def parse_delivery(text):
    match=re.match(r'^\s*\[([^\]]{1,80})\]\s*(.*)$',text,re.S)
    if not match:return text.strip(),None
    cue=match[1].strip().lower();cue=ALIASES.get(cue,cue)
    return match[2].strip(),cue

def direction(line,panel):
    explicit=line.get('emotion') or panel.get('emotion')
    if explicit:
        explicit=ALIASES.get(explicit.lower(),explicit.lower())
        return explicit,DIRECTIONS.get(explicit,'Perform this emotional direction naturally: '+explicit)
    text=line['text'].lower();scene=panel.get('scene','').lower();name=line['speaker'].lower()
    if any(w in text for w in ['how dare','you lied','get away','leave her alone','enough!','furious']):key='angry'
    elif any(w in text for w in ['thank you','thank goodness','we made it','like gotham']):key='relieved'
    elif any(w in text for w in ['coming apart','help!','please tell me','i’m scared',"i'm scared"]):key='fearful'
    elif any(w in text for w in ['stay still','i help people','it holds','you’re safe',"you're safe"]):key='reassuring'
    elif 'until morning' in text:key='dry'
    elif any(w in scene for w in ['furious','angry','anger']):key='angry'
    elif any(w in scene for w in ['terrified','frightened','panicking']) and name!='batman':key='fearful'
    else:key='calm'
    return key,DIRECTIONS[key]

def cast_voices(data,c):
    profiles=data.get('character_profiles',{})
    names=list(dict.fromkeys(x['speaker'] for p in data['panels'] for x in p.get('dialogue',[])))
    casting={};overrides=c.get('character_voices',{});used=set()
    hero_present=any(n.casefold() in ('superman','batman') for n in names)
    if hero_present:used.add('Ryan')
    for name in names:
        desc=next((value for key,value in profiles.items() if key.casefold()==name.casefold()),'').lower()
        if not desc:
            match=re.search(r'(?im)^'+re.escape(name)+r':\s*(.+)',data.get('characters',''))
            if match:desc=match[1].lower()
        female=bool(re.search(r'\b(female|woman|girl|lady)\b',desc))
        gender='female' if female else 'male'
        pool=['Vivian','Serena','Ono_Anna','Sohee'] if female else ['Ryan','Aiden','Uncle_Fu','Dylan','Eric']
        if name.casefold() in ('superman','batman'):speaker=overrides.get(name,'Ryan')
        elif name in overrides:speaker=overrides[name]
        else:
            speaker=next((voice for voice in pool if voice not in used),None)
            if speaker is None:raise ValueError('Too many characters for distinct stock voices. Reduce the cast or set explicit character voices.')
        used.add(speaker)
        persona=('An adult woman with a clear, natural English speaking voice.' if female else 'An adult man with a clear, natural English speaking voice.')
        if re.search(r'\b(child|young girl|young boy)\b',desc):persona='A youthful '+('girl' if female else 'boy')+' voice, light and clear, speaking natural English. Keep the delivery age-appropriate.'
        if name.lower() in ('batman','superman'):persona='An adult male superhero with a low, resonant, steady baritone. Calm authority, clear English consonants; no whispering, growling or imitation of any actor.'
        casting[name]={'gender':gender,'speaker':speaker,'persona':persona}
    return casting

def build_plan(c,data,folder):
    cast=cast_voices(data,c);lines=[]
    if not cast:raise ValueError('No character dialogue found. Use Speaker: dialogue lines in your script.')
    for i,panel in enumerate(data['panels'],1):
        for j,line in enumerate(panel.get('dialogue',[]),1):
            text,cue=parse_delivery(line['text']);entry=dict(line,text=text)
            if cue and not entry.get('emotion'):entry['emotion']=cue
            emotion,instruction=direction(entry,panel);actor=cast[line['speaker']]
            instruct=actor['persona']+' '+instruction
            if line.get('delivery'):instruct+=' '+str(line['delivery'])
            identity={'text':text,'speaker':actor['speaker'],'instruct':instruct,'model':'Qwen3-TTS-12Hz-1.7B-CustomVoice','version':1}
            key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
            lines.append(dict(identity,character=line['speaker'],emotion=emotion,panel=i,line=j,key=key,
                path=str(Path(folder)/'acted_lines'/f'{i:02}-{j:02}-{key[:12]}.wav')))
    return {'model_path':str(MODEL),'casting':cast,'lines':lines,'seed':data.get('seed',12345)}

def synthesize(c,data,folder):
    import imageio_ffmpeg
    folder=Path(folder);plan=build_plan(c,data,folder)
    if not PYTHON.exists() or not (MODEL/'model.safetensors').exists():
        raise RuntimeError('The expressive local voice engine is not installed. Complete the voice upgrade before rendering dialogue; no narrator was substituted.')
    (folder/'acted_lines').mkdir(exist_ok=True)
    job=folder/'acting_plan.json';job.write_text(json.dumps(plan,indent=2,ensure_ascii=False),encoding='utf-8')
    if any(not Path(x['path']).exists() for x in plan['lines']):
        temp=ROOT/'runtime-tmp';temp.mkdir(exist_ok=True)
        env=dict(os.environ,PYTHONUTF8='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HOME=str(ROOT/'models'/'voice-cache'),
            NUMBA_CACHE_DIR=str(temp/'numba'),TEMP=str(temp),TMP=str(temp),TOKENIZERS_PARALLELISM='false')
        with open(folder/'acting-worker.log','a',encoding='utf-8') as log:
            process=subprocess.Popen([str(PYTHON),'-u',str(CODE_HOME/'acting_worker.py'),str(job)],env=env,cwd=ROOT,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW)
            for line in process.stdout:
                log.write(line);log.flush()
                if line.startswith(('Loading the local','Acting line ','Saved acted line','Acted dialogue')):print(line.rstrip(),flush=True)
            if process.wait()!=0:raise RuntimeError('The local voice performance failed. Details are saved in acting-worker.log; the previous video was preserved.')
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe();durations=[];timings=[];offset=0
    for i,panel in enumerate(data['panels'],1):
        elapsed=0
        with wave.open(str(folder/f'voice_{i:02}.wav'),'wb') as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(24000)
            for line in [x for x in plan['lines'] if x['panel']==i]:
                raw=subprocess.run([ffmpeg,'-v','error','-i',line['path'],'-f','s16le','-ac','1','-ar','24000','pipe:1'],check=True,capture_output=True).stdout
                seconds=len(raw)/48000;timings.append({'start':offset+elapsed,'end':offset+elapsed+seconds,'speaker':line['character'],'text':line['text'],'emotion':line['emotion']})
                output.writeframes(raw);output.writeframes(b'\0\0'*7200);elapsed+=seconds+.3
            if not elapsed:output.writeframes(b'\0\0'*24000*3);elapsed=3
        duration=__import__('math').ceil((elapsed+.4)*24)/24;durations.append(duration);offset+=duration
    (folder/'acted_subtitle_timings.json').write_text(json.dumps(timings,indent=2),encoding='utf-8')
    (folder/'dialogue_voice_settings.json').write_text(json.dumps({'engine':'Qwen3-TTS-12Hz-1.7B-CustomVoice','casting':plan['casting'],
        'lines':[{'speaker':x['character'],'voice':x['speaker'],'emotion':x['emotion'],'text':x['text']} for x in plan['lines']]},indent=2),encoding='utf-8')
    return durations
