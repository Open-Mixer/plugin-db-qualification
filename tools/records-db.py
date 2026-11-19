#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""Builds the base qualification database from records/ (this repository's qualification store spec, section 5).

    records-db.py --records <dir> --out <file> --contract-dir <dir> [--built-from-file BUILT_FROM] [--class <class> ...]
                [--min-domain <domain>=<version> ...]

A build tool: it reads no environment variable. It writes a new file each run, to a temporary file in the output
directory renamed over --out only when every record is in and user_version is set; a refusal prints its name and
leaves no file. --class limits the build to the classes of one architecture (tools/sets.py list).
--min-domain refuses a domain whose info.version is lower than the floor given for it. The package's floors are its
Build-Depends on the contract packages; the flag is for a caller that builds from a contract directory of its own.
"""
import argparse
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qualification_db as q  # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser(prog="records-db.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--records", required=True, help="the records/ directory: <class>/<set>/")
    ap.add_argument("--out", required=True, help="the database file to write")
    ap.add_argument("--contract-dir", required=True, help="the installed contract directory: <domain>/<domain>.json")
    ap.add_argument("--built-from-file", help="a BUILT_FROM file holding the commit, for a tree with no .git")
    ap.add_argument("--min-domain", action="append", metavar="DOMAIN=VERSION",
                    help="refuse a domain whose info.version is lower (repeatable)")
    ap.add_argument("--class", dest="classes", action="append", help="build only this class (repeatable)")
    a = ap.parse_args(argv)
    try:
        q.build_base(a.records, a.out, a.contract_dir, a.built_from_file, a.classes, a.min_domain)
    except q.Refusal as e:
        print(f"records-db: refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
