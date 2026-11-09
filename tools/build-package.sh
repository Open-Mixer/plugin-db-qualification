#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# Build the records packages with plugin-qualify-records-package (plugin-qualify >= 0.17.0), either over the records
# this repository holds or from a new device run. A set is per machine class, per sample rate and per quantum: a run
# that measured several cells gives one set per cell, named <set>-<rate>-<quantum>, each its own package
# plugin-db-qualification-<class>-<set name>.
#
#   tools/build-package.sh [--out <dir>]
#       builds the .deb of every set under records/<class>/<set>/ with the tool, for a comparison with the packages
#       the release builds from debian/ (same files, same bytes). The version is the debian/changelog one.
#
#   tools/build-package.sh --from-run <run root> --set <set> --provenance <json> --version <version> --host-class <class>
#       takes every <run root>/b<rate>-<quantum>/qualification of a run (the layout of tools/fedora44/measure.sh) as
#       the set <set>-<rate>-<quantum>, as --from with --cell does for each.
#
#   tools/build-package.sh --from <qualification dir> [--cell <rate>/<quantum>] --set <set> --provenance <json> \
#           --version <version> --host-class <class>
#       takes a device's qualification directory (plugin-qualify-sync's qualification_dir): the tool judges which
#       records go in (a record with its probe copy intact; never an unmeasured one) and builds the package, and
#       records/<class>/<set name>/ is replaced by what the package holds. With --cell the set name is
#       <set>-<rate>-<quantum> and its provenance's grid is that cell; without it the set name is <set>.
#       A set of the class the RPM spec builds (packaging/plugin-db-qualification.spec, %global host_class) is added
#       to the spec's %global sets list and the spec's Version changes; the tool's .deb is used for its judgement of
#       which records go in and is discarded. A set of any other class is a Debian package: its debian/control stanza
#       (Depends and Description from the tool's own control) and debian/<package>.install are written, and the top
#       debian/changelog entry takes the version. No other set, of this class or another, is touched.
#       Review the diff, commit, tag v<version>.
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
spec=$root/packaging/plugin-db-qualification.spec
rpm_class=$(sed -n 's/^%global host_class //p' "$spec")
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# package_set <qualification dir> <set name> <rate/quantum or empty>: one set into this tree
package_set() {
    local qdir=$1 name=$2 grid=$3 work=$tmp/$2 prov deb pkg rel
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
    pkg=$(basename "$deb" | cut -d_ -f1)
    rel=usr/share/omx/qualification/$class/$name
    (cd "$work" && ar x "$deb" && tar -xJf data.tar.xz "./$rel" && tar -xJf control.tar.xz ./control)
    # a host comparison was measured on the old set's plugins: it goes with them, and the new set's is added after
    if ls "$root/records/$class/$name/"*.comparison.json >/dev/null 2>&1; then
        echo "records/$class/$name: its host comparison is dropped with the old records; add the new set's (README, \"The host comparison\")" >&2
    fi
    rm -rf "${root:?}/records/$class/$name"
    mkdir -p "$root/records/$class"
    cp -r "$work/$rel" "$root/records/$class/$name"

    if [ "$class" = "$rpm_class" ]; then
        # an RPM set: the records are the tool's, the package is the spec's; the set joins the spec's list
        local sets
        sets=$(sed -n 's/^%global sets //p' "$spec" | sed 's/%{nil}//')
        # shellcheck disable=SC2086 # the list is words
        sets=$(printf '%s\n' $sets "$name" | sort -u | tr '\n' ' ' | sed 's/ $//')
        sed -i "s/^%global sets .*/%global sets $sets/; s/^Version: .*/Version: $version/" "$spec"
        echo "$pkg $version (RPM): $(ls "$root/records/$class/$name" | wc -l) files; review git diff"
        # one version for both formats: an RPM-only run leaves debian/changelog to be written, and says so
        if [ "$(sed -n '1s/^[^(]*(\([^)]*\)).*/\1/p' "$root/debian/changelog")" != "$version" ]; then
            echo "debian/changelog: add a $version entry (the tag equals the spec and the changelog; tools/sets.py check holds them)" >&2
        fi
        return
    fi
    # a Debian set: its stanza in debian/control (replaced where it is, else added) and its own install file; the
    # package's own control is the source of the stanza's Depends and Description
    python3 - "$root/debian/control" "$work/control" "$pkg" <<'EOF'
import sys
path, tool_control, pkg = sys.argv[1:]
tool = open(tool_control, encoding="utf-8").read()
depends = next(l[len("Depends: "):] for l in tool.splitlines() if l.startswith("Depends: "))
description = tool[tool.index("\nDescription:") + 1:].rstrip("\n")
stanza = f"Package: {pkg}\nArchitecture: all\nMulti-Arch: foreign\nDepends: ${{misc:Depends}}, {depends}\nProvides: plugin-qualification-records\n{description}"
paras = [p for p in open(path, encoding="utf-8").read().strip("\n").split("\n\n") if p.strip()]
names = [next((l[len("Package: "):] for l in p.splitlines() if l.startswith("Package: ")), None) for p in paras]
if pkg in names:
    paras[names.index(pkg)] = stanza
else:
    paras.append(stanza)
open(path, "w", encoding="utf-8").write("\n\n".join(paras) + "\n")
EOF
    echo "records/$class/$name usr/share/omx/qualification/$class" > "$root/debian/$pkg.install"
    # every records package carries long file names and is not an upload that closes a bug
    [ -f "$root/debian/$pkg.lintian-overrides" ] ||
        printf '%s: package-has-long-file-name *\n%s: initial-upload-closes-no-bugs\n' "$pkg" "$pkg" > "$root/debian/$pkg.lintian-overrides"
    sed -i "1s/^\\([a-z0-9.+-]*\\) (.*) unstable/\\1 ($version) unstable/" "$root/debian/changelog"
    echo "$pkg $version: $(ls "$root/records/$class/$name" | wc -l) files; review git diff"
}

if [ -n "$from" ]; then
    if [ -n "$cell" ]; then
        package_set "$from" "$set_-${cell%/*}-${cell#*/}" "$cell"
    else
        package_set "$from" "$set_" ""
    fi
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
echo "$found sets from $from_run"
