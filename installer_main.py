"""Native 64-bit per-user installer, built as one self-contained executable."""
import argparse,json,os,queue,subprocess,sys,threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from installer_ops import install
BUNDLE=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--silent',action='store_true');parser.add_argument('--portable',action='store_true');parser.add_argument('--install-dir')
    args=parser.parse_args();product=json.loads((BUNDLE/'product.json').read_text())
    target=Path(args.install_dir or Path(os.environ.get('LOCALAPPDATA') or Path.home())/'Programs/ComicFactory')
    payload=BUNDLE/'payload.zip';digest=(BUNDLE/'payload.sha256').read_text().strip()
    if args.silent:install(payload,digest,target,product['version'],args.portable);return
    root=tk.Tk();root.title('Install Comic Factory');root.geometry('650x430');root.resizable(False,False)
    frame=ttk.Frame(root,padding=28);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Install Comic Factory',font=('Segoe UI',23,'bold')).pack(anchor='w')
    ttk.Label(frame,text='Windows / NVIDIA beta · '+product['version'],font=('Segoe UI',11)).pack(anchor='w',pady=(5,16))
    ttk.Label(frame,text='Create lettered comics and voiced videos using local AI.\n\nFirst launch downloads approximately 20 GB of models and runtimes.\nKeep at least 60 GB free. An NVIDIA RTX 30-series or newer GPU\nwith 8 GB VRAM and 24 GB RAM are required (32 GB RAM recommended).\n\nThe beta can still need story, artwork and speech-balloon review.',justify='left').pack(anchor='w')
    path=tk.StringVar(value=str(target));row=ttk.Frame(frame);row.pack(fill='x',pady=(18,8));ttk.Entry(row,textvariable=path).pack(side='left',fill='x',expand=True)
    def choose():
        folder=filedialog.askdirectory(title='Choose an empty app installation folder')
        if folder:path.set(str(Path(folder)/'ComicFactory'))
    ttk.Button(row,text='Choose folder',command=choose).pack(side='right',padx=(8,0))
    status=tk.StringVar(value='Installs for your user account; no administrator password required.')
    ttk.Label(frame,textvariable=status,wraplength=590).pack(anchor='w',pady=6)
    events=queue.Queue();busy=[False];button=ttk.Button(frame,text='Install');button.pack(anchor='e',pady=12)
    def start():
        if busy[0]:return
        install_root=Path(path.get()).expanduser().resolve()
        busy[0]=True;button.configure(state='disabled');status.set('Installing the application...')
        def worker():
            try:events.put(('done',str(install(payload,digest,install_root,product['version'],args.portable))))
            except Exception as exc:events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()
    button.configure(command=start)
    def poll():
        while not events.empty():
            kind,value=events.get();busy[0]=False
            if kind=='done':
                status.set('Installed. Open Comic Factory to prepare the local models.')
                def launch():subprocess.Popen([str(Path(value)/'ComicFactory.exe')],creationflags=subprocess.CREATE_NO_WINDOW);root.destroy()
                button.configure(state='normal',text='Open Comic Factory',command=launch)
            else:status.set(value);button.configure(state='normal',text='Retry install')
        root.after(150,poll)
    def close():
        if busy[0]:messagebox.showinfo('Installing','Please wait for the installation to finish.');return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close);root.after(150,poll);root.mainloop()
if __name__=='__main__':main()
