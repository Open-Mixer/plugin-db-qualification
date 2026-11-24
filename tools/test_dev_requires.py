"""The development packages carry what plugin-qualification-db.pc requires.

pkg-config --cflags and --libs on the reader resolve every module of the
.pc file's Requires.private, so the -dev (deb) and -devel (rpm) package
must pull each module's own development package, at the floor the build
uses. A module with no development package named here fails the test, so
a new Requires.private entry cannot be added without its packaging.
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


def floor(rel, name):
    m = re.search(re.escape(name) + r"\s*\(>=\s*([^)\s]+)\)", rel)
    return m.group(1) if m else None


def rpm_lines(prefix):
    return [l.strip() for l in read("packaging/plugin-qualification-records.spec").splitlines()
            if l.startswith(prefix)]


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
            want = floor(bdep, pkg)
            self.assertIsNotNone(want, f"{pkg}: not in Build-Depends with a floor")
            self.assertEqual(floor(dep, pkg), want,
                             f"libplugin-qualification-db-dev does not Depend on {pkg} (>= {want}), "
                             f"which the .pc file's {mod} needs")

    def test_rpm_devel_requires(self):
        req = rpm_dev_requires()
        breq = rpm_lines("BuildRequires:")
        for mod in pc_modules():
            pkg = DEV[mod][1]
            b = [l for l in breq if re.search(r"\b" + re.escape(pkg) + r"\s*>=", l)]
            self.assertTrue(b, f"{pkg}: not in BuildRequires with a floor")
            want = re.search(re.escape(pkg) + r"\s*>=\s*(\S+)", b[0]).group(1)
            self.assertIn(f"{pkg} >= {want}", req,
                          f"libplugin-qualification-db-devel does not Require {pkg} >= {want}, "
                          f"which the .pc file's {mod} needs")


if __name__ == "__main__":
    unittest.main()
