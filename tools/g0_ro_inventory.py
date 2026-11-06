#!/usr/bin/env python3
"""ETA_FULL_BSD G0: bounded metadata-only source/candidate inventory.

No product imports, no Git commands, no state DB reads, no host mutations.
Regular manifest-like files are SHA-256 hashed but their contents are NEVER
printed. Privileged/secret directories are not traversed. Exit 0 is NOT G0.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import sys

MAX_ROOTS = 5
MAX_VISITS = 850
MAX_MATCHES = 80
MAX_BYTES = 1024 * 1024
DEFAULT_DEPTH = 4
SKIP = frozenset({
    '.git', '.venv', '.cache', '__pycache__', 'node_modules', 'state',
    'secrets', 'secret', 'private', 'credentials', 'receipts',
    'evidence', 'tmp', 'work', 'logs', 'run', '.snapshots',
})
MARKER = re.compile(r'(manifest|checkpoint|source_identity|source_pin|\bpin\b|\bfreeze\b)', re.I)
ROLE_FILES = {
    'installed': (),  # The four product modules have already been verified.
    'conductor': (
        '08_MODEL_PRACY_MK1/RUN.sh', '06_EDITABLE/agents.json',
        '06_EDITABLE/policy/ROOT_CONDUCTOR.md',
    ),
    'z1': (
        'tools/agentctl.py', 'tools/cherub_task_contract.py',
        'tools/cherub_candidate.py', 'tools/cherub_flow.py',
    ),
    'staging2': ('product/tools/agentctl.py', 'tools/agentctl.py'),
    'df01': ('tools/agentctl.py', 'tools/cherub_flow.py'),
}


class Refusal(Exception):
    pass


def components(value, absolute=False):
    if not isinstance(value, str) or not value or value.startswith('/') != absolute:
        raise Refusal('PATH_SCOPE')
    seq = value.split('/')[1:] if absolute else value.split('/')
    if not seq or any(x in ('', '.', '..') or '\x00' in x or '\n' in x for x in seq):
        raise Refusal('NONCANONICAL_PATH')
    return seq


def open_dir(base, name):
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=base)


def open_abs_dir(path):
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in components(path, absolute=True):
            new = open_dir(fd, part)
            os.close(fd)
            fd = new
        return fd
    except BaseException:
        os.close(fd)
        raise


def open_rel_parent(root, relative):
    seq = components(relative)
    fd = os.dup(root)
    try:
        for part in seq[:-1]:
            new = open_dir(fd, part)
            os.close(fd)
            fd = new
        return fd, seq[-1]
    except BaseException:
        os.close(fd)
        raise


def sha_regular(parent_fd, filename):
    fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise Refusal('NOT_REGULAR')
        if before.st_size > MAX_BYTES:
            raise Refusal('SIZE_LIMIT')
        length = 0
        h = hashlib.sha256()
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            length += len(chunk)
            if length > MAX_BYTES:
                raise Refusal('SIZE_LIMIT')
            h.update(chunk)
        after = os.fstat(fd)
        identity = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        pathstat = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(pathstat.st_mode) or identity(before) != identity(after) or identity(after) != identity(pathstat) or length != before.st_size:
            raise Refusal('RACE_OR_REPLACEMENT')
        return {'sha256': h.hexdigest(), 'bytes': length}
    finally:
        os.close(fd)


def explicit(root_fd, path):
    try:
        parent, name = open_rel_parent(root_fd, path)
        try:
            return {'status': 'HASHED', **sha_regular(parent, name)}
        finally:
            os.close(parent)
    except FileNotFoundError:
        return {'status': 'ABSENT'}
    except (PermissionError, OSError, Refusal) as err:
        return {'status': 'BLOCKED', 'error_type': type(err).__name__}


def walk(root_fd, depth):
    pending = [(os.dup(root_fd), '', 0)]
    markers, issues = {}, []
    visit_count = 0
    try:
        while pending:
            fd, prefix, level = pending.pop()
            try:
                names = sorted(os.listdir(fd))
                for name in names:
                    visit_count += 1
                    if visit_count > MAX_VISITS:
                        issues.append('VISIT_LIMIT')
                        return markers, issues, visit_count
                    if name in SKIP:
                        continue
                    rel = f'{prefix}/{name}' if prefix else name
                    try:
                        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    except (OSError, ValueError):
                        issues.append('STAT_REFUSED')
                        continue
                    if stat.S_ISLNK(st.st_mode):
                        continue
                    if stat.S_ISDIR(st.st_mode):
                        if level < depth:
                            try:
                                pending.append((open_dir(fd, name), rel, level + 1))
                            except OSError:
                                issues.append('DIR_REFUSED')
                    elif stat.S_ISREG(st.st_mode) and MARKER.search(name):
                        if len(markers) >= MAX_MATCHES:
                            issues.append('MATCH_LIMIT')
                            return markers, issues, visit_count
                        try:
                            markers[rel] = {'status': 'HASHED', **sha_regular(fd, name)}
                        except (OSError, Refusal):
                            markers[rel] = {'status': 'BLOCKED'}
            finally:
                os.close(fd)
        return markers, issues, visit_count
    finally:
        for fd, _, _ in pending:
            os.close(fd)


def inspect(items, depth):
    roots, missing = {}, []
    for key, path in items:
        try:
            fd = open_abs_dir(path)
        except (OSError, Refusal) as err:
            roots[key] = {'status': 'UNAVAILABLE', 'error_type': type(err).__name__}
            missing.append(key)
            continue
        try:
            st = os.fstat(fd)
            try:
                gitstat = os.stat('.git', dir_fd=fd, follow_symlinks=False)
                git_kind = ('DIR' if stat.S_ISDIR(gitstat.st_mode) else 'FILE' if stat.S_ISREG(gitstat.st_mode) else 'OTHER')
            except FileNotFoundError:
                git_kind = 'ABSENT'
            except OSError:
                git_kind = 'NOT_READABLE'
            selected = {file: explicit(fd, file) for file in ROLE_FILES[key]}
            marks, issues, visited = walk(fd, depth)
            roots[key] = {
                'status': 'PRESENT', 'filesystem_identity': {'device': st.st_dev, 'inode': st.st_ino},
                'git_metadata_type': git_kind, 'git_head': 'NOT_ATTESTED',
                'selected_new_checks': selected, 'marker_metadata': marks,
                'walk_items_seen': visited, 'scan_issues': issues,
            }
            if issues:
                missing.append(key)
        finally:
            os.close(fd)
    return {
        'schema': 'eta-full-bsd-g0-bounded-inventory/1',
        'mode': 'READ_ONLY_METADATA_NOT_ADMISSION',
        'roots': roots, 'observed_root_labels': [x[0] for x in items],
        'not_fully_inspected': missing,
        'secrets_or_runtime_state_read': False,
        'current_git_head_attested': False,
        'active_mandate_attested': False,
        'w01_selected_files_prior': 'PASS_4_OF_4_NOT_RETESTED',
        'w01_full_source_identity': 'BLOCKED', 'g0': 'BLOCKED',
        'result': 'PARTIAL' if missing else 'METADATA_INVENTORY_ONLY',
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', action='append', required=True, help='known_label=/canonical/absolute/path; labels: installed,conductor,z1,staging2,df01')
    ap.add_argument('--depth', type=int, default=DEFAULT_DEPTH)
    ns = ap.parse_args(argv)
    try:
        if not 1 <= len(ns.root) <= MAX_ROOTS or not 0 <= ns.depth <= 5:
            raise Refusal('BOUNDS')
        entries = []
        for pair in ns.root:
            if '=' not in pair:
                raise Refusal('INPUT_FORMAT')
            label, path = pair.split('=', 1)
            if label not in ROLE_FILES or label in [x[0] for x in entries]:
                raise Refusal('LABEL')
            components(path, absolute=True)
            entries.append((label, path))
        report = inspect(entries, ns.depth)
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
        return 20 if report['result'] == 'PARTIAL' else 0
    except (Refusal, OSError, ValueError) as err:
        print(json.dumps({'result': 'BLOCKED', 'reason': str(err), 'g0': 'BLOCKED'}, sort_keys=True))
        return 21


if __name__ == '__main__':
    sys.exit(main())
