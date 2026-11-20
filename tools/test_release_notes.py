#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""tools/release-notes.py: the proofs' findings joined to the release notes under GitHub's limit of 125000 characters. The
`### UNPROVEN records` list of a section goes to the asset proof-notes-<kind>-records.md; the notes keep its heading and a
count line naming the asset; notes that would still be too long fail by name. The rpm proof of 2026112001 listed 1056
records and its release body was refused (HTTP 422).

    python3 -m unittest tools/test_release_notes.py
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "release-notes.py")
HEAD = "### UNPROVEN records: binary differs, the channel serves another omx-plugins version than the one they were measured with"


def section(kind, records, extra=""):
    lines = [f"## Install and sync proof ({kind})", "", "### UNPROVEN sets: the sync never takes them", "", f"- x86-64/set-{kind}-1: never taken", "",
             HEAD, ""]
    lines += [f"- x86-64/fedora44-48000-{i % 7}: urn:record-{i:05d} (omx-plugins measured 0.19.1-1.fc45, the channel serves 0.19.3-1.fc45) " + "x" * 60
              for i in range(records)]
    return "\n".join(lines) + "\n" + extra


class ReleaseNotes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.notes = os.path.join(self.tmp.name, "notes")
        self.assets = os.path.join(self.tmp.name, "assets")
        os.makedirs(self.notes)
        self.body = os.path.join(self.tmp.name, "body.md")
        self.out = os.path.join(self.tmp.name, "out.md")
        with open(self.body, "w", encoding="utf-8") as f:
            f.write("The release body.\n")

    def put(self, kind, text):
        with open(os.path.join(self.notes, f"proof-notes-{kind}-section.md"), "w", encoding="utf-8") as f:
            f.write(text)

    def run_tool(self):
        return subprocess.run([sys.executable, "-B", TOOL, self.body, self.notes, self.out, self.assets], capture_output=True, text=True)

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_an_oversize_records_list_goes_to_an_asset_and_the_body_names_it(self):
        text = section("rpm", 1056)
        self.assertGreater(len(text), 125000)
        self.put("rpm", text)
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.read(self.out)
        self.assertLessEqual(len(out), 125000)
        self.assertIn(HEAD, out)
        self.assertIn("1056 records, each named in the release asset proof-notes-rpm-records.md", out)
        self.assertNotIn("urn:record-00000", out)
        self.assertIn("- x86-64/set-rpm-1: never taken", out)
        asset = self.read(os.path.join(self.assets, "proof-notes-rpm-records.md"))
        self.assertIn(HEAD, asset)
        self.assertEqual(asset.count("urn:record-"), 1056)

    def test_a_small_list_goes_to_an_asset_too_so_both_kinds_read_alike(self):
        self.put("deb", section("deb", 2))
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("2 records, each named in the release asset proof-notes-deb-records.md", self.read(self.out))
        self.assertTrue(os.path.isfile(os.path.join(self.assets, "proof-notes-deb-records.md")))

    def test_a_section_without_records_makes_no_asset(self):
        self.put("deb", "## Install and sync proof (deb)\n\n### UNPROVEN sets: the sync never takes them\n\n- a: b\n")
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.assets, "proof-notes-deb-records.md")))

    def test_notes_still_too_long_fail_by_name(self):
        big = "### UNPROVEN sets: the sync never takes them\n\n" + "".join(f"- x86-64/set-{i}: " + "y" * 100 + "\n" for i in range(1500))
        self.put("rpm", section("rpm", 3, extra="\n" + big))
        r = self.run_tool()
        self.assertEqual(r.returncode, 1)
        self.assertIn("release-notes: the notes are", r.stderr)
        self.assertIn("125000", r.stderr)


if __name__ == "__main__":
    unittest.main()
