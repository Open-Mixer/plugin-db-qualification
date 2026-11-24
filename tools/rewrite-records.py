#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The one-off rewrite of records/ (this repository's qualification store spec, section 3.7, "Records of today: one
rewrite, no conversion").

    tools/rewrite-records.py --records records

For every CLAP record file: binary.path becomes the file's own name (its single list entry's path), and hostExtensions
is added from the probe output beside it (offer.clapExtensions, section 6.2); a probe that ended before it offered a list
gives the record none, nothing guessed. Nothing else changes: no other field, no file name, no key, no other file; LV2
records are already relative and are not touched. Each file keeps its text form (indent 1, UTF-8, one final newline).

A record that is not as the rewrite expects is refused by name and nothing is written: the list is not one file
(binary-files-not-one), the key is not that file's SHA-256 (key-not-the-binary), a path is absolute where the rewrite
does not make it relative (path-absolute, an LV2 record), the probe output is missing (probe-missing). A second run changes
nothing. The counts are printed; the exit code is 0, or 1 on a refusal.
"""
import argparse
import json
import os
import sys

sys.dont_write_bytecode = True
RECORD = ".qualification.json"


class Refusal(Exception):
    def __init__(self, name, label, msg):
        super().__init__(f"{name}: {label}: {msg}")


def text(value):
    return json.dumps(value, indent=1, ensure_ascii=False) + "\n"


def plan(records):
    """[(path, new text or None)] for every record file, and the counts; raises Refusal before anything is written."""
    out, counts = [], dict(rewritten=0, already=0, nolist=0, lv2=0)
    for cls in sorted(os.listdir(records), key=os.fsencode):
        cdir = os.path.join(records, cls)
        if not os.path.isdir(cdir):
            continue
        for s in sorted(os.listdir(cdir), key=os.fsencode):
            d = os.path.join(cdir, s)
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d), key=os.fsencode):
                if not f.endswith(RECORD):
                    continue
                label = f"{cls}/{s}/{f}"
                path = os.path.join(d, f)
                with open(path, encoding="utf-8") as fh:
                    raw = fh.read()
                rec = json.loads(raw)
                b = rec["binary"]
                entries = [e for e in b["files"] if e["path"] == b["path"]]
                if rec["plugin"]["format"] != "clap":
                    if b["path"].startswith("/"):
                        raise Refusal("path-absolute", label, f"binary.path {b['path']!r}: an LV2 record is relative already")
                    counts["lv2"] += 1
                    out.append((path, None))
                    continue
                if len(b["files"]) != 1:
                    raise Refusal("binary-files-not-one", label, f"binary.files holds {len(b['files'])} entries, a .clap is one file")
                entry = b["files"][0]
                if entry["sha256"] != b["sha256"]:
                    raise Refusal("key-not-the-binary", label, "binary.sha256 is not the SHA-256 of the file's entry")
                pf = os.path.join(d, rec["probe"]["file"])
                if not os.path.isfile(pf):
                    raise Refusal("probe-missing", label, f"{rec['probe']['file']}: no such probe output beside the record")
                with open(pf, encoding="utf-8") as fh:
                    offer = json.load(fh)["offer"]
                want = offer.get("clapExtensions")
                if want is None:
                    counts["nolist"] += 1
                if b["path"] == entry["path"] and rec.get("hostExtensions") == want and raw == text(rec):
                    counts["already"] += 1
                    out.append((path, None))
                    continue
                new = {}
                for k, v in rec.items():
                    if k == "hostExtensions":
                        continue
                    new[k] = v
                    if k == "binary":
                        new["binary"] = dict(b, path=entry["path"])
                        if want is not None:
                            new["hostExtensions"] = want
                counts["rewritten"] += 1
                out.append((path, text(new)))
    return out, counts


def main(argv):
    ap = argparse.ArgumentParser(prog="rewrite-records.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--records", required=True, help="the records/ directory: <class>/<set>/")
    a = ap.parse_args(argv)
    try:
        files, counts = plan(a.records)
    except Refusal as e:
        print(f"rewrite-records: refused: {e}", file=sys.stderr)
        return 1
    for path, new in files:
        if new is not None:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new)
    print(f"clap records rewritten: {counts['rewritten']}")
    print(f"clap records already in the form: {counts['already']}")
    print(f"clap records whose probe output holds no host extensions: {counts['nolist']}")
    print(f"lv2 records unchanged: {counts['lv2']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
