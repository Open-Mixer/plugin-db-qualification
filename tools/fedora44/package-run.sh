#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# Package the cells a fedora44 Job delivered into this tree, one set per cell, and print their outcome counts.
#
#   tools/fedora44/package-run.sh <RUN> <version>
#
# Reads branch records/fedora44/<RUN> from origin (the Job's own delivery: <RUN>/b<rate>-<quantum>/qualification),
# refuses a run whose Job is still writing it (a cell with no rest-stage record count in <RUN>/meta/job.log.tail), and
# runs tools/build-package.sh --from-run on it with --set fedora44, so each cell becomes
# records/x86-64/fedora44-<rate>-<quantum>. The provenance is tools/fedora44/provenance-template.json (what the Job's
# manifest fixes) with what the run itself recorded in <RUN>/meta: the machine, the kernel, every package and the
# plugin set, the date and the branch's revision. Review git diff, then commit.
set -euo pipefail
run=${1:?RUN}; version=${2:?version}
root=$(cd "$(dirname "$0")/../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git -C "$root" fetch -q origin "refs/heads/records/fedora44/$run"
sha=$(git -C "$root" rev-parse FETCH_HEAD)
git -C "$root" archive FETCH_HEAD "$run" | tar -x -C "$work"
# the last delivery carries the log up to the rest stage's record count of its last cell
for d in "$work/$run"/b*-*/; do
    cell=$(basename "$d"); cell=${cell#b}; cell=${cell/-//}
    grep -q "^stage rest $cell: [0-9]* records" "$work/$run/meta/job.log.tail" ||
        { echo "records/fedora44/$run ($sha): cell $cell has not finished its rest stage; not packaged" >&2; exit 1; }
done
measured=$(sed -n 's/^start \([0-9-]*\)T.*/\1/p' "$work/$run/meta/job.log.tail" | head -1)
python3 -I "$root/tools/fedora44/provenance.py" "$root/tools/fedora44/provenance-template.json" "$work/$run/meta" \
    "$work/provenance.json" "$run" "$sha" "$measured"
"$root/tools/build-package.sh" --from-run "$work/$run" --provenance "$work/provenance.json" --version "$version" \
    --host-class x86-64 --set fedora44
for d in "$work/$run"/b*-*/; do
    cell=$(basename "$d"); cell=${cell#b}
    python3 "$root/tools/outcomes.py" "$root/records/x86-64/fedora44-$cell"
done
