#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# Spec section 8, change 3, test 14: the command. Usage: test_command.sh <command> <fixture dir> <contract fixtures dir>
set -u
cmd=$1 fx=$2 ct=$3
good=$ct/contract-good
fail=0
note() { echo "  FAIL: $*"; fail=1; }

out=$("$cmd" query --json --base "$fx/base.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" 2>&1); rc=$?
[ $rc -eq 0 ] || note "query --json exited $rc: $out"
printf '%s\n' "$out" > "$fx/command-query.out"

# words and numbers only, one object a line, the same results as the library's reference
python3 -I - "$fx/command-query.out" "$fx/expect-merged.tsv" <<'PY' || fail=1
import json, sys
lines = [l for l in open(sys.argv[1]).read().splitlines() if l]
want = [l.split("\t") for l in open(sys.argv[2]).read().splitlines()]
bad = 0
def fail(m):
    global bad
    print("  FAIL:", m); bad = 1
if len(lines) != len(want):
    fail("%d lines, expected %d" % (len(lines), len(want)))
for i, (l, w) in enumerate(zip(lines, want)):
    try:
        o = json.loads(l)
    except ValueError as e:
        fail("line %d is not JSON: %s" % (i, l)); continue
    def scalar(v):
        return v is None or isinstance(v, (str, int, float)) and not isinstance(v, bool)
    for k, v in o.items():
        if k == "verdicts":
            if not isinstance(v, list) or not all(isinstance(x, dict) and all(scalar(y) for y in x.values()) for x in v):
                fail("verdicts of line %d are not words and numbers" % i)
        elif not scalar(v):
            fail("%s of line %d is not a word or a number" % (k, i))
    sha, fmt, uri, offer, cls, rate, quantum, layer, st, outcome, med, pn, p, hc, lat, hl, mf, mp, hm = w
    got = (o.get("sha256"), o.get("format"), o.get("uri"), o.get("offer"), o.get("host_class"), o.get("rate"),
           o.get("quantum"), o.get("layer"), o.get("outcome"), o.get("cost_median_ns"), o.get("cost_p_ns"),
           o.get("cost_p"), o.get("has_cost"), o.get("latency_frames"), o.get("has_latency"), o.get("mem_first_kb"),
           o.get("has_memory"))
    exp = (sha, fmt, uri, offer, cls, int(rate), int(quantum), layer, outcome, float(med), float(pn), int(p), int(hc),
           int(lat), int(hl), int(mf), int(hm))
    if got != exp:
        fail("line %d: got %r, expected %r" % (i, got, exp))
    if len(o.get("verdicts", [])) != 2:
        fail("line %d: %d verdicts, expected 2" % (i, len(o.get("verdicts", []))))
sys.exit(bad)
PY

# --base, --user, --contract-dir and their variables; a flag beats a variable
out2=$(PLUGIN_QUALIFICATION_DB_BASE="$fx/base.sqlite" PLUGIN_QUALIFICATION_DB_USER="$fx/user.sqlite" OMX_CONTRACT_PATH="$good" \
    "$cmd" query --json 2>&1); rc=$?
[ $rc -eq 0 ] && [ "$out2" = "$out" ] || note "the variables give other results (exit $rc)"
out3=$(PLUGIN_QUALIFICATION_DB_BASE="$fx/no-such.sqlite" "$cmd" query --json --base "$fx/base.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" 2>&1)
[ "$out3" = "$out" ] || note "a variable beat the flag"

# the filters reach the library
one=$("$cmd" query --json --base "$fx/base.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" --offer custom --host-class x86-64 --rate 48000 --quantum 256 2>&1 | wc -l)
[ "$one" -eq 2 ] || note "--offer custom --host-class x86-64 gave $one lines, expected 2"
pk=$("$cmd" query --json --base "$fx/base.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" --pkg-format rpm --pkg-name clap-dexed 2>&1 | wc -l)
[ "$pk" -eq 1 ] || note "the package query gave $pk lines, expected 1"

# check
c=$("$cmd" check --base "$fx/base.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" 2>&1); rc=$?
[ $rc -eq 0 ] && [ "$c" = "ok" ] || note "check: exit $rc, output '$c'"
c=$("$cmd" check --base "$fx/missing.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" 2>&1); rc=$?
case "$c" in qualification-db.absent*) ;; *) note "check of an absent base printed '$c'" ;; esac
[ $rc -eq 1 ] || note "check of an absent base exited $rc, expected 1"
c=$("$cmd" check --base "$fx/base.sqlite" --contract-dir "$ct/contract-no-conditional" --user '' 2>&1); rc=$?
case "$c" in qualification-db.word-unknown*) ;; *) note "check with a missing word printed '$c'" ;; esac
[ $rc -eq 1 ] || note "check with a missing word exited $rc"

# usage errors exit 2
for args in "" "frobnicate" "query --json --no-such-flag" "query --json --rate abc" "query" "check --base"; do
    # shellcheck disable=SC2086
    "$cmd" $args >/dev/null 2>&1; rc=$?
    [ $rc -eq 2 ] || note "'$args' exited $rc, expected 2"
done

if [ $fail -eq 0 ]; then echo "ok     14 the command"; else echo "not ok 14 the command"; fi
exit $fail
