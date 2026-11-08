#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""tools/fedora44/channel-check.sh: the pod's mod-host-protocol must come from the OpenMixer channel.

    python3 -m unittest tools/test_fedora44_channel_check.py

The script reads the installed package's repository id from FROM_REPO when set (the test), else from dnf.
"""
import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, 'fedora44', 'channel-check.sh')


def run(from_repo):
    env = dict(os.environ, FROM_REPO=from_repo)
    return subprocess.run(['bash', SCRIPT], env=env, capture_output=True, text=True)


class ChannelCheck(unittest.TestCase):
    def test_channel_repos_pass(self):
        for repo in ('openmixer', 'openmixer-noarch'):
            self.assertEqual(run(repo).returncode, 0, repo)

    def test_stock_fedora_fails(self):
        for repo in ('fedora', 'updates', 'copr:copr.fedorainfracloud.org:ycollet:audinux', '@System', ''):
            r = run(repo)
            self.assertNotEqual(r.returncode, 0, repo)
            self.assertIn('not the channel build', r.stdout + r.stderr)

    def test_version_text_is_not_the_fact(self):
        # a plain version with no "omx" in it (the channel's builds since 0.10.9) passes by its repository alone
        self.assertEqual(run('openmixer').returncode, 0)


if __name__ == '__main__':
    unittest.main()
