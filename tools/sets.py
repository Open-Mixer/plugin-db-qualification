#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The record sets this tree packages, and which package builds each: the one place the workflows read them from.

    tools/sets.py check                     the spec, debian/ and records/ agree (the check workflow)
    tools/sets.py names rpm|deb             the binary package names, space separated (binary-names of the builds)
    tools/sets.py list rpm|deb              one line per set: <package> <host class> <set> <cell or ->
    tools/sets.py github-output             rpm-set, rpm-names and deb-names, appended to $GITHUB_OUTPUT
    tools/sets.py prove rpm|deb <pkg dir>   tools/prove-set.sh for every set, one after the other: each installed
                                            alone, plugin-qualify-sync --system takes plugins from it, removed

A set is per machine class, per sample rate and per quantum; a set named <set>-<rate>-<quantum> holds that one cell.
The RPM sets are the %global sets list of packaging/plugin-db-qualification.spec, all of its %global host_class.
The Debian sets are the binary packages of debian/control, each installing the directory its
debian/<package>.install names. check holds them to the tree: every set under records/ is built by exactly one of
them, every one they name is in the tree, a package is plugin-db-qualification-<host class>-<set>, there is no
debian/install (several binary packages need one install file each), and the spec's Version is the top
debian/changelog version.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join("packaging", "plugin-db-qualification.spec")
CELL = re.compile(r"-([1-9][0-9]*)-([1-9][0-9]*)$")


def read(root, *path):
    with open(os.path.join(root, *path), encoding="utf-8") as f:
        return f.read()


def package(cls, set_):
    return f"plugin-db-qualification-{cls}-{set_}"


def cell(set_):
    m = CELL.search(set_)
    return f"{m.group(1)}/{m.group(2)}" if m else "-"


def spec_global(root, name):
    m = re.search(rf"^%global {name} (.*)$", read(root, SPEC), re.M)
    return m.group(1).strip() if m else None


def rpm_sets(root):
    """[(package, class, set)] of the spec's list."""
    cls = spec_global(root, "host_class")
    return [(package(cls, s), cls, s) for s in (spec_global(root, "sets") or "").replace("%{nil}", "").split()]


def deb_sets(root):
    """[(package, class, set)] of debian/control's binary packages, class and set read from each install file."""
    out = []
    for stanza in read(root, "debian", "control").strip().split("\n\n"):
        m = re.search(r"^Package: (\S+)$", stanza, re.M)
        if not m:
            continue
        pkg = m.group(1)
        try:
            line = read(root, "debian", f"{pkg}.install").strip()
        except OSError:
            out.append((pkg, None, None))
            continue
        m = re.fullmatch(r"records/([^/\s]+)/([^/\s]+) usr/share/omx/qualification/([^/\s]+)", line)
        out.append((pkg, m.group(1), m.group(2)) if m and m.group(1) == m.group(3) else (pkg, None, line))
    return out


def tree_sets(root):
    base = os.path.join(root, "records")
    if not os.path.isdir(base):
        return []
    return sorted((c, s) for c in os.listdir(base) for s in os.listdir(os.path.join(base, c))
                  if os.path.isdir(os.path.join(base, c, s)))


def problems(root):
    out = []
    built = {}
    for kind, sets in (("spec", rpm_sets(root)), ("debian/control", deb_sets(root))):
        for pkg, cls, set_ in sets:
            if cls is None:
                out.append(f"{kind}: {pkg} has no debian/{pkg}.install naming records/<class>/<set> usr/share/omx/qualification/<class>"
                           + (f" (it says {set_!r})" if set_ else ""))
                continue
            if pkg != package(cls, set_):
                out.append(f"{kind}: {pkg} installs records/{cls}/{set_}, whose package is {package(cls, set_)}")
            if (cls, set_) in built:
                out.append(f"{kind}: records/{cls}/{set_} is built by {built[(cls, set_)]} too")
            built[(cls, set_)] = pkg
            if not os.path.isfile(os.path.join(root, "records", cls, set_, "provenance.json")):
                out.append(f"{kind}: {pkg} names records/{cls}/{set_}, which the tree does not hold")
    for cls, set_ in tree_sets(root):
        if (cls, set_) not in built:
            out.append(f"records/{cls}/{set_}: no package builds it (the spec's %global sets, or a debian/control stanza)")
    rpm_class = spec_global(root, "host_class")
    for pkg, cls, set_ in deb_sets(root):
        if cls is not None and cls == rpm_class:
            out.append(f"debian/control: {pkg} is a {cls} set, which the spec builds")
    if os.path.exists(os.path.join(root, "debian", "install")):
        out.append("debian/install: each binary package has its own debian/<package>.install")
    deb = re.match(r"^\S+ \(([^)]*)\)", read(root, "debian", "changelog"))
    rpm = re.search(r"^Version: *(\S+)$", read(root, SPEC), re.M)
    if not deb or not rpm or deb.group(1) != rpm.group(1):
        out.append(f"debian/changelog is {deb and deb.group(1)} but the spec is {rpm and rpm.group(1)}; a tag must equal both")
    return out


def sets_of(root, kind):
    if kind not in ("rpm", "deb"):
        raise SystemExit(f"rpm or deb, not {kind}")
    return rpm_sets(root) if kind == "rpm" else deb_sets(root)


def main(argv, root=os.path.dirname(HERE)):
    cmd = argv[0] if argv else ""
    if cmd == "check" and len(argv) == 1:
        p = problems(root)
        for line in p:
            print(line)
        for kind in ("rpm", "deb"):
            print(f"{kind}: {' '.join(s[0] for s in sets_of(root, kind)) or 'no set'}")
        return 1 if p else 0
    if cmd == "names" and len(argv) == 2:
        print(" ".join(s[0] for s in sets_of(root, argv[1])))
        return 0
    if cmd == "list" and len(argv) == 2:
        for pkg, cls, set_ in sets_of(root, argv[1]):
            print(pkg, cls, set_, cell(set_))
        return 0
    if cmd == "github-output" and len(argv) == 1:
        rpm, deb = rpm_sets(root), deb_sets(root)
        lines = [f"rpm-set={'true' if rpm else 'false'}",
                 f"rpm-names={' '.join(s[0] for s in rpm)}",
                 f"deb-names={' '.join(s[0] for s in deb)}"]
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print("\n".join(lines))
        return 0
    if cmd == "prove" and len(argv) == 3:
        failed = []
        sets = sets_of(root, argv[1])
        for pkg, cls, set_ in sets:
            print(f"::group::{pkg}", flush=True)
            r = subprocess.run(["bash", os.path.join(HERE, "prove-set.sh"), argv[1], argv[2], pkg, cls, set_, cell(set_)], cwd=root)
            print("::endgroup::", flush=True)
            if r.returncode != 0:
                print(f"::error::{pkg}: the install-and-sync proof failed", flush=True)
                failed.append(pkg)
        print(f"{len(sets) - len(failed)} of {len(sets)} sets proven" + (f"; failed: {' '.join(failed)}" if failed else ""))
        return 1 if failed or not sets else 0
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
