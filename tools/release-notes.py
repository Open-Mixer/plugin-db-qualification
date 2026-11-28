#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The proofs' findings joined to the release notes (release.yml, job proof-notes).

    release-notes.py <body file> <notes dir> <out notes file> <assets dir>

<body file> is the release body without an earlier proof section; <notes dir> holds proof-notes-<kind>-section.md, one per
proof. The `### UNPROVEN records` list of a section goes to <assets dir>/proof-notes-<kind>-records.md (the release asset
of that name); the notes keep its heading and one count line that names the asset. GitHub refuses a release body over
125000 characters (HTTP 422): notes still over it fail by name, exit 1."""
import glob
import os
import re
import sys

LIMIT = 125000
RECORDS = "### UNPROVEN records"


def split_records(section, kind):
    """(section with its records list replaced by a count line, the records block or None)"""
    lines = section.split("\n")
    start = next((i for i, l in enumerate(lines) if l.startswith(RECORDS)), None)
    if start is None:
        return section, None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("#")), len(lines))
    block = lines[start:end]
    n = sum(1 for l in block if l.startswith("- "))
    asset = f"proof-notes-{kind}-records.md"
    kept = [lines[start], "", f"{n} records, each named in the release asset {asset}", ""]
    return "\n".join(lines[:start] + kept + lines[end:]), "\n".join(block).rstrip("\n") + "\n"


def main(argv):
    if len(argv) != 5:
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    body_file, notes_dir, out_file, assets_dir = argv[1:]
    with open(body_file, encoding="utf-8") as f:
        notes = f.read().rstrip("\n") + "\n"
    for path in sorted(glob.glob(os.path.join(notes_dir, "proof-notes-*-section.md"))):
        kind = re.match(r"proof-notes-(.*)-section\.md$", os.path.basename(path)).group(1)
        with open(path, encoding="utf-8") as f:
            section, records = split_records(f.read(), kind)
        if records is not None:
            os.makedirs(assets_dir, exist_ok=True)
            with open(os.path.join(assets_dir, f"proof-notes-{kind}-records.md"), "w", encoding="utf-8") as f:
                f.write(records)
        notes += "\n" + section.rstrip("\n") + "\n"
    if len(notes) > LIMIT:
        print(f"release-notes: the notes are {len(notes)} characters, over GitHub's limit of {LIMIT} for a release body", file=sys.stderr)
        return 1
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
