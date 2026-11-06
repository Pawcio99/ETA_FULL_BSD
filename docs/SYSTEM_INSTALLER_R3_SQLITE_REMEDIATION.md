# ETA_CHERUB FULL FreeBSD 15.1 — R3 root-installer source correction

2026-11-06. **Candidate / source-only**. Previous R2 commit `c3f360fde40c05dab4a75841dcbee0730583155f`. This change fixes two findings from the exact R2 Codex Code Review on PR #3: P1 at the DB file locking boundary and P2 at `recover('abort')`. It does NOT authorize host installation, root-staging R3, SQLite migration, service activation, grants or merger.

## Actual R2 fault

P1: `database_lock` and `create_state` used OS `flock` on the same SQLite database file while a separate SQLite connection used its own POSIX locking. On FreeBSD these can conflict. See https://man.freebsd.org/cgi/man.cgi?query=flock&sektion=2 and https://sqlite.org/lockingv3.html .

P2: Reproduced on unchanged R2 source and actual offhost SQLite: after crash at `after_database`, journal remained STAGED, then one row was inserted in `projects`. R2 `plan('abort')` succeeded; `recover('abort')` moved staged code with the database still nonempty. No data was deleted in the fixture, but the safety guard was bypassed. The reproducer never used the FreeBSD host.

## R3 delta

- `installer/eta_system_install.py`: candidate3, expected SHA-256 `b3c9e4d984c2e5851d8e52a8f7831718b99da2280e9ea442379b8aa560591dc8`, GitHub blob SHA1 `afa829df96d2a5173e46265da08a40d5d26f26c4`.
- No `flock` on SQLite file. Existing installer-wide `.writer.lock` remains separate. SQLite `BEGIN EXCLUSIVE` protects creation and withdraw/abort, and `BEGIN` protects read-only checks. Queries reuse the same connection holding the lease. All leases use `PRAGMA trusted_schema=OFF` and `query_only` after the EXCLUSIVE lock is obtained. Native platform restrictions remain.
- `plan('abort')` checks any existing DB regardless of event name, includes DB identity and its verification digest in the signed-by-hash plan. `recover('abort')` rechecks under SQLite EXCLUSIVE lock through code rename and event commit. Nonempty DB or competing writer => refuse. Partial or absent DB after STAGED => refuse automatic abort, retain all bytes for manual reconciliation. No retry or budget refund.
- `tests/test_system_installer.py`: 83 methods, SHA-256 `ce5d90348ef93f555bd42f1eb8a796eafac56efbff1acf0031e89bd6c14fcc9e`, GitHub blob `7bb79abc7ab510f73e5512b26ba10cd6c91fd1bd`. Includes direct competing SQLite process and P2 regression with real files. No product task/model launched.
- `tools/native_sqlite_lock_probe_r3.py`: SHA-256 `95a015b5facfe00b1dbc4d932c39db6bfc4e3f717e7627ce5fc4129522ab6cf1`, blob `9a76b706464b890fb0fde7e382b861020147cca5`. Diagnostic for ordinary UID: creates a fresh private SQLite fixture only in ~/Downloads; no product or root operations.
- Pinned private W09 payload is **unchanged**, SHA-256 `023cfa3776f37d9911a18661ff0d6920e3aa68476467b6a5eaeecb209a532b41`.

## Actual tests and evidence

Linux/Python3.13.5/SQLite3.46.1, UID/GID65534, groups empty, CapEff0, NoNewPrivs1. **83/83 PASS, exit0**. Full installer engine, DB and FS in disposable directories; 7 actual process-interruption checks. External child SQLite lock refusal while an exclusive lease is held, release to success, no mutation of DB under verify lease, R2 P2 fail-open reproduction and R3 nonempty/locked/corrupt/absent DB refusals. Native probe on Linux PASS. AST Python3.12 PASS, shell syntax PASS. A private ZIP with source/test/logs/patches/manifest has SHA-256 `c8198aa6f3ed283c3c1aec8a8ed6898a4d182c5678157b96ad5879c45078205b`, 15 entries, 14/14 manifest. This ZIP and W09 payload are **not** committed to this public repo.

## Gates / next step

`R2_NATIVE_READONLY_INSPECT_PLAN=PASS_REPORTED`; `R2_ROOT_OWNED_STAGING=PASS_REPORTED` for 3 files only; `R3_OFFHOST_TESTS=PASS_83_OF_83`; `R3_NATIVE_SQLITE_PROBE=NOT_TESTED`; `R3_NATIVE_INSPECT_PLAN=NOT_TESTED`; `R3_ROOT_STAGE=NOT_PERFORMED_NOT_AUTHORIZED`; `R3_ROOT_INSTALL=NOT_PERFORMED_NOT_AUTHORIZED`; `R3_FINAL_VALIDATOR_AND_SECURITY_REVIEWS=NOT_PERFORMED`.

First, independently review this frozen R3 commit and run the non-root *fresh disposable* SQLite probe on FreeBSD 15.1. Then native read-only inspect/plan as ordinary user. If admitted, submit a NEW exact request to stage R3 under a separate root-owned directory (do not overwrite R2), and later a different request for inactive installation. Old R2 plan hash is invalid for R3; do not execute R2 as root. PR stays DRAFT; no auto merge or source migration. No full G0/G1/G2/G7 acceptance.
