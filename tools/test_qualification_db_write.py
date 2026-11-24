#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The writer of a layer (this repository's qualification store spec, section 6.1): `put` and `delete` of
tools/qualification_db.py into the user or the system layer file, the command plugin-qualification-db-write, and every
refusal by its exact name.

    PDQ_SIBLINGS=<dir of the clones> python3 -m unittest tools/test_qualification_db_write.py

The words come from the owners' contract documents. The test assembles a contract directory from the sibling clones
(TEST ONLY, the writer reads no variable for it): PDQ_SIBLINGS names the directory that holds the clones
(plugin-hostd, plugin-hostd-protocol, plugin-db, omx-clap-core); each domain is read from `contract.d/<domain>/` at PDQ_REF
(default origin/main); the hosting words come from the data/ of omx-clap-core at the same ref, laid out as its
`make install-contract` lays them out (<contractdir>/3/<package>/ and its MANIFEST.json, <package> the name that tree
installs under: omx-clap since 0.34.0); tools/sibling_contract.py assembles it. Without PDQ_SIBLINGS the tests that need the words are
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
from sibling_contract import contract_dir, hosting_dir, hosting_package, remove  # noqa: E402

RECORDS = os.path.join(REPO, "records")
HEADER = os.path.join(REPO, "include", "plugin-qualification-db", "pqdb.h")
X86 = ("x86-64", "fedora44-48000-512")
LV2 = ("rpi5", "zynthian-vangelis")


def tearDownModule():
    remove()


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
            rt["otherThreads"] = {"allocations": 5, "locks": 0, "syscalls": 7}
        got = self.put_back(self.edited(put))
        rt = got["measurements"]["grid"][0]["rtSafety"]
        self.assertEqual((rt["ownThreads"], rt["otherThreads"]), (2, {"allocations": 5, "locks": 0, "syscalls": 7}))
        self.assertEqual(self.rows("SELECT rt_own_threads, rt_other_allocations, rt_other_locks, rt_other_syscalls FROM cell "
                                   "WHERE rt_own_threads IS NOT NULL"), [(2, 5, 0, 7)])

    def test_24_other_threads_with_the_inrun_names_is_refused_by_name(self):
        """The record format has no such fields (plugin-qualify spreads the probe point's names): not an alias."""
        def put(r):
            r["measurements"]["grid"][0]["rtSafety"]["otherThreads"] = {"allocationsInRun": 5, "locksInRun": 0, "syscallsInRun": 7}
        with self.assertRaises(q.Refusal) as cm:
            self.put(self.edited(put))
        self.assertEqual(cm.exception.name, "field-unmapped")
        self.assertIn("otherThreads.allocationsInRun", str(cm.exception))

    def test_24_records_of_today_hold_none(self):
        got = self.put_back(self.rec)
        for c in got["measurements"]["grid"]:
            self.assertNotIn("ownThreads", c.get("rtSafety", {}))
            self.assertNotIn("otherThreads", c.get("rtSafety", {}))
        self.assertEqual(self.rows("SELECT count(*) FROM cell WHERE rt_own_threads IS NOT NULL OR rt_other_locks IS NOT NULL"), [(0,)])

    def test_24_other_threads_with_one_count_only_is_refused_by_the_schema(self):
        def put(r):
            r["measurements"]["grid"][0]["rtSafety"]["otherThreads"] = {"locks": 1}
        self.refused("schema-refused", rec=self.edited(put))


class LatencyAndRules(Layer):
    """Latency and rules (spec section 3.5): latencyLineMs, rules and a cell's latencyMs, NULL when absent, and the
    adapter's hosts (QUALIFICATION_ADAPTER_HOSTS), not the judge's profiles."""

    def with_fields(self, r):
        r["latencyLineMs"] = 12.5
        r["rules"] = "plugin-qualify-rules/1.2"
        for i, c in enumerate(r["measurements"]["grid"]):
            c["latencyMs"] = [5.333333333333333, 10.666666666666666, 3][i % 3]

    def test_the_three_fields_are_stored_and_exported_as_written(self):
        rec = self.edited(self.with_fields)
        self.put(rec)
        self.assertEqual(self.rows("SELECT latency_line_ms, rules FROM record"), [(12.5, "plugin-qualify-rules/1.2")])
        self.assertEqual([v for (v,) in self.rows("SELECT latency_ms FROM cell ORDER BY ord")][:2], [5.333333333333333, 10.666666666666666])
        got = self.export()
        self.assertIsNone(first_difference(without_sentences(rec), got))
        # the shortest decimal that gives the same double, as JSON.stringify writes it
        self.assertEqual([repr(c["latencyMs"]) for c in got["measurements"]["grid"]][:2], ["5.333333333333333", "10.666666666666666"])
        self.assertEqual((got["latencyLineMs"], got["rules"]), (12.5, "plugin-qualify-rules/1.2"))

    def test_absent_they_are_null_and_read_back_absent(self):
        self.put()
        self.assertEqual(self.rows("SELECT latency_line_ms, rules FROM record"), [(None, None)])
        self.assertEqual(self.rows("SELECT count(*) FROM cell WHERE latency_ms IS NOT NULL"), [(0,)])
        got = self.export()
        self.assertNotIn("latencyLineMs", got)
        self.assertNotIn("rules", got)
        self.assertTrue(all("latencyMs" not in c for c in got["measurements"]["grid"]))

    def test_rules_is_a_name_of_the_rules_family(self):
        self.refused("schema-refused", rec=self.edited(lambda r: r.update(rules="v1")))
        self.refused("schema-refused", rec=self.edited(lambda r: r.update(rules="plugin-qualify-rules/x")))

    def test_the_adapter_host_is_a_word_of_the_adapter_hosts(self):
        rec, offer, cls = first_record(LV2, lambda r: "adapter" in r)
        rec["adapter"]["host"] = "mod-host"
        self.put(rec, offer=offer, cls=cls)
        self.assertEqual(self.rows("SELECT adapter_host FROM record"), [("mod-host",)])
        self.assertEqual(self.export()["adapter"]["host"], "mod-host")

    def test_an_adapter_code_of_an_adapter_host(self):
        rec, offer, cls = first_record(LV2, lambda r: "adapter" in r)
        rec["adapter"]["host"] = "jalv"
        rec["adapter"]["code"] = "jalv.no-jack-client"
        self.put(rec, offer=offer, cls=cls)
        self.assertEqual(self.rows("SELECT adapter_code FROM record"), [("jalv.no-jack-client",)])

    def test_a_judge_profile_is_no_adapter_host(self):
        profiles = q.Domains(contract_dir()).items[("qualification", "QUALIFICATION_HOST_PROFILES")]
        other = [p for p in profiles if p not in ("omx-clap-host", "mod-host", "jalv")]
        self.assertTrue(other, "the fixture has a profile that is no adapter host")
        rec, offer, cls = first_record(LV2, lambda r: "adapter" in r)
        rec["adapter"]["host"] = other[0]
        with self.assertRaises(q.Refusal) as cm:
            self.put(rec, offer=offer, cls=cls)
        self.assertEqual(cm.exception.name, "word-unknown")
        self.assertIn("adapter.host", str(cm.exception))


class FieldAudit(Layer):
    """The seven fields today's records carry that the first writer refused (spec section 3.5): plugin.name, the pool step's
    dspLoadOff/On and xrunsOff/On, and history[] with its unknownKeys and blockedBy; provenance stays refused."""

    def history(self):
        host = "omx-clap-host"
        return [
            {"hostClass": "x86_64/8/3000", "file": "history.tsv", "at": "2026-11-19T10:00:00.000Z",
             "key": {"uri": "clap:example", "digest": "ab" * 32}, "found": True, "windows": {"solo": 3, "grouped": 2},
             "summary": {"crashed": False, "raisesXruns": True}, "unknownKeys": {"zz": "1", "extra": "x y"},
             "verdicts": [
                 {"host": host, "measured": "isolated", "adjusted": "isolated", "move": "none", "reason": "history.not-liftable",
                  "blockedBy": ["refused", "hosting.rt-safety.violations-in-run"]},
                 {"host": host, "measured": None, "adjusted": None, "move": "none", "reason": "history.no-record"},
                 {"host": host, "measured": "in-process", "adjusted": "isolated", "move": "demote", "reason": "history.crashed",
                  "blockedBy": []}]},
            {"hostClass": "aarch64/4/2400", "file": "other.tsv", "at": "2026-11-19T11:00:00.000Z", "found": False,
             "unknownKeys": {}, "verdicts": [{"host": host, "measured": "isolated", "adjusted": "in-process", "move": "promote",
                                              "reason": "history.steady"}]}]

    def full(self, r):
        r["plugin"]["name"] = "Example Synth"
        step = r["run"]["steps"][0]
        step["pool"] = {"allocationsOn": 1, "dspLoadOff": 0.125, "dspLoadOn": 0.375, "xrunsOff": 0, "xrunsOn": 2}
        r["history"] = self.history()

    def test_a_record_with_all_of_them_is_stored_and_read_back(self):
        rec = self.edited(self.full)
        self.put(rec)
        got = self.export()
        self.assertIsNone(first_difference(without_sentences(rec), got))
        self.assertEqual(json.dumps(got["history"]), json.dumps(rec["history"]))   # plugin-qualify's key order
        self.assertEqual(got["plugin"]["name"], "Example Synth")
        self.assertEqual(self.rows("SELECT plugin_name FROM record"), [("Example Synth",)])
        self.assertEqual(self.rows("SELECT pool_dsp_load_off, pool_dsp_load_on, pool_xruns_off, pool_xruns_on FROM run_step "
                                   "WHERE pool_dsp_load_on IS NOT NULL"), [(0.125, 0.375, 0, 2)])

    def test_the_history_rows(self):
        self.put(self.edited(self.full))
        self.assertEqual(self.rows("SELECT ord, host_class, found, windows_solo, summary_raises_xruns, unknown_keys FROM record_history ORDER BY ord"),
                         [(0, "x86_64/8/3000", 1, 3, 1, 1), (1, "aarch64/4/2400", 0, None, None, 1)])
        self.assertEqual(self.rows("SELECT name, value FROM history_unknown_key ORDER BY name"), [("extra", "x y"), ("zz", "1")])
        self.assertEqual(self.rows("SELECT history_ord, ord, measured, adjusted, blocked_by FROM history_verdict ORDER BY history_ord, ord"),
                         [(0, 0, "isolated", "isolated", 1), (0, 1, None, None, None), (0, 2, "in-process", "isolated", 1),
                          (1, 0, "isolated", "in-process", None)])
        self.assertEqual(self.rows("SELECT verdict_ord, ord, code FROM history_blocked ORDER BY ord"),
                         [(0, 0, "refused"), (0, 1, "hosting.rt-safety.violations-in-run")])

    def test_absent_they_are_null_and_read_back_absent(self):
        self.put()
        self.assertEqual(self.rows("SELECT plugin_name FROM record"), [(None,)])
        self.assertEqual(self.rows("SELECT count(*) FROM record_history"), [(0,)])
        got = self.export()
        self.assertNotIn("name", got["plugin"])
        self.assertNotIn("history", got)

    def test_provenance_is_still_refused(self):
        rec = self.edited(lambda r: r.update(provenance={"set": "x"}))
        self.refused("field-unmapped", "provenance", rec=rec)

    def test_a_history_word_outside_its_item_is_refused(self):
        for path, fn in (("measured", lambda v: v.update(measured="running")), ("move", lambda v: v.update(move="sideways")),
                         ("reason", lambda v: v.update(reason="history.because")), ("host", lambda v: v.update(host="no-such-host"))):
            def f(r, fn=fn):
                self.full(r)
                fn(r["history"][0]["verdicts"][0])
            with self.subTest(path):
                with self.assertRaises(q.Refusal) as cm:
                    self.put(self.edited(f))
                self.assertEqual(cm.exception.name, "word-unknown")
                self.assertIn(f"history[0].verdicts[0].{path}", str(cm.exception))

    def test_a_blocked_code_is_a_pin_verdict_or_a_reason_code(self):
        def f(r):
            self.full(r)
            r["history"][0]["verdicts"][0]["blockedBy"] = ["not-a-code"]
        with self.assertRaises(q.Refusal) as cm:
            self.put(self.edited(f))
        self.assertEqual(cm.exception.name, "word-unknown")
        self.assertIn("not-a-code", str(cm.exception))

    def test_the_blockers_of_the_history_are_words_of_their_own_item(self):
        """blockers() of history-adjust.ts: refused, unknown, no-deciding-reason (QUALIFICATION_HISTORY_BLOCKERS)."""
        def f(r):
            self.full(r)
            r["history"][0]["verdicts"][0]["blockedBy"] = ["unknown", "no-deciding-reason", "refused", "hosting.stability.unsoaked"]
        rec = self.edited(f)
        self.put(rec)
        self.assertEqual(json.dumps(self.export()["history"]), json.dumps(rec["history"]))

    def test_a_pin_verdict_that_is_no_blocker_is_refused(self):
        def f(r):
            self.full(r)
            r["history"][0]["verdicts"][0]["blockedBy"] = ["isolated"]
        with self.assertRaises(q.Refusal) as cm:
            self.put(self.edited(f))
        self.assertEqual(cm.exception.name, "word-unknown")

    def test_an_empty_history_is_refused(self):
        self.refused("array-empty", "history", rec=self.edited(lambda r: r.update(history=[])))


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

    def test_a_layer_is_written_with_no_base_anywhere(self):
        """An absent base is a valid empty base layer (store spec, section 6): the writer never looks for one, and
        writes the user and the system layer whether or not a base exists."""
        for scope in ("user", "system"):
            root = os.path.join(self.tmp, scope)
            os.makedirs(root)
            self.assertEqual(os.listdir(root), [])
            self.put(scope=scope, root=root)
            found = [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs if f.endswith(".sqlite")]
            self.assertEqual(len(found), 1, found)
            with contextlib.closing(sqlite3.connect(found[0])) as db:
                self.assertEqual(db.execute("SELECT user_layer FROM store_info").fetchall(), [(1,)])
                self.assertEqual(db.execute("SELECT count(*) FROM record").fetchone(), (1,))
            self.assertFalse([f for f in found if "base" in os.path.basename(f)])

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


class HostingWords(Layer):
    """The hosting.* words are the codes of the contract package omx-clap (omx-clap-core's data/hosting.json and data/hosting/*.json,
    items of kind codes), read from the contract directory the package installs into; no hosting domain document."""

    def test_the_package_is_recorded_with_its_version(self):
        self.put()
        manifest = load(os.path.join(hosting_dir(), "MANIFEST.json"))
        self.assertEqual(self.rows("SELECT version FROM store_domain WHERE domain = 'hosting'"), [(manifest["version"],)])
        self.assertEqual(self.rows("SELECT count(*) FROM store_domain WHERE domain = ?", hosting_package()), [(0,)])
        self.assertGreater(self.rows("SELECT count(*) FROM word_check WHERE domain = 'hosting'")[0][0], 3)

    def test_a_hosting_code_of_the_package_is_a_word(self):
        words = set()
        for n in ("hosting.json",) + tuple("hosting/" + f for f in sorted(os.listdir(os.path.join(hosting_dir(), "hosting")))):
            for item in load(os.path.join(hosting_dir(), n)).values():
                if isinstance(item, dict) and item.get("kind") == "codes":
                    words.update(c["code"] for c in item["codes"].values())
        self.assertIn("hosting.clap.extensions-not-covered", words)
        dom = q.Domains(contract_dir())
        self.assertEqual(set(dom.items[("hosting", "HOSTING_CLAP_CODES")]),
                         {c["code"] for c in load(os.path.join(hosting_dir(), "hosting", "clap.json"))["HOSTING_CLAP_CODES"]["codes"].values()})

    def test_a_hosting_code_that_is_none_is_refused(self):
        rec = self.edited(lambda r: r["verdicts"][0]["reasons"].append(
            {"dimension": r["verdicts"][0]["reasons"][0]["dimension"], "rating": r["verdicts"][0]["reasons"][0]["rating"],
             "code": "hosting.clap.not-a-code", "params": {}}))
        with self.assertRaises(q.Refusal) as cm:
            self.put(rec)
        self.assertEqual(cm.exception.name, "word-unknown")
        self.assertIn("hosting.clap.not-a-code", str(cm.exception))

    def test_a_contract_directory_without_the_package_is_refused_by_name(self):
        c = os.path.join(self.tmp, "contract")
        shutil.copytree(contract_dir(), c)
        shutil.rmtree(os.path.join(c, "3"))
        with self.assertRaises(q.Refusal) as cm:
            q.put(self.rec, scope="user", offer=self.offer, host_class=self.cls, contract_dir=c, root=self.root)
        self.assertEqual(cm.exception.name, "contract.domain.absent")
        self.assertIn(f"(<schema major>/{hosting_package()}/MANIFEST.json)", str(cm.exception))
        self.assertFalse(os.path.exists(self.db))

    def test_the_package_under_its_name_before_0_34_0_is_not_read(self):
        """omx-clap-core before 0.34.0 installed the words as <schema major>/omx-clap-core/: that name is no source, the
        installed package is read by the one name the tree installs under now, and nothing falls back to the old one."""
        self.assertNotEqual(hosting_package(), "omx-clap-core")
        c = os.path.join(self.tmp, "contract")
        shutil.copytree(contract_dir(), c)
        os.rename(os.path.join(c, "3", hosting_package()), os.path.join(c, "3", "omx-clap-core"))
        with self.assertRaises(q.Refusal) as cm:
            q.put(self.rec, scope="user", offer=self.offer, host_class=self.cls, contract_dir=c, root=self.root)
        self.assertEqual(cm.exception.name, "contract.domain.absent")
        self.assertIn(f"(<schema major>/{hosting_package()}/MANIFEST.json)", str(cm.exception))
        self.assertFalse(os.path.exists(self.db))

    def test_a_hosting_domain_document_is_no_source_of_words(self):
        """A hosting/hosting.json beside the package is not read: the package's items are the words."""
        c = os.path.join(self.tmp, "contract")
        shutil.copytree(contract_dir(), c)
        os.makedirs(os.path.join(c, "hosting"))
        with open(os.path.join(c, "hosting", "hosting.json"), "w") as f:
            json.dump({"info": {"version": "9.9.9"}, "components": {"schemas": {}}}, f)
        q.put(self.rec, scope="user", offer=self.offer, host_class=self.cls, contract_dir=c, root=self.root)
        self.assertNotEqual(self.rows("SELECT version FROM store_domain WHERE domain = 'hosting'"), [("9.9.9",)])


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


COMMAND = os.path.join(HERE, "plugin-qualification-db-write")


class Command(Layer):
    """Section 6.1's command: put reads one record on standard input; refusals are named on standard error, exit 1."""

    def run_cmd(self, *args, stdin=""):
        cmd = [sys.executable, "-B", COMMAND, *args]
        return subprocess.run(cmd, input=stdin, capture_output=True, text=True)

    def put_cmd(self, rec=None, *extra, offer=None, cls=None, scope="user"):
        return self.run_cmd("put", "--scope", scope, "--offer", offer or self.offer, "--host-class", cls or self.cls,
                            "--root", self.root, "--contract-dir", contract_dir(), *extra,
                            stdin=json.dumps(rec if rec is not None else self.rec))

    def key_args(self, **kw):
        k = dict(sha256=self.rec["binary"]["sha256"], format=self.rec["plugin"]["format"], uri=self.rec["plugin"]["id"],
                 offer=self.offer, host_class=self.cls)
        k.update(kw)
        return ["--sha256", k["sha256"], "--format", k["format"], "--uri", k["uri"], "--offer", k["offer"],
                "--host-class", k["host_class"]]

    @staticmethod
    def dot_dot(r):
        r["binary"]["path"] = "../" + r["binary"]["path"]
        r["binary"]["files"][0]["path"] = r["binary"]["path"]

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
        lv2, loffer, lcls = first_record(LV2, lambda r: r["plugin"]["format"] == "lv2" and len(r["binary"]["files"]) > 2
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
            "schema-refused": (self.edited(self.dot_dot), {}),
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
                         "--contract-dir", contract_dir(), stdin="{not json")
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
        with open(HEADER, encoding="utf-8") as f:
            self.assertIn(f"#define PQDB_SCHEMA_VERSION {q.schema_version()}\n", f.read())


if __name__ == "__main__":
    unittest.main()
