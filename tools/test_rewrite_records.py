#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""tools/rewrite-records.py, the one-off rewrite of records/ (this repository's qualification store spec, section 3.7,
"Records of today: one rewrite, no conversion"), and the form it leaves records/ in.

    python3 -m unittest tools/test_rewrite_records.py

The rewrite sets a CLAP record's binary.path to its file's own name and adds hostExtensions (the probe output's
offer.clapExtensions), and changes nothing else. The corpus tests read records/ itself: red until the commit of their own
that rewrites it.
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TOOL = os.path.join(HERE, "rewrite-records.py")
RECORDS = os.path.join(REPO, "records")
CLAP_DIR = "/usr/lib64/clap/%s/Contents/x86_64-linux/%s"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(path, value):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=1, ensure_ascii=False)
        f.write("\n")


def sets():
    return [(c, s) for c in sorted(os.listdir(RECORDS)) for s in sorted(os.listdir(os.path.join(RECORDS, c)))]


def record_names(c, s):
    d = os.path.join(RECORDS, c, s)
    return sorted(f for f in os.listdir(d) if f.endswith(".qualification.json"))


def run_tool(records, *extra):
    if not os.path.exists(TOOL):
        raise AssertionError(f"{TOOL} does not exist")
    return subprocess.run([sys.executable, "-B", TOOL, "--records", records, *extra], capture_output=True, text=True)


def old_form(setdir):
    """A fixture in the form records/ had before the rewrite: an absolute CLAP binary.path, no hostExtensions."""
    for f in os.listdir(setdir):
        if f.endswith(".qualification.json"):
            p = os.path.join(setdir, f)
            rec = load(p)
            if rec["plugin"]["format"] == "clap":
                name = rec["binary"]["files"][0]["path"]
                rec["binary"]["path"] = CLAP_DIR % (name, name)
                rec.pop("hostExtensions", None)
            dump(p, rec)


class Rewrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pdq-rewrite-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.recs = os.path.join(self.tmp, "records")
        self.clap = self.fixture("x86-64", "fedora44-48000-512", 4)
        self.nolist = self.add_without_list()
        self.lv2 = self.fixture("rpi5", "zynthian-vangelis", None, lv2=True)

    def add_without_list(self):
        """One CLAP record whose probe ended without the host extensions list (a crashed or timed-out probe)."""
        src = os.path.join(RECORDS, "x86-64", "fedora44-48000-512")
        for f in record_names("x86-64", "fedora44-48000-512"):
            rec = load(os.path.join(src, f))
            if rec["plugin"]["format"] == "clap" and "clapExtensions" not in load(os.path.join(src, rec["probe"]["file"]))["offer"]:
                shutil.copy(os.path.join(src, f), self.clap)
                shutil.copy(os.path.join(src, rec["probe"]["file"]), self.clap)
                old_form(self.clap)
                return f
        raise AssertionError("no such record")

    def fixture(self, c, s, n, lv2=False):
        src = os.path.join(RECORDS, c, s)
        dst = os.path.join(self.recs, c, s)
        os.makedirs(dst)
        names = [f for f in record_names(c, s) if (load(os.path.join(src, f))["plugin"]["format"] == "lv2") == lv2]
        names = names[:n] if n else names[:3]
        for f in names:
            shutil.copy(os.path.join(src, f), dst)
            shutil.copy(os.path.join(src, load(os.path.join(src, f))["probe"]["file"]), dst)
        shutil.copy(os.path.join(src, "provenance.json"), dst)
        old_form(dst)
        return dst

    def files(self, d):
        return sorted(f for f in os.listdir(d) if f.endswith(".qualification.json"))

    def test_a_clap_record_gets_its_own_name_and_the_probes_extensions_and_nothing_else(self):
        before = {f: load(os.path.join(self.clap, f)) for f in self.files(self.clap)}
        r = run_tool(self.recs)
        self.assertEqual(r.returncode, 0, r.stderr)
        for f, was in before.items():
            now = load(os.path.join(self.clap, f))
            probe = load(os.path.join(self.clap, was["probe"]["file"]))
            want = copy.deepcopy(was)
            want["binary"]["path"] = was["binary"]["files"][0]["path"]
            if "clapExtensions" in probe["offer"]:
                want["hostExtensions"] = probe["offer"]["clapExtensions"]
            self.assertEqual(now, want, f)

    def test_the_file_keeps_its_text_form(self):
        run_tool(self.recs)
        for f in self.files(self.clap):
            with open(os.path.join(self.clap, f), encoding="utf-8") as fh:
                text = fh.read()
            self.assertEqual(text, json.dumps(json.loads(text), indent=1, ensure_ascii=False) + "\n", f)

    def test_an_lv2_record_is_not_touched(self):
        before = {f: open(os.path.join(self.lv2, f), "rb").read() for f in self.files(self.lv2)}
        r = run_tool(self.recs)
        self.assertEqual(r.returncode, 0, r.stderr)
        for f, data in before.items():
            self.assertEqual(open(os.path.join(self.lv2, f), "rb").read(), data, f)
            self.assertNotIn("hostExtensions", load(os.path.join(self.lv2, f)))

    def test_no_other_file_changes(self):
        names = [f for f in os.listdir(self.clap) if not f.endswith(".qualification.json")]
        before = {f: open(os.path.join(self.clap, f), "rb").read() for f in names}
        run_tool(self.recs)
        for f, data in before.items():
            self.assertEqual(open(os.path.join(self.clap, f), "rb").read(), data, f)

    def test_the_counts_are_printed(self):
        r = run_tool(self.recs)
        self.assertIn("clap records rewritten: 5", r.stdout)
        self.assertIn("clap records whose probe output holds no host extensions: 1", r.stdout)
        self.assertIn("lv2 records unchanged: 3", r.stdout)
        self.assertIn("clap records already in the form: 0", r.stdout)

    def test_a_second_run_changes_nothing(self):
        run_tool(self.recs)
        before = {f: open(os.path.join(self.clap, f), "rb").read() for f in self.files(self.clap)}
        r = run_tool(self.recs)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("clap records rewritten: 0", r.stdout)
        self.assertIn("clap records already in the form: 5", r.stdout)
        for f, data in before.items():
            self.assertEqual(open(os.path.join(self.clap, f), "rb").read(), data, f)

    def refused(self, name, d, f):
        before = {x: open(os.path.join(d, x), "rb").read() for x in os.listdir(d)}
        r = run_tool(self.recs)
        self.assertEqual(r.returncode, 1)
        self.assertIn(f"refused: {name}:", r.stderr)
        self.assertIn(f, r.stderr)
        for x, data in before.items():
            self.assertEqual(open(os.path.join(d, x), "rb").read(), data, "a refusal changed " + x)

    def test_a_probe_output_without_the_list_gives_the_record_none(self):
        """Nothing is guessed: a crashed or timed-out probe offered no list, and the record gets no hostExtensions."""
        rec = load(os.path.join(self.clap, self.nolist))
        r = run_tool(self.recs)
        self.assertEqual(r.returncode, 0, r.stderr)
        now = load(os.path.join(self.clap, self.nolist))
        self.assertNotIn("hostExtensions", now)
        self.assertEqual(now["binary"]["path"], rec["binary"]["files"][0]["path"])

    def test_a_clap_record_whose_list_is_not_one_file_is_refused(self):
        f = self.files(self.clap)[0]
        p = os.path.join(self.clap, f)
        rec = load(p)
        rec["binary"]["files"].append({"path": "z.clap", "sha256": "1" * 64})
        dump(p, rec)
        self.refused("binary-files-not-one", self.clap, f)

    def test_a_record_whose_key_is_not_its_files_entry_is_refused(self):
        f = self.files(self.clap)[0]
        p = os.path.join(self.clap, f)
        rec = load(p)
        rec["binary"]["files"][0]["sha256"] = "1" * 64
        dump(p, rec)
        self.refused("key-not-the-binary", self.clap, f)

    def test_an_lv2_record_with_an_absolute_path_is_refused(self):
        f = self.files(self.lv2)[0]
        p = os.path.join(self.lv2, f)
        rec = load(p)
        rec["binary"]["path"] = "/usr/lib/lv2/" + rec["binary"]["path"]
        dump(p, rec)
        self.refused("path-absolute", self.lv2, f)


class Corpus(unittest.TestCase):
    """records/ itself, after the rewrite (section 3.7): red until the commit that rewrites it."""

    def test_every_clap_record_is_in_the_relative_form_with_the_probes_extensions(self):
        bad = []
        clap = lv2 = 0
        for c, s in sets():
            d = os.path.join(RECORDS, c, s)
            for f in record_names(c, s):
                rec = load(os.path.join(d, f))
                b = rec["binary"]
                if rec["plugin"]["format"] == "clap":
                    clap += 1
                    ext = load(os.path.join(d, rec["probe"]["file"]))["offer"].get("clapExtensions")
                    if b["path"] != b["files"][0]["path"] or len(b["files"]) != 1 or rec.get("hostExtensions") != ext:
                        bad.append(f"{c}/{s}/{f}")
                else:
                    lv2 += 1
                    if b["path"].startswith("/") or "hostExtensions" in rec:
                        bad.append(f"{c}/{s}/{f}")
        self.assertEqual(bad[:3], [], f"{len(bad)} records are not in the form")
        # the migration's sets (9262 CLAP, 3691 LV2), the 22 reference sets (19,228, 5170), fedora44-192000-128 (88, 32)
        # and the Raspberry Pi re-measure (0, 4); the runs of 2026-11-23 with the LV2 packages the console serves
        # (#66): fedora44-rt-48000-128 holds (874, 986) where it held (874, 235), and fedora44-rt-96000-1024 and
        # fedora44-rt-192000-1024 are new, (874, 986) each
        self.assertEqual((clap, lv2), (9262 + 19228 + 88 + 2 * 874, 3691 + 5170 + 32 + 4 + 986 - 235 + 2 * 986))

    def test_every_key_is_the_sha256_of_its_binary_entry_and_every_list_is_in_byte_order(self):
        for c, s in sets():
            for f in record_names(c, s):
                b = load(os.path.join(RECORDS, c, s, f))["binary"]
                paths = [x["path"] for x in b["files"]]
                self.assertEqual(paths, sorted(paths, key=os.fsencode), f)
                self.assertEqual(len(set(paths)), len(paths), f)
                self.assertEqual([x["sha256"] for x in b["files"] if x["path"] == b["path"]], [b["sha256"]], f"{c}/{s}/{f}")


if __name__ == "__main__":
    unittest.main()
