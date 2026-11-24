#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The record check (tools/check-records.py) and the base database (tools/records-db.py) read the `qualification` domain,
plugin-hostd's: the build requires plugin-hostd-contract at a floor, names no other package for the domain, and no
Breaks, Replaces, Conflicts or Provides stands for the package the domain left (plugin-qualify-contract).

    python3 -m unittest tools/test_provenance_packaging.py
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class Packaging(unittest.TestCase):
    def test_the_spec_builds_against_plugin_hostd_contract(self):
        spec = read("packaging/plugin-qualification-records.spec").split("%changelog")[0]
        self.assertRegex(spec, re.compile(r"^BuildRequires: plugin-hostd-contract >= \d+\.\d+\.\d+$", re.M))
        self.assertNotIn("plugin-qualify-contract", spec)

    def test_debian_builds_against_plugin_hostd_contract(self):
        control = read("debian/control")
        self.assertRegex(control, r"plugin-hostd-contract \(>= \d+\.\d+\.\d+~\)")
        self.assertNotIn("plugin-qualify-contract", control)

    def test_no_relation_stands_for_the_old_package(self):
        for rel in ("packaging/plugin-qualification-records.spec", "debian/control", "debian/rules", "tools/sets.py"):
            for line in read(rel).splitlines():
                if re.match(r"^\s*(Breaks|Replaces|Conflicts|Provides|Obsoletes):", line):
                    self.assertNotIn("qualify-contract", line, rel)


if __name__ == "__main__":
    unittest.main()
