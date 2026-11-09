#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The one records package, plugin-qualification-records, per architecture: which sets each architecture carries,
what it depends on, which older package names it takes over, and which architectures a tag releases. The workflows,
debian/rules and the spec read all of it from here.

    tools/sets.py check                         packaging/arch-classes, packaging/release-arches, debian/control,
                                                the spec and records/ agree (the check workflow)
    tools/sets.py names deb|rpm                 the binary package name (binary-names of the builds)
    tools/sets.py list deb|rpm <arch>           one line per set the package of <arch> carries: <class> <set> <cell or ->
    tools/sets.py github-output                 what release.yml's plan job needs, appended to $GITHUB_OUTPUT
    tools/sets.py substvars <deb arch>          the substvars of the Debian package of <deb arch> (debian/rules)
    tools/sets.py install deb|rpm <arch> <dir>  copies records/<class>/ of every class of <arch> into <dir>/<class>/
                                                (debian/rules and the spec's %install)
    tools/sets.py spec                          rewrites the spec's per-architecture block from arch-classes and records/
    tools/sets.py prove deb|rpm <pkg dir>       installs the package of this machine's architecture from <pkg dir> and
                                                proves every set it carries (tools/prove-set.sh), one after the other

packaging/arch-classes maps a Debian architecture and an RPM architecture to a machine class and the plugin-qualify
range of that architecture's package. Every set under records/<class>/ goes into the package of its class's
architecture, at /usr/share/omx/qualification/<class>/<set>/; the sync chooses the set. A set is per machine class,
per sample rate and per quantum: a set named <set>-<rate>-<quantum> holds that one cell.

The package takes over the names the sets were published under before, one package per set: for every set,
plugin-db-qualification-<class>-<set>, and for the set's name without its cell, plugin-db-qualification-<class>-<base>
and omx-qualification-<class>-<base>. They are derived from records/ at build time, never written by hand. Debian
folds the names of its architecture's classes, and on every architecture the names of the Debian packages that were
Architecture: all (the rpi5 sets): Provides (= this version), Replaces and Breaks (<< this version). The RPM folds the
names of its architecture's classes: Provides and Obsoletes (< this version-release), in the block `spec` writes.
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGE = "plugin-qualification-records"
SPEC = os.path.join("packaging", f"{PACKAGE}.spec")
ARCH_CLASSES = os.path.join("packaging", "arch-classes")
RELEASE_ARCHES = os.path.join("packaging", "release-arches")
QUALIFICATION = os.path.join("usr", "share", "omx", "qualification")
CELL = re.compile(r"-([1-9][0-9]*)-([1-9][0-9]*)$")
# the classes whose Debian packages were Architecture: all, installable on any architecture: their names are folded
# by the package of every Debian architecture
DEB_ALL_CLASSES = ("rpi5",)
BLOCK_BEGIN = "# BEGIN per-architecture: written by tools/sets.py spec from packaging/arch-classes and records/"
BLOCK_END = "# END per-architecture"
FORMATS = ("deb", "rpm")


class Refused(Exception):
    pass


def read(root, *path):
    with open(os.path.join(root, *path), encoding="utf-8") as f:
        return f.read()


def rows(text):
    return [line.split() for line in text.splitlines() if line.split() and not line.lstrip().startswith("#")]


def arch_classes(root):
    """[{deb, rpm, class, from, below}] of packaging/arch-classes, in file order."""
    out = []
    for r in rows(read(root, ARCH_CLASSES)):
        if len(r) != 5:
            raise Refused(f"{ARCH_CLASSES}: {' '.join(r)!r} is not <deb arch> <rpm arch> <class> <from> <below>")
        out.append(dict(zip(("deb", "rpm", "class", "from", "below"), r)))
    return out


def release_arches(root):
    """{deb: [arch], rpm: [arch]} of packaging/release-arches."""
    out = {k: [] for k in FORMATS}
    seen = set()
    for r in rows(read(root, RELEASE_ARCHES)):
        if r[0] not in FORMATS or r[0] in seen:
            raise Refused(f"{RELEASE_ARCHES}: {' '.join(r)!r}: one line per format, deb or rpm, then its architectures")
        seen.add(r[0])
        out[r[0]] = r[1:]
    return out


def lines_of(root, kind, arch):
    return [line for line in arch_classes(root) if line[kind] == arch]


def classes(root, kind, arch):
    return [line["class"] for line in lines_of(root, kind, arch)]


def tree_sets(root, cls=None):
    """[(class, set)] under records/, sorted."""
    base = os.path.join(root, "records")
    if not os.path.isdir(base):
        return []
    return sorted((c, s) for c in os.listdir(base) if (cls is None or c == cls) and os.path.isdir(os.path.join(base, c))
                  for s in os.listdir(os.path.join(base, c)) if os.path.isdir(os.path.join(base, c, s)))


def cell(set_):
    m = CELL.search(set_)
    return f"{m.group(1)}/{m.group(2)}" if m else "-"


def carried(root, kind, arch):
    """[(class, set)] the package of <arch> carries; refused when <arch> has no class or a class has no set."""
    cls = classes(root, kind, arch)
    if not cls:
        raise Refused(f"{kind} architecture {arch} has no class in {ARCH_CLASSES}")
    out = []
    for c in cls:
        sets = tree_sets(root, c)
        if not sets:
            raise Refused(f"class {c} of {kind} architecture {arch} has no set under records/{c}/")
        out += sets
    return out


def qualify_range(root, kind, arch):
    """(from, below) of <arch>; refused when its classes give two ranges."""
    ranges = {(line["from"], line["below"]) for line in lines_of(root, kind, arch)}
    if len(ranges) != 1:
        raise Refused(f"{kind} architecture {arch} has {len(ranges)} plugin-qualify ranges in {ARCH_CLASSES}, not one")
    return ranges.pop()


def folded_names(root, cls_list):
    """The names the sets of these classes were published under, one package per set."""
    names = set()
    for c in cls_list:
        for _, s in tree_sets(root, c):
            names.add(f"plugin-db-qualification-{c}-{s}")
            base = CELL.sub("", s)
            names.add(f"plugin-db-qualification-{c}-{base}")
            names.add(f"omx-qualification-{c}-{base}")
    return sorted(names)


def deb_folded(root, arch):
    return folded_names(root, sorted(set(classes(root, "deb", arch)) | set(DEB_ALL_CLASSES)))


def changelog_version(root):
    m = re.match(r"^\S+ \(([^)]*)\)", read(root, "debian", "changelog"))
    return m.group(1) if m else None


def spec_version(root):
    m = re.search(r"^Version: *(\S+)$", read(root, SPEC), re.M)
    return m.group(1) if m else None


def substvars(root, arch):
    carried(root, "deb", arch)
    low, below = qualify_range(root, "deb", arch)
    version = changelog_version(root)
    names = deb_folded(root, arch)
    return "\n".join([
        f"qualify:Depends=plugin-qualify (>= {low}~), plugin-qualify (<< {below}~)",
        "records:Provides=" + ", ".join(f"{n} (= {version})" for n in names),
        "records:Replaces=" + ", ".join(f"{n} (<< {version})" for n in names),
        "records:Breaks=" + ", ".join(f"{n} (<< {version})" for n in names),
    ]) + "\n"


def install(root, kind, arch, dest):
    """records/<class>/ of every class of <arch> into <dest>/<class>/; the classes copied."""
    cls = []
    for c, _ in carried(root, kind, arch):
        if c not in cls:
            cls.append(c)
    os.makedirs(dest, exist_ok=True)
    for c in cls:
        target = os.path.join(dest, c)
        if os.path.exists(target):
            shutil.rmtree(target)
        shutil.copytree(os.path.join(root, "records", c), target)
        for d, _, files in os.walk(target):
            os.chmod(d, 0o755)
            for f in files:
                os.chmod(os.path.join(d, f), 0o644)
    return cls


def exclusive_arch(root):
    m = re.search(r"^ExclusiveArch: *(.*)$", read(root, SPEC), re.M)
    return m.group(1).split() if m else []


def spec_block(root):
    """The spec's per-architecture block: for each architecture it builds, the Requires and the folded names."""
    out = [BLOCK_BEGIN]
    for arch in exclusive_arch(root):
        low, below = qualify_range(root, "rpm", arch)
        out += [f"%ifarch {arch}", f"Requires: (plugin-qualify >= {low} with plugin-qualify < {below})"]
        for n in folded_names(root, classes(root, "rpm", arch)):
            out += [f"Provides: {n} = %{{version}}-%{{release}}", f"Obsoletes: {n} < %{{version}}-%{{release}}"]
        out.append("%endif")
    out.append(BLOCK_END)
    return "\n".join(out)


def spec_block_in_tree(root):
    text = read(root, SPEC)
    m = re.search(rf"^{re.escape(BLOCK_BEGIN)}$.*?^{re.escape(BLOCK_END)}$", text, re.M | re.S)
    return (m.group(0), text) if m else (None, text)


def write_spec(root):
    block, text = spec_block_in_tree(root)
    if block is None:
        raise Refused(f"{SPEC} has no per-architecture block ({BLOCK_BEGIN!r} to {BLOCK_END!r})")
    # the new block reads the spec (its ExclusiveArch): written before the file is opened for writing
    text = text.replace(block, spec_block(root))
    with open(os.path.join(root, SPEC), "w", encoding="utf-8") as f:
        f.write(text)


def control_stanzas(root):
    return [dict(re.findall(r"^([A-Za-z-]+): *(.*)$", s, re.M)) for s in read(root, "debian", "control").strip().split("\n\n")]


def problems(root):
    out = []
    try:
        lines = arch_classes(root)
        rel = release_arches(root)
    except (Refused, OSError) as e:
        return [str(e)]
    mapped = [line["class"] for line in lines]
    for c in sorted({c for c in mapped if mapped.count(c) > 1}):
        out.append(f"{ARCH_CLASSES}: class {c} is on two lines; a class is carried by one architecture")
    for c in sorted({c for c, _ in tree_sets(root)} - set(mapped)):
        out.append(f"records/{c}/: class {c} has no architecture in {ARCH_CLASSES}")
    deb_arches = sorted({line["deb"] for line in lines})
    for kind in FORMATS:
        for arch in sorted({line[kind] for line in lines}):
            try:
                qualify_range(root, kind, arch)
            except Refused as e:
                out.append(str(e))

    binaries = [s for s in control_stanzas(root) if "Package" in s]
    if [s["Package"] for s in binaries] != [PACKAGE]:
        out.append(f"debian/control: one binary package, {PACKAGE}, not {[s['Package'] for s in binaries]}")
    else:
        b = binaries[0]
        if sorted(b.get("Architecture", "").split()) != deb_arches:
            out.append(f"debian/control: Architecture is {b.get('Architecture')!r}, not the Debian architectures of "
                       f"{ARCH_CLASSES}: {' '.join(deb_arches)}")
        for field, var in (("Depends", "qualify:Depends"), ("Provides", "records:Provides"),
                           ("Replaces", "records:Replaces"), ("Breaks", "records:Breaks")):
            if f"${{{var}}}" not in b.get(field, ""):
                out.append(f"debian/control: {field} does not carry ${{{var}}}")
    for name in sorted(os.listdir(os.path.join(root, "debian"))):
        if name == "install" or (name.endswith((".install", ".lintian-overrides")) and name.rsplit(".", 1)[0] != PACKAGE):
            out.append(f"debian/{name}: a file of no package; the one binary package is {PACKAGE}")

    try:
        spec = read(root, SPEC)
    except OSError:
        return out + [f"{SPEC}: missing"]
    if not re.search(rf"^Name: *{re.escape(PACKAGE)}$", spec, re.M):
        out.append(f"{SPEC}: Name is not {PACKAGE}")
    rpm_arches = {line["rpm"] for line in lines}
    built = exclusive_arch(root)
    if not built:
        out.append(f"{SPEC}: no ExclusiveArch")
    for arch in built:
        if arch not in rpm_arches:
            out.append(f"{SPEC}: ExclusiveArch {arch} has no class in {ARCH_CLASSES}")
    block, _ = spec_block_in_tree(root)
    if block is None:
        out.append(f"{SPEC}: no per-architecture block")
    else:
        try:
            if block != spec_block(root):
                out.append(f"{SPEC}: the per-architecture block is not what tools/sets.py spec writes; run it")
        except Refused as e:
            out.append(str(e))

    for arch in rel["deb"]:
        if arch not in deb_arches:
            out.append(f"{RELEASE_ARCHES}: deb {arch} is not a Debian architecture of {ARCH_CLASSES}")
    for arch in rel["rpm"]:
        if arch not in built:
            out.append(f"{RELEASE_ARCHES}: rpm {arch} is not an ExclusiveArch of {SPEC}")
    for kind in FORMATS:
        for arch in rel[kind]:
            try:
                carried(root, kind, arch)
            except Refused as e:
                out.append(f"{RELEASE_ARCHES}: {e}")

    deb, rpm = changelog_version(root), spec_version(root)
    if not deb or not rpm or deb != rpm:
        out.append(f"debian/changelog is {deb} but the spec is {rpm}; a tag must equal both")
    return out


def machine_arch(root, kind):
    """The architecture of this machine in <kind>'s naming (PROVE_ARCH overrides it, for the tests)."""
    if os.environ.get("PROVE_ARCH"):
        return os.environ["PROVE_ARCH"]
    m = platform.machine()
    for line in arch_classes(root):
        if line["rpm"] == m:
            return line[kind]
    raise Refused(f"this machine ({m}) has no line in {ARCH_CLASSES}")


def prove(root, kind, pkgs):
    arch = machine_arch(root, kind)
    sets = carried(root, kind, arch)
    script = os.path.join(HERE, "prove-set.sh")
    print(f"{PACKAGE} for {kind} {arch}: {len(sets)} sets", flush=True)
    if subprocess.run(["bash", script, "install", kind, pkgs, arch], cwd=root).returncode != 0:
        print(f"::error::{PACKAGE} ({arch}) did not install", flush=True)
        subprocess.run(["bash", script, "remove", kind], cwd=root)
        return 1
    failed = []
    try:
        # the package holds the classes of its architecture, each with the sets of the tree, and nothing else
        installed = os.path.join(os.environ.get("PROVE_ROOT") or "/", QUALIFICATION)
        want = sorted({c for c, _ in sets})
        have = sorted(os.listdir(installed)) if os.path.isdir(installed) else []
        if have != want:
            print(f"::error::{PACKAGE} ({arch}) installs the classes {have}, not {want}", flush=True)
            return 1
        for c in want:
            got = sorted(os.listdir(os.path.join(installed, c)))
            tree = [s for k, s in sets if k == c]
            if got != tree:
                print(f"::error::{PACKAGE} ({arch}) installs the {c} sets {got}, not {tree}", flush=True)
                return 1
        for cls, set_ in sets:
            print(f"::group::{cls}/{set_}", flush=True)
            r = subprocess.run(["bash", script, "set", kind, cls, set_, cell(set_)], cwd=root)
            print("::endgroup::", flush=True)
            if r.returncode != 0:
                print(f"::error::{cls}/{set_}: the sync did not take it from the records", flush=True)
                failed.append(set_)
    finally:
        subprocess.run(["bash", script, "remove", kind], cwd=root)
    print(f"{len(sets) - len(failed)} of {len(sets)} sets proven" + (f"; failed: {' '.join(failed)}" if failed else ""))
    return 1 if failed or not sets else 0


def main(argv, root=os.path.dirname(HERE)):
    cmd = argv[0] if argv else ""
    try:
        if cmd == "check" and len(argv) == 1:
            p = problems(root)
            for line in p:
                print(line)
            if not p:
                for line in arch_classes(root):
                    n = len(tree_sets(root, line['class']))
                    print(f"{line['deb']}/{line['rpm']}: {line['class']}, {n} set{'' if n == 1 else 's'}, "
                          f"plugin-qualify {line['from']} up to {line['below']}")
                rel = release_arches(root)
                print(f"this version releases: deb {' '.join(rel['deb']) or 'none'}, rpm {' '.join(rel['rpm']) or 'none'}")
            return 1 if p else 0
        if cmd == "names" and len(argv) == 2 and argv[1] in FORMATS:
            print(PACKAGE)
            return 0
        if cmd == "list" and len(argv) == 3 and argv[1] in FORMATS:
            for cls, set_ in carried(root, argv[1], argv[2]):
                print(cls, set_, cell(set_))
            return 0
        if cmd == "github-output" and len(argv) == 1:
            rel = release_arches(root)
            # the install-and-sync proofs run where the records' plugins are: Debian's arm64 lv2vocoder, the
            # channel's x86_64 omx-plugins
            lines = [f"deb-arches={json.dumps(rel['deb'])}", f"deb-run={'true' if rel['deb'] else 'false'}",
                     f"deb-names={PACKAGE}", f"deb-prove={'true' if 'arm64' in rel['deb'] else 'false'}",
                     f"rpm-arches={json.dumps(rel['rpm'])}", f"rpm-run={'true' if rel['rpm'] else 'false'}",
                     f"rpm-names={PACKAGE}", f"rpm-prove={'true' if 'x86_64' in rel['rpm'] else 'false'}"]
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            print("\n".join(lines))
            return 0
        if cmd == "substvars" and len(argv) == 2:
            sys.stdout.write(substvars(root, argv[1]))
            return 0
        if cmd == "install" and len(argv) == 4 and argv[1] in FORMATS:
            for c in install(root, argv[1], argv[2], argv[3]):
                print(f"records/{c}/ -> {os.path.join(argv[3], c)}/")
            return 0
        if cmd == "spec" and len(argv) == 1:
            write_spec(root)
            return 0
        if cmd == "prove" and len(argv) == 3 and argv[1] in FORMATS:
            return prove(root, argv[1], argv[2])
    except Refused as e:
        print(f"tools/sets.py: {e}", file=sys.stderr)
        return 1
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
