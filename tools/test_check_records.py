#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""tools/check-records.py on the comparison records: a set built in a temporary directory, then broken one way at a time.

    python3 -m unittest tools/test_check_records.py
"""
import copy
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("check_records", os.path.join(HERE, "check-records.py"))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

COND = {"rate": 48000, "quantum": 256, "cycles": 5, "soakS": 10, "windowMs": 2000, "timeoutMs": 10000, "jack": "jackd 1.9.22", "realtime": "rtprio 70"}
PASS = {k: {"result": "pass"} for k in ("loads", "instantiates", "output", "cycles", "soak", "rtSafe")}
FIG = {"cpu": {"result": "measured", "percent": 0.5}, "latency": {"result": "not-observable", "detail": "mod-host sets no JACK latency callback"}}
VERSIONS = {"omx-clap-host": "omx-clap-host 0.27.0", "plugin-hostd": "plugin-hostd 0.16.0", "mod-host": "mod-host 0.10.6", "jalv": "jalv 1.8.0"}


def row(host, clean=True):
    checks = {**copy.deepcopy(PASS), **copy.deepcopy(FIG)}
    if not clean:
        checks["soak"] = {"result": "fail", "detail": "the host ended during the soak (SIGSEGV)"}
    r = {"host": host, "version": VERSIONS[host], "status": "ran", "checks": checks, "runsClean": clean}
    if not clean:
        r["crash"] = {"step": "soak", "signal": "SIGSEGV"}
    return r


def record(uri, dirty=()):
    return {
        "schema": "plugin-qualify.comparison-record/1",
        "plugin": {"format": "lv2", "id": uri},
        "stimulus": "tone",
        "conditions": COND,
        "measuredAt": "2026-11-04T10:00:00.000Z",
        "hosts": [row(h, h not in dirty) for h in check.HOSTS],
    }


def summary(records):
    hosts = []
    for h in check.HOSTS:
        rows = [r for rec in records for r in rec["hosts"] if r["host"] == h]
        n = len(rows)
        clean = sum(1 for r in rows if r["runsClean"])
        crashes = sum(1 for r in rows if r.get("crash"))
        hosts.append({"host": h, "version": VERSIONS[h], "status": "ran", "plugins": n, "loads": n, "instantiates": n, "output": n,
                      "runsClean": clean, "rtSafe": n, "rtObserved": n, "crashes": crashes, "cpuMedianPercent": 0.5,
                      "latencyObservable": h != "mod-host"})
    return {"schema": "plugin-qualify.comparison-summary/1", "hostClass": "x86-64", "set": "t", "measured": "2026-11-04",
            "publishable": True, "missing": [], "conditions": COND, "records": len(records), "common": len(records),
            "hosts": hosts, "beats": {}}


class ComparisonRecords(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.set = os.path.join(self.tmp.name, "x86-64", "t")
        os.makedirs(self.set)
        probe = b"{}"
        self.write("provenance.json", {"schema": check.PROVENANCE_SCHEMA, "set": "t", "hostClass": "x86-64",
                                       "package": {"name": "plugin-db-qualification-x86-64-t"}, "hostProfile": "omx-clap-host"})
        with open(os.path.join(self.set, "a.probe.json"), "wb") as f:
            f.write(probe)
        self.write("a.default.qualification.json", {
            "schema": check.RECORD_SCHEMA, "binary": {"path": "a.so", "files": [{"path": "a.so", "sha256": "0" * 64}]},
            "verdicts": [{"host": "omx-clap-host"}], "probe": {"file": "a.probe.json", "bytes": len(probe), "sha256": hashlib.sha256(probe).hexdigest()}})
        self.records = [record("urn:a"), record("urn:b", dirty=("mod-host",))]
        for i, r in enumerate(self.records):
            self.write(f"p{i}-lv2-000000000000.comparison.json", r)
        self.write(check.SUMMARY, summary(self.records))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, obj):
        with open(os.path.join(self.set, name), "w", encoding="utf-8") as f:
            json.dump(obj, f)

    def problems(self):
        return check.check_set(self.set)[0]

    def test_a_whole_set_passes(self):
        self.assertEqual(self.problems(), [])

    def test_comparison_records_need_their_summary(self):
        os.remove(os.path.join(self.set, check.SUMMARY))
        self.assertTrue(any("is missing, and the set holds 2 comparison records" in p for p in self.problems()))

    def test_an_unpublishable_summary_is_not_shipped(self):
        s = summary(self.records)
        s["publishable"] = False
        s["missing"] = [{"host": "jalv", "reason": "jalv is not installed (not on PATH)"}]
        self.write(check.SUMMARY, s)
        self.assertTrue(any("is not publishable (jalv: jalv is not installed" in p for p in self.problems()))

    def test_both_references_ran(self):
        s = summary(self.records)
        s["hosts"] = [h for h in s["hosts"] if h["host"] != "jalv"]
        self.write(check.SUMMARY, s)
        self.assertTrue(any("jalv did not run" in p for p in self.problems()))

    def test_the_summary_counts_are_its_records(self):
        s = summary(self.records)
        next(h for h in s["hosts"] if h["host"] == "mod-host")["runsClean"] = 2
        self.write(check.SUMMARY, s)
        self.assertTrue(any("mod-host: runsClean is 2, its records give 1" in p for p in self.problems()))

    def test_a_row_without_its_checks_is_refused(self):
        r = record("urn:a")
        del r["hosts"][2]["checks"]["rtSafe"]
        r["hosts"][3] = {"host": "jalv", "version": None, "status": "skipped"}
        self.write("p0-lv2-000000000000.comparison.json", r)
        p = self.problems()
        self.assertTrue(any("mod-host: check rtSafe is None" in x for x in p))
        self.assertTrue(any("jalv: skipped with no reason" in x for x in p))

    def test_not_observable_is_a_result_not_a_failure(self):
        r = record("urn:a")
        r["hosts"][2]["checks"]["rtSafe"] = {"result": "not-observable", "detail": "no callback"}
        self.write("p0-lv2-000000000000.comparison.json", r)
        s = summary([r, self.records[1]])
        mod = next(h for h in s["hosts"] if h["host"] == "mod-host")
        mod["rtSafe"], mod["rtObserved"] = 1, 1
        self.write(check.SUMMARY, s)
        self.assertEqual(self.problems(), [])


class OneCellSets(unittest.TestCase):
    """A set named <set>-<rate>-<quantum> holds only that cell: its records measured it and its provenance names it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.set = os.path.join(self.tmp.name, "x86-64", "t-48000-512")
        os.makedirs(self.set)
        self.prov = {"schema": check.PROVENANCE_SCHEMA, "set": "t-48000-512", "hostClass": "x86-64", "grid": "48000/512",
                     "package": {"name": "plugin-db-qualification-x86-64-t-48000-512"}, "hostProfile": "omx-clap-host"}
        self.write("provenance.json", self.prov)
        self.add_record("a", [(48000, 512)])

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, obj):
        with open(os.path.join(self.set, name), "w", encoding="utf-8") as f:
            json.dump(obj, f)

    def add_record(self, name, cells):
        probe = name.encode()
        with open(os.path.join(self.set, f"{name}.probe.json"), "wb") as f:
            f.write(probe)
        self.write(f"{name}.default.qualification.json", {
            "schema": check.RECORD_SCHEMA, "binary": {"path": "a.so", "files": [{"path": "a.so", "sha256": "0" * 64}]},
            "verdicts": [{"host": "omx-clap-host"}],
            "measurements": {"grid": [{"rate": r, "quantum": q, "outcome": "probe.ok"} for r, q in cells]},
            "probe": {"file": f"{name}.probe.json", "bytes": len(probe), "sha256": hashlib.sha256(probe).hexdigest()}})

    def problems(self):
        return check.check_set(self.set)[0]

    def test_a_set_of_its_cell_passes(self):
        self.assertEqual(self.problems(), [])

    def test_a_record_of_another_cell_is_refused(self):
        self.add_record("b", [(96000, 256)])
        self.assertTrue(any("b.default.qualification.json: measured 96000/256, not 48000/512" in p for p in self.problems()))

    def test_a_record_with_no_grid_is_refused(self):
        self.add_record("c", [])
        self.assertTrue(any("c.default.qualification.json: measured no cell, not 48000/512" in p for p in self.problems()))

    def test_a_record_that_also_measured_other_cells_passes(self):
        self.add_record("d", [(48000, 256), (48000, 512)])
        self.assertEqual(self.problems(), [])

    def test_the_provenance_names_the_cell(self):
        self.write("provenance.json", {**self.prov, "grid": "96000/256"})
        self.assertTrue(any("its grid '96000/256' does not name 48000/512" in p for p in self.problems()))
        self.write("provenance.json", {k: v for k, v in self.prov.items() if k != "grid"})
        self.assertTrue(any("its grid None does not name 48000/512" in p for p in self.problems()))

    def test_a_set_that_names_no_cell_is_not_held_to_one(self):
        self.assertIsNone(check.set_cell("zynthian-vangelis"))
        self.assertEqual(check.set_cell("zynthian-vangelis-48000-256"), (48000, 256))
        self.assertEqual(check.grid_cells("48000/256,96000/256; adapter passes at 48000/128"), {(48000, 256), (96000, 256), (48000, 128)})
        self.assertEqual(check.grid_cells([{"rate": 48000, "quantum": 512}, "96000/256"]), {(48000, 512), (96000, 256)})


if __name__ == "__main__":
    unittest.main()
