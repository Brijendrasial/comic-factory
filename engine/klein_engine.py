"""Local reference-image editing backend, with scene-first natural-language prompts."""
from pathlib import Path
import hashlib
import json
import re
from PIL import Image,ImageOps

def continuity_for_scene(notes,scene):
    aliases={'train':['train','locomotive','engine'],'station':['station','platform'],
             'boy':['boy','child'],'girl':['girl','child']}
    selected=[]
    words=set(re.findall(r'[a-z]+',scene.lower()))
    for clause in re.split(r'[;\n]+',notes):
        clause=clause.strip()
        if not clause: continue
        if ':' in clause:
            key=clause.split(':',1)[0].strip().lower()
            names=aliases.get(key,[key])
            if any(re.search(r'\b'+re.escape(name)+r's?\b',scene,re.I) for name in names):
                selected.append(clause)
        else:
            # Legacy free-form notes are applied by sentence rather than copied
            # wholesale, to reduce unrelated characters and objects leaking in.
            for sentence in re.split(r'(?<=[.!?])\s+',clause):
                meaningful=set(re.findall(r'[a-z]+',sentence.lower()))-{
                    'the','a','an','same','has','have','is','are','with','and','of','on','in','if','visible','modern'}
                if words & meaningful: selected.append(sentence)
    return ' '.join(selected)

def generate_illustrations(c,data,folder):
    import torch
    from diffusers import Flux2KleinPipeline,Flux2Transformer2DModel,AutoencoderKLFlux2,FlowMatchEulerDiscreteScheduler
    from transformers import AutoTokenizer,AutoModelForCausalLM
    from project import archive_files
    from art_quality import QualityGate,pending_reviews,framing_instruction,scoped_appearance,primary_appearance
    from runtime_paths import DATA_HOME
    root=DATA_HOME
    source=root/'local_models'/'klein'
    if not (source/'download_manifest.json').exists():
        raise RuntimeError('The reference-editing model has not finished downloading.')
    previous=json.loads((folder/'art_settings.json').read_text()) if (folder/'art_settings.json').exists() else {}
    reference_path=folder/'character_reference.png'
    external=c.get('reference_image','').strip()
    ref_source={'characters':data['characters'],'external':external,
                'mtime':Path(external).stat().st_mtime_ns if external else None}
    info_path=folder/'reference_source.json'
    old_source=json.loads(info_path.read_text()) if info_path.exists() else None
    if old_source and any(old_source.get(k)!=v for k,v in ref_source.items()):
        archive_files(folder,list(folder.glob('character_reference*.png')))
    if external and not reference_path.exists():
        with Image.open(external) as image:
            ImageOps.exif_transpose(image).convert('RGB').save(reference_path)
    size=int(c.get('image_size',1024))
    steps=int(c.get('klein_steps',4))
    def signature():
        values={'engine':'flux2-klein-4bit','version':4,'size':size,'steps':steps,
                'characters':data['characters'],'style':c['style'],
                'visual_continuity':data.get('visual_continuity',''),
                'reference_sha256':hashlib.sha256(reference_path.read_bytes()).hexdigest() if reference_path.exists() else None}
        return hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()
    fingerprint=signature()
    stale=[]
    if previous.get('fingerprint')!=fingerprint:
        stale.extend(folder.glob('art_*.png'))
    else:
        for i,panel in enumerate(data['panels'],1):
            old=next((p for p in previous.get('panels',[]) if p['panel']==i),{})
            if old.get('scene')!=panel['scene'] or old.get('seed')!=panel.get('seed',data['seed']+i):
                stale.append(folder/f'art_{i:02}.png')
    if stale:
        stale.extend(folder/n for n in ['comic.png','comic.mp4','complete.json'])
        archive_files(folder,list(dict.fromkeys(stale)))
    if previous.get('fingerprint')==fingerprint and all((folder/f'art_{i:02}.png').exists() for i in range(1,len(data['panels'])+1)) and not pending_reviews(c,data,folder):
        print('Using existing reference-edited artwork.',flush=True)
        return
    print('Loading the local reference-editing model...',flush=True)
    tokenizer=AutoTokenizer.from_pretrained(str(source/'tokenizer'),use_fast=True,local_files_only=True)
    # Load components explicitly: this quantized checkpoint's model index names
    # the slow tokenizer although only its fast-tokenizer JSON was exported.
    text_encoder=AutoModelForCausalLM.from_pretrained(str(source/'text_encoder'),dtype=torch.bfloat16,local_files_only=True)
    transformer=Flux2Transformer2DModel.from_pretrained(str(source/'transformer'),torch_dtype=torch.bfloat16,local_files_only=True)
    vae=AutoencoderKLFlux2.from_pretrained(str(source/'vae'),torch_dtype=torch.bfloat16,local_files_only=True)
    scheduler=FlowMatchEulerDiscreteScheduler.from_pretrained(str(source/'scheduler'),local_files_only=True)
    pipe=Flux2KleinPipeline(tokenizer=tokenizer,text_encoder=text_encoder,transformer=transformer,
        vae=vae,scheduler=scheduler,is_distilled=True)
    pipe.enable_model_cpu_offload()
    pipe.vae.enable_tiling()
    try:
        if not reference_path.exists():
            print('Drawing a character identity guide...',flush=True)
            text=(('One solo full-body character reference, strong readable silhouette, muscular anatomy when specified, on a neutral background. ' if data.get('character_profiles') else 'A tightly cropped head-and-shoulders character portrait on a neutral background. ')
                  +primary_appearance(data['characters'])+'. '+c['style']+'. Exactly one character, face and upper chest only. No lettering.')
            if data.get('character_profiles'):text=text.replace('face and upper chest only','entire head, shoulders, torso, arms, hands, legs and boots visible')
            guide=pipe(prompt=text,width=size,height=size,num_inference_steps=steps,guidance_scale=1.0,
                generator=torch.Generator('cpu').manual_seed(data['seed'])).images[0]
            guide.save(reference_path)
        info_path.write_text(json.dumps(ref_source,indent=2),encoding='utf-8')
        fingerprint=signature()
        metadata={'engine':'FLUX.2 Klein 4B NF4','fingerprint':fingerprint,'image_size':size,
            'steps':steps,'shared_reference':str(reference_path),
            'panels':[{'panel':i,'seed':p.get('seed',data['seed']+i),'scene':p['scene']}
                      for i,p in enumerate(data['panels'],1)]}
        (folder/'art_settings.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        reference=Image.open(reference_path).convert('RGB')
        profiles=data.get('character_profiles',{})
        references={}
        for number,(name,appearance) in enumerate(profiles.items()):
            path=reference_path if number==0 else folder/f'character_reference_{number+1:02}.png'
            if not path.exists():
                print('Drawing a separate costume reference for '+name+'...',flush=True)
                portrait=pipe(prompt='Exactly one solo character, full-body, neutral background. '+name+': '+appearance+'. '+c['style']+'. No other characters. No writing or speech balloons.',
                    width=768,height=768,num_inference_steps=steps,guidance_scale=1.0,
                    generator=torch.Generator('cpu').manual_seed(data['seed']+number*503)).images[0]
                portrait.save(path)
            with Image.open(path) as portrait:references[name]=ImageOps.contain(portrait.convert('RGB'),(512,512))
        def before_review():
            pipe.maybe_free_model_hooks()
            import gc
            gc.collect();torch.cuda.empty_cache()
        with QualityGate(c,data,folder) as gate:
            for i,panel in enumerate(data['panels'],1):
                notes=continuity_for_scene(data.get('visual_continuity',''),panel['scene'])
                text=('One comic-book illustration. Use the reference as an identity guide, not a pose to copy. '
                    +'Only the characters needed here: '+scoped_appearance(data['characters'],panel)+'\n'+c['style']+'. '
                    +framing_instruction(panel['scene'])+' No lettering or panel divisions. '
                    'Replace the reference pose and background. Only include the people requested in this scene, without duplicates. '
                    'Keep applicable visual details: '+notes+'\n'
                    'Draw this exact action and composition: '+panel['scene'])
                scene_references=[(name,img) for name,img in references.items() if re.search(r'\b'+re.escape(name)+r'\b',panel['scene'],re.I)]
                if scene_references:
                    text+='\nEach reference shows a DIFFERENT person: '+'; '.join(f'image {j+1} is {name}' for j,(name,_) in enumerate(scene_references))+'. Keep each reference costume on its own named character. Never copy Batman armor, cape, cowl or emblem onto a civilian. Plain clean artwork only, absolutely no words, symbols resembling letters, speech balloons or captions.'
                # Whole-image reference editing can transfer a superhero cape
                # onto every person. For multi-person scripted scenes, use the
                # full named profiles with text-to-image instead of blending
                # their costume references. Solo scenes retain identity editing.
                multi_person=len(scene_references)>1
                if multi_person:
                    text=('One clean cinematic comic illustration, no writing, no balloons. '+c['style']+'. '
                        'SEPARATE CHARACTER DESIGNS: '+'\n'.join(name+': '+profiles[name] for name,_ in scene_references)
                        +'\nEvery costume belongs only to its named wearer. Keep superhero capes, armor and masks strictly separate from civilian clothes. '
                        +'SETTING: '+data.get('visual_continuity','')+'\n'+framing_instruction(panel['scene'])
                        +'\nEXACT SCENE: '+panel['scene'])
                def draw(seed,correction):
                    prompt=text+('\nAnatomy correction for this retry: '+correction if correction else '')
                    print(f'Editing character into scene {i}/{len(data["panels"])}...',flush=True)
                    return pipe(image=None if multi_person else ([img for _,img in scene_references] if scene_references else reference),prompt=prompt,width=size,height=size,num_inference_steps=steps,
                        guidance_scale=1.0,generator=torch.Generator('cpu').manual_seed(seed)).images[0]
                gate.draw(i,panel,draw,before_review)
    finally:
        del pipe
        import gc
        gc.collect()
        try:torch.cuda.empty_cache()
        except RuntimeError:pass
