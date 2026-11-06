"""Readback verifier: package pin and bytes, not an installer PASS receipt.

No StateLedger import and no writable SQLite connection. This code is a
separate verification path, not an independent human/agent security review.
"""
import fcntl
import os
import sqlite3
from pathlib import Path
from eta_i3_package import need, canonical, sha

def inspect_image(root, package, location='image', *, require_state=True):
    manifest = package['manifest']
    files, directories = root.tree(location)
    expected = {'PACKAGE.json': 0o444,
                **{'product/tools/' + n: 0o444 for n in manifest['files']}}
    expected_dirs = {'product', 'product/tools'}
    if require_state:
        expected['state/cherub-state.sqlite3'] = 0o600
        expected_dirs.add('state')
    need(files == expected and directories == expected_dirs, 'INSTALLED_INVENTORY_OR_MODE_MISMATCH')
    need(root.read(location + '/PACKAGE.json') == canonical(manifest), 'INSTALLED_MANIFEST_MISMATCH')
    verified = []
    for name, item in manifest['files'].items():
        body = root.read(location + '/product/tools/' + name)
        need(len(body) == item['bytes'] and sha(body) == item['sha256'], 'INSTALLED_SOURCE_MISMATCH:' + name)
        verified.append(name)
    result = {'result': 'VERIFIED_SCOPED_LAB_IMAGE', 'files_verified': len(verified),
              'package_sha256': package['sha256'], 'location': location,
              'product_started': False, 'runtime_admission': False,
              'full_distribution': False, 'native_freebsd_tested': False}
    if not require_state:
        result['state'] = 'NOT_CREATED'
        return result
    path = root.path / location / 'state/cherub-state.sqlite3'
    # Directory topology was walked O_NOFOLLOW under the shared/exclusive lab lock.
    # Same-UID adversarial renames are NOT claimed to be contained by this lab adapter.
    parent, name = root.parent(location + '/state/cherub-state.sqlite3')
    fd = -1
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        before = os.fstat(fd)
        header = os.pread(fd, 100, 0)
        need(header[:16] == b'SQLite format 3\0' and header[18:20] == b'\1\1', 'INVALID_OR_WAL_DB')
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, isolation_level=None)
        try:
            db.execute('PRAGMA query_only=ON')
            need(db.execute('PRAGMA application_id').fetchone()[0] == manifest['state']['application_id'],
                 'STATE_APPLICATION_ID_MISMATCH')
            need(db.execute('PRAGMA user_version').fetchone()[0] == 2, 'STATE_VERSION_REQUIRES_SEPARATE_MIGRATION')
            actual = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
            need(actual == manifest['state']['tables'], 'STATE_SCHEMA_MISMATCH')
            need(db.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'STATE_INTEGRITY_FAIL')
            counts = {table: db.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in actual}
        finally:
            db.close()
        after = os.fstat(fd)
        need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) ==
             (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns), 'STATE_CHANGED_DURING_VERIFY')
        result['state'] = {'user_version': 2, 'rows': counts,
                           'sha256': sha(root.read(location + '/state/cherub-state.sqlite3', 0o600))}
    finally:
        if fd >= 0: os.close(fd)
        os.close(parent)
    return result
