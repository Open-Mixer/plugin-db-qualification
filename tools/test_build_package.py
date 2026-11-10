#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""tools/build-package.sh puts a run of two cells into records/ as two sets, and the one package follows them.

    python3 -m unittest tools/test_build_package.py

The script runs on a copy of this tree (tools, packaging, debian) with records/ holding the rpi5 set alone and no
x86-64 set, whatever sets this branch carries, and the stand-in tools/testdata/plugin-qualify-records-package first on
PATH: it writes a real .deb of what it was given, so the script's own unpacking (ar, tar) is what is tested. The run
is tools/testdata/run, the layout of tools/fedora44/measure.sh: b48000-512/qualification and
b96000-256/qualification, one record and one unmeasured plugin each.
"""
import filecmp
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# the version the spec carries today: a build at it changes nothing in debian/ the test does not expect
with open(os.path.join(ROOT, "packaging", "plugin-qualification-records.spec")) as _f:
    VERSION = next(l.split()[1] for l in _f if l.startswith("Version:"))
DATA = os.path.join(HERE, "testdata")
RUN = os.path.join(DATA, "run")
CELLS = {"48000-512": "48000/512", "96000-256": "96000/256"}
SPEC = ("packaging", "plugin-qualification-records.spec")

spec = importlib.util.spec_from_file_location("check_records", os.path.join(HERE, "check-records.py"))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
spec = importlib.util.spec_from_file_location("sets", os.path.join(HERE, "sets.py"))
sets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sets)


class BuildPackage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tree = os.path.join(self.tmp.name, "tree")
        for d in ("packaging", "debian"):
            shutil.copytree(os.path.join(ROOT, d), os.path.join(self.tree, d))
        os.makedirs(os.path.join(self.tree, "tools"))
        for f in ("build-package.sh", "check-records.py", "sets.py"):
            shutil.copy2(os.path.join(HERE, f), os.path.join(self.tree, "tools", f))
        # another class's set, which no run of these tests may touch
        self.other = os.path.join(self.tree, "records", "rpi5", "zynthian-vangelis")
        os.makedirs(self.other)
        with open(os.path.join(self.other, "provenance.json"), "w") as f:
            f.write("{}\n")
        # the tree as it starts: no x86-64 set and the arm64 deb the only format released, the spec's block written for that
        ra = os.path.join(self.tree, "packaging", "release-arches")
        with open(ra) as f:
            head = [l for l in f if l.startswith("#")]
        with open(ra, "w") as f:
            f.write("".join(head) + "deb arm64\nrpm\n")
        self.assertEqual(sets.main(["spec"], root=self.tree), 0)
        self.debian = self.snapshot("debian")

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, *args, version=VERSION, rc=0):
        env = dict(os.environ, PATH=DATA + os.pathsep + os.environ["PATH"])
        r = subprocess.run(["bash", os.path.join(self.tree, "tools", "build-package.sh"), *args,
                            "--provenance", os.path.join(DATA, "provenance.json"), "--version", version],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
        return r

    def snapshot(self, d):
        """{relative path: bytes} of a directory of the tree"""
        base = os.path.join(self.tree, d)
        out = {}
        for top, _, files in os.walk(base):
            for f in files:
                with open(os.path.join(top, f), "rb") as fh:
                    out[os.path.relpath(os.path.join(top, f), base)] = fh.read()
        return out

    def spec_text(self):
        return self.read(*SPEC)

    def assert_folded_by_the_rpm(self, names):
        text = self.spec_text()
        for n in names:
            self.assertIn(f"Provides: {n} = %{{version}}-%{{release}}\nObsoletes: {n} < %{{version}}-%{{release}}\n", text)

    def read(self, *path):
        with open(os.path.join(self.tree, *path), encoding="utf-8") as f:
            return f.read()

    def assert_cell_set(self, cls, name, cell, base):
        d = os.path.join(self.tree, "records", cls, name)
        prov = json.loads(self.read("records", cls, name, "provenance.json"))
        self.assertEqual(prov["set"], name)
        self.assertEqual(prov["hostClass"], cls)
        self.assertEqual(prov["package"], {"name": f"plugin-db-qualification-{cls}-{name}", "version": VERSION})
        self.assertEqual(prov["grid"], cell)
        self.assertEqual(prov["hostProfile"], "openmixer-console")
        # the records are the device's bytes, the unmeasured plugin stays out
        q = os.path.join(RUN, base, "qualification")
        shipped = sorted(f for f in os.listdir(d) if f != "provenance.json")
        self.assertEqual(shipped, sorted(f for f in os.listdir(q) if not f.endswith(".unmeasured.json")))
        for f in shipped:
            self.assertTrue(filecmp.cmp(os.path.join(d, f), os.path.join(q, f), shallow=False), f)
        problems, records = check.check_set(d)
        self.assertEqual((problems, records), ([], 1))

    def test_a_run_gives_one_set_per_cell_and_the_package_follows(self):
        r = self.build("--from-run", RUN, "--set", "fedora44", "--host-class", "x86-64")
        self.assertIn("2 sets from", r.stdout)
        self.assertEqual(sorted(os.listdir(os.path.join(self.tree, "records", "x86-64"))),
                         ["fedora44-48000-512", "fedora44-96000-256"])
        for suffix, cell in CELLS.items():
            self.assert_cell_set("x86-64", f"fedora44-{suffix}", cell, f"b{suffix}")
        self.assertIn(f"\nVersion: {VERSION}\n", self.spec_text())
        # the one package takes over each set's older name; nothing in debian/ is per set
        self.assert_folded_by_the_rpm(["plugin-db-qualification-x86-64-fedora44", "omx-qualification-x86-64-fedora44",
                                       "plugin-db-qualification-x86-64-fedora44-48000-512",
                                       "plugin-db-qualification-x86-64-fedora44-96000-256"])
        self.assertEqual(self.snapshot("debian"), self.debian)
        self.assertEqual(os.listdir(self.other), ["provenance.json"])
        self.assertEqual(sets.problems(self.tree), [])
        if shutil.which("rpmspec"):
            names = subprocess.run(["rpmspec", "-q", "--target", "x86_64", "--qf", "%{name}\n", os.path.join(self.tree, *SPEC)],
                                   capture_output=True, text=True, check=True).stdout.split()
            self.assertEqual(names, ["plugin-qualification-records"])

    def test_an_rpi5_run_adds_sets_and_no_packaging(self):
        spec_before = self.spec_text()
        self.build("--from-run", RUN, "--set", "zynthian-vangelis", "--host-class", "rpi5")
        self.assertEqual(sorted(os.listdir(os.path.join(self.tree, "records", "rpi5"))),
                         ["zynthian-vangelis", "zynthian-vangelis-48000-512", "zynthian-vangelis-96000-256"])
        for suffix, cell in CELLS.items():
            self.assert_cell_set("rpi5", f"zynthian-vangelis-{suffix}", cell, f"b{suffix}")
        # no stanza, no install file, no spec list: the arm64 package carries records/rpi5/ whole
        self.assertEqual(self.snapshot("debian"), self.debian)
        self.assertEqual(self.spec_text(), spec_before)
        self.assertEqual(os.listdir(self.other), ["provenance.json"])
        self.assertEqual(sets.problems(self.tree), [])
        out = subprocess.run(["python3", os.path.join(self.tree, "tools", "sets.py"), "substvars", "arm64"],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn(f"plugin-db-qualification-rpi5-zynthian-vangelis-48000-512 (= {VERSION})", out)

    def test_the_version_goes_where_it_lives(self):
        r = self.build("--from-run", RUN, "--set", "fedora44", "--host-class", "x86-64", version="2026120101")
        self.assertIn("\nVersion: 2026120101\n", self.spec_text())
        self.assertTrue(self.read("debian", "changelog").startswith("plugin-db-qualification (2026120101) unstable"))
        self.assertIn("debian/changelog: the top entry now names 2026120101", r.stderr)
        self.assertEqual(sets.problems(self.tree), [])

    def test_a_class_with_no_architecture_is_refused(self):
        r = self.build("--from-run", RUN, "--set", "bullseye", "--host-class", "pi4", rc=2)
        self.assertIn("class pi4 has no architecture in packaging/arch-classes", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tree, "records", "pi4")))

    def test_one_cell_with_from_and_cell_keeps_the_other_cells(self):
        self.build("--from", os.path.join(RUN, "b48000-512", "qualification"), "--cell", "48000/512",
                   "--set", "fedora44", "--host-class", "x86-64")
        self.build("--from", os.path.join(RUN, "b96000-256", "qualification"), "--cell", "96000/256",
                   "--set", "fedora44", "--host-class", "x86-64")
        for suffix, cell in CELLS.items():
            self.assert_cell_set("x86-64", f"fedora44-{suffix}", cell, f"b{suffix}")
        # building one again replaces it alone
        self.build("--from", os.path.join(RUN, "b48000-512", "qualification"), "--cell", "48000/512",
                   "--set", "fedora44", "--host-class", "x86-64")
        self.assertEqual(sorted(os.listdir(os.path.join(self.tree, "records", "x86-64"))),
                         ["fedora44-48000-512", "fedora44-96000-256"])
        self.assertEqual(sets.problems(self.tree), [])

    def test_a_single_from_still_names_the_set_as_given(self):
        self.build("--from", os.path.join(RUN, "b48000-512", "qualification"), "--set", "fedora44", "--host-class", "x86-64")
        prov = json.loads(self.read("records", "x86-64", "fedora44", "provenance.json"))
        self.assertEqual((prov["set"], prov["grid"]), ("fedora44", "48000/512 96000/256"))
        self.assertEqual(sets.problems(self.tree), [])

    def test_a_cell_that_is_not_the_records_is_refused_by_the_check(self):
        # the 96000/256 records packaged as the 48000/512 set: the package builds, check-records refuses it
        self.build("--from", os.path.join(RUN, "b96000-256", "qualification"), "--cell", "48000/512",
                   "--set", "fedora44", "--host-class", "x86-64")
        problems, _ = check.check_set(os.path.join(self.tree, "records", "x86-64", "fedora44-48000-512"))
        self.assertTrue(any("measured 96000/256, not 48000/512" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
