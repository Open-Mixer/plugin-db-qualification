#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# Build the records of a set with plugin-qualify-records-package (plugin-qualify >= 0.17.0), either over the records
# this repository holds or from a new device run. A set is per machine class, per sample rate and per quantum: a run
# that measured several cells gives one set per cell, named <set>-<rate>-<quantum>. Every set goes into the one
# package plugin-qualification-records of its class's architecture (packaging/arch-classes); nothing here is per set.
#
#   tools/build-package.sh [--out <dir>]
#       builds the tool's own .deb of every set under records/<class>/<set>/, for a comparison of its judgement with
#       the records the package ships (same files, same bytes). The version is the debian/changelog one.
#
#   tools/build-package.sh --from-run <run root> --set <set> --provenance <json> --version <version> --host-class <class>
#       takes every <run root>/b<rate>-<quantum>/qualification of a run (the layout of tools/fedora44/measure.sh) as
#       the set <set>-<rate>-<quantum>, as --from with --cell does for each.
#
#   tools/build-package.sh --from <qualification dir> [--cell <rate>/<quantum>] --set <set> --provenance <json> \
#           --version <version> --host-class <class>
#       takes a device's qualification directory (plugin-qualify-sync's qualification_dir): the tool judges which
#       records go in (a record with its probe copy intact; never an unmeasured one) and stamps the provenance, and
#       records/<class>/<set name>/ is replaced by what its package holds; the tool's .deb is then discarded. With
#       --cell the set name is <set>-<rate>-<quantum> and its provenance's grid is that cell; without it the set name
#       is <set>. The class must have an architecture in packaging/arch-classes. The version becomes the spec's
#       Version and the top debian/changelog entry's, and the spec's per-architecture block is written again
#       (tools/sets.py spec: the older names the package takes over follow records/). No other set, of this class or
#       another, is touched. Write the changelog entry, review the diff, commit, tag v<version>.
#
# plugin-qualify comes from the OpenMixer channel (apt) or, where that is not configured, from npm.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
out=$root/out
from=
from_run=
cell=
provenance=
version=
class=
set_=
while [ $# -gt 0 ]; do
    case $1 in
        --out) out=$2; shift 2 ;;
        --from) from=$2; shift 2 ;;
        --from-run) from_run=$2; shift 2 ;;
        --cell) cell=$2; shift 2 ;;
        --provenance) provenance=$2; shift 2 ;;
        --version) version=$2; shift 2 ;;
        --host-class) class=$2; shift 2 ;;
        --set) set_=$2; shift 2 ;;
        *) echo "unknown argument $1" >&2; exit 2 ;;
    esac
done
if [ -n "$from" ] && [ -n "$from_run" ]; then echo "--from and --from-run: one or the other" >&2; exit 2; fi
if [ -n "$cell" ] && [ -z "$from" ]; then echo "--cell goes with --from" >&2; exit 2; fi
if [ -n "$cell" ] && ! [[ $cell =~ ^[1-9][0-9]*/[1-9][0-9]*$ ]]; then echo "--cell is <rate>/<quantum>, not $cell" >&2; exit 2; fi

if ! command -v plugin-qualify-records-package >/dev/null; then
    if command -v apt-get >/dev/null && apt-cache policy plugin-qualify 2>/dev/null | grep -q 'Candidate: [0-9]'; then
        apt-get install -y --no-install-recommends plugin-qualify
    else
        npm install -g @openmixer/plugin-qualify
    fi
fi
tool=$(command -v plugin-qualify-records-package)

if [ -z "$from" ] && [ -z "$from_run" ]; then
    version=$(sed -n '1s/^[^(]*(\([^)]*\)).*/\1/p' "$root/debian/changelog")
    for dir in $(find "$root/records" -mindepth 2 -maxdepth 2 -type d | sort); do
        "$tool" "$dir" --host-class "$(basename "$(dirname "$dir")")" --set "$(basename "$dir")" \
            --provenance "$dir/provenance.json" --version "$version" --out "$out"
    done
    exit 0
fi

: "${provenance:?--provenance is needed}" "${version:?--version is needed}" "${class:?--host-class is needed}" "${set_:?--set is needed}"
spec=$root/packaging/plugin-qualification-records.spec
# a class the package carries: every set goes into the package of its class's architecture
if ! awk -v c="$class" '$1 !~ /^#/ && $3 == c {found = 1} END {exit !found}' "$root/packaging/arch-classes"; then
    echo "class $class has no architecture in packaging/arch-classes: add its line first" >&2; exit 2
fi
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# package_set <qualification dir> <set name> <rate/quantum or empty>: one set into this tree
package_set() {
    local qdir=$1 name=$2 grid=$3 work=$tmp/$2 prov deb rel
    mkdir -p "$work"
    prov=$provenance
    if [ -n "$grid" ]; then
        # the set's provenance names its cell: the one given, with grid set to the one cell this set holds
        prov=$work/provenance.in.json
        python3 -c 'import json, sys
text = sys.argv[1]
p = json.loads(text) if text.lstrip().startswith("{") else json.load(open(text, encoding="utf-8"))
p["grid"] = sys.argv[2]
json.dump(p, open(sys.argv[3], "w", encoding="utf-8"), indent=2)' "$provenance" "$grid" "$prov"
    fi
    "$tool" "$qdir" --host-class "$class" --set "$name" --provenance "$prov" --version "$version" --out "$work"
    deb=$(ls "$work"/*.deb)
    rel=usr/share/omx/qualification/$class/$name
    (cd "$work" && ar x "$deb" && tar -xJf data.tar.xz "./$rel")
    # a host comparison was measured on the old set's plugins: it goes with them, and the new set's is added after
    if ls "$root/records/$class/$name/"*.comparison.json >/dev/null 2>&1; then
        echo "records/$class/$name: its host comparison is dropped with the old records; add the new set's (README, \"The host comparison\")" >&2
    fi
    rm -rf "${root:?}/records/$class/$name"
    mkdir -p "$root/records/$class"
    cp -r "$work/$rel" "$root/records/$class/$name"

    echo "records/$class/$name $version: $(ls "$root/records/$class/$name" | wc -l) files; review git diff"
}

# the version where it lives (the spec and the top debian/changelog entry, which a tag equals), and the spec's
# per-architecture block, whose folded names follow records/
set_version() {
    sed -i "s/^Version: .*/Version: $version/" "$spec"
    if [ "$(sed -n '1s/^[^(]*(\([^)]*\)).*/\1/p' "$root/debian/changelog")" != "$version" ]; then
        sed -i "1s/^\\([a-z0-9.+-]*\\) (.*) unstable/\\1 ($version) unstable/" "$root/debian/changelog"
        echo "debian/changelog: the top entry now names $version; write what this version changes" >&2
    fi
    python3 "$root/tools/sets.py" spec
}

if [ -n "$from" ]; then
    if [ -n "$cell" ]; then
        package_set "$from" "$set_-${cell%/*}-${cell#*/}" "$cell"
    else
        package_set "$from" "$set_" ""
    fi
    set_version
    exit 0
fi

# a run: one set per b<rate>-<quantum>/qualification
found=0
for qdir in "$from_run"/b*-*/qualification; do
    [ -d "$qdir" ] || continue
    base=$(basename "$(dirname "$qdir")")
    if ! [[ $base =~ ^b([1-9][0-9]*)-([1-9][0-9]*)$ ]]; then
        echo "$qdir: $base is not b<rate>-<quantum>" >&2; exit 2
    fi
    package_set "$qdir" "$set_-${BASH_REMATCH[1]}-${BASH_REMATCH[2]}" "${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
    found=$((found + 1))
done
[ "$found" -gt 0 ] || { echo "$from_run holds no b<rate>-<quantum>/qualification" >&2; exit 2; }
set_version
echo "$found sets from $from_run"
