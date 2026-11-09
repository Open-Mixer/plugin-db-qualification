#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""tools/build-package.sh packages a run of two cells as two sets, each its own package.

    python3 -m unittest tools/test_build_package.py

The script runs on a copy of this tree (tools, packaging, debian) with the stand-in
tools/testdata/plugin-qualify-records-package first on PATH: it writes a real .deb of what it was given, so the
script's own unpacking (ar, tar) is what is tested. The run is tools/testdata/run, the layout of
tools/fedora44/measure.sh: b48000-512/qualification and b96000-256/qualification, one record and one unmeasured
plugin each.
"""
import filecmp
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(HERE, "testdata")
RUN = os.path.join(DATA, "run")
CELLS = {"48000-512": "48000/512", "96000-256": "96000/256"}

spec = importlib.util.spec_from_file_location("check_records", os.path.join(HERE, "check-records.py"))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)



def start_empty(tree):
    """the spec as the tests start from it: no x86-64 set listed, whatever sets this branch carries"""
    p = os.path.join(tree, "packaging", "plugin-db-qualification.spec")
    with open(p, encoding="utf-8") as f:
        s = f.read()
    with open(p, "w", encoding="utf-8") as f:
        f.write(re.sub(r"^%global sets .*$", "%global sets %{nil}", s, count=1, flags=re.M))

class BuildPackage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tree = os.path.join(self.tmp.name, "tree")
        for d in ("packaging", "debian"):
            shutil.copytree(os.path.join(ROOT, d), os.path.join(self.tree, d))
        start_empty(self.tree)
        os.makedirs(os.path.join(self.tree, "tools"))
        for f in ("build-package.sh", "check-records.py"):
            shutil.copy2(os.path.join(HERE, f), os.path.join(self.tree, "tools", f))
        # another class's set, which no run of these tests may touch
        self.other = os.path.join(self.tree, "records", "rpi5", "zynthian-vangelis")
        os.makedirs(self.other)
        with open(os.path.join(self.other, "provenance.json"), "w") as f:
            f.write("{}\n")

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, *args):
        env = dict(os.environ, PATH=DATA + os.pathsep + os.environ["PATH"])
        r = subprocess.run(["bash", os.path.join(self.tree, "tools", "build-package.sh"), *args,
                            "--provenance", os.path.join(DATA, "provenance.json"), "--version", "2026110901"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def read(self, *path):
        with open(os.path.join(self.tree, *path), encoding="utf-8") as f:
            return f.read()

    def spec_sets(self):
        return re.search(r"^%global sets (.*)$", self.read("packaging", "plugin-db-qualification.spec"), re.M).group(1).replace("%{nil}", "").split()

    def assert_cell_set(self, cls, name, cell, base):
        d = os.path.join(self.tree, "records", cls, name)
        prov = json.loads(self.read("records", cls, name, "provenance.json"))
        self.assertEqual(prov["set"], name)
        self.assertEqual(prov["hostClass"], cls)
        self.assertEqual(prov["package"], {"name": f"plugin-db-qualification-{cls}-{name}", "version": "2026110901"})
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

    def test_a_run_gives_one_rpm_set_per_cell(self):
        control = self.read("debian", "control")
        r = self.build("--from-run", RUN, "--set", "fedora44", "--host-class", "x86-64")
        self.assertIn("2 sets from", r.stdout)
        self.assertEqual(sorted(os.listdir(os.path.join(self.tree, "records", "x86-64"))),
                         ["fedora44-48000-512", "fedora44-96000-256"])
        for suffix, cell in CELLS.items():
            self.assert_cell_set("x86-64", f"fedora44-{suffix}", cell, f"b{suffix}")
        self.assertEqual(self.spec_sets(), ["fedora44-48000-512", "fedora44-96000-256"])
        self.assertIn("\nVersion: 2026110901\n", self.read("packaging", "plugin-db-qualification.spec"))
        # an RPM set leaves debian/ and the other class alone
        self.assertEqual(self.read("debian", "control"), control)
        self.assertEqual(os.listdir(self.other), ["provenance.json"])
        if shutil.which("rpmspec"):
            names = subprocess.run(["rpmspec", "-q", "--qf", "%{name}\n", os.path.join(self.tree, "packaging", "plugin-db-qualification.spec")],
                                   capture_output=True, text=True, check=True).stdout.split()
            self.assertEqual(names, ["plugin-db-qualification", "plugin-db-qualification-x86-64-fedora44-48000-512",
                                     "plugin-db-qualification-x86-64-fedora44-96000-256"])

    def test_a_run_gives_one_debian_package_per_cell(self):
        self.build("--from-run", RUN, "--set", "zynthian-vangelis", "--host-class", "rpi5")
        sets = sorted(os.listdir(os.path.join(self.tree, "records", "rpi5")))
        self.assertEqual(sets, ["zynthian-vangelis", "zynthian-vangelis-48000-512", "zynthian-vangelis-96000-256"])
        for suffix, cell in CELLS.items():
            self.assert_cell_set("rpi5", f"zynthian-vangelis-{suffix}", cell, f"b{suffix}")
        control = self.read("debian", "control")
        stanzas = control.strip().split("\n\n")
        self.assertTrue(stanzas[0].startswith("Source: plugin-db-qualification\n"))
        packages = [re.search(r"^Package: (.*)$", s, re.M).group(1) for s in stanzas[1:]]
        self.assertEqual(packages, ["plugin-db-qualification-rpi5-zynthian-vangelis",
                                    "plugin-db-qualification-rpi5-zynthian-vangelis-48000-512",
                                    "plugin-db-qualification-rpi5-zynthian-vangelis-96000-256"])
        # the set already there keeps its stanza; a new one takes Depends and Description from the tool's control
        self.assertEqual(stanzas[1], open(os.path.join(ROOT, "debian", "control")).read().strip().split("\n\n")[1])
        self.assertIn("Depends: ${misc:Depends}, plugin-qualify (>= 0.19.0~), plugin-qualify (<< 0.20~)\n", stanzas[2])
        self.assertIn("Description: plugin-db qualification layer: zynthian-vangelis-48000-512 set for rpi5\n", stanzas[2])
        for suffix in CELLS:
            pkg = f"plugin-db-qualification-rpi5-zynthian-vangelis-{suffix}"
            self.assertEqual(self.read("debian", f"{pkg}.install"),
                             f"records/rpi5/zynthian-vangelis-{suffix} usr/share/omx/qualification/rpi5\n")
            self.assertTrue(os.path.exists(os.path.join(self.tree, "debian", f"{pkg}.lintian-overrides")))
        self.assertFalse(os.path.exists(os.path.join(self.tree, "debian", "install")))
        self.assertTrue(self.read("debian", "changelog").startswith("plugin-db-qualification (2026110901) unstable"))
        self.assertEqual(self.spec_sets(), [])
        # the set already there is untouched
        self.assertEqual(os.listdir(self.other), ["provenance.json"])

    def test_one_cell_with_from_and_cell_keeps_the_other_cells(self):
        self.build("--from", os.path.join(RUN, "b48000-512", "qualification"), "--cell", "48000/512",
                   "--set", "fedora44", "--host-class", "x86-64")
        self.build("--from", os.path.join(RUN, "b96000-256", "qualification"), "--cell", "96000/256",
                   "--set", "fedora44", "--host-class", "x86-64")
        for suffix, cell in CELLS.items():
            self.assert_cell_set("x86-64", f"fedora44-{suffix}", cell, f"b{suffix}")
        self.assertEqual(self.spec_sets(), ["fedora44-48000-512", "fedora44-96000-256"])
        # building one again replaces it alone
        self.build("--from", os.path.join(RUN, "b48000-512", "qualification"), "--cell", "48000/512",
                   "--set", "fedora44", "--host-class", "x86-64")
        self.assertEqual(self.spec_sets(), ["fedora44-48000-512", "fedora44-96000-256"])
        self.assertEqual(sorted(os.listdir(os.path.join(self.tree, "records", "x86-64"))),
                         ["fedora44-48000-512", "fedora44-96000-256"])

    def test_a_single_from_still_names_the_set_as_given(self):
        self.build("--from", os.path.join(RUN, "b48000-512", "qualification"), "--set", "fedora44", "--host-class", "x86-64")
        prov = json.loads(self.read("records", "x86-64", "fedora44", "provenance.json"))
        self.assertEqual((prov["set"], prov["grid"]), ("fedora44", "48000/512 96000/256"))
        self.assertEqual(self.spec_sets(), ["fedora44"])

    def test_a_cell_that_is_not_the_records_is_refused_by_the_check(self):
        # the 96000/256 records packaged as the 48000/512 set: the package builds, check-records refuses it
        self.build("--from", os.path.join(RUN, "b96000-256", "qualification"), "--cell", "48000/512",
                   "--set", "fedora44", "--host-class", "x86-64")
        problems, _ = check.check_set(os.path.join(self.tree, "records", "x86-64", "fedora44-48000-512"))
        self.assertTrue(any("measured 96000/256, not 48000/512" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
