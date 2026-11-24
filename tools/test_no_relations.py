#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""No relations between this source's packages, and none to the older per-set names.

    python3 -m unittest tools/test_no_relations.py

The packages of this source carry no Provides, Replaces, Breaks or Conflicts (Debian) and no Provides, Obsoletes or
Conflicts (RPM): not on each other, not on the names the records were published under before, one package per set
(plugin-db-qualification-<class>-<set>, omx-qualification-<class>-<set>). Those names are pruned from the channel, not
taken over in code. A package states its dependencies with no version written by hand (tools/test_sets.py,
Dependencies); debian/rules writes no substvar and the spec has no generated block.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OLD_NAMES = re.compile(r"(plugin-db-qualification|omx-qualification)-(x86-64|rpi5)\b")
DEB_FIELDS = ("Provides", "Replaces", "Breaks", "Conflicts")
RPM_FIELDS = ("Provides", "Obsoletes", "Conflicts")


def read(*path):
    with open(os.path.join(ROOT, *path), encoding="utf-8") as f:
        return f.read()


class NoRelations(unittest.TestCase):
    def test_debian_control_has_no_relation_field(self):
        found = []
        for stanza in read("debian", "control").strip().split("\n\n"):
            name = re.search(r"^Package: *(\S+)", stanza, re.M)
            for field in DEB_FIELDS:
                if re.search(rf"^{field}:", stanza, re.M):
                    found.append(f"{name.group(1) if name else 'source'}: {field}")
        self.assertEqual(found, [])

    def test_the_spec_has_no_relation_line(self):
        found = [l for l in read("packaging", "plugin-qualification-records.spec").split("\n")
                 if re.match(rf"({'|'.join(RPM_FIELDS)}):", l)]
        self.assertEqual(found, [])

    def test_no_old_per_set_name_is_named_in_the_packaging(self):
        for path in (("debian", "control"), ("packaging", "plugin-qualification-records.spec")):
            self.assertIsNone(OLD_NAMES.search(read(*path)), "/".join(path))

    def test_debian_rules_writes_no_substvar(self):
        self.assertNotIn("substvars", read("debian", "rules"))


if __name__ == "__main__":
    unittest.main()
