# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The fedora44 Job measures the reference tier: real-time priority, in the namespace that grants it."""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
JOB = open(os.path.join(HERE, "fedora44", "job.yaml"), encoding="utf-8").read()
MEASURE = open(os.path.join(HERE, "fedora44", "measure.sh"), encoding="utf-8").read()


class RealTime(unittest.TestCase):
    def test_the_job_runs_in_the_real_time_namespace(self):
        self.assertRegex(JOB, r"(?m)^  namespace: omx-qualify-rt$")

    def test_the_container_adds_sys_nice_and_ipc_lock(self):
        caps = re.search(r"capabilities: \{add: \[([^\]]*)\]\}", JOB)
        self.assertIsNotNone(caps)
        self.assertEqual(sorted(c.strip() for c in caps.group(1).split(",")), ["IPC_LOCK", "SYS_NICE"])

    def test_jackd_starts_with_real_time_priority(self):
        starts = re.findall(r"jackd (-[^\n;]*) -d dummy -r \$rate -p \$per", MEASURE)
        self.assertTrue(starts)
        for args in starts:
            self.assertIn("-R", args.split())
            self.assertNotIn("-r", args.split())

    def test_a_base_without_sched_fifo_is_refused(self):
        self.assertIn("for t in /proc/${jpid:-0}/task/*; do chrt -p", MEASURE)
        self.assertIn('[ "$fifo" -eq 0 ]', MEASURE)
        self.assertRegex(MEASURE, r"not SCHED_FIFO[^\n]*\n\s*kill \$sup; pkill -x jackd; return 1")


if __name__ == "__main__":
    unittest.main()
