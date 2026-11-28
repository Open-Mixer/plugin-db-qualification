"""The development packages carry what plugin-qualification-db.pc requires.

pkg-config --cflags and --libs on the reader resolve every module of the
.pc file's Requires.private, so the -dev (deb) package must pull each
module's own development package. On RPM, rpm generates the -devel
package's pkgconfig(<module>) requirements from the .pc file itself, so
the spec types none for an OpenMixer module. No OpenMixer relation
carries a hand-written version (devel wave 2026-11-24); a third-party
module keeps its floor (sqlite 3.37.0, STRICT tables), the same in
Build-Depends/BuildRequires and in the development package. A module with no development package named here
fails the test, so a new Requires.private entry cannot be added without
its packaging.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# module of Requires.private -> (deb development package, rpm development package)
DEV = {
    "sqlite3": ("libsqlite3-dev", "sqlite-devel"),
    "libomx-domain": ("libomx-domain-dev", "libomx-domain-devel"),
}
# third-party modules: their floor is an API fact of that project and stays (kept: third-party)
THIRD_PARTY = {"sqlite3"}


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def pc_modules():
    m = re.search(r"^Requires\.private:\s*(.+)$", read("plugin-qualification-db.pc.in"), re.M)
    if not m:
        return []
    return [x.strip().split()[0] for x in m.group(1).split(",") if x.strip()]


def deb_field(stanza_start, field):
    text = read("debian/control")
    i = text.index(stanza_start)
    j = text.find("\n\n", i)
    stanza = text[i:j if j >= 0 else len(text)]
    m = re.search(r"^" + field + r":((?:.*\n?)(?:^ .*\n?)*)", stanza, re.M)
    return " ".join(m.group(1).split()) if m else ""


def names(rel):
    return [x.strip().split()[0] for x in rel.split(",") if x.strip()]


def entry(rel, name):
    """The entry of <name> in a relation field, as written ("libsqlite3-dev (>= 3.37.0)", "libomx-domain-dev")."""
    return next((x.strip() for x in rel.split(",") if x.strip().split()[0] == name), None)


def rpm_dev_requires():
    spec = read("packaging/plugin-qualification-records.spec")
    i = spec.index("%package -n libplugin-qualification-db-devel")
    j = spec.index("%description -n libplugin-qualification-db-devel")
    return [l.strip()[len("Requires:"):].strip() for l in spec[i:j].splitlines()
            if l.startswith("Requires:")]


class DevRequires(unittest.TestCase):
    def test_modules_are_known(self):
        mods = pc_modules()
        self.assertTrue(mods, "plugin-qualification-db.pc.in has no Requires.private")
        for mod in mods:
            self.assertIn(mod, DEV, f"{mod}: no development package named for this module")

    def test_deb_dev_depends(self):
        dep = deb_field("Package: libplugin-qualification-db-dev", "Depends")
        bdep = deb_field("Source:", "Build-Depends")
        for mod in pc_modules():
            pkg = DEV[mod][0]
            want = entry(bdep, pkg)
            self.assertIsNotNone(want, f"{pkg}: not in Build-Depends")
            self.assertEqual(entry(dep, pkg), want,
                             f"libplugin-qualification-db-dev does not Depend on {want}, which the .pc file's {mod} needs")
            if mod not in THIRD_PARTY:
                self.assertEqual(want, pkg, f"{want}: an OpenMixer package is named with no version")

    def test_rpm_devel_requires(self):
        """An OpenMixer module is not typed (rpm generates pkgconfig(<module>) from the .pc); a third-party one carries
        the BuildRequires floor."""
        req = rpm_dev_requires()
        breq = [l.split(":", 1)[1].strip() for l in read("packaging/plugin-qualification-records.spec").splitlines()
                if l.startswith("BuildRequires:")]
        for mod in pc_modules():
            pkg = DEV[mod][1]
            b = [l for l in breq if l.split()[0] == pkg]
            self.assertEqual(len(b), 1, f"{pkg}: not in BuildRequires")
            typed = [r for r in req if r.split()[0] == pkg]
            if mod in THIRD_PARTY:
                self.assertEqual(typed, b, f"libplugin-qualification-db-devel does not Require {b[0]}")
            else:
                self.assertEqual(b, [pkg], f"{b[0]}: an OpenMixer package is named with no version")
                self.assertEqual(typed, [], f"libplugin-qualification-db-devel types {pkg}: rpm generates pkgconfig({mod})")


if __name__ == "__main__":
    unittest.main()
