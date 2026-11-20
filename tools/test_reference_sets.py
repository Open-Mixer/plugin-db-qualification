#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The x86-64 sets of the reference tier, measured with real-time priority, beside the non-real-time sets: each is a
set of its own, named fedora44-rt-<rate>-<quantum>, and reads as plugin-qualify-sync reads it (tools/check-records.py).
The non-real-time sets keep their names and their tier. Where both tiers hold a cell, the reader answers with the
reference tier (the store spec, section 4; test/test_reader.c and test/test_command.sh).

    python3 -m unittest tools/test_reference_sets.py
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
X86 = os.path.join(ROOT, "records", "x86-64")
spec = importlib.util.spec_from_file_location("sets", os.path.join(HERE, "sets.py"))
sets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sets)

# the 22 runs of the fedora44 Job with real-time priority, one set per cell
REFERENCE = sorted([f"fedora44-rt-{r}-{q}" for r in (44100, 48000, 88200, 96000) for q in (64, 128, 256, 512)]
                   + [f"fedora44-rt-{r}-{q}" for r in (176400, 192000) for q in (128, 256, 512)])
# the non-real-time sets: the ten main held before the reference tier joined, and the run at 192000/128
# (records/fedora44/20261109-c192000-128), which joins as a set of its own
PROVISIONAL = sorted([f"fedora44-{r}-{q}" for r in (48000, 96000) for q in (64, 128, 256, 512)]
                     + [f"fedora44-192000-{q}" for q in (128, 256, 512)])
RECORDS_PER_SET = 1109


def provenance(name):
    with open(os.path.join(X86, name, "provenance.json"), encoding="utf-8") as f:
        return json.load(f)


class ReferenceSets(unittest.TestCase):
    def test_the_sets(self):
        """The x86-64 class holds the 22 reference sets and the 11 non-real-time sets, and nothing else."""
        self.assertEqual(sorted(os.listdir(X86)), sorted(REFERENCE + PROVISIONAL))

    def test_tier_from_the_name(self):
        """A set named fedora44-rt-* is of the reference tier, measured with SCHED_FIFO granted; every other x86-64 set
        is provisional: the tier reads from the name."""
        for name in sorted(os.listdir(X86)):
            p = provenance(name)
            with self.subTest(set=name):
                if name in REFERENCE:
                    self.assertEqual(p.get("tier"), "reference")
                    self.assertTrue(p["realtime"].startswith("SCHED_FIFO granted"), p["realtime"])
                    self.assertIn("SCHED_FIFO", p["jack"])
                else:
                    self.assertEqual(p.get("tier"), "provisional")
                    self.assertNotIn("-rt-", name)

    def test_each_set_whole(self):
        """Each reference set: its own name and package in its provenance, its one cell, 1109 records each with its
        probe output, the provenance, and nothing else."""
        for name in REFERENCE:
            with self.subTest(set=name):
                p = provenance(name)
                rate, quantum = map(int, re.search(r"-([0-9]+)-([0-9]+)$", name).groups())
                self.assertEqual(p["set"], name)
                self.assertEqual(p["hostClass"], "x86-64")
                self.assertEqual(p["package"]["name"], f"plugin-db-qualification-x86-64-{name}")
                self.assertEqual(p["cell"], {"rate": rate, "quantum": quantum})
                files = os.listdir(os.path.join(X86, name))
                recs = [f for f in files if f.endswith(".qualification.json")]
                probes = [f for f in files if f.endswith(".probe.json")]
                self.assertEqual(len(recs), RECORDS_PER_SET)
                self.assertEqual(sorted(f[: -len(".qualification.json")] for f in recs),
                                 sorted(f[: -len(".probe.json")] for f in probes))
                self.assertEqual(len(files), 2 * RECORDS_PER_SET + 1)

    def test_the_non_real_time_run_at_192000_128(self):
        """The run without real-time priority at 192000/128 is a set of its own, tier provisional, 120 records with
        their probe outputs, beside the reference set of that cell; its provenance names its records branch."""
        name = "fedora44-192000-128"
        p = provenance(name)
        self.assertEqual(p.get("tier"), "provisional")
        self.assertTrue(p["realtime"].startswith("none"), p["realtime"])
        self.assertEqual(p["cell"], {"rate": 192000, "quantum": 128})
        self.assertEqual(p["package"]["name"], f"plugin-db-qualification-x86-64-{name}")
        self.assertIn("records/fedora44/20261109-c192000-128", " ".join(p["sources"]))
        files = os.listdir(os.path.join(X86, name))
        self.assertEqual(len([f for f in files if f.endswith(".qualification.json")]), 120)
        self.assertEqual(len([f for f in files if f.endswith(".probe.json")]), 120)
        self.assertEqual(len(files), 241)
        r = subprocess.run([sys.executable, "-B", os.path.join(HERE, "check-records.py"), os.path.join(X86, name)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-2000:])

    def test_the_sets_read(self):
        """tools/check-records.py reads every reference set with no refusal."""
        r = subprocess.run([sys.executable, "-B", os.path.join(HERE, "check-records.py")]
                           + [os.path.join(X86, n) for n in REFERENCE], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-4000:])

    def test_packaged(self):
        """The amd64 and x86_64 packages carry every reference set, at its cell, and the measured-on class of its name
        is fedora44, so tools/sets.py prove proves it on a fedora44 image."""
        for kind, arch in (("deb", "amd64"), ("rpm", "x86_64")):
            carried = {s for c, s in sets.carried(ROOT, kind, arch) if c == "x86-64"}
            self.assertTrue(set(REFERENCE) <= carried, sorted(set(REFERENCE) - carried))
        for name in REFERENCE:
            self.assertEqual(sets.measured_on(name), "fedora44")


if __name__ == "__main__":
    unittest.main()
