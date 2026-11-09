#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""Record what kind of measurement a set is, in its provenance.json.

    tools/set-tier.py <tier> <set dir> ...

<tier> is one of:
  reference    measured in a container on JACK's dummy driver with real-time priority (SCHED_FIFO, memory locked):
               every figure is comparable across machines and classes
  provisional  measured on JACK's dummy driver without real-time priority: the crash, hang and unmeasured verdicts
               hold; cost, latency and xrun figures are not reference figures
  hardware     measured on the machine's own audio interface: the verdicts hold; its figures describe that interface
               and are not compared with the reference tier

The records and probe outputs are never touched: only provenance.json gains "tier" and "tierNote".
"""
import json
import os
import sys

NOTES = {
    "reference": "measured in a container on JACK's dummy driver with real-time priority (SCHED_FIFO, memory locked); "
                 "every figure is a reference figure",
    "provisional": "measured on JACK's dummy driver without real-time priority; the crash, hang and unmeasured verdicts "
                   "hold, the cost, latency and xrun figures are not reference figures",
    "hardware": "measured on the machine's own audio interface; the verdicts hold, the figures describe that interface "
                "and are not compared with the reference tier",
}


def main(argv):
    if len(argv) < 2 or argv[0] not in NOTES:
        sys.exit(__doc__)
    tier = argv[0]
    for d in argv[1:]:
        p = os.path.join(d, "provenance.json")
        with open(p, encoding="utf-8") as f:
            prov = json.load(f)
        prov["tier"] = tier
        prov["tierNote"] = NOTES[tier]
        with open(p, "w", encoding="utf-8") as f:
            json.dump(prov, f, indent=2)
            f.write("\n")
        print(f"{d}: tier {tier}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
