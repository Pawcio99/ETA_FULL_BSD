#!/usr/bin/env python3
"""ETA FreeBSD system installer R1: pinned W09 core, fresh INACTIVE installation.

Native CLI: FreeBSD 15.1-RELEASE/amd64, Python 3.12, -I -B; mutation requires root
and a separately confirmed exact plan. No native bypass, root-prefix option,
service start, pkg add, migration, network operation, grant or code activation.
Filesystem-engine tests use explicit private image objects, NOT this native CLI.
"""
from __future__ import annotations
import argparse
import ast
from contextlib import contextmanager, nullcontext
import ctypes
import errno
import fcntl
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import zipfile

VERSION = '1.0.0-candidate3'
PAYLOAD_SHA = '023cfa3776f37d9911a18661ff0d6920e3aa68476467b6a5eaeecb209a532b41'
PINS = {
    'agentctl.py': 'a0564e931d4fd3b437613fb204f08e17a2263cfcc372724ac308439c86a5965e',
    'cherub_candidate.py': 'ad9acb05e26b890d6917839312c38ba854ee79d602ec62e8eeb0f74535735f7a',
    'cherub_flow.py': 'e5cd1b7f7f7f1d3e637cbdb62cdfdcddd90841113a7ecaf49f4ad7f76e306255',
    'cherub_state.py': 'ff56156e3904d65bb8bb70091a7b8fa2782d773879afaf16929a60d4a8a87848',
    'cherub_task_contract.py': 'eb2986fcce870bb191ddc50b0e72faaa98676d657b3fda5549b7ecc7746a9d7c',
}
RID = 'w09-v2-' + PAYLOAD_SHA[:16]
RELEASES = 'usr/local/libexec/eta-cherub-full/releases'
CONTROL = 'var/db/eta-cherub-full-installer'
TX = CONTROL + '/' + RID
STAGE = RELEASES + '/.staging-' + RID
FINAL = RELEASES + '/' + RID
WITHDRAWN = RELEASES + '/.withdrawn-' + RID
DATABASE = TX + '/state/cherub-state.sqlite3'
LOCK = CONTROL + '/.writer.lock'
ANCHORS = ('usr', 'usr/local', 'usr/local/libexec',
           'usr/local/libexec/eta-cherub-full', RELEASES, 'var', 'var/db', CONTROL)
TABLES = {'projects','budgets','operations','messages','run_facts','outbox'}
FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
MAX_FILE = 2 * 1024 * 1024
STATES = {'PREPARED','STAGING','STAGED','STATE_READY','PUBLISHED',
          'VERIFIED_INACTIVE','WITHDRAWING','WITHDRAWN','WITHDRAWN_INCOMPLETE'}

class Blocked(RuntimeError):
    pass

def need(condition, reason):
    if not condition:
        raise Blocked(reason)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True, allow_nan=False) + '\n').encode('ascii')

def unique_json(data):
    def hook(pairs):
        out = {}
        for key, value in pairs:
            need(key not in out, 'DUPLICATE_JSON_KEY')
            out[key] = value
        return out
    return json.loads(data, object_pairs_hook=hook,
        parse_constant=lambda _: (_ for _ in ()).throw(Blocked('NONFINITE_JSON')))

def parts(path):
    items = path.split('/')
    need(items and all(re.fullmatch(r'[A-Za-z0-9._-]+', p) and p not in ('.','..')
                       for p in items), 'UNSAFE_PATH')
    return items

def identity(st):
    return [st.st_dev, st.st_ino, st.st_uid, st.st_gid,
            stat.S_IMODE(st.st_mode), getattr(st, 'st_flags', 0)]

def read_fd(fd, maximum=MAX_FILE):
    st = os.fstat(fd)
    need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_size <= maximum,
         'NOT_BOUNDED_SINGLE_REGULAR_FILE')
    result = bytearray()
    while True:
        b = os.read(fd, min(65536, maximum + 1 - len(result)))
        if not b: break
        result.extend(b)
        need(len(result) <= maximum, 'READ_LIMIT')
    after = os.fstat(fd)
    need(identity(st) == identity(after) and
         (st.st_size, st.st_mtime_ns, st.st_ctime_ns) ==
         (after.st_size, after.st_mtime_ns, after.st_ctime_ns) and
         len(result) == st.st_size, 'FILE_CHANGED_DURING_READ')
    return bytes(result)

def read_external(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try: return read_fd(fd)
    finally: os.close(fd)

class Package:
    def __init__(self, data):
        need(len(data) <= MAX_FILE and sha(data) == PAYLOAD_SHA, 'PAYLOAD_SHA256_MISMATCH')
        names = {'MANIFEST.json'} | {'payload/' + n for n in PINS}
        files = {}
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            need(len(z.infolist()) == 6, 'PAYLOAD_INVENTORY_COUNT')
            for info in z.infolist():
                need(info.filename in names and info.filename not in files,
                     'PAYLOAD_DUPLICATE_OR_UNKNOWN_PATH')
                need(not info.is_dir() and not info.flag_bits & 1 and
                     stat.S_IFMT(info.external_attr >> 16) == stat.S_IFREG and
                     stat.S_IMODE(info.external_attr >> 16) == 0o444 and
                     0 < info.file_size <= MAX_FILE, 'PAYLOAD_MEMBER_FLAGS')
                with z.open(info) as f: body = f.read(MAX_FILE + 1)
                need(len(body) == info.file_size, 'PAYLOAD_MEMBER_LENGTH')
                files[info.filename] = body
        need(set(files) == names, 'PAYLOAD_INVENTORY')
        self.payload = {n: files['payload/' + n] for n in PINS}
        need(all(sha(self.payload[n]) == d for n,d in PINS.items()), 'SOURCE_HASH_MISMATCH')
        self.manifest = unique_json(files['MANIFEST.json'])
        need(canonical(self.manifest) == files['MANIFEST.json'] and
             self.manifest['scope'] == 'FIVE_MODULE_LAB_CORE_NOT_FULL_DISTRIBUTION' and
             self.manifest['state']['user_version'] == 2, 'SOURCE_MANIFEST_CONTRACT')
        self.schema = None
        self.appid = None
        # Parse pinned source as DATA; never import/execute a package module as root.
        for node in ast.parse(self.payload['cherub_state.py']).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0],ast.Name):
                if node.targets[0].id == '_SCHEMA': self.schema = ast.literal_eval(node.value)
                if node.targets[0].id == '_APP_ID': self.appid = ast.literal_eval(node.value)
        need(type(self.schema) is dict and set(self.schema) == TABLES and
             all(type(v) is str and v.startswith('CREATE TABLE ' + k + ' ')
                 for k,v in self.schema.items()) and type(self.appid) is int,
             'PINNED_STATE_SCHEMA_UNAVAILABLE')
        need(self.schema == self.manifest['state']['tables'] and
             self.appid == self.manifest['state']['application_id'], 'STATE_SCHEMA_MISMATCH')
        self.release_info = canonical({'format':'eta-system-release/1', 'release':RID,
            'scope':'FIVE_MODULE_W09_CORE_NOT_FULL_DISTRIBUTION', 'payload_sha256':PAYLOAD_SHA,
            'files':PINS, 'state_version':2, 'platform':'FreeBSD_15.1_amd64',
            'activation':'NONE', 'runtime_admission':False})

class NativeACL:
    """FreeBSD libc fd-based ACL check. Nontrivial/unknown ACLs are refused, not removed."""
    def __init__(self):
        self.lib = ctypes.CDLL(None, use_errno=True)
        self.lib.acl_get_fd_np.argtypes = [ctypes.c_int, ctypes.c_int]
        self.lib.acl_get_fd_np.restype = ctypes.c_void_p
        self.lib.acl_is_trivial_np.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        self.lib.acl_is_trivial_np.restype = ctypes.c_int
        self.lib.acl_get_entry.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
        self.lib.acl_get_entry.restype = ctypes.c_int
        self.lib.acl_free.argtypes = [ctypes.c_void_p]
        self.lib.acl_free.restype = ctypes.c_int
    def __call__(self, fd):
        isdir = stat.S_ISDIR(os.fstat(fd).st_mode)
        access_acl_verified = False
        for kind in ((4, 2, 3) if isdir else (4, 2)):
            # ACL_TYPE_NFS4=4, ACCESS=2, DEFAULT=3 (sys/sys/acl.h).
            ctypes.set_errno(0)
            acl = self.lib.acl_get_fd_np(fd, kind)
            if not acl:
                error = ctypes.get_errno()
                need(error in {errno.EINVAL, errno.EOPNOTSUPP}, 'ACL_READ_ERROR:' + str(error))
                continue
            try:
                if kind == 3:
                    entry = ctypes.c_void_p()
                    rc = self.lib.acl_get_entry(acl, 0, ctypes.byref(entry))
                    need(rc == 0, 'DEFAULT_ACL_NOT_EMPTY')
                else:
                    trivial = ctypes.c_int(0)
                    need(self.lib.acl_is_trivial_np(acl, ctypes.byref(trivial)) == 0 and trivial.value == 1,
                         'NONTRIVIAL_ACL_REQUIRES_REVIEW')
                    # EINVAL/EOPNOTSUPP for *every* access-ACL type is not an
                    # attestation that the filesystem has safe ACL semantics.
                    access_acl_verified = True
            finally:
                self.lib.acl_free(acl)
        need(access_acl_verified, 'ACL_ACCESS_TYPES_UNSUPPORTED_OR_UNVERIFIED')

class Tree:
    """All installer I/O relative to retained root FD, with physical owner-only ancestry.

Root-only peers are trusted; this does not defend against a hostile administrator.
No path argument in the native CLI can select a different target root.
"""
    def __init__(self, root, owner, acl):
        self.path = Path(root)
        self.owner = owner
        self.acl = acl
        self.root = os.open(root, FLAGS)
        self.created = {}
        self.secure(self.root, directory=True)
    def close(self):
        if self.root >= 0: os.close(self.root); self.root = -1
    def secure(self, fd, directory=False, mode=None):
        st = os.fstat(fd)
        need((stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode))
             and st.st_uid == self.owner and not st.st_mode & 0o7022,
             'UNSAFE_OWNER_TYPE_OR_MODE')
        if not directory: need(st.st_nlink == 1, 'HARDLINK_REFUSED')
        if mode is not None: need(stat.S_IMODE(st.st_mode) == mode, 'MODE_MISMATCH')
        self.acl(fd)
        return st
    def directory(self, path='', create=False, mode=0o755):
        fd = os.dup(self.root)
        traversed = []
        try:
            for component in (parts(path) if path else []):
                traversed.append(component)
                made = False
                try: child = os.open(component, FLAGS, dir_fd=fd)
                except FileNotFoundError:
                    if not create: raise
                    os.mkdir(component, mode, dir_fd=fd)
                    child = os.open(component, FLAGS, dir_fd=fd); made = True
                    os.fchmod(child, mode)
                    os.fsync(fd)
                try: self.secure(child, directory=True)
                except BaseException:
                    os.close(child); raise
                if made: self.created['/'.join(traversed)] = identity(os.fstat(child))
                os.close(fd); fd = child
            return fd
        except BaseException:
            os.close(fd); raise
    def parent(self, path):
        seq = parts(path)
        return self.directory('/'.join(seq[:-1])), seq[-1]
    def snapshot(self, path):
        try: parent,name = self.parent(path)
        except FileNotFoundError: return None
        try:
            try: st = os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError: return None
            need(not stat.S_ISLNK(st.st_mode), 'SYMLINK_REFUSED:' + path)
            fd = os.open(name, FLAGS if stat.S_ISDIR(st.st_mode) else
                         os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
            try:
                self.secure(fd, directory=stat.S_ISDIR(st.st_mode))
                need(identity(st) == identity(os.fstat(fd)), 'PATH_IDENTITY_RACE')
                return identity(st)
            finally: os.close(fd)
        finally: os.close(parent)
    def exists(self, path):
        return self.snapshot(path) is not None
    def read(self, path, mode=None):
        parent,name = self.parent(path)
        fd = -1
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
            st = self.secure(fd, mode=mode)
            result = read_fd(fd)
            need(identity(st) == identity(os.stat(name,dir_fd=parent,follow_symlinks=False)), 'READ_REBOUND')
            return result
        finally:
            if fd >= 0: os.close(fd)
            os.close(parent)
    def mkdir(self, path, mode=0o700):
        parent,name = self.parent(path)
        child = -1
        try:
            os.mkdir(name, mode, dir_fd=parent)
            child = os.open(name, FLAGS, dir_fd=parent)
            os.fchmod(child, mode)
            self.secure(child, directory=True, mode=mode)
            os.fsync(child); os.fsync(parent)
        finally:
            if child >= 0: os.close(child)
            os.close(parent)
    def write(self, path, data, mode=0o444):
        parent,name = self.parent(path)
        fd = -1
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=parent)
            view = memoryview(data)
            while view:
                count = os.write(fd, view); need(count > 0, 'SHORT_WRITE'); view = view[count:]
            os.fchmod(fd, mode)
            self.secure(fd, mode=mode)
            os.fsync(fd); os.fsync(parent)
        finally:
            if fd >= 0: os.close(fd)
            os.close(parent)
    def move(self, source, destination):
        a,an = self.parent(source); b,bn = self.parent(destination)
        try:
            need(not self.exists(destination), 'MOVE_WOULD_OVERWRITE')
            st = os.stat(an,dir_fd=a,follow_symlinks=False)
            need(stat.S_ISDIR(st.st_mode) and st.st_uid == self.owner and not st.st_mode & 0o022,
                 'MOVE_UNSAFE_SOURCE')
            need(os.fstat(a).st_dev == os.fstat(b).st_dev, 'CROSS_FILESYSTEM_PUBLICATION')
            os.rename(an,bn,src_dir_fd=a,dst_dir_fd=b)
            os.fsync(a); os.fsync(b)
        finally: os.close(a); os.close(b)
    def listing(self, path):
        fd = self.directory(path)
        try: return sorted(os.listdir(fd))
        finally: os.close(fd)
    def inventory(self, path):
        files, directories = {}, set()
        pending = [(self.directory(path), '')]
        count = 0
        try:
            while pending:
                fd,prefix = pending.pop()
                try:
                    self.secure(fd, directory=True)
                    for name in sorted(os.listdir(fd)):
                        parts(name); count += 1; need(count <= 64, 'TREE_INVENTORY_LIMIT')
                        st = os.stat(name,dir_fd=fd,follow_symlinks=False)
                        relative = prefix + name
                        if stat.S_ISDIR(st.st_mode):
                            child = os.open(name,FLAGS,dir_fd=fd)
                            self.secure(child,directory=True)
                            directories.add(relative)
                            pending.append((child,relative + '/'))
                        else:
                            need(stat.S_ISREG(st.st_mode), 'TREE_SPECIAL_OR_SYMLINK')
                            data = self.read(path + '/' + relative)
                            files[relative] = {'sha256':sha(data),'bytes':len(data),
                                               'mode':stat.S_IMODE(st.st_mode)}
                finally: os.close(fd)
        finally:
            for fd,_ in pending: os.close(fd)
        return files,directories
    @contextmanager
    def lock(self, write=False, create=False):
        if create:
            fd = self.directory(CONTROL, create=True, mode=0o700); os.close(fd)
        if not self.exists(CONTROL):
            need(not write, 'NO_CONTROL_ROOT')
            yield; return
        parent,name = self.parent(LOCK); fd = -1
        try:
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            except FileNotFoundError:
                if not create:
                    need(not write, 'NO_LOCK_FILE'); yield; return
                fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=parent)
                os.fsync(fd); os.fsync(parent)
            self.secure(fd,mode=0o600)
            fcntl.flock(fd,(fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            yield
        finally:
            if fd >= 0: os.close(fd)
            os.close(parent)

class Engine:
    def __init__(self, fs, package, target, tool_sha, fault=lambda _:None):
        self.fs, self.pkg, self.target, self.tool_sha, self.fault = fs,package,target,tool_sha,fault
    def stable_target(self):
        return {k:v for k,v in self.target.items() if k not in ('boot','kernel')}
    def binding(self):
        return {'format':'eta-system-install-binding/1','release':RID,
                'target':self.stable_target(), 'package_sha256':PAYLOAD_SHA,
                'installer_sha256':self.tool_sha,'activated':False}
    def read_events(self):
        f = self.fs
        if not f.exists(TX): return []
        for path in (TX, TX + '/events'):
            fd=f.directory(path)
            try: f.secure(fd,directory=True,mode=0o700)
            finally: os.close(fd)
        need(f.read(TX + '/identity.json',0o444) == canonical(self.binding()), 'INSTALLATION_TARGET_BINDING_MISMATCH')
        approval = unique_json(f.read(TX + '/approval.json',0o444))
        need(approval.get('plan_sha256') == sha(canonical(approval.get('plan'))), 'STORED_PLAN_INVALID')
        names = f.listing(TX + '/events')
        need(len(names) <= 32 and names == [f'{n:06}.json' for n in range(1,len(names)+1)],
             'JOURNAL_GAP_OR_UNKNOWN_FILE')
        rows = []; previous = '0'*64
        for n,name in enumerate(names,1):
            raw = f.read(TX + '/events/' + name, 0o444)
            row = unique_json(raw)
            need(canonical(row)==raw and set(row)=={'format','sequence','previous','state','binding_sha256'}
                 and row['format']=='eta-install-event/1' and row['sequence']==n
                 and row['previous']==previous and row['state'] in STATES and
                 row['binding_sha256']==sha(canonical(self.binding())), 'JOURNAL_INVALID_OR_PARTIAL')
            previous = sha(raw); rows.append(row)
        return rows
    def event(self, state):
        rows = self.read_events()
        previous = sha(canonical(rows[-1])) if rows else '0'*64
        row = {'format':'eta-install-event/1','sequence':len(rows)+1,'previous':previous,
               'state':state,'binding_sha256':sha(canonical(self.binding()))}
        self.fs.write(TX + f'/events/{len(rows)+1:06}.json',canonical(row))
        self.fault('event_' + state)
    def code_verify(self, location=FINAL):
        files,dirs = self.fs.inventory(location)
        expected = {'RELEASE.json':{'sha256':sha(self.pkg.release_info),'bytes':len(self.pkg.release_info),'mode':0o444}}
        for name,data in self.pkg.payload.items():
            expected['product/tools/'+name] = {'sha256':PINS[name],'bytes':len(data),'mode':0o444}
        need(files==expected and dirs=={'product','product/tools'}, 'INSTALLED_SOURCE_INVENTORY_OR_HASH_MISMATCH')
        for path in ('', '/product', '/product/tools'):
            fd = self.fs.directory(location+path)
            try: self.fs.secure(fd,directory=True,mode=0o755)
            finally: os.close(fd)
        return {'source_files':5,'source_pins':PINS}
    @contextmanager
    def database_lock(self, exclusive=False):
        """Use SQLite's OWN locking, never flock on its DB file.

        The installer-wide flock remains on the separate .writer.lock file.
        For withdrawal/recovery hold BEGIN EXCLUSIVE until after final rename
        and journal commit. SQLite owns all database-file POSIX locks.
        """
        f = self.fs
        dfd=f.directory(TX+'/state')
        try: f.secure(dfd,directory=True,mode=0o700)
        finally: os.close(dfd)
        need(f.listing(TX+'/state') == ['cherub-state.sqlite3'], 'STATE_EXTRA_FILES_OR_WAL')
        parent,name = f.parent(DATABASE)
        fd = -1
        db = None
        try:
            fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent)
            f.secure(fd,mode=0o600)
            need(identity(os.fstat(fd))==f.snapshot(DATABASE),'DATABASE_REBOUND')
            uri=(f.path/DATABASE).as_uri()+ ('?mode=rw' if exclusive else '?mode=ro')
            db=sqlite3.connect(uri,uri=True,isolation_level=None,timeout=0)
            db.execute('PRAGMA trusted_schema=OFF')
            # BEGIN EXCLUSIVE must precede query_only (otherwise SQLite
            # refuses obtaining a RESERVED/EXCLUSIVE transaction lock).
            db.execute('BEGIN EXCLUSIVE' if exclusive else 'BEGIN')
            db.execute('PRAGMA query_only=ON')
            need(identity(os.fstat(fd))==f.snapshot(DATABASE),'DATABASE_REBOUND')
            yield (db,fd)
        finally:
            if db is not None:
                try:
                    if db.in_transaction: db.execute('ROLLBACK')
                finally: db.close()
            if fd>=0: os.close(fd)
            os.close(parent)
    def database_verify(self, lease=None):
        if lease is None:
            with self.database_lock() as locked: return self.database_verify(locked)
        db,held_fd=lease
        f = self.fs
        need(f.listing(TX+'/state')==['cherub-state.sqlite3'], 'STATE_EXTRA_FILES_OR_WAL')
        data = f.read(DATABASE,0o600)
        need(data[:16]==b'SQLite format 3\0' and data[18:20]==b'\1\1','STATE_INVALID_OR_WAL')
        before = os.fstat(held_fd)
        need(identity(before)==f.snapshot(DATABASE),'DATABASE_REBOUND')
        need(db.in_transaction,'STATE_SQLITE_LOCK_NOT_HELD')
        need(db.execute('PRAGMA application_id').fetchone()[0]==self.pkg.appid and
             db.execute('PRAGMA user_version').fetchone()[0]==2,'STATE_VERSION_MISMATCH_NO_MIGRATION')
        schema = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
        need(schema==self.pkg.schema,'STATE_SCHEMA_MISMATCH')
        need(db.execute('PRAGMA integrity_check').fetchall()==[('ok',)],'STATE_INTEGRITY_FAIL')
        counts = {n:db.execute('SELECT count(*) FROM '+n).fetchone()[0] for n in sorted(TABLES)}
        need(db.execute('PRAGMA foreign_key_check').fetchall()==[],'STATE_FOREIGN_KEY_ERROR')
        after = os.fstat(held_fd)
        need(identity(before)==identity(after) and before.st_mtime_ns==after.st_mtime_ns
             and before.st_ctime_ns==after.st_ctime_ns and data==f.read(DATABASE,0o600),
             'STATE_CHANGED_DURING_VERIFY')
        need(not any(counts.values()),'STATE_IN_USE_REQUIRES_SEPARATE_RECONCILIATION')
        return {'user_version':2,'sha256':sha(data),'rows':counts,'runtime_owner':'root-quarantined'}
    def create_state(self):
        f = self.fs
        f.mkdir(TX+'/state',0o700)
        f.write(DATABASE,b'',0o600)
        parent,name = f.parent(DATABASE)
        fd = os.open(name,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
        os.close(parent)
        try:
            # No flock on the database file: SQLite owns its POSIX locks.
            # The installer is serialized by the separate .writer.lock.
            self.fault('empty_database')
            uri = (f.path/DATABASE).as_uri()+'?mode=rw'
            db = sqlite3.connect(uri,uri=True,isolation_level=None,timeout=0)
            try:
                need(db.execute('PRAGMA journal_mode=DELETE').fetchone()[0]=='delete','JOURNAL_MODE')
                db.execute('PRAGMA synchronous=FULL'); db.execute('PRAGMA foreign_keys=ON')
                db.execute('PRAGMA trusted_schema=OFF'); db.execute('BEGIN EXCLUSIVE')
                for statement in self.pkg.schema.values(): db.execute(statement)
                db.execute('PRAGMA application_id='+str(self.pkg.appid)); db.execute('PRAGMA user_version=2')
                db.execute('COMMIT')
            finally: db.close()
            os.fsync(fd)
            self.database_verify()
        finally: os.close(fd)
        dfd=f.directory(TX+'/state')
        try: os.fsync(dfd)
        finally: os.close(dfd)
        self.fault('after_database')
    def current(self):
        rows = self.read_events()
        if not rows:
            need(not self.fs.exists(TX),'INCOMPLETE_INITIAL_JOURNAL_MANUAL_RECOVERY')
            need(not any(self.fs.exists(x) for x in (STAGE,FINAL,WITHDRAWN)), 'UNMANAGED_RELEASE_COLLISION')
            return {'state':'ABSENT','last_event':None}
        last = rows[-1]
        return {'state':last['state'],'last_event':sha(canonical(last))}
    def verify_unlocked(self, location=FINAL):
        code=self.code_verify(location)
        state=self.database_verify()
        return {'result':'VERIFIED_INSTALLED_INACTIVE_CORE','release':RID,
                'code_location':'/'+location,'state_location':'/'+DATABASE,
                'code':code,'state':state,'activated':False,'full_product':False,
                'runtime_admission':False}
    def verify(self):
        with self.fs.lock():
            current = self.current()
            need(current['state']=='VERIFIED_INACTIVE','NOT_VERIFIED_INACTIVE_RELEASE')
            return self.verify_unlocked()
    def status(self):
        with self.fs.lock():
            current=self.current()
            if current['state']=='VERIFIED_INACTIVE': return self.verify_unlocked()
            if current['state']=='WITHDRAWN':
                need(not self.fs.exists(FINAL) and not self.fs.exists(STAGE),'WITHDRAW_LAYOUT_MISMATCH')
                return {**self.verify_unlocked(WITHDRAWN),'result':'WITHDRAWN_DATA_RETAINED'}
            if current['state']=='WITHDRAWN_INCOMPLETE':
                need(not self.fs.exists(FINAL) and not self.fs.exists(STAGE),'ABORT_LAYOUT_MISMATCH')
                return {'result':'WITHDRAWN_INCOMPLETE_DATA_RETAINED','activated':False}
            return {'result':'ABSENT' if current['state']=='ABSENT' else 'RECOVERY_REQUIRED',
                    'journal':current,'activated':False}
    def plan_unlocked(self, operation='install'):
        need(operation in ('install','withdraw','complete','abort','complete-withdrawal'),'UNKNOWN_PLAN_OPERATION')
        f = self.fs
        current = self.current()
        if operation=='install':
            need(current['state'] in ('ABSENT','VERIFIED_INACTIVE'),'RECOVERY_REQUIRED_NO_AUTO_RETRY')
            if current['state']=='VERIFIED_INACTIVE': self.verify_unlocked()
        elif operation=='withdraw':
            need(current['state'] in ('VERIFIED_INACTIVE','WITHDRAWN'),'NOT_INSTALLED_INACTIVE')
            if current['state']=='WITHDRAWN':
                need(not f.exists(FINAL) and not f.exists(STAGE),'WITHDRAW_LAYOUT_MISMATCH')
                self.verify_unlocked(WITHDRAWN)
            else:
                self.verify_unlocked()
                need(not f.exists(WITHDRAWN),'WITHDRAW_COLLISION')
        else:
            need(current['state'] not in ('ABSENT','VERIFIED_INACTIVE','WITHDRAWN','WITHDRAWN_INCOMPLETE'),
                 'RECOVERY_NOT_APPLICABLE')
            if operation=='complete':
                need(current['state'] in ('STATE_READY','PUBLISHED','STAGED'), 'INCOMPLETE_REQUIRES_ABORT')
                need(f.exists(STAGE) != f.exists(FINAL),'RECOVERY_LOCATION_AMBIGUOUS')
                self.verify_unlocked(FINAL if f.exists(FINAL) else STAGE)
            elif operation=='complete-withdrawal':
                need(current['state']=='WITHDRAWING' and f.exists(WITHDRAWN) and
                     not f.exists(FINAL) and not f.exists(STAGE),'WITHDRAW_RECOVERY_NOT_APPLICABLE')
                self.verify_unlocked(WITHDRAWN)
            else:
                need(not f.exists(WITHDRAWN) and not (f.exists(FINAL) and f.exists(STAGE)),
                     'ABORT_LOCATION_AMBIGUOUS')
                # P2: The journal may still say STAGED after a committed DB create.
                # Any existing database MUST be validated (including empty tables),
                # even if the event has not advanced. A zero-byte/partial DB is
                # ambiguous: refuse automatic abort; require manual reconciliation.
                # Once STAGED is recorded, DB creation may have started and
                # been interrupted. A missing database cannot prove that no
                # durable state was ever created; refuse automatic abort.
                need(f.exists(DATABASE) or current['state'] in
                     ('PREPARED','STAGING'), 'STATE_FILE_MISSING_OR_UNCERTAIN_AT_STAGED')
                if f.exists(DATABASE):
                    self.database_verify()
                for p in (STAGE,FINAL):
                    if f.exists(p): f.inventory(p)
        snapshot={p:f.snapshot(p) for p in ANCHORS + (TX,STAGE,FINAL,WITHDRAWN,DATABASE)}
        root_state = self.database_verify() if f.exists(DATABASE) else None
        code_files = {'/'+FINAL+'/product/tools/'+n:{'sha256':PINS[n],'bytes':len(b),'mode':'0444'}
                      for n,b in sorted(self.pkg.payload.items())}
        doc={'format':'eta-system-plan/1','installer_version':VERSION,'installer_sha256':self.tool_sha,
             'operation':operation,'target':self.target,'payload_sha256':PAYLOAD_SHA,'release':RID,
             'scope':'SYSTEM_INSTALL_SCOPED_W09_CORE_INACTIVE','observed':current,
             'anchors_and_destinations':snapshot,'state_observation':root_state,
             'files':code_files,'code_metadata':'/'+FINAL+'/RELEASE.json',
             'fresh_state':'/'+DATABASE,'installation_control':'/'+TX,
             'installation_lock':'/'+LOCK,'stage':'/'+STAGE,'withdrawn':'/'+WITHDRAWN,
             'control_files':['/'+TX+'/identity.json','/'+TX+'/approval.json'],
             'initial_event_files':['/'+TX+f'/events/{n:06}.json' for n in range(1,7)],
             'sqlite_transient_files':['/'+DATABASE+'-journal'],
             'new_directory_candidates':{p: ('0700' if p.startswith(CONTROL) else '0755')
                 for p in ANCHORS if snapshot[p] is None},
             'ownership':'root:current-effective-root-group','new_state_mode':'0600',
             'directories_modes':{'release':'0755','control_and_state':'0700'},
             'will_start_services':False,'will_activate':False,'will_migrate_state':False,
             'will_touch_active_product':False,'will_register_with_pkg':False,
             'will_change_pf_vpn_dns_jails_zfs':False,'will_create_grants_or_budgets':False,
             'runtime_status':'NOT_AUTHORIZED','minimum_free_bytes':16*1024*1024}
        return {'plan':doc,'plan_sha256':sha(canonical(doc))}
    def plan(self, operation='install'):
        with self.fs.lock(): return self.plan_unlocked(operation)
    def confirm(self, expected, plan):
        need(type(expected) is str and re.fullmatch('[0-9a-f]{64}',expected) and
             hmac.compare_digest(expected,plan['plan_sha256']),'PLAN_NOT_CONFIRMED_OR_STALE')
    def recheck(self, snapshot):
        for path,wanted in snapshot.items():
            observed=self.fs.snapshot(path)
            if wanted is None and path in self.fs.created:
                wanted=self.fs.created[path]
            need(observed==wanted,'TARGET_CHANGED_SINCE_PLAN:'+path)
    def install(self, expected):
        plan=self.plan('install'); self.confirm(expected,plan)
        if plan['plan']['observed']['state']=='VERIFIED_INACTIVE':
            return {**self.verify(),'result':'ALREADY_INSTALLED_NO_WRITES'}
        # Reject inadequate free space BEFORE any state/code mutation.
        for path in ('usr/local','var/db'):
            fd=self.fs.directory(path)
            try:
                s=os.fstatvfs(fd)
                need(s.f_bavail*s.f_frsize>=16*1024*1024,'INSUFFICIENT_FREE_SPACE')
            finally: os.close(fd)
        f=self.fs
        with f.lock(write=True,create=True):
            self.recheck(plan['plan']['anchors_and_destinations'])
            d=f.directory(RELEASES,create=True,mode=0o755); os.close(d)
            f.mkdir(TX,0o700)
            f.write(TX+'/identity.json',canonical(self.binding()))
            f.write(TX+'/approval.json',canonical(plan))
            f.mkdir(TX+'/events',0o700)
            self.event('PREPARED')
            self.event('STAGING')
            f.mkdir(STAGE,0o755); f.mkdir(STAGE+'/product',0o755); f.mkdir(STAGE+'/product/tools',0o755)
            for name,data in sorted(self.pkg.payload.items()):
                f.write(STAGE+'/product/tools/'+name,data)
                self.fault('file_'+name)
            f.write(STAGE+'/RELEASE.json',self.pkg.release_info)
            self.code_verify(STAGE); self.event('STAGED')
            self.create_state(); self.event('STATE_READY')
            f.move(STAGE,FINAL); self.fault('after_publish'); self.event('PUBLISHED')
            result=self.verify_unlocked(); self.event('VERIFIED_INACTIVE')
            return result
    def withdraw(self, expected):
        plan=self.plan('withdraw'); self.confirm(expected,plan)
        if plan['plan']['observed']['state']=='WITHDRAWN':
            return {'result':'ALREADY_WITHDRAWN_NO_WRITES','release':RID,'files_deleted':0}
        with self.fs.lock(write=True):
            self.recheck(plan['plan']['anchors_and_destinations'])
            need(self.current()==plan['plan']['observed'],'JOURNAL_CHANGED_SINCE_PLAN')
            self.code_verify()
            with self.database_lock(exclusive=True) as lease:
                db=self.database_verify(lease)
                need(db==plan['plan']['state_observation'],'STATE_CHANGED_SINCE_PLAN')
                self.event('WITHDRAWING')
                self.fs.move(FINAL,WITHDRAWN); self.fault('after_withdraw')
                self.code_verify(WITHDRAWN); self.database_verify(lease)
                self.event('WITHDRAWN')
            return {'result':'WITHDRAWN_DATA_RETAINED','files_deleted':0,'state_sha256':db['sha256'],
                    'active_product_changed':False,'release':RID}
    def recover(self, decision, expected):
        plan=self.plan(decision); self.confirm(expected,plan)
        with self.fs.lock(write=True):
            self.recheck(plan['plan']['anchors_and_destinations'])
            need(self.current()==plan['plan']['observed'],'JOURNAL_CHANGED_SINCE_PLAN')
            if decision=='complete':
                self.verify_unlocked(FINAL if self.fs.exists(FINAL) else STAGE)
                if self.fs.exists(STAGE): self.fs.move(STAGE,FINAL)
                result=self.verify_unlocked(); self.event('VERIFIED_INACTIVE')
                return {**result,'result':'RECOVERED_NO_REEXECUTION'}
            if decision=='complete-withdrawal':
                self.verify_unlocked(WITHDRAWN); self.event('WITHDRAWN')
                return {'result':'RECOVERED_WITHDRAWAL_DATA_RETAINED','files_deleted':0}
            need(decision=='abort','UNKNOWN_RECOVERY')
            # P2: if an actual database exists, hold an SQLite EXCLUSIVE lease
            # through the entire abort; never assume STAGED means DB absent.
            # Invalid/partial, nonempty or locked databases refuse this operation.
            has_db=self.fs.exists(DATABASE)
            need(has_db == (plan['plan']['state_observation'] is not None),
                 'ABORT_STATE_PRESENCE_CHANGED')
            with (self.database_lock(exclusive=True) if has_db else nullcontext(None)) as lease:
                if has_db:
                    observed=self.database_verify(lease)
                    need(observed==plan['plan']['state_observation'],
                         'ABORT_STATE_CHANGED_SINCE_PLAN')
                for p in (STAGE,FINAL):
                    if self.fs.exists(p): self.fs.move(p,WITHDRAWN)
                self.event('WITHDRAWN_INCOMPLETE')
            return {'result':'ABORTED_PARTIAL_DATA_RETAINED','files_deleted':0,'release':RID}


def native_target():
    need(sys.platform.startswith('freebsd'),'FREEBSD_15_1_REQUIRED_NATIVE_NOT_TESTED_HERE')
    need(sys.version_info[:2]==(3,12),'PYTHON_3_12_REQUIRED')
    need(sys.flags.isolated and sys.dont_write_bytecode,'USE_PYTHON_I_B')
    need(all(fn in os.supports_dir_fd for fn in (os.open,os.stat,os.mkdir,os.rename))
         and os.listdir in os.supports_fd and os.stat in os.supports_follow_symlinks,
         'REQUIRED_DESCRIPTOR_RELATIVE_API_UNAVAILABLE')
    u=os.uname()
    need(u.sysname=='FreeBSD' and u.machine=='amd64' and
         re.fullmatch(r'15\.1-RELEASE(?:-p\d+)?',u.release),'UNSUPPORTED_KERNEL_OR_ARCH')
    def query(argv):
        done=subprocess.run(argv,capture_output=True,text=True,timeout=5,check=False,
            env={'PATH':'/bin:/sbin:/usr/bin:/usr/sbin','LC_ALL':'C'},cwd='/')
        need(done.returncode==0 and 0<len(done.stdout)<4096,'HOST_IDENTITY_QUERY_FAILED')
        return done.stdout.strip()
    userland=query(['/bin/freebsd-version','-u'])
    need(re.fullmatch(r'15\.1-RELEASE(?:-p\d+)?',userland),'USERLAND_NOT_15_1_RELEASE')
    jailed=query(['/sbin/sysctl','-n','security.jail.jailed'])
    need(jailed in ('0','1'),'JAIL_IDENTITY_UNKNOWN')
    hostuuid=query(['/sbin/sysctl','-n','kern.hostuuid'])
    need(re.fullmatch(r'[a-fA-F0-9-]{36}',hostuuid),'HOST_UUID_UNKNOWN')
    boot=query(['/sbin/sysctl','-n','kern.boottime'])
    return {'kind':'NATIVE_FREEBSD','userland':userland,'kernel':u.release,'machine':u.machine,
            'hostname':u.nodename,'hostuuid':hostuuid,'jailed':jailed,'boot':boot,
            'root_identity':identity(os.stat('/'))}

def secure_toolchain(fs, package_path):
    # Mutation requires all root-run files to be in physical root-owned directories.
    for path in (str(Path(__file__).absolute()), str(Path(package_path).absolute()), sys.executable):
        need(path.startswith('/'),'ABSOLUTE_TOOLCHAIN_PATH_REQUIRED')
        parent,name=fs.parent(path[1:]); fd=-1
        try:
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
            info=fs.secure(fd)
            need(info.st_size>0,'EMPTY_TOOLCHAIN_FILE')
        finally:
            if fd>=0: os.close(fd)
            os.close(parent)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('inspect','plan','install','verify','status',
                                     'rollback-plan','rollback','recovery-plan','recover'))
    p.add_argument('--package',required=True,help='exact private ETA_W09_CORE_LAB_R1.zip')
    p.add_argument('--confirm-plan',help='exact SHA-256 from corresponding read-only plan')
    p.add_argument('--allow-system-write',action='store_true',help='operator-authorized system file mutation only')
    p.add_argument('--decision',choices=('complete','abort','complete-withdrawal'),help='explicit recovery action; never rerun a task')
    args=p.parse_args(argv)
    fs=None
    try:
        need(sys.flags.isolated and sys.dont_write_bytecode,'USE_PYTHON_I_B')
        package=Package(read_external(args.package))
        if args.command=='inspect':
            result={'result':'PACKAGE_INTEGRITY_PASS','package_sha256':PAYLOAD_SHA,
                    'release':RID,'scope':'FIVE_MODULE_CORE_NOT_FULL','files':PINS,
                    'native_execution':'NOT_PERFORMED','activation':'NOT_IMPLEMENTED'}
        else:
            target=native_target()
            mutation=args.command in ('install','rollback','recover')
            if mutation:
                need(os.getuid()==os.geteuid()==0,'ROOT_REQUIRED_FOR_SYSTEM_WRITES')
                need(args.allow_system_write and args.confirm_plan,'SEPARATE_SYSTEM_WRITE_APPROVAL_REQUIRED')
            fs=Tree('/',0,NativeACL())
            if mutation: secure_toolchain(fs,args.package)
            tool_sha=sha(read_external(Path(__file__).absolute()))
            engine=Engine(fs,package,target,tool_sha)
            if args.command=='plan': result=engine.plan('install')
            elif args.command=='install': result=engine.install(args.confirm_plan)
            elif args.command=='verify': result=engine.verify()
            elif args.command=='status': result=engine.status()
            elif args.command=='rollback-plan': result=engine.plan('withdraw')
            elif args.command=='rollback': result=engine.withdraw(args.confirm_plan)
            else:
                need(args.decision is not None,'RECOVERY_DECISION_REQUIRED')
                result=(engine.plan(args.decision) if args.command=='recovery-plan'
                        else engine.recover(args.decision,args.confirm_plan))
        print(json.dumps(result,ensure_ascii=True,sort_keys=True,indent=2))
        return 20 if result.get('result')=='RECOVERY_REQUIRED' else 0
    except (Blocked,OSError,ValueError,KeyError,TypeError,sqlite3.Error,zipfile.BadZipFile,
            subprocess.SubprocessError,AttributeError) as exc:
        print(json.dumps({'result':'BLOCKED','reason':str(exc),'code_activation':False,
                          'on_interrupted_write':'USE_STATUS_AND_EXPLICIT_RECOVERY_NEVER_RETRY_BLINDLY'},
                         ensure_ascii=True,sort_keys=True),file=sys.stderr)
        return 20
    finally:
        if fs is not None: fs.close()

if __name__=='__main__':
    raise SystemExit(main())
