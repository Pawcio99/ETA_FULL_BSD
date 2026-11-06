# ETA FreeBSD system installer R4 — SQLite POSIX lock lifetime

Date: 2026-11-06. **SOURCE-ONLY CANDIDATE / NOT NATIVE-ACCEPTED**. Project ETA_CHERUB FULL / FreeBSD 15.1 only. Parent R3 `d25921733c03e83cbb38a7d2b3bf647d526a82b5`. This is NOT an installation grant. Five-module inactive W09 core, not a full distribution.

## Source of the new P1

On R3, the exact Codex Review of commit `d25921733c03e83cbb38a7d2b3bf647d526a82b5` found that `Tree.snapshot(DATABASE)` and `Tree.read(DATABASE)` open and close new file descriptors for the SAME SQLite DB inode while a SQLite `BEGIN EXCLUSIVE` transaction is held. POSIX/Unix record locks may then be dropped despite `db.in_transaction` still being true. Review discussion: https://github.com/Pawcio99/ETA_FULL_BSD/pull/3#discussion_r4497639452.

**We reproduced the defect on unchanged R3 source with actual SQLite and a separate Python process on Linux:** after `Engine.database_verify(lease)`, the child successfully executed `BEGIN EXCLUSIVE` while the installer lease was still in scope. Reproducer: `R3_DATABASE_VERIFY_EXTERNAL_CHILD_RC=0`, `EXCLUSIVE_ACQUIRED`. This is real concurrency evidence in Linux, not FreeBSD kernel attestation.

## Bounded repair R4

- Version `1.0.0-candidate4`.
- Under a live SQLite transaction, file identity is checked by `os.stat(name, dir_fd=trusted_parent, follow_symlinks=False)` and `os.fstat(retained_fd)`; **no extra database file descriptor is opened and closed**.
- Database bytes are read via the descriptor opened BEFORE SQLite begins its transaction, with `os.lseek` and the existing bounded `read_fd`; no `Tree.read(DATABASE)` or `Tree.snapshot(DATABASE)` while the SQLite lease is active.
- The separate installer-wide `.writer.lock` remains unchanged. No SQLite-file flock, weaker ACL, recovery fallback, migration, budget reset, active-product or host-security mutation.
- R3 P2 protection against abort with nonempty/locked/uncertain DB is retained without change.

Installer SHA-256: `e2fd3d96d351098f345df9d7bfb04614e409b741a6adc4a30cfbd91c362b1147` (Git blob `f6c3e2c43a36f724f40a72a03f7f665b86e84137`).
Test SHA-256: `95515ebe298d45a664040067e6c63cdcf4d237b6e482f4a852edc59a865ae352` (Git blob `7d84e848dd095f438e5c867e79b46bb04f360edc`).
The five-module private W09 payload SHA-256 remains `023cfa3776f37d9911a18661ff0d6920e3aa68476467b6a5eaeecb209a532b41`, with no changes.

## Actual R4 test results

**86/86 PASS**, exit0, Linux Python3.13.5 SQLite3.46.1 UID/GID65534, empty supplementary groups, `NoNewPrivs` through `setpriv`; no chroot/seccomp attestation for this particular run. Tests use real SQLite and filesystem operations in disposable private directories; not host install. A distinct child process was denied conflicting `BEGIN EXCLUSIVE` after `database_verify`, during `withdraw` rename and during `recover('abort')` rename; it succeeded after the lease was released. The same initial P1 reproducer on R3 resulted in **success** for the child (FAIL for isolation), whereas R4 denied the child (PASS for the lock).

Python3.12 AST syntax PASS, R4 offhost `inspect` PASS. **R4 native FreeBSD full installer engine, ACL, root effects and SQLite lock lifetime remain NOT TESTED**. Prior R3 standalone FreeBSD lock-probe PASS is not sufficient, since it did not execute the installer's lease path. The native R4 test suite must run as a non-root FreeBSD user to close that gap.

Private archive `ETA_FREEBSD_SYSTEM_INSTALLER_R4.zip`: SHA-256 `2b5b0f1d71f62b62417163be00c5957872f06d08ca84e7516b17039610b15df0`, 62,501 bytes; 14 entries, 13 manifest hashes, CRC PASS. Includes private W09 payload, raw logs, test outputs and handoff; not for this PUBLIC GitHub repo.

## Gate disposition and concrete next tests

- `R3_NATIVE_INSPECT_PLAN=PASS_REPORTED`; `R3_STANDALONE_SQLITE_PROBE=PASS_REPORTED`.
- `R3_CODE_REVIEW=CHANGES_REQUIRED_P1`.
- `R4_OFFHOST=PASS_86_OF_86`; `R4_NATIVE_FULL_TEST=NOT_TESTED`; `R4_NATIVE_INSPECT_PLAN=NOT_TESTED`.
- `R4_VALIDATOR_REVIEW=NOT_PERFORMED`; `R4_SECURITY_REVIEW=NOT_PERFORMED`.
- `R2_ROOT_OWNED_STAGING=PASS_REPORTED` only for older R2; `R4_ROOT_STAGING=NOT_AUTHORIZED`, `R4_SYSTEM_INSTALL=NOT_AUTHORIZED`, full G0/G1/G2/G7 NOT ACCEPTED.

Next, in an ordinary UID FreeBSD session, verify private R4 ZIP SHA/manifest, run the **actual 86-method test suite** using Python3.12 in a fresh user-owned disposable test directory, then `inspect` and read-only `plan` on R4. Do not re-run R3 probe and mistake it for R4 engine validation. Independently review exact R4 frozen bytes. Preserve R2 root-owned intake; never re-use its staging permission or previous plan digest. No `sudo`, root execution, merge or install based on this work order.
