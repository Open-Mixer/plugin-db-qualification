#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# Package the finished cells of a Raspberry Pi 5's qualification grid into this tree, one set per cell, and print
# their outcome counts.
#
#   tools/rpi5/package-cells.sh <grid dir> <version>
#
# <grid dir> is a copy of the device's grid run: b<rate>-<quantum>/qualification for each cell, a `done` stamp in each
# finished one, and meta/ (model, kernel, packages.tsv, sources.tsv) as the device recorded it. Only stamped cells are
# packaged, each as records/rpi5/zynthian-vangelis-<rate>-<quantum>; a cell marked unsupported is named and skipped.
# The provenance is tools/rpi5/provenance-template.json with the device's own meta and the cell's date.
set -euo pipefail
grid=${1:?grid dir}; version=${2:?version}
root=$(cd "$(dirname "$0")/../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/run"
for d in "$grid"/b*-*/; do
    cell=$(basename "$d")
    if [ -e "$d/unsupported" ]; then echo "$cell: unsupported ($(tail -1 "$d/unsupported")); not packaged"; continue; fi
    [ -e "$d/done" ] || { echo "$cell: not finished; not packaged"; continue; }
    ln -s "$(cd "$d" && pwd)" "$work/run/$cell"
done
ls "$work/run" | grep -q . || { echo "no finished cell in $grid"; exit 0; }
measured=$(date -u -r "$(ls -t "$grid"/b*-*/done | head -1)" +%F)
python3 -I - "$root/tools/rpi5/provenance-template.json" "$grid/meta" "$work/provenance.json" "$measured" <<'EOF'
import json, os, sys
template, meta, dst, measured = sys.argv[1:]
d = json.load(open(template, encoding="utf-8"))
read = lambda n: open(os.path.join(meta, n), encoding="utf-8").read().strip()
tsv = lambda n: dict(l.split("\t", 1) for l in read(n).splitlines() if "\t" in l)
d.update({"board": read("model"), "kernel": read("kernel"), "measured": measured,
          "sources": tsv("sources.tsv"), "packages": tsv("packages.tsv")})
json.dump(d, open(dst, "w", encoding="utf-8"), indent=2)
open(dst, "a").write("\n")
EOF
"$root/tools/build-package.sh" --from-run "$work/run" --provenance "$work/provenance.json" --version "$version" \
    --host-class rpi5 --set zynthian-vangelis
for c in "$work/run"/*; do
    cell=$(basename "$c"); cell=${cell#b}
    python3 "$root/tools/outcomes.py" "$root/records/rpi5/zynthian-vangelis-$cell"
done
