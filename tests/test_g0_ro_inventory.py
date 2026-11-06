import importlib.util
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

FILE = Path(__file__).with_name('g0_ro_inventory.py')
sp = importlib.util.spec_from_file_location('inventory', FILE)
inv = importlib.util.module_from_spec(sp)
sp.loader.exec_module(inv)

class G0InventoryTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name) / 'conductor'
        self.root.mkdir()
        r = self.root / '08_MODEL_PRACY_MK1'
        r.mkdir()
        (r / 'RUN.sh').write_bytes(b'not executed\n')
        (r / 'CHECKPOINT.json').write_bytes(b'{"stage":"blocked"}\n')
        (r / 'ZADANIE.txt').write_bytes(b'private input\n')
        (self.root / 'secrets').mkdir()
        (self.root / 'secrets' / 'MANIFEST.json').write_bytes(b'never read\n')
    def cmd(self, *opts):
        p = subprocess.run([sys.executable,'-B',str(FILE),'--root',f'conductor={self.root}',*opts],capture_output=True,text=True,timeout=8)
        return p.returncode,json.loads(p.stdout)
    def test_present(self):
        rc,r=self.cmd()
        self.assertEqual(rc,0)
        self.assertEqual(r['result'],'METADATA_INVENTORY_ONLY')
        self.assertIn('08_MODEL_PRACY_MK1/CHECKPOINT.json',r['roots']['conductor']['marker_metadata'])
        self.assertEqual(r['roots']['conductor']['selected_new_checks']['08_MODEL_PRACY_MK1/RUN.sh']['status'],'HASHED')
        self.assertFalse(r['current_git_head_attested'])
        self.assertEqual(r['g0'],'BLOCKED')
    def test_skips_secret_directory(self):
        r=self.cmd()[1]
        self.assertFalse(any('secrets' in k for k in r['roots']['conductor']['marker_metadata']))
    def test_no_zadanie_read(self):
        r=self.cmd()[1]
        self.assertFalse(any('ZADANIE' in k for k in r['roots']['conductor']['marker_metadata']))
        self.assertFalse(any('ZADANIE' in k for k in r['roots']['conductor']['selected_new_checks']))
    def test_missing_root(self):
        rc,r=self.cmd('--root',f'z1={self.root}/does-not-exist')
        self.assertEqual(rc,20)
        self.assertEqual(r['roots']['z1']['status'],'UNAVAILABLE')
    def test_symlink_root_refused(self):
        link=Path(self.t.name)/'link'
        link.symlink_to(self.root, target_is_directory=True)
        rc,r=self.cmd('--root',f'z1={link}')
        self.assertEqual(rc,20)
        self.assertEqual(r['roots']['z1']['status'],'UNAVAILABLE')
    def test_symlink_marker_skipped(self):
        d=self.root/'08_MODEL_PRACY_MK1'
        (d/'MANIFEST.sha256').symlink_to('/etc/passwd')
        rc,r=self.cmd()
        self.assertEqual(rc,0)
        self.assertNotIn('08_MODEL_PRACY_MK1/MANIFEST.sha256',r['roots']['conductor']['marker_metadata'])
    def test_symlink_file_refused(self):
        f=self.root/'08_MODEL_PRACY_MK1'/'RUN.sh'
        f.unlink();f.symlink_to('/etc/passwd')
        r=self.cmd()[1]
        self.assertEqual(r['roots']['conductor']['selected_new_checks']['08_MODEL_PRACY_MK1/RUN.sh']['status'],'BLOCKED')
    def test_reject_label(self):
        p=subprocess.run([sys.executable,'-B',str(FILE),'--root',f'danger={self.root}'],capture_output=True,text=True)
        self.assertEqual(p.returncode,21)
    def test_reject_traversal(self):
        p=subprocess.run([sys.executable,'-B',str(FILE),'--root',f'z1={self.root}/../conductor'],capture_output=True,text=True)
        self.assertEqual(p.returncode,21)
    def test_reject_duplicate(self):
        self.assertEqual(self.cmd('--root',f'conductor={self.root}')[0],21)
    def test_refuse_too_large_marker(self):
        marker=self.root/'MANIFEST.json'
        with marker.open('wb') as fh:fh.truncate(1024*1024+1)
        r=self.cmd()[1]
        self.assertEqual(r['roots']['conductor']['marker_metadata']['MANIFEST.json']['status'],'BLOCKED')
    def test_zero_depth_no_nested_marker(self):
        r=self.cmd('--depth','0')[1]
        self.assertEqual(r['roots']['conductor']['marker_metadata'],{})
    def test_no_bytecode_generated(self):
        before=set(self.root.rglob('*.pyc'))
        self.cmd()
        self.assertEqual(before,set(self.root.rglob('*.pyc')))
    def test_git_metadata_only(self):
        (self.root/'.git').mkdir()
        (self.root/'.git'/'config').write_bytes(b'FAKESECRET')
        r=self.cmd()[1]
        self.assertEqual(r['roots']['conductor']['git_metadata_type'],'DIR')
        self.assertEqual(r['roots']['conductor']['git_head'],'NOT_ATTESTED')
    def test_public_no_root_paths(self):
        r=self.cmd()[1]
        self.assertNotIn(str(self.root),json.dumps(r))
if __name__=='__main__':unittest.main(verbosity=2)
