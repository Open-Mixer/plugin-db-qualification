#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# The end of the hosting exception of this repository's qualification store spec (section 3.4): while omx-clap kept
# data/hosting*.json and had no `hosting` domain, the reader (src/pqdb.c, hosting_exception) did not open that domain.
# omx-clap ships it now and the exception is gone; this fails if both are true again, so the exception cannot return.
#   hosting-skip-ends.sh <omx-clap tree, or an installed contract directory> <pqdb.c>
#   hosting-skip-ends.sh --self-test
# Exit 0: the exception may stand, or is gone; 1: the domain exists and the reader still skips it; 2: usage.
set -u

check() {
    tree=$1 src=$2
    [ -r "$src" ] || { echo "hosting-skip-ends: cannot read $src" >&2; return 2; }
    [ -d "$tree" ] || { echo "hosting-skip-ends: $tree is not a directory" >&2; return 2; }
    doc=
    for p in "$tree/contract.d/hosting/hosting.json" "$tree/hosting/hosting.json"; do
        [ -f "$p" ] && doc=$p
    done
    if [ -n "$doc" ] && grep -q 'hosting_exception *(' "$src"; then
        echo "hosting-skip-ends: $doc exists, so omx-clap ships a hosting domain, and $src still holds hosting_exception: remove the exception (section 3.4)" >&2
        return 1
    fi
    echo "hosting-skip-ends: ok ($([ -n "$doc" ] && echo 'a hosting domain exists' || echo 'no hosting domain'); $(grep -q 'hosting_exception *(' "$src" && echo 'the reader skips it' || echo 'the reader does not skip it'))"
    return 0
}

if [ "${1:-}" = "--self-test" ]; then
    t=$(mktemp -d "${TMPDIR:-/tmp}/hosting-skip-ends-XXXXXX") || exit 2
    mkdir -p "$t/with/contract.d/hosting" "$t/without/contract.d/scan"
    echo '{}' > "$t/with/contract.d/hosting/hosting.json"
    printf 'static int hosting_exception(const char *d) { return 0; }\n' > "$t/skips.c"
    printf 'static int other(void) { return 0; }\n' > "$t/clean.c"
    bad=0
    expect() { # <wanted status> <tree> <source>
        check "$2" "$3" >/dev/null 2>"$t/err"; rc=$?
        if [ "$rc" -ne "$1" ]; then echo "  FAIL: $2 $3 gave $rc, wanted $1"; bad=1; else [ "$1" -eq 1 ] && cat "$t/err"; fi
    }
    expect 1 "$t/with" "$t/skips.c"       # the domain arrived and the reader still skips: red
    expect 0 "$t/with" "$t/clean.c"       # the domain arrived and the skip is gone
    expect 0 "$t/without" "$t/skips.c"    # no domain yet: the exception stands
    expect 0 "$t/without" "$t/clean.c"
    mkdir -p "$t/inst/hosting"; echo '{}' > "$t/inst/hosting/hosting.json"
    expect 1 "$t/inst" "$t/skips.c"       # an installed contract directory has the same layout
    [ -d "$t" ] && [ -n "$t" ] && rm -rf "$t"
    if [ $bad -eq 0 ]; then echo "ok     hosting-skip-ends.sh self-test"; else echo "not ok hosting-skip-ends.sh self-test"; fi
    exit $bad
fi
[ $# -eq 2 ] || { echo "usage: hosting-skip-ends.sh <omx-clap tree or contract directory> <pqdb.c> | --self-test" >&2; exit 2; }
check "$1" "$2"
