"""Windows launcher and resumable first-run setup wizard."""
import json,os,queue,subprocess,sys,threading,webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from setup_core import Setup,SetupCancelled,hardware,ready
BUNDLE=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
def configured_home():
    if os.environ.get('COMIC_FACTORY_HOME'):return Path(os.environ['COMIC_FACTORY_HOME']).expanduser().resolve()
    local=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local/share')
    try:return Path(json.loads((local/'ComicFactoryLauncher/storage.json').read_text())['data_home']).resolve()
    except (OSError,ValueError,KeyError,TypeError):return local/'ComicFactory'

def save_home(home):
    path=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local/share')/'ComicFactoryLauncher/storage.json'
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps({'data_home':str(Path(home).resolve())}),encoding='utf-8')

DEFAULT_HOME=configured_home()

def app(home):
    env=dict(os.environ,COMIC_FACTORY_HOME=str(home),PYTHONUTF8='1',COMIC_FACTORY_LAUNCHER=str(Path(sys.executable).resolve()) if getattr(sys,'frozen',False) else '')
    for key in ('PYTHONPATH','PYTHONHOME','PYTHONUSERBASE','VIRTUAL_ENV'):env.pop(key,None)
    env['PYTHONNOUSERSITE']='1'
    exe=home/'.venv/Scripts/pythonw.exe'
    with open(home/'logs/app-startup.log','a',encoding='utf-8') as log:
        subprocess.Popen([str(exe),str(BUNDLE/'engine/app.py')],cwd=home,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)

def main():
    if '--uninstall' in sys.argv:
        from installer_ops import uninstall
        root=tk.Tk();root.withdraw()
        if '--silent' in sys.argv or messagebox.askyesno('Uninstall Comic Factory','Remove the application? Your downloaded models and comic projects will be kept.'):
            uninstall(Path(sys.executable).resolve().parent,os.getpid())
        root.destroy();return
    if '--self-test' in sys.argv:
        root=tk.Tk();root.withdraw()
        assert (BUNDLE/'engine/app.py').is_file();assert (BUNDLE/'model-manifest.json').is_file()
        manifest=json.loads((BUNDLE/'model-manifest.json').read_text())
        assert manifest['python']['sha256'] and manifest['models']
        root.destroy();report={'launcher':'passed','tk':'passed','payload':'passed','frozen':bool(getattr(sys,'frozen',False))}
        if '--report' in sys.argv:Path(sys.argv[sys.argv.index('--report')+1]).write_text(json.dumps(report,indent=2))
        return
    home=DEFAULT_HOME
    if '--setup' not in sys.argv and ready(BUNDLE,home):app(home);return
    root=tk.Tk();root.title('Comic Factory — first-time setup');root.geometry('760x600');root.minsize(650,520)
    style=ttk.Style(root);style.theme_use('clam')
    frame=ttk.Frame(root,padding=24);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Comic Factory',font=('Segoe UI',24,'bold')).pack(anchor='w')
    ttk.Label(frame,text='Windows / NVIDIA beta · local generation · no paid API required',font=('Segoe UI',11)).pack(anchor='w',pady=(2,14))
    ttk.Label(frame,text='This setup installs private drawing and speech runtimes, downloads the AI models,\nand checks the GPU. Initial downloads are large; keep at least 60 GB free.\nOnce setup finishes, generation runs locally. Artwork can still need review.',wraplength=690,justify='left').pack(anchor='w')
    path=tk.StringVar(value=str(home));status=tk.StringVar(value='Choose a storage folder, then start setup. Download progress is saved if interrupted.')
    ttk.Label(frame,text='Models, settings and your comics').pack(anchor='w',pady=(18,2))
    row=ttk.Frame(frame);row.pack(fill='x');ttk.Entry(row,textvariable=path).pack(side='left',fill='x',expand=True)
    def browse():
        chosen=filedialog.askdirectory(title='Choose the Comic Factory storage folder',initialdir=path.get())
        if chosen:path.set(str(Path(chosen)/'ComicFactory'))
    choose=ttk.Button(row,text='Choose folder',command=browse);choose.pack(side='right',padx=(8,0))
    ttk.Label(frame,textvariable=status,wraplength=680).pack(anchor='w',pady=(18,5))
    progress=ttk.Progressbar(frame,mode='indeterminate');progress.pack(fill='x')
    text=tk.Text(frame,height=11,wrap='word',font=('Segoe UI',10));text.pack(fill='both',expand=True,pady=12)
    controls=ttk.Frame(frame);controls.pack(fill='x');events=queue.Queue();busy=[False];cancel=[None];success=[False]
    def report(value):events.put(('log',value))
    def start():
        if busy[0]:return
        target=Path(path.get()).expanduser().resolve()
        if target==Path(target.anchor):messagebox.showerror('Choose a folder','Choose a named folder, not a drive root.');return
        save_home(target)
        busy[0]=True;success[0]=False;start_button.configure(state='disabled');choose.configure(state='disabled');open_button.configure(state='disabled');progress.start(12)
        token=threading.Event();cancel[0]=token
        def worker():
            try:
                setup=Setup(BUNDLE,target,report,token);setup.run();events.put(('done',str(target)))
            except SetupCancelled:events.put(('error','Setup paused. Click Retry to resume the downloads.'))
            except Exception as exc:events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()
    def poll():
        while not events.empty():
            kind,value=events.get()
            if kind=='log':status.set(value);text.insert('end',value+'\n');text.see('end')
            else:
                busy[0]=False;progress.stop();choose.configure(state='normal');start_button.configure(state='normal',text='Verify / repair setup')
                if kind=='done':
                    success[0]=True;status.set('Ready to create. Open Comic Factory below.');open_button.configure(state='normal')
                else:status.set(value);text.insert('end',value+'\n');start_button.configure(text='Retry setup')
        root.after(150,poll)
    def launch():app(Path(path.get()).resolve());root.destroy()
    start_button=ttk.Button(controls,text='Set up my PC',command=start);start_button.pack(side='left')
    ttk.Button(controls,text='Pause',command=lambda:cancel[0].set() if cancel[0] else None).pack(side='left',padx=8)
    open_button=ttk.Button(controls,text='Open Comic Factory',command=launch,state='disabled');open_button.pack(side='right')
    def logs():
        folder=Path(path.get())/'logs';folder.mkdir(parents=True,exist_ok=True);os.startfile(folder)
    ttk.Button(controls,text='Open setup logs',command=logs).pack(side='right',padx=8)
    def close():
        if busy[0]:
            if messagebox.askyesno('Pause setup?','Pause setup and close? Completed downloads will be kept.'):
                cancel[0].set();status.set('Pausing safely. Close again when setup is paused.')
            return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close);root.after(150,poll);root.mainloop()

if __name__=='__main__':main()
