#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""tools/sets.py: the sets the spec and debian/ build agree with records/, the workflows' lists are theirs, and the
install-and-sync proof (tools/prove-set.sh) runs once per set.

    python3 -m unittest tools/test_sets.py

The tree is a copy of packaging/ and debian/ with records/ made of provenance files; the proof runs against a
PROVE_ROOT with stand-ins for apt-get, dpkg-query, dnf, rpm and plugin-qualify-sync on PATH that log what they were
asked.
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("sets", os.path.join(HERE, "sets.py"))
sets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sets)

CELLS = ("fedora44-48000-512", "fedora44-96000-256")
STUB = """#!/bin/bash
echo "$(basename "$0") $*" >> "$STUB_LOG"
case $(basename "$0") in
    dpkg-query|rpm) echo 0.19.1 ;;
    plugin-qualify-sync)
        cat "$PROVE_ROOT/etc/omx/qualify.conf" >> "$STUB_LOG"
        if grep -qx "grid ${BAD_GRID:-none}" "$PROVE_ROOT/etc/omx/qualify.conf"; then
            echo "plugin-qualify-sync: distributed: urn:a: binary differs"
        else
            echo "plugin-qualify-sync: distributed: urn:a: applied (set)"
        fi ;;
esac
"""


class Sets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "tree")
        for d in ("packaging", "debian"):
            shutil.copytree(os.path.join(ROOT, d), os.path.join(self.root, d))
        self.add_set("rpi5", "zynthian-vangelis")

    def tearDown(self):
        self.tmp.cleanup()

    def add_set(self, cls, name, under=None):
        d = os.path.join(under or self.root, *(["usr", "share", "omx", "qualification"] if under else ["records"]), cls, name)
        os.makedirs(d)
        with open(os.path.join(d, "provenance.json"), "w") as f:
            json.dump({"set": name, "packages": {"omx-plugins-clap": "0.18.0-1.fc44"}}, f)
        with open(os.path.join(d, "a.qualification.json"), "w") as f:
            f.write("{}")

    def path(self, *p):
        return os.path.join(self.root, *p)

    def edit(self, rel, old, new):
        p = self.path(*rel.split("/"))
        with open(p) as f:
            text = f.read()
        self.assertIn(old, text)
        with open(p, "w") as f:
            f.write(text.replace(old, new))

    def with_two_cells(self):
        for s in CELLS:
            self.add_set("x86-64", s)
        self.edit("packaging/plugin-db-qualification.spec", "%global sets %{nil}", "%global sets " + " ".join(CELLS))

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = sets.main(list(argv), root=self.root)
        return rc, out.getvalue()

    def test_this_tree_passes(self):
        self.assertEqual(sets.problems(ROOT), [])
        self.assertEqual(sets.problems(self.root), [])

    def test_two_cells_are_two_rpm_packages(self):
        self.with_two_cells()
        self.assertEqual(sets.problems(self.root), [])
        self.assertEqual(self.run_main("names", "rpm"),
                         (0, "plugin-db-qualification-x86-64-fedora44-48000-512 plugin-db-qualification-x86-64-fedora44-96000-256\n"))
        self.assertEqual(self.run_main("list", "rpm")[1].splitlines(), [
            "plugin-db-qualification-x86-64-fedora44-48000-512 x86-64 fedora44-48000-512 48000/512",
            "plugin-db-qualification-x86-64-fedora44-96000-256 x86-64 fedora44-96000-256 96000/256"])
        self.assertEqual(self.run_main("list", "deb")[1], "plugin-db-qualification-rpi5-zynthian-vangelis rpi5 zynthian-vangelis -\n")

    def test_github_output(self):
        out = os.path.join(self.tmp.name, "out")
        os.environ["GITHUB_OUTPUT"] = out
        try:
            self.assertEqual(self.run_main("github-output")[0], 0)
            with open(out) as f:
                written = f.read()
            self.assertEqual(written, "rpm-set=false\nrpm-names=\ndeb-names=plugin-db-qualification-rpi5-zynthian-vangelis\n")
            os.remove(out)
            self.with_two_cells()
            self.run_main("github-output")
            with open(out) as f:
                written = f.read()
            self.assertEqual(written.splitlines()[:2], [
                "rpm-set=true",
                "rpm-names=plugin-db-qualification-x86-64-fedora44-48000-512 plugin-db-qualification-x86-64-fedora44-96000-256"])
        finally:
            del os.environ["GITHUB_OUTPUT"]

    def test_a_set_no_package_builds_is_refused(self):
        self.add_set("x86-64", "fedora44-48000-512")
        self.assertIn("records/x86-64/fedora44-48000-512: no package builds it", "\n".join(sets.problems(self.root)))
        self.assertEqual(self.run_main("check")[0], 1)

    def test_a_listed_set_the_tree_does_not_hold_is_refused(self):
        self.edit("packaging/plugin-db-qualification.spec", "%global sets %{nil}", "%global sets fedora44-48000-512")
        self.assertIn("spec: plugin-db-qualification-x86-64-fedora44-48000-512 names records/x86-64/fedora44-48000-512, which the tree does not hold",
                      sets.problems(self.root))

    def test_a_debian_package_needs_its_own_install_file(self):
        os.rename(self.path("debian", "plugin-db-qualification-rpi5-zynthian-vangelis.install"), self.path("debian", "install"))
        p = "\n".join(sets.problems(self.root))
        self.assertIn("plugin-db-qualification-rpi5-zynthian-vangelis has no debian/plugin-db-qualification-rpi5-zynthian-vangelis.install", p)
        self.assertIn("debian/install: each binary package has its own", p)

    def test_a_package_is_named_for_its_set(self):
        with open(self.path("debian", "plugin-db-qualification-rpi5-zynthian-vangelis.install"), "w") as f:
            f.write("records/rpi5/other usr/share/omx/qualification/rpi5\n")
        self.add_set("rpi5", "other")
        p = "\n".join(sets.problems(self.root))
        self.assertIn("installs records/rpi5/other, whose package is plugin-db-qualification-rpi5-other", p)
        self.assertIn("records/rpi5/zynthian-vangelis: no package builds it", p)

    def test_one_version_for_both_formats(self):
        self.edit("packaging/plugin-db-qualification.spec", "\nVersion: ", "\nVersion: 1")
        self.assertTrue(any("a tag must equal both" in p for p in sets.problems(self.root)))

    def prove(self, kind, bad_grid=None):
        bin_ = os.path.join(self.tmp.name, "bin")
        os.makedirs(bin_, exist_ok=True)
        for tool in ("apt-get", "dpkg", "dpkg-query", "dnf", "rpm", "plugin-qualify-sync"):
            with open(os.path.join(bin_, tool), "w") as f:
                f.write(STUB)
            os.chmod(os.path.join(bin_, tool), 0o755)
        fake = os.path.join(self.tmp.name, "root")
        for s in CELLS:
            self.add_set("x86-64", s, under=fake)
        self.add_set("rpi5", "zynthian-vangelis", under=fake)
        os.makedirs(self.path("pkgs", "trixie"))
        log = os.path.join(self.tmp.name, "log")
        open(log, "w").close()
        env = {"PATH": bin_ + os.pathsep + os.environ["PATH"], "PROVE_ROOT": fake, "STUB_LOG": log}
        if bad_grid:
            env["BAD_GRID"] = bad_grid
        saved = dict(os.environ)
        os.environ.update(env)
        try:
            rc, out = self.run_main("prove", kind, "pkgs")
        finally:
            os.environ.clear()
            os.environ.update(saved)
        with open(log) as f:
            return rc, out, f.read()

    def test_every_rpm_set_is_installed_synced_and_removed_alone(self):
        self.with_two_cells()
        rc, out, log = self.prove("rpm")
        self.assertEqual(rc, 0, out + log)
        self.assertIn("2 of 2 sets proven", out)
        steps = [l for l in log.splitlines() if re.match(r"(dnf|plugin-qualify-sync|grid|host_class)", l)]
        self.assertEqual(steps, [
            "dnf install -y --setopt=install_weak_deps=False ./pkgs/plugin-db-qualification-x86-64-fedora44-48000-512-[0-9]*.noarch.rpm omx-plugins-clap-0.18.0 omx-plugins-lv2-0.18.0",
            "plugin-qualify-sync --system", "host_class x86-64", "grid 48000/512",
            "dnf remove -y plugin-db-qualification-x86-64-fedora44-48000-512",
            "dnf install -y --setopt=install_weak_deps=False ./pkgs/plugin-db-qualification-x86-64-fedora44-96000-256-[0-9]*.noarch.rpm omx-plugins-clap-0.18.0 omx-plugins-lv2-0.18.0",
            "plugin-qualify-sync --system", "host_class x86-64", "grid 96000/256",
            "dnf remove -y plugin-db-qualification-x86-64-fedora44-96000-256"])

    def test_a_set_the_sync_does_not_take_fails_the_proof(self):
        self.with_two_cells()
        rc, out, log = self.prove("rpm", bad_grid="96000/256")
        self.assertEqual(rc, 1)
        self.assertIn("1 of 2 sets proven; failed: plugin-db-qualification-x86-64-fedora44-96000-256", out)

    def test_the_debian_set_is_proven_with_no_grid(self):
        rc, out, log = self.prove("deb")
        self.assertEqual(rc, 0, out + log)
        self.assertIn("apt-get install -y --no-install-recommends ./pkgs/trixie/plugin-db-qualification-rpi5-zynthian-vangelis_*_all.deb lv2vocoder", log)
        self.assertIn("host_class rpi5\nlv2_extra\nhostd_port 0\n", log)
        self.assertNotIn("grid", log)
        self.assertIn("apt-get remove -y plugin-db-qualification-rpi5-zynthian-vangelis", log)

    def test_no_set_is_not_a_proof(self):
        self.assertEqual(self.prove("rpm")[0], 1)


if __name__ == "__main__":
    unittest.main()
