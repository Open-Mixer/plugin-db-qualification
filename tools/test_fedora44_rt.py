# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The fedora44 Job measures the reference tier: real-time priority, in the namespace that grants it."""
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
MEASURE_PATH = os.path.join(HERE, "fedora44", "measure.sh")
with open(os.path.join(HERE, "fedora44", "job.yaml"), encoding="utf-8") as _f:
    JOB = yaml.safe_load(_f)
with open(MEASURE_PATH, encoding="utf-8") as _f:
    MEASURE = _f.read()

# a stand-in chrt: the policy of a thread is the content of the file the fake /proc tree holds for it
FAKE_CHRT = """#!/bin/bash
[ "$1" = -p ] || exit 2
f=$(ls "$PROC"/*/task/"$2"/policy 2>/dev/null | head -1)
[ -n "$f" ] || exit 1
echo "pid $2's current scheduling policy: $(cat "$f")"
echo "pid $2's current scheduling priority: 70"
"""


class RealTime(unittest.TestCase):
    def test_the_job_runs_in_the_real_time_namespace(self):
        self.assertEqual(JOB["metadata"]["namespace"], "omx-qualify-rt")

    def test_the_container_adds_sys_nice_and_ipc_lock(self):
        containers = JOB["spec"]["template"]["spec"]["containers"]
        self.assertTrue(containers)
        for c in containers:
            self.assertEqual(sorted(c["securityContext"]["capabilities"]["add"]), ["IPC_LOCK", "SYS_NICE"])

    def test_jackd_starts_with_real_time_priority(self):
        starts = re.findall(r"jackd (-[^\n;]*) -d dummy -r \$rate -p \$per", MEASURE)
        self.assertTrue(starts)
        for args in starts:
            self.assertIn("-R", args.split())
            self.assertNotIn("-r", args.split())


class FifoCheck(unittest.TestCase):
    """measure.sh's own fifo_refused, defined by the script and run here over a fake /proc and a fake chrt."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proc = os.path.join(self.tmp.name, "proc")
        self.bin = os.path.join(self.tmp.name, "bin")
        os.makedirs(self.bin)
        chrt = os.path.join(self.bin, "chrt")
        with open(chrt, "w") as f:
            f.write(FAKE_CHRT)
        os.chmod(chrt, os.stat(chrt).st_mode | stat.S_IXUSR)
        # the two functions only, cut out of the script (sourcing measure.sh would run the whole Job)
        defs = re.search(r"(?ms)^fifo_threads\(\) \{.*?^\}\n^fifo_refused\(\)[^\n]*\n", MEASURE)
        self.assertIsNotNone(defs)
        self.defs = defs.group(0)

    def tearDown(self):
        self.tmp.cleanup()

    def jackd(self, pid, *policies):
        for i, pol in enumerate(policies):
            d = os.path.join(self.proc, str(pid), "task", str(pid + i))
            os.makedirs(d)
            with open(os.path.join(d, "policy"), "w") as f:
                f.write(pol)

    def refused(self, pid):
        env = {"PATH": self.bin + ":/usr/bin:/bin", "PROC": self.proc}
        r = subprocess.run(["bash", "-c", self.defs + f'fifo_refused "$1"', "x", pid], env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.stderr, "")
        return r.returncode == 0

    def test_a_base_without_sched_fifo_is_refused(self):
        self.jackd(100, "SCHED_OTHER", "SCHED_OTHER")
        self.assertTrue(self.refused("100"))
        # no jackd at all
        self.assertTrue(self.refused(""))
        self.assertTrue(self.refused("999"))
        # jack2 keeps its main thread at SCHED_OTHER; its audio thread is the one at SCHED_FIFO
        self.jackd(200, "SCHED_OTHER", "SCHED_FIFO")
        self.assertFalse(self.refused("200"))


if __name__ == "__main__":
    unittest.main()
