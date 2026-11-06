# ETA I3 M0/M1 — implemented and exercised disposable-root installation

Date: 2026-11-06. Scope: ETA_CHERUB FULL / FreeBSD 15.1 project, offhost Linux M0/M1 only. This is an implemented laboratory adapter, not a privileged host installer or a FULL release. Native FreeBSD remains NOT TESTED and explicitly refused by this adapter.

## What was executed

A deterministic package was built from exactly five unchanged SHA-256-pinned W09 modules. The real CLI sequence was exercised: init-lab -> plan -> stage -> apply -> verify -> status -> idempotent apply -> installed-module regressions -> verify -> rollback -> status. Every demo command returned zero. On completion the image is deactivated by rename to retained-image; state and source bytes are preserved, not deleted.

The relative product/tools layout and the existing StateLedger(create=True) API are reused. The fresh state has user_version=2, the actual W09 schema, and zero project, budget, operation, outbox or run_facts rows. No grant, default budget or active controller is created. The product task dispatcher, Codex, rootfs and services are not launched. The installation journal is local file-operation evidence, not a new runtime ledger/issuer.

## Source reuse and explicit boundary

The actual native product installer source has not been bound in this workspace. Historical A2 installers are runner installers; Cinnamon/APT installers belong to another project. Neither is imported here. The new code is restricted to a disposable-root backend for package integration tests. The host installation/promotion backend still has to be identified/adapted separately. The five modules do NOT close the whole ETA product dependency graph, optional DF01 paths or model/runner configuration.

No W09 source bytes changed. The private W09 artifact remains pinned at 66b5f9834706762325d977d39aac70c99c6f350d5fd54cadc5ac3f8a676e17bb. The deterministic data-only package is 113340 B, SHA-256 023cfa3776f37d9911a18661ff0d6920e3aa68476467b6a5eaeecb209a532b41. Hash pins are integrity references, not independent release signatures or admission.

## Actual test results

- New installer suite: 49/49 unittest methods PASS, exit 0.
- Existing real-stack regression against INSTALLED module paths: 47/47 PASS, exit 0.
- Existing W09 diagnostics against INSTALLED modules: 13/13 PASS, exit 0.
- A separate root-refusal probe returned expected exit 20 before workspace creation.
- Byte-identical package generation was checked; source hashes were rechecked after installation and regression.
- Python 3.12 AST compatibility was checked; actual interpreter was Python 3.13.5. This is not Python 3.12 runtime evidence.

The existing 47-test harness had ONLY its source-selection line adapted to the installed path; assertions and source pins were unchanged. Real modules, SQLite, contract validation and filesystem candidate operations ran; model driver, external gate and send ports remain synthetic. No real model session or authentic Conductor was started.

Installer tests include package hash/inventory/duplicate/traversal/symlink refusal; zero-write plan; staging and apply idempotence; actual StateLedger initialization; read-only readback; code/schema/mode/hardlink tampering; WAL/unknown files; refusal of v1 without migration; concurrent installer/database writers; nonempty state refusal; retained-state rollback; actual process interruption at five points and explicit recovery without re-executing an uncertain apply.

## Containment evidence

Initial execution setup stopped before tests: Landlock ABI probe returned ENOSYS (38), setup exit 121. Existing protections were not disabled. The successful test setup used a new disposable chroot, then dropped UID/GID to 65534, emptied supplementary groups, set CapEff=0 and NoNewPrivs=1, applied seccomp syscall denial and resource limits. Network socket, root-directory write and chroot escape syscall probes were actually denied. No mounts were created. Runtime Python 3.13.5 / SQLite 3.46.1. CPU limit 90 s/process, address-space limit 768 MiB, descriptor limit 128.

The adapter additionally requires non-root Linux, -B, a private owned /tmp/eta-i3-work-*/lab-* root, directory identity marker and explicit allow-disposable-writes. Marker/ownership/flock are NOT a sandbox against a malicious process with the same UID. Descriptor-relative operations and O_NOFOLLOW are used, but no hostile-same-UID TOCTOU resistance or power-loss/media durability is claimed. Directory and file fsync are used; process crashes, not power failures, were tested.

## Rollback and state

Fresh-only rollback retains the entire code/state image. SQLite SHA-256 before and after the demonstrated rollback is 03e78de53ee5bb13d3b02b8bd73595e24191694355efb25186a347e92c32da05. Nonempty state or an active database writer blocks automatic rollback. No v1->v2 migration, database rewind, budget refund, lease reset or external-effect reconciliation is implemented in this adapter.

## Public/private split and reproduction

Public: four generic installer modules, 49-test suite, package hash reference, this report and evidence index. Private: source payload, original W09 material, full raw logs and runtime artifacts. .gitignore is not a publication authorization control. No private payload is uploaded to this public repository.

For an already admitted non-root Linux offhost workspace: provide the exact private package at packages/ETA_W09_CORE_LAB_R1.zip; invoke python3 -I -B installer/eta_i3_lab.py init-lab and use its returned lab_root for plan/stage/apply/verify/status/rollback. Write commands require --allow-disposable-writes. Recovery is explicit: abort-stage, complete-image or complete-rollback. The private artifact includes complete reproduction instructions and test-environment setup; those are NOT commands for the user's FreeBSD workstation.

## Acceptance and next gate

M0/M1 technical execution: PASS_SCOPED_LAB_CORE. Independent final Validator/Security reviews: NOT PERFORMED. No claim of G0/G1/G2/G7 acceptance. Native build/package M2, host apply M3, production operation, authentic admission, full product dependency closure and full release remain unaccepted/not tested.

Next: review the frozen W09 and adapter bytes, bind the complete product layout to the existing FreeBSD installation mechanism, and prepare an exact separately authorized native build-only change order. Do not enable native apply by removing the Linux guard, do not merge automatically, and do not repeat source intake for these five unchanged modules.
