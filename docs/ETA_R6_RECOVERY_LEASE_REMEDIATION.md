# ETA_CHERUB FULL / FreeBSD 15.1 — R6 recovery lease contract

**State:** SOURCE_ONLY_CANDIDATE; offhost verified; native FreeBSD R6 and privileged operation NOT TESTED/NOT AUTHORIZED. Candidate is five-module W09 INACTIVE core only, not full ETA FULL nor G7.

## Why R6 exists

The operator's actual FreeBSD 15.1 / Python3.12.15 / SQLite3.53.4 R5 run completed 18 sidecar + 85 engine + 47 real-stack + 11 diagnostic = **161/161 PASS**, with `inspect=0` and `plan=0`. These observations remain R5-only.

Exact GitHub Codex Code Review of R5 commit `c65a0f1eddfb44949261e17e68d37d688a6b1725` found P2 (see https://github.com/Pawcio99/ETA_FULL_BSD/pull/3#discussion_r4498000465): the two `Engine.recover` completion branches release their SQLite/sidecar leases before recording the terminal journal event. A concurrent state consumer can acquire the lock and write before the installer records success.

**Reproduced on actual unchanged R5 files**, offhost with real SQLite and a separate process respecting the sidecar. Two R6 negative tests, run against R5 source, failed with `AssertionError: 0 != 3`: competing process acquired the sidecar and started SQLite before `VERIFIED_INACTIVE`/ `WITHDRAWN` event. This is a factual source-level problem, not a claim that it happened on FreeBSD.

## Minimal R6 source delta

- `installer/eta_system_install.py`: new version `1.0.0-candidate6`. `verify_unlocked(location, lease=None)` can use an existing locked connection; default behavior unchanged for status/verify.
- `recover('complete')`: maintain `database_lock(exclusive=True)` across code verification, DB validation, optional stage→final rename, re-verification and **final `VERIFIED_INACTIVE` event**. Compare observed DB digest/counters against exact previously accepted plan before changing anything.
- `recover('complete-withdrawal')`: maintain the same exclusive SQLite + sidecar lease through final `WITHDRAWN` event. Compare DB to plan.
- `recover('abort')`, `withdraw`, error guards, ACL, source hash, paths, original private W09 `cherub_state.py` and payload **unchanged**.
- In the two newly added tests a separate real child process attempts to acquire the sidecar **at the final event**. R5: child succeeds (2 failures). R6: child is denied, and succeeds only after lease release.
- Additional tests block recovery if DB rows change after plan or another DB writer obtains its own lock before recovery.

## Tests and evidence

Final exact R6 source SHA-256:
- installer `9d598090d712cbf63d6816e85ecf1e287182f9212e88982159e45fecd5e7773b`, Git blob `fb58097553fb3ed17676c45e2e1b8232e2b8d203`.
- tests `7cf1ace8985ac58dd0cc65802946bfd2b0e94923a877575b971c21416590aee5`, Git blob `6e54c3261cd344254c908a0cd87019cc4e6b6f0b`.
- unchanged private five-module package `ETA_W09_STATELOCK_CORE_R5.zip`, SHA-256 `532c109e085423df7222b8e48271d028a56cb397e1781da7592d202648005f26`.

Actual test execution (offhost Linux, Python3.13.5, SQLite3.46.1, ordinary uid1000; **NOT** a native FreeBSD execution):
- installer **90/90 PASS**, exit0,
- StateLedger sidecar **18/18 PASS**,
- real W08/W09 stack **47/47 PASS**,
- W09 diagnostics **13/13 PASS**,
- **168/168 PASS total** on source-only candidate R6.
- R5 negative reproducer with exact two R6 event tests: **2/2 failed as expected on R5**, showing newly added tests detect the problem.
- An initial R6 test harness had an escaped-string syntax error; corrected before final 90/90 run. The corresponding failed run is not mislabeled as PASS.

Private package `ETA_FREEBSD_SYSTEM_INSTALLER_R6.zip`: SHA-256 `4eb36d85a1ce861951728cf3318811e235a62add20fa28c4368a39e86de4c60a`, **115192 B, 28 entries, 27/27 manifest SHA-256 PASS**. Contains changed installer/test, unchanged private W09 package and source, raw logs, exact R5→R6 diffs, and a native **nonroot** runner. Do not publish private source data in this PUBLIC repository.

## Native R6 next

Run only as ordinary FreeBSD uid1001 after verifying private ZIP. The included `RUN_NATIVE_RO.sh` runs **89 native-relevant installer tests** (90 minus one Linux-only), 18 sidecar, 47 real-stack, 11 W09 diagnostics (2 legacy v1 intentionally skipped), total **165**, then `inspect` and read-only `plan`. This MUST NOT be counted PASS until operator actually provides a native result.

**Release hold:** R6 independent final Validator = NOT PERFORMED; R6 private StateLedger independent Security Review = NOT PERFORMED; root-owned staging R6 = NOT AUTHORIZED; system install R6 = NOT AUTHORIZED; G0/G1/G2/G7 = NOT ACCEPTED. Previous operator-approved root staging is R2 only and must not be reused. No original active code, SQLite state, PF/VPN/DNS, jail, ZFS, boot, grants or Conductor changed. Keep PR DRAFT and unmerged.

Focus any next review on the exact R6 frozen commit, the final event window and the fact that private W09 source is not in this public repo. Do not use an old native plan SHA for this modified version.
