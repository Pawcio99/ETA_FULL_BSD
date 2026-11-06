# ETA FreeBSD system installer R2 — ACL fail-closed source correction

Date 2026-11-06. STATUS: SOURCE_ONLY_CANDIDATE; NOT NATIVE-ACCEPTED.
Parent R1: `49f520187daa4a2e09c04a903e030d682b1f9a16`.
FreeBSD 15.1/amd64 only; five W09 modules, installed INACTIVE, no service/grants/migration/activation.

## Reproduced security flaw: SEC-ACL-01

The original R1 `NativeACL.__call__` silently accepted a file when both NFSv4 and POSIX access ACL retrievals returned `EINVAL`/`EOPNOTSUPP`. This is not a proof of safe access rights. The defect was actually reproduced on unchanged R1 bytes using a mocked libc: `R1_ALL_ACL_UNSUPPORTED=ACCEPTED_FAIL_OPEN`. R1 has NOT been run as root on the operator's FreeBSD; only native `inspect` and `plan` are known to have completed.

## Minimal R2 change

`NativeACL.__call__` now requires at least one actual successful access-ACL retrieval followed by a successful `acl_is_trivial_np` result; an empty directory DEFAULT ACL alone does not qualify. If NFS4 and ACCESS are both unsupported, it rejects `ACL_ACCESS_TYPES_UNSUPPORTED_OR_UNVERIFIED`. Valid ACCESS fallback remains supported. No ACLs or ownerships are changed, and no bypass is added.

Installer `VERSION=1.0.0-candidate2`. Script SHA256 `64c34c6a4a8f7f9eac4dff0e113630cef93996d458e9768c162e69034aafeac6`; test SHA256 `3c4cce13ea5331a624d81796ac0dc240767887142f14b004da29322793743b23`. Both GitHub blob SHA1 values were compared to exact locally tested bytes before commit: `f030a4020333c6934919d1cbfd2dc9c1acf014ca`, `b08086e3fac6a3eb605d42c2d94ab4cfabc726ee`. W09 payload is UNCHANGED: SHA256 `023cfa3776f37d9911a18661ff0d6920e3aa68476467b6a5eaeecb209a532b41`.

## Verification

Offhost Linux, Python 3.13.5, actual files and SQLite, unprivileged UID/GID65534, no capabilities (setpriv), `python -I -B`, process and resource limits. 72/72 tests PASS, exit0, including all previous 69 tests and new ACL negative/fallback cases. No fake pass for FreeBSD libc: tests mock native ACL calls. Not a native FreeBSD or independent review verdict.

Private delivery `ETA_FREEBSD_SYSTEM_INSTALLER_R2.zip`: SHA256 `b336db9fd9ad361d620ae6ad769980115ed7d2367e43754cdb0ea649a8710592`, 60377 bytes, 14 regular files / 13 verified manifest rows. Do not upload its private W09 binary payload to the public repo.

## Gate status and deployment consequences

`R1_NATIVE_READONLY_PLAN=PASS` for R1 only, but `R1_ROOT_ADMISSION=BLOCKED_SECURITY_FINDING`. The operator's previous R1 `plan_sha256` is NOT valid for R2. R2 requires fresh native `inspect` and `plan`, exact current tool hash, and independent recensions of the frozen bytes.

`R2_OFFHOST_TESTS=PASS_72_OF_72`; `R2_NATIVE_FREEBSD=NOT_TESTED`; `ROOT_OWNED_STAGING=NOT_AUTHORIZED`; `ROOT_INSTALL=NOT_AUTHORIZED`; `INDEPENDENT_VALIDATOR=NOT_PERFORMED`; `INDEPENDENT_SECURITY_REVIEWER=NOT_PERFORMED`; `G0/G1/G2/G7=NOT_ACCEPTED`.

The built-in secure-toolchain check executes after Python has loaded the source. It cannot by itself prevent malicious code already present in a user-owned script from running as root. Source must be authenticated BEFORE staging, and only a separately authorized trusted root-owned copy may be run as root. Do not run this installer from Downloads as root or use flags to bypass native checks.

## Next work order: ETA_NATIVE_INSTALL_ADMISSION_R2

1. Native read-only `inspect` and `plan` with frozen R2 bytes as an ordinary UID, preserving sensitive host fields privately.
2. Separate Validator/Security Reviewer on identical candidate SHA, with practical FreeBSD ACL behavior, SQLite v2, root parent ACL, journal, failure/recovery and TOCTOU scope.
3. Exactly scoped proposal for **root-owned source staging** and an independent pre-execution byte verification. Staging is NOT install.
4. Separate later authorization for inactive install, new plan confirmation, and independent post-install readback.
No PF/VPN/DNS, ZFS/jail, boot, active product, existing SQLite, grants or autonomous agent execution changes.
