#!/usr/bin/env python3
"""ETA I3 M0/M1: non-root Linux disposable-root installation adapter.

Not a host installer, broker, grant, service manager or FULL distribution.
Use python3 -I -B; CLI bootstrap adds only its reviewed sibling-tool directory.
Only the pinned StateLedger constructor is executed to create NEW empty v2 state.
No main(), dispatch, task execution, migration, service or privileged operation.
"""
from __future__ import annotations
import sys
from pathlib import Path
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).absolute().parent))
import argparse
import fcntl
import importlib.util
import json
import os
import sqlite3
import stat
import uuid
from eta_i3_package import Refusal, need, canonical, json_unique, sha, load_package, build_bytes, regular_read
from eta_i3_fs import Root, initialize, guard, private
from eta_i3_verify import inspect_image

STATES = {'STAGING', 'STAGED', 'APPLYING', 'INSTALLED_UNVERIFIED', 'VERIFIED',
          'ROLLING_BACK', 'ROLLED_BACK', 'ABORTING', 'ABORTED'}

def noop(_):
    pass

def record(root, package, *, pending_ok=False):
    need(pending_ok or not root.exists('.next-record'), 'RECOVERY_REQUIRED_PENDING_RECORD')
    if not root.exists('transaction.json'):
        return None
    value = json_unique(root.read('transaction.json', 0o600))
    need(set(value) == {'format','state','package_sha256','release_id','scope'} and
         value['format'] == 'eta-i3-install-receipt/1' and value['state'] in STATES and
         value['scope'] == 'DISPOSABLE_ROOT_ONLY_NOT_ADMISSION', 'INSTALL_RECEIPT_INVALID')
    need(value['package_sha256'] == package['sha256'] and
         value['release_id'] == package['manifest']['release_id'], 'EXISTING_PACKAGE_CONFLICT')
    return value

def write_record(root, package, state, fault=noop):
    root.replace_record({'format': 'eta-i3-install-receipt/1', 'state': state,
        'package_sha256': package['sha256'], 'release_id': package['manifest']['release_id'],
        'scope': 'DISPOSABLE_ROOT_ONLY_NOT_ADMISSION'}, fault)

def empty_lab(root):
    need(set(os.listdir(root.fd)) == {'.eta-i3-lab.json', '.mutation.lock'}, 'LAB_NOT_EMPTY')

def package_plan(package, lab):
    guard()
    with Root(lab) as root:
        previous = record(root, package)
        if previous is None:
            empty_lab(root)
        else:
            need(previous['state'] in ('STAGED', 'VERIFIED'), 'RECOVERY_OR_NEW_LAB_REQUIRED')
        return {'result': 'PLANNED_NO_WRITES', 'root': str(root.path),
            'package_sha256': package['sha256'], 'release_id': package['manifest']['release_id'],
            'previous_state': previous['state'] if previous else 'EMPTY',
            'source_files': {('image/product/tools/' + n): v for n,v in package['manifest']['files'].items()},
            'planned_state': 'image/state/cherub-state.sqlite3',
            'state_policy': 'CREATE_NEW_EMPTY_V2_ONLY',
            'installation_metadata': ['.stage', 'transaction.json', '.next-record', 'image/PACKAGE.json'],
            'rollback': 'RENAME_IMAGE_TO_RETAINED_DIRECTORY_NO_DATA_DELETION',
            'schema_migration': 'DENIED', 'services_or_product_started': False,
            'native_backend': 'NOT_IMPLEMENTED', 'grant': 'NONE'}

def stage(package, lab, *, fault=noop):
    with Root(lab, exclusive=True) as root:
        before = record(root, package)
        if before is not None:
            if before['state'] == 'STAGED':
                result = inspect_image(root, package, '.stage', require_state=False)
                return {**result, 'result': 'STAGED_IDEMPOTENT_NO_WRITES'}
            if before['state'] == 'VERIFIED':
                result = inspect_image(root, package)
                return {**result, 'result': 'ALREADY_INSTALLED_NO_WRITES'}
            raise Refusal('RECOVERY_OR_NEW_LAB_REQUIRED')
        empty_lab(root)
        write_record(root, package, 'STAGING', fault)
        root.mkdir('.stage')
        root.mkdir('.stage/product'); root.mkdir('.stage/product/tools')
        for name, data in sorted(package['payload'].items()):
            root.write_new('.stage/product/tools/' + name, data)
            fault('after_file_' + name)
        root.write_new('.stage/PACKAGE.json', canonical(package['manifest']))
        inspect_image(root, package, '.stage', require_state=False)
        write_record(root, package, 'STAGED', fault)
        return {'result': 'STAGED', 'package_sha256': package['sha256'], 'state_created': False}

def _new_state(root, package):
    root.mkdir('.stage/state')
    source = root.path / '.stage/product/tools/cherub_state.py'
    need(sha(root.read('.stage/product/tools/cherub_state.py')) ==
         package['manifest']['files']['cherub_state.py']['sha256'], 'STATE_CODE_PIN_CHANGED')
    spec = importlib.util.spec_from_file_location('eta_i3_pinned_state_' + uuid.uuid4().hex, source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Existing API, no initialization of projects, epochs, grants or budgets.
    with module.StateLedger(root.path / '.stage/state', create=True):
        pass
    fd = os.open(root.path / '.stage/state', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)

def apply(package, lab, *, fault=noop):
    with Root(lab, exclusive=True) as root:
        before = record(root, package)
        need(before is not None, 'STAGE_REQUIRED')
        if before['state'] == 'VERIFIED':
            return {**inspect_image(root, package), 'result': 'INSTALLED_IDEMPOTENT_NO_WRITES'}
        need(before['state'] == 'STAGED' and not root.exists('image'), 'RECOVERY_REQUIRED')
        inspect_image(root, package, '.stage', require_state=False)
        write_record(root, package, 'APPLYING', fault)
        _new_state(root, package)
        fault('after_database')
        checked = inspect_image(root, package, '.stage')
        need(not any(checked['state']['rows'].values()), 'NEW_STATE_NOT_EMPTY')
        root.rename_top('.stage', 'image')
        fault('after_publish')
        write_record(root, package, 'INSTALLED_UNVERIFIED', fault)
        checked = inspect_image(root, package)
        write_record(root, package, 'VERIFIED', fault)
        return {**checked, 'result': 'INSTALLED_AND_READBACK_VERIFIED',
                'state_initialized_using': 'EXISTING_STATELEDGER_CREATE_TRUE'}

def verify(package, lab):
    with Root(lab) as root:
        return inspect_image(root, package)

def status(package, lab):
    with Root(lab) as root:
        previous = record(root, package, pending_ok=True)
        if root.exists('.next-record'):
            return {'result': 'RECOVERY_REQUIRED', 'reason': 'PENDING_RECORD', 'receipt': previous}
        if previous is None:
            empty_lab(root)
            return {'result': 'EMPTY_LAB'}
        state = previous['state']
        if state == 'VERIFIED':
            return {**inspect_image(root, package), 'result': 'VERIFIED_LAB_ONLY'}
        if state == 'STAGED':
            return {**inspect_image(root, package, '.stage', require_state=False), 'result': 'STAGED'}
        if state == 'ROLLED_BACK':
            need(not root.exists('image') and root.exists('retained-image'), 'ROLLBACK_LAYOUT_MISMATCH')
            return {**inspect_image(root, package, 'retained-image'), 'result': 'ROLLED_BACK_STATE_RETAINED'}
        if state == 'ABORTED':
            need(not root.exists('image') and not root.exists('.stage'), 'ABORT_LAYOUT_MISMATCH')
            return {'result': 'ABORTED_PARTIAL_RETAINED', 'package_sha256': package['sha256']}
        return {'result': 'RECOVERY_REQUIRED', 'receipt': previous}

def rollback(package, lab, *, fault=noop):
    with Root(lab, exclusive=True) as root:
        previous = record(root, package)
        need(previous is not None, 'NOT_INSTALLED')
        if previous['state'] == 'ROLLED_BACK':
            need(not root.exists('image'), 'ROLLBACK_LAYOUT_MISMATCH')
            return {**inspect_image(root, package, 'retained-image'), 'result': 'ROLLED_BACK_IDEMPOTENT'}
        need(previous['state'] == 'VERIFIED' and not root.exists('retained-image'), 'RECOVERY_REQUIRED')
        checked = inspect_image(root, package)
        need(not any(checked['state']['rows'].values()), 'STATE_IN_USE_REQUIRES_EXTERNAL_RECONCILIATION')
        parent, name = root.parent('image/state/cherub-state.sqlite3')
        fd = -1
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Recheck under the database writer lock, before renaming either code or data.
            need(sha(root.read('image/state/cherub-state.sqlite3', 0o600)) == checked['state']['sha256'],
                 'STATE_CHANGED_BEFORE_ROLLBACK')
            write_record(root, package, 'ROLLING_BACK', fault)
            root.rename_top('image', 'retained-image')
            fault('after_rollback_move')
            need(sha(root.read('retained-image/state/cherub-state.sqlite3', 0o600)) == checked['state']['sha256'],
                 'STATE_CHANGED_DURING_ROLLBACK')
            write_record(root, package, 'ROLLED_BACK', fault)
        finally:
            if fd >= 0: os.close(fd)
            os.close(parent)
        return {'result': 'ROLLED_BACK_STATE_RETAINED', 'package_sha256': package['sha256'],
                'state_sha256_before': checked['state']['sha256'],
                'state_sha256_after': checked['state']['sha256'], 'files_deleted': 0}

def recover(package, lab, decision):
    """Explicit operator decision; never repeat an interrupted StateLedger create."""
    need(decision in ('abort-stage', 'complete-image', 'complete-rollback'), 'INVALID_RECOVERY_DECISION')
    with Root(lab, exclusive=True) as root:
        previous = record(root, package, pending_ok=True)
        need(previous is not None, 'NO_RECORDED_OPERATION')
        pending = root.exists('.next-record')
        if pending:
            nxt = json_unique(root.read('.next-record', 0o600))
            need(nxt.get('package_sha256') == package['sha256'] and nxt.get('state') in STATES,
                 'INVALID_PENDING_RECORD')
        if decision == 'complete-image':
            need(previous['state'] in ('APPLYING', 'INSTALLED_UNVERIFIED') and
                 root.exists('image') and not root.exists('.stage'), 'IMAGE_RECOVERY_NOT_APPLICABLE')
            checked = inspect_image(root, package)
            need(not any(checked['state']['rows'].values()), 'RECOVERY_STATE_NOT_EMPTY')
            if pending: root.rename_top('.next-record', 'retained-pending-' + uuid.uuid4().hex)
            write_record(root, package, 'VERIFIED')
            return {**checked, 'result': 'RECOVERED_VERIFIED_WITHOUT_RERUN'}
        if decision == 'complete-rollback':
            need(previous['state'] == 'ROLLING_BACK' and not root.exists('image') and
                 root.exists('retained-image'), 'ROLLBACK_RECOVERY_NOT_APPLICABLE')
            checked = inspect_image(root, package, 'retained-image')
            need(not any(checked['state']['rows'].values()), 'RECOVERY_STATE_NOT_EMPTY')
            if pending: root.rename_top('.next-record', 'retained-pending-' + uuid.uuid4().hex)
            write_record(root, package, 'ROLLED_BACK')
            return {**checked, 'result': 'RECOVERED_ROLLBACK_STATE_RETAINED'}
        need(previous['state'] in ('STAGING', 'STAGED', 'APPLYING', 'ABORTING') and
             not root.exists('image'), 'ABORT_NOT_APPLICABLE')
        need(root.exists('.stage') or root.exists('retained-partial'), 'NO_PARTIAL_STAGE')
        if root.exists('.stage'): root.tree('.stage')  # refuse links and unbounded/foreign content
        if pending: root.rename_top('.next-record', 'retained-pending-' + uuid.uuid4().hex)
        write_record(root, package, 'ABORTING')
        if root.exists('.stage'): root.rename_top('.stage', 'retained-partial')
        write_record(root, package, 'ABORTED')
        return {'result': 'ABORTED_PARTIAL_RETAINED', 'files_deleted': 0}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init-lab'); init.add_argument('--workspace')
    build = sub.add_parser('build-package')
    build.add_argument('--w09-archive', required=True); build.add_argument('--output', required=True)
    for name in ('plan', 'stage', 'apply', 'verify', 'status', 'rollback', 'recover'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--package', required=True); cmd.add_argument('--sha256', required=True)
        cmd.add_argument('--lab-root', required=True)
        if name in ('stage', 'apply', 'rollback', 'recover'):
            cmd.add_argument('--allow-disposable-writes', action='store_true', required=True)
        if name == 'recover':
            cmd.add_argument('--decision', choices=('abort-stage','complete-image','complete-rollback'), required=True)
    args = parser.parse_args(argv)
    try:
        guard()
        if args.command == 'init-lab':
            result = {'result': 'PRIVATE_EMPTY_LAB_CREATED', 'lab_root': initialize(args.workspace)}
        elif args.command == 'build-package':
            data = build_bytes(regular_read(args.w09_archive))
            # Build is not a plan operation. Existing output is never overwritten.
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(fd, 'wb') as f:
                    f.write(data); f.flush(); os.fsync(f.fileno())
            except BaseException:
                raise
            result = {'result': 'PACKAGE_CREATED', 'sha256': sha(data), 'bytes': len(data)}
        else:
            package = load_package(args.package, args.sha256)
            actions = {'plan': package_plan, 'stage': stage, 'apply': apply, 'verify': verify,
                       'status': status, 'rollback': rollback}
            result = (recover(package, args.lab_root, args.decision) if args.command == 'recover'
                      else actions[args.command](package, args.lab_root))
        print(json.dumps(result, sort_keys=True, ensure_ascii=True))
        return 20 if result.get('result') == 'RECOVERY_REQUIRED' else 0
    except (Refusal, OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'result': 'BLOCKED', 'reason': str(exc), 'native_installation': False,
                          'grant': 'NONE'}, sort_keys=True))
        return 20

if __name__ == '__main__':
    raise SystemExit(main())
