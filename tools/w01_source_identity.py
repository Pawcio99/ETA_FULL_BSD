#!/usr/bin/env python3
"""ETA FULL BSD W01: bounded, fail-closed, read-only source evidence.

This script hashes *only* explicitly selected relative regular files. It makes
no source mutation, launch, admission, network request, or Git write. stdout
JSON is not a grant or proof of runtime isolation. Invoke with python -B.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import sys

MAX_FILES = 64
MAX_BYTES_PER_FILE = 32 * 1024 * 1024
HEX64 = re.compile(r"[a-fA-F0-9]{64}\Z")


class Refusal(Exception):
    pass


def parts(value, absolute=False):
    if not isinstance(value, str) or not value:
        raise Refusal("EMPTY_PATH")
    if absolute != value.startswith("/"):
        raise Refusal("PATH_SCOPE")
    bits = value.split("/")
    if absolute:
        bits = bits[1:]
    if not bits or any(s in ("", ".", "..") or "\x00" in s for s in bits):
        raise Refusal("NONCANONICAL_PATH")
    return bits


def open_directory(parent_fd, component):
    return os.open(
        component,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        dir_fd=parent_fd,
    )


def open_root(root):
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in parts(root, absolute=True):
            child = open_directory(fd, component)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def digest_regular(root_fd, relative):
    components = parts(relative)
    base = os.dup(root_fd)
    try:
        for part in components[:-1]:
            nxt = open_directory(base, part)
            os.close(base)
            base = nxt
        name = components[-1]
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=base)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise Refusal("NOT_REGULAR_FILE")
            if before.st_size > MAX_BYTES_PER_FILE:
                raise Refusal("FILE_TOO_LARGE")
            sha = hashlib.sha256()
            count = 0
            while True:
                block = os.read(fd, 65536)
                if not block:
                    break
                count += len(block)
                if count > MAX_BYTES_PER_FILE:
                    raise Refusal("FILE_TOO_LARGE")
                sha.update(block)
            after = os.fstat(fd)
            path_after = os.stat(name, dir_fd=base, follow_symlinks=False)
            identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
            if identity(before) != identity(after) or identity(after) != identity(path_after) or count != before.st_size:
                raise Refusal("SOURCE_CHANGED_DURING_READ")
            if not stat.S_ISREG(path_after.st_mode):
                raise Refusal("PATH_REPLACED")
            return {"sha256": sha.hexdigest(), "bytes": count}
        finally:
            os.close(fd)
    finally:
        os.close(base)


def inspect(args):
    selection = list(args.file)
    for other in (args.manifest, args.checkpoint):
        if other and other not in selection:
            selection.append(other)
    if not selection or len(selection) > MAX_FILES or len(selection) != len(set(selection)):
        raise Refusal("INVALID_FILE_SET")
    for path in selection:
        parts(path)
    expected = {}
    for entry in args.expect:
        if "=" not in entry:
            raise Refusal("INVALID_EXPECTATION")
        path, value = entry.rsplit("=", 1)
        parts(path)
        if path not in selection or not HEX64.fullmatch(value) or path in expected:
            raise Refusal("INVALID_EXPECTATION")
        expected[path] = value.lower()
    root_fd = open_root(args.source_root)
    try:
        files = {}
        for path in selection:
            files[path] = digest_regular(root_fd, path)
    finally:
        os.close(root_fd)
    mismatched = [path for path, digest in expected.items() if files[path]["sha256"] != digest]
    return {
        "schema": "eta-full-bsd-w01-source-evidence/1",
        "mode": "READ_ONLY_OBSERVATION_NOT_ADMISSION",
        "source_root": args.source_root,
        "selected_file_count": len(selection),
        "files": files,
        "manifest_path": args.manifest,
        "checkpoint_path": args.checkpoint,
        "expected_hash_count": len(expected),
        "mismatched": mismatched,
        "complete_tree_attested": False,
        "git_commit_attested": False,
        "active_mandate_attested": False,
        "current_host_attested": False,
        "g0": "BLOCKED_PENDING_W01_W04_EVIDENCE",
        "result": "MISMATCH" if mismatched else "PASS_SELECTED_FILES_ONLY",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, help="canonical absolute source directory")
    parser.add_argument("--file", action="append", default=[], help="explicit relative source file (repeat)")
    parser.add_argument("--manifest", help="optional relative manifest file to hash (not execute)")
    parser.add_argument("--checkpoint", help="optional relative checkpoint file to hash (not execute)")
    parser.add_argument("--expect", action="append", default=[], help="relative/path=64hex for historical pin comparison")
    opts = parser.parse_args(argv)
    try:
        report = inspect(opts)
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
        return 0 if not report["mismatched"] else 20
    except (Refusal, OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"schema": "eta-full-bsd-w01-source-evidence/1", "result": "BLOCKED", "reason": str(exc), "mode": "READ_ONLY_OBSERVATION_NOT_ADMISSION"}, ensure_ascii=True, sort_keys=True))
        return 21


if __name__ == "__main__":
    sys.exit(main())
