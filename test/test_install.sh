#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# The install: the DDL and the writer beside each other, the DDL named by the .pc's `schema` variable.
# Usage: test_install.sh <staging root> [libdir, default /usr/lib]
set -u
root=$1
libdir=${2:-/usr/lib}
fail=0
note() { echo "  FAIL: $*"; fail=1; }
pc=$root$libdir/pkgconfig/plugin-qualification-db.pc
[ -f "$pc" ] || note "no $pc"
schema=$(PKG_CONFIG_PATH=$root$libdir/pkgconfig pkg-config --variable=schema plugin-qualification-db 2>&1)
[ "$schema" = "/usr/share/plugin-qualification-db/qualification.sql" ] || note "pkg-config --variable=schema gave '$schema'"
cmp -s "$root/usr/share/plugin-qualification-db/qualification.sql" schema/qualification.sql || note "the installed DDL is not schema/qualification.sql"
[ -f "$root/usr/include/plugin-qualification-db/pqdb.h" ] || note "no header"
[ -f "$root/usr/share/man/man1/plugin-qualification-db.1" ] || note "no manual page"
for w in 'records' 'scope' 'binary\\-path' 'layer' 'counts' 'key\\-mismatch\|key-mismatch'; do
    grep -q -- "$w" "$root/usr/share/man/man1/plugin-qualification-db.1" || note "the manual page does not mention $w"
done
[ -x "$root/usr/bin/plugin-qualification-db" ] || note "no command"
[ -e "$root$libdir/libplugin-qualification-db.so.0" ] && [ -L "$root$libdir/libplugin-qualification-db.so" ] || note "no library or .so link"
[ -f "$root/usr/share/plugin-qualification-db/qualification_db.py" ] || note "no writer module"
[ -f "$root/usr/share/man/man1/plugin-qualification-db-write.1" ] || note "no manual page of the writer"
w=$root/usr/bin/plugin-qualification-db-write
[ -x "$w" ] || note "no writer command"
! grep -q '@MODULEDIR@' "$w" && grep -q 'MODULEDIR = "/usr/share/plugin-qualification-db"' "$w" || note "the writer command names no module directory"
if [ $fail -eq 0 ]; then echo "ok     install: DDL, header, library, commands and .pc"; else echo "not ok install"; fi
exit $fail
