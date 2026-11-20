#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""tools/replace-sets.sh <class> <out-dir> <set>...: the runbook for when a class is measured again.

    python3 -m unittest tools/test_replace_sets.py

It removes the class's old sets from git, imports each new set from <out-dir>/<set>/ (a `plugin-qualify --out`
directory) with <out-dir>/<set>.provenance.json (tools/sets.py import), rewrites the spec's per-architecture block, builds
the base database from the new records and runs the checks. The test runs it on a small git repository: the old sets go,
the new ones come, a refusal stops it before anything is removed.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(HERE, "replace-sets.sh")
SRC = os.path.join(ROOT, "records", "x86-64", "fedora44-48000-512")


def git(cwd, *args):
    return subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false",
                           *args], capture_output=True, text=True, check=True).stdout


class ReplaceSets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pdq-replace-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tree = os.path.join(self.tmp, "tree")
        for d in ("packaging", "debian", "tools"):
            shutil.copytree(os.path.join(ROOT, d), os.path.join(self.tree, d), ignore=shutil.ignore_patterns("__pycache__", "testdata"))
        shutil.copy2(os.path.join(ROOT, "BUILT_FROM"), self.tree)
        for old in ("fedora44-48000-512", "fedora44-96000-256"):
            d = os.path.join(self.tree, "records", "x86-64", old)
            os.makedirs(d)
            open(os.path.join(d, "provenance.json"), "w").write("{}")
        shutil.copytree(os.path.join(ROOT, "records", "rpi5"), os.path.join(self.tree, "records", "rpi5"))
        git(self.tree, "init", "-q")
        git(self.tree, "add", "-A")
        git(self.tree, "commit", "-q", "-m", "tree")
        self.out = os.path.join(self.tmp, "runs")
        n = sorted(f for f in os.listdir(SRC) if f.endswith(".qualification.json"))[0]
        probe = json.load(open(os.path.join(SRC, n)))["probe"]["file"]
        for s in ("fedora45-48000-512",):
            os.makedirs(os.path.join(self.out, s))
            shutil.copy2(os.path.join(SRC, n), os.path.join(self.out, s))
            shutil.copy2(os.path.join(SRC, probe), os.path.join(self.out, s))
            json.dump({"schema": "plugin-qualify.distributed-provenance/1", "set": s, "hostClass": "x86-64",
                       "package": {"name": f"plugin-db-qualification-x86-64-{s}"}, "hostProfile": "omx-clap-host", "grid": "48000/512"},
                      open(os.path.join(self.out, s + ".provenance.json"), "w"))

    def run_script(self, *args):
        env = dict(os.environ, REPLACE_SETS_SKIP="base,suite")   # the base and the suite are the caller's run, not this test's
        return subprocess.run(["bash", SCRIPT, *args], cwd=self.tree, capture_output=True, text=True, env=env)

    def test_it_is_a_bash_script_that_parses(self):
        self.assertTrue(os.path.exists(SCRIPT), SCRIPT)
        self.assertEqual(subprocess.run(["bash", "-n", SCRIPT]).returncode, 0)

    def test_no_arguments_is_a_usage_error(self):
        self.assertEqual(self.run_script().returncode, 2)
        self.assertEqual(self.run_script("x86-64", self.out).returncode, 2)

    def test_the_old_sets_go_and_the_new_come(self):
        r = self.run_script("x86-64", self.out, "fedora45-48000-512")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(os.listdir(os.path.join(self.tree, "records", "x86-64"))), ["fedora45-48000-512"])
        self.assertIn("records/x86-64/fedora44-48000-512", git(self.tree, "status", "--short"))
        self.assertTrue(os.path.isdir(os.path.join(self.tree, "records", "rpi5", "zynthian-vangelis")), "another class is untouched")

    def test_a_missing_set_directory_stops_it_before_anything_is_removed(self):
        r = self.run_script("x86-64", self.out, "fedora45-96000-256")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn(f"replace-sets: {self.out}/fedora45-96000-256: no such directory", r.stderr)
        self.assertEqual(sorted(os.listdir(os.path.join(self.tree, "records", "x86-64"))), ["fedora44-48000-512", "fedora44-96000-256"])
        self.assertEqual(git(self.tree, "status", "--short"), "")

    def test_an_unknown_class_stops_it(self):
        r = self.run_script("pi4", self.out, "fedora45-48000-512")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("replace-sets: pi4 is no class of packaging/arch-classes", r.stderr)
        self.assertEqual(git(self.tree, "status", "--short"), "")


if __name__ == "__main__":
    unittest.main()
