#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""tools/sets.py: the one package, plugin-qualification-records, per architecture, held to packaging/arch-classes,
packaging/release-arches, debian/, the spec and records/; debian/rules' install and substvars steps per architecture;
the workflows' outputs; and the install-and-sync proof (tools/prove-set.sh), installed once and run once per set.

    python3 -m unittest tools/test_sets.py

The tree is a copy of packaging/, debian/ and tools/sets.py with records/ made of small sets, starting from the rpi5
set alone and no x86-64 set, whatever sets this branch carries. debian/rules runs under make with a stand-in
dh_gencontrol; the proof runs against a PROVE_ROOT with stand-ins for apt-get, dpkg-query, dnf, rpm and
plugin-qualify-sync on PATH that log what they were asked.
"""
import contextlib
import filecmp
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("sets", os.path.join(HERE, "sets.py"))
sets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sets)

PKG = "plugin-qualification-records"
SPEC = os.path.join("packaging", f"{PKG}.spec")
CELLS = ("fedora44-48000-512", "fedora44-96000-256")
with open(os.path.join(ROOT, "debian", "changelog"), encoding="utf-8") as _f:
    VERSION = re.match(r"^\S+ \(([^)]*)\)", _f.read()).group(1)
# the sync stand-in takes plugins from the set the settings file's grid names (fedora44-<rate>-<quantum>), or from
# zynthian-vangelis with no grid; WRONG_SET makes it take one from another set too, BAD_GRID makes that cell's differ
STUB = """#!/bin/bash
echo "$(basename "$0") $*" >> "$STUB_LOG"
case $(basename "$0") in
    dpkg-query|rpm) echo 0.20.1 ;;
    plugin-qualify-sync)
        conf=$PROVE_ROOT/etc/omx/qualify.conf
        cat "$conf" >> "$STUB_LOG"
        grid=$(sed -n 's/^grid //p' "$conf")
        if [ -n "$grid" ]; then set_=fedora44-${grid%/*}-${grid#*/}; else set_=zynthian-vangelis; fi
        if [ "$grid" = "${BAD_GRID:-none}" ]; then
            echo "plugin-qualify-sync: distributed: urn:a: binary differs"
        else
            echo "plugin-qualify-sync: distributed: urn:a: applied ($set_)"
            [ -z "${WRONG_SET:-}" ] || echo "plugin-qualify-sync: distributed: urn:b: applied ($WRONG_SET)"
        fi ;;
esac
"""


class Tree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "tree")
        for d in ("packaging", "debian"):
            shutil.copytree(os.path.join(ROOT, d), os.path.join(self.root, d))
        os.makedirs(self.path("tools"))
        shutil.copy2(os.path.join(HERE, "sets.py"), self.path("tools", "sets.py"))
        self.add_set("rpi5", "zynthian-vangelis")
        self.respec()

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, *p):
        return os.path.join(self.root, *p)

    def add_set(self, cls, name, under=None):
        d = os.path.join(under or self.root, *(["usr", "share", "omx", "qualification"] if under else ["records"]), cls, name)
        os.makedirs(d)
        with open(os.path.join(d, "provenance.json"), "w") as f:
            json.dump({"set": name, "packages": {"omx-plugins-clap": "0.18.0-1.fc44"}}, f)
        with open(os.path.join(d, "a.qualification.json"), "w") as f:
            f.write(json.dumps({"set": name}))

    def with_two_cells(self):
        for s in CELLS:
            self.add_set("x86-64", s)
        self.respec()

    def respec(self):
        self.assertEqual(sets.main(["spec"], root=self.root), 0)

    def edit(self, rel, old, new):
        p = self.path(*rel.split("/"))
        with open(p) as f:
            text = f.read()
        self.assertIn(old, text)
        with open(p, "w") as f:
            f.write(text.replace(old, new))

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = sets.main(list(argv), root=self.root)
        return rc, out.getvalue()

    def problems(self):
        return "\n".join(sets.problems(self.root))


class Check(Tree):
    def test_this_tree_passes(self):
        self.assertEqual(sets.problems(ROOT), [])
        self.assertEqual(sets.problems(self.root), [])
        self.with_two_cells()
        self.assertEqual(sets.problems(self.root), [])

    def test_one_binary_name_on_every_format(self):
        self.assertEqual(self.run_main("names", "deb"), (0, PKG + "\n"))
        self.assertEqual(self.run_main("names", "rpm"), (0, PKG + "\n"))

    def test_each_architecture_lists_its_classes_sets(self):
        self.with_two_cells()
        self.assertEqual(self.run_main("list", "deb", "arm64"), (0, "rpi5 zynthian-vangelis -\n"))
        self.assertEqual(self.run_main("list", "rpm", "x86_64")[1].splitlines(),
                         ["x86-64 fedora44-48000-512 48000/512", "x86-64 fedora44-96000-256 96000/256"])
        self.assertEqual(self.run_main("list", "deb", "amd64")[1], self.run_main("list", "rpm", "x86_64")[1])

    def test_a_class_with_no_architecture_is_refused(self):
        self.add_set("pi4", "bullseye")
        self.assertIn("records/pi4/: class pi4 has no architecture in packaging/arch-classes", self.problems())
        self.assertEqual(self.run_main("check")[0], 1)

    def test_a_class_on_two_architectures_is_refused(self):
        with open(self.path("packaging", "arch-classes"), "a") as f:
            f.write("riscv64 riscv64 rpi5 0.20.0 0.21\n")
        self.assertIn("class rpi5 is on two lines", self.problems())

    def test_one_version_for_both_formats(self):
        self.edit(SPEC, "\nVersion: ", "\nVersion: 1")
        self.assertIn("a tag must equal both", self.problems())
        self.edit(SPEC, "\nVersion: 1", "\nVersion: ")
        self.assertEqual(sets.problems(self.root), [])
        self.edit("debian/changelog", f"({VERSION})", "(2026010101)")
        self.assertIn(f"debian/changelog is 2026010101 but the spec is {VERSION}", self.problems())

    def test_the_spec_block_follows_records_and_arch_classes(self):
        for s in CELLS:
            self.add_set("x86-64", s)
        self.assertIn("the per-architecture block is not what tools/sets.py spec writes", self.problems())
        self.respec()
        self.assertEqual(sets.problems(self.root), [])
        self.edit("packaging/arch-classes", "0.20.1 ", "0.20.2 ")
        self.assertIn("the per-architecture block is not what tools/sets.py spec writes", self.problems())

    def test_debian_control_is_one_package_for_the_mapped_architectures(self):
        self.edit("debian/control", "Architecture: amd64 arm64", "Architecture: all")
        self.assertIn("Architecture is 'all', not the Debian architectures of packaging/arch-classes: amd64 arm64", self.problems())
        self.edit("debian/control", "Architecture: all", "Architecture: amd64 arm64")
        self.edit("debian/control", "Breaks: ${records:Breaks}", "Breaks: foo")
        self.assertIn("Breaks does not carry ${records:Breaks}", self.problems())

    def test_an_old_per_set_file_is_refused(self):
        with open(self.path("debian", "plugin-db-qualification-rpi5-zynthian-vangelis.install"), "w") as f:
            f.write("records/rpi5/zynthian-vangelis usr/share/omx/qualification/rpi5\n")
        self.assertIn("debian/plugin-db-qualification-rpi5-zynthian-vangelis.install: a file of no package", self.problems())

    def test_a_released_architecture_needs_sets(self):
        self.edit("packaging/release-arches", "\nrpm\n", "\nrpm x86_64\n")
        self.assertIn("release-arches: class x86-64 of rpm architecture x86_64 has no set under records/x86-64/", self.problems())
        self.with_two_cells()
        self.assertEqual(sets.problems(self.root), [])
        self.edit("packaging/release-arches", "\nrpm x86_64\n", "\nrpm aarch64\n")
        self.assertIn("rpm aarch64 is not an ExclusiveArch", self.problems())

    def test_github_output(self):
        out = os.path.join(self.tmp.name, "out")
        os.environ["GITHUB_OUTPUT"] = out
        try:
            self.assertEqual(self.run_main("github-output")[0], 0)
            with open(out) as f:
                self.assertEqual(f.read().splitlines(), [
                    'deb-arches=["arm64"]', "deb-run=true", f"deb-names={PKG}", "deb-prove=true",
                    "rpm-arches=[]", "rpm-run=false", f"rpm-names={PKG}", "rpm-prove=false"])
            os.remove(out)
            # the later version: the amd64 deb and the x86_64 rpm join
            self.with_two_cells()
            self.edit("packaging/release-arches", "deb arm64\nrpm\n", "deb arm64 amd64\nrpm x86_64\n")
            self.assertEqual(sets.problems(self.root), [])
            self.run_main("github-output")
            with open(out) as f:
                written = f.read().splitlines()
            self.assertIn('deb-arches=["arm64", "amd64"]', written)
            self.assertIn('rpm-arches=["x86_64"]', written)
            self.assertIn("rpm-run=true", written)
            self.assertIn("rpm-prove=true", written)
        finally:
            del os.environ["GITHUB_OUTPUT"]


class Substvars(Tree):
    def vars(self, arch):
        rc, out = self.run_main("substvars", arch)
        self.assertEqual(rc, 0)
        return dict(line.split("=", 1) for line in out.splitlines())

    def names(self, field):
        return [re.match(r"(\S+) \(", n).group(1) for n in field.split(", ")]

    def test_arm64_takes_plugin_qualify_0_20_0_and_folds_the_rpi5_names(self):
        self.with_two_cells()
        v = self.vars("arm64")
        self.assertEqual(v["qualify:Depends"], "plugin-qualify (>= 0.20.0~), plugin-qualify (<< 0.21~)")
        self.assertEqual(v["records:Provides"],
                         f"omx-qualification-rpi5-zynthian-vangelis (= {VERSION}), plugin-db-qualification-rpi5-zynthian-vangelis (= {VERSION})")
        for field in ("records:Replaces", "records:Breaks"):
            self.assertEqual(v[field], f"omx-qualification-rpi5-zynthian-vangelis (<< {VERSION}), "
                                       f"plugin-db-qualification-rpi5-zynthian-vangelis (<< {VERSION})")

    def test_amd64_takes_plugin_qualify_0_20_1_and_folds_every_cell(self):
        self.with_two_cells()
        v = self.vars("amd64")
        self.assertEqual(v["qualify:Depends"], "plugin-qualify (>= 0.20.1~), plugin-qualify (<< 0.21~)")
        want = ["omx-qualification-rpi5-zynthian-vangelis", "omx-qualification-x86-64-fedora44",
                "plugin-db-qualification-rpi5-zynthian-vangelis", "plugin-db-qualification-x86-64-fedora44",
                "plugin-db-qualification-x86-64-fedora44-48000-512", "plugin-db-qualification-x86-64-fedora44-96000-256"]
        for field, op in (("records:Provides", "="), ("records:Replaces", "<<"), ("records:Breaks", "<<")):
            self.assertEqual(self.names(v[field]), want)
            self.assertTrue(all(n.endswith(f"({op} {VERSION})") for n in v[field].split(", ")), v[field])

    def test_the_rpm_folds_its_classes_names(self):
        self.with_two_cells()
        block = sets.spec_block(self.root)
        self.assertIn("%ifarch x86_64\nRequires: (plugin-qualify >= 0.20.1 with plugin-qualify < 0.21)\n", block)
        for n in ("plugin-db-qualification-x86-64-fedora44", "omx-qualification-x86-64-fedora44",
                  "plugin-db-qualification-x86-64-fedora44-48000-512", "plugin-db-qualification-x86-64-fedora44-96000-256"):
            self.assertIn(f"Provides: {n} = %{{version}}-%{{release}}\nObsoletes: {n} < %{{version}}-%{{release}}\n", block)
        self.assertNotIn("rpi5", block)
        if shutil.which("rpmspec"):
            def q(*what):
                return subprocess.run(["rpmspec", "-q", "--target", "x86_64", *what, self.path(SPEC)],
                                      capture_output=True, text=True, check=True).stdout
            self.assertIn("(plugin-qualify >= 0.20.1 with plugin-qualify < 0.21)", q("--requires"))
            self.assertIn("plugin-db-qualification-x86-64-fedora44-48000-512 <", q("--obsoletes"))
            self.assertEqual(q("--qf", "%{name}\n"), PKG + "\n")

    def test_an_architecture_with_no_class_or_no_set_is_refused(self):
        self.assertEqual(self.run_main("substvars", "i386")[0], 1)
        # amd64's class has no set until the x86-64 sets are in the tree
        self.assertEqual(self.run_main("substvars", "amd64")[0], 1)


@unittest.skipUnless(shutil.which("make"), "make is not installed")
class Rules(Tree):
    """debian/rules' own steps, as dpkg-buildpackage runs them for one architecture."""

    def make(self, target, arch):
        bin_ = os.path.join(self.tmp.name, "bin")
        os.makedirs(bin_, exist_ok=True)
        with open(os.path.join(bin_, "dh_gencontrol"), "w") as f:
            f.write(f"#!/bin/sh\ncp debian/{PKG}.substvars \"$GENCONTROL_SAW\"\n")
        os.chmod(os.path.join(bin_, "dh_gencontrol"), 0o755)
        saw = os.path.join(self.tmp.name, "substvars")
        env = dict(os.environ, PATH=bin_ + os.pathsep + os.environ["PATH"], GENCONTROL_SAW=saw)
        r = subprocess.run(["make", "-f", "debian/rules", target, f"DEB_HOST_ARCH={arch}"], cwd=self.root,
                           capture_output=True, text=True, env=env)
        return r, saw

    def installed(self):
        base = self.path("debian", PKG, "usr", "share", "omx", "qualification")
        return sorted(os.path.relpath(os.path.join(d, f), base) for d, _, fs in os.walk(base) for f in fs)

    def test_arm64_installs_only_the_rpi5_sets(self):
        self.with_two_cells()
        r, _ = self.make("override_dh_install", "arm64")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.installed(), ["rpi5/zynthian-vangelis/a.qualification.json", "rpi5/zynthian-vangelis/provenance.json"])
        base = self.path("debian", PKG, "usr", "share", "omx", "qualification")
        self.assertTrue(filecmp.cmp(os.path.join(base, "rpi5", "zynthian-vangelis", "provenance.json"),
                                    self.path("records", "rpi5", "zynthian-vangelis", "provenance.json"), shallow=False))

    def test_amd64_installs_only_the_x86_64_sets(self):
        self.with_two_cells()
        r, _ = self.make("override_dh_install", "amd64")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.installed(), [f"x86-64/{s}/{f}" for s in CELLS for f in ("a.qualification.json", "provenance.json")])

    def test_gencontrol_gets_the_architectures_substvars(self):
        self.with_two_cells()
        for arch, low in (("arm64", "0.20.0"), ("amd64", "0.20.1")):
            if os.path.exists(self.path("debian", f"{PKG}.substvars")):
                os.remove(self.path("debian", f"{PKG}.substvars"))
            r, saw = self.make("override_dh_gencontrol", arch)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(saw) as f:
                text = f.read()
            self.assertIn(f"qualify:Depends=plugin-qualify (>= {low}~), plugin-qualify (<< 0.21~)\n", text)
            self.assertEqual("fedora44-48000-512" in text, arch == "amd64")

    def test_an_architecture_with_no_class_or_no_set_fails_the_build(self):
        r, _ = self.make("override_dh_install", "i386")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("deb architecture i386 has no class", r.stderr)
        r, _ = self.make("override_dh_install", "amd64")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("class x86-64 of deb architecture amd64 has no set under records/x86-64/", r.stderr)


class Prove(Tree):
    def prove(self, kind, arch, extra_classes=(), **env_extra):
        bin_ = os.path.join(self.tmp.name, "bin")
        os.makedirs(bin_, exist_ok=True)
        for tool in ("apt-get", "dpkg", "dpkg-query", "dnf", "rpm", "plugin-qualify-sync"):
            with open(os.path.join(bin_, tool), "w") as f:
                f.write(STUB)
            os.chmod(os.path.join(bin_, tool), 0o755)
        fake = os.path.join(self.tmp.name, "root")
        # what the package installs: the sets of its architecture's classes
        for cls, s in sets.carried(self.root, kind, arch):
            self.add_set(cls, s, under=fake)
        for cls, s in extra_classes:
            self.add_set(cls, s, under=fake)
        os.makedirs(self.path("pkgs", "trixie"), exist_ok=True)
        log = os.path.join(self.tmp.name, "log")
        open(log, "w").close()
        env = {"PATH": bin_ + os.pathsep + os.environ["PATH"], "PROVE_ROOT": fake, "STUB_LOG": log, "PROVE_ARCH": arch,
               **env_extra}
        saved = dict(os.environ)
        os.environ.update(env)
        try:
            rc, out = self.run_main("prove", kind, "pkgs")
        finally:
            os.environ.clear()
            os.environ.update(saved)
        with open(log) as f:
            return rc, out, f.read()

    def steps(self, log):
        return [l for l in log.splitlines() if re.match(r"(apt-get|dnf|plugin-qualify-sync|grid|host_class)", l)]

    def test_the_rpm_is_installed_once_and_every_set_synced_in_turn(self):
        self.with_two_cells()
        rc, out, log = self.prove("rpm", "x86_64")
        self.assertEqual(rc, 0, out + log)
        self.assertIn("2 of 2 sets proven", out)
        self.assertEqual(self.steps(log), [
            f"dnf install -y --setopt=install_weak_deps=False ./pkgs/{PKG}-[0-9]*.x86_64.rpm",
            "dnf install -y --setopt=install_weak_deps=False omx-plugins-clap-0.18.0 omx-plugins-lv2-0.18.0",
            "plugin-qualify-sync --system", "host_class x86-64", "grid 48000/512",
            "dnf remove -y omx-plugins-clap omx-plugins-lv2",
            "dnf install -y --setopt=install_weak_deps=False omx-plugins-clap-0.18.0 omx-plugins-lv2-0.18.0",
            "plugin-qualify-sync --system", "host_class x86-64", "grid 96000/256",
            "dnf remove -y omx-plugins-clap omx-plugins-lv2",
            f"dnf remove -y {PKG}"])

    def test_a_set_the_sync_does_not_take_fails_the_proof(self):
        self.with_two_cells()
        rc, out, log = self.prove("rpm", "x86_64", BAD_GRID="96000/256")
        self.assertEqual(rc, 1)
        self.assertIn("1 of 2 sets proven; failed: fedora44-96000-256", out)

    def test_plugins_taken_from_another_set_fail_the_proof(self):
        self.with_two_cells()
        rc, out, log = self.prove("rpm", "x86_64", WRONG_SET="fedora44-48000-512")
        self.assertEqual(rc, 1)
        self.assertIn("1 of 2 sets proven; failed: fedora44-96000-256", out)

    def test_the_arm64_deb_is_proven_with_no_grid(self):
        self.with_two_cells()
        rc, out, log = self.prove("deb", "arm64")
        self.assertEqual(rc, 0, out + log)
        self.assertIn("1 of 1 sets proven", out)
        self.assertEqual(self.steps(log), [
            f"apt-get install -y --no-install-recommends ./pkgs/trixie/{PKG}_*_arm64.deb lv2vocoder",
            "plugin-qualify-sync --system", "host_class rpi5",
            f"apt-get remove -y {PKG}"])
        self.assertIn("host_class rpi5\nlv2_extra\nhostd_port 0\n", log)

    def test_a_package_that_installs_another_class_fails_the_proof(self):
        self.with_two_cells()
        rc, out, log = self.prove("deb", "arm64", extra_classes=[("x86-64", "fedora44-48000-512")])
        self.assertEqual(rc, 1)
        self.assertNotIn("plugin-qualify-sync", log)
        self.assertIn(f"apt-get remove -y {PKG}", log)

    def test_no_set_is_not_a_proof(self):
        os.environ["PROVE_ARCH"] = "x86_64"
        try:
            self.assertEqual(self.run_main("prove", "rpm", "pkgs")[0], 1)
        finally:
            del os.environ["PROVE_ARCH"]


if __name__ == "__main__":
    unittest.main()
