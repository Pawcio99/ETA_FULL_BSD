#!/bin/sh
# No automatic install. Pass an explicit subcommand; shell performs no system writes.
set -eu
umask 077
BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
PY=/usr/local/bin/python3.12
[ -x "$PY" ] || {
    echo 'BLOCKED=PYTHON3_12_REQUIRED_NO_AUTOMATIC_PACKAGE_INSTALL' >&2
    exit 20
}
[ "$#" -gt 0 ] || {
    echo 'Usage: sh INSTALL_FREEBSD.sh inspect|plan|install|verify|status|rollback-plan|rollback|recovery-plan|recover [options]' >&2
    echo 'Default operation: NONE. Native mutations need exact confirmed plan and separate operator approval.' >&2
    exit 2
}
exec "$PY" -I -B "$BASE/installer/eta_system_install.py" "$@" \
    --package "$BASE/packages/ETA_W09_STATELOCK_CORE_R5.zip"
