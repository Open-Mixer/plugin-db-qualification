# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""tools/fedora44/provenance.py over a run whose image installed the served omx-clap 0.34.0 stack (#78).

    python3 -m unittest tools/test_fedora44_provenance.py

omx-clap 0.34.0 ships its runtime as omx-clap-libs and its contract package as omx-clap-contract (omx-clap-core and
omx-clap-core-contract before it, which it obsoletes): a provenance names the packages the run installed, so a run on
the served channel writes one, and a list naming only the old packages is refused by name.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "fedora44", "provenance.py")
TEMPLATE = os.path.join(HERE, "fedora44", "provenance-template.json")
# `dnf repoquery --installed --qf '%{name} %{evr} %{from_repo}'` of a fedora:44 image on the channel of 2026-11-24
SERVED = {
    "jack-audio-connection-kit": "1.9.22-12.fc44", "lilv": "0.24.26-6.fc44", "mod-host": "0.10.6-3.fc44",
    "mod-host-protocol": "0.3.2-1.fc44", "nodejs22": "1:22.21.0-1.fc44", "omx-clap-host": "0.34.0-1.fc44",
    "omx-clap-libs": "0.34.0-1.fc44", "omx-clap-contract": "0.34.0-1.fc44", "omx-contract-data": "3.21.0-1.fc44",
    "omx-plugins-clap": "0.9.0-1.fc44", "omx-plugins-lv2": "0.9.0-1.fc44", "plugin-hostd": "0.21.1-1.fc44",
    "plugin-hostd-contract": "0.21.1-1.fc44", "plugin-qualify": "0.21.1-1.fc44", "python3-lilv": "0.24.26-6.fc44",
}


class Provenance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pdq-prov-")
        self.meta = os.path.join(self.tmp.name, "meta")
        os.makedirs(self.meta)
        with open(os.path.join(self.meta, "plugin-packages.tsv"), "w", encoding="utf-8") as f:
            f.write("omx-plugins-clap\t0.9.0-1.fc44\n")
        with open(os.path.join(self.meta, "lscpu"), "w", encoding="utf-8") as f:
            f.write("Model name:  AMD Ryzen 7 5700U\n16\n")
        with open(os.path.join(self.meta, "uname"), "w", encoding="utf-8") as f:
            f.write("Linux h2 6.17.7-300.fc44.x86_64 #1 SMP PREEMPT_DYNAMIC x86_64 GNU/Linux\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, installed):
        with open(os.path.join(self.meta, "installed.txt"), "w", encoding="utf-8") as f:
            f.writelines(f"{n} {v} openmixer\n" for n, v in sorted(installed.items()))
        out = os.path.join(self.tmp.name, "provenance.json")
        r = subprocess.run([sys.executable, "-I", TOOL, TEMPLATE, self.meta, out, "20261124", "0" * 40, "2026-11-24"],
                           capture_output=True, text=True)
        return r, out

    def test_a_run_on_the_served_stack_names_omx_clap_libs_and_omx_clap_contract(self):
        r, out = self.run_tool(SERVED)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as f:
            packages = json.load(f)["packages"]
        self.assertEqual(packages["omx-clap-contract"], "0.34.0-1.fc44")
        self.assertEqual(packages["omx-clap-libs"], "0.34.0-1.fc44")
        self.assertFalse([k for k in packages if k.startswith("omx-clap-core")], packages)

    def test_a_list_with_the_names_before_0_34_0_only_is_refused_by_name(self):
        old = {k: v for k, v in SERVED.items() if k not in ("omx-clap-libs", "omx-clap-contract")}
        old.update({"omx-clap-core": "0.33.1-1.fc44", "omx-clap-core-contract": "0.33.1-1.fc44"})
        r, _ = self.run_tool(old)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("names no omx-clap-contract, omx-clap-libs", r.stderr)


if __name__ == "__main__":
    unittest.main()
