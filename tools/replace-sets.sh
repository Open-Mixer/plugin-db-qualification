#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# Replace the sets of one machine class with new qualification runs.
#
#   tools/replace-sets.sh <class> <out-dir> <set>...
#
# <out-dir>/<set>/ is the `plugin-qualify --out` directory of each new set (*.qualification.json and *.probe.json files),
# <out-dir>/<set>.provenance.json its provenance. Run it from the root of the repository, on a clean tree:
#   1. every new set is checked to be there before anything is removed;
#   2. `git rm` of the class's old sets;
#   3. `tools/sets.py import` of each new set (it runs tools/check-records.py on it);
#   4. `tools/sets.py spec`, and `tools/sets.py check`;
#   5. the base database is built from records/ to a temporary file (tools/records-db.py; the contract directory is
#      $OMX_CONTRACT_PATH, else libomx-domain's contractdir);
#   6. the checks and the test suite.
# REPLACE_SETS_SKIP=base,suite leaves out steps 5 and 6 (the test of this script does). Nothing is committed: look at
# `git status`, then commit the removal, the import and the spec in their own commits.
set -euo pipefail

usage() { echo "usage: tools/replace-sets.sh <class> <out-dir> <set>..." >&2; exit 2; }
[ "$#" -ge 3 ] || usage
class=$1 out=$2
shift 2
skip=${REPLACE_SETS_SKIP:-}

grep -Eq "^[a-z0-9]+ +[a-z0-9_]+ +${class}( |\$)" packaging/arch-classes || { echo "replace-sets: $class is no class of packaging/arch-classes" >&2; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "replace-sets: the tree is not clean" >&2; exit 1; }
for s in "$@"; do
    [ -d "$out/$s" ] || { echo "replace-sets: $out/$s: no such directory" >&2; exit 1; }
    [ -f "$out/$s.provenance.json" ] || { echo "replace-sets: $out/$s.provenance.json: no such file" >&2; exit 1; }
done

echo "== git rm: the old sets of $class"
git rm -r -q "records/$class"
for s in "$@"; do
    echo "== import $class/$s"
    python3 tools/sets.py import "$class" "$s" "$out/$s" --provenance "$out/$s.provenance.json"
    git add "records/$class/$s"
done
echo "== spec and check"
python3 tools/sets.py spec
python3 tools/sets.py check

case ",$skip," in *,base,*) ;; *)
    echo "== the base database from records/"
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    python3 tools/records-db.py --records records --out "$tmp/qualification.sqlite" \
        --contract-dir "${OMX_CONTRACT_PATH:-$(pkg-config --variable=contractdir libomx-domain)}" --built-from-file BUILT_FROM
    ;;
esac
case ",$skip," in *,suite,*) ;; *)
    echo "== the checks and the suite"
    python3 tools/check-records.py
    PDQ_SIBLINGS=${PDQ_SIBLINGS:?PDQ_SIBLINGS names the sibling clones the suite reads the owners words from} \
        systemd-run --user --scope -q -p MemoryMax=2G python3 -B -m unittest tools.test_records_db tools.test_rewrite_records \
        tools.test_check_records tools.test_qualification_db_write tools.test_sets tools.test_build_package \
        tools.test_no_relations tools.test_dev_requires tools.test_replace_sets
    ;;
esac
echo "replace-sets: done; commit the removal, the import and the spec in their own commits"
