#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""Check the record sets under records/<host class>/<set>/ the way plugin-qualify-sync will read them.

    tools/check-records.py [<set dir> ...]

Without arguments every set under records/ is checked. A set passes when:

- its provenance.json is plugin-qualify.distributed-provenance/1, names the set and host class of its directory,
  and the package plugin-db-qualification-<host class>-<set>;
- every *.qualification.json is a plugin-qualify.qualification-record/1 with its binary's files and its probe output
  beside it, whose size and SHA-256 are the ones the record names (a record with no verdict for the provenance's
  hostProfile is counted and named, not refused: the sync only skips it under that host);
- every *.probe.json is the probe output of a record (nothing is shipped that no record judged);
- every *.comparison.json is a plugin-qualify.comparison-record/1 (plugin-qualify compare: one plugin through
  omx-clap-host, plugin-hostd, mod-host and jalv with the same checks), and a set that holds them holds their
  comparison-summary.json, a publishable plugin-qualify.comparison-summary/1 of exactly those records, in which mod-host
  and jalv ran: a comparison without its references is never shipped;
- nothing else is in the directory (no *.unmeasured.json: an unmeasured record never applies);
- a set of one cell, named <set>-<rate>-<quantum> (fedora44-48000-512), holds only records whose measurement grid
  holds that cell, and its provenance's grid names it: a set is per machine class, per sample rate and per quantum.

The exit code is 0 when every set passes and 1 otherwise; each problem is printed on its own line.
"""
import hashlib
import json
import os
import re
import sys

RECORD = ".qualification.json"
PROBE = ".probe.json"
PROVENANCE_SCHEMA = "plugin-qualify.distributed-provenance/1"
RECORD_SCHEMA = "plugin-qualify.qualification-record/1"
COMPARISON = ".comparison.json"
SUMMARY = "comparison-summary.json"
COMPARISON_SCHEMA = "plugin-qualify.comparison-record/1"
SUMMARY_SCHEMA = "plugin-qualify.comparison-summary/1"
HOSTS = ("omx-clap-host", "plugin-hostd", "mod-host", "jalv")
REFERENCES = ("mod-host", "jalv")
CHECKS = {"loads", "instantiates", "output", "cycles", "soak", "rtSafe"}
FIGURES = {"cpu", "latency"}
CHECK_RESULTS = {"pass", "fail", "not-observable", "not-run"}
FIGURE_RESULTS = {"measured", "not-observable", "not-run"}
CELL_SET = re.compile(r"-([1-9][0-9]*)-([1-9][0-9]*)$")
COUNTS = ("loads", "instantiates", "output", "runsClean", "rtSafe", "rtObserved", "crashes")


def set_cell(set_name):
    """The (rate, quantum) a set of one cell is named for (fedora44-48000-512), or None for a set that names none."""
    m = CELL_SET.search(set_name)
    return (int(m.group(1)), int(m.group(2))) if m else None


def grid_cells(grid):
    """The cells a provenance's grid names: "48000/512", "48000/256,96000/256", or a list of those or of {rate, quantum}."""
    if isinstance(grid, str):
        return {(int(r), int(q)) for r, q in re.findall(r"([0-9]+)/([0-9]+)", grid)}
    cells = set()
    for g in grid if isinstance(grid, list) else []:
        if isinstance(g, dict) and isinstance(g.get("rate"), int) and isinstance(g.get("quantum"), int):
            cells.add((g["rate"], g["quantum"]))
        elif isinstance(g, str):
            cells |= grid_cells(g)
    return cells


def record_cells(rec):
    """The cells a qualification record measured (measurements.grid)."""
    return {(g.get("rate"), g.get("quantum")) for g in ((rec.get("measurements") or {}).get("grid") or []) if isinstance(g, dict)}


def comparison_problems(rec):
    """What makes a comparison record not one; the rules of plugin-qualify's comparisonRecordProblems, and the checks'."""
    out = []
    if rec.get("schema") != COMPARISON_SCHEMA:
        out.append(f"schema is {rec.get('schema')!r}")
    plugin = rec.get("plugin") or {}
    if not isinstance(plugin.get("id"), str) or not isinstance(plugin.get("format"), str):
        out.append("names no plugin")
    cond = rec.get("conditions") or {}
    if not all(isinstance(cond.get(k), int) and cond.get(k) > 0 for k in ("rate", "quantum", "cycles", "soakS", "timeoutMs")):
        out.append("its conditions name no rate, quantum, cycles, soak or timeout")
    rows = rec.get("hosts")
    if not isinstance(rows, list) or not rows:
        out.append("holds no host row")
        return out
    seen = set()
    for h in rows:
        host = h.get("host")
        if host not in HOSTS:
            out.append(f"a row of the unknown host {host!r}")
            continue
        if host in seen:
            out.append(f"{host}: two rows")
        seen.add(host)
        status = h.get("status")
        if status in ("skipped", "not-applicable"):
            if not h.get("reason"):
                out.append(f"{host}: {status} with no reason")
            continue
        if status != "ran":
            out.append(f"{host}: status {status!r}")
            continue
        checks = h.get("checks") or {}
        if not isinstance(h.get("runsClean"), bool):
            out.append(f"{host}: ran with no runsClean")
        for k in sorted(CHECKS | FIGURES):
            c = checks.get(k)
            allowed = CHECK_RESULTS if k in CHECKS else FIGURE_RESULTS
            if not isinstance(c, dict) or c.get("result") not in allowed:
                out.append(f"{host}: check {k} is {c.get('result') if isinstance(c, dict) else c!r}")
    return out


def summary_problems(summary, set_name, host_class, records):
    """A shipped summary: publishable, of this set, of exactly these records, with both references run."""
    out = []
    if summary.get("schema") != SUMMARY_SCHEMA:
        out.append(f"schema is {summary.get('schema')!r}")
    if summary.get("set") != set_name or summary.get("hostClass") != host_class:
        out.append(f"names set {summary.get('set')!r} and host class {summary.get('hostClass')!r}, not its directory's")
    if summary.get("publishable") is not True:
        out.append(f"is not publishable ({'; '.join(m.get('host', '?') + ': ' + m.get('reason', '') for m in summary.get('missing') or []) or 'no --publish'})")
    if summary.get("records") != len(records):
        out.append(f"counts {summary.get('records')!r} records, the directory holds {len(records)}")
    hosts = {h.get("host"): h for h in summary.get("hosts") or []}
    for ref in REFERENCES:
        if (hosts.get(ref) or {}).get("status") != "ran":
            out.append(f"{ref} did not run: a comparison is measured against mod-host and jalv")
    for name, h in hosts.items():
        if h.get("status") == "ran" and not h.get("version"):
            out.append(f"{name}: ran with no version")
        plugins = h.get("plugins")
        for k in COUNTS:
            v = h.get(k)
            if not isinstance(v, int) or not isinstance(plugins, int) or v < 0 or v > plugins:
                out.append(f"{name}: {k} is {v!r} of {plugins!r} plugins")
        # the counts are the records': recount them, so a summary never says what its records do not
        rows = [r for rec in records for r in rec.get("hosts") or [] if r.get("host") == name and r.get("status") == "ran"]
        recount = {
            "plugins": len(rows),
            "runsClean": sum(1 for r in rows if r.get("runsClean") is True),
            "rtSafe": sum(1 for r in rows if ((r.get("checks") or {}).get("rtSafe") or {}).get("result") == "pass"),
            "crashes": sum(1 for r in rows if r.get("crash")),
        }
        for k, v in recount.items():
            if h.get(k) != v:
                out.append(f"{name}: {k} is {h.get(k)!r}, its records give {v}")
    return out


def check_set(path):
    problems = []
    path = os.path.normpath(path)
    set_name = os.path.basename(path)
    host_class = os.path.basename(os.path.dirname(path))

    def bad(name, why):
        problems.append(f"{path}/{name}: {why}")

    try:
        with open(os.path.join(path, "provenance.json"), encoding="utf-8") as f:
            prov = json.load(f)
    except (OSError, ValueError) as e:
        bad("provenance.json", f"does not read ({e})")
        return problems, 0
    if prov.get("schema") != PROVENANCE_SCHEMA:
        bad("provenance.json", f"schema is {prov.get('schema')!r}, not {PROVENANCE_SCHEMA}")
    if prov.get("set") != set_name or prov.get("hostClass") != host_class:
        bad("provenance.json", f"names set {prov.get('set')!r} and host class {prov.get('hostClass')!r}, not its directory's")
    want = f"plugin-db-qualification-{host_class}-{set_name}"
    if (prov.get("package") or {}).get("name") != want:
        bad("provenance.json", f"names the package {(prov.get('package') or {}).get('name')!r}, not {want}")
    host = prov.get("hostProfile")
    if not isinstance(host, str) or not host:
        bad("provenance.json", "names no hostProfile")
    cell = set_cell(set_name)
    if cell is not None and cell not in grid_cells(prov.get("grid")):
        bad("provenance.json", f"its grid {prov.get('grid')!r} does not name {cell[0]}/{cell[1]}, the cell of the set's name")

    names = sorted(os.listdir(path))
    judged = set()
    records = 0
    without_verdict = 0
    comparisons = []
    for name in names:
        if name == "provenance.json" or name.endswith(PROBE):
            continue
        if name.endswith(COMPARISON):
            try:
                with open(os.path.join(path, name), encoding="utf-8") as f:
                    rec = json.load(f)
            except (OSError, ValueError) as e:
                bad(name, f"does not read ({e})")
                continue
            for why in comparison_problems(rec):
                bad(name, why)
            comparisons.append(rec)
            continue
        if name == SUMMARY:
            continue
        if not name.endswith(RECORD):
            bad(name, "is neither a record, a probe output nor the provenance")
            continue
        records += 1
        try:
            with open(os.path.join(path, name), encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError) as e:
            bad(name, f"does not read ({e})")
            continue
        if rec.get("schema") != RECORD_SCHEMA:
            bad(name, f"schema is {rec.get('schema')!r}")
        if cell is not None and cell not in record_cells(rec):
            cells = ", ".join(f"{r}/{q}" for r, q in sorted(record_cells(rec), key=str)) or "no cell"
            bad(name, f"measured {cells}, not {cell[0]}/{cell[1]}, the cell of the set's name")
        binary = rec.get("binary") or {}
        files = binary.get("files")
        if not isinstance(binary.get("path"), str) or not isinstance(files, list) or not files:
            bad(name, "names no binary with its files")
        elif any(not isinstance(x.get("path"), str) or len(str(x.get("sha256", ""))) != 64 for x in files):
            bad(name, "a file of its binary has no path or no SHA-256")
        if isinstance(host, str) and not any(v.get("host") == host for v in rec.get("verdicts") or []):
            without_verdict += 1
        probe = rec.get("probe") or {}
        pname = probe.get("file")
        if not isinstance(pname, str) or not pname.endswith(PROBE) or os.path.basename(pname) != pname:
            bad(name, f"names no probe output beside it ({pname!r})")
            continue
        judged.add(pname)
        try:
            with open(os.path.join(path, pname), "rb") as f:
                data = f.read()
        except OSError:
            bad(name, f"its probe output {pname} is missing")
            continue
        if probe.get("bytes") is not None and probe.get("bytes") != len(data):
            bad(pname, f"is {len(data)} bytes, the record says {probe.get('bytes')}")
        if hashlib.sha256(data).hexdigest() != probe.get("sha256"):
            bad(pname, "does not hash as its record says")
    for name in names:
        if name.endswith(PROBE) and name not in judged:
            bad(name, "is the probe output of no record")
    if SUMMARY in names:
        try:
            with open(os.path.join(path, SUMMARY), encoding="utf-8") as f:
                summary = json.load(f)
        except (OSError, ValueError) as e:
            bad(SUMMARY, f"does not read ({e})")
        else:
            for why in summary_problems(summary, set_name, host_class, comparisons):
                bad(SUMMARY, why)
    elif comparisons:
        bad(SUMMARY, f"is missing, and the set holds {len(comparisons)} comparison records")
    if comparisons:
        print(f"{path}: {len(comparisons)} comparison records")
    if records == 0:
        problems.append(f"{path}: holds no record")
    if without_verdict:
        print(f"{path}: {without_verdict} records hold no verdict for {host} and never apply under it")
    return problems, records


def main(argv):
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "records")
    sets = argv or sorted(
        os.path.join(root, c, s)
        for c in os.listdir(root)
        for s in os.listdir(os.path.join(root, c))
        if os.path.isdir(os.path.join(root, c, s))
    )
    failed = False
    for s in sets:
        problems, records = check_set(s)
        for p in problems:
            print(p)
        failed = failed or bool(problems)
        print(f"{os.path.normpath(s)}: {records} records, {'FAILED' if problems else 'ok'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
