# Private package input

The public repository deliberately does not contain the W09 source ZIP or the five-module payload. Obtain the operator-approved private artifact `ETA_I3_LAB_INSTALL_R1.zip` or build the exact package from the pinned W09 input using the reviewed `installer/eta_i3_lab.py build-package` command in an admitted non-root Linux offhost environment. Do not publish private sources or SQLite stores here.

Expected payload file: `packages/ETA_W09_CORE_LAB_R1.zip` (113340 bytes). Required SHA-256 is in `PACKAGE_SHA256`; it is a trusted reference pin, not an issuer signature or execution grant. Tests fail without these actual bytes; a filename, URL or report does not supply them.

This package is a scoped W09 core, not a complete ETA FULL distribution and not a native FreeBSD package. No runtime/autostart/native install backend is implemented. The original W09 ZIP pin is `66b5f9834706762325d977d39aac70c99c6f350d5fd54cadc5ac3f8a676e17bb`.
