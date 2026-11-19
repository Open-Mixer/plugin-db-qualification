#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# The install: the DDL beside the header, named by the .pc's `schema` variable. Usage: test_install.sh <staging root>
set -u
root=$1
fail=0
note() { echo "  FAIL: $*"; fail=1; }
pc=$root/usr/lib/pkgconfig/plugin-qualification-db.pc
[ -f "$pc" ] || note "no $pc"
schema=$(PKG_CONFIG_PATH=$root/usr/lib/pkgconfig pkg-config --variable=schema plugin-qualification-db 2>&1)
[ "$schema" = "/usr/share/plugin-qualification-db/qualification.sql" ] || note "pkg-config --variable=schema gave '$schema'"
cmp -s "$root/usr/share/plugin-qualification-db/qualification.sql" schema/qualification.sql || note "the installed DDL is not schema/qualification.sql"
[ -f "$root/usr/include/plugin-qualification-db/pqdb.h" ] || note "no header"
[ -x "$root/usr/bin/plugin-qualification-db" ] || note "no command"
[ -e "$root/usr/lib/libplugin-qualification-db.so.0" ] && [ -L "$root/usr/lib/libplugin-qualification-db.so" ] || note "no library or .so link"
if [ $fail -eq 0 ]; then echo "ok     install: DDL, header, library, command and .pc"; else echo "not ok install"; fi
exit $fail
