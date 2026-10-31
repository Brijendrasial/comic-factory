"""Local comic factory. No hosted inference or paid APIs."""
import os
from pathlib import Path
from runtime_paths import DATA_HOME, CODE_HOME, ensure_data, engine_python
ROOT = ensure_data()
os.environ.setdefault('HF_HOME', str(ROOT / 'models'))
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
import argparse
import datetime as dt
import gc
import json
import math
import random
import subprocess
import sys
import time
import traceback
import wave
from PIL import Image, ImageDraw, ImageFont, ImageOps

def log(message):
    try:
        print(message, flush=True)
    except OSError as exc:
        if exc.errno not in (22,32):raise
        # A closed GUI pipe must not invalidate a successfully saved project.
        sys.stdout=sys.stderr=open(ROOT/'factory-output.log','a',encoding='utf-8',buffering=1)
        print(message,flush=True)

def save_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)

def config():
    c = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    if not 1 <= int(c['comics_per_batch']) <= 100:
        raise ValueError('Choose between 1 and 100 comics per batch.')
    if not 2 <= int(c['panels']) <= 12:
        raise ValueError('Choose between 2 and 12 panels.')
    if c['language'].lower() != 'english':
        raise ValueError('This first version supports English narration. Add a matching Piper voice and text layout before changing language.')
    if c.get('offline'):
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
    return c

def release():
    import torch
    gc.collect()
    try:
        torch.cuda.empty_cache()
    except RuntimeError:
        # After a CUDA failure, cleanup must not hide the original error.
        log('The GPU could not clear its cache after an error. Saved pages are retained; restart the planning process to resume.')

def story_request(c, cast, premise, setting, detail):
    user_prompt=c.get('prompt','').strip()
    if user_prompt:
        return (f'Write a complete English comic story in about {c["panels"]*30} words. '
            f'Use {c["panels"]} short paragraphs, one per panel. '
            'Follow the reader\'s requested characters, setting, events, tone and ending. '
            'Keep the named characters and their identities. Do not replace them with unrelated characters. '
            'Do not change their costumes. Focus narration on actions rather than describing clothing. '
            'Every paragraph must describe concrete visible actions by named characters. Avoid poetic metaphors. '
            'Give the story a clear beginning, middle and ending that fits the request. '
            f'Character appearance reference: {cast}\n'
            f'Fixed visual and story facts: {c.get("continuity","")}\n'
            f'READER REQUEST:\n{user_prompt}\n'
            'Return only the story, no title, labels or commentary.')
    return (f'Tell a complete {c["panels"]*30}-word science fiction story for a {c["audience"]} audience. '
        f'The main characters are: {cast} {premise} '
        f'Start in {setting}. Include a {detail} as a small visual detail. '
        f'Creative theme: {c["theme"]}. '
        f'{c["panels"]} short paragraphs. Explain exactly how they solve the problem. '
        'End happily. Only the story, no title or labels.')

def validate_story(data, count):
    if isinstance(data,dict) and data.get('format')=='comic-book-v1':
        from book import validate_book
        return validate_book(data)
    if not isinstance(data, dict) or not isinstance(data.get('title'), str) or not data['title'].strip():
        raise ValueError('Story needs a title.')
    if not isinstance(data.get('characters'), str) or not data['characters'].strip():
        raise ValueError('Story needs fixed character descriptions.')
    if len(data.get('panels', [])) != count:
        raise ValueError(f'Story needs exactly {count} panels.')
    for panel in data['panels']:
        for key in ['scene', 'narration']:
            if not isinstance(panel.get(key), str) or not panel[key].strip():
                raise ValueError(f'Panel needs {key}.')
        if len(panel['narration'].split()) > 90:
            raise ValueError('Narration is too long for a readable panel.')
    return data

def story(c, folder):
    from scripted import parse_script
    explicit=parse_script(c)
    if explicit is not None:
        log('Keeping your exact script, dialogue and separate character descriptions.')
        validate_story(explicit,c['panels'])
        save_json(folder/'story.json',explicit)
        (folder/'story.txt').write_text(explicit['title']+'\n\n'+'\n\n'.join(p['narration'] for p in explicit['panels']),encoding='utf-8')
        return explicit
    if c.get('prompt','').strip() and any(folder.glob('structured_story_attempt_*.json')):
        from book import request_spec
        if request_spec(c)['pages']==1:
            from single_story import plan
            recovered=plan(c,folder,None,log,save_json,random.SystemRandom().randrange(2**31),cached_only=True)
            if recovered is not None:return recovered
    import re
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, StoppingCriteria, StoppingCriteriaList
    from copy import deepcopy
    log('Writing an original story locally...')
    local_writer=ROOT/'local_models'/('writer_v2' if 'Qwen3-4B' in c['story_model'] else 'writer')
    source = str(local_writer) if (local_writer/'download_manifest.json').exists() else c['story_model']
    tokenizer = AutoTokenizer.from_pretrained(source)
    if 'bnb-4bit' in c['story_model']:
        model=AutoModelForCausalLM.from_pretrained(source,dtype=torch.bfloat16,device_map={'':'cuda:0'})
    else:
        model = AutoModelForCausalLM.from_pretrained(source, dtype=torch.float16).to('cuda')
    seed = random.SystemRandom().randrange(2**31)
    torch.manual_seed(seed)
    rng = random.Random(seed)
    cast = rng.choice([
        'Pip is a round yellow robot wearing a teal scarf. Mira is a red-haired girl wearing a blue jacket.',
        'Niko is a curly-haired boy wearing green overalls. Lumi is a small silver robot with round blue eyes.',
        'Ada is a dark-haired girl wearing a purple spacesuit. Bolt is a small orange robot with a square face.'
    ])
    premise = rng.choice([
        'They help a lost alien child get home by reconnecting a loose wire inside a broken star-lamp.',
        'They save a wilting moon garden by clearing a pebble from its blocked watering pipe.',
        'They rescue a tiny delivery drone caught in a tree by building a safe ramp from spare boards.',
        'They restore music to a space festival by cleaning dust from a robot orchestra bell.',
        'They find a stranded explorer and guide them home by realigning a signal mirror.',
        'They fix a dark moon library by recharging its solar battery with a portable mirror.',
        'They help a shy alien join a parade by building a little cart for its oversized musical instrument.',
        'They stop a floating picnic from drifting away by tying the baskets together with a spare scarf.'
    ])
    setting = rng.choice(['a rooftop garden','a moon village','a floating market','a seaside spaceport',
        'a forest observatory','a desert research station','a snowy mountain town','a colorful canal city',
        'a little asteroid farm','a bustling robot neighborhood','a glass-domed greenhouse','a quiet hilltop library'])
    detail = rng.choice(['striped umbrella','paper kite','tiny teapot','blue bicycle','polka-dot hat',
        'orange watering can','glowing pebble','green lunchbox','singing flower','wind-up duck',
        'patchwork blanket','red balloon','wooden toy boat','silver lunch tray','yellow raincoat','little pinwheel'])
    tokenizer_data=[None]
    def generate(prompt, max_tokens=600, sample=False,schema=None):
        inputs = tokenizer.apply_chat_template([{'role':'user','content':prompt}],tokenize=True,
            add_generation_prompt=True,return_tensors='pt').to('cuda')
        generation=deepcopy(model.generation_config)
        generation.do_sample=sample
        generation.temperature=0.7 if sample else None
        generation.top_p=0.9 if sample else None
        generation.top_k=20 if sample else None
        # Long book prompts otherwise allocate a full quadratic attention matrix
        # during prefill, on top of the model and growing GPU KV cache.
        generation.use_cache=True
        generation.prefill_chunk_size=256
        generation.cache_implementation='offloaded'
        generation.cache_config=None
        log(f'Reading {inputs.shape[-1]} context tokens in small chunks; writer cache uses system memory.')
        constrained={}
        if schema is not None:
            from lmformatenforcer import JsonSchemaParser,CharacterLevelParserConfig
            from lmformatenforcer.integrations.transformers import build_token_enforcer_tokenizer_data,build_transformers_prefix_allowed_tokens_fn
            if tokenizer_data[0] is None:
                log('Preparing structured writing checks locally...')
                tokenizer_data[0]=build_token_enforcer_tokenizer_data(tokenizer)
            parser_config=CharacterLevelParserConfig(force_json_field_order=bool(schema.get('x-ordered',False)))
            constrained['prefix_allowed_tokens_fn']=build_transformers_prefix_allowed_tokens_fn(tokenizer_data[0],JsonSchemaParser(schema,config=parser_config))
        started=time.monotonic();last=[started]
        class Progress(StoppingCriteria):
            def __call__(self,input_ids,scores,**kwargs):
                now=time.monotonic()
                if now-last[0]>=15:
                    log(f'Writer active: {input_ids.shape[-1]-inputs.shape[-1]} tokens generated, {int(now-started)} seconds.');last[0]=now
                return False
        with torch.inference_mode():
            output = model.generate(inputs,attention_mask=torch.ones_like(inputs),max_new_tokens=max_tokens,
                        pad_token_id=tokenizer.eos_token_id,generation_config=generation,use_model_defaults=False,
                        stopping_criteria=StoppingCriteriaList([Progress()]),**constrained)
        return tokenizer.decode(output[0,inputs.shape[-1]:],skip_special_tokens=True).strip()
    try:
        from book import request_spec,plan_book
        spec=request_spec(c)
        if spec['pages']>1:
            log(f'Request detected: {spec["pages"]} pages, {spec["panels_per_page"]} panels per page. The short-comic panel setting will not shorten this book.')
            return plan_book(c,folder,generate,log,save_json)
        if c.get('prompt','').strip():
            from single_story import plan
            return plan(c,folder,generate,log,save_json,seed)
        custom=bool(c.get('prompt','').strip())
        if c.get('characters','').strip():
            cast=c['characters'].strip()
        elif custom:
            log('Identifying the characters from your prompt...')
            cast=generate('Name the main characters requested below and briefly describe their visual appearance and costumes. '
                'For established comic-book heroes, use their recognizable appearance. '
                'Do not invent replacement characters. Return only appearance descriptions in about 40 words.\n'+c['prompt'],180)
            cast=re.sub(r'(?i)\b(?:appearance|costume)\s*:', '',cast.replace('**',''))
            cast=' '.join(cast.split())
        continuity=c.get('continuity','').strip()
        if not continuity:
            continuity=generate('Write a concise visual continuity guide for recurring objects and locations in this comic request. '
                'Choose consistent colors and materials if unspecified. Preserve stated physical conditions, such as a broken bridge remaining broken. '
                'Do not add story events or change facts. Return entries as Object: description, one entry per line. '
                'Use short object nouns as keys, for example Train: silver passenger train; Bridge: broken middle span. About 40 words total.\n'+
                (c['prompt'] if custom else premise+' '+setting),140)
        feedback=''
        for attempt in range(3):
            planning=dict(c,continuity=continuity)
            prompt = story_request(planning,cast,premise,setting,detail)
            if feedback:
                prompt+='\nCorrect these problems from the previous draft: '+feedback
            prose = generate(prompt, c['panels']*150+150, attempt>0)
            (folder/f'story_attempt_{attempt+1}.txt').write_text(prose,encoding='utf-8')
            paragraphs = [re.sub(r'^\s*(?:\d+[.)]|Panel\s+\d+:)\s*','',p.strip(),flags=re.I)
                          for p in re.split(r'\n\s*\n',prose) if p.strip()]
            if len(paragraphs)!=c['panels']:
                sentences=re.split(r'(?<=[.!?])\s+', ' '.join(paragraphs))
                if len(sentences)<c['panels']:
                    log('Retrying story: too few complete sentences for the panel count.')
                    continue
                cumulative=[0]
                for sentence in sentences:
                    cumulative.append(cumulative[-1]+len(sentence.split()))
                cuts=[0]
                for n in range(1,c['panels']):
                    candidates=range(cuts[-1]+1,len(sentences)-(c['panels']-n)+1)
                    cuts.append(min(candidates,key=lambda j:abs(cumulative[j]-cumulative[-1]*n/c['panels'])))
                cuts.append(len(sentences))
                paragraphs=[' '.join(sentences[a:b]) for a,b in zip(cuts,cuts[1:])]
            review_question=('Does this story have a complete ending AND preserve the characters, events, setting and physical facts in the reader request? '
                'Reply NO for contradictions, such as a broken object suddenly being intact without being repaired, '
                'or a character changing costumes. A sad or suspenseful ending is allowed when requested. Reader request: '+c['prompt']+'\n'
                if custom else 'Does it end with the characters successfully solving the main problem? ')
            review = generate('Read this story. '+review_question+
                'Reply YES or NO, then one sentence explaining why.\nSTORY:\n'+prose,100)
            (folder/f'review_attempt_{attempt+1}.txt').write_text(review,encoding='utf-8')
            if not review.upper().lstrip('*').startswith('YES'):
                feedback=review
                log('Retrying story: the ending did not pass local review.')
                continue
            panels=[]
            for paragraph in paragraphs:
                narration=paragraph
                if len(narration.split())>45:
                    condensed=generate('Rewrite this story paragraph as two short sentences, about 30 words total. '
                        'Keep the character names, actions and outcome. Return ONLY the rewritten paragraph.\n'+paragraph,150)
                    if 12<=len(condensed.split())<=65 and condensed.rstrip().endswith(('.', '!', '?', '"', '\u201d')):
                        narration=condensed.replace('\n',' ')
                # Reject incomplete sentences instead of drawing truncated output.
                if not narration.rstrip().endswith(('.', '!', '?', '"', '\u201d')) or len(narration.split())>90:
                    break
                context=(c.get('prompt','') if custom else premise+' '+setting)+'\nCONTINUITY: '+continuity
                scene_instruction=('Describe one illustration of the following story moment in one sentence under 30 words. '
                    'Use exact character names and ONE concrete visible action. Name important objects and the location. '
                    'Use a wide or medium camera view. Follow the story facts; do not add plot events, injuries or props. '
                    'For abstract feelings show the characters reacting at the established location. No metaphors, text or commentary. '
                    '\nCHARACTERS: '+cast+'\nREADER REQUEST: '+context+'\nSTORY MOMENT: '+narration)
                scene_feedback=''
                for scene_attempt in range(2):
                    scene=generate(scene_instruction+scene_feedback,120)
                    scene_review=generate('Check the illustration against the story moment AND reader request. '
                        'Camera angles and visible expressions are allowed. Reply NO for invented events, conflicting actions, '
                        'wrong characters, wrong locations or metaphors that cannot be drawn. '
                        'Reply YES or NO followed by a brief reason.\nREADER REQUEST: '+context+
                        '\nSTORY MOMENT: '+narration+'\nILLUSTRATION: '+scene,70)
                    if scene_review.upper().strip(' *').startswith('YES'):
                        break
                    scene_feedback='\nCorrect the previous description: '+scene_review
                panels.append({'scene':scene.replace('\n',' '),'narration':narration,
                    'scene_check':scene_review,'needs_review':not scene_review.upper().strip(' *').startswith('YES')})
            if len(panels)!=c['panels']:
                log('Retrying story: one paragraph was too long or unfinished.')
                continue
            title=spec['title'] or generate('Give this story a title of at most six words that fits its requested tone. Reply only with the title.\n'+prose,35)
            if not spec['title']:title=title.splitlines()[0].strip(' #*"')[:80]
            data={'title':title,'characters':cast,'panels':panels,'seed':seed}
            try:
                validate_story(data,c['panels'])
            except ValueError as exc:
                log('Retrying story: '+str(exc))
                continue
            words = ' '.join(p['narration'].lower() for p in panels)
            duplicate=False
            for existing in (ROOT/'library').glob('*/story.json'):
                if existing.parent==folder:
                    continue
                prior=json.loads(existing.read_text(encoding='utf-8'))
                if ' '.join(p['narration'].lower() for p in prior['panels'])==words:
                    duplicate=True
                    break
            if duplicate:
                log('Retrying story: this story already exists in the library.')
                continue
            data.update(request_prompt=c.get('prompt',''),visual_continuity=continuity,premise='' if custom else premise,setting='' if custom else setting)
            save_json(folder/'story.json',data)
            (folder/'story.txt').write_text(title+'\n\n'+'\n\n'.join(p['narration'] for p in panels),encoding='utf-8')
            return data
        raise RuntimeError('The local writer could not produce a complete story after three attempts. See story_attempt files.')
    finally:
        del model,tokenizer
        release()


def illustration_prompts(c, data, panel, tokenizer, tokenizer_2):
    def shorten(text, encoder, budget):
        ids=encoder.encode(text,add_special_tokens=False,truncation=False)
        return encoder.decode(ids[:budget],skip_special_tokens=True)
    from art_quality import scoped_appearance
    appearance = scoped_appearance(data['characters'],panel).replace(' is a ', ', ').replace(' wearing a ', ', ').replace(' with ', ', ')
    # Reserve space for both identity and action in CLIP's 77-token window.
    first=f"Single scene, coherent anatomy. {shorten(panel['scene'],tokenizer,43)}. {shorten(c['style'],tokenizer,20)}"
    if any(word in panel['scene'].lower() for word in ['press','push','pull','brac','grip','lift']):
        second=f"{shorten(panel['scene'],tokenizer_2,43)}. {shorten(appearance,tokenizer_2,27)}"
    else:
        second=f"{shorten(appearance,tokenizer_2,35)}. {shorten(panel['scene'],tokenizer_2,35)}"
    return shorten(first,tokenizer,75),shorten(second,tokenizer_2,75)

def illustrations(c, data, folder):
    if c.get('image_engine')=='klein':
        from klein_engine import generate_illustrations
        generate_illustrations(c,data,folder)
        return
    from art_engine import generate_illustrations
    log('Loading the improved local drawing pipeline...')
    generate_illustrations(c,data,folder,illustration_prompts)

def font(size):
    for name in ['C:/Windows/Fonts/segoeui.ttf', 'C:/Windows/Fonts/arial.ttf']:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default(size=size)

def draw_text_box(image, text, box, initial=30, color='white'):
    draw = ImageDraw.Draw(image)
    x,y,w,h = box
    for size in range(initial, 17, -1):
        f = font(size)
        lines, line = [], ''
        for word in text.split():
            candidate = (line + ' ' + word).strip()
            if draw.textlength(candidate, font=f) > w and line:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        spacing = int(size*1.4)
        if len(lines)*spacing <= h:
            for j,line in enumerate(lines):
                draw.text((x,y+j*spacing), line, font=f, fill=color)
            return
    raise ValueError('Caption is too long to fit. Shorten narration in story.json.')

def cards(data, folder, width=1024, preview=False):
    if any(p.get('dialogue') for p in data['panels']):
        from lettering import dialogue_card
        results=[];lettering_audit=[]
        for i,panel in enumerate(data['panels'],1):
            with Image.open(folder/f'art_{i:02}.png') as art:
                card,layout=dialogue_card(data,panel,art,width,font)
            card.save(folder/f'panel_{i:02}.png');results.append(card);lettering_audit.append(dict(panel=i,**layout))
        save_json(folder/'layout.json',layout)
        save_json(folder/'lettering_layout.json',lettering_audit)
        gutter=width//48;rows=math.ceil(len(results)/2)
        title_height=width//10
        page=Image.new('RGB',(width*2+gutter*3,(layout['height']+gutter)*rows+gutter+title_height),'white')
        draw=ImageDraw.Draw(page)
        draw.text((gutter,title_height//4),data['title'],font=font(width//23),fill='#111827')
        for i,card in enumerate(results):page.paste(card,(gutter+(i%2)*(width+gutter),title_height+gutter+(i//2)*(layout['height']+gutter)))
        if preview:
            ImageDraw.Draw(page).rectangle((0,0,page.width,24),fill='#9a3412')
            ImageDraw.Draw(page).text((8,3),'PREVIEW - ARTWORK NEEDS REVIEW',fill='white')
        page.save(folder/('comic_preview.png' if preview else 'comic.png'))
        results[0].save(folder/'cover.jpg',quality=92)
        return
    top=width*5//64
    footer=width//4
    height=width+top+footer
    margin=width*3//100
    layout={'width':width,'height':height,'art_top':top,'art_size':width,'caption_top':top+width}
    save_json(folder/'layout.json',layout)
    for i,panel in enumerate(data['panels'], 1):
        art = Image.open(folder/f'art_{i:02}.png').convert('RGB')
        art=ImageOps.pad(art,(width,width),color='#111827')
        card = Image.new('RGB', (width,height), '#111827')
        card.paste(art, (0,top))
        title_box=(margin,top//5,width-2*margin,top*3//4)
        caption_box=(margin,top+width+margin,width-2*margin,footer-2*margin)
        draw_text_box(card, f"{data['title']}  |  {i}", title_box, width//30)
        draw_text_box(card, panel['narration'], caption_box, width//30)
        card.save(folder/f'panel_{i:02}.png')
        overlay = Image.new('RGBA', (width,height), (0,0,0,0))
        draw = ImageDraw.Draw(overlay)
        draw.rectangle((0,0,width,top-1), fill='#111827')
        draw.rectangle((0,top+width,width,height), fill='#111827')
        draw_text_box(overlay, f"{data['title']}  |  {i}", title_box, width//30)
        draw_text_box(overlay, panel['narration'], caption_box, width//30)
        overlay.save(folder/f'overlay_{i:02}.png')
    rows = math.ceil(len(data['panels'])/2)
    gutter=width//48
    page = Image.new('RGB', (2*width+3*gutter,rows*(height+gutter)+gutter), '#e5e7eb')
    for i in range(len(data['panels'])):
        page.paste(Image.open(folder/f'panel_{i+1:02}.png'), (gutter+(i%2)*(width+gutter),gutter+(i//2)*(height+gutter)))
    if preview:
        ImageDraw.Draw(page).rectangle((0,0,page.width,24),fill='#9a3412')
        ImageDraw.Draw(page).text((8,3),'PREVIEW - ARTWORK NEEDS REVIEW',fill='white')
    page.save(folder/('comic_preview.png' if preview else 'comic.png'))
    Image.open(folder/'panel_01.png').save(folder/'cover.jpg', quality=92)

def checked_cards(data,folder,width=1024,preview=False):
    from speech_layout import BalloonLayoutError
    try:
        cards(data,folder,width,preview=preview)
        (folder/'lettering_review.json').unlink(missing_ok=True)
        return True
    except BalloonLayoutError as exc:
        save_json(folder/'lettering_review.json',{'issue':str(exc),'artwork_preserved':True})
        log('Speech balloon placement needs review: '+str(exc))
        log(f'STORYBOARD_READY:{folder}')
        return False

def voice_model(c):
    from huggingface_hub import hf_hub_download
    name = c['voice']
    if name != 'en_US-lessac-medium':
        raise ValueError('This version is configured for the English Lessac voice.')
    base = 'en/en_US/lessac/medium/'
    target = ROOT/'voices'
    for suffix in ['.onnx', '.onnx.json']:
        path = target/(name+suffix)
        if not path.exists():
            source = hf_hub_download('rhasspy/piper-voices', base+name+suffix)
            target.mkdir(exist_ok=True)
            import shutil
            shutil.copy2(source,path)
    return target/(name+'.onnx')

def narration(c, data, folder):
    if data.get('script_source')=='explicit-user-script-v1' or any(p.get('dialogue') for p in data['panels']):
        from dialogue_voice import synthesize
        log('Performing character dialogue locally with distinct voices and line emotions...')
        return synthesize(c,data,folder,voice_model)
    from piper import PiperVoice
    log('Recording narration locally...')
    voice = PiperVoice.load(str(voice_model(c)))
    durations = []
    for i,panel in enumerate(data['panels'], 1):
        path = folder/f'voice_{i:02}.wav'
        if not path.exists():
            with wave.open(str(path),'wb') as output:
                voice.synthesize_wav(panel['narration'], output)
        with wave.open(str(path),'rb') as wav:
            durations.append(wav.getnframes()/wav.getframerate()+0.4)
    return durations

def stamp(seconds):
    milliseconds = round(seconds*1000)
    s,ms = divmod(milliseconds,1000)
    minutes,s = divmod(s,60)
    hours,minutes = divmod(minutes,60)
    return f'{hours:02}:{minutes:02}:{s:02},{ms:03}'

def video(data, folder, durations, background_music=False, music_settings=None):
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    layout=json.loads((folder/'layout.json').read_text()) if (folder/'layout.json').exists() else {'width':768,'height':1024,'art_top':64}
    width,height,top=layout['width'],layout['height'],layout['art_top']
    clips, subtitles, offset = [], [], 0.0
    for i,(panel,duration) in enumerate(zip(data['panels'],durations),1):
        log(f'Animating and subtitling panel {i}...')
        frames = math.ceil(duration*24)
        duration = frames/24
        clip = folder/f'clip_{i:02}.mp4'
        graph = (f"[0:v]scale={width*2}:{width*2},zoompan=z='min(zoom+0.00018,1.08)':"
                 f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={frames}:s={width}x{width}:fps=24,"
                 f"pad={width}:{height}:0:{top}:color=0x111827[art];[art][1:v]overlay=0:0[v]")
        if layout.get('speech_balloons'):
            subprocess.run([ffmpeg,'-y','-loglevel','error','-loop','1','-i',str(folder/f'panel_{i:02}.png'),
                '-i',str(folder/f'voice_{i:02}.wav'),'-map','0:v','-map','1:a','-af','apad','-t',str(duration),
                '-r','24','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-ar','44100','-ac','1',str(clip)],check=True)
        else:
            subprocess.run([ffmpeg,'-y','-loglevel','error','-i',str(folder/f'art_{i:02}.png'),
                        '-i',str(folder/f'overlay_{i:02}.png'),'-i',str(folder/f'voice_{i:02}.wav'),
                        '-filter_complex',graph,'-map','[v]','-map','2:a', '-af','apad',
                        '-t',str(duration),'-c:v','libx264','-preset','fast','-crf','20',
                        '-pix_fmt','yuv420p','-c:a','aac','-ar','44100','-ac','1',str(clip)],check=True)
        clips.append(f"file '{clip.name}'")
        subtitles.append(f"{i}\n{stamp(offset)} --> {stamp(offset+duration)}\n{panel['narration']}\n")
        offset += duration
    if (folder/'acted_subtitle_timings.json').exists() and any(p.get('dialogue') for p in data['panels']):
        timings=json.loads((folder/'acted_subtitle_timings.json').read_text(encoding='utf-8'))
        subtitles=[f"{i}\n{stamp(t['start'])} --> {stamp(t['end'])}\n{t['text']}\n" for i,t in enumerate(timings,1)]
    (folder/'subtitles.srt').write_text('\n'.join(subtitles),encoding='utf-8')
    (folder/'clips.txt').write_text('\n'.join(clips),encoding='utf-8')
    subprocess.run([ffmpeg,'-y','-loglevel','error','-f','concat','-safe','0','-i',str(folder/'clips.txt'),
                    '-c','copy','-movflags','+faststart',str(folder/'comic_narration.mp4')],check=True)
    from music import apply_music
    settings=dict(music_settings or {},background_music=background_music)
    apply_music(folder,settings,offset)

def make(c, folder, plan_only=False):
    started = time.time()
    folder.mkdir(parents=True,exist_ok=True)
    log(f'PROJECT_CREATED:{folder}')
    save_json(folder/'settings.json',c)
    if (folder/'story.json').exists():
        data = validate_story(json.loads((folder/'story.json').read_text(encoding='utf-8')),c['panels'])
    else:
        data = story(c,folder)
    if data is None:return
    from book import request_spec
    if request_spec(dict(c,prompt=data.get('request_prompt','')))['pages']>1 and data.get('format')!='comic-book-v1':
        raise ValueError('This older project contains a short comic despite a multi-page request. It has been preserved. Create a new comic to use the corrected book planner.')
    uncertain=any(panel.get('needs_review') for panel in data['panels']) and not data.get('storyboard_reviewed',False)
    if plan_only or uncertain:
        if uncertain:
            log('A scene needs review before drawing. Correct or approve it in the storyboard editor.')
        log(f'STORYBOARD_READY:{folder}')
        return
    if data.get('format')=='comic-book-v1':
        from book import render_book
        if render_book(c,data,folder,illustrations,cards,log,save_json):
            save_json(folder/'complete.json',{'title':data['title'],'pages':data['book_spec']['pages'],'seconds':round(time.time()-started,1),'completed':dt.datetime.now().isoformat()})
            log(f'Finished: {folder}')
        return
    illustrations(c,data,folder)
    save_json(folder/'story.json',data)
    from art_quality import pending_reviews
    pending=pending_reviews(c,data,folder)
    if pending:
        from project import archive_files
        archive_files(folder,[folder/name for name in ['comic.png','comic.mp4','comic_narration.mp4','complete.json']])
        if not checked_cards(data,folder,int(c.get('output_width',1024)),preview=True):return
        save_json(folder/'render_status.json',{'state':'needs_art_review','preview':'comic_preview.png','video_created':False,'panels':pending})
        log('Some drawings need anatomy review before comic/video assembly. Open the storyboard to inspect or regenerate those panels.')
        log('ART_REVIEW_REQUIRED:'+str(folder))
        log(f'STORYBOARD_READY:{folder}')
        return
    if not checked_cards(data,folder,int(c.get('output_width',1024))):return
    durations = narration(c,data,folder)
    video(data,folder,durations,c.get('background_music',False),c)
    save_json(folder/'render_status.json',{'state':'complete','comic':'comic.png','video':'comic.mp4'})
    save_json(folder/'complete.json',{'title':data['title'],'seconds':round(time.time()-started,1),'completed':dt.datetime.now().isoformat()})
    log(f'Finished: {folder}')

def run_batch(c, count=None, resume=None, plan_only=False):
    from filelock import FileLock, Timeout
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('NVIDIA GPU is unavailable to PyTorch. Check the driver and CUDA-enabled PyTorch installation.')
    # File locks are released by the OS even if the process crashes.
    try:
        with FileLock(str(ROOT/'factory.lock'), timeout=0):
            (ROOT/'stop-after-current.flag').unlink(missing_ok=True)
            if resume:
                from project import archive_files
                archive_files(Path(resume),[Path(resume)/'error.txt'])
                if not (Path(resume)/'story.json').exists():
                    if not (Path(resume)/'settings.json').exists():raise ValueError('This folder has no saved comic request to resume.')
                    saved_settings=json.loads((Path(resume)/'settings.json').read_text(encoding='utf-8'))
                    saved_settings['_plan_page_limit']=c.get('_plan_page_limit',0)
                    make(saved_settings,Path(resume).resolve(),plan_only)
                    return
                saved=json.loads((Path(resume)/'story.json').read_text(encoding='utf-8'))
                c['panels']=saved.get('book_spec',{}).get('panels_per_page',len(saved['panels']))
                c['prompt']=saved.get('request_prompt','')
                c['characters']=saved['characters']
                c['continuity']=saved.get('visual_continuity','')
                make(c,Path(resume).resolve(),plan_only)
                return
            failures = []
            for n in range(count or int(c['comics_per_batch'])):
                if (ROOT/'stop-after-current.flag').exists():
                    log('Stopped after finishing the current comic.')
                    break
                if __import__('shutil').disk_usage(ROOT).free < 15*1024**3:
                    raise RuntimeError('Less than 15 GB disk space remains. Generation stopped.')
                folder = ROOT/'library'/f"{dt.datetime.now():%Y-%m-%d_%H-%M-%S}_{n+1:02}"
                try:
                    make(c,folder,plan_only)
                except Exception:
                    folder.mkdir(parents=True,exist_ok=True)
                    (folder/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
                    failures.append(str(folder))
                    log(f'Comic failed; details saved in {folder}/error.txt')
                    release()
            if failures:
                raise RuntimeError(f'{len(failures)} comic(s) failed. Review the error files and resume those folders.')
    except Timeout:
        raise RuntimeError('A comic batch is already running. Wait for it to finish.')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count',type=int)
    parser.add_argument('--resume')
    parser.add_argument('--prompt',help='Comic characters, setting and plot to follow.')
    parser.add_argument('--characters',help='Optional fixed appearance and costume descriptions.')
    parser.add_argument('--plan-only',action='store_true',help='Write the storyboard for review before drawing.')
    parser.add_argument('--plan-limit',type=int,default=0,help='Pause after this many scripted book pages; zero plans the complete book. Use with --plan-only.')
    parser.add_argument('--music-only',action='store_true',help='Update music on an existing comic without regenerating artwork.')
    parser.add_argument('--voice-only',action='store_true',help='Upgrade character voices and rebuild video while preserving artwork.')
    args = parser.parse_args()
    try:
        c=config()
        if args.plan_limit<0 or (args.plan_limit and not args.plan_only):raise ValueError('--plan-limit requires --plan-only and a nonnegative page count.')
        c['_plan_page_limit']=args.plan_limit
        if args.prompt is not None:
            c['prompt']=args.prompt.strip()
        if args.characters is not None:
            c['characters']=args.characters.strip()
        if args.voice_only:
            if not args.resume:raise ValueError('Choose an existing comic with --resume to upgrade its voices.')
            from filelock import FileLock
            from voice_upgrade import rebuild
            with FileLock(str(ROOT/'factory.lock'),timeout=0):rebuild(c,Path(args.resume).resolve())
            return
        if args.music_only:
            if not args.resume:
                raise ValueError('Choose an existing comic with --resume when updating music.')
            from filelock import FileLock
            from music import apply_music
            with FileLock(str(ROOT/'factory.lock'),timeout=0):
                apply_music(Path(args.resume),c)
            log(f'Finished: {Path(args.resume).resolve()}')
            return
        run_batch(c,args.count,args.resume,args.plan_only)
    except Exception:
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
