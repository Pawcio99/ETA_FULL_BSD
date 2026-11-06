"""Descriptor-relative I/O restricted to an owned disposable Linux lab root.

This is an installation-test boundary, NOT an OS sandbox or admission issuer.
A hostile process with the same UID is outside this single-writer threat model.
"""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import uuid
from eta_i3_package import need, canonical, json_unique

DIRFLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC

def guard():
    need(sys.platform.startswith('linux'), 'NATIVE_BACKEND_NOT_IMPLEMENTED')
    need(os.getuid() == os.geteuid() and os.geteuid() != 0, 'NONROOT_OFFHOST_REQUIRED')
    need(sys.dont_write_bytecode, 'INVOKE_PYTHON_WITH_B_OR_I_B')

def private(info, mode, directory=False):
    need((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)) and
         info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == mode,
         'OWNERSHIP_TYPE_OR_MODE_MISMATCH')
    if not directory:
        need(info.st_nlink == 1, 'HARDLINK_REFUSED')

def root_path(value):
    path = Path(value)
    need(str(path) == str(value) and path.is_absolute() and len(path.parts) == 4 and
         path.parts[:2] == ('/', 'tmp') and
         re.fullmatch(r'eta-i3-work-[A-Za-z0-9_-]+', path.parts[2]) and
         re.fullmatch(r'lab-[A-Za-z0-9_-]+', path.parts[3]), 'NOT_DISPOSABLE_LAB_PATH')
    return path

def initialize(workspace=None):
    guard()
    if workspace is None:
        workspace = Path(tempfile.mkdtemp(prefix='eta-i3-work-', dir='/tmp'))
    else:
        workspace = Path(workspace)
    need(workspace.parent == Path('/tmp') and
         re.fullmatch(r'eta-i3-work-[A-Za-z0-9_-]+', workspace.name), 'INVALID_WORKSPACE')
    tmpfd = os.open('/tmp', DIRFLAGS)
    try:
        info = os.fstat(tmpfd)
        need(info.st_uid == 0 and info.st_mode & stat.S_ISVTX, 'UNTRUSTED_TMP')
        parent = os.open(workspace.name, DIRFLAGS, dir_fd=tmpfd)
        try:
            private(os.fstat(parent), 0o700, True)
            name = 'lab-' + uuid.uuid4().hex
            os.mkdir(name, 0o700, dir_fd=parent)
            fd = os.open(name, DIRFLAGS, dir_fd=parent)
            try:
                st = os.fstat(fd)
                marker = {'format': 'eta-i3-disposable-lab/1', 'uid': os.geteuid(),
                          'device': st.st_dev, 'inode': st.st_ino,
                          'runtime_admission': False, 'root_id': uuid.uuid4().hex}
                for target, data in (('.eta-i3-lab.json', canonical(marker)), ('.mutation.lock', b'')):
                    item = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                   0o600, dir_fd=fd)
                    try:
                        os.write(item, data); os.fsync(item)
                    finally:
                        os.close(item)
                os.fsync(fd); os.fsync(parent)
            finally:
                os.close(fd)
        finally:
            os.close(parent)
    finally:
        os.close(tmpfd)
    return str(workspace / name)

class Root:
    def __init__(self, path, *, exclusive=False):
        guard()
        self.path = root_path(path)
        self.fd = self.lock = -1
        self.exclusive = exclusive
    def __enter__(self):
        tmp = parent = -1
        try:
            tmp = os.open('/tmp', DIRFLAGS)
            info = os.fstat(tmp)
            need(info.st_uid == 0 and info.st_mode & stat.S_ISVTX, 'UNTRUSTED_TMP')
            parent = os.open(self.path.parent.name, DIRFLAGS, dir_fd=tmp)
            private(os.fstat(parent), 0o700, True)
            self.fd = os.open(self.path.name, DIRFLAGS, dir_fd=parent)
            private(os.fstat(self.fd), 0o700, True)
            marker = json_unique(self.read('.eta-i3-lab.json', 0o600))
            st = os.fstat(self.fd)
            need(marker.get('format') == 'eta-i3-disposable-lab/1' and
                 marker.get('uid') == os.geteuid() and marker.get('device') == st.st_dev and
                 marker.get('inode') == st.st_ino and marker.get('runtime_admission') is False,
                 'LAB_MARKER_MISMATCH')
            self.lock = os.open('.mutation.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=self.fd)
            private(os.fstat(self.lock), 0o600)
            fcntl.flock(self.lock, (fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise
        finally:
            if parent >= 0: os.close(parent)
            if tmp >= 0: os.close(tmp)
    def __exit__(self, *args):
        if self.lock >= 0: os.close(self.lock); self.lock = -1
        if self.fd >= 0: os.close(self.fd); self.fd = -1
    def parent(self, path):
        bits = str(path).split('/')
        need(bits and all(re.fullmatch(r'[A-Za-z0-9_.-]+', b) and b not in ('.', '..') for b in bits),
             'UNSAFE_RELATIVE_PATH')
        fd = os.dup(self.fd)
        try:
            for b in bits[:-1]:
                new = os.open(b, DIRFLAGS, dir_fd=fd)
                private(os.fstat(new), 0o700, True)
                os.close(fd); fd = new
            return fd, bits[-1]
        except BaseException:
            os.close(fd); raise
    def read(self, path, mode=0o444, maximum=2*1024*1024):
        parent, name = self.parent(path)
        fd = -1
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
            before = os.fstat(fd); private(before, mode)
            need(before.st_size <= maximum, 'LAB_FILE_TOO_LARGE')
            data = bytearray()
            while True:
                part = os.read(fd, 65536)
                if not part: break
                data.extend(part); need(len(data) <= maximum, 'LAB_FILE_TOO_LARGE')
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            def identity(s): return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns
            need(identity(before) == identity(after) == identity(named) and len(data) == before.st_size,
                 'FILE_CHANGED_DURING_READ')
            return bytes(data)
        finally:
            if fd >= 0: os.close(fd)
            os.close(parent)
    def exists(self, path):
        parent, name = self.parent(path)
        try:
            try: os.stat(name, dir_fd=parent, follow_symlinks=False); return True
            except FileNotFoundError: return False
        finally:
            os.close(parent)
    def mkdir(self, path):
        need(self.exclusive, 'WRITE_LOCK_REQUIRED')
        parent, name = self.parent(path)
        try:
            os.mkdir(name, 0o700, dir_fd=parent); os.fsync(parent)
        finally:
            os.close(parent)
    def write_new(self, path, data, mode=0o444):
        need(self.exclusive, 'WRITE_LOCK_REQUIRED')
        parent, name = self.parent(path)
        fd = -1
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=parent)
            view = memoryview(data)
            while view:
                n = os.write(fd, view); need(n > 0, 'SHORT_WRITE'); view = view[n:]
            os.fchmod(fd, mode); os.fsync(fd); os.fsync(parent)
        finally:
            if fd >= 0: os.close(fd)
            os.close(parent)
    def replace_record(self, value, fault=lambda _: None):
        self.write_new('.next-record', canonical(value), 0o600)
        fault('before_record_' + value['state'])
        if self.exists('transaction.json'):
            self.read('transaction.json', 0o600)
        os.replace('.next-record', 'transaction.json', src_dir_fd=self.fd, dst_dir_fd=self.fd)
        os.fsync(self.fd)
    def rename_top(self, source, destination):
        need(self.exclusive and '/' not in source + destination, 'TOP_LEVEL_MOVE_ONLY')
        need(not self.exists(destination), 'DESTINATION_EXISTS')
        # No deletion or overwrite. Inspection and rename use the retained root fd.
        info = os.stat(source, dir_fd=self.fd, follow_symlinks=False)
        need(not stat.S_ISLNK(info.st_mode), 'LINK_MOVE_REFUSED')
        os.rename(source, destination, src_dir_fd=self.fd, dst_dir_fd=self.fd)
        os.fsync(self.fd)
    def tree(self, base):
        parent,name = self.parent(base)
        try: start = os.open(name, DIRFLAGS, dir_fd=parent)
        finally: os.close(parent)
        pending=[(start, '')]; files={}; directories=set(); count=0
        try:
            while pending:
                fd,prefix = pending.pop()
                try:
                    private(os.fstat(fd), 0o700, True)
                    for name in sorted(os.listdir(fd)):
                        count += 1; need(count <= 40, 'LAB_TREE_LIMIT')
                        rel = prefix + name
                        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                        if stat.S_ISDIR(st.st_mode):
                            private(st, 0o700, True); directories.add(rel)
                            pending.append((os.open(name, DIRFLAGS, dir_fd=fd), rel + '/'))
                        else:
                            need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.geteuid(),
                                 'NONREGULAR_LAB_ENTRY')
                            files[rel] = stat.S_IMODE(st.st_mode)
                finally: os.close(fd)
        finally:
            for fd,_ in pending: os.close(fd)
        return files, directories
