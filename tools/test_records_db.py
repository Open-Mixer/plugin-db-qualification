#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""tools/records-db.py: the base database built from records/ (this repository's qualification store spec, sections 5
and 8, change 2). The round trip runs over every record of records/; the refusals run on small sets copied from it.

    python3 -m unittest tools/test_records_db.py

The words come from the owners' contract documents. The test assembles a contract directory from the sibling clones:
TEST ONLY, the tool reads no environment variable. PDQ_SIBLINGS names the directory that holds the clones
(plugin-qualify, plugin-hostd, plugin-db, omx-clap-core); each domain is read from `contract.d/<domain>/` at
PDQ_REF (default origin/main), the hosting domain at PDQ_HOSTING_REF (default origin/lane/omx-clap-core-hosting-domain,
until the hosting domain is on main). Without PDQ_SIBLINGS the tests that need the words are skipped, saying so.
"""
import contextlib
import copy
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TOOL = os.path.join(HERE, "records-db.py")
RECORDS = os.path.join(REPO, "records")
SCHEMA = os.path.join(REPO, "schema", "qualification.sql")
TSV = os.path.join(HERE, "testdata", "field-columns.tsv")
COMMIT = "0123456789abcdef0123456789abcdef01234567"
SRC_SET = ("x86-64", "fedora44-48000-512")
DOMAIN_REPO = {"qualification": "plugin-qualify", "machine": "plugin-hostd", "probe": "plugin-hostd",
               "plugin-db": "plugin-db", "hosting": "omx-clap-core"}

SIBLINGS = os.environ.get("PDQ_SIBLINGS")  # TEST ONLY
REF = os.environ.get("PDQ_REF", "origin/main")
HOSTING_REF = os.environ.get("PDQ_HOSTING_REF", "origin/lane/omx-clap-core-hosting-domain")

SENTENCE_PATHS = ("binary.unpinnable", "run.steps[].detail", "measurements.grid[].memory.unmeasuredDetail",
                  "measurements.unmeasured[].detail", "tiers.dimmed")
PROVENANCE_SENTENCES = ("image", "board", "kernel", "realtime", "jack", "grid", "tierNote", "sources", "repositories")
MAP_PATHS = ("verdicts[].reasons[].params.*", "cost[].reasons[].params.*", "adapter.params.*", "adapter.cells[].params.*",
             "adapter.versions.*", "rejudged.figures.adapter.versions.*")
# the table of every array of section 3.5 and the number of its elements across the files
ARRAY_TABLES = {
    "binary.files[]": "record_file", "run.steps[]": "run_step", "probe.ends[]": "probe_end", "verdicts[]": "verdict",
    "cost[]": "cost_entry", "tiers.offeredOn[]": "tier_offered", "measurements.grid[]": "cell",
    "measurements.grid[].rtSafety.events[]": "cell_event", "measurements.unmeasured[]": "unmeasured",
    "measurements.behaviour.features.required[]": "feature_required", "notMeasured[]": "not_measured",
    "adapter.cells[]": "adapter_cell", "memoryRun.cells[]": "memory_run_cell", "rejudged.owes[]": "rejudged_owe",
}

_contract = {}


def contract_dir():
    """The contract directory assembled from the sibling clones, once; skips the test when they are not given."""
    if "dir" in _contract:
        return _contract["dir"]
    if not SIBLINGS:
        raise unittest.SkipTest("PDQ_SIBLINGS is not set: no sibling clones to read the owners' words from "
                                "(plugin-qualify, plugin-hostd, plugin-db, omx-clap-core)")
    root = tempfile.mkdtemp(prefix="pdq-contract-")
    for dom, repo in DOMAIN_REPO.items():
        clone = os.path.join(SIBLINGS, repo)
        if not os.path.isdir(clone):
            raise unittest.SkipTest(f"{clone}: no such sibling clone")
        ref = HOSTING_REF if dom == "hosting" else REF
        r = subprocess.run(["git", "-C", clone, "show", f"{ref}:contract.d/{dom}/{dom}.json"], capture_output=True)
        if r.returncode:
            raise unittest.SkipTest(f"{repo} {ref}: contract.d/{dom}/{dom}.json: {r.stderr.decode().strip()}")
        os.makedirs(os.path.join(root, dom))
        with open(os.path.join(root, dom, dom + ".json"), "wb") as f:
            f.write(r.stdout)
    _contract["dir"] = root
    return root


def tearDownModule():
    if "dir" in _contract:
        shutil.rmtree(_contract["dir"], ignore_errors=True)


def run_tool(records, out, contract, *extra):
    if not os.path.exists(TOOL):
        raise AssertionError(f"{TOOL} does not exist")
    cmd = [sys.executable, "-B", TOOL, "--records", records, "--out", out, "--contract-dir", contract, *extra]
    return subprocess.run(cmd, capture_output=True, text=True)


def build_ok(case, records, out, contract=None, *extra):
    r = run_tool(records, out, contract or contract_dir(), "--built-from-file",
                 write_commit(os.path.dirname(os.path.dirname(os.path.abspath(out)))), *extra)
    case.assertEqual(r.returncode, 0, f"records-db.py refused: {r.stderr}")
    return r


def write_commit(d):
    path = os.path.join(d, "BUILT_FROM")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(COMMIT + "\n")
    return path


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(path, value):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=1, ensure_ascii=False)
        f.write("\n")


def record_files(cls, set_):
    d = os.path.join(RECORDS, cls, set_)
    return sorted((f for f in os.listdir(d) if f.endswith(".qualification.json")), key=os.fsencode)


def to_relative(setdir):
    """Section 3.7's rewrite on a fixture copy: a CLAP record's binary.path is its file's own name and its hostExtensions
    are the probe output's offer.clapExtensions. (records/ itself gets it once, in a commit of its own.)"""
    for f in os.listdir(setdir):
        if f.endswith(".qualification.json"):
            p = os.path.join(setdir, f)
            rec = load(p)
            if rec["plugin"]["format"] == "clap":
                rec["binary"]["path"] = rec["binary"]["files"][0]["path"]
                rec["hostExtensions"] = load(os.path.join(setdir, rec["probe"]["file"]))["offer"]["clapExtensions"]
            dump(p, rec)


def make_set(tmp, files=None, n=3, src=SRC_SET, name=None):
    """records/<class>/<set>/ in `tmp` with the provenance and `files` (or the first n) of a real set, probe outputs too."""
    cls, set_ = src
    dst = os.path.join(tmp, "records", cls, name or set_)
    os.makedirs(dst)
    shutil.copy(os.path.join(RECORDS, cls, set_, "provenance.json"), dst)
    if name:
        prov = load(os.path.join(dst, "provenance.json"))
        prov["set"] = name
        dump(os.path.join(dst, "provenance.json"), prov)
    for f in files or record_files(cls, set_)[:n]:
        shutil.copy(os.path.join(RECORDS, cls, set_, f), dst)
        shutil.copy(os.path.join(RECORDS, cls, set_, load(os.path.join(dst, f))["probe"]["file"]), dst)
    to_relative(dst)
    return dst


def find(predicate, src=SRC_SET, start=""):
    """The first record file of a real set whose parsed value satisfies the predicate."""
    for f in record_files(*src):
        if f >= start and predicate(load(os.path.join(RECORDS, *src, f)), f):
            return f
    raise AssertionError(f"no record of {src} satisfies the predicate")


def find_any(predicate):
    """((class, set), file) of the first record of records/ that satisfies the predicate."""
    for cls in sorted(os.listdir(RECORDS)):
        for s in sorted(os.listdir(os.path.join(RECORDS, cls))):
            for f in record_files(cls, s):
                if predicate(load(os.path.join(RECORDS, cls, s, f))):
                    return (cls, s), f
    raise AssertionError("no record satisfies the predicate")


def edit(setdir, fname, fn):
    p = os.path.join(setdir, fname)
    rec = load(p)
    fn(rec)
    dump(p, rec)


def leaves(v, path="", out=None, elems=None):
    """Normalised leaf paths of a record: `[]` for an element, `*` for a named value of a params or versions map."""
    out = {} if out is None else out
    elems = {} if elems is None else elems
    if isinstance(v, dict):
        named = path.endswith(".params") or path.endswith(".versions")
        for k, x in v.items():
            leaves(x, f"{path}.{'*' if named else k}" if path else k, out, elems)
    elif isinstance(v, list):
        for x in v:
            elems[path + "[]"] = elems.get(path + "[]", 0) + 1
            leaves(x, path + "[]", out, elems)
    else:
        out[path] = out.get(path, 0) + 1
    return out, elems


def schema_word_columns():
    """(table, column) of every column the DDL gives the word shape: `instr(c, ' ') = 0`."""
    with open(SCHEMA, encoding="utf-8") as f:
        sql = f.read()
    cols = []
    for m in re.finditer(r"CREATE TABLE (\w+) \((.*?)\n\) STRICT;", sql, re.S):
        for c in re.finditer(r"(\w+)\s+TEXT[^\n]*?instr\(\1, ' '\)", m.group(2)):
            cols.append((m.group(1), c.group(1)))
    return cols


class NoWordList(unittest.TestCase):
    def test_17_the_ddl_holds_no_word_list(self):
        """Fails when a word list is written into a CHECK. `typeof(c) IN ('integer', 'real')` names SQLite types."""
        with open(SCHEMA, encoding="utf-8") as f:
            sql = f.read()
        sql = re.sub(r"typeof\(\w+\) IN \('integer', 'real'\)", "", sql)
        self.assertIsNone(re.search(r"\bIN\s*\(\s*'", sql), "a CHECK holds a quoted word list")

    def test_ddl_word_columns_found(self):
        self.assertGreaterEqual(len(schema_word_columns()), 55)


class Fields(unittest.TestCase):
    def test_every_field_of_the_records_is_mapped_or_a_sentence(self):
        """The hand-written table covers every leaf of every record: a field that is in no table is a gap."""
        with open(TSV, encoding="utf-8") as f:
            table = {l.split("\t")[0] for l in f if l.strip() and not l.startswith(("#", "P:"))}
        known = table | set(MAP_PATHS) | set(SENTENCE_PATHS)
        seen = {}
        for cls in sorted(os.listdir(RECORDS)):
            for s in sorted(os.listdir(os.path.join(RECORDS, cls))):
                for f in record_files(cls, s):
                    for p in leaves(load(os.path.join(RECORDS, cls, s, f)))[0]:
                        seen.setdefault(p, f"{cls}/{s}/{f}")
        gaps = {p: f for p, f in seen.items() if p not in known}
        self.assertEqual(gaps, {}, "fields of records/ in no table of field-columns.tsv")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pdq-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.out = os.path.join(self.tmp, "out")
        os.makedirs(self.out)
        self.db = os.path.join(self.out, "qualification.sqlite")

    def refused(self, name, *words, contract=None, extra=()):
        """The build is refused by `name`, naming each of `words`, and leaves nothing in the output directory."""
        r = run_tool(os.path.join(self.tmp, "records"), self.db, contract or contract_dir(),
                     "--built-from-file", write_commit(self.tmp), *extra)
        self.assertNotEqual(r.returncode, 0, "the build was not refused")
        self.assertIn(f"refused: {name}:", r.stderr)
        for w in words:
            self.assertIn(w, r.stderr)
        self.assertEqual(os.listdir(self.out), [], "a refusal left a file")
        return r.stderr

    def rows(self, sql, *args):
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            return db.execute(sql, args).fetchall()


class DdlColumns(Base):
    """Case 24: the columns of the row judge (record_extension, record.host_extensions, cell.rt_own_threads and
    rt_other_*) are written and exported, and the DDL's own checks hold."""
    LV2 = ("rpi5", "zynthian-vangelis")

    def made(self, fn=None, src=SRC_SET, files=None, n=2):
        d = make_set(self.tmp, files, n=n, src=src)
        names = sorted(f for f in os.listdir(d) if f.endswith(".qualification.json"))
        if fn:
            edit(d, names[0], fn)
        return d, names[0]

    def exported(self, d, name):
        build_ok(self, os.path.join(self.tmp, "records"), self.db)
        sys.path.insert(0, HERE)
        import qualification_db
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            ids = {f"{r[1]}.{r[2]}.qualification.json": r[0] for r in db.execute("SELECT record_id, name, offer FROM record")}
            got = qualification_db.Exporter(db).export_record(ids[name])
        return got

    def same(self, d, name):
        got = self.exported(d, name)
        want = RoundTrip.strip(load(os.path.join(d, name)))
        self.assertIsNone(RoundTrip.first_difference(want, got), name)
        return got

    def test_24_host_extensions_of_a_clap_record_round_trip(self):
        d, f = self.made(lambda r: r.update(hostExtensions=["clap.log", "clap.params"]))
        got = self.same(d, f)
        self.assertEqual(got["hostExtensions"], ["clap.log", "clap.params"])
        self.assertEqual(self.rows("SELECT host_extensions FROM record WHERE name || '.' || offer || '.qualification.json' = ?", f), [(1,)])
        self.assertEqual(self.rows("SELECT ord, extension FROM record_extension JOIN record USING (record_id) "
                                   "WHERE name || '.' || offer || '.qualification.json' = ? ORDER BY ord", f),
                         [(0, "clap.log"), (1, "clap.params")])

    def test_24_an_empty_list_of_host_extensions_is_data(self):
        d, f = self.made(lambda r: r.update(hostExtensions=[]))
        self.assertEqual(self.same(d, f)["hostExtensions"], [])
        self.assertEqual(self.rows("SELECT host_extensions FROM record WHERE name || '.' || offer || '.qualification.json' = ?", f), [(1,)])
        self.assertEqual(self.rows("SELECT count(*) FROM record_extension JOIN record USING (record_id) "
                                   "WHERE name || '.' || offer || '.qualification.json' = ?", f), [(0,)])

    def test_24_an_lv2_record_has_no_host_extensions(self):
        f = find(lambda r, n: r["plugin"]["format"] == "lv2", self.LV2)
        d, f = self.made(src=self.LV2, files=[f])
        got = self.same(d, f)
        self.assertNotIn("hostExtensions", got)
        self.assertEqual(self.rows("SELECT host_extensions FROM record"), [(None,)])
        self.assertEqual(self.rows("SELECT count(*) FROM record_extension"), [(0,)])

    def test_24_a_clap_record_without_host_extensions_is_refused(self):
        d, f = self.made(lambda r: r.pop("hostExtensions"))
        self.refused("field-absent", f, "hostExtensions")

    def test_24_an_lv2_record_with_host_extensions_is_refused(self):
        f = find(lambda r, n: r["plugin"]["format"] == "lv2", self.LV2)
        d, f = self.made(lambda r: r.update(hostExtensions=["clap.log"]), src=self.LV2, files=[f])
        self.refused("field-unmapped", f, "hostExtensions")

    def test_24_own_threads_and_other_threads_round_trip(self):
        def put(r):
            rt = r["measurements"]["grid"][0]["rtSafety"]
            rt["ownThreads"] = 2
            rt["otherThreads"] = {"allocationsInRun": 5, "locksInRun": 0, "syscallsInRun": 7}
        d, f = self.made(put)
        got = self.same(d, f)
        rt = got["measurements"]["grid"][0]["rtSafety"]
        self.assertEqual((rt["ownThreads"], rt["otherThreads"]),
                         (2, {"allocationsInRun": 5, "locksInRun": 0, "syscallsInRun": 7}))
        self.assertEqual(self.rows("SELECT rt_own_threads, rt_other_allocations, rt_other_locks, rt_other_syscalls FROM cell "
                                   "WHERE ord = 0 AND rt_own_threads IS NOT NULL"), [(2, 5, 0, 7)])

    def test_24_records_of_today_hold_none_and_read_back_none(self):
        d, f = self.made()
        got = self.same(d, f)
        for c in got["measurements"]["grid"]:
            self.assertNotIn("ownThreads", c.get("rtSafety", {}))
            self.assertNotIn("otherThreads", c.get("rtSafety", {}))
        self.assertEqual(self.rows("SELECT count(*) FROM cell WHERE rt_own_threads IS NOT NULL OR rt_other_locks IS NOT NULL"), [(0,)])

    def test_24_other_threads_with_one_count_only_is_refused_by_the_schema(self):
        def put(r):
            r["measurements"]["grid"][0]["rtSafety"]["otherThreads"] = {"locksInRun": 1}
        d, f = self.made(put)
        self.refused("schema-refused", f)


class Refusals(Base):
    def one(self, fn, n=2):
        d = make_set(self.tmp, n=n)
        f = record_files(*SRC_SET)[0]
        edit(d, f, fn)
        return f

    def test_05_a_word_outside_its_domain_is_refused(self):
        f = self.one(lambda r: r["verdicts"][0].update(rating="excellent"))
        err = self.refused("word-unknown", f, "verdicts[0].rating", "excellent")

    def test_06_a_field_no_column_holds_is_refused(self):
        f = self.one(lambda r: r["verdicts"][0].update(mood="calm"))
        self.refused("field-unmapped", f, "verdicts[0].mood")

    def test_15_a_resource_budget_unmeasured_reason_is_refused(self):
        """`limit-exceeded` is a word of the resource budget's item, not of the measurement's."""
        f = self.one(lambda r: r["measurements"]["grid"][0].update(memory={"unmeasuredReason": "limit-exceeded"}))
        self.refused("word-unknown", f, "measurements.grid[0].memory.unmeasuredReason", "limit-exceeded")

    def test_16_formats_are_checked_against_the_plugin_db_item(self):
        """A plugin-db domain whose formats item holds `clap` only refuses an LV2 record."""
        cls, set_ = "rpi5", "zynthian-vangelis"
        f = find(lambda r, n: r["plugin"]["format"] == "lv2", (cls, set_))
        make_set(self.tmp, [f], src=(cls, set_))
        c = os.path.join(self.tmp, "contract")
        shutil.copytree(contract_dir(), c)
        p = os.path.join(c, "plugin-db", "plugin-db.json")
        doc = load(p)
        item = doc["components"]["schemas"]["PLUGIN_DB_ADDRESS_FORMATS"]
        item["oneOf"] = [o for o in item["oneOf"] if o["const"] == "clap"]
        dump(p, doc)
        self.refused("word-unknown", f, "plugin.format", "lv2", contract=c)

    def test_10_a_short_sha256_and_a_format_outside_the_set_are_refused(self):
        def short(r):
            r["binary"].update(sha256=r["binary"]["sha256"][:63])
            r["binary"]["files"][0]["sha256"] = r["binary"]["sha256"]  # the key stays the binary's entry's (section 3.7)
        f = self.one(short)
        self.refused("schema-refused", f)
        shutil.rmtree(os.path.join(self.tmp, "records"))
        f = self.one(lambda r: r["plugin"].update(format="vst3"))
        self.refused("word-unknown", f, "plugin.format", "vst3")

    def test_10_the_schema_refuses_them_itself(self):
        db = sqlite3.connect(":memory:")
        with open(SCHEMA, encoding="utf-8") as f:
            db.executescript(f.read())
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO plugin (sha256, format, uri) VALUES (?, 'clap', 'x')", ("a" * 63,))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO plugin (sha256, format, uri) VALUES (?, 'a b', 'x')", ("a" * 64,))

    def test_an_empty_object_is_refused(self):
        f = self.one(lambda r: r["measurements"]["grid"][0].update(latency={}))
        self.refused("empty-object", f, "measurements.grid[0].latency")

    def test_a_present_empty_array_of_the_only_with_rows_list_is_refused(self):
        f = self.one(lambda r: r["probe"].update(ends=[]))
        self.refused("array-empty", f, "probe.ends")

    def test_an_absent_always_present_array_is_refused(self):
        f = self.one(lambda r: r.pop("verdicts"))
        self.refused("field-absent", f, "verdicts")

    def test_a_probe_output_that_differs_is_refused(self):
        d = make_set(self.tmp, n=2)
        f = record_files(*SRC_SET)[0]
        with open(os.path.join(d, load(os.path.join(d, f))["probe"]["file"]), "ab") as p:
            p.write(b" ")
        self.refused("probe-mismatch", f)

    def test_9_an_absent_contract_directory_is_refused(self):
        make_set(self.tmp, n=2)
        self.refused("contract.dir.absent", contract=os.path.join(self.tmp, "no-such-dir"))

    def test_9_a_second_claim_on_one_key_and_cell_is_refused(self):
        d = make_set(self.tmp, n=2)
        f = [x for x in record_files(*SRC_SET) if x.endswith(".default.qualification.json")][0]
        # the copy of a record under another name claims the same cell of the same key
        shutil.copy(os.path.join(d, f), os.path.join(d, "copy-of-" + f))
        shutil.copy(os.path.join(RECORDS, *SRC_SET, load(os.path.join(RECORDS, *SRC_SET, f))["probe"]["file"]), d)
        self.refused("claim-duplicate", "copy-of-" + f)


class Identity(Base):
    def test_04_two_builds_are_row_identical_and_byte_identical(self):
        for s in ("fedora44-48000-512", "fedora44-96000-64"):
            make_set(self.tmp, n=40, src=("x86-64", s))
        out2 = os.path.join(self.tmp, "second")
        os.makedirs(out2)
        build_ok(self, os.path.join(self.tmp, "records"), self.db)
        build_ok(self, os.path.join(self.tmp, "records"), os.path.join(out2, "qualification.sqlite"))
        dumps = []
        for p in (self.db, os.path.join(out2, "qualification.sqlite")):
            with contextlib.closing(sqlite3.connect(p)) as db:
                dumps.append(sorted(db.iterdump()))
        self.assertEqual(dumps[0], dumps[1])
        with open(self.db, "rb") as a, open(os.path.join(out2, "qualification.sqlite"), "rb") as b:
            self.assertEqual(hashlib.sha256(a.read()).hexdigest(), hashlib.sha256(b.read()).hexdigest())

    def test_a_new_file_each_run_over_an_old_one(self):
        make_set(self.tmp, n=2)
        build_ok(self, os.path.join(self.tmp, "records"), self.db)
        first = self.rows("SELECT count(*) FROM record")
        build_ok(self, os.path.join(self.tmp, "records"), self.db)
        self.assertEqual(self.rows("SELECT count(*) FROM record"), first)
        self.assertEqual(os.listdir(self.out), ["qualification.sqlite"])


class Params(Base):
    """Cases 18 and 19: a param's number keeps its type, and the adapter's params keep their presence."""

    def export_all(self):
        sys.path.insert(0, HERE)
        import qualification_db as q
        db = sqlite3.connect(self.db)
        self.addCleanup(db.close)
        ex = q.Exporter(db)
        return {r[1]: ex.export_record(r[0]) for r in db.execute("SELECT record_id, name || '.' || offer FROM record")}

    def build_one(self, src, f, fn):
        shutil.rmtree(os.path.join(self.tmp, "records"), ignore_errors=True)
        if os.path.exists(self.db):
            os.unlink(self.db)
        d = make_set(self.tmp, [f], src=src)
        edit(d, f, fn)
        build_ok(self, os.path.join(self.tmp, "records"), self.db)
        return self.export_all()[f[: -len(".qualification.json")]]

    def test_18_a_fractional_reason_param_and_an_integer_one(self):
        src, f = find_any(lambda r: r["verdicts"] and r["verdicts"][0]["reasons"])

        def fix(r):
            r["verdicts"][0]["reasons"][0]["params"] = {"coreFractionP95": 0.37, "blocks": 40}
        rec = self.build_one(src, f, fix)
        got = {n: (v, t) for n, v, t in self.rows(
            "SELECT p.name, p.number, typeof(p.number) FROM reason_param p JOIN reason r USING (reason_id) "
            "WHERE r.verdict_ord = 0 AND r.ord = 0")}
        self.assertEqual(got, {"coreFractionP95": (0.37, "real"), "blocks": (40, "integer")})
        params = rec["verdicts"][0]["reasons"][0]["params"]
        self.assertEqual(params, {"coreFractionP95": 0.37, "blocks": 40})
        self.assertIsInstance(params["blocks"], int)
        self.assertIsInstance(params["coreFractionP95"], float)

    def test_19_adapter_params_round_trip(self):
        src, f = find_any(lambda r: "adapter" in r and len(r["adapter"].get("cells", [])) >= 2)

        def with_params(r):
            r["adapter"]["params"] = {"resp": 3, "step": "add"}
            r["adapter"]["cells"][0]["params"] = {"peak": 0.5}
            r["adapter"]["cells"][1]["params"] = {}

        def empty_params(r):
            r["adapter"]["params"] = {}
            for c in r["adapter"]["cells"]:
                c.pop("params", None)

        def no_params(r):
            r["adapter"].pop("params", None)
            for c in r["adapter"]["cells"]:
                c.pop("params", None)

        rec = self.build_one(src, f, with_params)
        self.assertEqual(rec["adapter"]["params"], {"resp": 3, "step": "add"})
        self.assertEqual(rec["adapter"]["cells"][0]["params"], {"peak": 0.5})
        self.assertEqual(rec["adapter"]["cells"][1]["params"], {})
        self.assertEqual(self.rows("SELECT adapter_params FROM record"), [(1,)])
        self.assertEqual(self.rows("SELECT ord, params FROM adapter_cell ORDER BY ord")[:2], [(0, 1), (1, 1)])
        rec = self.build_one(src, f, empty_params)
        self.assertEqual(rec["adapter"]["params"], {})
        self.assertTrue(all("params" not in c for c in rec["adapter"]["cells"]))
        self.assertEqual(self.rows("SELECT adapter_params FROM record"), [(1,)])
        self.assertEqual({r[0] for r in self.rows("SELECT params FROM adapter_cell")}, {0})
        rec = self.build_one(src, f, no_params)
        self.assertNotIn("params", rec["adapter"])
        self.assertEqual(self.rows("SELECT adapter_params FROM record"), [(0,)])
        self.assertEqual(self.rows("SELECT count(*) FROM adapter_param"), [(0,)])


class BuiltFrom(Base):
    GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@example.invalid"}

    def git(self, cwd, *args, **kw):
        env = {**os.environ, **self.GIT_ENV}
        return subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, env=env, **kw)

    def repo(self):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(repo)
        shutil.move(os.path.join(self.tmp, "records"), os.path.join(repo, "records"))
        with open(os.path.join(repo, "BUILT_FROM"), "w") as f:
            f.write("$Format:%H$\n")
        with open(os.path.join(repo, ".gitattributes"), "w") as f:
            f.write("BUILT_FROM export-subst\n")
        self.git(repo, "init", "-q")
        self.git(repo, "add", "-A")
        tree = self.git(repo, "write-tree").stdout.decode().strip()
        env = {**os.environ, **self.GIT_ENV}
        commit = subprocess.run(["git", "-C", repo, "commit-tree", tree, "-m", "fixture"], check=True,
                                capture_output=True, env=env).stdout.decode().strip()
        self.git(repo, "update-ref", "HEAD", commit)
        return repo, commit

    def test_12_a_git_archive_tarball_carries_its_commit(self):
        make_set(self.tmp, n=2)
        repo, commit = self.repo()
        tar = os.path.join(self.tmp, "src.tar")
        self.git(repo, "archive", "--format=tar", "-o", tar, "HEAD")
        src = os.path.join(self.tmp, "src")
        os.makedirs(src)
        subprocess.run(["tar", "-xf", tar, "-C", src], check=True)
        r = run_tool(os.path.join(src, "records"), self.db, contract_dir(), "--built-from-file", os.path.join(src, "BUILT_FROM"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.rows("SELECT built_from FROM store_info"), [(commit,)])

    def test_12_a_git_checkout_takes_head(self):
        make_set(self.tmp, n=2)
        repo, commit = self.repo()
        r = run_tool(os.path.join(repo, "records"), self.db, contract_dir())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.rows("SELECT built_from FROM store_info"), [(commit,)])

    def test_12_a_checkout_with_the_placeholder_file_takes_head(self):
        """An unsubstituted BUILT_FROM falls back to git's HEAD inside a checkout (a build from a checkout)."""
        make_set(self.tmp, n=2)
        repo, commit = self.repo()
        r = run_tool(os.path.join(repo, "records"), self.db, contract_dir(), "--built-from-file", os.path.join(repo, "BUILT_FROM"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.rows("SELECT built_from FROM store_info"), [(commit,)])

    def test_12_a_copied_tree_with_an_unsubstituted_file_is_refused(self):
        make_set(self.tmp, n=2)
        repo, _ = self.repo()
        copy_ = os.path.join(self.tmp, "copy")
        shutil.copytree(repo, copy_, ignore=shutil.ignore_patterns(".git"))
        r = run_tool(os.path.join(copy_, "records"), self.db, contract_dir(), "--built-from-file", os.path.join(copy_, "BUILT_FROM"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("refused: built-from-unknown:", r.stderr)
        self.assertEqual(os.listdir(self.out), [])
        r = run_tool(os.path.join(copy_, "records"), self.db, contract_dir())
        self.assertIn("refused: built-from-unknown:", r.stderr)
        self.assertEqual(os.listdir(self.out), [])


class MinDomain(Base):
    """--min-domain <domain>=<version>, repeatable: a domain whose info.version is lower is refused by name."""

    def version(self, dom):
        return load(os.path.join(contract_dir(), dom, dom + ".json"))["info"]["version"]

    def test_a_domain_older_than_its_floor_is_refused(self):
        make_set(self.tmp, n=2)
        self.refused("qualification-db.domain-too-old", "qualification", self.version("qualification"), "99.0.0",
                     extra=("--min-domain", "machine=0.0.1", "--min-domain", "qualification=99.0.0"))

    def test_domains_at_or_above_their_floors_build(self):
        make_set(self.tmp, n=2)
        build_ok(self, os.path.join(self.tmp, "records"), self.db, None,
                 "--min-domain", f"qualification={self.version('qualification')}", "--min-domain", "plugin-db=0.0.1")
        self.assertEqual(self.rows("SELECT count(*) FROM record"), [(2,)])

    def test_a_floor_for_a_domain_the_store_does_not_check_is_refused(self):
        make_set(self.tmp, n=2)
        self.refused("contract.domain.absent", "nosuch", extra=("--min-domain", "nosuch=1.0.0"))

    def test_a_floor_that_is_not_a_version_is_refused(self):
        make_set(self.tmp, n=2)
        self.refused("min-domain.invalid", "qualification=latest", extra=("--min-domain", "qualification=latest"))


class Packaging(unittest.TestCase):
    """The package builds the base database beside today's files, with floors only (spec sections 5 and 7)."""
    CONTRACTS = ("plugin-qualify-contract", "plugin-hostd-contract", "plugin-db-contract", "omx-clap-core-contract")

    def read(self, *path):
        with open(os.path.join(REPO, *path), encoding="utf-8") as f:
            return f.read()

    def test_the_source_tarball_carries_its_commit(self):
        self.assertEqual(self.read("BUILT_FROM"), "$Format:%H$\n")
        self.assertIn("BUILT_FROM export-subst", self.read(".gitattributes").splitlines())

    def test_debian_build_depends_hold_floors_only(self):
        control = self.read("debian", "control").split("\n\n")[0].replace("\n ", " ")
        deps = re.search(r"^Build-Depends: (.*)$", control, re.M).group(1)
        self.assertIn("python3-jsonschema:native", deps)
        for pkg in self.CONTRACTS:
            self.assertRegex(deps, rf"{pkg} \(>= \d+(\.\d+)+~\)", pkg)
        self.assertNotRegex(deps, r"\(<|<<|<=")
        self.assertNotRegex(re.sub(r"debhelper-compat \(= 13\)", "", deps), r"\(=")

    def test_rpm_build_requires_hold_floors_only(self):
        spec = self.read("packaging", "plugin-qualification-records.spec")
        self.assertIn("BuildRequires: python3-jsonschema", spec)
        for pkg in self.CONTRACTS:
            self.assertRegex(spec, rf"(?m)^BuildRequires: {pkg} >= \d+(\.\d+)+$", pkg)
        self.assertNotRegex(spec, r"(?m)^BuildRequires:.* (<|<=) ")

    def test_both_builds_generate_the_database_into_the_package(self):
        rules, spec = self.read("debian", "rules"), self.read("packaging", "plugin-qualification-records.spec")
        for text in (rules, spec):
            self.assertIn("tools/records-db.py", text)
            self.assertIn("--built-from-file BUILT_FROM", text)
            self.assertIn("qualification.sqlite", text)
            self.assertIn("variable=contractdir", text)
        self.assertRegex(spec, r"(?m)^echo .*qualification\.sqlite.* >> records\.files")

    def test_the_database_is_generated_not_committed(self):
        tracked = subprocess.run(["git", "-C", REPO, "ls-files", "*.sqlite"], capture_output=True, text=True).stdout
        self.assertEqual(tracked.strip(), "")


class SmallStore(Base):
    def test_14_a_claim_is_tied_to_its_record_and_cell(self):
        make_set(self.tmp, n=3)
        build_ok(self, os.path.join(self.tmp, "records"), self.db)
        with contextlib.closing(sqlite3.connect(self.db, isolation_level=None)) as db:
            db.execute("PRAGMA foreign_keys = ON")
            rid, pid, offer, cls, rate, quantum = db.execute(
                "SELECT record_id, plugin_id, offer, host_class, rate, quantum FROM claim LIMIT 1").fetchone()
            other = db.execute("SELECT plugin_id FROM plugin WHERE plugin_id <> ? LIMIT 1", (pid,)).fetchone()[0]
            bad = {"offer": (rid, pid, "custom" if offer == "default" else "default", cls, rate, quantum),
                   "class": (rid, pid, offer, "rpi5", rate, quantum),
                   "plugin": (rid, other, offer, cls, rate, quantum),
                   "cell": (rid, pid, offer, cls, rate + 1, quantum + 1)}
            for what, row in bad.items():
                with self.assertRaises(sqlite3.IntegrityError, msg=what):
                    db.execute("INSERT INTO claim (record_id, plugin_id, offer, host_class, rate, quantum) "
                               "VALUES (?, ?, ?, ?, ?, ?)", row)

    def test_8_store_info_domains_and_word_checks(self):
        make_set(self.tmp, n=3)
        build_ok(self, os.path.join(self.tmp, "records"), self.db)
        self.assertEqual(self.rows("SELECT user_layer, record_schema, built_from FROM store_info"),
                         [(0, "plugin-qualify.qualification-record/1", COMMIT)])
        self.assertEqual(self.rows("PRAGMA user_version"), [(1,)])
        self.assertEqual(self.rows("PRAGMA page_size"), [(4096,)])
        self.assertEqual(self.rows("PRAGMA journal_mode"), [("delete",)])
        domains = dict(self.rows("SELECT domain, version FROM store_domain"))
        self.assertEqual(sorted(domains), sorted(DOMAIN_REPO))
        for dom, version in domains.items():
            self.assertEqual(version, load(os.path.join(contract_dir(), dom, dom + ".json"))["info"]["version"])
        checked = {(t, c) for t, c in self.rows("SELECT DISTINCT tbl, col FROM word_check")}
        missing = [tc for tc in schema_word_columns() if tc not in checked]
        self.assertEqual(missing, [], "word columns with no word_check row")
        for (d, i) in self.rows("SELECT DISTINCT domain, item FROM word_check"):
            self.assertIn(d, domains)
            self.assertIn(i, load(os.path.join(contract_dir(), d, d + ".json"))["components"]["schemas"])


class RoundTrip(unittest.TestCase):
    """Cases 1 to 3, 7 and 13: the base database of every set of records/, both classes."""

    @classmethod
    def setUpClass(cls):
        contract_dir()
        cls.tmp = tempfile.mkdtemp(prefix="pdq-roundtrip-")
        cls.db_path = os.path.join(cls.tmp, "qualification.sqlite")
        r = run_tool(RECORDS, cls.db_path, contract_dir(), "--built-from-file", write_commit(cls.tmp))
        if r.returncode:
            raise AssertionError(f"records-db.py refused: {r.stderr}")
        sys.path.insert(0, HERE)
        import qualification_db
        cls.q = qualification_db
        cls.db = sqlite3.connect(cls.db_path)
        cls.db.row_factory = sqlite3.Row
        cls.files = [(c, s, f) for c in sorted(os.listdir(RECORDS)) for s in sorted(os.listdir(os.path.join(RECORDS, c)))
                     for f in record_files(c, s)]

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @staticmethod
    def strip(rec):
        rec = copy.deepcopy(rec)
        rec["binary"].pop("unpinnable", None)
        rec["tiers"].pop("dimmed", None)
        for s in rec["run"]["steps"]:
            s.pop("detail", None)
        for c in rec["measurements"]["grid"]:
            c.get("memory", {}).pop("unmeasuredDetail", None)
        for u in rec["measurements"].get("unmeasured", []):
            u.pop("detail", None)
        return rec

    @staticmethod
    def first_difference(a, b, path=""):
        if isinstance(a, dict) and isinstance(b, dict):
            for k in sorted(set(a) | set(b)):
                if k not in a or k not in b:
                    return f"{path}.{k}: only in the {'file' if k in a else 'database'}"
                d = RoundTrip.first_difference(a[k], b[k], f"{path}.{k}")
                if d:
                    return d
            return None
        if isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                return f"{path}: {len(a)} elements in the file, {len(b)} in the database"
            for i, (x, y) in enumerate(zip(a, b)):
                d = RoundTrip.first_difference(x, y, f"{path}[{i}]")
                if d:
                    return d
            return None
        if isinstance(a, bool) != isinstance(b, bool) or a != b:
            return f"{path}: {a!r} in the file, {b!r} in the database"
        return None

    def record_ids(self):
        return {(r["cls"], r["sn"], f"{r['name']}.{r['offer']}.qualification.json"): r["record_id"] for r in self.db.execute(
            "SELECT r.record_id, s.host_class cls, s.name sn, r.name, r.offer FROM record r JOIN record_set s USING (set_id)")}

    def test_01_every_record_comes_back_equal_through_the_database(self):
        ex = self.q.Exporter(self.db)
        ids = self.record_ids()
        self.assertEqual(len(ids), len(self.files))
        for c, s, f in self.files:
            want = self.strip(load(os.path.join(RECORDS, c, s, f)))
            got = ex.export_record(ids[(c, s, f)])
            d = self.first_difference(want, got)
            self.assertIsNone(d, f"{c}/{s}/{f}: {d}")

    def test_01_every_provenance_field_comes_back_equal(self):
        ex = self.q.Exporter(self.db)
        for r in self.db.execute("SELECT set_id, host_class, name FROM record_set"):
            want = load(os.path.join(RECORDS, r["host_class"], r["name"], "provenance.json"))
            for k in PROVENANCE_SENTENCES:
                want.pop(k, None)
            if "settings" in want:
                want["settings"].pop("note", None)
            got = ex.export_set(r["set_id"])
            self.assertIsNone(self.first_difference(want, got), f"{r['host_class']}/{r['name']}")

    def test_01_the_ids_follow_the_byte_order_of_the_paths(self):
        ids = self.record_ids()
        order = sorted(ids, key=lambda k: os.fsencode("/".join(k)))
        self.assertEqual([ids[k] for k in order], list(range(1, len(ids) + 1)))
        sets = [(r["host_class"], r["name"]) for r in self.db.execute("SELECT host_class, name FROM record_set ORDER BY set_id")]
        self.assertEqual(sets, sorted(sets, key=lambda k: os.fsencode("/".join(k))))

    def test_02_counts_are_equal(self):
        per_set = {}
        arrays, tier_objects, plugins, names = {}, {"inProcess": 0, "isolated": 0}, set(), {}
        for c, s, f in self.files:
            rec = load(os.path.join(RECORDS, c, s, f))
            per_set[(c, s)] = per_set.get((c, s), 0) + 1
            plugins.add((rec["plugin"]["format"], rec["binary"]["sha256"], rec["plugin"]["id"]))
            lv, el = leaves(rec)
            for p, n in el.items():
                arrays[p] = arrays.get(p, 0) + n
            for p, n in lv.items():
                if p.endswith(".*"):
                    arrays[p] = arrays.get(p, 0) + n
            for t in tier_objects:
                tier_objects[t] += "host" in rec["tiers"].get(t, {})
        got = {(r["host_class"], r["name"]): r["n"] for r in self.db.execute(
            "SELECT s.host_class, s.name, count(r.record_id) n FROM record_set s LEFT JOIN record r USING (set_id) GROUP BY s.set_id")}
        self.assertEqual(got, per_set, "record rows per set differ from the record files per set")
        self.assertEqual(len(per_set), self.db.execute("SELECT count(*) FROM record_set").fetchone()[0])
        self.assertEqual(len(plugins), self.db.execute("SELECT count(*) FROM plugin").fetchone()[0])
        count = lambda t: self.db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        for path, table in ARRAY_TABLES.items():
            self.assertEqual(count(table), arrays.get(path, 0), f"{path} -> {table}")
        self.assertEqual(count("reason"), arrays["verdicts[].reasons[]"] + arrays["cost[].reasons[]"])
        self.assertEqual(count("reason_param"), arrays["verdicts[].reasons[].params.*"] + arrays["cost[].reasons[].params.*"])
        self.assertEqual(count("adapter_param"), arrays["adapter.params.*"])
        self.assertEqual(count("adapter_cell_param"), arrays["adapter.cells[].params.*"])
        self.assertEqual(count("record_version"), arrays["adapter.versions.*"] + arrays["rejudged.figures.adapter.versions.*"])
        self.assertEqual(count("tier"), sum(tier_objects.values()))
        self.assertEqual(count("claim"), arrays["measurements.grid[]"])

    def test_03_the_package_fields_and_the_absent_fields_read_back_null(self):
        cols = ("pkg_format", "pkg_name", "pkg_version", "pkg_release", "pkg_distro", "pkg_arch")
        n = self.db.execute("SELECT count(*) FROM record WHERE " + " AND ".join(f"{c} IS NULL" for c in cols)).fetchone()[0]
        self.assertEqual(n, len(self.files))
        absent_tested = absent_interposer = 0
        for c, s, f in self.files:
            rec = load(os.path.join(RECORDS, c, s, f))
            absent_tested += "testedVersion" not in rec
            absent_interposer += "interposer" not in rec["tool"]
        self.assertEqual(self.db.execute("SELECT count(*) FROM record WHERE tested_version IS NULL").fetchone()[0], absent_tested)
        self.assertEqual(self.db.execute("SELECT count(*) FROM record WHERE tool_interposer IS NULL").fetchone()[0], absent_interposer)
        self.assertEqual(self.db.execute("SELECT count(*) FROM record WHERE tested_version = '' OR tool_interposer = ''").fetchone()[0], 0)

    def test_07_no_sentence_is_stored(self):
        stored = set()
        for (t,) in self.db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
            for row in self.db.execute(f"SELECT * FROM {t}"):
                stored.update(v for v in tuple(row) if isinstance(v, str))
        sentences = set()
        for c, s, f in self.files:
            rec = load(os.path.join(RECORDS, c, s, f))
            if "unpinnable" in rec["binary"]:
                sentences.add(rec["binary"]["unpinnable"])
            if "dimmed" in rec["tiers"]:
                sentences.add(rec["tiers"]["dimmed"])
            sentences.update(x["detail"] for x in rec["run"]["steps"] if "detail" in x)
            sentences.update(x["detail"] for x in rec["measurements"].get("unmeasured", []))
            sentences.update(x["memory"]["unmeasuredDetail"] for x in rec["measurements"]["grid"]
                             if "unmeasuredDetail" in x.get("memory", {}))
        for c in os.listdir(RECORDS):
            for s in os.listdir(os.path.join(RECORDS, c)):
                prov = load(os.path.join(RECORDS, c, s, "provenance.json"))
                for k in PROVENANCE_SENTENCES:
                    v = prov.get(k)
                    sentences.update([v] if isinstance(v, str) else (v or {}).values() if isinstance(v, dict) else [])
                if "note" in prov.get("settings", {}):
                    sentences.add(prov["settings"]["note"])
        self.assertGreater(len(sentences), 50)
        self.assertEqual(sorted(x for x in sentences & stored)[:3], [], "a sentence is stored in a column")

    def test_13_the_hand_written_field_table_agrees_with_the_columns(self):
        """Every path of field-columns.tsv, read from the JSON and from the column with this test's own SQL."""
        lines = []
        with open(TSV, encoding="utf-8") as f:
            for l in f:
                if l.strip() and not l.startswith("#"):
                    parts = l.rstrip("\n").split("\t")
                    lines.append((parts[0], *parts[1].split("."), parts[2] if len(parts) > 2 else ""))
        self.assertGreater(len(lines), 150)
        queries = []
        for path, table, col, mode in lines:
            if path.startswith("P:"):
                self.check_provenance_line(path[2:], table, col)
                continue
            n = path.count("[]")
            if table == "plugin":
                sql = f"SELECT r.record_id, p.{col} FROM record r JOIN plugin p USING (plugin_id)"
            elif table == "record":
                sql = f"SELECT record_id, {col} FROM record"
            elif table == "tier":
                sql = f"SELECT record_id, {col} FROM tier WHERE tier = '{path.split('.')[1]}'"
            elif table == "reason":
                parent = "verdict_ord" if path.startswith("verdicts") else "cost_ord"
                sql = f"SELECT record_id, {parent}, ord, {col} FROM reason WHERE {parent} IS NOT NULL"
            elif table == "cell_event":
                sql = f"SELECT record_id, cell_ord, ord, {col} FROM cell_event"
            else:
                sql = f"SELECT record_id, ord, {col} FROM {table}"
            queries.append((path, table, col, mode, {tuple(r[:-1]): r[-1] for r in self.db.execute(sql)}, [0]))
        for (c, s, f), rid in self.record_ids().items():
            rec = load(os.path.join(RECORDS, c, s, f))
            for path, table, col, mode, sqlvals, seen in queries:
                for idx, value in json_values(rec, path):
                    seen[0] += 1
                    want = expected_column(rec, value, mode)
                    got = sqlvals.get((rid,) + idx)
                    self.assertTrue(want == got, f"{c}/{s}/{f}: {path}{list(idx)} is {want!r} in the file, "
                                                 f"{table}.{col} holds {got!r}")
        for path, table, col, mode, sqlvals, seen in queries:
            self.assertGreater(seen[0], 0, f"{path}: no record holds it")
            self.assertGreaterEqual(seen[0], len([v for v in sqlvals.values() if v is not None]), f"{path}: rows without a field")

    def check_provenance_line(self, jpath, table, col):
        for r in self.db.execute(f"SELECT host_class, name, {col} v FROM record_set"):
            prov = load(os.path.join(RECORDS, r["host_class"], r["name"], "provenance.json"))
            v = prov
            for k in jpath.split("."):
                v = v[k]
            self.assertEqual(v, r["v"], f"{r['host_class']}/{r['name']}: {jpath} -> {table}.{col}")


ABSENT = object()


def json_values(rec, path):
    """[(index tuple, value or ABSENT)] of a path of the table: `[]` walks each element. A missing parent object gives
    ABSENT when no array is left to walk, and nothing otherwise."""
    segs = path.split(".")
    out = []

    def walk(v, i, idx):
        if i == len(segs):
            out.append((idx, v))
            return
        seg = segs[i]
        if seg.endswith("[]"):
            key = seg[:-2]
            arr = v.get(key) if isinstance(v, dict) else None
            if arr is None:
                return
            for k, el in enumerate(arr):
                if i + 1 == len(segs):
                    out.append((idx + (k,), el))
                else:
                    walk(el, i + 1, idx + (k,))
            return
        if not isinstance(v, dict) or seg not in v:
            if not any(s.endswith("[]") for s in segs[i + 1:]) and not seg.endswith("[]"):
                out.append((idx, ABSENT))
            return
        walk(v[seg], i + 1, idx)

    walk(rec, 0, ())
    return out


def expected_column(rec, value, mode):
    if mode == "present":
        return None if value is ABSENT else 1
    if mode == "presence":
        return 0 if value is ABSENT else 1
    if mode == "presence:adapter":
        return None if "adapter" not in rec else (0 if value is ABSENT else 1)
    if value is ABSENT:
        return None
    if isinstance(value, bool):
        return int(value)
    return value


if __name__ == "__main__":
    unittest.main()
