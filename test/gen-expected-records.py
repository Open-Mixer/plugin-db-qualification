#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""Regenerates test/fixtures/records/*.json: the documents the Python exporter of the qualification store spec
(section 5, tools/qualification_db.py) writes for the records of the fixture store records.sqlite, which test 21 of
the reader compares with pqdb_record_json, byte for byte.

    gen-expected-records.py <qualification_db.py> <records.sqlite> <out dir>

The exporter's own tree does not yet map the three fields section 3.5 added (hostExtensions, rtSafety.ownThreads and
rtSafety.otherThreads); this script adds them after the exporter has run, at the places the spec's table names:
hostExtensions after testedVersion, ownThreads and otherThreads after processErrors. Delete that part when the exporter
maps them itself and the files below are unchanged. A document is the compact JSON of one record, no trailing newline.
Usage of the fixture store: make-fixtures.py <dir> writes <dir>/records.sqlite."""
import importlib.util, json, os, sqlite3, sys

def after(d, anchor, new):
    """d with the items of `new` inserted after the key `anchor` (the order of a dict is the order of the document)."""
    out = {}
    for k, v in d.items():
        out[k] = v
        if k == anchor:
            out.update(new)
    return out if anchor in d else {**d, **new}

def main(module, store, out_dir):
    spec = importlib.util.spec_from_file_location("qualification_db", module)
    qdb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qdb)
    db = sqlite3.connect(store)
    exp = qdb.Exporter(db)
    os.makedirs(out_dir, exist_ok=True)
    for rid, fmt, uri, offer, cls, ext in db.execute(
            "SELECT r.record_id, p.format, p.uri, r.offer, r.host_class, r.host_extensions FROM record r "
            "JOIN plugin p ON p.plugin_id = r.plugin_id ORDER BY r.record_id").fetchall():
        doc = exp.export_record(rid)
        if ext == 1:
            names = [r[0] for r in db.execute("SELECT extension FROM record_extension WHERE record_id = ? ORDER BY ord", (rid,))]
            doc = after(doc, "testedVersion", {"hostExtensions": names})
        cells = db.execute("SELECT rt_interposer, rt_own_threads, rt_other_allocations, rt_other_locks, rt_other_syscalls "
                           "FROM cell WHERE record_id = ? ORDER BY ord", (rid,)).fetchall()
        for c, (interposer, own, oa, ol, osy) in zip(doc["measurements"]["grid"], cells):
            add = {}
            if own is not None:
                add["ownThreads"] = own
            if oa is not None:
                add["otherThreads"] = {"allocationsInRun": oa, "locksInRun": ol, "syscallsInRun": osy}
            if add and interposer is not None:
                c["rtSafety"] = after(c["rtSafety"], "processErrors", add)
        name = "%s-%s.%s.%s.json" % (fmt, uri.split(":")[-1], offer, cls)
        with open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="") as f:
            f.write(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))

if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
