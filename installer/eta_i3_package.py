"""Pinned W09 -> deterministic, data-only laboratory package. No code execution."""
from __future__ import annotations
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import zipfile

INPUT_SHA256 = '66b5f9834706762325d977d39aac70c99c6f350d5fd54cadc5ac3f8a676e17bb'
PINS = {
    'agentctl.py': 'a0564e931d4fd3b437613fb204f08e17a2263cfcc372724ac308439c86a5965e',
    'cherub_candidate.py': 'ad9acb05e26b890d6917839312c38ba854ee79d602ec62e8eeb0f74535735f7a',
    'cherub_flow.py': 'e5cd1b7f7f7f1d3e637cbdb62cdfdcddd90841113a7ecaf49f4ad7f76e306255',
    'cherub_state.py': 'ff56156e3904d65bb8bb70091a7b8fa2782d773879afaf16929a60d4a8a87848',
    'cherub_task_contract.py': 'eb2986fcce870bb191ddc50b0e72faaa98676d657b3fda5549b7ecc7746a9d7c',
}
MAX_ARCHIVE = 4 * 1024 * 1024
MAX_ENTRY = 1024 * 1024

class Refusal(ValueError):
    pass

def need(value, message):
    if not value:
        raise Refusal(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def canonical(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                       allow_nan=False) + '\n').encode('ascii')

def json_unique(data):
    def hook(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=hook,
                      parse_constant=lambda value: (_ for _ in ()).throw(Refusal('NONFINITE_JSON')))

def regular_read(path, maximum=MAX_ARCHIVE):
    """Read bounded bytes from an existing non-symlink, non-hardlinked file."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        a = os.fstat(fd)
        need(stat.S_ISREG(a.st_mode) and a.st_nlink == 1, 'INPUT_NOT_SINGLE_REGULAR_FILE')
        need(a.st_size <= maximum, 'INPUT_TOO_LARGE')
        out = bytearray()
        while True:
            part = os.read(fd, min(65536, maximum + 1 - len(out)))
            if not part:
                break
            out.extend(part)
            need(len(out) <= maximum, 'INPUT_TOO_LARGE')
        b = os.fstat(fd)
        need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns) ==
             (b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns,b.st_ctime_ns), 'INPUT_CHANGED')
        need(len(out) == a.st_size, 'INPUT_TRUNCATED')
        return bytes(out)
    finally:
        os.close(fd)

def zip_files(data, exact=None):
    need(len(data) <= MAX_ARCHIVE, 'ARCHIVE_TOO_LARGE')
    out = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        need(len(z.infolist()) <= 64, 'EXCESSIVE_ENTRIES')
        for i in z.infolist():
            name = i.filename
            need(name not in out and not i.is_dir(), 'DUPLICATE_OR_DIRECTORY')
            need(name and not name.startswith('/') and '\\' not in name and
                 all(p not in ('', '.', '..') for p in name.split('/')) and
                 all(32 <= ord(c) < 127 for c in name), 'UNSAFE_ARCHIVE_PATH')
            need(stat.S_IFMT(i.external_attr >> 16) in (0, stat.S_IFREG), 'NONREGULAR_ARCHIVE_ENTRY')
            need(not (i.external_attr >> 16) & 0o7000 and not i.flag_bits & 1, 'UNSAFE_ARCHIVE_FLAGS')
            need(0 <= i.file_size <= MAX_ENTRY, 'ENTRY_TOO_LARGE')
            with z.open(i) as stream:
                body = stream.read(MAX_ENTRY + 1)
            need(len(body) == i.file_size and len(body) <= MAX_ENTRY, 'ENTRY_LENGTH_MISMATCH')
            out[name] = body
            need(sum(map(len, out.values())) <= MAX_ARCHIVE, 'EXPANSION_LIMIT')
    if exact is not None:
        need(set(out) == set(exact), 'ARCHIVE_INVENTORY_MISMATCH')
    return out

def expected_manifest(payload):
    tree = ast.parse(payload['cherub_state.py'])
    schema = None
    app_id = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == '_SCHEMA':
                schema = ast.literal_eval(node.value)
            if node.targets[0].id == '_APP_ID':
                app_id = ast.literal_eval(node.value)
    need(isinstance(schema, dict) and isinstance(app_id, int), 'STATE_SCHEMA_NOT_EXTRACTED')
    source_digest = sha(canonical(PINS))
    return {
        'format': 'eta-i3-scoped-core/1',
        'project': 'ETA_CHERUB_FULL_FREEBSD',
        'release_id': 'w09-v2-' + source_digest[:16],
        'scope': 'FIVE_MODULE_LAB_CORE_NOT_FULL_DISTRIBUTION',
        'target_platform': 'FreeBSD_15.1',
        'install_backend': 'LINUX_DISPOSABLE_ROOT_ONLY',
        'source_input_sha256': INPUT_SHA256,
        'source_manifest_sha256': source_digest,
        'state': {'user_version': 2, 'application_id': app_id, 'tables': schema,
                  'policy': 'FRESH_EMPTY_ONLY_NO_MIGRATION_NO_GRANTS'},
        'files': {name: {'sha256': PINS[name], 'bytes': len(payload[name]), 'mode': '0444'}
                  for name in sorted(PINS)},
        'startup': 'NONE', 'privileged_backend': 'NOT_IMPLEMENTED',
    }

def build_bytes(source_archive):
    need(sha(source_archive) == INPUT_SHA256, 'W09_ARCHIVE_PIN_MISMATCH')
    source = zip_files(source_archive)
    rows = source['MANIFEST_SHA256'].decode('ascii').splitlines()
    observed = {}
    for line in rows:
        digest, name = line.split('  ', 1)
        need(name not in observed and name in source and sha(source[name]) == digest,
             'W09_MANIFEST_MISMATCH')
        observed[name] = digest
    need(set(observed) == set(source) - {'MANIFEST_SHA256'}, 'W09_CLOSED_INVENTORY_MISMATCH')
    payload = {name: source['source/' + name] for name in PINS}
    need(all(sha(payload[n]) == h for n,h in PINS.items()), 'W09_SOURCE_PIN_MISMATCH')
    return pack_payload(payload)

def pack_payload(payload):
    manifest = expected_manifest(payload)
    entries = {'MANIFEST.json': canonical(manifest),
               **{'payload/' + n: payload[n] for n in sorted(PINS)}}
    buff = io.BytesIO()
    with zipfile.ZipFile(buff, 'w', compression=zipfile.ZIP_STORED) as z:
        for name in sorted(entries):
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.create_system = 3
            zi.external_attr = (stat.S_IFREG | 0o444) << 16
            z.writestr(zi, entries[name])
    return buff.getvalue()

def load_package(path, digest):
    need(isinstance(digest, str) and len(digest) == 64 and
         all(c in '0123456789abcdef' for c in digest), 'EXPECTED_SHA256_REQUIRED')
    data = regular_read(path)
    need(sha(data) == digest, 'PACKAGE_SHA256_MISMATCH')
    files = zip_files(data, {'MANIFEST.json', *('payload/' + n for n in PINS)})
    manifest = json_unique(files['MANIFEST.json'])
    payload = {n: files['payload/' + n] for n in PINS}
    need(all(sha(payload[n]) == h for n,h in PINS.items()), 'PAYLOAD_PIN_MISMATCH')
    need(manifest == expected_manifest(payload) and files['MANIFEST.json'] == canonical(manifest),
         'MANIFEST_CONTRACT_MISMATCH')
    return {'manifest': manifest, 'payload': payload, 'sha256': digest}
