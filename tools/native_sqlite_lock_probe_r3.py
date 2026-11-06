#!/usr/bin/env python3
"""Non-root native SQLite locking probe, NOT a product or root installer.

Writes exactly one fresh private SQLite fixture in a newly created home/Downloads
subdirectory. No existing files are overwritten, no network, root, model, jail,
PF, ZFS, DNS, services or grants. Executes only itself as one extra child.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def child(dbfile):
    db = sqlite3.connect(dbfile, timeout=0, isolation_level=None)
    try:
        try:
            db.execute('BEGIN IMMEDIATE')
        except sqlite3.OperationalError as exc:
            if 'locked' not in str(exc).lower():
                print('UNEXPECTED_SQLITE_ERROR', str(exc))
                return 3
            print('SQLITE_LOCK_DENIED')
            return 2
        db.execute('SELECT count(*) FROM lock_probe').fetchone()
        db.execute('ROLLBACK')
        print('SQLITE_LOCK_ACQUIRED')
        return 0
    finally:
        db.close()


def main():
    if os.getuid() == 0 or os.geteuid() == 0:
        print('BLOCKED=ROOT_NOT_ALLOWED')
        return 20
    if len(sys.argv) == 3 and sys.argv[1] == '--child':
        candidate = Path(sys.argv[2])
        allowed = Path.home() / 'Downloads'
        if not (candidate.is_absolute() and
                candidate.name == 'test_only.sqlite3' and
                candidate.parent.parent == allowed and
                candidate.parent.name.startswith('ETA_R3_SQLITE_LOCK.') and
                not candidate.is_symlink() and
                not candidate.parent.is_symlink()):
            print('BLOCKED=UNTRUSTED_FIXTURE_PATH')
            return 20
        return child(str(candidate))
    if len(sys.argv) != 1:
        print('BLOCKED=INVALID_ARGUMENTS')
        return 20
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        print('BLOCKED=RUN_PYTHON_I_B')
        return 20
    parent = Path.home() / 'Downloads'
    if not parent.is_dir() or parent.is_symlink():
        print('BLOCKED=DOWNLOADS_REQUIRED')
        return 20
    directory = Path(tempfile.mkdtemp(prefix='ETA_R3_SQLITE_LOCK.', dir=parent))
    dbpath = directory / 'test_only.sqlite3'
    db = sqlite3.connect(dbpath, timeout=0, isolation_level=None)
    try:
        db.execute('PRAGMA journal_mode=DELETE')
        db.execute('CREATE TABLE lock_probe(id INTEGER PRIMARY KEY)')
    finally:
        db.close()
    before = sha(dbpath)
    c = sqlite3.connect(dbpath, timeout=0, isolation_level=None)
    try:
        c.execute('PRAGMA trusted_schema=OFF')
        c.execute('BEGIN EXCLUSIVE')
        c.execute('PRAGMA query_only=ON')
        c.execute('SELECT count(*) FROM lock_probe').fetchone()
        denied = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).resolve()),
                                 '--child', str(dbpath)],capture_output=True,text=True,timeout=10)
        c.execute('ROLLBACK')
    finally:
        c.close()
    allowed = subprocess.run([sys.executable, '-I','-B',str(Path(__file__).resolve()),
                              '--child',str(dbpath)],capture_output=True,text=True,timeout=10)
    same = before == sha(dbpath)
    ok = denied.returncode == 2 and denied.stdout.strip() == 'SQLITE_LOCK_DENIED' and \
         allowed.returncode == 0 and allowed.stdout.strip() == 'SQLITE_LOCK_ACQUIRED' and same
    print(json.dumps({'result':'PASS' if ok else 'FAIL',
                      'platform':sys.platform, 'python':sys.version.split()[0],
                      'sqlite':sqlite3.sqlite_version,'uid':os.getuid(),
                      'held_exclusive_rejects_child':denied.stdout.strip(),
                      'after_release_allows_child':allowed.stdout.strip(),
                      'db_sha256_preserved':same,
                      'fixture_directory':str(directory),
                      'root_installer_executed':False},sort_keys=True))
    return 0 if ok else 21

if __name__ == '__main__':
    raise SystemExit(main())
