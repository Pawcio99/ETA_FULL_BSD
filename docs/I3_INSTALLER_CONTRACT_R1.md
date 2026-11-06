# ETA FULL BSD — parallel installer model I3, contract draft

**Not an installer implementation, execution grant, nor an accepted release.** The existing installation/promotion mechanism must be identified and adapted rather than replaced with a new privileged broker. Product target FreeBSD 15.1 only. Frozen full product dependency graph and runtime host admission are not yet attested.

## Acceptance-oriented interface phases (logical, names TBD)

- **Intake**: verify full source/release manifest, toolchain, immutable candidate digest, policy, target identity, existing version, current StateLedger v1/v2 and required migration. Reject unsigned/changed bytes, symlinks/traversal and unknown components.
- **Plan** (read-only): print exact paths/files, owners and permissions, version constraints, storage and state consequences, secret handling, rollback checkpoint requirements, and which operations require elevated authority. Nothing starts automatically.
- **Stage**: create a private versioned source candidate in *approved* isolated workspace, never overwrite active files; use least privilege and explicit provenance. No automatic PF/VPN/DNS, boot, jail, ZFS, sysctl, service, broker/grant or state changes.
- **Apply** (separately authorized): one source writer, frozen revision, fail-closed identity checks and bounded transaction log. Do not merge code and data migration into an unreviewed step. v1->v2 StateLedger upgrade requires a distinct approved migration and recovery plan.
- **Verify**: independent readback of installed digest, state version, ACL/ownership, single active version, status and service health in the allowed scope; never equate stdout PASS/exit0 with accepted independent receipt.
- **Rollback**: only admitted prior code version, verified state compatibility, reconciled external effects and old budget; on unknown effect or incompatible schema, stop rather than blindly restore the old DB.

## First laboratory pilot exit criteria (INSTALLATION_PREVIEW_LAB)

1. One full-source and state manifest, frozen against package.
2. Source-only installer tests for missing/wrong inputs, refusal to touch outside allowed directory, repeated plan/apply, interrupted apply/recovery, readback, and rollback. Zero privileged native effects in source-only phase.
3. One separately approved isolated target with an admitted installer mechanism; exact change order and independent post-change verification.
4. Validated W08/W09 source candidate, real ledger and no auto-retry, external receipt handling and two independent reviews.
5. Distinguish limited lab installation from MK-2.1 G4/G5/G6 and full release G7. No claim of full product until K1–K3 achieved.

Installer I3 design can continue in parallel with W09 source reviews. No new host commands required at this step.
