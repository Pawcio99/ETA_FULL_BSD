"""Offhost deterministic FreeBSD pkg-build INPUT preview regressions; not pkg create."""
import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import m2_pkg_preview as m2
import eta_i3_package as pkg
INPUT = ROOT/'ETA_W09_CORE_LAB_R1.zip'
DATA = INPUT.read_bytes()


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parsed = pkg.load_package(INPUT, m2.ZIP_PIN)
        cls.preview = m2.build_bytes(cls.parsed)
        with zipfile.ZipFile(io.BytesIO(cls.preview)) as z:
            cls.entries = {info.filename:z.read(info) for info in z.infolist()}
            cls.infos = z.infolist()
        cls.manifest = json.loads(cls.entries['+MANIFEST'])

    def test_source_package_pin(self):
        self.assertEqual(hashlib.sha256(DATA).hexdigest(), m2.ZIP_PIN)

    def test_source_package_exact_five_files(self):
        self.assertEqual(len(self.parsed['payload']),5)
        self.assertEqual(set(self.parsed['payload']),set(pkg.PINS))

    def test_deterministic_bytes(self):
        self.assertEqual(self.preview, m2.build_bytes(self.parsed))

    def test_frozen_timestamp_and_no_compression(self):
        self.assertTrue(all(i.date_time == (1980,1,1,0,0,0) for i in self.infos))
        self.assertTrue(all(i.compress_type == zipfile.ZIP_STORED for i in self.infos))

    def test_closed_preview_inventory(self):
        self.assertEqual(set(self.entries),
            {'+MANIFEST','README_BUILD_ONLY.md','PACKAGE_INTAKE_SHA256',
             'STAGE_SOURCE_SHA256SUMS'}|
             {m2.STAGE_PARENT+'/'+name for name in pkg.PINS})

    def test_safe_zip_modes(self):
        self.assertTrue(all(stat.S_IFMT(i.external_attr>>16)==stat.S_IFREG
                            for i in self.infos))
        self.assertTrue(all(stat.S_IMODE(i.external_attr>>16)==0o444
                            for i in self.infos))

    def test_pkg_manifest_abi_and_identity(self):
        self.assertEqual(self.manifest['abi'], 'FreeBSD:15:amd64')
        self.assertEqual(self.manifest['arch'], 'FreeBSD:15:amd64')
        self.assertEqual(self.manifest['name'], m2.PKG_NAME)
        self.assertEqual(self.manifest['version'], m2.PKG_VERSION)

    def test_no_active_product_path(self):
        self.assertNotIn('libexec/eta-cherub-full',str(self.manifest))
        self.assertTrue(all(k.startswith('/usr/local/share/eta-full-bsd-five-module-preview/tools/')
                         for k in self.manifest['files']))

    def test_no_install_scripts(self):
        self.assertFalse('scripts' in self.manifest)
        self.assertFalse('service' in self.manifest)
        self.assertFalse('commands' in self.manifest)
        self.assertNotIn('pkg add',self.entries['README_BUILD_ONLY.md'].decode().lower())

    def test_checksums_and_flat_size(self):
        self.assertEqual(self.manifest['flatsize'],sum(len(x) for x in self.parsed['payload'].values()))
        for name,body in self.parsed['payload'].items():
            self.assertEqual(m2.sha(body),pkg.PINS[name])
            self.assertEqual(self.entries[m2.STAGE_PARENT+'/'+name],body)
            self.assertEqual(self.manifest['files'][m2.PREFIX+'/'+m2.STAGE_SUBPATH+'/'+name],m2.sha(body))

    def test_manifest_canonical(self):
        self.assertEqual(self.entries['+MANIFEST'],m2.canonical(self.manifest))

    def test_no_state_or_secrets(self):
        self.assertFalse(any('state/' in path or 'secret' in path or 'grant' in path for path in self.entries))

    def test_wrong_source_pin_blocks(self):
        with self.assertRaises(pkg.Refusal):
            pkg.load_package(INPUT, '0'*64)

    def test_wrong_source_content_blocks(self):
        bad = dict(self.parsed)
        bad['payload'] = dict(self.parsed['payload'])
        bad['payload']['agentctl.py'] += b'edited\n'
        with self.assertRaises(pkg.Refusal):m2.build_bytes(bad)

    def test_wrong_scope_blocks(self):
        bad = dict(self.parsed)
        bad['manifest'] = dict(self.parsed['manifest'])
        bad['manifest']['scope']='FULL_PRODUCT'
        with self.assertRaises(pkg.Refusal):m2.build_bytes(bad)

    def test_wrong_state_schema_version_blocks(self):
        bad = dict(self.parsed)
        bad['manifest'] = dict(self.parsed['manifest'])
        bad['manifest']['state'] = dict(self.parsed['manifest']['state'])
        bad['manifest']['state']['user_version'] = 1
        with self.assertRaises(pkg.Refusal):m2.build_bytes(bad)

    def test_unprivileged_cli_output_created_once(self):
        with tempfile.TemporaryDirectory(prefix='eta-m2-') as root:
            target = Path(root)/'build-only.zip'
            args=[sys.executable,'-I','-B',str(ROOT/'m2_pkg_preview.py'),
                  '--package',str(INPUT),'--sha256',m2.ZIP_PIN,'--output',str(target)]
            first=subprocess.run(args,capture_output=True,text=True,timeout=10)
            self.assertEqual(first.returncode,0,first.stderr+first.stdout)
            self.assertEqual(target.read_bytes(),self.preview)
            second=subprocess.run(args,capture_output=True,text=True,timeout=10)
            self.assertEqual(second.returncode,20)
            self.assertEqual(target.read_bytes(),self.preview)

    def test_bad_abi_not_silently_changed(self):
        self.assertEqual(m2.FREEBSD_ABI,'FreeBSD:15:amd64')

if __name__ == '__main__': unittest.main(verbosity=2)
