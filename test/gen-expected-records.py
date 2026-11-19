#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""Regenerates test/fixtures/records/*.json: the documents the Python exporter of the qualification store spec
(section 5, tools/qualification_db.py) writes for the records of the fixture store records.sqlite, which test 21 of
the reader compares with pqdb_record_json, byte for byte.

    gen-expected-records.py <qualification_db.py> <records.sqlite> <out dir>

The exporter's own tree does not yet map the three fields section 3.5 added (hostExtensions, rtSafety.ownThreads and
rtSafety.otherThreads, latencyLineMs, rules and a cell's latencyMs); this script adds them after the exporter has run, where the reader writes them:
hostExtensions before measuredAt, latencyLineMs and rules after it, a cell's latencyMs after its latency (the order of
plugin-qualify's record), ownThreads and otherThreads before the events of rtSafety. Delete that part when the exporter
maps them itself and the files below are unchanged. A document is the compact JSON of one record, no trailing newline.
Usage of the fixture store: make-fixtures.py <dir> writes <dir>/records.sqlite."""
import importlib.util, json, os, sqlite3, sys

def before(d, anchor, new):
    """d with the items of `new` inserted before the key `anchor` (the order of a dict is the order of the document)."""
    out = {}
    for k, v in d.items():
        if k == anchor:
            out.update(new)
        out[k] = v
    return out

def js(v):
    """A number as JSON.stringify writes it: 10, not 10.0."""
    return int(v) if isinstance(v, float) and v == int(v) else v

def history(db, rid):
    """history[] of a record, in plugin-qualify's order (HistoryBlock, Adjustment)."""
    blocks = []
    for (ho, hc, file, at, ku, kd, found, ws, wg, sc, sr, unk) in db.execute(
            "SELECT ord, host_class, file, at, key_uri, key_digest, found, windows_solo, windows_grouped, summary_crashed, "
            "summary_raises_xruns, unknown_keys FROM record_history WHERE record_id = ? ORDER BY ord", (rid,)).fetchall():
        b = {"hostClass": hc, "file": file, "at": at}
        if ku is not None:
            b["key"] = {"uri": ku, "digest": kd}
        b["found"] = bool(found)
        if ws is not None:
            b["windows"] = {"solo": ws, "grouped": wg}
        if sc is not None:
            b["summary"] = {"crashed": bool(sc), "raisesXruns": bool(sr)}
        if unk == 1:
            b["unknownKeys"] = {n: v for n, v in db.execute("SELECT name, value FROM history_unknown_key WHERE record_id = ? AND history_ord = ? ORDER BY rowid", (rid, ho))}
        b["verdicts"] = []
        for (vo, host, measured, adjusted, move, reason, blocked) in db.execute(
                "SELECT ord, host, measured, adjusted, move, reason, blocked_by FROM history_verdict "
                "WHERE record_id = ? AND history_ord = ? ORDER BY ord", (rid, ho)).fetchall():
            v = {"host": host, "measured": measured, "adjusted": adjusted, "move": move, "reason": reason}
            if blocked == 1:
                v["blockedBy"] = [r[0] for r in db.execute("SELECT code FROM history_blocked WHERE record_id = ? AND history_ord = ? "
                                                           "AND verdict_ord = ? ORDER BY ord", (rid, ho, vo))]
            b["verdicts"].append(v)
        blocks.append(b)
    return blocks

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
            doc = before(doc, "measuredAt", {"hostExtensions": names})
        row = db.execute("SELECT plugin_name FROM record WHERE record_id = ?", (rid,)).fetchone()
        if row[0] is not None:
            doc["plugin"] = {**doc["plugin"], "name": row[0]}
        steps = doc["run"]["steps"]
        for st, pr in zip(steps, db.execute("SELECT pool_dsp_load_off, pool_dsp_load_on, pool_xruns_off, pool_xruns_on "
                                            "FROM run_step WHERE record_id = ? ORDER BY ord", (rid,))):
            new = {k: js(v) for k, v in zip(("dspLoadOff", "dspLoadOn", "xrunsOff", "xrunsOn"), pr) if v is not None}
            if new:
                st["pool"] = {**st.get("pool", {}), **new}
        lm, rules = db.execute("SELECT latency_line_ms, rules FROM record WHERE record_id = ?", (rid,)).fetchone()
        add = {}
        if lm is not None:
            add["latencyLineMs"] = float(lm) if float(lm) != int(lm) else int(lm)    # JSON.stringify writes 10, not 10.0
        if rules is not None:
            add["rules"] = rules
        hist = history(db, rid)
        if hist:
            add["history"] = hist
        if add:
            out = {}
            for k, v in doc.items():
                out[k] = v
                if k == "measuredAt":
                    out.update(add)
            doc = out
        lat = [r[0] for r in db.execute("SELECT latency_ms FROM cell WHERE record_id = ? ORDER BY ord", (rid,))]
        for c, v in zip(doc["measurements"]["grid"], lat):
            if v is not None:
                v = float(v) if float(v) != int(v) else int(v)
                keys = list(c)
                pos = keys.index("latency") + 1 if "latency" in c else 3
                c.update({k: c.pop(k) for k in keys[pos:]})      # move what follows to the end,
                c["latencyMs"] = v                               # put latencyMs where it belongs,
                c.update({k: c.pop(k) for k in keys[pos:]})      # and the rest after it
        cells = db.execute("SELECT rt_interposer, rt_own_threads, rt_other_allocations, rt_other_locks, rt_other_syscalls "
                           "FROM cell WHERE record_id = ? ORDER BY ord", (rid,)).fetchall()
        for c, (interposer, own, oa, ol, osy) in zip(doc["measurements"]["grid"], cells):
            add = {}
            if own is not None:
                add["ownThreads"] = own
            if oa is not None:
                add["otherThreads"] = {"allocationsInRun": oa, "locksInRun": ol, "syscallsInRun": osy}
            if add and interposer is not None:
                c["rtSafety"] = before(c["rtSafety"], "events", add)
        name = "%s-%s.%s.%s.json" % (fmt, uri.split(":")[-1], offer, cls)
        with open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="") as f:
            f.write(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))

if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
