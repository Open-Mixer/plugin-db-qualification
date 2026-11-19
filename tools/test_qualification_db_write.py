#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The writer of a layer (this repository's qualification store spec, section 6.1): `put` and `delete` of
tools/qualification_db.py into the user or the system layer file, and every refusal by its exact name.

    PDQ_SIBLINGS=<dir of the clones> python3 -m unittest tools/test_qualification_db_write.py

The words come from the owners' contract documents, assembled by tools/test_records_db.py (TEST ONLY: PDQ_SIBLINGS).
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
sys.path.insert(0, HERE)
import test_records_db as T  # noqa: E402
import qualification_db as q  # noqa: E402

LV2 = ("rpi5", "zynthian-vangelis")


def first_record(src=T.SRC_SET, predicate=None, offer=None):
    """(record, offer, host class) of the first record of a real set; its paths already in the section 3.7 form."""
    tmp = tempfile.mkdtemp(prefix="pdq-fixture-")
    try:
        f = T.find(predicate or (lambda r, n: True), src)
        d = T.make_set(tmp, [f], src=src)
        rec = T.load(os.path.join(d, f))
        return rec, f.rsplit(".", 3)[-3], src[0]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class Layer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pdq-layer-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = os.path.join(self.tmp, "qualification")
        self.db = os.path.join(self.root, "qualification.sqlite")
        self.rec, self.offer, self.cls = first_record(
            LV2, lambda r, n: r["plugin"]["format"] == "clap" and len(r["measurements"]["grid"]) > 1)

    def put(self, rec=None, scope="user", offer=None, cls=None, root=None):
        return q.put(rec if rec is not None else self.rec, scope=scope, offer=offer or self.offer, host_class=cls or self.cls,
                     contract_dir=T.contract_dir(), root=root or self.root)

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
        want = copy.deepcopy(self.rec)
        want["binary"].pop("unpinnable", None)
        want["tiers"].pop("dimmed", None)
        for s in want["run"]["steps"]:
            s.pop("detail", None)
        for c in want["measurements"]["grid"]:
            c.get("memory", {}).pop("unmeasuredDetail", None)
        for u in want["measurements"].get("unmeasured", []):
            u.pop("detail", None)
        self.assertIsNone(T.RoundTrip.first_difference(want, got))

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
        rec, offer, cls = first_record(LV2, lambda r, n: r["plugin"]["format"] == "lv2" and len(r["binary"]["files"]) > 2
                            and r["binary"]["files"][0]["path"] != r["binary"]["path"])
        first = rec["binary"]["files"][0]
        self.assertNotEqual(first["path"], rec["binary"]["path"])
        rec["binary"]["sha256"] = first["sha256"]
        with self.assertRaises(q.Refusal) as cm:
            q.put(rec, scope="user", offer=offer, host_class=cls, contract_dir=T.contract_dir(), root=self.root)
        self.assertEqual(cm.exception.name, "key-not-the-binary")

    def lv2(self):
        return first_record(LV2, lambda r, n: r["plugin"]["format"] == "lv2" and len(r["binary"]["files"]) > 2
                            and r["binary"]["files"][0]["path"] != r["binary"]["path"])

    def put_lv2(self, rec, offer, cls):
        with self.assertRaises(q.Refusal) as cm:
            q.put(rec, scope="user", offer=offer, host_class=cls, contract_dir=T.contract_dir(), root=self.root)
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


COMMAND = os.path.join(HERE, "plugin-qualification-db-write")


class Command(Layer):
    """Section 6.1's command: put reads one record on standard input; refusals are named on standard error, exit 1."""

    def run_cmd(self, *args, stdin=""):
        cmd = [sys.executable, "-B", COMMAND, *args]
        return subprocess.run(cmd, input=stdin, capture_output=True, text=True)

    def put_cmd(self, rec=None, *extra, offer=None, cls=None, scope="user"):
        return self.run_cmd("put", "--scope", scope, "--offer", offer or self.offer, "--host-class", cls or self.cls,
                            "--root", self.root, "--contract-dir", T.contract_dir(), *extra,
                            stdin=json.dumps(rec if rec is not None else self.rec))

    def key_args(self, **kw):
        k = dict(sha256=self.rec["binary"]["sha256"], format=self.rec["plugin"]["format"], uri=self.rec["plugin"]["id"],
                 offer=self.offer, host_class=self.cls)
        k.update(kw)
        return ["--sha256", k["sha256"], "--format", k["format"], "--uri", k["uri"], "--offer", k["offer"],
                "--host-class", k["host_class"]]

    def test_the_command_exists_and_is_executable(self):
        self.assertTrue(os.access(COMMAND, os.X_OK), COMMAND)

    def test_put_writes_the_record_and_prints_nothing(self):
        r = self.put_cmd()
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertEqual(self.rows("SELECT offer, host_class FROM record"), [(self.offer, self.cls)])

    def test_the_system_scope(self):
        r = self.put_cmd(scope="system")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(self.db))

    def test_delete_removes_the_record(self):
        self.assertEqual(self.put_cmd().returncode, 0)
        r = self.run_cmd("delete", "--scope", "user", "--root", self.root, *self.key_args())
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertEqual(self.rows("SELECT count(*) FROM record"), [(0,)])

    def test_delete_of_a_key_the_layer_lacks_exits_0(self):
        self.assertEqual(self.put_cmd().returncode, 0)
        r = self.run_cmd("delete", "--scope", "user", "--root", self.root, *self.key_args(host_class="x86-64"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.rows("SELECT count(*) FROM record"), [(1,)])

    def test_every_refusal_is_named_on_standard_error_with_exit_1_and_writes_nothing(self):
        lv2, loffer, lcls = first_record(LV2, lambda r, n: r["plugin"]["format"] == "lv2" and len(r["binary"]["files"]) > 2
                                         and r["binary"]["files"][0]["path"] != r["binary"]["path"])
        swapped = copy.deepcopy(lv2)
        swapped["binary"]["files"][0], swapped["binary"]["files"][1] = swapped["binary"]["files"][1], swapped["binary"]["files"][0]
        twice = copy.deepcopy(lv2)
        twice["binary"]["files"].insert(1, dict(twice["binary"]["files"][0]))
        cases = {
            "path-absolute": (self.edited(lambda r: r["binary"].update(path="/usr/lib/clap/" + r["binary"]["path"])), {}),
            "binary-not-in-files": (self.edited(lambda r: r["binary"].update(path="Other.clap")), {}),
            "key-not-the-binary": (self.edited(lambda r: r["binary"].update(sha256="0" * 64)), {}),
            "files-unordered": (swapped, {"offer": loffer, "cls": lcls}),
            "files-duplicate": (twice, {"offer": loffer, "cls": lcls}),
            "files-empty": (self.edited(lambda r: r["binary"].update(files=[])), {}),
            "word-unknown": (self.edited(lambda r: r["verdicts"][0].update(rating="excellent")), {}),
            "field-unmapped": (self.edited(lambda r: r["verdicts"][0].update(mood="calm")), {}),
            "schema-refused": (self.edited(lambda r: (r["binary"].update(path="../" + r["binary"]["path"]),
                                                      r["binary"]["files"][0].update(path="../" + r["binary"]["path"]))), {}),
        }
        for name, (rec, kw) in cases.items():
            with self.subTest(name):
                r = self.put_cmd(rec, **kw)
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertEqual(r.stdout, "")
                self.assertTrue(r.stderr.startswith(f"plugin-qualification-db-write: refused: {name}: "), r.stderr)
                self.assertFalse(os.path.exists(self.db), "a refusal created the layer")

    def test_a_word_of_the_command_line_is_checked(self):
        r = self.put_cmd(offer="gold")
        self.assertEqual(r.returncode, 1)
        self.assertIn("refused: word-unknown:", r.stderr)

    def test_standard_input_that_is_no_json_is_refused(self):
        r = self.run_cmd("put", "--scope", "user", "--offer", self.offer, "--host-class", self.cls, "--root", self.root,
                         "--contract-dir", T.contract_dir(), stdin="{not json")
        self.assertEqual(r.returncode, 1)
        self.assertIn("refused: file-unreadable:", r.stderr)

    def test_an_absent_contract_directory_is_refused(self):
        r = self.run_cmd("put", "--scope", "user", "--offer", self.offer, "--host-class", self.cls, "--root", self.root,
                         "--contract-dir", os.path.join(self.tmp, "nope"), stdin=json.dumps(self.rec))
        self.assertEqual(r.returncode, 1)
        self.assertIn("refused: contract.dir.absent:", r.stderr)

    def test_a_scope_that_is_none_is_a_usage_error(self):
        r = self.run_cmd("put", "--scope", "world", "--offer", "default", "--host-class", "x86-64")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.run_cmd().returncode, 2)

    def test_delete_with_a_missing_flag_is_a_usage_error(self):
        r = self.run_cmd("delete", "--scope", "user", "--sha256", "0" * 64)
        self.assertEqual(r.returncode, 2)


class Version(unittest.TestCase):
    def test_the_writer_and_the_reader_name_one_version(self):
        with open(q.HEADER, encoding="utf-8") as f:
            self.assertIn(f"#define PQDB_SCHEMA_VERSION {q.schema_version()}\n", f.read())


if __name__ == "__main__":
    unittest.main()
