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

    tools/rewrite-records.py --probe-format-2 --records DIR [--dry-run]

The re-cut to probe output format 2 (Open-Mixer/plugin-hostd#269): the cost unit is "nsPerSample", omx-contract's
RESOURCE_UNITS id, where format 1 wrote "ns-per-sample". It runs on a records branch checked out for the re-cut, never on
the branch the device wrote: that branch stays as it is. DIR is walked whole, so a fixture directory of records works as
records/ does. For every record, its probe output gets "formatVersion": "2.0" and each cost "unit": "nsPerSample", by
replacing those words in its text and nothing else (the device's layout stays), and the record's probe.sha256 and
probe.bytes name the new bytes, replaced in its text in the same way. The new text must parse to the old document with exactly those values changed.

Refused by name, nothing written: the probe output is missing (probe-missing), is not plugin-hostd.probe-output of
major 1 or 2 (probe-not-the-format), is not the bytes the record names (probe-not-the-records), or does not come out as
the old document with those values changed (probe-not-as-expected); the record does not come out as the old record
with only those two values changed (record-not-as-expected). The record's text is edited in those two values only, so
it keeps its own form. A probe output already at format 2 is counted and left. --dry-run plans and prints the counts and
writes nothing.
"""
import copy
import hashlib
import re
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


PROBE_FORMAT = "plugin-hostd.probe-output"
OLD_UNIT, NEW_UNIT = "ns-per-sample", "nsPerSample"
VERSION_1 = re.compile(r'"formatVersion": "1\.[0-9]+"')
UNIT_1 = '"unit": "%s"' % OLD_UNIT


def walk_records(records):
    """every record file under records, in byte order of its path"""
    for d, dirs, files in os.walk(records):
        dirs.sort(key=os.fsencode)
        for f in sorted(files, key=os.fsencode):
            if f.endswith(RECORD):
                yield d, f


def format2(raw, label):
    """the probe output's text at format 2, its count of cost units renamed; or None when it is format 2 already"""
    doc = json.loads(raw)
    version = str(doc.get("formatVersion", "")) if isinstance(doc, dict) else ""
    major = version.split(".")[0]
    if doc.get("format") != PROBE_FORMAT or major not in ("1", "2"):
        raise Refusal("probe-not-the-format", label, f"format {doc.get('format')!r} formatVersion {version!r}")
    if major == "2":
        if OLD_UNIT in raw:
            raise Refusal("probe-not-as-expected", label, f"format 2 but it holds {OLD_UNIT!r}")
        return None, 0
    want, renamed = copy.deepcopy(doc), 0
    want["formatVersion"] = "2.0"
    for point in want.get("grid") or []:
        cost = point.get("cost") if isinstance(point, dict) else None
        if isinstance(cost, dict) and cost.get("unit") == OLD_UNIT:
            cost["unit"] = NEW_UNIT
            renamed += 1
    new, n = VERSION_1.subn('"formatVersion": "2.0"', raw)
    if n != 1:
        raise Refusal("probe-not-as-expected", label, f"formatVersion is written {n} times, not once")
    new = new.replace(UNIT_1, '"unit": "%s"' % NEW_UNIT)
    if OLD_UNIT in new or json.loads(new) != want:
        raise Refusal("probe-not-as-expected", label, "the new text is not the old document with only formatVersion and the cost units changed")
    return new, renamed


def recut_record(raw, probe, want, label):
    """the record's text with only its probe.sha256 and probe.bytes values replaced: the record keeps its own text form"""
    if raw.count(probe["sha256"]) != 1:
        raise Refusal("record-not-as-expected", label, "the probe output's SHA-256 is not written once in the record")
    new = raw.replace(probe["sha256"], want["probe"]["sha256"])
    if "bytes" in probe and probe["bytes"] != want["probe"]["bytes"]:
        spots = [m for m in re.finditer(r'"bytes": %d(?![0-9.eE])' % probe["bytes"], new)]
        fits = [m for m in spots if json.loads(new[:m.start()] + '"bytes": %d' % want["probe"]["bytes"] + new[m.end():]) == want]
        if len(fits) != 1:
            raise Refusal("record-not-as-expected", label, "probe.bytes is not written once where the probe output is named")
        m = fits[0]
        new = new[:m.start()] + '"bytes": %d' % want["probe"]["bytes"] + new[m.end():]
    if json.loads(new) != want:
        raise Refusal("record-not-as-expected", label, "the new text is not the old record with only probe.sha256 and probe.bytes changed")
    return new


def plan_format2(records):
    """[(path, new bytes)] for every file the re-cut changes, and the counts; raises Refusal before anything is written."""
    out, counts, done = [], dict(records=0, recut=0, already=0, units=0), {}
    for d, f in walk_records(records):
        label = os.path.relpath(os.path.join(d, f), records)
        path = os.path.join(d, f)
        with open(path, "rb") as fh:
            rec_raw = fh.read().decode("utf-8")
        rec = json.loads(rec_raw)
        counts["records"] += 1
        probe = rec.get("probe") or {}
        pf = os.path.join(d, str(probe.get("file")))
        if not probe.get("file") or not os.path.isfile(pf):
            raise Refusal("probe-missing", label, f"{probe.get('file')}: no such probe output beside the record")
        with open(pf, "rb") as fh:
            data = fh.read()
        if hashlib.sha256(data).hexdigest() != probe.get("sha256") or probe.get("bytes", len(data)) != len(data):
            raise Refusal("probe-not-the-records", label, f"{probe['file']} is not the bytes the record names")
        if pf not in done:
            new, renamed = format2(data.decode("utf-8"), os.path.relpath(pf, records))
            done[pf] = None if new is None else new.encode("utf-8")
            if new is not None:
                out.append((pf, done[pf]))
                counts["units"] += renamed
        new_data = done[pf]
        if new_data is None:
            counts["already"] += 1
            continue
        want = copy.deepcopy(rec)
        want["probe"]["sha256"] = hashlib.sha256(new_data).hexdigest()
        if "bytes" in probe:
            want["probe"]["bytes"] = len(new_data)
        out.append((path, recut_record(rec_raw, probe, want, label).encode("utf-8")))
        counts["recut"] += 1
    return out, counts


def main(argv):
    ap = argparse.ArgumentParser(prog="rewrite-records.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--records", required=True, help="the records/ directory: <class>/<set>/")
    ap.add_argument("--probe-format-2", action="store_true", help="re-cut the probe outputs to format 2 (cost unit nsPerSample)")
    ap.add_argument("--dry-run", action="store_true", help="plan and print the counts, write nothing")
    a = ap.parse_args(argv)
    if a.probe_format_2:
        try:
            files, counts = plan_format2(a.records)
        except Refusal as e:
            print(f"rewrite-records: refused: {e}", file=sys.stderr)
            return 1
        if not a.dry_run:
            for path, new in files:
                with open(path, "wb") as fh:
                    fh.write(new)
        print(f"{'dry run, nothing written: ' if a.dry_run else ''}records read: {counts['records']}")
        print(f"records re-cut to probe format 2: {counts['recut']}")
        print(f"probe outputs re-cut: {len(files) - counts['recut']}")
        print(f"cost units renamed {OLD_UNIT} -> {NEW_UNIT}: {counts['units']}")
        print(f"records whose probe output is format 2 already: {counts['already']}")
        return 0
    if a.dry_run:
        ap.error("--dry-run goes with --probe-format-2")
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
