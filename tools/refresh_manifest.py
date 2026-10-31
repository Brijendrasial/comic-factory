"""Maintainer tool: lock upstream revisions, file sizes and SHA-256 hashes."""
import hashlib,json,os,sys,time,urllib.request,urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('HF_HOME',str(ROOT/'build/hf-cache'))
from huggingface_hub import HfApi

def get(url):
    request=urllib.request.Request(url,headers={'User-Agent':'ComicFactory-Manifest/0.1'})
    with urllib.request.urlopen(request,timeout=60) as response:return response.read()

def github_asset(repo,tag,name):
    release=json.loads(get(f'https://api.github.com/repos/{repo}/releases/tags/{tag}'))
    asset=next(a for a in release['assets'] if a['name']==name)
    digest=asset.get('digest','')
    if not digest.startswith('sha256:'):raise ValueError('Upstream release has no published SHA-256: '+name)
    return {'url':asset['browser_download_url'],'sha256':digest.split(':',1)[1],'size':asset['size']}

def main():
    result={'format':1,'models':[]}
    result['python']=github_asset('astral-sh/python-build-standalone','20261026','cpython-3.12.16+20261026-x86_64-pc-windows-msvc-install_only.tar.gz')
    result['ollama']=github_asset('ollama/ollama','v0.40.13','ollama-windows-amd64.zip')
    selected=[('Story writer','unsloth/Qwen3-4B-Instruct-2507-bnb-4bit','f12db89cd5156e090618dded9b4367f23f8f3b33','writer_v2'),
        ('Comic artwork','hlhc/FLUX.2-klein-4B-bnb-4bit','199c1411ab9dc4111e9fe7e8e3dc3fc4e63c2648','klein'),
        ('Expressive voices','Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice','0c0e3051f131929182e2c023b9537f8b1c68adfe','emotional_voice')]
    api=HfApi()
    for name,repo,revision,folder in selected:
        print('Locking',name,repo,flush=True);info=api.model_info(repo,revision=revision,files_metadata=True)
        model={'name':name,'repo':repo,'revision':info.sha,'license':getattr(info.card_data,'license',None),'marker':f'local_models/{folder}/download_manifest.json','files':[]}
        for item in info.siblings:
            relative=item.rfilename
            if relative.startswith('.') or relative.endswith(('.py','.png','.jpg','.mp4','.gif')) or 'SMOKE' in relative:continue
            url=f'https://huggingface.co/{repo}/resolve/{info.sha}/'+urllib.parse.quote(relative,safe='/')
            if item.lfs:
                digest=item.lfs.sha256;size=item.size
            else:
                data=get(url+'?download=true');digest=hashlib.sha256(data).hexdigest();size=len(data)
            model['files'].append({'path':f'local_models/{folder}/{relative}','relative':relative,'url':url,'size':size,'sha256':digest})
        result['models'].append(model)
    tag='4b-instruct-q4_K_M';url=f'https://registry.ollama.ai/v2/library/qwen3-vl/manifests/{tag}'
    manifest=get(url);data=json.loads(manifest)
    reviewer={'name':'Artwork reviewer','repo':'ollama/qwen3-vl','revision':hashlib.sha256(manifest).hexdigest(),'license':'Apache-2.0','files':[]}
    # Keep the pinned registry manifest in the source package; the model layers
    # themselves download directly from the original registry with their hashes.
    (ROOT/'reviewer-manifest.json').write_bytes(manifest)
    for layer in [data['config']]+data['layers']:
        digest=layer['digest'];reviewer['files'].append({'path':'local_models/vision_models/blobs/'+digest.replace(':','-'),
            'url':'https://registry.ollama.ai/v2/library/qwen3-vl/blobs/'+digest,'size':layer['size'],'sha256':digest.split(':')[1]})
    result['models'].append(reviewer)
    result['reviewer_manifest_path']=f'local_models/vision_models/manifests/registry.ollama.ai/library/qwen3-vl/{tag}'
    result['download_bytes']=sum(a['size'] for m in result['models'] for a in m['files'])+result['python']['size']+result['ollama']['size']
    (ROOT/'model-manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('Locked download size (excluding Python packages):',round(result['download_bytes']/1024**3,2),'GiB',flush=True)
if __name__=='__main__':main()
