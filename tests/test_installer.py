import hashlib,json,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from installer_ops import install,MARKER

class InstallerTests(unittest.TestCase):
 def setUp(self):
  parent=ROOT/'build/test-tmp';parent.mkdir(parents=True,exist_ok=True)
  self.temp=tempfile.TemporaryDirectory(dir=parent);self.folder=Path(self.temp.name)
  self.payload=self.folder/'payload.zip'
  with zipfile.ZipFile(self.payload,'w') as archive:
   archive.writestr('ComicFactory.exe',b'test executable fixture')
   archive.writestr('_internal/product.json','{"version":"test"}')
  self.digest=hashlib.sha256(self.payload.read_bytes()).hexdigest()
 def tearDown(self):self.temp.cleanup()
 def test_install_tracks_owned_files_and_can_update_without_removing_custom_files(self):
  target=self.folder/'app';install(self.payload,self.digest,target,'test',portable=True)
  self.assertTrue((target/MARKER).exists());self.assertTrue((target/'ComicFactory.exe').exists())
  (target/'my-notes.txt').write_text('keep this')
  install(self.payload,self.digest,target,'test2',portable=True)
  self.assertEqual((target/'my-notes.txt').read_text(),'keep this')
  self.assertEqual(json.loads((target/MARKER).read_text())['version'],'test2')
 def test_unrelated_nonempty_folder_is_not_overwritten(self):
  target=self.folder/'app';target.mkdir();(target/'personal.txt').write_text('private')
  with self.assertRaises(ValueError):install(self.payload,self.digest,target,'test',portable=True)
  self.assertEqual((target/'personal.txt').read_text(),'private')
 def test_tampered_payload_is_not_installed(self):
  with self.assertRaises(ValueError):install(self.payload,'0'*64,self.folder/'app','test',portable=True)
  self.assertFalse((self.folder/'app/ComicFactory.exe').exists())
 def test_installer_payload_cannot_write_outside_install_tree(self):
  with zipfile.ZipFile(self.payload,'a') as archive:archive.writestr('../escaped.txt','bad')
  digest=hashlib.sha256(self.payload.read_bytes()).hexdigest()
  with self.assertRaises(ValueError):install(self.payload,digest,self.folder/'app','test',portable=True)
  self.assertFalse((self.folder/'escaped.txt').exists())
if __name__=='__main__':unittest.main()
