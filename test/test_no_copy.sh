#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# The groupable codes are the qualification domain's (QUALIFICATION_GROUPABLE_CONDITIONAL_CODES, read at open): no source
# file of the reader holds a copy of one. It proves it sees a planted copy before it trusts a clean tree.
# Usage: test_no_copy.sh <src dir>
src=${1:-src}
scan() { grep -rlE '"hosting\.rt-safety\.[a-z-]+"' "$1" 2>/dev/null; }
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
printf 'static const char *const G[] = { "hosting.rt-safety.own-threads", NULL };\n' > "$work/planted.c"
[ -n "$(scan "$work")" ] || { echo "not ok the scan cannot see a planted copy"; exit 1; }
found=$(scan "$src")
if [ -n "$found" ]; then echo "not ok a copy of a groupable code is in: $found"; exit 1; fi
echo "ok     no copy of the groupable codes in the reader's source"
