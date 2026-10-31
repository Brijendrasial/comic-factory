"""Preserve explicitly supplied comic scripts without asking a model to rewrite them."""
import re,secrets

def parse_script(c):
    prompt=c.get('prompt','')
    matches=list(re.finditer(r'(?im)^PANEL\s+(\d+)\s*(?:[—–-]\s*(.*))?$',prompt))
    if not matches:return None
    if len(matches)!=int(c['panels']):raise ValueError('The scripted panel count differs from Panels per comic.')
    header=prompt[:matches[0].start()]
    title=re.search(r'(?im)^TITLE:\s*(.+)',header)
    cast_match=re.search(r'(?is)CHARACTER REFERENCES\s*\n(.*?)(?=\nSETTING\s*\n)',header)
    if not title or not cast_match:return None
    cast={}
    for line in cast_match[1].splitlines():
        m=re.match(r'^([\w ]{1,40}):\s*(.+)',line.strip())
        if m:cast[m[1].strip()]=m[2].strip()
    if not cast:raise ValueError('Give each character a separate Name: appearance line.')
    for name in cast:
        if name.lower()=='batman':
            cast[name]+=' Powerfully muscular adult superhero: broad shoulders, thick chest, strong arms and thighs. Only Batman wears the cowl, cape, bat emblem and utility belt.'
        elif not re.search(r'\b(superhero|superman|supergirl|wonder woman|spider.man)\b',name+' '+cast[name],re.I):
            cast[name]+=' Distinct civilian clothing belonging only to this character; bare visible face, no superhero cowl, no cape, no bat emblem or superhero armor.'
    setting=re.search(r'(?is)\nSETTING\s*\n(.*?)(?=\nFOLLOW THIS SCRIPT)',header)
    names=list(cast);panels=[]
    for i,m in enumerate(matches):
        if int(m[1])!=i+1:raise ValueError('Script panel numbers must be consecutive.')
        body=prompt[m.end():matches[i+1].start() if i+1<len(matches) else len(prompt)]
        body=re.split(r'(?im)^\s*(?:COMIC PAGE REQUIREMENTS|LETTERING|VIDEO REQUIREMENTS|OUTPUTS|VISUAL RULES)\s*$',body)[0]
        visual=re.search(r'(?ims)^Visual:\s*(.*?)(?=\n[\w ]{1,40}:|\Z)',body)
        if not visual:raise ValueError(f'Panel {i+1} needs a Visual: line.')
        dialogue=[]
        for line in body.splitlines():
            line_match=re.match(r'^([\w ]{1,40}):\s*(.+)',line.strip())
            if not line_match:continue
            speaker=next((n for n in names if n.lower()==line_match[1].lower()),None)
            if speaker:
                text=line_match[2].strip().strip('“”"')
                from acting import parse_delivery
                text,emotion=parse_delivery(text)
                text=text.strip('“”"')
                if len(text.split())>25:raise ValueError('Keep each dialogue balloon below 26 words.')
                entry={'speaker':speaker,'text':text}
                if emotion:entry['emotion']=emotion
                dialogue.append(entry)
        positions={n:{'x':.25 if j%2==0 else .75,'y':.46} for j,n in enumerate(names)}
        staging=' Screen positions: '+'; '.join(n+(' on the LEFT' if j%2==0 else ' on the RIGHT') for j,n in enumerate(names))+'. Keep faces below the top third; leave the top third uncluttered for later lettering.'
        panels.append({'scene':visual[1].strip()+staging,'dialogue':dialogue,
            'narration':' '.join(d['text'] for d in dialogue) or ' ',
            'speaker_positions':positions,'scene_check':'Explicit user script preserved.','needs_review':False})
    return {'title':title[1].strip(),'characters':'\n'.join(n+': '+v for n,v in cast.items()),
        'character_profiles':cast,'panels':panels,'seed':secrets.randbelow(2**31),
        'request_prompt':prompt,'visual_continuity':setting[1].strip() if setting else '',
        'script_source':'explicit-user-script-v1','storyboard_reviewed':False}
