"""Separate process keeps speech-model memory and dependencies outside the artist."""
import json,os,sys,time
from pathlib import Path
from runtime_paths import DATA_HOME
root=DATA_HOME
os.environ.setdefault('HF_HUB_OFFLINE','1');os.environ.setdefault('TRANSFORMERS_OFFLINE','1')
os.environ.setdefault('NUMBA_CACHE_DIR',str(root/'runtime-tmp'/'numba'))
import torch,numpy as np,soundfile as sf
from qwen_tts import Qwen3TTSModel

def main():
    plan=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    print('Loading the local emotional voice model...',flush=True)
    model=Qwen3TTSModel.from_pretrained(plan['model_path'],device_map='cuda:0',dtype=torch.bfloat16,attn_implementation='sdpa',local_files_only=True)
    supported=set(model.get_supported_speakers())
    for i,line in enumerate(plan['lines']):
        path=Path(line['path'])
        if path.exists():continue
        if line['speaker'].lower() not in {x.lower() for x in supported}:raise ValueError('Unsupported speaker: '+line['speaker'])
        print(f"Acting line {i+1}/{len(plan['lines'])}: {line['character']} — {line['emotion']}",flush=True)
        torch.manual_seed((int(plan['seed'])+i*307)%(2**31));started=time.time()
        wavs,sr=model.generate_custom_voice(text=line['text'],language='English',speaker=line['speaker'],instruct=line['instruct'],
            max_new_tokens=700,do_sample=True,temperature=.7,top_p=.9,repetition_penalty=1.08)
        audio=np.asarray(wavs[0],dtype=np.float32).reshape(-1)
        if len(audio)<sr*.15 or not np.isfinite(audio).all():raise RuntimeError('Invalid or empty dialogue audio.')
        active=np.flatnonzero(np.abs(audio)>.003)
        if len(active):audio=audio[max(0,active[0]-int(sr*.08)):min(len(audio),active[-1]+int(sr*.2))]
        if len(audio)/sr>max(12,len(line['text'].split())*1.5):raise RuntimeError('The voice continued beyond the expected line. Retry this line.')
        peak=float(np.max(np.abs(audio)))
        if peak>.95:audio*=.95/peak
        path.parent.mkdir(parents=True,exist_ok=True);pending=path.with_suffix('.pending.wav')
        sf.write(pending,audio,sr,subtype='PCM_16');pending.replace(path)
        print(f"Saved acted line ({len(audio)/sr:.1f}s audio, {time.time()-started:.1f}s processing).",flush=True)
    print('Acted dialogue complete; releasing graphics memory.',flush=True)
if __name__=='__main__':main()
