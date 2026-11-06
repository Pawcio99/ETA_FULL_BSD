# ETA_FULL_BSD

Repository for **ETA_CHERUB FULL / FreeBSD 15.1**. It is **not** the AGENTS/MK1, Ubuntu FULL, or CHERUB_VM01 project.

This public repository currently contains a G0 **source-only candidate**, not an accepted or executable release. The existing ETA Conductor remains authoritative. No GitHub commit, CI status or PR grants admission, root permissions or host deployment.

## Project entrypoints

- [Approved project baseline and SHA-256 references](docs/PROJECT_BASELINE.md)
- [W01–W32 roadmap, G0–G7](docs/ROADMAP_W01_W32.md)
- [G0 / W01–W04 exact work order and blockers](docs/G0_W01_W04_WORK_ORDER.md)
- [Decision register](docs/DECISIONS.md)
- [W01 read-only source identity tool](tools/w01_source_identity.py)
- [Synthetic tests](tests/test_w01_source_identity.py)

G0 stays **BLOCKED** until the actual canonical FreeBSD product sources, revision/manifest/checkpoint and current host restrictions are independently bound and reviewed. The public repository does not contain the private MK-2.1 original document, host receipts or product rootfs.
