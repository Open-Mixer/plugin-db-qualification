#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The outcome counts of record sets, as plugin-qualify-sync reads each record's verdict for a host.

    tools/outcomes.py [--host omx-clap-host] <set or qualification dir> ...

One line a directory: qualified, refused, crashed, hung and unmeasured, then the plugins with no verdict for the host.
The outcome of a verdict is plugin-qualify's own (outcomeOfVerdict, src/distributed-records.ts): not measured is
crashed on probe.crashed, hung on probe.timeout, else unmeasured; measured is qualified when suitable or conditional,
refused when unsuitable, else unmeasured.
"""
import argparse
import collections
import glob
import json
import os
import sys

OUTCOMES = ("qualified", "refused", "crashed", "hung", "unmeasured")


def outcome(v):
    if not v.get("measured"):
        return {"probe.crashed": "crashed", "probe.timeout": "hung"}.get(v.get("deciding"), "unmeasured")
    if v.get("rating") in ("suitable", "conditional"):
        return "qualified"
    return "refused" if v.get("rating") == "unsuitable" else "unmeasured"


def counts(path, host):
    c, none = collections.Counter(), 0
    for f in sorted(glob.glob(os.path.join(path, "*.qualification.json"))):
        verdicts = [v for v in json.load(open(f, encoding="utf-8"))["verdicts"] if v.get("host") == host]
        if not verdicts:
            none += 1
            continue
        c[outcome(verdicts[0])] += 1
    return c, none


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="omx-clap-host")
    ap.add_argument("dirs", nargs="+")
    a = ap.parse_args(argv)
    for d in a.dirs:
        c, none = counts(d, a.host)
        print(f"{d}: " + ", ".join(f"{k} {c[k]}" for k in OUTCOMES) + f" ({none} records with no {a.host} verdict)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
