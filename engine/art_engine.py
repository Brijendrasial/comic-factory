"""Higher-resolution drawing with a shared visual character reference."""
from pathlib import Path
import json
import hashlib
from PIL import Image, ImageOps

NEGATIVE=('low quality, low resolution, deformed, distorted anatomy, extra limbs, extra fingers, '
    'missing arms, missing legs, disconnected limbs, disembodied hands, fused legs, '
    'duplicate person, fused bodies, tiled image, repeating pattern, texture sheet, contact sheet, '
    'speech bubbles, letters, text, watermark, collage, split screen, multiple panels')

def reference_influence(c,panel):
    base=float(c.get('reference_strength',0.3))
    if 'reference_strength' in panel:
        return float(panel['reference_strength'])
    interaction=any(word in panel['scene'].lower() for word in ['press','push','pull','brac','grip','lift'])
    return min(base,0.15) if interaction else base

def generate_illustrations(c,data,folder,prompt_builder):
    import torch
    from diffusers import StableDiffusionXLPipeline,DPMSolverMultistepScheduler
    from transformers import CLIPVisionModelWithProjection
    from runtime_paths import DATA_HOME
    root=DATA_HOME
    size=int(c.get('image_size',1024))
    steps=int(c.get('sdxl_steps',c.get('steps',36)))
    source=str(root/'local_models'/'artist') if (root/'local_models'/'artist'/'download_manifest.json').exists() else c.get('sdxl_model','stabilityai/stable-diffusion-xl-base-1.0')
    use_reference=c.get('consistent_characters',True)
    from project import archive_files
    from art_quality import QualityGate,pending_reviews,primary_appearance
    external=c.get('reference_image','').strip()
    external_stamp=Path(external).stat().st_mtime_ns if external else None
    signature={'size':size,'steps':steps,'style':c['style'],'characters':data['characters'],
        'reference':external,'reference_mtime':external_stamp,'strength':c.get('reference_strength',0.3),
        'enabled':use_reference,'guidance':c.get('guidance_scale',5.5),'engine_version':3}
    fingerprint=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
    previous=json.loads((folder/'art_settings.json').read_text()) if (folder/'art_settings.json').exists() else {}
    stale=[]
    if previous.get('fingerprint')!=fingerprint:
        stale.extend(folder.glob('art_*.png'))
        stale.extend(folder/name for name in ['comic.png','comic.mp4','complete.json'])
    else:
        for i,panel in enumerate(data['panels'],1):
            prior=next((x for x in previous.get('panels',[]) if x['panel']==i),{})
            if (prior.get('scene')!=panel['scene'] or prior.get('seed')!=panel.get('seed',data['seed']+i)
                or prior.get('reference_strength',c.get('reference_strength',0.3))!=reference_influence(c,panel)):
                stale.append(folder/f'art_{i:02}.png')
    ref_info_path=folder/'reference_source.json'
    ref_info={'characters':data['characters'],'external':external,'mtime':external_stamp,'portrait_version':2}
    old_ref=json.loads(ref_info_path.read_text()) if ref_info_path.exists() else None
    if old_ref is not None and old_ref!=ref_info:
        stale.append(folder/'character_reference.png')
        stale.extend(folder.glob('art_*.png'))
    archive_files(folder,list(dict.fromkeys(stale)))
    if previous.get('fingerprint')==fingerprint and all((folder/f'art_{i:02}.png').exists() for i in range(1,len(data['panels'])+1)) and not pending_reviews(c,data,folder):
        print('Using existing artwork with matching settings.',flush=True)
        return
    adapter=root/'local_models'/'reference'
    kwargs={}
    if use_reference:
        if not (adapter/'download_manifest.json').exists():
            raise RuntimeError('The character-reference model is not installed yet. Finish its setup before drawing.')
        kwargs['image_encoder']=CLIPVisionModelWithProjection.from_pretrained(
            str(adapter/'models'/'image_encoder'),torch_dtype=torch.float16,local_files_only=True)
    pipe=StableDiffusionXLPipeline.from_pretrained(source,torch_dtype=torch.float16,variant='fp16',use_safetensors=True,**kwargs)
    pipe.scheduler=DPMSolverMultistepScheduler.from_config(pipe.scheduler.config,
        algorithm_type='sde-dpmsolver++',use_karras_sigmas=True,euler_at_final=True)
    if use_reference:
        pipe.load_ip_adapter(str(adapter),subfolder='sdxl_models',
            weight_name='ip-adapter-plus_sdxl_vit-h.safetensors',image_encoder_folder=None,local_files_only=True)
    # Keep UNet's added reference layers below the laptop GPU's memory limit.
    # Whole-model offload can overflow 8 GB at 1024 px and trigger very slow
    # Windows shared-memory paging instead of raising a CUDA memory error.
    if torch.cuda.get_device_properties(0).total_memory < 10*1024**3:
        pipe.enable_sequential_cpu_offload()
    else:
        pipe.enable_model_cpu_offload()
    pipe.vae.enable_tiling()
    def trim(text,tokenizer,n=75):
        ids=tokenizer.encode(text,add_special_tokens=False,truncation=False)
        return tokenizer.decode(ids[:n],skip_special_tokens=True)
    def draw(prompt,prompt_2,seed,extra=None,reference_sheet=False):
        print('Preparing scene text...',flush=True)
        negative_text=NEGATIVE
        if not reference_sheet:
            negative_text+=', isolated character on plain white background, character reference sheet, posed studio portrait'
            if any(word in prompt.lower() for word in ['kneeling','bracing','pressing','walking','standing on']):
                negative_text+=', flying, airborne, floating'
        positive,negative,pooled,negative_pooled=pipe.encode_prompt(prompt=prompt,prompt_2=prompt_2,
            device=pipe._execution_device,num_images_per_prompt=1,do_classifier_free_guidance=True,negative_prompt=negative_text)
        # Cached image embeddings skip the image encoder during sampling. Explicitly
        # offload text encoders so they do not remain in the 8 GB GPU alongside UNet.
        pipe.maybe_free_model_hooks()
        print('Rendering the scene...',flush=True)
        return pipe(prompt_embeds=positive,negative_prompt_embeds=negative,
            pooled_prompt_embeds=pooled,negative_pooled_prompt_embeds=negative_pooled,
            width=size,height=size,original_size=(size,size),target_size=(size,size),
            num_inference_steps=steps,guidance_scale=float(c.get('guidance_scale',5.5)),
            generator=torch.Generator('cpu').manual_seed(seed),**(extra or {})).images[0]
    try:
        embeddings=None
        reference_path=folder/'character_reference.png'
        if use_reference:
            if external and not reference_path.exists():
                with Image.open(external) as original:
                    ImageOps.pad(ImageOps.exif_transpose(original).convert('RGB'),(1024,1024),color='white').save(reference_path)
            if not reference_path.exists():
                print('Drawing the shared character reference...',flush=True)
                pipe.set_ip_adapter_scale(0)
                blank=Image.new('RGB',(224,224),'white')
                prompt=trim(f"One character, head and shoulders portrait, face clearly visible, neutral background. {primary_appearance(data['characters'])}. {c['style']}",pipe.tokenizer)
                prompt2=trim(f"Close portrait of {primary_appearance(data['characters'])}. Front view, clear face, upper chest and shoulders only, comic illustration.",pipe.tokenizer_2)
                image=draw(prompt,prompt2,data['seed'],{'ip_adapter_image':blank},reference_sheet=True)
                image.save(reference_path)
            ref_info_path.write_text(json.dumps(ref_info,indent=2),encoding='utf-8')
            pipe.set_ip_adapter_scale(float(c.get('reference_strength',0.3)))
            reference=Image.open(reference_path).convert('RGB')
            print('Preparing the shared character appearance...',flush=True)
            embeddings=pipe.prepare_ip_adapter_image_embeds(reference,None,pipe._execution_device,1,True)
            pipe.maybe_free_model_hooks()
        metadata={'fingerprint':fingerprint,'image_size':size,'steps':steps,'scheduler':'DPM++ SDE Karras',
            'shared_reference':str(reference_path) if use_reference else None,
            'panels':[{'panel':i,'seed':panel.get('seed',data['seed']+i),'scene':panel['scene'],
                       'reference_strength':reference_influence(c,panel)}
                      for i,panel in enumerate(data['panels'],1)]}
        (folder/'art_settings.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        def before_review():
            pipe.maybe_free_model_hooks()
            import gc
            gc.collect();torch.cuda.empty_cache()
        with QualityGate(c,data,folder) as gate:
            for i,panel in enumerate(data['panels'],1):
                print(f'Drawing panel {i}/{len(data["panels"])} at {size} px...',flush=True)
                if use_reference:
                    pipe.set_ip_adapter_scale(reference_influence(c,panel))
                prompt,prompt2=prompt_builder(c,data,panel,pipe.tokenizer,pipe.tokenizer_2)
                extra={'ip_adapter_image_embeds':embeddings} if embeddings is not None else {}
                def render_candidate(seed,correction):
                    first=trim(('Natural connected anatomy, intact limbs. ' if correction else '')+prompt,pipe.tokenizer)
                    return draw(first,prompt2,seed,extra)
                gate.draw(i,panel,render_candidate,before_review)
        (folder/'art_settings.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    finally:
        del pipe
        import gc
        gc.collect()
        try:torch.cuda.empty_cache()
        except RuntimeError:pass
