"""Explicit multi-page requests, checkpointed scripts, and one image per page."""
import copy
import json
import random
import re
import shutil
from pathlib import Path


def request_spec(c):
    text=c.get('prompt','')
    counts=[int(n) for n in re.findall(r'(?i)\b(\d+)\s*[-–— ]\s*pages?\b',text)]
    pages=counts[0] if counts else 1
    if pages>60 or pages<1:
        raise ValueError('Use 1–60 pages per book.')
    title=re.search(r'(?i)\btitled\s*[*_]*["“]([^"”]+)["”]',text)
    span=re.search(r'(?i)(\d+)\s*[-–—]\s*(\d+)\s+panels?\s+per\s+page',text)
    low,high=(int(span[1]),int(span[2])) if span else (4,6)
    if not 1<=low<=high<=12:raise ValueError('Unsupported panels-per-page range.')
    panels=min(high,max(low,int(c.get('panels',4))))
    return {'pages':pages,'panels_per_page':panels,'min_panels':low,'max_panels':high,
            'title':title[1].strip() if title else None,
            'anchors':[name for name in ['Superman','Lois Lane','Clark Kent','Batman','Wonder Woman'] if name.lower() in text.lower()]}


def json_answer(text):
    text=re.sub(r'<think>.*?</think>','',text,flags=re.S).strip()
    text=re.sub(r'^```(?:json)?\s*|\s*```$','',text,flags=re.I).strip()
    start=text.find('{')
    if start<0:raise ValueError('The writer did not return JSON.')
    value,end=json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(value,dict):raise ValueError('Expected a JSON object.')
    if text[start+end:].strip():raise ValueError('Unexpected text after JSON.')
    return value


def words(text):
    return len(text.split())


def lettering(panel):
    return '\n'.join(f'{b["speaker"]}: {b["text"]}' for b in panel['dialogue'])


def page_warnings(page,bible):
    notes=[]
    time_clause=re.search(r'(?i)\btime\s*:\s*([^.;\n]+)',page.get('continuity',''))
    if time_clause and re.search(r'(?i)\b(morning|dawn|sunrise)\b',time_clause[1]) and re.search(r'(?i)\b\d{1,2}(?::\d\d)?\s*pm\b',time_clause[1]):
        notes.append('The continuity notes mix morning with a PM time. Check the time of day and lighting.')
    protocol=re.search(r'(?im)^release_protocol:\s*(.*)',bible.get('rules',''))
    if protocol and re.search(r'\b(fear|fears|empathy|emotion|emotional|belief|breath)\b',protocol[1],re.I):
        notes.append('The saved machine solution relies on feelings instead of a physical release procedure. Review the story rules before drawing.')
    return notes


def validate_page(page,number,count):
    if page.get('number')!=number:raise ValueError(f'Expected page {number}.')
    if len(page.get('panels',[]))!=count:raise ValueError(f'Use exactly {count} panels on this page.')
    spoken=0
    for i,panel in enumerate(page['panels'],1):
        if not isinstance(panel.get('visual'),str) or not panel['visual'].strip():raise ValueError('Each panel needs a visual.')
        if not isinstance(panel.get('dialogue'),list):raise ValueError('Use dialogue: [] for a silent panel.')
        for balloon in panel['dialogue']:
            if not all(isinstance(balloon.get(k),str) and balloon[k].strip() for k in ['speaker','text']):raise ValueError('Each balloon needs speaker and exact text.')
            if words(balloon['text'])>25:raise ValueError('A speech balloon exceeds 25 words.')
            spoken+=words(balloon['text'])
        if not isinstance(panel.get('sfx',''),str):raise ValueError('Sound effects must be a string, empty when unnecessary.')
        panel['number']=i
    if spoken>100:raise ValueError('This page exceeds 100 spoken/caption words.')
    if not isinstance(page.get('continuity'),str):raise ValueError('Include the end-of-page continuity notes.')
    return page


def validate_book(data):
    spec=data['book_spec']
    expected=spec['pages']*spec['panels_per_page']
    if len(data.get('panels',[]))!=expected:raise ValueError('The saved book has missing panels.')
    if spec['title'] and data['title']!=spec['title']:raise ValueError('The requested title was changed.')
    for n in range(1,spec['pages']+1):
        panels=[p for p in data['panels'] if p.get('page')==n]
        if len(panels)!=spec['panels_per_page']:raise ValueError(f'Page {n} is incomplete.')
        if [p.get('panel') for p in panels]!=list(range(1,len(panels)+1)):raise ValueError('Panel numbering is inconsistent.')
        total=0
        for p in panels:
            if not p.get('scene','').strip():raise ValueError('A visual is missing.')
            # The editor can change lettering, so validate the actual saved text.
            for line in p.get('narration','').splitlines():
                content=line.split(':',1)[-1]
                if words(content)>25:raise ValueError('A lettering balloon exceeds 25 words.')
                total+=words(content)
        if total>100:raise ValueError(f'Page {n} lettering exceeds 100 words.')
    return data


def plan_book(c,folder,generate,log,save_json):
    spec=request_spec(c)
    checkpoint=folder/'book_plan.json'
    state=json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else {'request':c['prompt'],'spec':spec,'outline':[]}
    if state['request']!=c['prompt']:raise ValueError('This checkpoint belongs to another request. Create a new project.')
    state.setdefault('seed',random.SystemRandom().randrange(2**31))
    save_json(checkpoint,state)
    def ask(label,instruction,tokens,validator,schema=None):
        feedback=''
        for attempt in range(3):
            log(label+f' (attempt {attempt+1}/3)')
            prompt=('You are completing ONE structured subtask for a comic production program. '
                    'Return ONLY a valid JSON object matching the requested structure. Do not answer any other subtask, '
                    'do not add Markdown, and do not replace requested characters, title or story premise. '
                    'The full reader request below is reference material; its output-order instructions apply to the final book, not this subtask.\n'
                    '<reader_request>\n'+c['prompt']+'\n</reader_request>\nCURRENT SUBTASK:\n'+instruction+feedback)
            raw=generate(prompt,tokens,attempt>0,schema=schema)
            (folder/(re.sub(r'[^a-z0-9]+','-',label.lower()).strip('-')+f'-attempt-{attempt+1}.txt')).write_text(raw,encoding='utf-8')
            try:return validator(json_answer(raw))
            except (ValueError,KeyError,TypeError) as ex:feedback='\nThe previous attempt failed validation: '+str(ex)+'. Correct that error.'
        raise RuntimeError(label+' failed validation after three attempts. Saved checkpoints are retained; no unrelated fallback story was substituted.')
    if 'bible' not in state:
        machine_story='machine' in c['prompt'].lower() and 'future' in c['prompt'].lower()
        rule_keys=['mechanism','storage','cost','release_protocol','limitations','early_clues'] if machine_story else ['world_rules','limitations','early_clues','resolution_setup']
        rule_example={key:'specific consistent story facts' for key in rule_keys}
        hero_notes=('Use the canonical red-and-yellow S shield on Superman, blue suit, red cape and boots. '
                    'Clark Kent and Superman are one person. Clark’s original reporting and Lois’s uncovered evidence must both be essential to the resolution. '
                    if 'Superman' in spec['anchors'] else 'Preserve the requested cast and recognizable identities. ')
        mechanism_notes=('Use measurable forces and engineering controls. The release protocol must name an isolated destination, a mechanical release control and a rated capacity. '
                         'Explain exactly where deferred danger is stored and how people can resolve it without undoing rescues. '
                         'Stored forces could be released in measured batches into evacuated, isolated infrastructure; invent a coherent protocol of your own. '
                         'Resolve the physical risk through those established controls. ' if machine_story else
                         'Establish the world’s rules, limitations and resolution clues before the climax. Preserve the reader’s genre and premise. ')
        def check_bible(x):
            for key in ['synopsis']:
                if not isinstance(x.get(key),str) or not x[key].strip():raise ValueError('Missing '+key)
            if isinstance(x.get('rules'),dict):
                protocol=x['rules'].get('release_protocol','').lower()
                if re.search(r'\b(fear|fears|empathy|emotion|emotional|belief|courage|breath)\b',protocol):
                    raise ValueError('The release protocol must physically handle stored danger, not turn danger into feelings.')
                x['rules']='\n'.join(f'{k}: {v}' for k,v in x['rules'].items())
            if not isinstance(x.get('rules'),str) or not x['rules'].strip():raise ValueError('Missing physical machine rules.')
            if not isinstance(x.get('characters'),dict) or not x['characters']:raise ValueError('Characters must be an object mapping names to appearance descriptions.')
            canonical={
                'Superman':'Superman (Clark Kent): adult man with black hair and blue eyes; blue suit, red cape and boots, yellow belt, familiar red-and-yellow S shield.',
                'Clark Kent':'Clark Kent: the same man as Superman, wearing glasses, a charcoal business suit, white shirt and blue tie while reporting for the Daily Planet.',
                'Lois Lane':'Lois Lane: adult woman with dark shoulder-length hair, navy jacket, cream blouse and charcoal trousers; notebook and phone for her investigation.'}
            cast={name:description for name,description in x['characters'].items() if isinstance(description,str)}
            for name in spec['anchors']:
                if name in canonical:cast[name]=canonical[name]
            x['characters']='\n'.join(f'{name}: {description}' for name,description in cast.items())
            for name in spec['anchors']:
                if name.lower() not in x['characters'].lower():raise ValueError('Missing requested character: '+name)
            if spec['title']:x['title']=spec['title']
            elif not x.get('title'):raise ValueError('A title is required.')
            return x
        state['bible']=ask('Planning synopsis, cast and machine rules',
            'Return {"title":"...","synopsis":"one paragraph including the intended ending",'
            '"characters":{"character full name":"brief costume and appearance description; include every principal character"},'
            '"rules":'+json.dumps(rule_example)+'}. '+hero_notes+mechanism_notes+
            'Respect the reader’s supplied title and all requested character roles.',1800,check_bible,
            {'type':'object','properties':{'title':{'type':'string'},'synopsis':{'type':'string'},'characters':{'type':'object','additionalProperties':{'type':'string'}},
              'rules':{'type':'object','properties':{k:{'type':'string'} for k in rule_keys},'required':rule_keys,'additionalProperties':False}},'required':['title','synopsis','characters','rules'],'additionalProperties':False})
        save_json(checkpoint,state)
        if (__import__('runtime_paths').DATA_HOME/'stop-after-current.flag').exists():
            log(f'PLANNING_PAUSED:{folder}');return None
    bible=state['bible']
    while len(state['outline'])<spec['pages']:
        start=len(state['outline'])+1;end=min(start+4,spec['pages'])
        def check_outline(x):
            entries=x.get('outline',[])
            if [p.get('number') for p in entries]!=list(range(start,end+1)):raise ValueError('Outline page numbers are missing or wrong.')
            if any(not isinstance(p.get('beat'),str) or not p['beat'].strip() for p in entries):raise ValueError('Every page needs a concrete plot beat.')
            return entries
        entries=ask(f'Outlining pages {start}-{end}',
            f'Return {{"outline":[{{"number":{start},"beat":"events, character choice, clue or rule established, and page-turn hook"}}]}} '
            f'for exactly pages {start} through {end}, of {spec["pages"]}. Each entry has ONLY number and beat; beat is one concise sentence, at most 60 words. No other fields. Follow the reader’s specified page ranges and pivotal revelations. '
            'Keep the ending satisfying and the logic consistent.\nSTORY BIBLE: '+json.dumps(bible,ensure_ascii=False)+
            '\nOUTLINE SO FAR: '+json.dumps(state['outline'],ensure_ascii=False),1200,check_outline,
            {'type':'object','properties':{'outline':{'type':'array','minItems':end-start+1,'maxItems':end-start+1,'items':{'type':'object','properties':{'number':{'type':'integer','enum':list(range(start,end+1))},'beat':{'type':'string'}},'required':['number','beat'],'additionalProperties':False}}},'required':['outline'],'additionalProperties':False})
        state['outline'].extend(entries);save_json(checkpoint,state)
        if (__import__('runtime_paths').DATA_HOME/'stop-after-current.flag').exists():
            log(f'PLANNING_PAUSED:{folder}');return None
    scripts=folder/'script_pages';scripts.mkdir(exist_ok=True)
    pages=[]
    def draft_data():
        panels=[]
        for page in pages:
            warnings=page_warnings(page,bible)
            for p in page['panels']:
                panels.append({'page':page['number'],'panel':p['number'],'scene':p['visual'],'dialogue':p['dialogue'],
                               'sfx':p.get('sfx',''),'narration':lettering(p),'needs_review':bool(warnings),'scene_check':' '.join(warnings)})
        return {'format':'comic-book-v1','title':bible['title'],'synopsis':bible['synopsis'],'characters':bible['characters'],
                'visual_continuity':bible['rules'],'outline':state['outline'],'book_spec':spec,'panels':panels,
                'seed':state.get('seed',17381),'request_prompt':c['prompt']}
    for n in range(1,spec['pages']+1):
        limit=int(c.get('_plan_page_limit',0))
        if limit and n>limit:
            log(f'PLANNING_PAUSED:{folder}')
            return None
        path=scripts/f'page_{n:02}.json'
        if path.exists():page=validate_page(json.loads(path.read_text(encoding='utf-8')),n,spec['panels_per_page'])
        else:
            earlier=pages[-1]['continuity'] if pages else 'Opening page. Establish the emotional stake and rescue geography.'
            instruction=(f'Write ONLY page {n} of {spec["pages"]}, with exactly {spec["panels_per_page"]} panels. '
                'Return {"number":'+str(n)+',"panels":[{"visual":"one drawable moment: characters, expression, action, setting, camera and lighting",'
                '"dialogue":[{"speaker":"name or CAPTION","text":"exact balloon text"}],"sfx":"only if useful, otherwise empty string"}],'
                '"continuity":"end-of-page location, time, costumes, injuries, evidence and what each principal character knows"}. '
                'Each balloon must be at most 25 words; all balloons together at most 100 words per page. Silent panels use dialogue: []. '
                'Do not put multiple sequential actions in one image. Follow the page outline, geography and established rules. '
                'No new powers, arbitrary sacrifice, or unexplained fixes. Use visual breathing room, warmth and clear speaker labels.\n'
                'BIBLE: '+json.dumps(bible,ensure_ascii=False)+'\nCOMPLETE OUTLINE: '+json.dumps(state['outline'],ensure_ascii=False)+
                '\nPREVIOUS CONTINUITY: '+earlier)
            page=ask(f'Writing page {n} of {spec["pages"]}',instruction,2400,lambda x:validate_page(x,n,spec['panels_per_page']),
                {'type':'object','properties':{'number':{'type':'integer','enum':[n]},'panels':{'type':'array','minItems':spec['panels_per_page'],'maxItems':spec['panels_per_page'],'items':{'type':'object','properties':{'visual':{'type':'string'},'dialogue':{'type':'array','maxItems':5,'items':{'type':'object','properties':{'speaker':{'type':'string'},'text':{'type':'string'}},'required':['speaker','text'],'additionalProperties':False}},'sfx':{'type':'string'}},'required':['visual','dialogue','sfx'],'additionalProperties':False}},'continuity':{'type':'string'}},'required':['number','panels','continuity'],'additionalProperties':False})
            save_json(path,page)
        pages.append(page)
        write_script(draft_data(),folder)
        log(f'Saved page {n}/{spec["pages"]}. It will not be regenerated on resume.')
        if (__import__('runtime_paths').DATA_HOME/'stop-after-current.flag').exists() and n<spec['pages']:
            log(f'PLANNING_PAUSED:{folder}')
            return None
    data=draft_data()
    validate_book(data);save_json(folder/'story.json',data);write_script(data,folder)
    return data


def write_script(data,folder):
    lines=['# '+data['title'],'','## Synopsis','',data['synopsis'],'','## Character and costume reference','',data['characters'],
           '','## Machine rules and continuity','',data['visual_continuity'],'','## Page outline','']
    lines += [f'{x["number"]}. {x["beat"]}' for x in data['outline']]
    lines += ['','## Complete panel-by-panel script','']
    letters=['# Exact lettering — '+data['title'],'']
    completed=max((p['page'] for p in data['panels']),default=0)
    for n in range(1,completed+1):
        lines += [f'### Page {n}',''];letters += [f'## Page {n}','']
        for p in [p for p in data['panels'] if p['page']==n]:
            text=p.get('narration','').strip()
            lines += [f'**Panel {p["panel"]}**','',f'**Visual:** {p["scene"]}','',
                      '**Dialogue/captions:**\n'+(text or '(Silent.)'),'',f'**Sound effects:** {p.get("sfx") or "None."}','']
            letters += [f'Panel {p["panel"]}:',text or '(Silent.)',f'SFX: {p["sfx"]}' if p.get('sfx') else '','']
    if completed<data['book_spec']['pages']:lines += [f'**Next page: {completed+1}. Planning is incomplete; resume this project to continue.**','']
    (folder/'SCRIPT.md').write_text('\n'.join(lines),encoding='utf-8')
    (folder/'LETTERING.md').write_text('\n'.join(letters),encoding='utf-8')
    (folder/'story.txt').write_text('\n'.join(lines),encoding='utf-8')


def render_book(c,data,folder,illustrations,cards,log,save_json):
    from PIL import Image
    validate_book(data);write_script(data,folder)
    log(f'Rendering {data["book_spec"]["pages"]} separate comic pages. Existing pages are reused.')
    for n in range(1,data['book_spec']['pages']+1):
        target=folder/'pages'/f'page_{n:02}';target.mkdir(parents=True,exist_ok=True)
        page=copy.deepcopy(data);page['panels']=[p for p in data['panels'] if p['page']==n]
        page['title']=f'{data["title"]} — Page {n}'
        # Keep a common reference between page renders while each page is saved separately.
        for name in ['character_reference.png','reference_source.json']:
            if (folder/name).exists() and not (target/name).exists():shutil.copy2(folder/name,target/name)
        log(f'Drawing page {n}/{data["book_spec"]["pages"]}...')
        illustrations(c,page,target)
        from art_quality import pending_reviews
        if pending_reviews(c,page,target):
            from project import archive_files
            archive_files(target,[target/'comic.png'])
            archive_files(folder,[folder/'comic-book.pdf',folder/f'page_{n:02}.png',folder/'complete.json'])
            log(f'Page {n} needs anatomy review before the book can continue.')
            log(f'STORYBOARD_READY:{folder}')
            return False
        for name in ['character_reference.png','reference_source.json']:
            if (target/name).exists() and not (folder/name).exists():shutil.copy2(target/name,folder/name)
        cards(page,target,int(c.get('output_width',1024)))
        shutil.copy2(target/'comic.png',folder/f'page_{n:02}.png')
        save_json(folder/'render_progress.json',{'completed_pages':n,'total_pages':data['book_spec']['pages']})
        stop=__import__('runtime_paths').DATA_HOME/'stop-after-current.flag'
        if stop.exists() and n<data['book_spec']['pages']:
            log('Stopped after the current page. Resume this project to continue.');return False
    # A real multi-page PDF, never one giant image containing the whole book.
    images=[]
    try:
        for n in range(1,data['book_spec']['pages']+1):
            with Image.open(folder/f'page_{n:02}.png') as im:images.append(im.convert('RGB'))
        images[0].save(folder/'comic-book.pdf',save_all=True,append_images=images[1:],resolution=150)
    finally:
        for im in images:im.close()
    return True
