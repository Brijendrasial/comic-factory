"""Plan a short request as a structured, drawable, voiced comic script."""
import copy,json,re
EMOTIONS=['calm','angry','fearful','urgent','reassuring','relieved','sad','happy','warm']

def normalize_identities(draft,request):
    """Resolve established aliases only when the described costume agrees."""
    draft=copy.deepcopy(draft);changes=[];characters=draft.get('characters',[])
    aliases={}
    known={'Superman':('clark kent','kal-el','kal el'),'Batman':('bruce wayne',)}
    for hero,alternate_names in known.items():
        if not re.search(r'\b'+hero+r'\b',request,re.I):continue
        if any(c.get('name','').strip().casefold()==hero.casefold() for c in characters):continue
        for character in characters:
            name=character.get('name','').strip();appearance=character.get('appearance','').casefold()
            costume=(hero.casefold() in appearance or ('cape' in appearance and ('blue' in appearance if hero=='Superman' else ('cowl' in appearance or 'bat' in appearance))))
            if name.casefold() in alternate_names and costume:
                aliases[name]=hero;character['name']=hero;changes.append(name+' -> '+hero)
    # A generic speaker label can refer to the only child already in the cast.
    children=[c['name'] for c in characters if c.get('age_group')=='child']
    if len(children)==1 and not any(c.get('name','').casefold()=='child' for c in characters):aliases['Child']=children[0]
    for panel in draft.get('panels',[]):
        for line in panel.get('dialogue',[]):
            for old,new in aliases.items():
                if line.get('speaker','').strip().casefold()==old.casefold():line['speaker']=new;break
        for old,new in aliases.items():
            if isinstance(panel.get('visual'),str):panel['visual']=re.sub(r'\b'+re.escape(old)+r'\b',new,panel['visual'],flags=re.I)
    return draft,changes

def schema(count):
    line={'type':'object','properties':{'speaker':{'type':'string','minLength':1,'maxLength':30},'text':{'type':'string','minLength':1,'maxLength':120},'emotion':{'type':'string','enum':EMOTIONS}},'required':['speaker','text','emotion']}
    character={'type':'object','properties':{'name':{'type':'string','minLength':1,'maxLength':30},'gender':{'type':'string','enum':['male','female']},'age_group':{'type':'string','enum':['adult','child']},'appearance':{'type':'string','minLength':10,'maxLength':200}},'required':['name','gender','age_group','appearance']}
    panel={'type':'object','properties':{'visual':{'type':'string','minLength':25,'maxLength':330},'dialogue':{'type':'array','minItems':0,'maxItems':2,'items':line}},'required':['visual','dialogue']}
    return {'type':'object','x-ordered':True,'properties':{'title':{'type':'string','minLength':1,'maxLength':80},'setting':{'type':'string','minLength':10,'maxLength':200},
        'characters':{'type':'array','minItems':1,'maxItems':3,'items':character},
        'panels':{'type':'array','minItems':count,'maxItems':count,'items':panel}},'required':['title','setting','characters','panels']}

def validate(draft,count,request):
    if not isinstance(draft.get('title'),str) or not draft['title'].strip():raise ValueError('A title is required.')
    characters=draft.get('characters',[])
    if not 1<=len(characters)<=3:raise ValueError('Use one to three characters.')
    names=[x['name'].strip() for x in characters]
    for character in characters:
        if character.get('gender') not in ('male','female') or not character.get('appearance','').strip():raise ValueError('Each character needs an appearance and voice casting.')
        if any(x in character['appearance'].lower() for x in ('cannot generate','cannot create','not available in this environment')):raise ValueError('Character descriptions must describe people, not rendering capabilities.')
        if not character['name'].strip():raise ValueError('Each character needs a name or an unambiguous role label.')
    if len(set(n.casefold() for n in names))!=len(names):raise ValueError('Character names must be distinct.')
    for name in ('Superman','Batman'):
        if re.search(r'\b'+name+r'\b',request,re.I) and name.casefold() not in [n.casefold() for n in names]:raise ValueError('Preserve the requested hero '+name+'.')
    if len(draft.get('panels',[]))!=count:raise ValueError('Incorrect panel count.')
    words=0
    for panel in draft['panels']:
        if not isinstance(panel.get('visual'),str) or len(panel['visual'].split())<6:raise ValueError('Every panel needs a concrete visual description.')
        if len(panel['visual'].split())>60:raise ValueError('Keep each visual description below 61 words and show one moment.')
        if re.search(r'(?i)then (?:a )?(?:wide|close.up|medium)|camera cuts',panel['visual']):raise ValueError('Use one camera view per panel, without a cut to another image.')
        if not 0<=len(panel.get('dialogue',[]))<=2:raise ValueError('Use at most two spoken lines per panel.')
        for line in panel['dialogue']:
            name=next((n for n in names if n.casefold()==line['speaker'].casefold()),None)
            if name is None:raise ValueError('Dialogue speaker is missing from the character list.')
            line['speaker']=name
            if not 1<=len(line['text'].split())<=20:raise ValueError('Each balloon must contain 1–20 words.')
            if line.get('emotion') not in EMOTIONS:raise ValueError('Invalid acting emotion.')
            words+=len(line['text'].split())
    if words>100:raise ValueError('Keep the page below 101 spoken words.')
    if not any(p['dialogue'] for p in draft['panels']):raise ValueError('The requested voiced comic needs character dialogue.')
    for hero in ('Superman','Batman'):
        if re.search(r'\b'+hero+r'\b',request,re.I) and not any(line['speaker'].casefold()==hero.casefold() for p in draft['panels'] for line in p['dialogue']):raise ValueError('Give the main hero '+hero+' at least one spoken line.')
    return draft

def plan(c,folder,generate,log,save_json,seed,cached_only=False):
    count=int(c['panels']);request=c.get('prompt','');feedback=''
    cached=[]
    settings_path=folder/'settings.json'
    if settings_path.exists():
        saved=json.loads(settings_path.read_text(encoding='utf-8'))
        if saved.get('prompt','')==request and int(saved.get('panels',count))==count:
            paths=sorted(folder.glob('structured_story_attempt_*.json'),key=lambda p:int(p.stem.rsplit('_',1)[1]),reverse=True)
            cached=[(p,p.read_text(encoding='utf-8')) for p in paths]
    first_new=max([int(p.stem.rsplit('_',1)[1]) for p,_ in cached],default=0)+1
    for attempt in range(len(cached)+(0 if cached_only else 3)):
        prompt=('You are the SCRIPT WRITER inside a working local comic/video renderer. Write only the JSON screenplay requested by the schema. '
            'The renderer, not you, draws images, adds speech balloons and synthesizes voices. Do not refuse or discuss rendering capabilities. '
            f'Write exactly {count} sequential panels for ONE complete original comic page. '
            'Keep the requested named heroes and give the main hero at least one spoken line. Use recognizable costumes and established abilities. '
            'Use at most THREE named characters. Give every person a proper name (not Child, Woman or Villain), age_group, and male/female voice casting. Appearance describes fixed clothing, face and build ONLY; no actions, voices or emotions. Include a second speaking character when different voices are requested. '
            'Keep the setting and costume details stable. Use only characters needed in each illustration. '
            'Give each panel one drawable action in at most 45 words, with clear foreground positions and ONE camera view. Big action must be visible: a rescue, impact or obstacle, not just standing and talking. '
            'For four panels: establish immediate danger, escalate the action, show the decisive rescue/action, then show a clear resolved outcome. '
            'Do not end with an unexplained threat, cliffhanger or a promise of action later unless requested. '
            'Give each panel 0–2 short spoken lines, each at most 20 words; below 100 words across the page. '
            'Dialogue is spoken by named characters, not narration. Each line has an emotion from the schema. '
            'Keep text OUT of the visual description: the renderer adds dialogue later. Leave open space near heads for balloons. '
            'Do not introduce a new power or unexplained machine to solve the climax. Readers age 12+, no graphic injuries. '
            'Return only JSON.\nREADER REQUEST:\n'+request+'\nFIXED CAST IF PROVIDED:\n'+c.get('characters','')+
            '\nPREVIOUS STRUCTURAL ERRORS TO CORRECT:\n'+feedback)
        if attempt<len(cached):
            path,raw=cached[attempt];log('Checking the saved draft with corrected identity rules: '+path.name)
        else:
            number=attempt-len(cached)
            log(f'Planning the action, character dialogue and emotions (attempt {number+1}/3)...')
            raw=generate(prompt,500+count*300,True,schema=schema(count))
            (folder/f'structured_story_attempt_{first_new+number}.json').write_text(raw,encoding='utf-8')
        try:
            draft,changes=normalize_identities(json.loads(raw),request)
            draft=validate(draft,count,request)
        except (ValueError,TypeError,KeyError) as exc:
            feedback=str(exc);log('Correcting the structured script: '+feedback);continue
        if changes:log('Recognized the requested superhero identity: '+', '.join(changes))
        profiles={}
        for character in draft['characters']:
            name=character['name'].strip();description=character.get('age_group','adult').capitalize()+' '+character['gender']+'. '+character['appearance'].strip()
            if name.casefold()=='superman':description+=' Powerful muscular physique, broad shoulders and strong arms. Blue suit, red cape and boots, red-and-yellow S shield; this costume belongs only to Superman.'
            profiles[name]=description
        names=list(profiles);panels=[]
        for panel in draft['panels']:
            involved=[n for n in names if re.search(r'\b'+re.escape(n)+r'\b',panel['visual'],re.I) or any(d['speaker']==n for d in panel['dialogue'])]
            if not involved:involved=names
            positions={name:{'x':(i+1)/(len(involved)+1),'y':.4} for i,name in enumerate(involved)}
            staging=' Screen positions: '+'; '.join(name+(' on the LEFT' if i==0 else ' on the RIGHT' if i==len(involved)-1 else ' in the CENTER') for i,name in enumerate(involved))+'. Leave clear space around faces for later lettering.'
            panels.append({'scene':panel['visual']+staging,'dialogue':panel['dialogue'],
                'narration':' '.join(x['text'] for x in panel['dialogue']) or 'Silent panel.',
                'speaker_positions':positions,'scene_check':'Structured comic script; inspect action and continuity in storyboard.','needs_review':False})
        data={'title':draft['title'],'characters':'\n'.join(name+': '+description for name,description in profiles.items()),'character_profiles':profiles,
            'panels':panels,'seed':seed,'request_prompt':request,'visual_continuity':draft['setting'],
            'script_source':'generated-dialogue-v1','storyboard_reviewed':False,'identity_normalizations':changes}
        save_json(folder/'story.json',data)
        (folder/'story.txt').write_text(data['title']+'\n\n'+'\n\n'.join('\n'.join(x['speaker']+': ['+x['emotion']+'] '+x['text'] for x in p['dialogue']) for p in panels),encoding='utf-8')
        log('Structured storyboard saved with exact character dialogue and emotion cues.')
        return data
    if cached_only:return None
    raise RuntimeError('The local writer could not validate its comic script. Drafts were saved; '+feedback)
