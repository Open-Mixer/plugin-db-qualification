#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""Writes the contract-directory fixtures of test/fixtures/: small domain documents in the layout omx-contract's
loader reads (<dir>/<domain>/<last segment>.json), holding the words the fixture stores use. They are committed;
this script is how they were made and how to change them. Three directories:

  contract-good              every domain, the words the stores hold, qualification at 1.1.0
  contract-no-conditional    the same, but the rating word `conditional` is not in QUALIFICATION_MEASUREMENT_VERDICT_RATINGS
  contract-old               the same as good, but qualification at 1.0.0 (a store checked against 1.1.0 is too new for it)
"""
import json, os, re, sys

WORDS = {
    "plugin-db": ("1.0.0", {"PLUGIN_DB_ADDRESS_FORMATS": ["clap", "lv2"]}),
    "machine": ("1.0.0", {
        "MACHINE_ARCHES": ["aarch64", "x86_64"],
        "MACHINE_FAMILIES": ["cortex-a76", "zen4"],
        "MACHINE_CORE_BANDS": ["cores-4", "cores-8"],
        "MACHINE_CLOCK_BANDS": ["ghz-2", "ghz-3"]}),
    "probe": ("1.0.0", {
        "PROBE_REASONS": ["on-request"],
        "PROBE_OUTCOMES": ["probe.ok", "probe.crashed"],
        "PROBE_SIGNALS": ["SIGSEGV", "SIGABRT"]}),
    # no "hosting": this pass the hosting codes stay in omx-clap-core's data/hosting*.json and there is no hosting domain
    # (the store's hosting exception); the reader skips them, and its test hosting-skip-ends fails if one is written here
    "qualification": ("1.1.0", {
        "QUALIFICATION_HOST_CLASSES": ["rpi5", "x86-64"],
        "QUALIFICATION_SET_TIERS": ["reference", "provisional", "hardware"],
        "QUALIFICATION_HOST_PROFILES": ["omx-clap-host", "openmixer-console"],
        "QUALIFICATION_ADAPTER_HOSTS": ["omx-clap-host", "mod-host", "jalv"],
        "QUALIFICATION_OFFERS": ["default", "custom"],
        "QUALIFICATION_PACKAGE_FORMATS": ["deb", "rpm"],
        "QUALIFICATION_PACKAGE_DISTROS": ["trixie", "fc44", "fc45"],
        "QUALIFICATION_PACKAGE_ARCHES": ["arm64", "amd64", "all", "aarch64", "x86_64", "noarch"],
        "QUALIFICATION_MEASUREMENT_VERDICT_RATINGS": ["qualified", "conditional", "unqualified"],
        "QUALIFICATION_VERDICT_HOSTINGS": ["isolated", "in-process"],
        "QUALIFICATION_VERDICT_ARMS": ["declaration", "run"],
        "QUALIFICATION_ADAPTER_CODE_KINDS": ["resp", "signal", "no-jack-client"],
        "QUALIFICATION_MEMORY_BOUND_OUTCOMES": ["probe.oom"]}),
}

def camel(w):
    parts = re.split(r"[^A-Za-z0-9]+", w)
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])

def doc(domain, version, items):
    schemas = {}
    for item, words in items.items():
        schemas[item] = {
            "description": "The words of %s." % item,
            "x-since": "1.0.0",
            "oneOf": [{"const": w, "title": camel(w), "description": "The word %s." % w, "x-code": i}
                      for i, w in enumerate(words)]}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://openmixer.org/contract/" + domain,
            "info": {"title": "The %s fixture" % domain, "version": version, "x-owner": "fixture",
                     "x-stability": "experimental"},
            "components": {"schemas": schemas}}

def write(root, variant):
    for domain, (version, items) in WORDS.items():
        items = {k: list(v) for k, v in items.items()}
        if variant == "no-conditional" and domain == "qualification":
            items["QUALIFICATION_MEASUREMENT_VERDICT_RATINGS"].remove("conditional")
        if variant == "old" and domain == "qualification":
            version = "1.0.0"
        d = os.path.join(root, "contract-" + variant, domain)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, domain + ".json"), "w") as f:
            json.dump(doc(domain, version, items), f, indent=2)
            f.write("\n")

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "fixtures")
    for v in ("good", "no-conditional", "old"):
        write(out, v)
