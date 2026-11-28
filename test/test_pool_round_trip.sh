#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# The pool word round trip (the owner's ruling of 2026-11-28): a record whose pool step ended `cores` is stored by the
# writer (the word is QUALIFICATION_STEP_RESULTS's in the qualification domain), and the reader gives its pin pool=cores.
# The control: a contract directory whose domain lacks the word refuses the put by name, and nothing is stored.
# Usage: test_pool_round_trip.sh <test_reader> <contract dir>
set -u
reader=$1; cdir=$2
here=$(cd "$(dirname "$0")/.." && pwd)
rec=$here/records/x86-64/fedora44-192000-128/co.midilab.JC303@unversioned-8e3a7b84c86d.custom.qualification.json
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
fail=0
python3 -c 'import json,sys
r=json.load(open(sys.argv[1]))
for s in r["run"]["steps"]:
    if s["step"] == "pool": s["result"] = "cores"
json.dump(r, open(sys.argv[2], "w"))' "$rec" "$work/cores.json"
put() { python3 "$here/tools/plugin-qualification-db-write" put --scope user --offer custom --host-class x86-64 --root "$1" \
          --schema "$here/schema/qualification.sql" --contract-dir "$2" < "$work/cores.json"; }
mkdir -p "$work/a"
if put "$work/a" "$cdir" 2> "$work/err"; then
  layer=$(find "$work/a" -name '*.sqlite' | head -1)
  got=$("$reader" pins "$layer" "$cdir" omx-clap-host | grep '^co.midilab.JC303 ')
  case "$got" in
    "co.midilab.JC303 isolated cores 0") echo "ok     a pool step of cores is stored and its pin says pool=cores" ;;
    *) echo "not ok the pin of the stored record: '$got'"; fail=1 ;;
  esac
else
  echo "not ok the writer refused a pool step of cores: $(cat "$work/err")"; fail=1
fi
# the control: the domain without the word
cp -r "$cdir" "$work/old"
python3 -c 'import json,sys
p=sys.argv[1]+"/qualification/qualification.json"; d=json.load(open(p))
i=d["components"]["schemas"]["QUALIFICATION_STEP_RESULTS"]; i["oneOf"]=[w for w in i["oneOf"] if w["const"]!="cores"]
json.dump(d, open(p, "w"))' "$work/old"
mkdir -p "$work/b"
if put "$work/b" "$work/old" 2> "$work/err2"; then
  echo "not ok a domain without cores still stored the record"; fail=1
elif grep -q 'cores' "$work/err2"; then
  echo "ok     a domain without the word refuses the put, by the word"
else
  echo "not ok the refusal does not name the word: $(cat "$work/err2")"; fail=1
fi
exit $fail
