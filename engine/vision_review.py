"""Offline image reviewer using the existing portable Ollama runtime."""
import argparse,base64,io,json,os,subprocess,time,urllib.request
from pathlib import Path
from PIL import Image,ImageOps
from runtime_paths import DATA_HOME, CODE_HOME, ensure_data
ROOT=ensure_data()
DEFAULT_RUNTIME=DATA_HOME/'runtime'/'ollama'/'ollama.exe'
MODEL='qwen3-vl:4b-instruct-q4_K_M'


class LocalReviewer:
    def __init__(self,c=None):
        self.c=c or {};self.model=self.c.get('anatomy_model',MODEL)
        if ':cloud' in self.model:raise ValueError('The anatomy reviewer must use a local model.')
        self.base='http://127.0.0.1:11439';self.server=None;self.log=None
    def request(self,path,data=None,timeout=600,stream=False):
        req=urllib.request.Request(self.base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        response=urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=timeout)
        if stream:return response
        with response as r:
            raw=r.read();return json.loads(raw) if raw else {}
    def __enter__(self):
        runtime=Path(self.c.get('anatomy_runtime',str(DEFAULT_RUNTIME)))
        if not runtime.exists():raise RuntimeError('The local image-review runtime is missing.')
        models=ROOT/'local_models'/'vision_models';models.mkdir(parents=True,exist_ok=True)
        profile=ROOT/'local_models'/'vision_profile';profile.mkdir(exist_ok=True)
        env=dict(os.environ,OLLAMA_HOST='127.0.0.1:11439',OLLAMA_MODELS=str(models),OLLAMA_NO_CLOUD='1',
                 OLLAMA_KEEP_ALIVE='0',OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1',OLLAMA_CONTEXT_LENGTH='4096',USERPROFILE=str(profile))
        self.log=open(ROOT/'vision-server.log','a',encoding='utf-8')
        self.server=subprocess.Popen([str(runtime),'serve'],env=env,stdout=self.log,stderr=self.log,creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(90):
            if self.server.poll() is not None:
                self.close();raise RuntimeError('Image-review service could not start. See vision-server.log.')
            try:self.request('/api/version',timeout=2);return self
            except Exception:time.sleep(1)
        self.close();raise RuntimeError('Image-review service startup timed out.')
    def close(self):
        if self.server is not None and self.server.poll() is None:
            subprocess.run(['taskkill','/PID',str(self.server.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            if self.server.poll() is None:self.server.terminate()
            try:self.server.wait(timeout=10)
            except subprocess.TimeoutExpired:self.server.kill();self.server.wait(timeout=10)
        if self.log is not None:self.log.close()
    def __exit__(self,*_):self.close()
    def installed(self):
        return any(m['name']==self.model for m in self.request('/api/tags')['models'])
    def chat_json(self,payload):
        # Retry truncated review text without redrawing the existing artwork.
        for budget in (1200,2200):
            payload['options']=dict(payload.get('options',{}),num_predict=budget)
            response=self.request('/api/chat',payload,timeout=600)
            try:return json.loads(response['message']['content'])
            except json.JSONDecodeError:
                if budget==2200:raise ValueError('The visual review remained incomplete after two attempts.')
                print('Visual reviewer: completing an interrupted response; keeping the existing drawing...',flush=True)
    def install(self):
        last=-10
        with self.request('/api/pull',{'model':self.model,'stream':True},timeout=1800,stream=True) as response:
            for line in response:
                if not line.strip():continue
                item=json.loads(line)
                if item.get('error'):raise RuntimeError(item['error'])
                if item.get('total'):
                    percent=int(item.get('completed',0)*100/item['total'])
                    if percent>=last+10:print(f'Downloading local image reviewer: {percent}%',flush=True);last=percent
                else:print(item.get('status','Installing...'),flush=True)
    def lower_body_check(self,image):
        crop=image.crop((0,int(image.height*.45),image.width,image.height))
        crop.thumbnail((768,512));buffer=io.BytesIO();crop.save(buffer,format='PNG')
        schema={'type':'object','properties':{'figures':{'type':'array','items':{'type':'object','properties':{
            'description':{'type':'string'},'visible_legs':{'type':'integer','minimum':0,'maximum':8},
            'visible_feet':{'type':'integer','minimum':0,'maximum':8},'foot_locations':{'type':'array','items':{'type':'string'}},
            'uncertain':{'type':'boolean'}},'required':['description','visible_legs','visible_feet','foot_locations','uncertain']}}},'required':['figures']}
        return self.chat_json({'model':self.model,'messages':[{'role':'user','content':
            'This is an intentional lower-body crop of a comic. Count each foreground HUMAN separately. '
            'Trace every visible leg from its thigh through knee and ankle to its shoe or boot. '
            'List the location of EACH distinct visible foot individually, including extra or duplicated feet. '
            'A dangling shoe between two other boots is still a foot: do not ignore it to make the anatomy normal. '
            'Do not count reflections, detached equipment or background people. Cropped heads and arms are intentional. '
            'Give literal counts even when a person has more than two legs or feet; do not normalize the count. '
            'Use uncertain=true if ownership of a foot cannot be established. Do not assume a hidden limb is missing.',
            'images':[base64.b64encode(buffer.getvalue()).decode()]}],
            'format':schema,'stream':False,'think':False,'keep_alive':'1m','options':{'temperature':0,'num_ctx':4096}})

    def review(self,path,scene,characters=''):
        if not self.installed():raise RuntimeError('The local image-review model is not installed. Run vision_review.py --install first.')
        with Image.open(path) as original:
            image=ImageOps.exif_transpose(original).convert('RGB');image.thumbnail((896,896))
            buffer=io.BytesIO();image.save(buffer,format='PNG')
        observation_prompt=('Look ONLY at the image, without guessing the intended story. First count every visible human and robot, including small and background figures. '
                'Describe at most four foreground figures, each in at most 45 words; summarize background crowds together. Include each figure clothing colors, headgear, capes, visible muscular build, arms, hands, legs and feet. '
                'Do not guess that an occluded or cropped limb is missing. Record only directly visible major defects: disconnected limbs, impossible joints, fused bodies or extra limbs. '
                'A normal kneeling, flying or foreshortened pose is not a defect by itself. For each foreground face, estimate its mouth center as normalized x,y coordinates from 0 to 1 measured from the image top left. Give concise literal observations, not a verdict about the story.')
        prompt=('Compare literal visual observations against the requested scene. '
                'Inspect for OBVIOUS major anatomy or body-structure defects. '
                'Report missing arms or legs that should be visible, disconnected limbs, fused bodies, extra limbs or impossible joints. '
                'A limb outside the camera crop, behind the torso, behind an object, or naturally occluded is NOT automatically missing. '
                'Close-up portraits do not need visible legs. Respect intentional injuries and nonhuman character designs described in the scene. '
                'Do not demand visible hands or feet when the requested framing excludes them. Do not invent defects you cannot see. '
                'verdict=pass when no clear major defect is visible; retry for a clear correctable defect; review when evidence is genuinely ambiguous. '
                'Also flag a clearly unintended duplicate person or visibly merged people. Do not judge story writing or lettering. '
                'Give short factual issues and a positive, concrete correction that preserves the requested action. Match the observed mouth coordinates to the named characters in speaker_positions; do not invent coordinates not in the observations. '
                'SCENE: '+scene+'\nCHARACTERS: '+characters[:2500])
        schema={'type':'object','properties':{'verdict':{'type':'string','enum':['pass','retry','review']},
                'issues':{'type':'array','items':{'type':'string'}},'correction':{'type':'string'},
                'speaker_positions':{'type':'array','items':{'type':'object','properties':{'speaker':{'type':'string'},'x':{'type':'number','minimum':0,'maximum':1},'y':{'type':'number','minimum':0,'maximum':1}},'required':['speaker','x','y']}}},'required':['verdict','issues','correction','speaker_positions']}
        if characters.startswith('COSTUME_REVIEW_REQUIRED:'):
            prompt+='\nAlso compare the observed outfits and visible build with each named profile. Retry a clearly wrong costume, a civilian wearing a superhero cape or cowl, or a slender figure when a muscular superhero is explicitly required. Do not claim to see an emblem or detail absent from the literal observations. When clothing identity cannot be determined, use review.'
        try:
            print('Visual reviewer: inspecting the figures actually visible in the image...',flush=True)
            observation_schema={'type':'object','properties':{'humans':{'type':'integer'},'robots':{'type':'integer'},
                'figures':{'type':'array','items':{'type':'string'}},'visible_defects':{'type':'array','items':{'type':'string'}},
                'mouths':{'type':'array','items':{'type':'object','properties':{'description':{'type':'string'},'x':{'type':'number','minimum':0,'maximum':1},'y':{'type':'number','minimum':0,'maximum':1}},'required':['description','x','y']}}},'required':['humans','robots','figures','visible_defects','mouths']}
            observations=self.chat_json({'model':self.model,'messages':[{'role':'user','content':observation_prompt,'images':[base64.b64encode(buffer.getvalue()).decode()]}],
                'format':observation_schema,'stream':False,'think':False,'keep_alive':'1m','options':{'temperature':0,'num_ctx':4096}})
            print('Visual reviewer: checking those observations against the requested pose and framing...',flush=True)
            answer=self.chat_json({'model':self.model,'messages':[{'role':'user','content':prompt+'\nLITERAL IMAGE OBSERVATIONS:\n'+json.dumps(observations)}],
                'format':schema,'stream':False,'think':False,'keep_alive':0,'options':{'temperature':0,'num_ctx':4096}})
            if answer.get('verdict') not in ('pass','retry','review') or not isinstance(answer.get('issues'),list):raise ValueError('Invalid visual-review response.')
            if answer['verdict']=='pass' and answer['issues']:answer['verdict']='review'
            if answer['verdict']=='retry' and not answer['issues']:answer['verdict']='review'
            if answer['verdict']=='pass' and characters.startswith('COSTUME_REVIEW_REQUIRED:'):
                print('Visual reviewer: separately tracing legs and counting individual feet...',flush=True)
                details=self.lower_body_check(image)
                answer['lower_body_check']=details
                for figure in details.get('figures',[]):
                    if figure.get('visible_legs',0)>2 or figure.get('visible_feet',0)>2:
                        answer['verdict']='retry'
                        answer['issues'].append('Extra leg or foot: '+figure.get('description','foreground figure'))
                        answer['correction']='Each human has one coherent body, exactly two legs and two feet. Show separated, uncrossed legs and clearly connected ankles. Remove any duplicated shoe between the two feet.'
                    elif figure.get('uncertain') and answer['verdict']=='pass':
                        answer['verdict']='review';answer['issues'].append('Foot ownership is unclear: '+figure.get('description','foreground figure'))
            answer['observations']=observations
            return answer
        finally:
            self.request('/api/generate',{'model':self.model,'keep_alive':0},timeout=60)
            for _ in range(30):
                if not self.request('/api/ps')['models']:break
                time.sleep(.5)
            else:raise RuntimeError('The image reviewer did not release graphics memory. Generation paused to avoid memory pressure.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--install',action='store_true');p.add_argument('--image');p.add_argument('--scene',default='A comic illustration of a human character.')
    args=p.parse_args()
    with LocalReviewer() as reviewer:
        if args.install:reviewer.install()
        if args.image:print(json.dumps(reviewer.review(args.image,args.scene),indent=2),flush=True)
        else:print('Reviewer installed: '+str(reviewer.installed()),flush=True)
