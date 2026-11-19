#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# The installed .pc carries the prefix of its own install, not that of an earlier staged one: `make check` stages an
# install under /usr, then `make install PREFIX=/usr/local` must say /usr/local. Usage: test_prefix.sh <staging root>
set -u
root=$1
pc=$root/usr/local/lib/pkgconfig/plugin-qualification-db.pc
fail=0
note() { echo "  FAIL: $*"; fail=1; }
[ -f "$pc" ] || note "no $pc"
grep -qx 'prefix=/usr/local' "$pc" 2>/dev/null || note "prefix is not /usr/local: $(grep '^prefix=' "$pc" 2>&1)"
schema=$(pkg-config --variable=schema "$pc" 2>&1)
[ "$schema" = "/usr/local/share/plugin-qualification-db/qualification.sql" ] || note "schema is '$schema'"
[ -f "$root/usr/local/share/plugin-qualification-db/qualification.sql" ] || note "the DDL is not under /usr/local/share"
if [ $fail -eq 0 ]; then echo "ok     install under another PREFIX: the .pc says its own"; else echo "not ok install under another PREFIX"; fi
exit $fail
