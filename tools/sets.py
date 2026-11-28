#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The records package, plugin-qualification-records, per architecture (beside the reader's three packages): which sets each architecture carries,
and which architectures a tag releases. The workflows,
debian/rules and the spec read all of it from here.

    tools/sets.py check                         packaging/arch-classes, packaging/release-arches, debian/control,
                                                the spec and records/ agree (the check workflow)
    tools/sets.py names deb|rpm                 the binary package names, space-separated (binary-names of the builds)
    tools/sets.py list deb|rpm <arch>           one line per set the package of <arch> carries: <class> <set> <cell or ->
    tools/sets.py github-output                 what release.yml's plan job needs, appended to $GITHUB_OUTPUT
    tools/sets.py install deb|rpm <arch> <dir>  copies records/<class>/ of every class of <arch> into <dir>/<class>/
                                                (debian/rules and the spec's %install)
    tools/sets.py import <class> <set> <out-dir> [--provenance <file>]
                                                copies the *.qualification.json and *.probe.json files of a
                                                `plugin-qualify --out` directory (and the provenance) into
                                                records/<class>/<set>/, then runs tools/check-records.py on it; a
                                                refusal is named and leaves the tree as it was
    tools/sets.py prove deb|rpm <pkg dir>       installs the package of this machine's architecture from <pkg dir> and
                                                proves every set it carries of this machine's host class
                                                (tools/prove-set.sh), one after the other; the others are named, not proven

packaging/arch-classes maps a Debian architecture and an RPM architecture to a machine class. Every set under
records/<class>/ goes into the package of its class's architecture, at /usr/share/omx/qualification/<class>/<set>/; the
sync chooses the set. A set is per machine class, per sample rate and per quantum: a set named <set>-<rate>-<quantum> holds that one cell.

The package carries no relation to the names the sets were published under before, one package per set, and none to
another package of this source: no Provides, Replaces, Breaks, Conflicts or Obsoletes. Those names are pruned from the
channel. `check` refuses a relation in debian/control or the spec.
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
# The source package's binary packages, exactly (this repository's qualification store spec, section 7): the records
# package, which this tool builds the sets of, and the reader's library, its development files and its command, the DDL
# (plugin-qualification-db-schema) and the layer writer (plugin-qualification-db-write). A package, or a
# debian/<name>.install, .symbols or .lintian-overrides file, of any other name is refused.
DEB_PACKAGES = [PACKAGE, "libplugin-qualification-db0", "libplugin-qualification-db-dev", "plugin-qualification-db",
                "plugin-qualification-db-schema", "plugin-qualification-db-write"]
RPM_PACKAGES = [PACKAGE, "libplugin-qualification-db", "libplugin-qualification-db-devel", "plugin-qualification-db",
                "plugin-qualification-db-schema", "plugin-qualification-db-write"]
PACKAGE_FILES = (".install", ".symbols", ".lintian-overrides")
SPEC = os.path.join("packaging", f"{PACKAGE}.spec")
ARCH_CLASSES = os.path.join("packaging", "arch-classes")
RELEASE_ARCHES = os.path.join("packaging", "release-arches")
QUALIFICATION = os.path.join("usr", "share", "omx", "qualification")
BASE_DB = "qualification.sqlite"
RECORD = ".qualification.json"
PROBE = ".probe.json"
CELL = re.compile(r"-([1-9][0-9]*)-([1-9][0-9]*)$")
FORMATS = ("deb", "rpm")
# tools/prove-set.sh set: the sync never took the set (named, not failed)
UNPROVEN_RC = 3


class Refused(Exception):
    pass


def read(root, *path):
    with open(os.path.join(root, *path), encoding="utf-8") as f:
        return f.read()


def rows(text):
    return [line.split() for line in text.splitlines() if line.split() and not line.lstrip().startswith("#")]


def arch_classes(root):
    """[{deb, rpm, class}] of packaging/arch-classes, in file order."""
    out = []
    for r in rows(read(root, ARCH_CLASSES)):
        if len(r) != 3:
            raise Refused(f"{ARCH_CLASSES}: {' '.join(r)!r} is not <deb arch> <rpm arch> <class>")
        out.append(dict(zip(("deb", "rpm", "class"), r)))
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


def _records_db():
    """tools/records-db.py, which holds the rule that settles a cell two sets hold (spec section 4): the proof reads it
    from there, with no second copy."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("records_db", os.path.join(HERE, "records-db.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def set_cells(root, cls, set_):
    """{(rate, quantum)} a set holds: the cell its name gives, or, for a set not named for one, every cell its
    records' grids hold."""
    c = cell(set_)
    if c != "-":
        rate, quantum = c.split("/")
        return {(int(rate), int(quantum))}
    held = set()
    d = os.path.join(root, "records", cls, set_)
    for name in sorted(os.listdir(d)):
        if name.endswith(".qualification.json"):
            with open(os.path.join(d, name), encoding="utf-8") as f:
                grid = (json.load(f).get("measurements") or {}).get("grid") or []
            held.update((p["rate"], p["quantum"]) for p in grid)
    return held


def expected_winner(root, cls, set_, run_cell):
    """The set the sync is to take the plugins of <set_>'s run from: of the sets of the class that hold every cell the
    run is at (its cell, or, with none, the cells of <set_>), the one the store's claim rule settles on (tier, then
    provenance `measured`; tools/records-db.py `_takes_claim`). A cell the rule refuses (the same tier and date, no
    date, neither tier the reference) is refused here by the rule's own name."""
    rdb = _records_db()
    want = set_cells(root, cls, set_) if run_cell == "-" else {tuple(int(x) for x in run_cell.split("/"))}
    if not want:
        return set_  # a set that holds no cell is superseded at none
    won = None
    for name in sorted(os.listdir(os.path.join(root, "records", cls))):
        if not want <= set_cells(root, cls, name):
            continue
        with open(os.path.join(root, "records", cls, name, "provenance.json"), encoding="utf-8") as f:
            prov = json.load(f)
        mine = (prov.get("tier"), prov.get("measured"))
        if won is None:
            won = (name, mine)
            continue
        rate, quantum = min(want)
        try:
            takes = rdb.Writer._takes_claim(f"{cls}/{name}", mine, f"{cls}/{won[0]}", won[1], {"rate": rate, "quantum": quantum})
        except rdb.Refusal as e:
            raise Refused(f"{cls}/{set_}: {e}") from e
        if takes:
            won = (name, mine)
    return won[0]


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


def changelog_version(root):
    m = re.match(r"^\S+ \(([^)]*)\)", read(root, "debian", "changelog"))
    return m.group(1) if m else None


def spec_version(root):
    m = re.search(r"^Version: *(\S+)$", read(root, SPEC), re.M)
    return m.group(1) if m else None


def spec_release(root):
    m = re.search(r"^Release: *(\S+)$", read(root, SPEC), re.M)
    return m.group(1) if m else None


class ImportRefused(Refused):
    def __init__(self, name, msg):
        super().__init__(f"import: {name}: {msg}")


def import_set(root, cls, set_, out, provenance=None):
    """A `plugin-qualify --out` directory into records/<cls>/<set_>/: its *.qualification.json and *.probe.json files, byte
    for byte, and the provenance given. Refused by name, and then nothing is written (a set that fails the records check is
    removed again): file-other, class-unknown, set-exists, dir-absent, dir-empty, probe-missing, qualification-missing,
    set-check-failed."""
    if cls not in {line["class"] for line in arch_classes(root)}:
        raise ImportRefused("class-unknown", f"{cls!r} is not a class of {ARCH_CLASSES}")
    dest = os.path.join(root, "records", cls, set_)
    if os.path.exists(dest):
        raise ImportRefused("set-exists", f"records/{cls}/{set_}/ exists; a set is never replaced, a new measurement is a new set")
    if not os.path.isdir(out):
        raise ImportRefused("dir-absent", f"{out}: no such directory")
    names = sorted(os.listdir(out), key=os.fsencode)
    if not names:
        raise ImportRefused("dir-empty", f"{out} holds no file")
    for n in names:
        if os.path.islink(os.path.join(out, n)) or not os.path.isfile(os.path.join(out, n)) or not n.endswith((RECORD, PROBE)):
            raise ImportRefused("file-other", f"{n}: only *{RECORD} and *{PROBE} files are imported")
    records = {n[: -len(RECORD)] for n in names if n.endswith(RECORD)}
    probes = {n[: -len(PROBE)] for n in names if n.endswith(PROBE)}
    for stem in sorted(records - probes):
        raise ImportRefused("probe-missing", f"{stem}{RECORD} has no {stem}{PROBE}")
    for stem in sorted(probes - records):
        raise ImportRefused("qualification-missing", f"{stem}{PROBE} has no {stem}{RECORD}")
    if provenance is not None and not os.path.isfile(provenance):
        raise ImportRefused("file-other", f"{provenance}: no such provenance file")
    os.makedirs(dest)
    try:
        for n in names:
            shutil.copyfile(os.path.join(out, n), os.path.join(dest, n))
        if provenance is not None:
            shutil.copyfile(provenance, os.path.join(dest, "provenance.json"))
        r = subprocess.run([sys.executable, "-B", os.path.join(root, "tools", "check-records.py"), dest], capture_output=True, text=True)
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    if r.returncode:
        shutil.rmtree(dest, ignore_errors=True)
        parent = os.path.dirname(dest)
        if not os.listdir(parent):
            os.rmdir(parent)
        raise ImportRefused("set-check-failed", f"records/{cls}/{set_}/ fails tools/check-records.py:\n{(r.stdout + r.stderr).strip()}")
    return len(records)


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

    for s in control_stanzas(root):
        for field in ("Provides", "Replaces", "Breaks", "Conflicts"):
            if field in s:
                out.append(f"debian/control: {s.get('Package', 'the source')}: {field} is a relation; the packages of this source "
                           "carry none (the older names are pruned from the channel)")
    binaries = [s for s in control_stanzas(root) if "Package" in s]
    names = [s["Package"] for s in binaries]
    if names != DEB_PACKAGES:
        out.append(f"debian/control: the binary packages are exactly {DEB_PACKAGES}, not {names}")
    for b in binaries:
        if b["Package"] != PACKAGE:
            continue
        if sorted(b.get("Architecture", "").split()) != deb_arches:
            out.append(f"debian/control: Architecture is {b.get('Architecture')!r}, not the Debian architectures of "
                       f"{ARCH_CLASSES}: {' '.join(deb_arches)}")
    for name in sorted(os.listdir(os.path.join(root, "debian"))):
        stem, ext = os.path.splitext(name)
        if name == "install" or (ext in PACKAGE_FILES and stem not in DEB_PACKAGES):
            out.append(f"debian/{name}: a file of no package; the binary packages are {' '.join(DEB_PACKAGES)}")

    try:
        spec = read(root, SPEC)
    except OSError:
        return out + [f"{SPEC}: missing"]
    for field in ("Provides", "Obsoletes", "Conflicts"):
        if re.search(rf"^{field}:", spec, re.M):
            out.append(f"{SPEC}: {field}: is a relation; the packages of this source carry none (the older names are pruned from the channel)")
    if not re.search(rf"^Name: *{re.escape(PACKAGE)}$", spec, re.M):
        out.append(f"{SPEC}: Name is not {PACKAGE}")
    declared = re.findall(r"^%package +(.*?) *$", spec, re.M)
    if declared != [f"-n {n}" for n in RPM_PACKAGES[1:]]:
        out.append(f"{SPEC}: the %package lines are exactly {[f'-n {n}' for n in RPM_PACKAGES[1:]]}, not {declared}")
    rpm_arches = {line["rpm"] for line in lines}
    built = exclusive_arch(root)
    if not built:
        out.append(f"{SPEC}: no ExclusiveArch")
    for arch in built:
        if arch not in rpm_arches:
            out.append(f"{SPEC}: ExclusiveArch {arch} has no class in {ARCH_CLASSES}")

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
    # owner 2026-11-24 (#81): the version is 0.MAJOR.MINOR, the date stamp is the Release, never the version
    if rpm and not re.fullmatch(r"0\.\d+\.\d+", rpm):
        out.append(f"{SPEC}: Version {rpm} is not 0.MAJOR.MINOR; the date stamp YYYYMMDDXX goes in the Release")
    rel = spec_release(root)
    if not rel or not re.fullmatch(r"\d{10}%\{\?dist\}", rel):
        out.append(f"{SPEC}: Release {rel} is not YYYYMMDDXX%{{?dist}}, the date and the day's serial")
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


NOTE_SECTIONS = (
    ("wrong", "WRONG WINNER: cells where the sync takes another set than the store's rule gives them"),
    ("unproven-set", "UNPROVEN sets: the sync never takes them"),
    ("unproven-record", "UNPROVEN records: binary differs, the channel serves another omx-plugins version than the one they were measured with"),
    ("pick", "Cells where the sync takes the set the store's rule gives them"),
)


def write_notes(path):
    """The findings tools/prove-set.sh appended to <path> as "<kind>|<text>", written back as the sections of the
    release notes, each line once. The numbers of WRONG WINNER and UNPROVEN record lines."""
    if not path or not os.path.isfile(path):
        return 0, 0
    with open(path, encoding="utf-8") as f:
        found = [l.rstrip("\n").split("|", 1) for l in f if "|" in l]
    out = []
    for kind, title in NOTE_SECTIONS:
        lines = sorted({t for k, t in found if k == kind})
        if lines:
            out += [f"### {title}", ""] + [f"- {t}" for t in lines] + [""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return len({t for k, t in found if k == "wrong"}), len({t for k, t in found if k == "unproven-record"})


def prove(root, kind, pkgs):
    arch = machine_arch(root, kind)
    sets = carried(root, kind, arch)
    script = os.path.join(HERE, "prove-set.sh")
    # PROVE_NOTES: the file the proof's findings go to, for the release notes (a new one each run)
    notes_file = os.environ.get("PROVE_NOTES")
    if notes_file and os.path.exists(notes_file):
        os.remove(notes_file)
    print(f"{PACKAGE} for {kind} {arch}: {len(sets)} sets", flush=True)
    if not sets:
        print(f"::error::{PACKAGE} ({arch}) carries no set: nothing to prove", flush=True)
        return 1
    # the host class of this machine: the class packaging/arch-classes gives its architecture (x86_64: x86-64, aarch64:
    # rpi5). The operating system is no part of it: qualification results are stable across releases and OS names.
    here = "/".join(classes(root, kind, arch))
    if subprocess.run(["bash", script, "install", kind, pkgs, arch], cwd=root).returncode != 0:
        print(f"::error::{PACKAGE} ({arch}) did not install", flush=True)
        subprocess.run(["bash", script, "remove", kind], cwd=root)
        return 1
    failed, unproven_sets = [], []
    total, unmatched = len(sets), []
    try:
        # the package holds the classes of its architecture, each with the sets of the tree, and nothing else
        installed = os.path.join(os.environ.get("PROVE_ROOT") or "/", QUALIFICATION)
        # beside the classes, the base database the package builds from them (the spec, debian/rules): it is no class
        base = os.path.join(installed, BASE_DB)
        if not os.path.isfile(base) or os.path.getsize(base) == 0:
            print(f"::error::{PACKAGE} ({arch}) installs no base database {BASE_DB} in {installed}", flush=True)
            return 1
        want = sorted({c for c, _ in sets})
        have = sorted(e for e in os.listdir(installed) if e != BASE_DB) if os.path.isdir(installed) else []
        if have != want:
            print(f"::error::{PACKAGE} ({arch}) installs the classes {have}, not {want}", flush=True)
            return 1
        for c in want:
            got = sorted(os.listdir(os.path.join(installed, c)))
            tree = [s for k, s in sets if k == c]
            if got != tree:
                print(f"::error::{PACKAGE} ({arch}) installs the {c} sets {got}, not {tree}", flush=True)
                return 1
        # a set is proven on a machine of its class, whatever its name says about the image it was measured on; a set of
        # another class is named, not proven, and does not fail
        unmatched = [(c, s) for c, s in sets if c not in classes(root, kind, arch)]
        for cls, set_ in unmatched:
            print(f"::notice::{cls}/{set_}: a set of the {cls} class, not proven on an {here} machine", flush=True)
        if unmatched:
            print(f"{len(unmatched)} sets of another host class, not proven on an {here} machine", flush=True)
        total = len(sets)
        sets = [x for x in sets if x not in unmatched]
        if not sets:
            print(f"::warning::proved 0 of {len(unmatched)} sets: none is a set of the {here} class", flush=True)
        for cls, set_ in sets:
            print(f"::group::{cls}/{set_}", flush=True)
            try:
                winner = expected_winner(root, cls, set_, cell(set_))
            except Refused as e:
                print(f"::error::{e}", flush=True)
                print("::endgroup::", flush=True)
                failed.append(set_)
                continue
            r = subprocess.run(["bash", script, "set", kind, cls, set_, cell(set_), winner], cwd=root)
            print("::endgroup::", flush=True)
            if r.returncode == UNPROVEN_RC:
                unproven_sets.append(set_)
            elif r.returncode != 0:
                print(f"::error::{cls}/{set_}: the sync did not take it from the records", flush=True)
                failed.append(set_)
    finally:
        subprocess.run(["bash", script, "remove", kind], cwd=root)
    wrong, unproven = write_notes(notes_file)
    if unproven:
        print(f"::warning::{unproven} records UNPROVEN: binary differs, the omx-plugins the channel serves is not the version they were measured with; they stay as measured and the release notes name them", flush=True)
    if wrong:
        print(f"::warning::{wrong} cells where plugin-qualify takes another set than the store's rule gives them (named in the notes)", flush=True)
    print(f"{len(sets) - len(failed) - len(unproven_sets)} of {total} sets proven, {len(unmatched)} not proven (measured on another host class)"
          + (f", {len(unproven_sets)} UNPROVEN (never taken by the sync): {' '.join(unproven_sets)}" if unproven_sets else "")
          + (f"; failed: {' '.join(failed)}" if failed else ""))
    return 1 if failed else 0


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
                    print(f"{line['deb']}/{line['rpm']}: {line['class']}, {n} set{'' if n == 1 else 's'}")
                rel = release_arches(root)
                print(f"this version releases: deb {' '.join(rel['deb']) or 'none'}, rpm {' '.join(rel['rpm']) or 'none'}")
            return 1 if p else 0
        if cmd == "names" and len(argv) == 2 and argv[1] in FORMATS:
            print(" ".join(DEB_PACKAGES if argv[1] == "deb" else RPM_PACKAGES))
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
                     f"deb-names={' '.join(DEB_PACKAGES)}", f"deb-prove={'true' if 'arm64' in rel['deb'] else 'false'}",
                     f"rpm-arches={json.dumps(rel['rpm'])}", f"rpm-run={'true' if rel['rpm'] else 'false'}",
                     f"rpm-names={' '.join(RPM_PACKAGES)}", f"rpm-prove={'true' if 'x86_64' in rel['rpm'] else 'false'}"]
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            print("\n".join(lines))
            return 0
        if cmd == "install" and len(argv) == 4 and argv[1] in FORMATS:
            for c in install(root, argv[1], argv[2], argv[3]):
                print(f"records/{c}/ -> {os.path.join(argv[3], c)}/")
            return 0
        if cmd == "import" and len(argv) in (4, 6) and (len(argv) == 4 or argv[4] == "--provenance"):
            n = import_set(root, argv[1], argv[2], argv[3], argv[5] if len(argv) == 6 else None)
            print(f"records/{argv[1]}/{argv[2]}/: {n} record{'' if n == 1 else 's'} imported and checked")
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
