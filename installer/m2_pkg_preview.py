#!/usr/bin/env python3
"""ETA I3 M2: deterministic FreeBSD pkg CREATE-ONLY input; no native apply.

Uses the existing eta_i3_package.load_package intake and its pinned W09 hashes.
No installation, no extraction to the host filesystem, no code execution,
no SQLite initialization and no grant. Refuses root/non-Linux, on purpose.
The returned archive is an input blueprint, NOT a FreeBSD pkg artifact.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import zipfile

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from eta_i3_package import Refusal, PINS, load_package, need

ZIP_PIN = '023cfa3776f37d9911a18661ff0d6920e3aa68476467b6a5eaeecb209a532b41'
PKG_NAME = 'eta-full-bsd-five-module-preview'
PKG_VERSION = '0.0.0_1'
FREEBSD_ABI = 'FreeBSD:15:amd64'
PREFIX = '/usr/local'
STAGE_SUBPATH = 'share/eta-full-bsd-five-module-preview/tools'
STAGE_PARENT = 'stage/usr/local/' + STAGE_SUBPATH
DESCRIPTION = (
    'BUILD-ONLY five-module ETA W09 core packaging preview. '
    'Not a complete ETA FULL distribution; do not install or run.'
)
README = '''# ETA M2 / FreeBSD 15.1 — BUILD-ONLY input

This ZIP is not a FreeBSD pkg and is NOT approved for installation.
It contains five pinned Python source files below stage/usr/local/share/
eta-full-bsd-five-module-preview/tools/ and a +MANIFEST for review.
The prefix intentionally avoids the active product /usr/local/libexec/eta-cherub-full.
No state, grant, broker, service, rc script, hook or VM configuration is included.

BUILD INPUT (requires separately admitted native FreeBSD environment):
- Inspect every member, hash and path before extraction.
- Materialize the STAGE directory only into an operator-approved empty private workspace.
- Use FreeBSD 15.1 pkg-create(8): `pkg create -n -r STAGE -M +MANIFEST -o OUTPUT`.
- Verify generated package independently. Installation and source execution are forbidden.

The package metadata uses a non-distribution maintainer placeholder and a
non-product package name. A real release must resolve maintainer, license,
full source dependency graph, Python 3.12 dependency, origin, and real paths.
Any native build-only command, filesystem materialization, or pkg invocation
requires a separately approved exact-scope work order.
'''

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True, allow_nan=False) + '\n').encode('ascii')

def manifest_for(package: dict) -> dict:
    need(package['manifest']['scope'] == 'FIVE_MODULE_LAB_CORE_NOT_FULL_DISTRIBUTION',
         'NOT_PINNED_FIVE_MODULE_INPUT')
    need(package['manifest']['state']['user_version'] == 2, 'STATE_VERSION_NOT_V2')
    payload = package['payload']
    need(set(payload) == set(PINS), 'SOURCE_FILE_SET_MISMATCH')
    files = {}
    for name in sorted(PINS):
        data = payload[name]
        need(sha(data) == PINS[name] and
             package['manifest']['files'][name]['bytes'] == len(data),
             'SOURCE_PIN_OR_SIZE_MISMATCH')
        files[PREFIX + '/' + STAGE_SUBPATH + '/' + name] = PINS[name]
    return {
        'name': PKG_NAME,
        'version': PKG_VERSION,
        'origin': 'devel/' + PKG_NAME,
        'comment': 'BUILD-ONLY preview; not complete ETA FULL',
        'desc': DESCRIPTION,
        'maintainer': 'not-for-distribution@example.invalid',
        'www': 'https://github.com/Pawcio99/ETA_FULL_BSD',
        'prefix': PREFIX,
        'arch': FREEBSD_ABI,
        'abi': FREEBSD_ABI,
        'flatsize': sum(len(payload[name]) for name in PINS),
        'files': files,
        'annotations': {'eta_scope': 'NOT_INSTALLABLE_FULL',
                        'eta_native_build': 'NOT_YET_TESTED'},
    }

def build_bytes(package: dict) -> bytes:
    manifest = manifest_for(package)
    paths = {'+MANIFEST': canonical(manifest),
             'README_BUILD_ONLY.md': README.encode('utf-8'),
             'PACKAGE_INTAKE_SHA256': (package['sha256'] + '  ETA_W09_CORE_LAB_R1.zip\n').encode('ascii')}
    for name, data in package['payload'].items():
        paths[STAGE_PARENT + '/' + name] = data
    hash_list = ''.join(f'{sha(paths[STAGE_PARENT + "/" + name])}  {STAGE_PARENT}/{name}\n'
                        for name in sorted(PINS))
    paths['STAGE_SOURCE_SHA256SUMS'] = hash_list.encode('ascii')
    buff = io.BytesIO()
    with zipfile.ZipFile(buff, 'w', compression=zipfile.ZIP_STORED) as dst:
        for path in sorted(paths):
            need(not path.startswith('/') and '..' not in path.split('/'), 'UNSAFE_PREVIEW_PATH')
            info = zipfile.ZipInfo(path, date_time=(1980,1,1,0,0,0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o444) << 16
            dst.writestr(info, paths[path])
    return buff.getvalue()

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        need(sys.platform.startswith('linux') and os.getuid() == os.geteuid() != 0,
             'NONROOT_OFFHOST_LINUX_REQUIRED')
        need(sys.dont_write_bytecode, 'PYTHON_NO_BYTECODE_REQUIRED')
        need(args.sha256 == ZIP_PIN, 'W09_CORE_PACKAGE_PIN_REQUIRED')
        package = load_package(Path(args.package), args.sha256)
        data = build_bytes(package)
        out = Path(args.output)
        need(out.is_absolute() and out.parent.is_dir(), 'OUTPUT_MUST_HAVE_EXISTING_PARENT')
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        print(json.dumps({'result':'BUILD_ONLY_PREVIEW_CREATED',
            'preview_sha256':sha(data),'preview_bytes':len(data),
            'source_files':len(PINS),'native_pkg_create':'NOT_EXECUTED',
            'native_install':'NOT_AUTHORIZED','full_distribution':False},
            sort_keys=True))
        return 0
    except (Refusal, ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        print(json.dumps({'result':'BLOCKED','reason':str(exc),'native_pkg_create':'NOT_EXECUTED'},sort_keys=True))
        return 20

if __name__ == '__main__':
    raise SystemExit(main())
