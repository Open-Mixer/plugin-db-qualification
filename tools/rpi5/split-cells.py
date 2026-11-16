#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""One-shot: convert records/rpi5/zynthian-vangelis, whose records each hold several cells, to one set per cell.

    tools/rpi5/split-cells.py convert <old set dir> <class dir>
    tools/rpi5/split-cells.py verify  <old set dir> <class dir>

convert writes <class dir>/<set>-<rate>-<quantum>/ for every cell any record of <old set dir> measured. A record goes
into the set of each cell of its measurements.grid, identical except that its grid holds that cell alone; its probe
output is copied byte for byte; the provenance is the old one with its set, package name and grid naming the cell.
Nothing is re-measured and no value is changed.

verify reads the old set and the new sets and compares exactly: every identity field and every other field of every
record, the one grid entry of each cell, every probe output's bytes, every provenance field but the three that name the
set; no new record without an old one, no old cell without its record. It prints one proof line and exits 1 on a
difference. It was run once, against `git archive` of the commit before the conversion; the old set is gone since.
"""
import copy
import json
import os
import sys

RECORD = ".qualification.json"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def canon(obj):
    return json.dumps(obj, sort_keys=True)


def cell_key(g):
    return (g["rate"], g["quantum"])


def cells_of(rec):
    return [cell_key(g) for g in rec["measurements"]["grid"]]


def base(old):
    return os.path.basename(os.path.normpath(old))


def set_name(old, cell):
    return f"{base(old)}-{cell[0]}-{cell[1]}"


def old_records(old):
    return sorted(n for n in os.listdir(old) if n.endswith(RECORD))


def split(rec, cell):
    new = copy.deepcopy(rec)
    new["measurements"]["grid"] = [g for g in rec["measurements"]["grid"] if cell_key(g) == cell]
    return new


def provenance(prov, name, cell):
    new = copy.deepcopy(prov)
    new["set"] = name
    new["package"]["name"] = f"plugin-db-qualification-{prov['hostClass']}-{name}"
    new["grid"] = f"{cell[0]}/{cell[1]}"
    return new


def dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def convert(old, dest):
    prov = load(os.path.join(old, "provenance.json"))
    cells = sorted({c for n in old_records(old) for c in cells_of(load(os.path.join(old, n)))})
    for cell in cells:
        out = os.path.join(dest, set_name(old, cell))
        os.makedirs(out)
        dump(os.path.join(out, "provenance.json"), provenance(prov, set_name(old, cell), cell))
    for n in old_records(old):
        rec = load(os.path.join(old, n))
        probe = rec["probe"]["file"]
        with open(os.path.join(old, probe), "rb") as f:
            data = f.read()
        for cell in cells_of(rec):
            out = os.path.join(dest, set_name(old, cell))
            dump(os.path.join(out, n), split(rec, cell))
            with open(os.path.join(out, probe), "wb") as f:
                f.write(data)
    return cells


def without_grid(rec):
    out = {k: v for k, v in rec.items() if k != "measurements"}
    out["measurements"] = {k: v for k, v in rec["measurements"].items() if k != "grid"}
    return out


def verify(old, dest):
    prov = load(os.path.join(old, "provenance.json"))
    bad = []
    seen = {}
    pairs = probes = records = 0
    for n in old_records(old):
        rec = load(os.path.join(old, n))
        records += 1
        pname = rec["probe"]["file"]
        with open(os.path.join(old, pname), "rb") as f:
            probe_bytes = f.read()
        for cell in cells_of(rec):
            sdir = os.path.join(dest, set_name(old, cell))
            seen.setdefault(cell, set()).add(n)
            try:
                new = load(os.path.join(sdir, n))
            except OSError:
                bad.append(f"{sdir}/{n}: missing")
                continue
            pairs += 1
            entry = [g for g in rec["measurements"]["grid"] if cell_key(g) == cell]
            if new["measurements"]["grid"] != entry or canon(new["measurements"]["grid"]) != canon(entry):
                bad.append(f"{sdir}/{n}: the cell {cell} differs")
            if canon(without_grid(rec)) != canon(without_grid(new)) or list(rec) != list(new):
                bad.append(f"{sdir}/{n}: a field outside the grid differs")
            try:
                with open(os.path.join(sdir, pname), "rb") as f:
                    if f.read() != probe_bytes:
                        bad.append(f"{sdir}/{pname}: bytes differ")
                    probes += 1
            except OSError:
                bad.append(f"{sdir}/{pname}: missing")
    for cell, names in sorted(seen.items()):
        sdir = os.path.join(dest, set_name(old, cell))
        have = {x for x in os.listdir(sdir) if x.endswith(RECORD)}
        if have != names:
            bad.append(f"{sdir}: holds {len(have)} records, the old set has {len(names)} for the cell")
        np = load(os.path.join(sdir, "provenance.json"))
        named = ("set", "grid", "package")
        if canon({k: v for k, v in np.items() if k not in named}) != canon({k: v for k, v in prov.items() if k not in named}) or list(np) != list(prov):
            bad.append(f"{sdir}/provenance.json: a field beyond set, package and grid differs")
        if (np["set"] != set_name(old, cell) or np["grid"] != f"{cell[0]}/{cell[1]}"
                or canon({k: v for k, v in np["package"].items() if k != "name"}) != canon({k: v for k, v in prov["package"].items() if k != "name"})):
            bad.append(f"{sdir}/provenance.json: set, grid or package version wrong")
    for s in sorted(os.listdir(dest)):
        if s.startswith(base(old) + "-") and s not in {set_name(old, c) for c in seen}:
            bad.append(f"{dest}/{s}: a set of no old cell")
    for b in bad[:20]:
        print(b)
    if bad:
        print(f"round trip FAILED: {len(bad)} differences")
        return 1
    print(f"round trip ok: {records} old records, {len(seen)} cells, {pairs} per-cell records and {probes} probe outputs "
          "equal to the old ones, every field exact, no value changed")
    return 0


def main(argv):
    if len(argv) != 3 or argv[0] not in ("convert", "verify"):
        print(__doc__)
        return 2
    if argv[0] == "convert":
        for c in convert(argv[1], argv[2]):
            print(set_name(argv[1], c))
        return 0
    return verify(argv[1], argv[2])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
