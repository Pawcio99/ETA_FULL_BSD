#!/usr/bin/env python3
"""Filesystem engine acceptance on disposable image, plus native-gate contract tests.
This suite never selects / as an installation target. Native execution NOT TESTED.
"""
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

BASE=Path(__file__).resolve().parents[1]
SCRIPT=BASE/'installer/eta_system_install.py'
spec=importlib.util.spec_from_file_location('sysinstaller',SCRIPT)
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
PACKAGE=BASE/'packages/ETA_W09_STATELOCK_CORE_R5.zip'
P=s.Package(PACKAGE.read_bytes())
TOOL=s.sha(SCRIPT.read_bytes())
WORK=Path(os.environ.get('ETA_SYS_TEST_ROOT',tempfile.gettempdir()))


def snapshot(root):
    out={}
    for p in sorted(root.rglob('*')):
        st=p.lstat()
        out[str(p.relative_to(root))]={'mode':st.st_mode,'uid':st.st_uid,'gid':st.st_gid,
            'inode':st.st_ino,'size':st.st_size,'mtime':st.st_mtime_ns,
            'data':s.sha(p.read_bytes()) if p.is_file() and not p.is_symlink() else None}
    return out

def target(root):
    return {'kind':'OFFHOST_FIXTURE_NOT_NATIVE','userland':'SIMULATED','kernel':'TEST',
            'hostuuid':'fixture','machine':'amd64','boot':'TEST_BOOT','hostname':'TEST',
            'root_identity':s.identity(root.stat())}

def engine(root,fault=lambda _:None):
    fs=s.Tree(str(root),os.geteuid(),lambda fd:None)
    return s.Engine(fs,P,target(root),TOOL,fault)

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='eta-system-test-',dir=WORK)
        self.root=Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        for p in ('usr/local/libexec/eta-cherub-full/product','var/db/eta-cherub-full/state'):
            (self.root/p).mkdir(parents=True,mode=0o700)
        self.active=self.root/'usr/local/libexec/eta-cherub-full/product/ACTIVE_SENTINEL'
        self.active.write_bytes(b'EXISTING_ACTIVE_PRODUCT_DO_NOT_TOUCH\n')
        self.old_db=self.root/'var/db/eta-cherub-full/state/OLD_V1_SENTINEL'
        self.old_db.write_bytes(b'OLD_PRIVATE_RUNTIME_STORE\n')
        self.e=engine(self.root);self.addCleanup(self.e.fs.close)
    def install(self):
        p=self.e.plan()
        result=self.e.install(p['plan_sha256'])
        self.assertEqual(result['result'],'VERIFIED_INSTALLED_INACTIVE_CORE')
        return result
    def db(self):return self.root/s.DATABASE
    def crash(self,event):
        r=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).resolve()),
            '--crash',str(self.root),event],capture_output=True,text=True,timeout=12)
        self.assertEqual(r.returncode,86,r.stdout+r.stderr)
        self.assertEqual(self.e.status()['result'],'RECOVERY_REQUIRED')
    def test_payload_pin_exact(self):
        self.assertEqual(s.sha(PACKAGE.read_bytes()),s.PAYLOAD_SHA)
        self.assertEqual(set(P.payload),set(s.PINS))
    def test_payload_mutation_rejected(self):
        with self.assertRaisesRegex(s.Blocked,'SHA256'):s.Package(PACKAGE.read_bytes()+b'wrong')
    def test_invalid_zip_rejected_before_parsing(self):
        with self.assertRaises(s.Blocked):s.Package(b'no zip')
    def test_duplicate_json_rejected(self):
        with self.assertRaises(s.Blocked):s.unique_json(b'{"k":1,"k":2}')
    def test_plan_no_writes(self):
        before=snapshot(self.root);p=self.e.plan()
        self.assertFalse(p['plan']['will_activate'])
        self.assertFalse(p['plan']['will_migrate_state'])
        self.assertEqual(snapshot(self.root),before)
    def test_plan_deterministic(self):self.assertEqual(self.e.plan(),self.e.plan())
    def test_wrong_confirmation_no_writes(self):
        before=snapshot(self.root)
        with self.assertRaisesRegex(s.Blocked,'CONFIRMED'):self.e.install('0'*64)
        self.assertEqual(snapshot(self.root),before)
    def test_plan_stale_new_directory(self):
        p=self.e.plan();(self.root/s.RELEASES).mkdir()
        before=snapshot(self.root)
        with self.assertRaisesRegex(s.Blocked,'STALE'):self.e.install(p['plan_sha256'])
        self.assertEqual(snapshot(self.root),before)
    def test_plan_stale_boot_identity(self):
        p=self.e.plan();self.e.target['boot']='other'
        with self.assertRaisesRegex(s.Blocked,'STALE'):self.e.install(p['plan_sha256'])
    def test_valid_install_files_and_schema(self):
        r=self.install()
        self.assertEqual(r['code']['source_files'],5)
        self.assertEqual(set(r['state']['rows'].values()),{0})
        self.assertEqual(r['state']['user_version'],2)
        for n,h in s.PINS.items():
            p=self.root/s.FINAL/'product/tools'/n
            self.assertEqual(s.sha(p.read_bytes()),h)
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o444)
    def test_old_active_code_and_state_untouched(self):
        before=(self.active.read_bytes(),self.active.stat(),self.old_db.read_bytes(),self.old_db.stat())
        self.install();plan=self.e.plan('withdraw');self.e.withdraw(plan['plan_sha256'])
        self.assertEqual(self.active.read_bytes(),before[0]);self.assertEqual(self.active.stat(),before[1])
        self.assertEqual(self.old_db.read_bytes(),before[2]);self.assertEqual(self.old_db.stat(),before[3])
    def test_repeat_install_is_noop(self):
        self.install();before=snapshot(self.root)
        result=self.e.install(self.e.plan()['plan_sha256'])
        self.assertEqual(result['result'],'ALREADY_INSTALLED_NO_WRITES')
        self.assertEqual(snapshot(self.root),before)
    def test_verify_and_status_no_writes(self):
        self.install();before=snapshot(self.root)
        self.assertEqual(self.e.verify()['result'],'VERIFIED_INSTALLED_INACTIVE_CORE')
        self.e.status();self.assertEqual(snapshot(self.root),before)
    def test_existing_unmanaged_release_not_overwritten(self):
        (self.root/s.FINAL).mkdir(parents=True)
        (self.root/s.FINAL/'foreign').write_bytes(b'x')
        before=snapshot(self.root)
        with self.assertRaisesRegex(s.Blocked,'COLLISION'):self.e.plan()
        self.assertEqual(snapshot(self.root),before)
    def test_symlink_ancestor_rejected(self):
        p=self.root/'usr/local/libexec/eta-cherub-full'
        moved=self.root/'existing';p.rename(moved);p.symlink_to(moved)
        before=snapshot(self.root)
        with self.assertRaises(OSError):self.e.plan()
        self.assertEqual(snapshot(self.root),before)
    def test_symlink_destination_rejected(self):
        (self.root/s.RELEASES).mkdir()
        (self.root/s.FINAL).symlink_to(self.root/'var/db')
        with self.assertRaisesRegex(s.Blocked,'SYMLINK'):self.e.plan()
    def test_group_writable_ancestor_refused(self):
        d=self.root/'usr/local';d.chmod(0o775)
        with self.assertRaisesRegex(s.Blocked,'UNSAFE'):self.e.plan()
    def test_extended_acl_boundary_refusal(self):
        self.e.fs.acl=lambda fd: s.need(False,'NONTRIVIAL_ACL_REQUIRES_REVIEW')
        with self.assertRaisesRegex(s.Blocked,'ACL'):self.e.plan()
    def test_no_permission_downgrade_of_existing_dirs(self):
        d=self.root/'usr/local/libexec/eta-cherub-full';d.chmod(0o750)
        self.install();self.assertEqual(stat.S_IMODE(d.stat().st_mode),0o750)
    def test_hardlinked_code_refused(self):
        self.install();p=self.root/s.FINAL/'product/tools/agentctl.py'
        os.link(p,self.root/'extra-link')
        with self.assertRaisesRegex(s.Blocked,'HARDLINK'):self.e.verify()
    def test_code_mutation_refused(self):
        self.install();p=self.root/s.FINAL/'product/tools/agentctl.py'
        p.chmod(0o600);p.write_bytes(b'bad');p.chmod(0o444)
        with self.assertRaisesRegex(s.Blocked,'HASH'):self.e.verify()
    def test_code_mode_mutation_refused(self):
        self.install();p=self.root/s.FINAL/'product/tools/agentctl.py';p.chmod(0o644)
        with self.assertRaisesRegex(s.Blocked,'HASH'):self.e.verify()
    def test_extra_file_refused(self):
        self.install();(self.root/s.FINAL/'extra').write_bytes(b'x')
        with self.assertRaisesRegex(s.Blocked,'HASH'):self.e.verify()
    def test_fifo_not_opened(self):
        self.install();os.mkfifo(self.root/s.FINAL/'fifo',0o600)
        with self.assertRaisesRegex(s.Blocked,'SPECIAL'):self.e.verify()
    def test_state_mode_mutation_refused(self):
        self.install();self.db().chmod(0o640)
        with self.assertRaisesRegex(s.Blocked,'MODE'):self.e.verify()
    def test_state_symlink_refused(self):
        self.install();data=self.db().read_bytes();self.db().unlink()
        elsewhere=self.root/'db-elsewhere';elsewhere.write_bytes(data);self.db().symlink_to(elsewhere)
        with self.assertRaises(OSError):self.e.verify()
    def test_state_v1_no_migration(self):
        self.install()
        with sqlite3.connect(self.db()) as db:db.execute('PRAGMA user_version=1')
        before=self.db().read_bytes()
        with self.assertRaisesRegex(s.Blocked,'NO_MIGRATION'):self.e.verify()
        self.assertEqual(self.db().read_bytes(),before)
    def test_state_schema_mutation(self):
        self.install()
        with sqlite3.connect(self.db()) as db:db.execute('CREATE TABLE foreign_table (x TEXT)')
        with self.assertRaisesRegex(s.Blocked,'SCHEMA'):self.e.verify()
    def test_state_wal_refused(self):
        self.install();Path(str(self.db())+'-wal').write_bytes(b'x')
        with self.assertRaisesRegex(s.Blocked,'WAL'):self.e.verify()
    def test_nonempty_state_blocks_withdraw(self):
        self.install()
        with sqlite3.connect(self.db()) as db:db.execute('INSERT INTO projects VALUES (?,?,?,?)',('x',1,'p','m'))
        before=snapshot(self.root)
        with self.assertRaisesRegex(s.Blocked,'STATE_IN_USE'):self.e.plan('withdraw')
        self.assertEqual(snapshot(self.root),before)
    def test_state_directory_mode_mismatch(self):
        self.install();self.db().parent.chmod(0o755)
        with self.assertRaisesRegex(s.Blocked,'MODE'):self.e.verify()
    def test_control_directory_mode_mismatch(self):
        self.install();(self.root/s.TX).chmod(0o755)
        with self.assertRaisesRegex(s.Blocked,'MODE'):self.e.status()
    def test_partial_event_blocks_recovery(self):
        self.crash('event_STAGED')
        path=self.root/s.TX/'events/000004.json';path.write_bytes(b'{');path.chmod(0o444)
        with self.assertRaises((ValueError,s.Blocked)):self.e.plan('abort')
    def test_plan_lists_control_and_temporary_files(self):
        p=self.e.plan()['plan']
        self.assertEqual(len(p['control_files']),2)
        self.assertEqual(len(p['initial_event_files']),6)
        self.assertIn('/'+s.DATABASE+'-journal',p['sqlite_transient_files'])
    def test_actual_stateledger_opens_fresh_database(self):
        self.install()
        p=self.root/s.FINAL/'product/tools/cherub_state.py'
        sp=importlib.util.spec_from_file_location('real_state_for_install',p)
        m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
        with m.StateLedger(self.db().parent,create=False) as ledger:
            self.assertIsNotNone(ledger)
        self.e.verify()
    def test_second_installer_writer_blocked(self):
        with self.e.fs.lock(write=True,create=True):
            with self.assertRaises(BlockingIOError):self.e.plan()
    def test_database_writer_blocks_verify_and_withdraw(self):
        self.install()
        writer=sqlite3.connect(self.db(),timeout=0,isolation_level=None)
        try:
            writer.execute('BEGIN EXCLUSIVE')
            with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):
                self.e.verify()
            with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):
                self.e.plan('withdraw')
        finally:
            writer.execute('ROLLBACK');writer.close()
    def test_no_flock_on_database_fd_during_install_and_withdraw(self):
        import fcntl
        true_flock=fcntl.flock
        checked={'calls':0}
        def guarded(fd,operation):
            if self.db().exists():
                a=os.fstat(fd); b=self.db().stat()
                self.assertNotEqual((a.st_dev,a.st_ino),(b.st_dev,b.st_ino),
                                    'P1: flock used on SQLite database file')
            checked['calls']+=1
            return true_flock(fd,operation)
        with patch.object(s.fcntl,'flock',side_effect=guarded):
            self.install()
            self.e.withdraw(self.e.plan('withdraw')['plan_sha256'])
        self.assertGreater(checked['calls'],0)
    def test_sqlite_exclusive_lease_rejects_external_writer(self):
        self.install()
        with self.e.database_lock(exclusive=True) as lease:
            self.e.database_verify(lease)
            competing=sqlite3.connect(self.db(),timeout=0,isolation_level=None)
            try:
                with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):
                    competing.execute('BEGIN IMMEDIATE')
            finally:
                competing.close()
        after=sqlite3.connect(self.db(),timeout=0,isolation_level=None)
        try:
            after.execute('BEGIN IMMEDIATE'); after.execute('ROLLBACK')
        finally:
            after.close()
    def _external_exclusive_writer(self):
        """Separate Python process: SQLite BEGIN EXCLUSIVE, never flock."""
        return subprocess.run([sys.executable, '-I', '-B', '-c',
            "import sqlite3,sys; db=sqlite3.connect(sys.argv[1],timeout=0,"
            "isolation_level=None); db.execute('BEGIN EXCLUSIVE'); "
            "print('EXCLUSIVE_ACQUIRED'); db.execute('ROLLBACK'); db.close()",
            str(self.db())], capture_output=True, text=True, timeout=10)
    def _assert_sqlite_exclusive_not_acquired(self):
        contender=self._external_exclusive_writer()
        self.assertNotEqual(contender.returncode,0,
            'P1: second process acquired an EXCLUSIVE DB lock while installer owns lease')
        self.assertIn('locked',contender.stderr.lower())
    def test_r4_p1_db_verify_does_not_drop_sqlite_kernel_lock(self):
        """Specifically reproduces R3's close-induced lock loss."""
        self.install()
        with self.e.database_lock(exclusive=True) as lease:
            self.e.database_verify(lease)
            self._assert_sqlite_exclusive_not_acquired()
            self.e.database_verify(lease)
            self._assert_sqlite_exclusive_not_acquired()
        contender=self._external_exclusive_writer()
        self.assertEqual(contender.returncode,0,contender.stderr)
        self.assertEqual(contender.stdout.strip(),'EXCLUSIVE_ACQUIRED')
    def test_r4_p1_withdraw_retains_sqlite_lock_through_rename(self):
        self.install()
        plan=self.e.plan('withdraw')
        move=self.e.fs.move
        def verify_lock_before_move(source,destination):
            if source==s.FINAL:
                self._assert_sqlite_exclusive_not_acquired()
            return move(source,destination)
        with patch.object(self.e.fs,'move',side_effect=verify_lock_before_move):
            self.e.withdraw(plan['plan_sha256'])
        self.assertEqual(self.e.status()['result'],'WITHDRAWN_DATA_RETAINED')
        self.assertEqual(self._external_exclusive_writer().returncode,0)
    def test_r4_p1_abort_retains_sqlite_lock_through_rename(self):
        self.crash('after_database')
        plan=self.e.plan('abort')
        move=self.e.fs.move
        def verify_lock_before_move(source,destination):
            if source==s.STAGE:
                self._assert_sqlite_exclusive_not_acquired()
            return move(source,destination)
        with patch.object(self.e.fs,'move',side_effect=verify_lock_before_move):
            self.e.recover('abort',plan['plan_sha256'])
        self.assertEqual(self.e.status()['result'],'WITHDRAWN_INCOMPLETE_DATA_RETAINED')
        self.assertEqual(self._external_exclusive_writer().returncode,0)
    def test_sqlite_exclusive_lease_is_not_a_database_mutation(self):
        self.install();before=snapshot(self.root)
        with self.e.database_lock(exclusive=True) as lease:
            self.e.database_verify(lease)
        self.assertEqual(snapshot(self.root),before)
    def test_rollback_retains_identical_db(self):
        self.install();before=self.db().read_bytes()
        r=self.e.withdraw(self.e.plan('withdraw')['plan_sha256'])
        self.assertEqual(r['files_deleted'],0);self.assertEqual(self.db().read_bytes(),before)
        self.assertFalse((self.root/s.FINAL).exists())
        self.assertTrue((self.root/s.WITHDRAWN).is_dir())
        self.assertEqual(self.e.status()['result'],'WITHDRAWN_DATA_RETAINED')
    def test_repeat_rollback_noop(self):
        self.install();self.e.withdraw(self.e.plan('withdraw')['plan_sha256']);before=snapshot(self.root)
        r=self.e.withdraw(self.e.plan('withdraw')['plan_sha256'])
        self.assertEqual(r['result'],'ALREADY_WITHDRAWN_NO_WRITES')
        self.assertEqual(snapshot(self.root),before)
    def test_rollback_stale_plan_refused(self):
        self.install();p=self.e.plan('withdraw');self.e.target['boot']='next'
        with self.assertRaisesRegex(s.Blocked,'STALE'):self.e.withdraw(p['plan_sha256'])
    def test_journal_corruption_blocks(self):
        self.install();p=next((self.root/s.TX/'events').glob('*.json'))
        p.chmod(0o600);p.write_bytes(b'partial');p.chmod(0o444)
        with self.assertRaises((ValueError,s.Blocked)):self.e.status()
    def test_journal_gap_blocks(self):
        self.install();p=self.root/s.TX/'events/000002.json';p.unlink()
        with self.assertRaisesRegex(s.Blocked,'JOURNAL_GAP'):self.e.status()
    def test_foreign_target_binding_refused(self):
        self.install();self.e.target['hostuuid']='different-machine'
        with self.assertRaisesRegex(s.Blocked,'BINDING'):self.e.status()
    def test_crash_mid_code_then_abort_retains_partial(self):
        self.crash('file_agentctl.py')
        with self.assertRaisesRegex(s.Blocked,'RECOVERY'):self.e.plan()
        before=(self.root/s.STAGE/'product/tools/agentctl.py').read_bytes()
        self.e.recover('abort',self.e.plan('abort')['plan_sha256'])
        self.assertEqual((self.root/s.WITHDRAWN/'product/tools/agentctl.py').read_bytes(),before)
        self.assertEqual(self.e.status()['result'],'WITHDRAWN_INCOMPLETE_DATA_RETAINED')
    def test_crash_empty_db_not_recreated(self):
        self.crash('empty_database');self.assertEqual(self.db().stat().st_size,0)
        before=snapshot(self.root)
        with self.assertRaisesRegex(s.Blocked,'STATE_INVALID'):
            self.e.plan('complete')
        # P2: A partial DB cannot be proven unused: preserve everything and refuse.
        with self.assertRaisesRegex(s.Blocked,'STATE_INVALID'):
            self.e.plan('abort')
        self.assertEqual(self.db().stat().st_size,0)
        self.assertEqual(snapshot(self.root),before)
    def test_external_process_sqlite_writer_blocks_withdraw(self):
        self.install()
        worker=subprocess.Popen([sys.executable,'-I','-B','-c',
            "import sqlite3,sys;db=sqlite3.connect(sys.argv[1],timeout=0,isolation_level=None);"
            "db.execute('BEGIN EXCLUSIVE');print('LOCKED',flush=True);sys.stdin.readline();"
            "db.execute('ROLLBACK');db.close()", str(self.db())],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            self.assertEqual(worker.stdout.readline().strip(),'LOCKED')
            before=snapshot(self.root)
            with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):
                self.e.plan('withdraw')
            self.assertEqual(snapshot(self.root),before)
        finally:
            if worker.poll() is None:
                worker.stdin.write('release\n'); worker.stdin.flush()
            stdout,stderr=worker.communicate(timeout=8)
        self.assertEqual(worker.returncode,0,stderr)
    def test_abort_plan_includes_database_identity(self):
        self.crash('after_database')
        plan=self.e.plan('abort')
        self.assertIn(s.DATABASE,plan['plan']['anchors_and_destinations'])
        self.assertIsNotNone(plan['plan']['anchors_and_destinations'][s.DATABASE])
    def test_abort_after_committed_database_requires_valid_unused_state(self):
        self.crash('after_database')
        before=self.db().read_bytes()
        plan=self.e.plan('abort')
        self.assertEqual(plan['plan']['state_observation']['rows'],
                         {k:0 for k in s.TABLES})
        result=self.e.recover('abort',plan['plan_sha256'])
        self.assertEqual(result['result'],'ABORTED_PARTIAL_DATA_RETAINED')
        self.assertEqual(self.db().read_bytes(),before)
        self.assertEqual(self.e.status()['result'],'WITHDRAWN_INCOMPLETE_DATA_RETAINED')
    def test_abort_after_committed_db_nonempty_refused(self):
        self.crash('after_database')
        with sqlite3.connect(self.db()) as db:
            db.execute('INSERT INTO projects VALUES (?,?,?,?)',('x',1,'p','m'))
        before=snapshot(self.root)
        with self.assertRaisesRegex(s.Blocked,'STATE_IN_USE'):
            self.e.plan('abort')
        self.assertEqual(snapshot(self.root),before)
    def test_abort_with_writer_started_after_plan_is_refused(self):
        self.crash('after_database')
        plan=self.e.plan('abort')
        writer=sqlite3.connect(self.db(),timeout=0,isolation_level=None)
        try:
            writer.execute('BEGIN EXCLUSIVE')
            before=snapshot(self.root)
            with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):
                self.e.recover('abort',plan['plan_sha256'])
            self.assertEqual(snapshot(self.root),before)
        finally:
            writer.execute('ROLLBACK');writer.close()
    def test_abort_after_plan_if_db_became_nonempty_refused(self):
        self.crash('after_database')
        plan=self.e.plan('abort')
        with sqlite3.connect(self.db()) as db:
            db.execute('INSERT INTO projects VALUES (?,?,?,?)',('x',1,'p','m'))
        before=snapshot(self.root)
        with self.assertRaises((s.Blocked,sqlite3.OperationalError)):
            self.e.recover('abort',plan['plan_sha256'])
        self.assertEqual(snapshot(self.root),before)
    def test_abort_after_staged_journal_with_missing_db_is_non_destructive(self):
        self.crash('after_database')
        self.db().unlink()
        with self.assertRaisesRegex(s.Blocked,'STATE_EXTRA_FILES_OR_WAL'):
            self.e.plan('complete')
        before=snapshot(self.root)
        # Completed-schema bytes were lost. No dangerous attempt to recreate.
        # Operator must retain the partially staged code for separate recovery.
        with self.assertRaises((s.Blocked,OSError)):
            self.e.plan('abort')
        self.assertEqual(snapshot(self.root),before)
    def test_staged_event_without_db_refuses_automatic_abort(self):
        self.crash('event_STAGED')
        self.assertFalse(self.db().exists())
        before=snapshot(self.root)
        with self.assertRaisesRegex(s.Blocked,'STATE_FILE_MISSING_OR_UNCERTAIN'):
            self.e.plan('abort')
        self.assertEqual(snapshot(self.root),before)
    def test_crash_after_db_complete_no_reinit(self):
        self.crash('after_database');before=self.db().read_bytes()
        r=self.e.recover('complete',self.e.plan('complete')['plan_sha256'])
        self.assertEqual(r['result'],'RECOVERED_NO_REEXECUTION')
        self.assertEqual(self.db().read_bytes(),before)
    def test_crash_after_publish(self):
        self.crash('after_publish');before=self.db().read_bytes()
        self.e.recover('complete',self.e.plan('complete')['plan_sha256'])
        self.assertEqual(self.db().read_bytes(),before);self.e.verify()
    def test_crash_after_published_event(self):
        self.crash('event_PUBLISHED')
        self.e.recover('complete',self.e.plan('complete')['plan_sha256']);self.e.verify()
    def _competing_sidecar_and_sqlite_process(self):
        """A real separate process obeying the StateLedger sidecar contract.

        Exit 3 = refused by flock; exit 4 = flock acquired, but SQLite busy;
        exit 0 = unsafe full takeover during claimed recovery ownership.
        """
        code = """import fcntl, os, sqlite3, sys
fd = os.open(sys.argv[1], os.O_RDWR | os.O_NOFOLLOW)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print('SIDECAR_DENIED')
    sys.exit(3)
db = sqlite3.connect(sys.argv[2], timeout=0, isolation_level=None)
try:
    db.execute('BEGIN IMMEDIATE')
except sqlite3.OperationalError:
    print('SQLITE_DENIED')
    sys.exit(4)
print('WRITER_ACQUIRED')
db.execute('ROLLBACK')
db.close()
os.close(fd)
"""
        return subprocess.run([sys.executable,'-I','-B','-c',code,
                  str(self.root/s.DBLOCK),str(self.db())],
                  capture_output=True,text=True,timeout=10)
    def test_r6_complete_recovery_keeps_sidecar_until_final_event(self):
        self.crash('after_database')
        plan=self.e.plan('complete')
        original=self.e.event
        seen=[]
        def check_at_event(state):
            if state=='VERIFIED_INACTIVE':
                contender=self._competing_sidecar_and_sqlite_process()
                seen.append((contender.returncode,contender.stdout.strip()))
                self.assertEqual(contender.returncode,3,contender.stderr)
                self.assertEqual(contender.stdout.strip(),'SIDECAR_DENIED')
            original(state)
        with patch.object(self.e,'event',side_effect=check_at_event):
            result=self.e.recover('complete',plan['plan_sha256'])
        self.assertEqual(result['result'],'RECOVERED_NO_REEXECUTION')
        self.assertEqual(seen,[(3,'SIDECAR_DENIED')])
        self.assertEqual(self._competing_sidecar_and_sqlite_process().returncode,0)
    def test_r6_withdrawal_recovery_keeps_sidecar_until_final_event(self):
        self.install()
        self.crash('after_withdraw')
        plan=self.e.plan('complete-withdrawal')
        original=self.e.event
        seen=[]
        def check_at_event(state):
            if state=='WITHDRAWN':
                contender=self._competing_sidecar_and_sqlite_process()
                seen.append((contender.returncode,contender.stdout.strip()))
                self.assertEqual(contender.returncode,3,contender.stderr)
                self.assertEqual(contender.stdout.strip(),'SIDECAR_DENIED')
            original(state)
        with patch.object(self.e,'event',side_effect=check_at_event):
            result=self.e.recover('complete-withdrawal',plan['plan_sha256'])
        self.assertEqual(result['result'],'RECOVERED_WITHDRAWAL_DATA_RETAINED')
        self.assertEqual(seen,[(3,'SIDECAR_DENIED')])
        self.assertEqual(self._competing_sidecar_and_sqlite_process().returncode,0)
    def test_r6_complete_recovery_refuses_changed_state_after_plan(self):
        self.crash('after_database')
        plan=self.e.plan('complete')
        with sqlite3.connect(self.db()) as conn:
            conn.execute('INSERT INTO projects VALUES (?,?,?,?)',('late',1,'p','m'))
        before=snapshot(self.root)
        with self.assertRaises(s.Blocked):
            self.e.recover('complete',plan['plan_sha256'])
        self.assertEqual(snapshot(self.root),before)
    def test_r6_withdrawal_recovery_refuses_active_writer(self):
        self.install()
        self.crash('after_withdraw')
        plan=self.e.plan('complete-withdrawal')
        contender=sqlite3.connect(self.db(),timeout=0,isolation_level=None)
        try:
            contender.execute('BEGIN EXCLUSIVE')
            before=snapshot(self.root)
            with self.assertRaises((sqlite3.OperationalError,BlockingIOError)):
                self.e.recover('complete-withdrawal',plan['plan_sha256'])
            self.assertEqual(snapshot(self.root),before)
        finally:
            contender.execute('ROLLBACK')
            contender.close()
    def test_crash_withdraw_recovery(self):
        self.install();before=self.db().read_bytes();self.crash('after_withdraw')
        self.e.recover('complete-withdrawal',self.e.plan('complete-withdrawal')['plan_sha256'])
        self.assertEqual(self.db().read_bytes(),before)
        self.assertEqual(self.e.status()['result'],'WITHDRAWN_DATA_RETAINED')
    def test_withdraw_destination_collision_no_overwrite(self):
        self.install();(self.root/s.WITHDRAWN).mkdir()
        before=snapshot(self.root)
        with self.assertRaisesRegex(s.Blocked,'COLLISION'):self.e.plan('withdraw')
        self.assertEqual(snapshot(self.root),before)
    def test_nonempty_db_before_confirm_refused(self):
        self.install();p=self.e.plan('withdraw')
        with sqlite3.connect(self.db()) as db:db.execute('INSERT INTO projects VALUES (?,?,?,?)',('x',1,'p','m'))
        with self.assertRaisesRegex(s.Blocked,'STATE_IN_USE'):self.e.withdraw(p['plan_sha256'])
    def test_status_absent_no_writes(self):
        before=snapshot(self.root);self.assertEqual(self.e.status()['result'],'ABSENT')
        self.assertEqual(before,snapshot(self.root))

class NativeGateTests(unittest.TestCase):
    def test_native_cli_on_linux_refuses_without_writes(self):
        r=subprocess.run([sys.executable,'-I','-B',str(SCRIPT),'install','--package',str(PACKAGE),
            '--allow-system-write','--confirm-plan','0'*64],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,20)
        self.assertIn('FREEBSD_15_1_REQUIRED',r.stderr)
    def test_no_cli_prefix_override_exists(self):
        r=subprocess.run([sys.executable,'-I','-B',str(SCRIPT),'plan','--package',str(PACKAGE),
            '--prefix','/tmp'],capture_output=True,text=True)
        self.assertEqual(r.returncode,2)
    def test_inspect_works_without_system_mutation(self):
        r=subprocess.run([sys.executable,'-I','-B',str(SCRIPT),'inspect','--package',str(PACKAGE)],
            capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0);self.assertEqual(json.loads(r.stdout)['result'],'PACKAGE_INTEGRITY_PASS')
    def test_isolation_flags_required(self):
        r=subprocess.run([sys.executable,'-B',str(SCRIPT),'inspect','--package',str(PACKAGE)],capture_output=True,text=True)
        self.assertEqual(r.returncode,20);self.assertIn('USE_PYTHON_I_B',r.stderr)
    def fake_native(self,userland='15.1-RELEASE-p6',machine='amd64',kernel='15.1-RELEASE-p6'):
        from types import SimpleNamespace
        def execute(argv,**kwargs):
            values={'/bin/freebsd-version':userland,'security.jail.jailed':'0',
                    'kern.hostuuid':'00000000-0000-0000-0000-000000000001','kern.boottime':'boot'}
            return SimpleNamespace(returncode=0,stdout=values.get(argv[-1],values.get(argv[0]))+'\n')
        return patch.multiple(s.sys,platform='freebsd15',version_info=(3,12,0)),patch.object(s.os,'uname',
               return_value=SimpleNamespace(sysname='FreeBSD',machine=machine,release=kernel,nodename='fixture')),\
               patch.object(s.subprocess,'run',side_effect=execute)
    def test_native_mutation_denied_without_root(self):
        with patch.object(s,'native_target',return_value={'kind':'SYNTHETIC_GATE_TEST'}),\
             patch.object(s.os,'getuid',return_value=65534),\
             patch.object(s.os,'geteuid',return_value=65534),\
             patch.object(s,'Tree') as target:
            rc=s.main(['install','--package',str(PACKAGE),'--allow-system-write','--confirm-plan','0'*64])
            self.assertEqual(rc,20);target.assert_not_called()
    def test_native_mutation_denied_without_explicit_flag(self):
        with patch.object(s,'native_target',return_value={'kind':'SYNTHETIC_GATE_TEST'}),\
             patch.object(s.os,'getuid',return_value=0),\
             patch.object(s.os,'geteuid',return_value=0),\
             patch.object(s,'Tree') as target:
            rc=s.main(['install','--package',str(PACKAGE),'--confirm-plan','0'*64])
            self.assertEqual(rc,20);target.assert_not_called()
    def test_native_python_version_refused(self):
        with patch.object(s.sys,'platform','freebsd15'),patch.object(s.sys,'version_info',(3,13,0)):
            with self.assertRaisesRegex(s.Blocked,'PYTHON_3_12'):s.native_target()
    def test_native_identity_contract_synthetic_positive(self):
        a,b,c=self.fake_native()
        with a,b,c:
            v=s.native_target();self.assertEqual(v['userland'],'15.1-RELEASE-p6')
    def test_native_identity_wrong_release(self):
        a,b,c=self.fake_native(userland='15.0-RELEASE')
        with a,b,c,self.assertRaisesRegex(s.Blocked,'USERLAND'):s.native_target()
    def test_native_identity_wrong_arch(self):
        a,b,c=self.fake_native(machine='arm64')
        with a,b,c,self.assertRaisesRegex(s.Blocked,'ARCH'):s.native_target()
    def test_native_identity_wrong_kernel(self):
        a,b,c=self.fake_native(kernel='15.1-STABLE')
        with a,b,c,self.assertRaisesRegex(s.Blocked,'KERNEL'):s.native_target()
    def test_native_identity_readonly_timeout(self):
        a,b,c=self.fake_native()
        with a,b,patch.object(s.subprocess,'run',side_effect=subprocess.TimeoutExpired('x',5)),\
                self.assertRaises(subprocess.TimeoutExpired):s.native_target()
    def test_acl_nontrivial_refused_mocked_libc(self):
        fake=MagicMock();fake.acl_get_fd_np.return_value=1
        def trivial(ptr,out):ctypes.cast(out,ctypes.POINTER(ctypes.c_int))[0]=0;return 0
        fake.acl_is_trivial_np.side_effect=trivial
        with patch.object(s.ctypes,'CDLL',return_value=fake):
            acl=s.NativeACL()
            with tempfile.TemporaryFile() as f,self.assertRaisesRegex(s.Blocked,'NONTRIVIAL'):acl(f.fileno())
        fake.acl_free.assert_called_once()
    def test_acl_error_not_ignored(self):
        fake=MagicMock()
        def get(*args):ctypes.set_errno(13);return None
        fake.acl_get_fd_np.side_effect=get
        with patch.object(s.ctypes,'CDLL',return_value=fake):
            acl=s.NativeACL()
            with tempfile.TemporaryFile() as f,self.assertRaisesRegex(s.Blocked,'ACL_READ_ERROR'):acl(f.fileno())
    def test_acl_unsupported_filesystem_contract(self):
        # A filesystem where every access ACL API is unsupported must NOT
        # be silently treated as having safe, empty/trivial ACLs.
        fake=MagicMock()
        def get(*args):ctypes.set_errno(s.errno.EOPNOTSUPP);return None
        fake.acl_get_fd_np.side_effect=get
        with patch.object(s.ctypes,'CDLL',return_value=fake):
            acl=s.NativeACL()
            with tempfile.TemporaryFile() as f, self.assertRaisesRegex(s.Blocked,'ACL_ACCESS_TYPES_UNSUPPORTED'):
                acl(f.fileno())
        self.assertEqual(fake.acl_get_fd_np.call_count,2)
    def test_acl_all_access_types_invalid_refused(self):
        fake=MagicMock()
        def get(*args):ctypes.set_errno(s.errno.EINVAL);return None
        fake.acl_get_fd_np.side_effect=get
        with patch.object(s.ctypes,'CDLL',return_value=fake):
            acl=s.NativeACL()
            with tempfile.TemporaryFile() as f, self.assertRaisesRegex(s.Blocked,'ACL_ACCESS_TYPES_UNSUPPORTED'):
                acl(f.fileno())
    def test_acl_default_only_does_not_prove_access(self):
        # An empty POSIX default ACL proves nothing about the access ACL.
        fake=MagicMock()
        def get(fd,kind):
            if kind==3: return 1
            ctypes.set_errno(s.errno.EOPNOTSUPP); return None
        fake.acl_get_fd_np.side_effect=get
        fake.acl_get_entry.return_value=0
        with patch.object(s.ctypes,'CDLL',return_value=fake):
            acl=s.NativeACL()
            with tempfile.TemporaryDirectory(prefix='eta-acl-') as path:
                fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
                try:
                    with self.assertRaisesRegex(s.Blocked,'ACL_ACCESS_TYPES_UNSUPPORTED'):
                        acl(fd)
                finally: os.close(fd)
        self.assertEqual(fake.acl_get_fd_np.call_count,3)
    def test_acl_access_fallback_trivial_pass(self):
        fake=MagicMock()
        def get(fd,kind):
            if kind==4:ctypes.set_errno(s.errno.EINVAL);return None
            return 1
        def trivial(ptr,out):ctypes.cast(out,ctypes.POINTER(ctypes.c_int))[0]=1;return 0
        fake.acl_get_fd_np.side_effect=get
        fake.acl_is_trivial_np.side_effect=trivial
        with patch.object(s.ctypes,'CDLL',return_value=fake):
            acl=s.NativeACL()
            with tempfile.TemporaryFile() as f:acl(f.fileno())
        self.assertEqual(fake.acl_get_fd_np.call_count,2)
    def test_default_acl_inheritance_refused_mocked(self):
        fake=MagicMock();fake.acl_get_fd_np.return_value=1
        def trivial(ptr,out):ctypes.cast(out,ctypes.POINTER(ctypes.c_int))[0]=1;return 0
        fake.acl_is_trivial_np.side_effect=trivial;fake.acl_get_entry.return_value=1
        with patch.object(s.ctypes,'CDLL',return_value=fake):
            acl=s.NativeACL();fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
            try:
                with self.assertRaisesRegex(s.Blocked,'DEFAULT_ACL'):acl(fd)
            finally:os.close(fd)
    def test_acl_trivial_allowed_mocked_libc(self):
        fake=MagicMock();fake.acl_get_fd_np.return_value=1
        def trivial(ptr,out):ctypes.cast(out,ctypes.POINTER(ctypes.c_int))[0]=1;return 0
        fake.acl_is_trivial_np.side_effect=trivial
        with patch.object(s.ctypes,'CDLL',return_value=fake):
            acl=s.NativeACL()
            with tempfile.TemporaryFile() as f:acl(f.fileno())
        self.assertEqual(fake.acl_free.call_count,2)

class Result(unittest.TextTestResult):
    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
    def addSuccess(self,t):super().addSuccess(t);self.rows.append({'test':t.id(),'status':'PASS'})
    def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'test':t.id(),'status':'FAIL','detail':self._exc_info_to_string(e,t)})
    def addError(self,t,e):super().addError(t,e);self.rows.append({'test':t.id(),'status':'ERROR','detail':self._exc_info_to_string(e,t)})

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--crash':
        root=Path(sys.argv[2]);event=sys.argv[3]
        def fault(point):
            if point==event:os._exit(86)
        e=engine(root,fault)
        if event=='after_withdraw':e.withdraw(e.plan('withdraw')['plan_sha256'])
        else:e.install(e.plan()['plan_sha256'])
        raise SystemExit(99)
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(InstallerTests),
                             unittest.defaultTestLoader.loadTestsFromTestCase(NativeGateTests)])
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
    report={'schema':'eta-system-installer-tests/1','methods':r.testsRun,
            'pass':len([x for x in r.rows if x['status']=='PASS']),'failures':len(r.failures),'errors':len(r.errors),
            'scope':'REAL_ENGINE_DISPOSABLE_IMAGE_AND_MOCKED_NATIVE_PREFLIGHT',
            'native_FreeBSD':'NOT_TESTED','native_ACL_libc':'NOT_TESTED_MOCKED_CONTRACT_ONLY',
            'process_crash_tests':7,'uid':os.getuid(),'gid':os.getgid(),'groups':os.getgroups(),
            'python':sys.version,'sqlite':sqlite3.sqlite_version,'script_sha256':TOOL,
            'payload_sha256':s.PAYLOAD_SHA,'records':r.rows}
    (WORK/'SYSTEM_INSTALLER_TESTS.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if r.wasSuccessful() else 1)
