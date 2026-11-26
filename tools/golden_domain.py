# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The golden `qualification` domain of the tests: the two items tools/check-records.py reads for a provenance, frozen from
plugin-qualify's domain 1.4.0 (2d6aefc) before the domain moved to plugin-hostd. A test that runs the record check takes
it as OMX_CONTRACT_PATH, where the check looks first, so no test reads an installed domain."""
import json
import os

HOST_PROFILES = ("omx-clap-host", "openmixer-console", "openmixer-pi-4gb", "openmixer-pi-8gb")  # QUALIFICATION_HOST_PROFILES
HOST_CLASSES = ("rpi5", "x86-64")  # QUALIFICATION_HOST_CLASSES


def write_domain(root, profiles=HOST_PROFILES, classes=HOST_CLASSES):
    """A contract directory holding a qualification domain with these two items, as OMX_CONTRACT_PATH stands for one"""
    os.makedirs(os.path.join(root, "qualification"), exist_ok=True)
    doc = {"components": {"schemas": {
        "QUALIFICATION_HOST_PROFILES": {"oneOf": [{"const": w, "title": w} for w in profiles]},
        "QUALIFICATION_HOST_CLASSES": {"oneOf": [{"const": w, "title": w} for w in classes]}}}}
    with open(os.path.join(root, "qualification", "qualification.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f)
    return root
