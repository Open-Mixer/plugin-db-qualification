#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The writer of a layer (this repository's qualification store spec, section 6.1): `put` and `delete` of
tools/qualification_db.py into the user or the system layer file, the command plugin-qualification-db-write, and every
refusal by its exact name.

    PDQ_SIBLINGS=<dir of the clones> python3 -m unittest tools/test_qualification_db_write.py

The words come from the owners' contract documents. The test assembles a contract directory from the sibling clones
(TEST ONLY, the writer reads no variable for it): PDQ_SIBLINGS names the directory that holds the clones
(plugin-qualify, plugin-hostd, plugin-db, omx-clap-core); each domain is read from `contract.d/<domain>/` at PDQ_REF
(default origin/main), the hosting domain at PDQ_HOSTING_REF. Without PDQ_SIBLINGS the tests that need the words are
skipped, saying so. The fixture records are records of records/, in the section 3.7 form the rewrite of records/ gives
them (a CLAP record's relative binary.path and its hostExtensions).
"""
import contextlib
import copy
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qualification_db as q  # noqa: E402

RECORDS = os.path.join(REPO, "records")
HEADER = os.path.join(REPO, "include", "plugin-qualification-db", "pqdb.h")
DOMAIN_REPO = {"qualification": "plugin-qualify", "machine": "plugin-hostd", "probe": "plugin-hostd",
               "plugin-db": "plugin-db", "hosting": "omx-clap-core"}
SIBLINGS = os.environ.get("PDQ_SIBLINGS")  # TEST ONLY
REF = os.environ.get("PDQ_REF", "origin/main")
HOSTING_REF = os.environ.get("PDQ_HOSTING_REF", "origin/lane/omx-clap-core-hosting-domain")
X86 = ("x86-64", "fedora44-48000-512")
LV2 = ("rpi5", "zynthian-vangelis")
_contract = {}


def contract_dir():
    """The contract directory assembled from the sibling clones, once; skips the test when they are not given."""
    if "dir" in _contract:
        return _contract["dir"]
    if not SIBLINGS:
        raise unittest.SkipTest("PDQ_SIBLINGS is not set: no sibling clones to read the owners' words from")
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


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def first_difference(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path}.{k}: only in the {'record' if k in a else 'database'}"
            d = first_difference(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return f"{path}: {len(a)} elements in the record, {len(b)} in the database"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_difference(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    if isinstance(a, bool) != isinstance(b, bool) or a != b:
        return f"{path}: {a!r} in the record, {b!r} in the database"
    return None


def without_sentences(rec):
    """The record as the database gives it back: its sentences are not stored (section 3.5)."""
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


def first_record(src=X86, predicate=lambda r: True):
    """(record, offer, host class) of the first record of a real set that satisfies the predicate, in the form of section
    3.7: a CLAP record's binary.path is its file's own name and its hostExtensions are the probe output's list (a
    crashed or timed-out probe offered none, and the record gets none)."""
    cls, set_ = src
    d = os.path.join(RECORDS, cls, set_)
    for f in sorted(os.listdir(d), key=os.fsencode):
        if not f.endswith(".qualification.json"):
            continue
        rec = load(os.path.join(d, f))
        if rec["plugin"]["format"] == "clap":
            rec["binary"]["path"] = rec["binary"]["files"][0]["path"]
            offer = load(os.path.join(d, rec["probe"]["file"]))["offer"]
            rec.pop("hostExtensions", None)
            if "clapExtensions" in offer:
                rec["hostExtensions"] = offer["clapExtensions"]
        if predicate(rec):
            return rec, f.rsplit(".", 3)[-3], cls
    raise AssertionError(f"no record of {src} satisfies the predicate")


class Layer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pdq-layer-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = os.path.join(self.tmp, "qualification")
        self.db = os.path.join(self.root, "qualification.sqlite")
        self.rec, self.offer, self.cls = first_record(
            LV2, lambda r: r["plugin"]["format"] == "clap" and len(r["measurements"]["grid"]) > 1)

    def put(self, rec=None, scope="user", offer=None, cls=None, root=None):
        return q.put(rec if rec is not None else self.rec, scope=scope, offer=offer or self.offer, host_class=cls or self.cls,
                     contract_dir=contract_dir(), root=root or self.root)

    def rows(self, sql, *args):
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            return db.execute(sql, args).fetchall()

    def refused(self, name, *words, rec=None):
        with self.assertRaises(q.Refusal) as cm:
            self.put(rec)
        self.assertEqual(cm.exception.name, name, str(cm.exception))
        for w in words:
            self.assertIn(w, str(cm.exception))
        self.assertFalse(os.path.exists(self.db), "a refusal created the layer")

    def edited(self, fn, rec=None):
        r = copy.deepcopy(rec or self.rec)
        fn(r)
        return r

    def other_offer(self):
        """The record and the word of the other offer: the probe file's name carries the offer."""
        other = "custom" if self.offer == "default" else "default"
        return self.edited(lambda r: r["probe"].update(file=r["probe"]["file"].replace(f".{self.offer}.", f".{other}."))), other

    def export(self):
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            return q.Exporter(db).export_record(1)


class Columns(Layer):
    """Case 24: the columns of the row judge (record_extension, record.host_extensions, cell.rt_own_threads and
    rt_other_*) are written and read back, and the DDL's own checks hold."""

    def named(self, rec):
        return f"{rec['probe']['file'][: -len('.' + self.offer + '.probe.json')]}"

    def put_back(self, rec):
        self.put(rec)
        got = self.export()
        self.assertIsNone(first_difference(without_sentences(rec), got))
        return got

    def test_24_host_extensions_of_a_clap_record_round_trip(self):
        rec = self.edited(lambda r: r.update(hostExtensions=["clap.log", "clap.params"]))
        self.assertEqual(self.put_back(rec)["hostExtensions"], ["clap.log", "clap.params"])
        self.assertEqual(self.rows("SELECT host_extensions FROM record"), [(1,)])
        self.assertEqual(self.rows("SELECT ord, extension FROM record_extension ORDER BY ord"),
                         [(0, "clap.log"), (1, "clap.params")])

    def test_24_an_empty_list_of_host_extensions_is_data(self):
        self.assertEqual(self.put_back(self.edited(lambda r: r.update(hostExtensions=[])))["hostExtensions"], [])
        self.assertEqual(self.rows("SELECT host_extensions FROM record"), [(1,)])
        self.assertEqual(self.rows("SELECT count(*) FROM record_extension"), [(0,)])

    def test_24_a_clap_record_without_the_list_is_stored_without_it(self):
        """A probe that crashed or timed out offered no list (254 records of records/): nothing is guessed, the column
        stays NULL, and the row judge owes figures-unreadable (section 6.2)."""
        self.assertNotIn("hostExtensions", self.put_back(self.edited(lambda r: r.pop("hostExtensions", None))))
        self.assertEqual(self.rows("SELECT host_extensions FROM record"), [(None,)])

    def test_24_an_lv2_record_has_none(self):
        rec, offer, cls = first_record(LV2, lambda r: r["plugin"]["format"] == "lv2")
        self.put(rec, offer=offer, cls=cls)
        self.assertEqual(self.rows("SELECT host_extensions FROM record"), [(None,)])
        self.assertNotIn("hostExtensions", self.export())

    def test_24_an_lv2_record_with_host_extensions_is_refused(self):
        rec, offer, cls = first_record(LV2, lambda r: r["plugin"]["format"] == "lv2")
        rec["hostExtensions"] = ["clap.log"]
        with self.assertRaises(q.Refusal) as cm:
            self.put(rec, offer=offer, cls=cls)
        self.assertEqual(cm.exception.name, "field-unmapped")
        self.assertIn("hostExtensions", str(cm.exception))

    def test_24_own_threads_and_other_threads_round_trip(self):
        def put(r):
            rt = r["measurements"]["grid"][0]["rtSafety"]
            rt["ownThreads"] = 2
            rt["otherThreads"] = {"allocationsInRun": 5, "locksInRun": 0, "syscallsInRun": 7}
        got = self.put_back(self.edited(put))
        rt = got["measurements"]["grid"][0]["rtSafety"]
        self.assertEqual((rt["ownThreads"], rt["otherThreads"]), (2, {"allocationsInRun": 5, "locksInRun": 0, "syscallsInRun": 7}))
        self.assertEqual(self.rows("SELECT rt_own_threads, rt_other_allocations, rt_other_locks, rt_other_syscalls FROM cell "
                                   "WHERE rt_own_threads IS NOT NULL"), [(2, 5, 0, 7)])

    def test_24_records_of_today_hold_none(self):
        got = self.put_back(self.rec)
        for c in got["measurements"]["grid"]:
            self.assertNotIn("ownThreads", c.get("rtSafety", {}))
            self.assertNotIn("otherThreads", c.get("rtSafety", {}))
        self.assertEqual(self.rows("SELECT count(*) FROM cell WHERE rt_own_threads IS NOT NULL OR rt_other_locks IS NOT NULL"), [(0,)])

    def test_24_other_threads_with_one_count_only_is_refused_by_the_schema(self):
        def put(r):
            r["measurements"]["grid"][0]["rtSafety"]["otherThreads"] = {"locksInRun": 1}
        self.refused("schema-refused", rec=self.edited(put))


class Put(Layer):
    def test_a_missing_layer_is_created_from_the_ddl_and_holds_the_record(self):
        self.put()
        self.assertEqual(self.rows("PRAGMA user_version"), [(q.schema_version(),)])
        self.assertEqual(self.rows("SELECT user_layer, record_schema, built_from FROM store_info"),
                         [(1, q.RECORD_SCHEMA, None)])
        self.assertEqual(self.rows("SELECT set_id, host_class, offer FROM record"), [(None, self.cls, self.offer)])
        self.assertEqual(self.rows("SELECT count(*) FROM record_set"), [(0,)])
        self.assertEqual(sorted(d for (d,) in self.rows("SELECT domain FROM store_domain")), sorted(q.DOMAINS))
        self.assertGreater(self.rows("SELECT count(*) FROM word_check")[0][0], 50)

    def test_the_record_reads_back_equal(self):
        self.put()
        got = self.export()
        want = without_sentences(self.rec)
        self.assertIsNone(first_difference(want, got))

    def test_the_name_comes_from_the_probe_file_and_the_offer(self):
        self.put()
        stem = self.rec["probe"]["file"][: -len(f".{self.offer}.probe.json")]
        self.assertEqual(self.rows("SELECT name FROM record"), [(stem,)])

    def test_a_second_put_of_the_same_shadow_key_replaces_the_whole_record(self):
        self.put()
        cells = len(self.rec["measurements"]["grid"])
        again = self.edited(lambda r: r["measurements"].update(grid=r["measurements"]["grid"][:1]))
        self.assertGreater(cells, 1)
        self.put(again)
        self.assertEqual(self.rows("SELECT count(*) FROM record"), [(1,)])
        self.assertEqual(self.rows("SELECT count(*) FROM cell"), [(1,)])
        self.assertEqual(self.rows("SELECT count(*) FROM claim"), [(1,)])
        # the rows of a fresh layer with the second record alone are the rows of the replaced one
        fresh = os.path.join(self.tmp, "fresh")
        self.put(again, root=fresh)
        with contextlib.closing(sqlite3.connect(self.db)) as a, contextlib.closing(sqlite3.connect(os.path.join(fresh, "qualification.sqlite"))) as b:
            self.assertEqual(sorted(a.iterdump()), sorted(b.iterdump()))

    def test_another_offer_or_class_is_another_shadow_key(self):
        self.put()
        rec, other = self.other_offer()
        self.put(rec, offer=other)
        self.put(cls="x86-64")
        self.assertEqual(self.rows("SELECT count(*) FROM record"), [(3,)])
        self.assertEqual(self.rows("SELECT count(*) FROM plugin"), [(1,)])

    def test_the_system_scope_has_its_own_root(self):
        self.put(scope="system", root=os.path.join(self.tmp, "system"))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "system", "qualification.sqlite")))
        self.assertFalse(os.path.exists(self.db))

    def test_the_layer_places_are_the_spec_ones(self):
        self.assertEqual(q.layer_path("system"), "/var/lib/omx/qualification/qualification.sqlite")
        self.assertTrue(q.layer_path("user").endswith("/.local/share/omx/qualification/qualification.sqlite"))
        self.assertEqual(q.layer_path("user", "/x"), "/x/qualification.sqlite")

    def test_a_layer_of_another_version_is_refused(self):
        self.put()
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            db.execute("PRAGMA user_version = 2")
        with self.assertRaises(q.Refusal) as cm:
            self.put()
        self.assertEqual(cm.exception.name, "schema-other")


class Refusals(Layer):
    """Every refusal by its exact name, naming the path, and nothing written."""

    def test_path_absolute(self):
        rec = self.edited(lambda r: r["binary"].update(path="/usr/lib/clap/" + r["binary"]["path"]))
        self.refused("path-absolute", "binary.path", "/usr/lib/clap/", rec=rec)

    def test_binary_not_in_files(self):
        rec = self.edited(lambda r: r["binary"].update(path="Other.clap"))
        self.refused("binary-not-in-files", "binary.path", "Other.clap", rec=rec)

    def test_key_not_the_binary(self):
        """Ruling 10: the key's SHA-256 is the binary entry's own."""
        rec = self.edited(lambda r: r["binary"].update(sha256="0" * 64))
        self.refused("key-not-the-binary", "binary.sha256", rec=rec)

    def test_key_not_the_binary_for_an_lv2_key_taken_from_the_first_entry(self):
        rec, offer, cls = first_record(LV2, lambda r: r["plugin"]["format"] == "lv2" and len(r["binary"]["files"]) > 2
                            and r["binary"]["files"][0]["path"] != r["binary"]["path"])
        first = rec["binary"]["files"][0]
        self.assertNotEqual(first["path"], rec["binary"]["path"])
        rec["binary"]["sha256"] = first["sha256"]
        with self.assertRaises(q.Refusal) as cm:
            q.put(rec, scope="user", offer=offer, host_class=cls, contract_dir=contract_dir(), root=self.root)
        self.assertEqual(cm.exception.name, "key-not-the-binary")

    def lv2(self):
        return first_record(LV2, lambda r: r["plugin"]["format"] == "lv2" and len(r["binary"]["files"]) > 2
                            and r["binary"]["files"][0]["path"] != r["binary"]["path"])

    def put_lv2(self, rec, offer, cls):
        with self.assertRaises(q.Refusal) as cm:
            q.put(rec, scope="user", offer=offer, host_class=cls, contract_dir=contract_dir(), root=self.root)
        self.assertFalse(os.path.exists(self.db))
        return cm.exception

    def test_files_unordered(self):
        rec, offer, cls = self.lv2()
        rec["binary"]["files"][0], rec["binary"]["files"][1] = rec["binary"]["files"][1], rec["binary"]["files"][0]
        e = self.put_lv2(rec, offer, cls)
        self.assertEqual(e.name, "files-unordered")
        self.assertIn("binary.files[1].path", str(e))

    def test_files_are_compared_as_bytes_and_not_by_locale(self):
        """`Z.so` sorts before `a.so`: the order is UTF-8 bytes."""
        rec = self.edited(lambda r: r["binary"].update(files=[
            {"path": "a.so", "sha256": r["binary"]["sha256"]}, {"path": "Z.so", "sha256": "1" * 64}]))
        self.refused("files-unordered", "Z.so", rec=rec)

    def test_files_duplicate(self):
        rec, offer, cls = self.lv2()
        rec["binary"]["files"].insert(1, dict(rec["binary"]["files"][0]))
        e = self.put_lv2(rec, offer, cls)
        self.assertEqual(e.name, "files-duplicate")
        self.assertIn(rec["binary"]["files"][0]["path"], str(e))

    def test_files_empty(self):
        rec = self.edited(lambda r: r["binary"].update(files=[]))
        self.refused("files-empty", "binary.files", rec=rec)

    def test_a_dot_dot_segment_is_refused_by_the_schema(self):
        def f(r):
            r["binary"]["path"] = "../" + r["binary"]["path"]
            r["binary"]["files"][0]["path"] = r["binary"]["path"]
        self.refused("schema-refused", rec=self.edited(f))

    def test_word_unknown(self):
        rec = self.edited(lambda r: r["verdicts"][0].update(rating="excellent"))
        self.refused("word-unknown", "verdicts[0].rating", "excellent", rec=rec)

    def test_a_word_of_the_call_is_checked_too(self):
        with self.assertRaises(q.Refusal) as cm:
            self.put(offer="gold")
        self.assertEqual(cm.exception.name, "word-unknown")
        self.assertIn("gold", str(cm.exception))
        with self.assertRaises(q.Refusal) as cm:
            self.put(cls="z80")
        self.assertEqual(cm.exception.name, "word-unknown")
        self.assertFalse(os.path.exists(self.db))

    def test_field_unmapped(self):
        rec = self.edited(lambda r: r["verdicts"][0].update(mood="calm"))
        self.refused("field-unmapped", "verdicts[0].mood", rec=rec)

    def test_a_probe_file_that_is_not_the_offers_is_refused(self):
        rec = self.edited(lambda r: r["probe"].update(file="x.json"))
        self.refused("file-name", "probe.file", rec=rec)

    def test_a_refusal_leaves_an_existing_layer_as_it_was(self):
        self.put()
        before = open(self.db, "rb").read()
        with self.assertRaises(q.Refusal):
            self.put(self.edited(lambda r: r["binary"].update(sha256="0" * 64)))
        self.assertEqual(open(self.db, "rb").read(), before)


class Delete(Layer):
    def key(self, **kw):
        k = dict(sha256=self.rec["binary"]["sha256"], format=self.rec["plugin"]["format"], uri=self.rec["plugin"]["id"],
                 offer=self.offer, host_class=self.cls)
        k.update(kw)
        return k

    def test_delete_removes_the_record_and_its_rows(self):
        self.put()
        q.delete(scope="user", root=self.root, **self.key())
        for t in ("record", "plugin", "cell", "claim", "verdict", "record_file", "record_extension"):
            self.assertEqual(self.rows(f"SELECT count(*) FROM {t}"), [(0,)], t)

    def test_delete_keeps_the_other_offer(self):
        self.put()
        rec, other = self.other_offer()
        self.put(rec, offer=other)
        q.delete(scope="user", root=self.root, **self.key())
        self.assertEqual(self.rows("SELECT offer FROM record"), [(other,)])
        self.assertEqual(self.rows("SELECT count(*) FROM plugin"), [(1,)])

    def test_a_key_the_layer_does_not_hold_is_not_an_error(self):
        self.put()
        q.delete(scope="user", root=self.root, **self.key(offer="custom" if self.offer == "default" else "default"))
        self.assertEqual(self.rows("SELECT count(*) FROM record"), [(1,)])

    def test_delete_in_a_missing_layer_is_not_an_error_and_creates_nothing(self):
        q.delete(scope="user", root=self.root, **self.key())
        self.assertFalse(os.path.exists(self.root))

    def test_a_sha256_that_is_not_one_is_refused(self):
        with self.assertRaises(q.Refusal) as cm:
            q.delete(scope="user", root=self.root, **self.key(sha256="abc"))
        self.assertEqual(cm.exception.name, "field-type")


class Version(unittest.TestCase):
    def test_the_writer_and_the_reader_name_one_version(self):
        with open(HEADER, encoding="utf-8") as f:
            self.assertIn(f"#define PQDB_SCHEMA_VERSION {q.schema_version()}\n", f.read())


if __name__ == "__main__":
    unittest.main()
