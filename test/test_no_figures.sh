#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# A quick check that ran and ended with no figures (spec section 6.0; plugin-hostd's pins-from-the-store spec, section 9
# point 7, decided by the coordinator, the owner to confirm): each of the three endings is stored by the writer and read
# back by the reader as refused with its reason; one with no reason, or a word that is no reason, is refused by the
# writer by name and nothing is written; other files are no match; a record with figures put for the plugin takes its
# place; a layer at user_version 2 is migrated to 3 on open.
# Usage: test_no_figures.sh <test_reader> <contract dir>
set -u
reader=$1; cdir=$2
here=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
fail=0
ok() { echo "ok     $1"; }
bad() { echo "not ok $1"; fail=1; }
A=$(printf 'a%.0s' $(seq 64)); B=$(printf 'b%.0s' $(seq 64))
URI=co.midilab.JC303
nf() { root=$1; shift
       python3 "$here/tools/plugin-qualification-db-write" no-figures --scope user --root "$root" --schema "$here/schema/qualification.sql" \
         --contract-dir "$cdir" --format clap --uri "$URI" --host omx-clap-host --file "JC303.clap=$A" "$@" 2>"$work/err"; }
layer() { find "$1" -name '*.sqlite' | head -1; }
read_back() { "$reader" nofig "$(layer "$1")" "$cdir" clap "$URI" omx-clap-host "JC303.clap=$2"; }
for reason in probe.crashed probe.memory-limit probe.timeout; do
  d=$work/$reason; mkdir -p "$d"
  if nf "$d" --reason "$reason"; then
    got=$(read_back "$d" "$A")
    [ "$got" = "refused $reason" ] && ok "$reason is stored and read back refused, with its reason" || bad "$reason read back as '$got'"
    got=$(read_back "$d" "$B")
    [ "$got" = "none" ] && ok "$reason: other bytes are no match" || bad "$reason: other bytes read back as '$got'"
  else
    bad "$reason refused by the writer: $(cat "$work/err")"
  fi
done
for r in "" probe.ok; do
  d=$work/bad-$r; mkdir -p "$d"
  if nf "$d" --reason "$r"; then bad "a record with no figures and the reason '$r' was stored"
  elif grep -q 'refused: no-figures-reason' "$work/err" && [ -z "$(layer "$d")" ]; then ok "the reason '$r' is refused by name, and nothing is written"
  else bad "the reason '$r': $(cat "$work/err")"; fi
done
# a record with figures for the plugin takes the figure-less one's place
d=$work/put; mkdir -p "$d"
nf "$d" --reason probe.timeout
[ "$(read_back "$d" "$A")" = "refused probe.timeout" ] || bad "the figure-less record to be replaced was not stored"
rec=$here/records/x86-64/fedora44-192000-128/co.midilab.JC303@unversioned-8e3a7b84c86d.custom.qualification.json
if python3 "$here/tools/plugin-qualification-db-write" put --scope user --offer custom --host-class x86-64 --root "$d" \
     --schema "$here/schema/qualification.sql" --contract-dir "$cdir" < "$rec" 2>"$work/err"; then
  got=$(read_back "$d" "$A")
  [ "$got" = "none" ] && ok "a record with figures takes the figure-less one's place" || bad "after a put: '$got'"
else
  bad "the put of a record with figures: $(cat "$work/err")"
fi
# a layer at 2 (no no_figures table) is migrated to 3 when the reader opens it
d=$work/v2; mkdir -p "$d"
python3 "$here/tools/plugin-qualification-db-write" put --scope user --offer custom --host-class x86-64 --root "$d" \
  --schema "$here/schema/qualification.sql" --contract-dir "$cdir" < "$rec"
python3 -c 'import sqlite3,sys
c=sqlite3.connect(sys.argv[1]); c.execute("DROP TABLE no_figures_file"); c.execute("DROP TABLE no_figures")
c.execute("PRAGMA user_version = 2"); c.commit()' "$(layer "$d")"
got=$(read_back "$d" "$A")
v=$(python3 -c 'import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute("PRAGMA user_version").fetchone()[0])' "$(layer "$d")")
[ "$got" = "none" ] && [ "$v" = 3 ] && ok "a layer at 2 is migrated to 3 on open" || bad "a layer at 2: '$got', user_version $v"
exit $fail
