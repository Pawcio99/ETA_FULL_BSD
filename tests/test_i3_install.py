#!/usr/bin/env python3
"""Real filesystem/SQLite/CLI/crash tests, only within a disposable offhost root."""
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import unittest
import zipfile
import fcntl

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'installer'))
import eta_i3_lab as lab
import eta_i3_package as pkg
from eta_i3_fs import Root
from eta_i3_verify import inspect_image
WORKSPACE = Path(os.environ['ETA_I3_WORKSPACE'])
PACKAGE = BASE / 'packages/ETA_W09_CORE_LAB_R1.zip'
PIN = (BASE / 'packages/PACKAGE_SHA256').read_text().split()[0]
DATA = PACKAGE.read_bytes()
P = pkg.load_package(PACKAGE, PIN)


def tree_snapshot(root):
    out = {}
    for path in sorted(Path(root).rglob('*')):
        st = path.lstat()
        out[str(path.relative_to(root))] = [st.st_mode, st.st_ino, st.st_size, st.st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None]
    return out


def archive_variant(change):
    files = pkg.zip_files(DATA)
    entries = list(files.items())
    entries = change(entries)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as z:
        for name, body in entries:
            if isinstance(name, zipfile.ZipInfo):
                z.writestr(name, body)
            else:
                info = zipfile.ZipInfo(name); info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o444) << 16
                z.writestr(info, body)
    return output.getvalue()


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(lab.initialize(WORKSPACE))
    def write_variant(self, data):
        path = WORKSPACE / ('input-' + self.root.name + '.zip')
        path.write_bytes(data)
        return path, pkg.sha(data)
    def rejected_archive(self, change):
        path, digest = self.write_variant(archive_variant(change))
        before = tree_snapshot(self.root)
        with self.assertRaises((pkg.Refusal, zipfile.BadZipFile, ValueError, KeyError)):
            pkg.load_package(path, digest)
        self.assertEqual(tree_snapshot(self.root), before)
    def install(self):
        lab.stage(P, str(self.root))
        result = lab.apply(P, str(self.root))
        self.assertEqual(result['result'], 'INSTALLED_AND_READBACK_VERIFIED')
        return result
    def db(self):
        return self.root / 'image/state/cherub-state.sqlite3'
    def crash(self, event, operation):
        p = subprocess.run([sys.executable,'-I','-B',str(Path(__file__).resolve()),
            '--crash-worker',str(self.root),event,operation],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode, 86, p.stdout + p.stderr)
        self.assertEqual(lab.status(P,str(self.root))['result'],'RECOVERY_REQUIRED')
    def test_package_exact_source_bytes(self):
        self.assertEqual(set(P['payload']), set(pkg.PINS))
        for name,data in P['payload'].items(): self.assertEqual(pkg.sha(data),pkg.PINS[name])
        self.assertEqual(P['manifest']['state']['user_version'],2)
    def test_rebuild_is_byte_identical(self):
        self.assertEqual(pkg.pack_payload(P['payload']), DATA)
        self.assertEqual(pkg.pack_payload(P['payload']),pkg.pack_payload(P['payload']))
    def test_wrong_outer_hash(self):
        with self.assertRaisesRegex(pkg.Refusal,'SHA256_MISMATCH'): pkg.load_package(PACKAGE,'0'*64)
    def test_corrupt_payload_rejected_even_with_matching_outer_hash(self):
        self.rejected_archive(lambda e: [(n,b+b'#tampered\n' if n=='payload/agentctl.py' else b) for n,b in e])
    def test_wrong_manifest_state_version(self):
        def change(e):
            m=json.loads(dict(e)['MANIFEST.json']);m['state']['user_version']=1
            return [(n,pkg.canonical(m) if n=='MANIFEST.json' else b) for n,b in e]
        self.rejected_archive(change)
    def test_extra_package_file(self): self.rejected_archive(lambda e:e+[('payload/unapproved.py',b'x')])
    def test_missing_package_file(self): self.rejected_archive(lambda e:e[:-1])
    def test_duplicate_zip_entry(self): self.rejected_archive(lambda e:e+[e[0]])
    def test_zip_traversal(self): self.rejected_archive(lambda e:e+[('../outside',b'bad')])
    def test_zip_absolute_path(self): self.rejected_archive(lambda e:e+[('/etc/test',b'bad')])
    def test_zip_backslash(self): self.rejected_archive(lambda e:e+[('payload\\evil',b'bad')])
    def test_zip_symlink(self):
        def change(e):
            x=zipfile.ZipInfo('link');x.create_system=3;x.external_attr=(stat.S_IFLNK|0o777)<<16
            return e+[(x,b'/etc/passwd')]
        self.rejected_archive(change)
    def test_zip_oversize_entry(self): self.rejected_archive(lambda e:e+[('large',b'x'*(pkg.MAX_ENTRY+1))])
    def test_archive_source_input_sha_required(self):
        with self.assertRaisesRegex(pkg.Refusal,'W09_ARCHIVE_PIN_MISMATCH'): pkg.build_bytes(b'not an archive')
    def test_duplicate_json_key(self):
        with self.assertRaisesRegex(pkg.Refusal,'DUPLICATE_JSON'): pkg.json_unique(b'{"x":1,"x":2}')
    def test_package_symlink(self):
        link=WORKSPACE/('link-'+self.root.name);link.symlink_to(PACKAGE)
        with self.assertRaises(OSError):pkg.load_package(link,PIN)
    def test_nonlab_root_rejected(self):
        with self.assertRaises(pkg.Refusal): lab.package_plan(P,'/usr/local/libexec/eta-cherub-full')
    def test_lab_root_symlink_rejected(self):
        link=self.root.parent/('lab-link-'+self.root.name);link.symlink_to(self.root)
        with self.assertRaises(OSError): lab.package_plan(P,str(link))
    def test_marker_identity_tamper(self):
        mark=self.root/'.eta-i3-lab.json';m=json.loads(mark.read_text());m['inode']+=1;mark.write_bytes(pkg.canonical(m))
        with self.assertRaisesRegex(pkg.Refusal,'MARKER_MISMATCH'):lab.package_plan(P,str(self.root))
    def test_lab_permissions_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises(pkg.Refusal):lab.package_plan(P,str(self.root))
        self.root.chmod(0o700)
    def test_plan_is_zero_write(self):
        before=tree_snapshot(self.root);r=lab.package_plan(P,str(self.root))
        self.assertEqual(r['result'],'PLANNED_NO_WRITES')
        self.assertEqual(tree_snapshot(self.root),before)
    def test_stage_and_idempotent_repeat(self):
        self.assertEqual(lab.stage(P,str(self.root))['result'],'STAGED')
        before=tree_snapshot(self.root)
        self.assertEqual(lab.stage(P,str(self.root))['result'],'STAGED_IDEMPOTENT_NO_WRITES')
        self.assertEqual(tree_snapshot(self.root),before)
        self.assertFalse((self.root/'.stage/state').exists())
    def test_apply_real_stateledger_creates_empty_v2(self):
        r=self.install()
        self.assertEqual(r['files_verified'],5)
        self.assertEqual(set(r['state']['rows'].values()),{0})
        with sqlite3.connect(self.db().as_uri()+'?mode=ro',uri=True) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],2)
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(stat.S_IMODE(self.db().stat().st_mode),0o600)
    def test_apply_repeat_has_no_writes(self):
        self.install();before=tree_snapshot(self.root)
        self.assertEqual(lab.apply(P,str(self.root))['result'],'INSTALLED_IDEMPOTENT_NO_WRITES')
        self.assertEqual(tree_snapshot(self.root),before)
    def test_independent_verify_no_writes(self):
        self.install();before=tree_snapshot(self.root)
        self.assertEqual(lab.verify(P,str(self.root))['result'],'VERIFIED_SCOPED_LAB_IMAGE')
        self.assertEqual(tree_snapshot(self.root),before)
    def test_apply_without_stage(self):
        before=tree_snapshot(self.root)
        with self.assertRaisesRegex(pkg.Refusal,'STAGE_REQUIRED'):lab.apply(P,str(self.root))
        self.assertEqual(tree_snapshot(self.root),before)
    def test_unknown_preexisting_image_refused(self):
        (self.root/'image').mkdir(mode=0o700);before=tree_snapshot(self.root)
        with self.assertRaisesRegex(pkg.Refusal,'LAB_NOT_EMPTY'):lab.stage(P,str(self.root))
        self.assertEqual(tree_snapshot(self.root),before)
    def test_staged_symlink_refused(self):
        lab.stage(P,str(self.root));file=self.root/'.stage/product/tools/agentctl.py'
        file.unlink();file.symlink_to('/etc/passwd')
        with self.assertRaises(pkg.Refusal):lab.apply(P,str(self.root))
        self.assertFalse((self.root/'.stage/state').exists())
    def test_source_tamper_not_hidden_by_verified_receipt(self):
        self.install();file=self.root/'image/product/tools/agentctl.py'
        file.chmod(0o644);file.write_bytes(b'# tampered\n');file.chmod(0o444)
        with self.assertRaisesRegex(pkg.Refusal,'SOURCE_MISMATCH'):lab.verify(P,str(self.root))
    def test_installed_unknown_file_refused(self):
        self.install();(self.root/'image/product/tools/extra.py').write_bytes(b'x')
        with self.assertRaisesRegex(pkg.Refusal,'INVENTORY'):lab.verify(P,str(self.root))
    def test_installed_hardlink_refused(self):
        self.install();file=self.root/'image/product/tools/agentctl.py'
        os.link(file,WORKSPACE/('hard-'+self.root.name))
        with self.assertRaisesRegex(pkg.Refusal,'NONREGULAR'):lab.verify(P,str(self.root))
    def test_installed_mode_tamper_refused(self):
        self.install();(self.root/'image/product/tools/agentctl.py').chmod(0o666)
        with self.assertRaisesRegex(pkg.Refusal,'INVENTORY'):lab.verify(P,str(self.root))
    def test_v1_schema_refuses_automatic_migration(self):
        self.install()
        with sqlite3.connect(self.db()) as c:c.execute('PRAGMA user_version=1')
        original=self.db().read_bytes()
        with self.assertRaisesRegex(pkg.Refusal,'VERSION'):lab.apply(P,str(self.root))
        self.assertEqual(self.db().read_bytes(),original)
    def test_database_schema_tamper(self):
        self.install()
        with sqlite3.connect(self.db()) as c:c.execute('CREATE TABLE foreign_table (x TEXT)')
        with self.assertRaisesRegex(pkg.Refusal,'SCHEMA'):lab.verify(P,str(self.root))
    def test_wal_artifact_refused(self):
        self.install();Path(str(self.db())+'-wal').write_bytes(b'fake')
        with self.assertRaisesRegex(pkg.Refusal,'INVENTORY'):lab.verify(P,str(self.root))
    def test_database_truncated(self):
        self.install();self.db().write_bytes(b'not sqlite')
        with self.assertRaisesRegex(pkg.Refusal,'INVALID_OR_WAL'):lab.verify(P,str(self.root))
    def test_rollback_retains_identical_database(self):
        self.install();data=self.db().read_bytes();r=lab.rollback(P,str(self.root))
        self.assertEqual(r['files_deleted'],0);self.assertFalse((self.root/'image').exists())
        self.assertEqual((self.root/'retained-image/state/cherub-state.sqlite3').read_bytes(),data)
        self.assertEqual(lab.status(P,str(self.root))['result'],'ROLLED_BACK_STATE_RETAINED')
    def test_rollback_repeat_no_writes(self):
        self.install();lab.rollback(P,str(self.root));before=tree_snapshot(self.root)
        self.assertEqual(lab.rollback(P,str(self.root))['result'],'ROLLED_BACK_IDEMPOTENT')
        self.assertEqual(tree_snapshot(self.root),before)
    def test_nonempty_state_preserved_and_rollback_refused(self):
        self.install()
        with sqlite3.connect(self.db()) as c:c.execute('INSERT INTO projects VALUES (?,?,?,?)',('test',1,'p','m'))
        before=tree_snapshot(self.root)
        with self.assertRaisesRegex(pkg.Refusal,'STATE_IN_USE'):lab.rollback(P,str(self.root))
        self.assertEqual(tree_snapshot(self.root),before)
    def test_active_db_writer_refused(self):
        self.install();fd=os.open(self.db(),os.O_RDONLY)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):lab.rollback(P,str(self.root))
        finally:os.close(fd)
        self.assertTrue((self.root/'image').exists())
    def test_second_install_writer_refused(self):
        with Root(str(self.root),exclusive=True):
            with self.assertRaises(BlockingIOError):lab.stage(P,str(self.root))
    def test_process_crash_during_stage_abort_no_deletion(self):
        self.crash('after_file_agentctl.py','stage')
        data=(self.root/'.stage/product/tools/agentctl.py').read_bytes()
        with self.assertRaises(pkg.Refusal):lab.stage(P,str(self.root))
        r=lab.recover(P,str(self.root),'abort-stage')
        self.assertEqual(r['files_deleted'],0)
        self.assertEqual((self.root/'retained-partial/product/tools/agentctl.py').read_bytes(),data)
    def test_process_crash_after_database_no_auto_retry(self):
        lab.stage(P,str(self.root));self.crash('after_database','apply')
        path=self.root/'.stage/state/cherub-state.sqlite3';data=path.read_bytes()
        with self.assertRaises(pkg.Refusal):lab.apply(P,str(self.root))
        lab.recover(P,str(self.root),'abort-stage')
        self.assertEqual((self.root/'retained-partial/state/cherub-state.sqlite3').read_bytes(),data)
    def test_process_crash_after_publish_recovery_no_recreate(self):
        lab.stage(P,str(self.root));self.crash('after_publish','apply');data=self.db().read_bytes()
        r=lab.recover(P,str(self.root),'complete-image')
        self.assertEqual(r['result'],'RECOVERED_VERIFIED_WITHOUT_RERUN')
        self.assertEqual(self.db().read_bytes(),data)
        self.assertEqual(lab.status(P,str(self.root))['result'],'VERIFIED_LAB_ONLY')
    def test_process_crash_record_commit_recovered(self):
        lab.stage(P,str(self.root));self.crash('before_record_VERIFIED','apply');data=self.db().read_bytes()
        self.assertTrue((self.root/'.next-record').exists())
        lab.recover(P,str(self.root),'complete-image')
        self.assertFalse((self.root/'.next-record').exists())
        self.assertEqual(self.db().read_bytes(),data)
    def test_process_crash_rollback_recovered(self):
        self.install();data=self.db().read_bytes();self.crash('after_rollback_move','rollback')
        r=lab.recover(P,str(self.root),'complete-rollback')
        self.assertEqual(r['result'],'RECOVERED_ROLLBACK_STATE_RETAINED')
        self.assertEqual((self.root/'retained-image/state/cherub-state.sqlite3').read_bytes(),data)
    def test_abort_does_not_remove_installed_image(self):
        self.install();before=tree_snapshot(self.root)
        with self.assertRaises(pkg.Refusal):lab.recover(P,str(self.root),'abort-stage')
        self.assertEqual(tree_snapshot(self.root),before)
    def test_no_outside_target_mutation(self):
        sentinel=WORKSPACE/('sentinel-'+self.root.name);sentinel.write_bytes(b'preserve')
        old=sentinel.stat();self.install();lab.rollback(P,str(self.root))
        self.assertEqual(sentinel.read_bytes(),b'preserve')
        self.assertEqual(old.st_mtime_ns,sentinel.stat().st_mtime_ns)
    def test_real_cli_plan_and_missing_write_flag(self):
        cmd=[sys.executable,'-I','-B',str(BASE/'installer/eta_i3_lab.py')]
        args=['--package',str(PACKAGE),'--sha256',PIN,'--lab-root',str(self.root)]
        r=subprocess.run(cmd+['plan']+args,capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(r.stdout)['result'],'PLANNED_NO_WRITES')
        r=subprocess.run(cmd+['stage']+args,capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,2)
        self.assertFalse((self.root/'.stage').exists())

class Result(unittest.TextTestResult):
    records=[]
    def addSuccess(self,test):super().addSuccess(test);self.records.append({'test':test.id(),'status':'PASS'})
    def addFailure(self,test,err):super().addFailure(test,err);self.records.append({'test':test.id(),'status':'FAIL','detail':self._exc_info_to_string(err,test)})
    def addError(self,test,err):super().addError(test,err);self.records.append({'test':test.id(),'status':'ERROR','detail':self._exc_info_to_string(err,test)})

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--crash-worker':
        _,_,root,event,operation=sys.argv
        def fault(point):
            if point==event:os._exit(86)
        getattr(lab,operation)(P,root,fault=fault)
        raise SystemExit('DID_NOT_REACH_CRASH_POINT')
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(InstallTests)
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
    output={'scope':'M0_M1_OFFHOST_LINUX_DISPOSABLE_ROOT', 'uid':os.getuid(),
            'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),
            'records':r.records,'package_sha256':PIN,'sqlite':sqlite3.sqlite_version,
            'native_freebsd':'NOT_TESTED','independent_reviews':'NOT_PERFORMED'}
    (WORKSPACE/'INSTALL_TEST_RESULTS.json').write_text(json.dumps(output,indent=2)+'\n')
    raise SystemExit(0 if r.wasSuccessful() else 1)
