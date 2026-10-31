import copy
import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox
from tkinter.scrolledtext import ScrolledText

def open_editor(parent,folder,render_callback):
    from project import update_storyboard
    from art_quality import read_quality,digest
    folder=Path(folder).resolve()
    original=json.loads((folder/'story.json').read_text(encoding='utf-8'))
    settings=json.loads((__import__('runtime_paths').DATA_HOME/'config.json').read_text(encoding='utf-8'))
    classic=settings.get('image_engine')!='klein'
    win=tk.Toplevel(parent)
    win.title('Review characters and scenes | '+original['title'])
    win.geometry('950x820')
    controls=ttk.Frame(win,padding=12)
    controls.pack(side='bottom',fill='x')
    ttk.Label(controls,text='Edits are saved locally. Replaced artwork and videos are preserved in history/.').pack(anchor='w')
    actions=ttk.Frame(controls)
    actions.pack(fill='x',pady=6)
    canvas=tk.Canvas(win,highlightthickness=0)
    scroll=ttk.Scrollbar(win,orient='vertical',command=canvas.yview)
    scroll.pack(side='right',fill='y')
    canvas.pack(side='left',fill='both',expand=True)
    canvas.configure(yscrollcommand=scroll.set)
    body=ttk.Frame(canvas,padding=18)
    if (folder/'lettering_review.json').exists():
        lettering_issue=json.loads((folder/'lettering_review.json').read_text(encoding='utf-8')).get('issue','Adjust the speech balloons.')
        ttk.Label(body,text='Speech balloons: '+lettering_issue,wraplength=850).pack(anchor='w',pady=8)
    item=canvas.create_window((0,0),window=body,anchor='nw')
    body.bind('<Configure>',lambda _:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',lambda event:canvas.itemconfigure(item,width=event.width))
    ttk.Label(body,text='Title').pack(anchor='w')
    title=tk.StringVar(value=original['title'])
    ttk.Entry(body,textvariable=title).pack(fill='x',pady=(2,10))
    ttk.Label(body,text='Fixed character appearance — names, faces, costume colors').pack(anchor='w')
    cast=ScrolledText(body,height=3,wrap='word',font=('Segoe UI',11))
    cast.pack(fill='x',pady=(2,12)); cast.insert('1.0',original['characters'])
    ttk.Label(body,text='Recurring objects and locations — colors, materials and fixed story facts').pack(anchor='w')
    ttk.Label(body,text='Use Name: description entries, separated by new lines or semicolons. Example: Train: silver passenger train.',wraplength=850).pack(anchor='w')
    continuity=ScrolledText(body,height=3,wrap='word',font=('Segoe UI',11))
    continuity.pack(fill='x',pady=(2,12)); continuity.insert('1.0',original.get('visual_continuity',''))
    fields=[]
    win._preview_images=[]
    for i,panel in enumerate(original['panels'],1):
        ttk.Separator(body).pack(fill='x',pady=10)
        label=f'PAGE {panel["page"]} · PANEL {panel["panel"]}' if 'page' in panel else f'PANEL {i}'
        ttk.Label(body,text=label,font=('Segoe UI',13,'bold')).pack(anchor='w')
        if panel.get('needs_review'):
            ttk.Label(body,text='Please review: '+panel.get('scene_check','Scene consistency was uncertain.'),wraplength=850).pack(anchor='w',pady=4)
        art_folder=folder/'pages'/f'page_{panel["page"]:02}' if 'page' in panel else folder
        art_index=panel['panel'] if 'page' in panel else i
        artwork=art_folder/f'art_{art_index:02}.png'
        report=read_quality(art_folder)['panels'].get(str(art_index),{})
        accept=None
        mouth_positions=copy.deepcopy(panel.get('speaker_positions',{}))
        if report and report.get('verdict')!='pass':
            ttk.Label(body,text='Visual check: '+'; '.join(report.get('issues',[])),wraplength=850).pack(anchor='w',pady=4)
            accept=tk.BooleanVar(value=artwork.exists() and panel.get('art_approved_sha256')==digest(artwork))
            ttk.Checkbutton(body,text='I inspected this drawing and accept its anatomy',variable=accept).pack(anchor='w',pady=3)
        if artwork.exists():
            from PIL import Image,ImageTk
            with Image.open(artwork) as source:
                preview=source.copy(); preview.thumbnail((220,220))
            photo=ImageTk.PhotoImage(preview,master=win)
            win._preview_images.append(photo)
            image_label=ttk.Label(body,image=photo);image_label.pack(anchor='w',pady=4)
            if original.get('character_profiles'):
                selected_speaker=tk.StringVar(value=next(iter(original['character_profiles'])))
                ttk.Label(body,text='Adjust a balloon tail: choose its speaker, then click their mouth in the preview.').pack(anchor='w')
                ttk.Combobox(body,state='readonly',textvariable=selected_speaker,values=list(original['character_profiles'])).pack(anchor='w')
                def place_mouth(event,positions=mouth_positions,speaker=selected_speaker,w=preview.width,h=preview.height):
                    positions[speaker.get()]={'x':min(1,max(0,event.x/w)),'y':min(1,max(0,event.y/h))}
                image_label.bind('<Button-1>',place_mouth)
            ttk.Button(body,text='View full-size artwork',command=lambda path=artwork:os.startfile(path)).pack(anchor='w',pady=(0,6))
        ttk.Label(body,text='What should appear — one action, location and camera view').pack(anchor='w')
        scene=ScrolledText(body,height=3,wrap='word',font=('Segoe UI',11))
        scene.pack(fill='x',pady=(2,6)); scene.insert('1.0',panel['scene'])
        scripted=bool(original.get('character_profiles')) and any(p.get('dialogue') for p in original['panels'])
        ttk.Label(body,text='Dialogue — Speaker: [angry / worried / relieved / calm] text. Leave the brackets out for automatic delivery.' if scripted else 'Narration / visible caption — shorter text is easier to read').pack(anchor='w')
        narration=ScrolledText(body,height=3,wrap='word',font=('Segoe UI',11))
        narration.pack(fill='x',pady=(2,6)); narration.insert('1.0','\n'.join(d['speaker']+': '+('['+d['emotion']+'] ' if d.get('emotion') else '')+d['text'] for d in panel.get('dialogue',[])) if scripted else panel['narration'])
        mode=tk.StringVar(value={0.15:'Prioritize action',0.3:'Balance',0.55:'Prioritize likeness'}.get(panel.get('reference_strength'),'Automatic'))
        if classic:
            ttk.Label(body,text='Character guide for this panel').pack(anchor='w')
            ttk.Combobox(body,state='readonly',textvariable=mode,
                values=['Automatic','Prioritize action','Balance','Prioritize likeness']).pack(fill='x',pady=(2,8))
        fields.append((scene,narration,mode,accept,artwork,mouth_positions))
    def save(reroll=None,render=False):
        data=copy.deepcopy(original)
        data['title']=title.get().strip()
        data['characters']=cast.get('1.0','end-1c').strip()
        if data.get('character_profiles'):
            data['character_profiles']={line.split(':',1)[0].strip():line.split(':',1)[1].strip() for line in data['characters'].splitlines() if ':' in line}
        data['visual_continuity']=continuity.get('1.0','end-1c').strip()
        data['storyboard_reviewed']=True
        for panel,(scene,narration,mode,accept,artwork,mouth_positions) in zip(data['panels'],fields):
            if mouth_positions:panel['speaker_positions']=mouth_positions
            panel['scene']=scene.get('1.0','end-1c').strip()
            panel['narration']=narration.get('1.0','end-1c').strip()
            if data.get('character_profiles') and any(p.get('dialogue') for p in original['panels']):
                panel['dialogue']=[{'speaker':line.split(':',1)[0].strip(),'text':line.split(':',1)[1].strip()} for line in panel['narration'].splitlines() if ':' in line and line.split(':',1)[1].strip()]
                from acting import parse_delivery
                for line in panel['dialogue']:
                    line['text'],emotion=parse_delivery(line['text'])
                    if emotion:line['emotion']=emotion
                panel['narration']=' '.join(d['text'] for d in panel['dialogue']) or 'Silent panel.'
            if accept is not None:
                if accept.get() and artwork.exists():panel['art_approved_sha256']=digest(artwork)
                else:panel.pop('art_approved_sha256',None)
            if classic:
                value={'Prioritize action':0.15,'Balance':0.3,'Prioritize likeness':0.55}.get(mode.get())
                if value is None:
                    panel.pop('reference_strength',None)
                else:
                    panel['reference_strength']=value
        try:
            update_storyboard(folder,data,reroll)
            original.clear(); original.update(copy.deepcopy(data))
        except Exception as exc:
            messagebox.showerror('Storyboard',str(exc),parent=win); return
        if render:
            render_callback(folder)
        else:
            messagebox.showinfo('Storyboard','Saved. Render this storyboard to update its comic and video.',parent=win)
    ttk.Button(actions,text='Save storyboard',command=save).pack(side='left',padx=3)
    ttk.Button(actions,text='Save and render',command=lambda:save(render=True)).pack(side='left',padx=3)
    ttk.Label(actions,text='Panel:').pack(side='left',padx=(12,2))
    selected=tk.IntVar(value=1)
    ttk.Spinbox(actions,from_=1,to=len(fields),textvariable=selected,width=3).pack(side='left')
    def regenerate():
        try:
            index=selected.get()
            if not 1<=index<=len(fields): raise ValueError('Choose a valid panel number.')
        except Exception as exc:
            messagebox.showerror('Panel',str(exc),parent=win); return
        save(index,True)
    ttk.Button(actions,text='Regenerate panel',command=regenerate).pack(side='left',padx=4)
    ttk.Button(actions,text='Regenerate all',command=lambda:save('all',True)).pack(side='left',padx=4)
    return win
