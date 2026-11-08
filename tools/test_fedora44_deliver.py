#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""tools/fedora44/measure.sh delivers its records: deliver() commits them to the branch, and a push that fails is red.

    python3 -m unittest tools/test_fedora44_deliver.py

deliver() is cut out of the script and run against a bare repository on disk.
"""
import os
import re
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, 'fedora44', 'measure.sh')


def deliver_function():
    text = open(SCRIPT).read()
    m = re.search(r'^deliver\(\) \{\n.*?^\}\n', text, re.S | re.M)
    assert m, 'deliver() is not in measure.sh'
    return m.group(0)


class Deliver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.remote = os.path.join(t, 'remote.git')
        subprocess.run(['git', 'init', '-q', '--bare', self.remote], check=True)
        self.cache = os.path.join(t, 'cache')
        q = os.path.join(self.cache, 'b48000-512', 'qualification')
        os.makedirs(q)
        open(os.path.join(q, 'x.qualification.json'), 'w').write('{}')
        self.out = os.path.join(t, 'out')
        os.makedirs(self.out)
        open(os.path.join(self.out, 'job.log'), 'w').write('log\n')

    def tearDown(self):
        self.tmp.cleanup()

    def run_deliver(self, repo):
        script = 'out=%s cache=%s SET=s1 BASES="48000/512 96000/256" BRANCH=records/fedora44/s1 REPO=%s\nWORK=1\n%s\ndeliver test\n' % (
            self.out, self.cache, repo, deliver_function().replace('/work/deliver', os.path.join(self.tmp.name, 'w')))
        return subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                              env=dict(os.environ, PUSH_WAIT='0', GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null'))

    def test_records_land_on_the_branch(self):
        r = self.run_deliver(self.remote)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        files = subprocess.run(['git', '-C', self.remote, 'ls-tree', '-r', '--name-only', 'records/fedora44/s1'],
                               capture_output=True, text=True, check=True).stdout.split()
        self.assertIn('s1/b48000-512/qualification/x.qualification.json', files)
        self.assertIn('s1/meta/job.log.tail', files)

    def test_a_failed_push_is_red(self):
        r = self.run_deliver(os.path.join(self.tmp.name, 'no-such-remote.git'))
        self.assertNotEqual(r.returncode, 0)

    def test_the_job_does_not_wait_to_be_copied(self):
        self.assertNotIn('waiting to be copied', open(SCRIPT).read())


if __name__ == '__main__':
    unittest.main()
