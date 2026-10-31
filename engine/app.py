import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText
from runtime_paths import DATA_HOME, CODE_HOME, ensure_data, engine_python
ROOT = ensure_data()

def main():
    window = tk.Tk()
    window.title('Comic Factory | Windows beta')
    window.geometry('1000x900')
    window.minsize(820,700)
    window.configure(bg='#101828')
    style = ttk.Style()
    style.theme_use('clam')
    style.configure('TFrame', background='#101828')
    style.configure('TLabel', background='#101828', foreground='#e4e7ec',font=('Segoe UI',11))
    style.configure('TButton',font=('Segoe UI',11),padding=8)
    style.configure('TCheckbutton',background='#101828',foreground='#e4e7ec',font=('Segoe UI',11))
    outer=ttk.Frame(window,padding=18)
    outer.pack(fill='both',expand=True)
    bottom=ttk.Frame(outer)
    bottom.pack(side='bottom',fill='x')
    form=ttk.Frame(outer)
    form.pack(fill='both',expand=True)
    canvas=tk.Canvas(form,bg='#101828',highlightthickness=0)
    scroll=ttk.Scrollbar(form,orient='vertical',command=canvas.yview)
    scroll.pack(side='right',fill='y'); canvas.pack(side='left',fill='both',expand=True)
    canvas.configure(yscrollcommand=scroll.set)
    frame=ttk.Frame(canvas,padding=6)
    item=canvas.create_window((0,0),window=frame,anchor='nw')
    frame.bind('<Configure>',lambda _:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',lambda event:canvas.itemconfigure(item,width=event.width))
    def wheel(event):
        if not isinstance(event.widget,tk.Text):
            canvas.yview_scroll(-int(event.delta/120),'units')
    window.bind_all('<MouseWheel>',wheel,add='+')
    ttk.Label(frame,text='COMIC FACTORY',font=('Segoe UI',24,'bold')).pack(anchor='w')
    ttk.Label(frame,text='Stories, illustrations, local narration, subtitles and motion videos.').pack(anchor='w',pady=(4,18))
    cfg = json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
    ttk.Label(frame,text='Your comic prompt').pack(anchor='w',pady=(4,3))
    prompt_box=ScrolledText(frame,height=5,wrap='word',font=('Segoe UI',11),bg='#192539',fg='#e4e7ec',insertbackground='white')
    prompt_box.pack(fill='x')
    prompt_box.insert('1.0',cfg.get('prompt',''))
    ttk.Label(frame,text='Example: Superman saves a runaway train in Metropolis. End with a funny moment.').pack(anchor='w',pady=(4,0))
    ttk.Label(frame,text='Leave blank for automatic stories. You can name DC, Marvel, or your own characters.').pack(anchor='w')
    values={}
    request_label=tk.StringVar()
    def show_request(*_):
        from book import request_spec
        try:
            spec=request_spec(dict(cfg,prompt=prompt_box.get('1.0','end-1c'),panels=values['panels'].get() if 'panels' in values else cfg['panels']))
            request_label.set(f'Requested book: {spec["pages"]} pages, {spec["panels_per_page"]} panels per page. Pages are planned and saved individually.' if spec['pages']>1 else 'Short comic mode. Include a page count in your prompt to create a multi-page book.')
        except ValueError as exc:request_label.set(str(exc))
    ttk.Label(frame,textvariable=request_label,wraplength=900).pack(anchor='w',pady=5)
    prompt_box.bind('<KeyRelease>',show_request,add='+');show_request()
    for key,label in [('characters','Character appearance (optional; costumes, colors, faces)'),
                      ('continuity','Recurring details (optional; e.g. Train: silver passenger train; Station: stone pillars)'),
                      ('theme','Fallback theme (when prompt is blank)'),('style','Art style'),('comics_per_batch','Comics per batch'),('panels','Panels in a short comic / preferred panels per book page')]:
        ttk.Label(frame,text=label).pack(anchor='w',pady=(8,3))
        values[key]=tk.StringVar(value=str(cfg.get(key,'')))
        ttk.Entry(frame,textvariable=values[key]).pack(fill='x')
        if key=='panels':values[key].trace_add('write',show_request)
    ttk.Label(frame,text='Character reference image (optional; a clear head-and-shoulders portrait works best)').pack(anchor='w',pady=(12,3))
    reference=tk.StringVar(value=cfg.get('reference_image',''))
    refrow=ttk.Frame(frame); refrow.pack(fill='x')
    ttk.Entry(refrow,textvariable=reference).pack(side='left',fill='x',expand=True)
    def browse_reference():
        path=filedialog.askopenfilename(title='Choose a character reference',filetypes=[('Images','*.png *.jpg *.jpeg *.webp'),('All files','*.*')])
        if path: reference.set(path)
    ttk.Button(refrow,text='Browse image',command=browse_reference).pack(side='left',padx=(6,0))
    ttk.Label(frame,text='Blank: the generator draws and reuses a shared character reference.').pack(anchor='w',pady=4)
    strength=tk.DoubleVar(value=cfg.get('reference_strength',0.3))
    strength_label=tk.StringVar()
    def show_strength(*_): strength_label.set(f'Reference influence: {strength.get():.2f} — higher values can copy the reference pose')
    strength.trace_add('write',show_strength); show_strength()
    if cfg.get('image_engine')!='klein':
        ttk.Label(frame,textvariable=strength_label).pack(anchor='w',pady=(8,3))
        ttk.Scale(frame,from_=0.1,to=0.8,variable=strength).pack(fill='x')
    quality=tk.StringVar(value='Quality: 1024 px' if cfg.get('image_size',1024)==1024 else 'Fast: 768 px')
    ttk.Label(frame,text='Drawing quality').pack(anchor='w',pady=(8,3))
    ttk.Combobox(frame,state='readonly',textvariable=quality,values=['Quality: 1024 px','Fast: 768 px']).pack(fill='x')
    anatomy=tk.BooleanVar(value=cfg.get('anatomy_check',True))
    ttk.Checkbutton(frame,text='Check visible anatomy locally and retry defective panels',variable=anatomy).pack(anchor='w',pady=(8,3))
    ttk.Label(frame,text='Up to two retries per panel. Uncertain or repeatedly defective drawings are held for review.',wraplength=900).pack(anchor='w')
    ttk.Separator(frame).pack(fill='x',pady=14)
    ttk.Label(frame,text='Background music (video)',font=('Segoe UI',13,'bold')).pack(anchor='w')
    music_enabled=tk.BooleanVar(value=cfg.get('background_music',True))
    ttk.Checkbutton(frame,text='Add background music',variable=music_enabled).pack(anchor='w',pady=4)
    music_source=tk.StringVar(value='Local audio file' if cfg.get('music_mode')=='file' else 'Built-in instrumental')
    ttk.Combobox(frame,state='readonly',textvariable=music_source,values=['Built-in instrumental','Local audio file']).pack(fill='x',pady=4)
    ttk.Label(frame,text='Built-in mood').pack(anchor='w')
    music_mood=tk.StringVar(value=cfg.get('music_style','Heroic'))
    mood_picker=ttk.Combobox(frame,state='readonly',textvariable=music_mood,values=['Heroic','Calm','Mystery'])
    mood_picker.pack(fill='x',pady=4)
    music_path=tk.StringVar(value=cfg.get('music_file',''))
    music_row=ttk.Frame(frame); music_row.pack(fill='x',pady=4)
    music_entry=ttk.Entry(music_row,textvariable=music_path)
    music_entry.pack(side='left',fill='x',expand=True)
    def browse_music():
        path=filedialog.askopenfilename(title='Choose background music',filetypes=[('Audio','*.mp3 *.wav *.m4a *.ogg *.flac'),('All files','*.*')])
        if path: music_path.set(path)
    music_browse=ttk.Button(music_row,text='Browse music',command=browse_music)
    music_browse.pack(side='left',padx=(6,0))
    def music_source_changed(*_):
        local=music_source.get()=='Local audio file'
        mood_picker.configure(state='disabled' if local else 'readonly')
        music_entry.configure(state='normal' if local else 'disabled')
        music_browse.configure(state='normal' if local else 'disabled')
    music_source.trace_add('write',music_source_changed); music_source_changed()
    music_volume=tk.DoubleVar(value=cfg.get('music_volume',0.22))
    music_volume_label=tk.StringVar()
    def music_volume_changed(*_): music_volume_label.set(f'Music volume: {music_volume.get()*100:.0f}%')
    music_volume.trace_add('write',music_volume_changed); music_volume_changed()
    ttk.Label(frame,textvariable=music_volume_label).pack(anchor='w',pady=(8,3))
    ttk.Scale(frame,from_=0,to=0.5,variable=music_volume).pack(fill='x')
    music_duck=tk.BooleanVar(value=cfg.get('duck_music',True))
    ttk.Checkbutton(frame,text='Lower music automatically while the narrator speaks',variable=music_duck).pack(anchor='w',pady=6)
    ttk.Label(frame,text='English narration • reference-image scene editing • editable storyboards • local generation').pack(anchor='w',pady=14)
    buttons = ttk.Frame(bottom)
    buttons.pack(fill='x')
    status = tk.StringVar(value='Local models are installed. Ready to create. Daily schedule is not enabled.')
    ttk.Label(bottom,textvariable=status,wraplength=920).pack(anchor='w',pady=10)
    output = tk.Text(bottom,bg='#192539',fg='#d0d5dd',font=('Consolas',9),height=5,wrap='word')
    output.pack(fill='both',expand=True)
    messages=queue.Queue()
    running=[False]
    latest_project=[None]
    def save():
        cfg['prompt']=prompt_box.get('1.0','end-1c').strip()
        if len(cfg['prompt'])>12000:
            raise ValueError('Please keep the prompt under 12,000 characters.')
        for key,value in values.items():
            cfg[key]=int(value.get()) if key in ['comics_per_batch','panels'] else value.get()
        if not 1<=cfg['comics_per_batch']<=100 or not 2<=cfg['panels']<=12:
            raise ValueError('Use 1–100 comics and 2–12 panels.')
        from book import request_spec
        request_spec(cfg)
        if len(cfg['characters'])>2000:
            raise ValueError('Keep character descriptions under 2,000 characters.')
        if len(cfg['continuity'])>2000:
            raise ValueError('Keep recurring object and location notes under 2,000 characters.')
        cfg['reference_image']=reference.get().strip()
        if cfg['reference_image'] and not Path(cfg['reference_image']).is_file():
            raise ValueError('The reference image does not exist. Browse to an image or clear the field.')
        cfg['consistent_characters']=True
        cfg['reference_strength']=round(strength.get(),2)
        cfg['image_size']=1024 if quality.get().startswith('Quality') else 768
        cfg['anatomy_check']=anatomy.get()
        cfg['anatomy_retries']=2
        cfg['sdxl_steps']=36 if cfg['image_size']==1024 else 24
        cfg['steps']=cfg.get('klein_steps',4) if cfg.get('image_engine')=='klein' else cfg['sdxl_steps']
        cfg['output_width']=1024
        cfg.update(background_music=music_enabled.get(),music_mode='file' if music_source.get()=='Local audio file' else 'generated',
                   music_style=music_mood.get(),music_file=music_path.get().strip(),music_volume=round(music_volume.get(),3),duck_music=music_duck.get())
        if cfg['background_music'] and cfg['music_mode']=='file' and not Path(cfg['music_file']).is_file():
            raise ValueError('Choose an existing local music file or switch to built-in music.')
        (ROOT/'config.json').write_text(json.dumps(cfg,indent=2,ensure_ascii=False),encoding='utf-8')
    def start(sample=False,plan=False,project=None,music_only=False,voice_only=False):
        if running[0]:
            return
        try:
            save()
        except Exception as exc:
            messagebox.showerror('Settings',str(exc)); return
        if project is None and not cfg.get('prompt','').strip():
            messagebox.showinfo('Your comic idea','Enter a comic idea or a full panel script first.');return
        running[0]=True
        status.set('Updating music locally. Artwork will be reused.' if music_only else 'Working locally. Keep the PC awake and connected to power.')
        def worker():
            try:
                args=[str(engine_python()),'-u',str(CODE_HOME/'factory.py')]
                if sample:
                    args+=['--count','1']
                if plan:
                    args+=['--plan-only']
                if project:
                    args+=['--resume',str(project)]
                if music_only:
                    args+=['--music-only']
                if voice_only:args+=['--voice-only']
                env=dict(os.environ,PYTHONUTF8='1')
                process=subprocess.Popen(args,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                                         encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW)
                review_project=None
                planning_paused=False
                art_review=False
                for line in process.stdout:
                    if line.startswith('PROJECT_CREATED:'):
                        messages.put(('project',line.split(':',1)[1].strip()))
                    elif line.startswith('STORYBOARD_READY:'):
                        review_project=line.split(':',1)[1].strip()
                        messages.put(('project',review_project))
                    elif line.startswith('Finished: '):
                        messages.put(('project',line[len('Finished: '):].strip()))
                    elif line.startswith('PLANNING_PAUSED:'):
                        planning_paused=True
                        messages.put(('project',line.split(':',1)[1].strip()))
                    elif line.startswith('ART_REVIEW_REQUIRED:'):
                        art_review=True
                    messages.put(line)
                code=process.wait()
                if review_project:
                    messages.put(('project',review_project))
                messages.put(('done',code,plan or bool(review_project),music_only,planning_paused,art_review))
            except Exception as exc:
                messages.put(str(exc)+'\n'); messages.put(('done',1,False,music_only))
        threading.Thread(target=worker,daemon=True).start()
    def poll():
        while not messages.empty():
            entry=messages.get()
            if isinstance(entry,tuple):
                if entry[0]=='project':
                    latest_project[0]=Path(entry[1])
                    continue
                running[0]=False
                if len(entry)>4 and entry[4]:
                    status.set('Book planning paused at a saved page. Choose Resume book planning to continue.');continue
                if len(entry)>3 and entry[3]:
                    status.set('Music updated. Open your library to play the comic.' if entry[1]==0 else 'Music update failed. See the details below.')
                else:
                    status.set('Finished. Open your library to see the results.' if entry[1]==0 else 'Generation failed. See the details below and error.txt in the comic folder.')
                if entry[1]==0 and len(entry)>2 and entry[2]:
                    status.set('Storyboard ready. Review the scenes, then choose Save and render.')
                    review()
                    if len(entry)>5 and entry[5]:
                        status.set('Video paused: some artwork needs review. A comic preview with text is saved. Inspect the flagged drawings, then Save and render.')
            else:
                output.insert('end',entry); output.see('end')
                if isinstance(entry,str) and entry.startswith(('Writing page ','Saved page ','Outlining pages ','Writer active:','Drawing page ','Request detected:','Drawing panel ','Checking visible anatomy','Retrying only this panel:','Visual reviewer:','Loading the local emotional','Acting line ','Saved acted line','Upgrading character voices')):
                    status.set(entry.strip())
        window.after(200,poll)
    def review():
        from storyboard import open_editor
        folder=latest_project[0]
        if folder is None:
            selected=filedialog.askdirectory(title='Choose a comic storyboard folder',initialdir=ROOT/'library')
            if not selected: return
            folder=Path(selected)
        if not (folder/'story.json').exists():
            messagebox.showerror('Storyboard','Choose a comic folder containing story.json.'); return
        latest_project[0]=folder
        open_editor(window,folder,lambda chosen:start(project=chosen))
    ttk.Button(buttons,text='Make one comic',command=lambda:start(True)).grid(row=0,column=0,padx=4,pady=4,sticky='ew')
    ttk.Button(buttons,text='Plan story first',command=lambda:start(True,True)).grid(row=0,column=1,padx=4,pady=4,sticky='ew')
    ttk.Button(buttons,text='Review storyboard',command=review).grid(row=0,column=2,padx=4,pady=4,sticky='ew')
    ttk.Button(buttons,text='Run batch',command=start).grid(row=1,column=0,padx=4,pady=4,sticky='ew')
    def stop():
        if running[0]:
            (ROOT/'stop-after-current.flag').touch()
            status.set('Stop requested. The current planning step or drawn page will finish before a book pauses; a short comic finishes before its batch stops.')
    ttk.Button(buttons,text='Stop after current',command=stop).grid(row=1,column=1,padx=4,pady=4,sticky='ew')
    def library():
        (ROOT/'library').mkdir(exist_ok=True)
        os.startfile(ROOT/'library')
    ttk.Button(buttons,text='Open library',command=library).grid(row=1,column=2,padx=4,pady=4,sticky='ew')
    def update_music():
        if running[0]: return
        selected=filedialog.askdirectory(title='Choose a comic folder to update its music',initialdir=latest_project[0] or ROOT/'library')
        if selected:
            start(project=Path(selected),music_only=True)
    ttk.Button(buttons,text='Update music on existing comic',command=update_music).grid(row=2,column=0,columnspan=3,padx=4,pady=4,sticky='ew')
    def resume_plan():
        if running[0]:return
        folder=latest_project[0]
        if folder is None:
            chosen=filedialog.askdirectory(title='Choose the unfinished book folder',initialdir=ROOT/'library')
            if not chosen:return
            folder=Path(chosen)
        if not (folder/'book_plan.json').exists():
            messagebox.showerror('Resume planning','Choose a multi-page book folder containing book_plan.json.');return
        start(sample=True,plan=True,project=folder)
    ttk.Button(buttons,text='Resume book planning',command=resume_plan).grid(row=3,column=0,columnspan=3,padx=4,pady=4,sticky='ew')
    def upgrade_voices():
        if running[0]:return
        selected=filedialog.askdirectory(title='Choose a comic folder for expressive character voices',initialdir=latest_project[0] or ROOT/'library')
        if selected:start(project=Path(selected),voice_only=True)
    ttk.Button(buttons,text='Upgrade voices and video (reuse images)',command=upgrade_voices).grid(row=4,column=0,columnspan=3,padx=4,pady=4,sticky='ew')
    def resume_saved():
        if running[0]:return
        selected=filedialog.askdirectory(title='Choose a saved or failed comic folder',initialdir=latest_project[0] or ROOT/'library')
        if selected:start(sample=True,project=Path(selected))
    ttk.Button(buttons,text='Resume saved comic',command=resume_saved).grid(row=5,column=0,columnspan=3,padx=4,pady=4,sticky='ew')
    for column in range(3): buttons.columnconfigure(column,weight=1)
    def close():
        if running[0] and not messagebox.askyesno('Comic still running','The comic will continue running after this window closes. Close the window?'):
            return
        window.destroy()
    window.protocol('WM_DELETE_WINDOW',close)
    poll()
    window.mainloop()

if __name__=='__main__':
    main()
