# ETA_CHERUB FULL / FreeBSD 15.1 — StateLedger sidecar lock, R5

**SOURCE_ONLY_CANDIDATE. Native R5 not tested. No root staging/install/activation authorization.**

### Root cause confirmed by the operator
On FreeBSD 15.1, Python 3.12.15, SQLite 3.53.4 the R4 85-method native test completed 84 methods without issue and 1 test with ERROR:
`test_actual_stateledger_opens_fresh_database` failed at `cherub_state.py:207` / `PRAGMA application_id`: `sqlite3.OperationalError: database is locked`.

The **private actual W09 StateLedger** opened `cherub-state.sqlite3`, applied `fcntl.flock(LOCK_EX|LOCK_NB)` to that same DB inode and then opened SQLite. FreeBSD `flock` and POSIX `fcntl` locks can conflict. This is *not* resolved by changing the installer alone; previous offhost Linux tests could not detect it. References: https://man.freebsd.org/cgi/man.cgi?query=flock&sektion=2 ; https://www.sqlite.org/howtocorrupt.html .

### R5 private source delta (not published)
The existing **StateLedger** moves its single-controller `flock` from the SQLite DB inode to a persistent sibling `cherub-state.sqlite3.lock` (mode0600; same owner; one regular inode). SQLite alone controls DB locks. The DB descriptor used for bounds/header checks is closed **before** the SQLite connection begins. Both DB and lock are required by `create=False`; `create=True` refuses existing DB **or existing lock**, preventing implicit reset after an interrupted creation. No second runtime ledger, credential issuer, grant or admission.

Only the **public installer adapter** is changed here: it now installs the revised pinned five-module package, creates the private lock alongside the fresh inactive v2 database, and takes the same separate sidecar lock for verification, withdrawal and recovery. R5 gets a new release identity, avoiding collision with R2/R4. The private product source remains accessible only through the operator-approved private archive, **not this public GitHub repository**. Therefore a public Codex Review alone cannot attest the private StateLedger delta.

### Actual source-only results
Linux Python3.13.5 SQLite3.46.1, UID65534:
- Installer integration / file, state, crash recovery: **86/86 PASS**.
- Sidecar identity/ownership/dual writer/installer lease: **18/18 PASS**.
- Actual W08/W09 registry + revised StateLedger: **47/47 PASS**.
- W09 diagnostics and disposable-copy migration with explicit sidecar creation: **13/13 PASS**.
Total: **164/164 PASS** on the exact final R5 source/package/installer combination.

The R5 private delivery `ETA_R5_STATELOCK.zip` has SHA-256 `2ce41af18010951be82c2619823e9f38968c34c74fceb3683825f2844826bb25`, **26/26 SHA-256 manifest entries**. It includes all five private sources, regression suites, raw logs and a non-root native runner. Do not commit the private archive or logs into PUBLIC GitHub.

### Public pins
- Private five-module package `ETA_W09_STATELOCK_CORE_R5.zip`: SHA-256 `532c109e085423df7222b8e48271d028a56cb397e1781da7592d202648005f26`; 115443 B.
- Private revised `cherub_state.py`: SHA-256 `1410761598ac35349bcd832b348b61e8c1c4fe7a1ded25d549f3eaed2f59c9c4`.
- Public installer `eta_system_install.py`: SHA-256 `40e9e3495a8a45718fd66c600deb8b6878ea2ad6b2b35604aa0b9cad6897d62e` (Git blob `3349620098bf03c74637557161b124e1be86bde7`).
- Public installer regression `test_system_installer.py`: SHA-256 `07e65330eaefd55bd0d87e8c38ed84583c37e29accc3613ab3b5758d1834d1bc` (Git blob `16dab80ac37ca4069cf87494ffb6fb9fe05f2f98`).

### Native acceptance next, strictly read-only
Operator as nonroot UID1001 downloads private R5 delivery, verifies its ZIP SHA-256, unpacks to fresh private Downloads workspace, runs included `RUN_NATIVE_RO.sh`. It runs **161 native-relevant tests**: 85 installer (skips Linux-only denial test), 18 new lock tests, 47 real-stack, 11 diagnostics (skips two tests that execute the known-incompatible historical v1 StateLedger on FreeBSD). Skipped cases are **NOT TESTED** natively, not PASS. Then `inspect` and read-only `plan`. No root, installed product, active runtime state, PF/VPN/DNS, jail/ZFS, boot, schema migration or grants.

**Gate:** R5 native execution NOT TESTED, R5 source-independent reviews NOT PERFORMED, R5 root stage NOT AUTHORIZED, R5 install NOT AUTHORIZED, G0/G1/G2/G7 NOT ACCEPTED. Prior R2 root-owned stage and R4 native result are retained, not repurposed for R5. Do not run any `install`/ `rollback` or `recover` as root.
