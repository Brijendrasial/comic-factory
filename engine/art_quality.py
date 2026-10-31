"""Bounded local visual review, preserved candidates, and explicit review holds."""
import hashlib,json,re,shutil,time
from pathlib import Path


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def framing_instruction(scene):
    text=scene.lower()
    close=any(x in text for x in ['close-up','close up','portrait','head and shoulders','upper body','waist-up','waist up'])
    if close:return 'Respect the requested camera crop. Visible hands and limbs must connect naturally to the body; limbs outside the crop need not be shown.'
    full=any(re.search(r'\b'+word+r'\b',text) for word in ['wide','full-body','full body','standing','walking','running','flying','kneel','kneeling','jumping'])
    if full:return 'Keep the specified bodies inside the frame with breathing room around heads and feet. Show coherent complete silhouettes, naturally connected arms and legs, hands attached to forearms, and feet attached to legs. Preserve natural occlusion and the requested pose.'
    return 'Use coherent proportions and naturally connected limbs. Keep the active hands and the requested interaction clearly readable. Preserve the requested camera framing.'


def scoped_appearance(characters,panel):
    context=panel['scene']+' '+' '.join(x.get('speaker','') for x in panel.get('dialogue',[]))
    clauses=[x.strip() for x in re.split(r'\n+|(?<=[.!?])\s+',characters) if x.strip()]
    selected=[]
    for clause in clauses:
        if 'not a character' in clause.lower():continue
        name=re.split(r'\s+is\s+|:',clause,maxsplit=1)[0].strip()
        names=[name]
        parts=re.findall(r'[A-Za-z]+',name)
        if 1<len(parts)<=4:names.extend(p for p in [parts[0],parts[-1]] if p.lower() not in ('dr','mr','ms','mrs'))
        if len(name.split())<=5 and any(re.search(r'\b'+re.escape(n)+r'\b',context,re.I) for n in names):selected.append(clause)
    return ' '.join(selected) if selected else characters


def primary_appearance(characters):
    clauses=[x.strip() for x in re.split(r'\n+|(?<=[.!?])\s+',characters) if x.strip() and 'not a character' not in x.lower()]
    return next((x for x in clauses if x.lower().startswith('superman')),clauses[0] if clauses else characters)


def read_quality(folder):
    path=Path(folder)/'anatomy_reviews.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version':1,'panels':{}}


def write_quality(folder,data):
    path=Path(folder)/'anatomy_reviews.json';tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)


def approved(panel,path):return path.exists() and panel.get('art_approved_sha256')==digest(path)


def pending_reviews(c,data,folder):
    if not c.get('anatomy_check',True):return []
    report=read_quality(folder);pending=[]
    for i,panel in enumerate(data['panels'],1):
        path=Path(folder)/f'art_{i:02}.png';entry=report['panels'].get(str(i),{})
        if approved(panel,path):continue
        if not path.exists() or entry.get('sha256')!=digest(path) or entry.get('verdict')!='pass' or entry.get('reviewer')!=c.get('anatomy_model','qwen3-vl:4b-instruct-q4_K_M'):
            pending.append({'panel':i,'issues':entry.get('issues') or ['This drawing has not passed visual review.']})
    return pending


class QualityGate:
    def __init__(self,c,data,folder):
        self.c=c;self.data=data;self.folder=Path(folder);self.report=read_quality(folder);self.reviewer=None
        self.enabled=c.get('anatomy_check',True)
    def __enter__(self):return self
    def __exit__(self,*_):
        if self.reviewer is not None:self.reviewer.close()
    def review(self,path,panel,before_review):
        try:
            before_review()
            if self.reviewer is None:
                from vision_review import LocalReviewer
                self.reviewer=LocalReviewer(self.c).__enter__()
            appearances=scoped_appearance(self.data['characters'],panel)
            if self.data.get('character_profiles'):
                appearances='COSTUME_REVIEW_REQUIRED:\n'+'\n'.join(name+': '+desc for name,desc in self.data['character_profiles'].items() if re.search(r'\b'+re.escape(name)+r'\b',panel['scene'],re.I))
            return self.reviewer.review(path,panel['scene'],appearances)
        except Exception as ex:
            return {'verdict':'review','issues':['Visual reviewer unavailable: '+str(ex)],'correction':''}
    def draw(self,index,panel,draw,before_review=lambda:None):
        path=self.folder/f'art_{index:02}.png';key=str(index)
        if not self.enabled:
            if not path.exists():draw(panel.get('seed',self.data['seed']+index),'').save(path)
            return
        if approved(panel,path):return
        old=self.report['panels'].get(key,{})
        if path.exists() and old.get('sha256')==digest(path) and old.get('verdict')=='pass' and old.get('reviewer')==self.c.get('anatomy_model','qwen3-vl:4b-instruct-q4_K_M'):return
        candidates=self.folder/'quality_candidates';candidates.mkdir(exist_ok=True)
        base=panel.get('seed',self.data['seed']+index);correction='';attempts=[]
        maximum=1+max(0,min(3,int(self.c.get('anatomy_retries',2))))
        run=str(time.time_ns())
        for attempt in range(maximum):
            seed=(base+attempt*1009)%(2**31)
            candidate=candidates/f'panel-{index:02}-{run}-attempt-{attempt+1}.png'
            if attempt==0 and path.exists():shutil.copy2(path,candidate)
            else:
                print(f'Drawing panel {index}: anatomy attempt {attempt+1}/{maximum}...',flush=True)
                draw(seed,correction).save(candidate)
            print(f'Checking visible anatomy in panel {index}...',flush=True)
            result=self.review(candidate,panel,before_review)
            attempts.append(dict(result,seed=seed,candidate=str(candidate.relative_to(self.folder))))
            self.report['panels'][key]={'verdict':result['verdict'],'issues':result['issues'],'attempts':attempts,
                'sha256':digest(candidate),'chosen_seed':seed,'reviewer':self.c.get('anatomy_model','qwen3-vl:4b-instruct-q4_K_M')}
            write_quality(self.folder,self.report)
            if result['verdict']=='pass':
                positions={entry['speaker']:{'x':entry['x'],'y':entry['y']} for entry in result.get('speaker_positions',[]) if entry.get('speaker') in self.data.get('character_profiles',{}) and isinstance(entry.get('x'),(int,float)) and isinstance(entry.get('y'),(int,float)) and 0<=entry['x']<=1 and 0<=entry['y']<=1}
                if positions:panel.setdefault('speaker_positions',{}).update(positions)
                shutil.copy2(candidate,path);print(f'Panel {index} passed the local visual check.',flush=True);return
            if result['verdict']=='review':break
            correction=result.get('correction','')[:1000]
            print('Retrying only this panel: '+'; '.join(result['issues']),flush=True)
        # Save a preview for the editor, but prevent automatic page/video assembly.
        shutil.copy2(candidate,path)
        self.report['panels'][key]['verdict']='review'
        write_quality(self.folder,self.report)
        print(f'Panel {index} needs visual review; candidates were retained.',flush=True)
