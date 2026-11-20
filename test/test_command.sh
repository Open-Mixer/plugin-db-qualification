#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# Spec section 8, change 3, tests 14, 22 and 23: the command.
# Usage: test_command.sh <command> <fixture dir> <contract fixtures dir> [<shim.so>]
# With the shim and PQDB_TEST_CONTRACTDIR (the contract directory the library was built for) it also runs --scope.
set -u
cmd=$1 fx=$2 ct=$3 shim=${4:-}
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
        elif k == "files":
            if not isinstance(v, list) or not v or not all(isinstance(x, dict) and list(x) == ["path", "sha256"] and all(isinstance(y, str) for y in x.values()) for x in v):
                fail("files of line %d is not a non-empty array of path and sha256" % i)
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
[ $rc -eq 0 ] && [ "$c" = "ok base-absent" ] || note "check of an absent base: exit $rc, output '$c'"

# an absent base is an empty base layer: exit 0, the answer says so, the user layer answers alone
# stdout holds records only (each line a stored record, or none); stderr carries the one named line
want="plugin-qualification-db: base-absent: $fx/missing.sqlite: the base layer is empty"
a=$("$cmd" query --json --base "$fx/missing.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" 2>"$fx/abs.err"); rc=$?
[ $rc -eq 0 ] || note "query with an absent base exited $rc"
[ "$(cat "$fx/abs.err")" = "$want" ] || note "query with an absent base: stderr is '$(cat "$fx/abs.err")'"
u=$("$cmd" query --json --layer user --base "$fx/missing.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" 2>/dev/null)
[ "$a" = "$u" ] && [ -n "$u" ] || note "query with an absent base is not the user layer's alone"
printf '%s\n' "$a" | python3 -I -c '
import json, sys
for l in sys.stdin.read().splitlines():
    o = json.loads(l)
    assert "sha256" in o and "layer" in o and "base" not in o, l' || note "stdout of query with an absent base holds a line that is no record"
a=$("$cmd" counts --json --base "$fx/missing.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" 2>"$fx/abs.err"); rc=$?
[ $rc -eq 0 ] || note "counts with an absent base exited $rc"
[ "$(cat "$fx/abs.err")" = "$want" ] || note "counts with an absent base: stderr is '$(cat "$fx/abs.err")'"
printf '%s\n' "$a" | python3 -I -c '
import json, sys
for l in sys.stdin.read().splitlines():
    o = json.loads(l)
    assert "format" in o and "plugins" in o and "base" not in o, l' || note "stdout of counts with an absent base holds a line that is no count"
a=$("$cmd" query --json --base "$fx/missing.sqlite" --user '' --contract-dir "$good" 2>"$fx/abs.err"); rc=$?
[ $rc -eq 0 ] && [ -z "$a" ] || note "no layer at all: exit $rc, stdout '$a'"
[ "$(cat "$fx/abs.err")" = "$want" ] || note "no layer at all: stderr is '$(cat "$fx/abs.err")'"
for v in query counts; do
    "$cmd" $v --json --base "$fx/base.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" >/dev/null 2>"$fx/abs.err"
    [ ! -s "$fx/abs.err" ] || note "$v with a base present wrote to stderr: $(cat "$fx/abs.err")"
done
# a base that exists and cannot be used is refused by name
mkdir -p "$fx/base-dir.sqlite"
for arm in "base-dir.sqlite" ; do
    c=$("$cmd" query --json --base "$fx/$arm" --user "$fx/user.sqlite" --contract-dir "$good" 2>&1); rc=$?
    case "$c" in qualification-db.unreadable*) ;; *) note "a directory as the base printed '$c'" ;; esac
    [ $rc -eq 1 ] || note "a directory as the base exited $rc"
done
printf 'not sqlite' > "$fx/junk.sqlite"
c=$("$cmd" counts --json --base "$fx/junk.sqlite" --user '' --contract-dir "$good" 2>&1); rc=$?
case "$c" in qualification-db.unreadable*) ;; *) note "a junk base printed '$c'" ;; esac
[ $rc -eq 1 ] || note "a junk base exited $rc"
c=$("$cmd" check --base "$fx/base-v2.sqlite" --user '' --contract-dir "$good" 2>&1); rc=$?
case "$c" in qualification-db.schema-other*) ;; *) note "a base of version 2 printed '$c'" ;; esac
[ $rc -eq 1 ] || note "a base of version 2 exited $rc"
if [ "$(id -u)" -ne 0 ]; then
    cp "$fx/base.sqlite" "$fx/denied.sqlite"; chmod 000 "$fx/denied.sqlite"
    c=$("$cmd" query --json --base "$fx/denied.sqlite" --user '' --contract-dir "$good" 2>&1); rc=$?
    case "$c" in qualification-db.unreadable*) ;; *) note "an unreadable base printed '$c'" ;; esac
    [ $rc -eq 1 ] || note "an unreadable base exited $rc"
else
    echo "skip   unreadable base: running as root, a mode 000 file is readable"
fi
c=$("$cmd" check --base "$fx/base.sqlite" --contract-dir "$ct/contract-no-conditional" --user '' 2>&1); rc=$?
case "$c" in qualification-db.word-unknown*) ;; *) note "check with a missing word printed '$c'" ;; esac
[ $rc -eq 1 ] || note "check with a missing word exited $rc"

# usage errors exit 2
for args in "" "frobnicate" "query --json --no-such-flag" "query --json --rate abc" "query" "check --base"; do
    # shellcheck disable=SC2086
    "$cmd" $args >/dev/null 2>&1; rc=$?
    [ $rc -eq 2 ] || note "'$args' exited $rc, expected 2"
done

# ---- test 22: the widened shape ----
keys='layer sha256 format uri offer host_class set pkg_format pkg_name pkg_version pkg_release pkg_distro pkg_arch binary_path layout_scheme layout_sha256 tested_version unpinnable files rate quantum outcome cost_median_ns cost_p_ns cost_p has_cost latency_frames has_latency mem_first_kb mem_per_instance_kb has_memory verdicts'
"$cmd" query --json --layer base --base "$fx/base.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" > "$fx/command-base.out" 2>&1
python3 -I - "$fx/command-query.out" "$keys" "$fx/command-base.out" <<'PY' || fail=1
import json, sys
bad = 0
want = sys.argv[2].split()
seen = set()
# the merged answer hides the base record that has a layout (a user record shadows it): the base's own shows the variety
for n, l in enumerate([l for l in open(sys.argv[1]).read().splitlines() if l] + [l for l in open(sys.argv[3]).read().splitlines() if l]):
    o = json.loads(l)
    if list(o) != want:
        print("  FAIL: line %d keys are %s, expected %s" % (n, list(o), want)); bad = 1; break
    if o["unpinnable"] not in (0, 1): print("  FAIL: unpinnable %r" % o["unpinnable"]); bad = 1
    for k in ("binary_path",):
        if not isinstance(o[k], str): print("  FAIL: %s is %r" % (k, o[k])); bad = 1
    seen.add((o["layout_scheme"] is None, o["unpinnable"], o["tested_version"] is None))
if len(seen) < 3:
    print("  FAIL: the fixtures show no variety of layout, unpinnable and tested_version: %s" % sorted(seen)); bad = 1
sys.exit(bad)
PY
rec="--base $fx/records.sqlite --user '' --contract-dir $good"
# --records: one line a record, the record document of pqdb_record_json
eval "$cmd" query --json --records $rec > "$fx/command-records.out" 2>&1; rc=$?
[ $rc -eq 0 ] || note "query --json --records exited $rc"
python3 -I - "$fx/command-records.out" "$ct/records" <<'PY' || fail=1
import json, os, sys
lines = [l for l in open(sys.argv[1], encoding="utf-8").read().split("\n") if l]
bad = 0
if len(lines) != 3:
    print("  FAIL: --records printed %d lines, expected one a record (3)" % len(lines)); bad = 1
for l in lines:
    o = json.loads(l)
    if list(o) != ["layer", "sha256", "format", "uri", "offer", "host_class", "record"]:
        print("  FAIL: --records keys %s" % list(o)); bad = 1; continue
    name = "%s-%s.%s.%s.json" % (o["format"], o["uri"].split(":")[-1], o["offer"], o["host_class"])
    doc = open(os.path.join(sys.argv[2], name), encoding="utf-8").read()
    head = '{"layer":"%s","sha256":"%s","format":"%s","uri":"%s","offer":"%s","host_class":"%s","record":' % (
        o["layer"], o["sha256"], o["format"], o["uri"], o["offer"], o["host_class"])
    if l != head + doc + "}":
        print("  FAIL: --records line of %s is not the record document of the library" % name); bad = 1
sys.exit(bad)
PY
"$cmd" query --json --records --rate 48000 --base "$fx/base.sqlite" --user '' --contract-dir "$good" >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] || note "--records with --rate exited $rc, expected 2"
"$cmd" query --json --records --quantum 256 --base "$fx/base.sqlite" --user '' --contract-dir "$good" >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] || note "--records with --quantum exited $rc, expected 2"

# --layer
n=$("$cmd" query --json --layer user --base "$fx/base.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" 2>&1 | wc -l)
[ "$n" -eq "$(wc -l < "$fx/expect-user.tsv")" ] || note "--layer user gave $n lines"
n=$("$cmd" query --json --layer base --base "$fx/base.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" 2>&1 | wc -l)
[ "$n" -eq "$(wc -l < "$fx/expect-base.tsv")" ] || note "--layer base gave $n lines"
n=$("$cmd" query --json --binary-path Sub/p1.clap --base "$fx/base.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" 2>&1 | wc -l)
[ "$n" -eq 1 ] || note "--binary-path Sub/p1.clap gave $n lines, expected 1"

# counts
for layer in "" user base; do
    if [ -n "$layer" ]; then arg="--layer $layer"; want=$fx/expect-counts-$layer.tsv; else arg=""; want=$fx/expect-counts-merged.tsv; fi
    # shellcheck disable=SC2086
    "$cmd" counts --json $arg --base "$fx/base.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" > "$fx/command-counts.out" 2>&1; rc=$?
    [ $rc -eq 0 ] || note "counts $arg exited $rc"
    python3 -I - "$fx/command-counts.out" "$want" <<'PY' || fail=1
import json, sys
got = [json.loads(l) for l in open(sys.argv[1]).read().splitlines() if l]
want = [l.split("\t") for l in open(sys.argv[2]).read().splitlines()]
exp = [{"format": f, "plugins": int(p), "offered": int(o), "not_offered": int(n)} for f, p, o, n in want]
if got != exp or [list(g) for g in got] != [["format", "plugins", "offered", "not_offered"]] * len(exp):
    print("  FAIL: counts gave %r, expected %r" % (got, exp)); sys.exit(1)
PY
done

# usage errors of the new options exit 2
for args in "query --json --layer system" "query --json --layer" "counts" "counts --json --layer both" "counts --json --rate 1" "query --json --scope other" \
            "query --json --scope user --base $fx/base.sqlite" "query --json --scope system --user $fx/user.sqlite" "check --scope user --base $fx/base.sqlite"; do
    # shellcheck disable=SC2086
    "$cmd" $args >/dev/null 2>&1; rc=$?
    [ $rc -eq 2 ] || note "'$args' exited $rc, expected 2"
done

# ---- test 23: check verifies the key ----
c=$("$cmd" check --base "$fx/base-key-mismatch.sqlite" --user '' --contract-dir "$good" 2>&1); rc=$?
case "$c" in qualification-db.key-mismatch*) ;; *) note "check of a store with a wrong key printed '$c'" ;; esac
case "$c" in *aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa*p1.clap*) ;; *) note "the message does not name the key and the path: '$c'" ;; esac
[ $rc -eq 1 ] || note "check of a store with a wrong key exited $rc, expected 1"
c=$("$cmd" check --base "$fx/base-key-no-entry.sqlite" --user '' --contract-dir "$good" 2>&1); rc=$?
case "$c" in qualification-db.key-mismatch*other.clap*) ;; *) note "check of a binary_path with no entry printed '$c'" ;; esac
[ $rc -eq 1 ] || note "check of a binary_path with no entry exited $rc"
c=$("$cmd" check --base "$fx/base.sqlite" --user "$fx/user.sqlite" --contract-dir "$good" 2>&1); rc=$?
[ $rc -eq 0 ] && [ "$c" = "ok" ] || note "check of stores that hold the rule: exit $rc, output '$c'"
c=$("$cmd" check --base "$fx/records.sqlite" --user '' --contract-dir "$good" 2>&1); rc=$?
[ $rc -eq 0 ] && [ "$c" = "ok" ] || note "check of the records store: exit $rc, output '$c'"

# ---- test 22: --scope, under the shim (the places are rewritten to fixtures; the trace says what was opened) ----
if [ -n "$shim" ] && [ -n "${PQDB_TEST_CONTRACTDIR:-}" ]; then
    root=$(mktemp -d "${TMPDIR:-/tmp}/pqdb-cmd-XXXXXX")
    mkdir -p "$root/usr/share/omx/qualification" "$root/var/lib/omx/qualification" "$root/home/u/.local/share/omx/qualification" "$root/xdg/omx/qualification"
    cp "$fx/base.sqlite" "$root/usr/share/omx/qualification/qualification.sqlite"
    cp "$fx/scope-system.sqlite" "$root/var/lib/omx/qualification/qualification.sqlite"
    cp "$fx/scope-home.sqlite" "$root/home/u/.local/share/omx/qualification/qualification.sqlite"
    cp "$fx/scope-xdg.sqlite" "$root/xdg/omx/qualification/qualification.sqlite"
    scoped() {
        LD_PRELOAD=$shim PQDB_SHIM_TRACE="$root/trace" PQDB_SHIM_HOME="$root/home/u" XDG_DATA_HOME="$root/xdg" \
        PQDB_SHIM_MAP="/usr/share/omx/qualification=$root/usr/share/omx/qualification:/var/lib/omx/qualification=$root/var/lib/omx/qualification:$PQDB_TEST_CONTRACTDIR=$good" \
        "$cmd" "$@"
    }
    rm -f "$root/trace"
    sys=$(scoped query --json --scope system 2>&1); rc=$?
    [ $rc -eq 0 ] || note "--scope system exited $rc: $sys"
    case "$sys" in *1111111111111111111111111111111111111111111111111111111111111111*) ;; *) note "--scope system does not read the system layer" ;; esac
    case "$sys" in *2222222222222222222222222222222222222222222222222222222222222222*|*3333333333333333333333333333333333333333333333333333333333333333*) note "--scope system read the home's or XDG_DATA_HOME's layer" ;; esac
    if grep -q '/\.local/share\|/xdg/' "$root/trace"; then note "--scope system touched the home or XDG_DATA_HOME"; fi
    rm -f "$root/trace"
    usr=$(scoped query --json --scope user 2>&1); rc=$?
    [ $rc -eq 0 ] || note "--scope user exited $rc: $usr"
    case "$usr" in *2222222222222222222222222222222222222222222222222222222222222222*) ;; *) note "--scope user does not read the home's layer" ;; esac
    case "$usr" in *1111111111111111111111111111111111111111111111111111111111111111*|*3333333333333333333333333333333333333333333333333333333333333333*) note "--scope user read the system layer or XDG_DATA_HOME's" ;; esac
    if grep -q '/var/lib/omx/qualification' "$root/trace"; then note "--scope user touched the system layer"; fi
    rm -rf "$root"
else
    echo "skip   --scope under the shim: no shim or no PQDB_TEST_CONTRACTDIR"
fi

# a figure that is not finite is refused by name, never printed as `inf` (the library's pqdb_each says so, the command too)
out=$("$cmd" query --json --base "$fx/nonfinite-cpu.sqlite" --user '' --contract-dir "$good" 2>"$fx/command-nonfinite.err"); rc=$?
[ $rc -eq 1 ] || note "query --json of a store with an infinite figure exited $rc, expected 1"
case "$out" in *inf*|*nan*) note "query --json printed a non-finite figure: $out" ;; esac
grep -q 'qualification-db.not-a-store' "$fx/command-nonfinite.err" && grep -q 'cost_median' "$fx/command-nonfinite.err" || note "the refusal does not name not-a-store and the column: $(cat "$fx/command-nonfinite.err")"
# the figures are written as JSON.stringify writes a number: 2, not 2.0 or 2e+00
python3 -I - "$fx/command-query.out" <<'PY' || fail=1
import json, sys
bad = 0
for l in open(sys.argv[1]).read().splitlines():
    if l and ("e+" in l.split('"cost_median_ns":')[1].split(",")[0]):
        print("  FAIL: a figure is written with an exponent where JSON.stringify writes none: %s" % l[:120]); bad = 1
sys.exit(bad)
PY
if [ $fail -eq 0 ]; then echo "ok     14, 22 and 23 the command"; else echo "not ok 14, 22 and 23 the command"; fi
exit $fail
