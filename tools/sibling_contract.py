# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""TEST ONLY: the contract directory the writer and the base build are tested against, assembled from sibling clones.

PDQ_SIBLINGS names the directory that holds the clones (plugin-qualify, plugin-hostd, plugin-db, omx-clap-core); each
domain is read from `contract.d/<domain>/` at PDQ_REF (default origin/main). The hosting words are the data/ of
omx-clap-core at the same ref, laid out as its `make install-contract` lays them: <contractdir>/3/<package>/ and a
MANIFEST.json, where <package> is the name that tree installs under (its Makefile's `CORE =`, omx-clap since 0.34.0),
read from the tree and never written here. Without PDQ_SIBLINGS a test that needs the words is skipped, saying so.
The writer and the base build read no variable of this module.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

DOMAIN_REPO = {"qualification": "plugin-hostd", "machine": "plugin-hostd", "probe": "plugin-hostd-protocol",
               "plugin-db": "plugin-db"}
HOSTING_REPO = "omx-clap-core"
SCHEMA_MAJOR = "3"
SIBLINGS = os.environ.get("PDQ_SIBLINGS")
REF = os.environ.get("PDQ_REF", "origin/main")
_contract = {}


def git_show(clone, ref, path):
    r = subprocess.run(["git", "-C", clone, "show", f"{ref}:{path}"], capture_output=True)
    if r.returncode:
        raise unittest.SkipTest(f"{os.path.basename(clone)} {ref}: {path}: {r.stderr.decode().strip()}")
    return r.stdout


def _clone(repo):
    if not SIBLINGS:
        raise unittest.SkipTest("PDQ_SIBLINGS is not set: no sibling clones to read the owners' words from "
                                f"({', '.join(sorted(set(DOMAIN_REPO.values()) | {HOSTING_REPO}))})")
    clone = os.path.join(SIBLINGS, repo)
    if not os.path.isdir(clone):
        raise unittest.SkipTest(f"{clone}: no such sibling clone")
    return clone


def hosting_package():
    """The contract package name omx-clap-core's tree installs its data/ under: its Makefile's `CORE =` at PDQ_REF."""
    m = re.search(r"(?m)^CORE\s*=\s*(\S+)\s*$", git_show(_clone(HOSTING_REPO), REF, "Makefile").decode())
    if not m:
        raise AssertionError(f"{HOSTING_REPO} {REF}: its Makefile names no CORE, the package install-contract lays out")
    return m.group(1)


def hosting_dir():
    """<contractdir>/3/<package>/ of the assembled contract directory."""
    return os.path.join(contract_dir(), SCHEMA_MAJOR, hosting_package())


def _qualification_items(doc):
    # plugin-qualify names the hosts an adapter runs a plugin under (QUALIFICATION_ADAPTER_HOSTS, spec section 3.4)
    # in its line 3, and the words of the pin verdicts and the history (QUALIFICATION_PIN_VERDICTS, _HISTORY_MOVES, _HISTORY_REASONS,
    # from plugin-qualify's pins-file.ts and history-adjust.ts); until its domain publishes the items the fixture adds them
    schemas = doc["components"]["schemas"]
    schemas.setdefault("QUALIFICATION_ADAPTER_HOSTS", {"oneOf": [{"const": h} for h in ("omx-clap-host", "mod-host", "jalv")]})
    schemas.setdefault("QUALIFICATION_PIN_VERDICTS", {"oneOf": [{"const": w} for w in ("in-process", "isolated", "refused")]})
    schemas.setdefault("QUALIFICATION_HISTORY_BLOCKERS",
                       {"oneOf": [{"const": w} for w in ("refused", "unknown", "no-deciding-reason")]})
    schemas.setdefault("QUALIFICATION_HISTORY_MOVES", {"oneOf": [{"const": w} for w in ("demote", "promote", "none")]})
    schemas.setdefault("QUALIFICATION_HISTORY_REASONS", {
        "oneOf": [{"const": "history." + w} for w in ("crashed", "xruns-grouped", "crashed-alone", "steady", "no-record",
                                                      "no-change", "not-liftable")]})


def contract_dir():
    """The contract directory assembled from the sibling clones, once; skips the test when they are not given. The
    domains are documents (<domain>/<domain>.json); the hosting words are omx-clap-core's data/, installed as its
    `make install-contract` does: <schema major>/<package>/ with the files as they are and a MANIFEST.json."""
    if "dir" in _contract:
        return _contract["dir"]
    clones = {repo: _clone(repo) for repo in sorted(set(DOMAIN_REPO.values()) | {HOSTING_REPO})}
    package = hosting_package()
    root = tempfile.mkdtemp(prefix="pdq-contract-")
    for dom, repo in DOMAIN_REPO.items():
        os.makedirs(os.path.join(root, dom))
        doc = json.loads(git_show(clones[repo], REF, f"contract.d/{dom}/{dom}.json"))
        if dom == "qualification":
            _qualification_items(doc)
        with open(os.path.join(root, dom, dom + ".json"), "w") as f:
            json.dump(doc, f)
    core = clones[HOSTING_REPO]
    names = subprocess.run(["git", "-C", core, "ls-tree", "-r", "--name-only", REF, "data"], capture_output=True, text=True,
                           check=True).stdout.split("\n")
    dest = os.path.join(root, SCHEMA_MAJOR, package)
    for n in sorted(x for x in names if x.endswith(".json")):
        rel = n[len("data/"):]
        os.makedirs(os.path.join(dest, os.path.dirname(rel)), exist_ok=True)
        with open(os.path.join(dest, rel), "wb") as f:
            f.write(git_show(core, REF, n))
    with open(os.path.join(dest, "MANIFEST.json"), "w") as f:
        json.dump({"package": package, "version": git_show(core, REF, "VERSION").decode().strip(),
                   "schemaMajor": int(SCHEMA_MAJOR), "files": {}}, f)
    _contract["dir"] = root
    return root


def remove():
    if "dir" in _contract:
        shutil.rmtree(_contract.pop("dir"), ignore_errors=True)
