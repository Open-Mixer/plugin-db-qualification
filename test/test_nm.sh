#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# Spec section 8, change 3, test 11 (symbols): the library imports no getenv or secure_getenv, and exports only pqdb_*.
# Usage: test_nm.sh <libplugin-qualification-db.so.0>
set -eu
lib=$1
fail=0
imports=$(nm -D --undefined-only "$lib" | awk '{print $NF}' | sed 's/@.*//')
for s in getenv secure_getenv; do
    case "
$imports
" in *"
$s
"*) echo "  FAIL: $lib imports $s"; fail=1 ;; esac
done
exports=$(nm -D --defined-only "$lib" | awk '$2 ~ /^[TDBRVW]$/ {print $3}' | sed 's/@.*//' | grep -v '^pqdb_' || true)
if [ -n "$exports" ]; then echo "  FAIL: $lib exports other than pqdb_*: $exports"; fail=1; fi
if [ $fail -eq 0 ]; then echo "ok     11 no getenv import, only pqdb_* exported"; else echo "not ok 11 symbols"; fi
exit $fail
