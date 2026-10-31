import ast,hashlib,http.server,io,json,os,sys,tarfile,tempfile,threading,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from setup_core import download,extract_archive,SetupCancelled,ready

class ProductTests(unittest.TestCase):
 def setUp(self):
  parent=ROOT/'build/test-tmp';parent.mkdir(parents=True,exist_ok=True)
  self.temp=tempfile.TemporaryDirectory(dir=parent);self.folder=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def test_source_has_no_personal_absolute_paths_or_private_config(self):
  for source in (ROOT/'engine').glob('*.py'):
   text=source.read_text(encoding='utf-8');ast.parse(text)
   self.assertNotIn('C:\\Users\\',text,source.name);self.assertNotIn('C:/Users/',text,source.name)
  defaults=json.loads((ROOT/'engine/defaults.json').read_text())
  for name in ('prompt','characters','reference_image','music_file'):self.assertEqual(defaults[name],'')
 def test_every_download_is_pinned_and_checksummed(self):
  manifest=json.loads((ROOT/'model-manifest.json').read_text())
  for asset in [manifest['python'],manifest['ollama']]+[a for m in manifest['models'] for a in m['files']]:
   self.assertTrue(asset['url'].startswith('https://'));self.assertEqual(len(asset['sha256']),64);self.assertGreater(asset['size'],0)
   if asset.get('path'):self.assertTrue((self.folder/asset['path']).resolve().is_relative_to(self.folder.resolve()))
 def test_archive_path_traversal_is_rejected(self):
  path=self.folder/'bad.zip'
  with zipfile.ZipFile(path,'w') as archive:archive.writestr('../escape.txt','bad')
  with self.assertRaises(ValueError):extract_archive(path,self.folder/'target')
  self.assertFalse((self.folder/'escape.txt').exists())
 def test_tar_link_is_rejected(self):
  path=self.folder/'bad.tar'
  with tarfile.open(path,'w') as archive:
   item=tarfile.TarInfo('link');item.type=tarfile.SYMTYPE;item.linkname='../escape';archive.addfile(item)
  with self.assertRaises(ValueError):extract_archive(path,self.folder/'target')
 def test_partial_download_resumes_and_verifies_hash(self):
  data=b'comic-data-'*2000;requests=[]
  class Handler(http.server.BaseHTTPRequestHandler):
   def do_GET(self):
    header=self.headers.get('Range');requests.append(header);offset=int(header[6:].split('-')[0]) if header else 0
    self.send_response(206 if header else 200)
    if header:self.send_header('Content-Range',f'bytes {offset}-{len(data)-1}/{len(data)}')
    self.send_header('Content-Length',str(len(data)-offset));self.end_headers();self.wfile.write(data[offset:])
   def log_message(self,*args):pass
  server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   target=self.folder/'asset.bin';target.with_name('asset.bin.partial').write_bytes(data[:100])
   asset={'url':f'http://127.0.0.1:{server.server_port}/asset','size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
   download(asset,target,lambda _:None,allow_http=True)
   self.assertEqual(target.read_bytes(),data);self.assertEqual(requests[0],'bytes=100-')
   download(asset,target,lambda _:None,allow_http=True);self.assertEqual(len(requests),1)
  finally:server.shutdown();server.server_close()
 def test_cancelled_setup_does_not_discard_completed_partial_data(self):
  target=self.folder/'asset';partial=target.with_name('asset.partial');partial.write_bytes(b'saved')
  token=threading.Event();token.set()
  with self.assertRaises(SetupCancelled):download({'url':'https://example.com/file','size':100,'sha256':'0'*64},target,lambda _:None,token)
  self.assertEqual(partial.read_bytes(),b'saved')
 def test_a_ready_flag_alone_does_not_skip_missing_models(self):
  (self.folder/'setup-state.json').write_text(json.dumps({'ready':True}))
  self.assertFalse(ready(ROOT,self.folder))
 def test_data_paths_do_not_follow_the_install_directory(self):
  import subprocess
  env=dict(os.environ,COMIC_FACTORY_HOME=str(self.folder/'data'),PYTHONDONTWRITEBYTECODE='1')
  script="import sys; sys.path.insert(0,sys.argv[1]); import runtime_paths; root=runtime_paths.ensure_data(); print(root); assert (root/'config.json').exists()"
  result=subprocess.run([sys.executable,'-c',script,str(ROOT/'engine')],env=env,capture_output=True,text=True,check=True)
  self.assertIn(str(self.folder/'data'),result.stdout);self.assertFalse((ROOT/'engine/config.json').exists())
 def test_custom_model_storage_is_remembered_on_next_launch(self):
  from launcher import configured_home,save_home
  with patch.dict(os.environ,{'LOCALAPPDATA':str(self.folder)},clear=True):
   chosen=self.folder/'another-volume/ComicFactory';save_home(chosen)
   self.assertEqual(configured_home(),chosen.resolve())
 def test_explicit_home_overrides_a_saved_storage_location(self):
  from launcher import configured_home,save_home
  with patch.dict(os.environ,{'LOCALAPPDATA':str(self.folder)},clear=True):
   save_home(self.folder/'saved')
   with patch.dict(os.environ,{'COMIC_FACTORY_HOME':str(self.folder/'explicit')}):self.assertEqual(configured_home(),(self.folder/'explicit').resolve())
if __name__=='__main__':unittest.main()
