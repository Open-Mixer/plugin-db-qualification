#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""Builds the base qualification database from records/ (this repository's qualification store spec, section 5).

    records-db.py --records <dir> --out <file> --contract-dir <dir> [--built-from-file BUILT_FROM] [--class <class> ...]
                [--min-domain <domain>=<version> ...]

A build tool: it reads no environment variable. It writes a new file each run, to a temporary file in the output
directory renamed over --out only when every record is in and user_version is set; a refusal prints its name and
leaves no file. --class limits the build to the classes of one architecture (tools/sets.py list).
--min-domain refuses a domain whose info.version is lower than the floor given for it. The package's floors are its
Build-Depends on the contract packages; the flag is for a caller that builds from a contract directory of its own.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qualification_db import (  # noqa: E402
    Checker, Domains, Emitter, L, Map, Obj, RECORD_SCHEMA, Refusal, Scope, SCHEMA_SQL, Sentence, _insert, _insert_record,
    _insert_tree, parse_record, schema_version)

PROVENANCE_SCHEMA = "plugin-qualify.distributed-provenance/1"
# a set of one cell is named <set>-<rate>-<quantum> (tools/sets.py)
CELL = re.compile(r"-([1-9][0-9]*)-([1-9][0-9]*)$")
# the set tier whose record claims a cell another tier's set also holds (section 4, ruling 2026-11-20)
REFERENCE = "reference"


def _provenance():
    s = "record_set"
    return Obj({
        "schema": L(s, "schema"),
        "set": L(s, "name"),
        "hostClass": L(s, "host_class"),
        "hostProfile": L(s, "host_profile"),
        "tier": L(s, "tier"),
        "measured": L(s, "measured"),
        "date": L(s, "date"),
        "package": Obj({"name": L(s, "package_name"), "version": L(s, "package_version")}, req=True),
        "packages": Map("set_package", by=(("set_id", "set_id"),), kind="text", cols=("name", "version"),
                        const={"pass": 0}, always=True),
        "passes": Map("set_package", by=(("set_id", "set_id"),), kind="text", cols=("name", "version"),
                      const={"pass": 1}),
        # `settings` is handled by the caller: its keys are set_setting rows, its `note` a sentence
        "tierNote": Sentence(), "image": Sentence(), "board": Sentence(), "kernel": Sentence(), "realtime": Sentence(),
        "jack": Sentence(), "grid": Sentence(), "sources": Sentence(), "repositories": Sentence(),
    }, req=True)


PROVENANCE = _provenance()


class Writer:
    """Builds a new base database file."""

    def __init__(self, domains, built_from):
        self.domains = domains
        self.checker = Checker(self.domains)
        self.built_from = built_from
        self.version = schema_version()

    def build(self, sets, out):
        """`sets`: [(class, set, dir)] in byte order. Writes `out` (temp file and rename); a refusal leaves nothing."""
        outdir = os.path.dirname(os.path.abspath(out))
        if not os.path.isdir(outdir):
            raise Refusal("out.dir.absent", f"{outdir}: no such directory")
        fd, tmp = tempfile.mkstemp(prefix=".qualification-", suffix=".tmp", dir=outdir)
        os.close(fd)
        try:
            self._build(sets, tmp)
            os.replace(tmp, out)
        except BaseException:
            for p in (tmp, tmp + "-journal"):
                try:
                    os.unlink(p)
                except FileNotFoundError:
                    pass
            raise

    def _build(self, sets, path):
        os.unlink(path)
        db = sqlite3.connect(path, isolation_level=None)
        try:
            db.execute("PRAGMA page_size = 4096")
            db.execute("PRAGMA journal_mode = DELETE")
            db.execute("PRAGMA foreign_keys = ON")
            with open(SCHEMA_SQL, encoding="utf-8") as f:
                db.executescript(f.read())
            cur = db.cursor()
            cur.execute("BEGIN")
            cur.execute("INSERT INTO store_info (one, user_layer, record_schema, built_from) VALUES (1, 0, ?, ?)",
                        (RECORD_SCHEMA, self.built_from))
            for dom in sorted(self.domains.version):
                cur.execute("INSERT INTO store_domain (domain, version) VALUES (?, ?)", (dom, self.domains.version[dom]))
            for tbl, col, dom, item in self.checker.rows():
                cur.execute("INSERT INTO word_check (tbl, col, domain, item) VALUES (?, ?, ?, ?)", (tbl, col, dom, item))
            plugins, claims = {}, {}
            for cls, name, d in sets:
                self._set(cur, cls, name, d, plugins, claims)
            cur.execute("COMMIT")
            bad = db.execute("PRAGMA foreign_key_check").fetchall()
            if bad:
                raise Refusal("schema-refused", f"foreign key check failed: {bad[0]}")
            db.execute("VACUUM")
            db.execute(f"PRAGMA user_version = {self.version}")
        finally:
            db.close()

    def _set(self, cur, cls, name, d, plugins, claims):
        ppath = os.path.join(d, "provenance.json")
        if not os.path.isfile(ppath):
            raise Refusal("provenance-missing", f"{ppath}: a set has a provenance.json")
        prov = _load(ppath)
        em = Emitter(self.checker, f"{cls}/{name}/provenance.json")
        scope = Scope({"record_set": {}})
        if not isinstance(prov, dict):
            em.refuse("field-type", "", "expected an object")
        settings = prov.get("settings", {})
        if not isinstance(settings, dict) or ("settings" in prov and not settings):
            em.refuse("field-type" if not isinstance(settings, dict) else "empty-object", "settings", "expected a non-empty object")
        if "cell" in prov:
            # the cell of a set of one cell, as plugin-qualify writes it: checked against the set's name, not stored
            # (record_set.name and the set's cells hold it; section 3.5)
            c = prov["cell"]
            if (not isinstance(c, dict) or sorted(c) != ["quantum", "rate"]
                    or not all(isinstance(c[k], int) and not isinstance(c[k], bool) for k in c)):
                em.refuse("field-type", "cell", "expected {rate, quantum}, two integers")
            m = CELL.search(name)
            if not m:
                em.refuse("cell-mismatch", "cell", f"{c['rate']}/{c['quantum']}, but the set's name {name} names no cell")
            if (c["rate"], c["quantum"]) != (int(m.group(1)), int(m.group(2))):
                em.refuse("cell-mismatch", "cell", f"{c['rate']}/{c['quantum']}, not {m.group(1)}/{m.group(2)}, the cell of the set's name")
        em.obj(PROVENANCE, {k: v for k, v in prov.items() if k not in ("settings", "cell")}, scope, "")
        s = scope.rows["record_set"]
        if s["name"] != name or s["host_class"] != cls:
            em.refuse("set-mismatch", "set", f"provenance names {s['host_class']}/{s['name']}, the directory is {cls}/{name}")
        if prov["schema"] != PROVENANCE_SCHEMA:
            em.refuse("field-unmapped", "schema", f"expected {PROVENANCE_SCHEMA}")
        sid = _insert(cur, "record_set", s)
        tier = s["tier"]
        for k, v in settings.items():
            if k == "note":
                if not isinstance(v, str):
                    em.refuse("field-type", "settings.note", "a sentence is text")
                continue
            if not isinstance(v, str):
                em.refuse("field-type", f"settings.{k}", "expected text")
            if not self.checker.ok("set_setting", "key", k):
                em.refuse("word-unknown", f"settings.{k}", f"{k!r} is no word of {self.checker.describe('set_setting', 'key')}")
            cur.execute("INSERT INTO set_setting (set_id, key, value) VALUES (?, ?, ?)", (sid, k, v))
        for r in scope.kids:
            _insert_tree(cur, r, {"set_id": sid}, None)
        files = sorted((f for f in os.listdir(d) if f.endswith(".qualification.json")), key=os.fsencode)
        for f in files:
            self._record(cur, cls, name, d, sid, tier, f, plugins, claims)

    def _record(self, cur, cls, setname, d, sid, tier, fname, plugins, claims):
        label = f"{cls}/{setname}/{fname}"
        stem = fname[: -len(".qualification.json")]
        recname, dot, offer = stem.rpartition(".")
        if not dot or not recname:
            raise Refusal("file-name", f"{label}: the name is <name>.<offer>.qualification.json")
        rec = _load(os.path.join(d, fname))
        em, scope = parse_record(self.checker, label, rec)
        r, p = scope.rows["record"], scope.rows["plugin"]
        if not self.checker.ok("record", "offer", offer):
            em.refuse("word-unknown", "(file name)", f"{offer!r} is no word of {self.checker.describe('record', 'offer')}")
        # the probe output the record judged
        pf = os.path.join(d, r["probe_file"])
        if os.path.basename(r["probe_file"]) != r["probe_file"] or not os.path.isfile(pf):
            em.refuse("probe-missing", "probe.file", f"{r['probe_file']}: no such probe output in the set")
        with open(pf, "rb") as f:
            data = f.read()
        if hashlib.sha256(data).hexdigest() != r["probe_sha256"] or len(data) != r["probe_bytes"]:
            em.refuse("probe-mismatch", "probe", f"{r['probe_file']} is not the probe output the record names (sha256 or bytes differ)")
        key = (p["sha256"], p["format"], p["uri"])
        try:
            if key not in plugins:
                plugins[key] = _insert(cur, "plugin", p)
            pid = plugins[key]
            rid = _insert_record(cur, scope, pid, dict(set_id=sid, host_class=cls, offer=offer, name=recname))
            for cell in (k for k in scope.kids if k.table == "cell"):
                ck = (pid, offer, cls, cell.cols["rate"], cell.cols["quantum"])
                # one claim per key, offer, class and cell (section 4). Ruling 2026-11-20: where a set of the reference
                # tier and a set of another tier hold one, the reference tier's record claims it, whichever set comes
                # first; the other record stays whole, without the claim. Two of one tier, or two of which neither is
                # of the reference tier, are refused.
                if ck in claims:
                    held, held_tier = claims[ck]
                    if tier == REFERENCE and held_tier != REFERENCE:
                        cur.execute("UPDATE claim SET record_id = ? WHERE plugin_id = ? AND offer = ? AND host_class = ? "
                                    "AND rate = ? AND quantum = ?", (rid,) + ck)
                        claims[ck] = (label, tier)
                        continue
                    if held_tier == REFERENCE and tier != REFERENCE:
                        continue
                    raise Refusal("claim-duplicate", f"{label}: the cell {cell.cols['rate']}/{cell.cols['quantum']} of this key, "
                                  f"offer and class is already claimed by {held}")
                claims[ck] = (label, tier)
                cur.execute("INSERT INTO claim (record_id, plugin_id, offer, host_class, rate, quantum) VALUES (?, ?, ?, ?, ?, ?)",
                            (rid,) + ck)
        except sqlite3.IntegrityError as e:
            raise Refusal("schema-refused", f"{label}: {e}") from e


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise Refusal("file-unreadable", f"{path}: {e}") from e


def walk(records_dir, classes=None):
    """[(class, set, dir)] in byte order of their paths."""
    if not os.path.isdir(records_dir):
        raise Refusal("records.dir.absent", f"{records_dir}: no such directory")
    found = []
    for cls in sorted(os.listdir(records_dir), key=os.fsencode):
        cdir = os.path.join(records_dir, cls)
        if not os.path.isdir(cdir) or (classes and cls not in classes):
            continue
        for s in sorted(os.listdir(cdir), key=os.fsencode):
            if os.path.isdir(os.path.join(cdir, s)):
                found.append((cls, s, os.path.join(cdir, s)))
    for c in classes or ():
        if not any(f[0] == c for f in found):
            raise Refusal("class-absent", f"{records_dir}/{c}: the class has no set")
    return found


def built_from(records_dir, built_from_file=None):
    """The commit the base is built from: a substituted BUILT_FROM, else git's HEAD in a checkout; never guessed."""
    if built_from_file:
        try:
            with open(built_from_file, encoding="utf-8") as f:
                text = f.read().strip()
        except OSError as e:
            raise Refusal("built-from-unknown", f"{built_from_file}: {e}") from e
        if re.fullmatch(r"[0-9a-f]{40}", text):
            return text
        if not text.startswith("$Format:"):
            raise Refusal("built-from-unknown", f"{built_from_file} holds no commit ({text[:48]!r})")
        # the placeholder git archive substitutes: in a checkout it is still the placeholder, and git knows the commit
    try:
        out = subprocess.run(["git", "-C", records_dir, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as e:
        raise Refusal("built-from-unknown", f"{records_dir} is no git checkout and no substituted BUILT_FROM file was given") from e
    if not re.fullmatch(r"[0-9a-f]{40}", out):
        raise Refusal("built-from-unknown", f"git rev-parse HEAD gave {out!r}")
    return out


def _version_tuple(text):
    if not re.fullmatch(r"\d+(\.\d+)*", text):
        raise Refusal("min-domain.invalid", f"{text!r} is no version")
    return tuple(int(x) for x in text.split("."))


def parse_min_domain(items):
    """{domain: version} from ["<domain>=<version>", ...]."""
    floors = {}
    for item in items or ():
        dom, eq, ver = item.partition("=")
        if not eq or not dom:
            raise Refusal("min-domain.invalid", f"{item}: expected <domain>=<version>")
        if not re.fullmatch(r"\d+(\.\d+)*", ver):
            raise Refusal("min-domain.invalid", f"{item}: {ver!r} is no version")
        floors[dom] = ver
    return floors


def build_base(records_dir, out, contract_dir, built_from_file=None, classes=None, min_domain=None):
    floors = parse_min_domain(min_domain)
    sets = walk(records_dir, classes)
    # the contract directory is read first: an absent one is the first refusal
    domains = Domains(contract_dir)
    for dom, floor in floors.items():
        if dom not in domains.version:
            raise Refusal("contract.domain.absent", f"--min-domain {dom}={floor}: the store checks no domain {dom}")
        if _version_tuple(domains.version[dom]) < _version_tuple(floor):
            raise Refusal("qualification-db.domain-too-old", f"the {dom} domain is at {domains.version[dom]}, below the floor {floor}")
    writer = Writer(domains, built_from(records_dir, built_from_file))
    writer.build(sets, out)


def export_set(ex, set_id):
    s = dict(ex.db.execute("SELECT * FROM record_set WHERE set_id = ?", (set_id,)).fetchone())
    v = ex.build(PROVENANCE, {"record_set": s}, s)
    settings = {r["key"]: r["value"] for r in ex.db.execute("SELECT * FROM set_setting WHERE set_id = ? ORDER BY rowid", (set_id,))}
    if settings:
        v["settings"] = settings
    else:
        v.pop("settings", None)
    return v


def main(argv):
    ap = argparse.ArgumentParser(prog="records-db.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--records", required=True, help="the records/ directory: <class>/<set>/")
    ap.add_argument("--out", required=True, help="the database file to write")
    ap.add_argument("--contract-dir", required=True, help="the installed contract directory: <domain>/<domain>.json")
    ap.add_argument("--built-from-file", help="a BUILT_FROM file holding the commit, for a tree with no .git")
    ap.add_argument("--min-domain", action="append", metavar="DOMAIN=VERSION",
                    help="refuse a domain whose info.version is lower (repeatable)")
    ap.add_argument("--class", dest="classes", action="append", help="build only this class (repeatable)")
    a = ap.parse_args(argv)
    try:
        build_base(a.records, a.out, a.contract_dir, a.built_from_file, a.classes, a.min_domain)
    except Refusal as e:
        print(f"records-db: refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
