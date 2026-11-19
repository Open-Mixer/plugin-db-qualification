# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The provenance of a fedora44 run says the scheduling the run had, from its own meta/rt.txt: a run granted
SCHED_FIFO (the reference tier) is never published as one that ran without real-time priority."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "fedora44"))
import provenance  # noqa: E402

TEMPLATE = os.path.join(HERE, "fedora44", "provenance-template.json")

RT = """ulimit -r 95 -l unlimited
SCHED_FIFO: yes
CapEff:	00000000a88465fb
base 48000/256: jackd pid 4167, 1 thread(s) at SCHED_FIFO
"""


class provenance_case(unittest.TestCase):

    def run_of(self, rt=None):
        meta = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(meta))
        with open(os.path.join(meta, "installed.txt"), "w") as f:
            for k in provenance.HOST:
                f.write(f"{k} 1.0\n")
        open(os.path.join(meta, "plugin-packages.tsv"), "w").write("calf\t0.90\n")
        open(os.path.join(meta, "lscpu"), "w").write("Model name: AMD Ryzen 7 PRO 8700GE\n")
        open(os.path.join(meta, "uname"), "w").write("Linux h2 7.2.7-300.fc45.x86_64 #1\n")
        if rt is not None:
            open(os.path.join(meta, "rt.txt"), "w").write(rt)
        dst = os.path.join(meta, "provenance.json")
        provenance.main(TEMPLATE, meta, dst, "20261109rt-c48000-256", "0" * 40, "2026-11-09")
        return json.load(open(dst))

    def test_a_run_granted_sched_fifo_says_so(self):
        p = self.run_of(RT)
        self.assertIn("SCHED_FIFO", p["realtime"])
        self.assertNotIn("none", p["realtime"])
        self.assertIn("ulimit -r 95 -l unlimited", p["realtime"])
        self.assertIn("1 thread(s) at SCHED_FIFO", p["jack"])
        self.assertNotIn("not real-time", p["jack"])

    def test_a_run_refused_sched_fifo_or_with_no_rt_record_keeps_the_template(self):
        template = json.load(open(TEMPLATE))
        for rt in (None, RT.replace("SCHED_FIFO: yes", "SCHED_FIFO: refused")):
            p = self.run_of(rt)
            self.assertEqual(p["realtime"], template["realtime"])
            self.assertEqual(p["jack"], template["jack"])


if __name__ == "__main__":
    unittest.main()
