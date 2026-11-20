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
# the reader's packages beside the records package (this repository's qualification store spec, section 7)
DEB_NAMES = [PKG, "libplugin-qualification-db0", "libplugin-qualification-db-dev", "plugin-qualification-db",
             "plugin-qualification-db-schema", "plugin-qualification-db-write"]
RPM_NAMES = [PKG, "libplugin-qualification-db", "libplugin-qualification-db-devel", "plugin-qualification-db",
             "plugin-qualification-db-schema", "plugin-qualification-db-write"]
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
        if [ -n "$grid" ]; then set_=${STUB_HOST:-fedora44}-${grid%/*}-${grid#*/}; else set_=zynthian-vangelis; fi
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
        # the tree as a class's first release finds it: the arm64 deb alone, so a test adds the x86-64 sets and the
        # amd64/x86_64 formats itself, whatever this repo's own release-arches names today
        with open(self.path("packaging", "release-arches")) as f:
            head = [l for l in f if l.startswith("#")]
        with open(self.path("packaging", "release-arches"), "w") as f:
            f.write("".join(head) + "deb arm64\nrpm\n")
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
        self.assertEqual(self.run_main("names", "deb"), (0, " ".join(DEB_NAMES) + "\n"))
        self.assertEqual(self.run_main("names", "rpm"), (0, " ".join(RPM_NAMES) + "\n"))

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
            f.write("riscv64 riscv64 rpi5 0.20.0\n")
        self.assertIn("class rpi5 is on two lines", self.problems())

    def test_the_packaging_states_floors_only(self):
        self.with_two_cells()
        for text in (sets.spec_block(self.root), sets.substvars(self.root, "amd64"), sets.substvars(self.root, "arm64"),
                     self.read_file(SPEC), self.read_file("debian/control"), self.read_file("packaging/arch-classes")):
            self.assertNotRegex(text, r"plugin-qualify \(?(<|<<) ?\d|with plugin-qualify <")
        for line in sets.arch_classes(self.root):
            self.assertEqual(sorted(line), ["class", "deb", "from", "rpm"])

    def read_file(self, rel):
        with open(self.path(*rel.split("/")), encoding="utf-8") as f:
            return f.read()

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
        # the block holds the floors only: a set added to records/ moves nothing in it
        self.assertEqual(sets.problems(self.root), [])
        self.edit("packaging/arch-classes", "0.20.1\n", "0.20.2\n")
        self.assertIn("the per-architecture block is not what tools/sets.py spec writes", self.problems())

    def test_debian_control_is_one_package_for_the_mapped_architectures(self):
        self.edit("debian/control", "Architecture: amd64 arm64", "Architecture: all")
        self.assertIn("Architecture is 'all', not the Debian architectures of packaging/arch-classes: amd64 arm64", self.problems())
        self.edit("debian/control", "Architecture: all", "Architecture: amd64 arm64")

    def test_a_relation_in_debian_control_is_refused(self):
        """No package of this source Provides, Replaces, Breaks or Conflicts another: the old names are pruned from the channel."""
        for field in ("Provides", "Replaces", "Breaks", "Conflicts"):
            self.edit("debian/control", "Architecture: amd64 arm64\n", f"Architecture: amd64 arm64\n{field}: foo\n")
            self.assertIn(f"{field} is a relation", self.problems())
            self.edit("debian/control", f"{field}: foo\n", "")

    def test_a_relation_in_the_spec_is_refused(self):
        for field in ("Provides", "Obsoletes", "Conflicts"):
            self.edit(SPEC, "\n%description\n", f"\n{field}: foo = 1\n\n%description\n")
            self.assertIn(f"{field}: is a relation", self.problems())
            self.edit(SPEC, f"\n{field}: foo = 1\n", "")

    def layout(self, deb=None, rpm=None):
        """The tree's debian/control and spec with the records package and the reader's three, or the given names."""
        deb = DEB_NAMES[1:] if deb is None else deb
        rpm = RPM_NAMES[1:] if rpm is None else rpm
        control = self.read_file("debian/control")
        stanzas = control.strip().split("\n\n")
        keep = [x for x in stanzas if not re.search(r"^Package: ", x, re.M) or re.search(rf"^Package: {PKG}$", x, re.M)]
        extra = ["Package: %s\nArchitecture: any\nDepends: ${misc:Depends}\nDescription: the reader\n The reader." % n for n in deb]
        with open(self.path("debian", "control"), "w") as f:
            f.write("\n\n".join(keep + extra) + "\n")
        text = re.sub(r"^%package .*\n", "", self.read_file(SPEC), flags=re.M)
        with open(self.path(*SPEC.split(os.sep)), "w") as f:
            f.write(text.replace("\n%prep\n", "\n" + "".join("%package -n " + n + "\n" for n in rpm) + "\n%prep\n", 1))
        for n in DEB_NAMES[1:]:
            for ext in ("install", "symbols", "lintian-overrides"):
                if os.path.exists(self.path("debian", f"{n}.{ext}")):
                    os.remove(self.path("debian", f"{n}.{ext}"))

    def test_the_six_package_layout_passes(self):
        self.layout()
        self.assertEqual(sets.problems(self.root), [])
        for n in DEB_NAMES[1:]:
            for ext in ("install", "symbols", "lintian-overrides"):
                with open(self.path("debian", f"{n}.{ext}"), "w") as f:
                    f.write("x\n")
        self.assertEqual(sets.problems(self.root), [])

    def test_a_seventh_binary_package_is_refused(self):
        self.layout(deb=DEB_NAMES[1:] + ["libplugin-qualification-db-extra"])
        self.assertIn("debian/control: the binary packages are exactly", self.problems())

    def test_a_missing_binary_package_is_refused(self):
        self.layout(deb=DEB_NAMES[2:4])
        self.assertIn("debian/control: the binary packages are exactly", self.problems())

    def test_a_seventh_rpm_package_or_a_missing_one_is_refused(self):
        self.layout(rpm=RPM_NAMES[1:] + ["libplugin-qualification-db-extra"])
        self.assertIn("the %package lines are exactly", self.problems())
        self.layout(rpm=RPM_NAMES[2:5])
        self.assertIn("the %package lines are exactly", self.problems())

    def test_a_file_of_no_package_is_refused_for_every_kind(self):
        self.layout()
        for ext in ("install", "symbols", "lintian-overrides"):
            with open(self.path("debian", f"libplugin-qualification-db-other.{ext}"), "w") as f:
                f.write("x\n")
            self.assertIn(f"debian/libplugin-qualification-db-other.{ext}: a file of no package", self.problems())
            os.remove(self.path("debian", f"libplugin-qualification-db-other.{ext}"))

    def test_an_old_per_set_file_is_refused(self):
        with open(self.path("debian", "plugin-db-qualification-rpi5-zynthian-vangelis.install"), "w") as f:
            f.write("records/rpi5/zynthian-vangelis usr/share/omx/qualification/rpi5\n")
        self.assertIn("debian/plugin-db-qualification-rpi5-zynthian-vangelis.install: a file of no package", self.problems())

    def test_a_released_architecture_needs_sets(self):
        self.edit("packaging/release-arches", "\nrpm\n", "\nrpm x86_64\n")
        self.assertIn("release-arches: class x86-64 of rpm architecture x86_64 has no set under records/x86-64/", self.problems())
        self.with_two_cells()
        self.assertEqual(sets.problems(self.root), [])
        self.edit("packaging/release-arches", "\nrpm x86_64\n", "\nrpm riscv64\n")
        self.assertIn("rpm riscv64 is not an ExclusiveArch", self.problems())

    def test_github_output(self):
        out = os.path.join(self.tmp.name, "out")
        os.environ["GITHUB_OUTPUT"] = out
        try:
            self.assertEqual(self.run_main("github-output")[0], 0)
            with open(out) as f:
                self.assertEqual(f.read().splitlines(), [
                    'deb-arches=["arm64"]', "deb-run=true", f"deb-names={' '.join(DEB_NAMES)}", "deb-prove=true",
                    "rpm-arches=[]", "rpm-run=false", f"rpm-names={' '.join(RPM_NAMES)}", "rpm-prove=false"])
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


class Import(Tree):
    """`tools/sets.py import <class> <set> <out-dir> [--provenance <file>]`: a plugin-qualify --out directory into
    records/<class>/<set>/, by name, refusing what is not a record or has no pair."""
    SRC = os.path.join(ROOT, "records", "x86-64", "fedora44-48000-512")

    def setUp(self):
        super().setUp()
        shutil.copy2(os.path.join(HERE, "check-records.py"), self.path("tools", "check-records.py"))
        self.out = os.path.join(self.tmp.name, "out")
        os.makedirs(self.out)
        names = sorted(f for f in os.listdir(self.SRC) if f.endswith(".qualification.json"))[:2]
        for n in names:
            shutil.copy2(os.path.join(self.SRC, n), self.out)
            with open(os.path.join(self.SRC, n)) as f:
                shutil.copy2(os.path.join(self.SRC, json.load(f)["probe"]["file"]), self.out)
        self.prov = os.path.join(self.tmp.name, "provenance.json")
        self.write_prov("fedora45-48000-512")

    def write_prov(self, set_, **over):
        prov = {"schema": "plugin-qualify.distributed-provenance/1", "set": set_, "hostClass": "x86-64",
                "package": {"name": f"plugin-db-qualification-x86-64-{set_}"}, "hostProfile": "omx-clap-host", "grid": "48000/512"}
        prov.update(over)
        with open(self.prov, "w") as f:
            json.dump(prov, f)

    def snapshot(self):
        return sorted((os.path.relpath(d, self.root), f) for d, _, fs in os.walk(self.root) for f in fs)

    def imp(self, cls="x86-64", set_="fedora45-48000-512", out=None, prov=True):
        argv = ["import", cls, set_, out or self.out] + (["--provenance", self.prov] if prov else [])
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(io.StringIO()):
            rc = sets.main(argv, root=self.root)
        return rc, buf.getvalue()

    def refused(self, name, **kw):
        before = self.snapshot()
        rc, err = self.imp(**kw)
        self.assertEqual(rc, 1, err)
        self.assertIn(f"import: {name}:", err)
        self.assertEqual(self.snapshot(), before, "a refusal changed the tree")
        return err

    def test_the_records_and_probes_are_copied_and_the_check_passes(self):
        before = self.snapshot()
        rc, err = self.imp()
        self.assertEqual(rc, 0, err)
        dest = self.path("records", "x86-64", "fedora45-48000-512")
        self.assertEqual(sorted(os.listdir(dest)), sorted(os.listdir(self.out) + ["provenance.json"]))
        for f in os.listdir(self.out):
            self.assertTrue(filecmp.cmp(os.path.join(self.out, f), os.path.join(dest, f), shallow=False), f)
        added = [x for x in self.snapshot() if x not in before]
        self.assertTrue(all(d == os.path.join("records", "x86-64", "fedora45-48000-512") for d, _ in added), added)
        self.assertEqual([x for x in before if x not in self.snapshot()], [])

    def test_any_other_file_is_refused(self):
        with open(os.path.join(self.out, "notes.txt"), "w") as f:
            f.write("x")
        self.assertIn("notes.txt", self.refused("file-other"))

    def test_a_directory_in_the_out_dir_is_refused(self):
        os.makedirs(os.path.join(self.out, "sub"))
        self.refused("file-other")

    def test_an_unknown_class_is_refused(self):
        self.assertIn("pi4", self.refused("class-unknown", cls="pi4"))

    def test_a_set_that_exists_is_refused(self):
        self.imp()
        self.refused("set-exists")

    def test_an_empty_directory_is_refused(self):
        empty = os.path.join(self.tmp.name, "empty")
        os.makedirs(empty)
        self.refused("dir-empty", out=empty)

    def test_a_missing_directory_is_refused(self):
        self.refused("dir-absent", out=os.path.join(self.tmp.name, "nope"))

    def test_a_record_without_its_probe_is_refused(self):
        probe = next(f for f in os.listdir(self.out) if f.endswith(".probe.json"))
        os.remove(os.path.join(self.out, probe))
        self.assertIn(probe, self.refused("probe-missing"))

    def test_a_probe_without_its_record_is_refused(self):
        rec = next(f for f in os.listdir(self.out) if f.endswith(".qualification.json"))
        os.remove(os.path.join(self.out, rec))
        self.assertIn(rec.replace(".qualification.json", ".probe.json"), self.refused("qualification-missing"))

    def test_a_set_that_fails_the_records_check_is_refused_and_leaves_nothing(self):
        self.write_prov("another-set")
        err = self.refused("set-check-failed")
        self.assertIn("provenance.json", err)
        self.assertFalse(os.path.exists(self.path("records", "x86-64", "fedora45-48000-512")))

    def test_without_a_provenance_the_check_refuses(self):
        self.refused("set-check-failed", prov=False)

    def test_the_usage_names_it(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            sets.main([], root=self.root)
        self.assertIn("tools/sets.py import", buf.getvalue())


class ReleaseArches(unittest.TestCase):
    """What this repository's own packaging/release-arches offers: no amd64 deb."""

    def test_the_deb_is_arm64_alone_and_the_rpm_is_x86_64_and_aarch64(self):
        self.assertEqual(sets.release_arches(ROOT), {"deb": ["arm64"], "rpm": ["x86_64", "aarch64"]})

    def test_every_consumer_still_passes(self):
        self.assertEqual(sets.problems(ROOT), [])
        out = os.path.join(tempfile.mkdtemp(prefix="pdq-gho-"), "out")
        os.environ["GITHUB_OUTPUT"] = out
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sets.main(["github-output"], root=ROOT), 0)
        finally:
            del os.environ["GITHUB_OUTPUT"]
        with open(out) as f:
            written = f.read().splitlines()
        self.assertIn('deb-arches=["arm64"]', written)
        self.assertIn('rpm-arches=["x86_64", "aarch64"]', written)
        self.assertIn("deb-prove=true", written)
        self.assertIn("rpm-prove=true", written)


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
        self.assertEqual(v, {"qualify:Depends": "plugin-qualify (>= 0.20.0~)"})

    def test_amd64_takes_plugin_qualify_0_20_1_and_folds_every_cell(self):
        self.with_two_cells()
        v = self.vars("amd64")
        self.assertEqual(v, {"qualify:Depends": "plugin-qualify (>= 0.20.1~)"})

    def test_the_rpm_folds_its_classes_names(self):
        self.with_two_cells()
        block = sets.spec_block(self.root)
        self.assertIn("%ifarch x86_64\nRequires: plugin-qualify >= 0.20.1\n", block)
        self.assertNotRegex(block, r"(?m)^(Provides|Obsoletes|Conflicts):")
        # each architecture's block names its own classes only
        self.assertNotIn("rpi5", block.split("%endif")[0])
        self.assertIn("%ifarch aarch64\nRequires: plugin-qualify >= 0.20.0\n", block)
        self.assertNotIn("x86-64", block.split("%ifarch aarch64")[1])
        if shutil.which("rpmspec"):
            def q(*what):
                return subprocess.run(["rpmspec", "-q", "--target", "x86_64", *what, self.path(SPEC)],
                                      capture_output=True, text=True, check=True).stdout
            self.assertIn("plugin-qualify >= 0.20.1", q("--requires"))
            self.assertEqual(q("--obsoletes").split(), [])
            self.assertEqual(q("--qf", "%{name}\n").split(), RPM_NAMES)

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
        # the reader's files are split by dh_install from the .install lists: not this test's concern
        with open(os.path.join(bin_, "dh_install"), "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(os.path.join(bin_, "dh_install"), 0o755)
        # the base database's builder and the contract directory's path: this test is about what the rules pass them
        with open(os.path.join(bin_, "pkg-config"), "w") as f:
            f.write("#!/bin/sh\necho /contract/dir\n")
        os.chmod(os.path.join(bin_, "pkg-config"), 0o755)
        with open(self.path("tools", "records-db.py"), "w") as f:
            f.write("import sys\nopen('records-db.args', 'w').write(' '.join(sys.argv[1:]))\n"
                    "open(sys.argv[sys.argv.index('--out') + 1], 'w').write('database')\n")
        saw = os.path.join(self.tmp.name, "substvars")
        env = dict(os.environ, PATH=bin_ + os.pathsep + os.environ["PATH"], GENCONTROL_SAW=saw)
        r = subprocess.run(["make", "-f", "debian/rules", target, f"DEB_HOST_ARCH={arch}"], cwd=self.root,
                           capture_output=True, text=True, env=env)
        return r, saw

    def read_args(self):
        with open(self.path("records-db.args")) as f:
            return f.read().split()

    def installed(self):
        base = self.path("debian", PKG, "usr", "share", "omx", "qualification")
        return sorted(os.path.relpath(os.path.join(d, f), base) for d, _, fs in os.walk(base) for f in fs)

    def test_arm64_installs_only_the_rpi5_sets(self):
        self.with_two_cells()
        r, _ = self.make("override_dh_install", "arm64")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.installed(), ["qualification.sqlite", "rpi5/zynthian-vangelis/a.qualification.json",
                                            "rpi5/zynthian-vangelis/provenance.json"])
        self.assertEqual(self.read_args(), ["--records", "records", "--class", "rpi5", "--contract-dir", "/contract/dir",
                                            "--built-from-file", "BUILT_FROM", "--out",
                                            f"debian/{PKG}/usr/share/omx/qualification/qualification.sqlite"])
        base = self.path("debian", PKG, "usr", "share", "omx", "qualification")
        self.assertTrue(filecmp.cmp(os.path.join(base, "rpi5", "zynthian-vangelis", "provenance.json"),
                                    self.path("records", "rpi5", "zynthian-vangelis", "provenance.json"), shallow=False))

    def test_amd64_installs_only_the_x86_64_sets(self):
        self.with_two_cells()
        r, _ = self.make("override_dh_install", "amd64")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.installed(), ["qualification.sqlite"] + [f"x86-64/{s}/{f}" for s in CELLS
                                                                       for f in ("a.qualification.json", "provenance.json")])
        self.assertIn("--class x86-64 ", " ".join(self.read_args()) + " ")
        self.assertNotIn("rpi5", self.read_args())

    def test_gencontrol_gets_the_architectures_substvars(self):
        self.with_two_cells()
        for arch, low in (("arm64", "0.20.0"), ("amd64", "0.20.1")):
            if os.path.exists(self.path("debian", f"{PKG}.substvars")):
                os.remove(self.path("debian", f"{PKG}.substvars"))
            r, saw = self.make("override_dh_gencontrol", arch)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(saw) as f:
                text = f.read()
            self.assertIn(f"qualify:Depends=plugin-qualify (>= {low}~)\n", text)
            self.assertNotIn("fedora44", text)

    def test_an_architecture_with_no_class_or_no_set_fails_the_build(self):
        r, _ = self.make("override_dh_install", "i386")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("deb architecture i386 has no class", r.stderr)
        r, _ = self.make("override_dh_install", "amd64")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("class x86-64 of deb architecture amd64 has no set under records/x86-64/", r.stderr)


class Prove(Tree):
    def prove(self, kind, arch, extra_classes=(), image=None, os_release=None, **env_extra):
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
        # the image's own identity: /etc/os-release under PROVE_ROOT (a Fedora 44 container, or Debian 13 for the deb)
        image = image or ("fedora", "44") if kind == "rpm" else image or ("debian", "13")
        os.makedirs(os.path.join(fake, "etc"), exist_ok=True)
        if os_release is not None:
            with open(os.path.join(fake, "etc", "os-release"), "w") as f:
                f.write(os_release)
        elif image != "none":
            with open(os.path.join(fake, "etc", "os-release"), "w") as f:
                f.write(f'NAME="Test"\nID={image[0]}\nVERSION_ID="{image[1]}"\n')
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
        self.assertIn("2 of 2 sets proven, 0 not proven (measured on another host class)", out)
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
        self.assertIn("1 of 2 sets proven, 0 not proven (measured on another host class); failed: fedora44-96000-256", out)

    def test_plugins_taken_from_another_set_fail_the_proof(self):
        self.with_two_cells()
        rc, out, log = self.prove("rpm", "x86_64", WRONG_SET="fedora44-48000-512")
        self.assertEqual(rc, 1)
        self.assertIn("1 of 2 sets proven, 0 not proven (measured on another host class); failed: fedora44-96000-256", out)

    def test_the_arm64_deb_is_proven_with_no_grid(self):
        self.with_two_cells()
        rc, out, log = self.prove("deb", "arm64")
        self.assertEqual(rc, 0, out + log)
        self.assertIn("1 of 1 sets proven, 0 not proven (measured on another host class)", out)
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

    def with_an_rpi5_set(self):
        """x86_64's package carrying a set of the rpi5 class too (the proof names it, it does not prove it)."""
        real = sets.carried
        self.addCleanup(setattr, sets, "carried", real)
        sets.carried = lambda root, kind, arch: real(root, kind, arch) + [("rpi5", "zynthian-vangelis")]

    def test_a_fedora44_set_is_proven_on_a_fedora45_image(self):
        # qualification results are stable: x86-64 is a host class, not an operating system
        self.with_two_cells()
        rc, out, log = self.prove("rpm", "x86_64", image=("fedora", "45"))
        self.assertEqual(rc, 0, out + log)
        self.assertIn("2 of 2 sets proven, 0 not proven (measured on another host class)", out)
        self.assertEqual(log.count("plugin-qualify-sync --system"), 2)
        self.assertNotIn("::notice::", out)
        self.assertNotIn("::warning::", out)

    def test_a_set_of_another_host_class_is_named_and_not_proven_whatever_the_os(self):
        self.with_two_cells()
        self.with_an_rpi5_set()
        for image in (("fedora", "44"), ("fedora", "45")):
            shutil.rmtree(os.path.join(self.tmp.name, "root"), ignore_errors=True)
            rc, out, log = self.prove("rpm", "x86_64", image=image)
            self.assertEqual(rc, 0, out + log)
            self.assertIn("::notice::rpi5/zynthian-vangelis: a set of the rpi5 class, not proven on an x86-64 machine", out)
            self.assertIn("1 sets of another host class, not proven on an x86-64 machine", out)
            self.assertIn("2 of 3 sets proven, 1 not proven (measured on another host class)", out)
            self.assertEqual(log.count("plugin-qualify-sync --system"), 2)
            self.assertNotIn("::warning::", out)

    def test_a_set_measured_on_this_host_class_is_proven(self):
        self.with_two_cells()
        rc, out, log = self.prove("rpm", "x86_64", image=("fedora", "44"))
        self.assertEqual(rc, 0, out + log)
        self.assertIn("2 of 2 sets proven, 0 not proven (measured on another host class)", out)
        self.assertNotIn("::notice::", out)

    def test_no_set_of_this_host_class_warns_and_does_not_fail(self):
        self.with_two_cells()
        real = sets.carried
        self.addCleanup(setattr, sets, "carried", real)
        sets.carried = lambda root, kind, arch: [("rpi5", "zynthian-vangelis")]
        rc, out, log = self.prove("rpm", "x86_64", image=("fedora", "45"))
        self.assertEqual(rc, 0, out + log)
        self.assertIn("::warning::proved 0 of 1 sets: none is a set of the x86-64 class", out)
        self.assertIn("0 of 1 sets proven, 1 not proven (measured on another host class)", out)
        self.assertNotIn("plugin-qualify-sync", log)

    def test_a_set_without_a_host_class_in_its_name_is_always_proven(self):
        self.with_two_cells()
        rc, out, log = self.prove("deb", "arm64", image=("debian", "13"))
        self.assertEqual(rc, 0, out + log)
        self.assertIn("1 of 1 sets proven, 0 not proven (measured on another host class)", out)

    def test_a_package_that_carries_no_set_fails_the_proof(self):
        self.with_two_cells()
        saved = sets.carried
        sets.carried = lambda root, kind, arch: []
        try:
            rc, out, log = self.prove("rpm", "x86_64")
        finally:
            sets.carried = saved
        self.assertEqual(rc, 1, out)
        self.assertIn("::error::", out)
        self.assertIn("carries no set", out)

    def test_no_set_is_not_a_proof(self):
        os.environ["PROVE_ARCH"] = "x86_64"
        try:
            self.assertEqual(self.run_main("prove", "rpm", "pkgs")[0], 1)
        finally:
            del os.environ["PROVE_ARCH"]


if __name__ == "__main__":
    unittest.main()
