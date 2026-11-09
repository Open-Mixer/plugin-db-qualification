#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The provenance of a fedora44 Job's records: the template's fixed fields with what the run recorded in its meta/.

    tools/fedora44/provenance.py <template json> <run meta dir> <out json> <RUN> <branch sha> <measured date>
"""
import json
import os
import sys

# the packages of the measuring stack, named in every provenance; the plugin set comes from plugin-packages.tsv
HOST = ["jack-audio-connection-kit", "lilv", "mod-host", "mod-host-protocol", "nodejs22", "omx-clap-core",
        "omx-clap-core-contract", "omx-clap-host", "omx-contract-data", "omx-plugins-clap", "omx-plugins-lv2",
        "plugin-hostd", "plugin-hostd-contract", "plugin-qualify", "python3-lilv"]
ORDER = ["image", "board", "kernel", "measured", "hostProfile", "realtime", "jack", "settings", "sources",
         "repositories", "packages"]


def main(template, meta, dst, run, sha, measured):
    d = json.load(open(template, encoding="utf-8"))
    installed = {}
    for line in open(os.path.join(meta, "installed.txt"), encoding="utf-8"):
        p = line.split()
        if len(p) >= 2:
            installed[p[0]] = p[1]
    missing = [k for k in HOST if k not in installed]
    if missing:
        sys.exit(f"{meta}/installed.txt names no {', '.join(missing)}")
    packages = {k: installed[k] for k in HOST}
    for line in open(os.path.join(meta, "plugin-packages.tsv"), encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) == 2:
            packages[p[0]] = p[1]
    cpu = next(l.split(":", 1)[1].strip() for l in open(os.path.join(meta, "lscpu"), encoding="utf-8")
               if l.startswith("Model name"))
    kernel = open(os.path.join(meta, "uname"), encoding="utf-8").read().split()[2]
    d.update({
        "board": f"{cpu} (x86_64, 8 cores, 16 threads), a real machine: cluster node h2, in a Kubernetes pod limited to 3 CPUs",
        "kernel": f"{kernel} (PREEMPT_DYNAMIC)",
        "measured": measured,
        "sources": {f"plugin-db-qualification tools/fedora44 (Job), records branch records/fedora44/{run}": sha},
        "packages": packages,
    })
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({k: d[k] for k in ORDER}, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    if len(sys.argv) != 7:
        sys.exit(__doc__)
    main(*sys.argv[1:])
