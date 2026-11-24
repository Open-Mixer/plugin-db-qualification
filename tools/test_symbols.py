"""The reader's symbols file names every function its public header declares.

dpkg-gensymbols only warns when the library exports a function that
debian/libplugin-qualification-db0.symbols does not name, so a function added
to the header would ship with no minimum version: a package built against it
could install beside an older library that lacks it. This test reads the
public header and the symbols file and fails naming each declared function the
file does not carry, and each name the file carries that the header no longer
declares.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADER = "include/plugin-qualification-db/pqdb.h"
SYMBOLS = "debian/libplugin-qualification-db0.symbols"


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def declared():
    return set(re.findall(r"^[A-Za-z_][\w \t*]*?\b(pqdb_\w+)\s*\(", read(HEADER), re.M))


def carried():
    return {m.group(1): m.group(2)
            for m in re.finditer(r"^ (pqdb_\w+)@Base (\S+)$", read(SYMBOLS), re.M)}


class Symbols(unittest.TestCase):
    def test_header_declares_functions(self):
        self.assertTrue(declared(), f"{HEADER}: no pqdb_ function found")

    def test_every_declared_function_is_carried(self):
        missing = sorted(declared() - set(carried()))
        self.assertEqual(missing, [], f"{SYMBOLS} does not name: {', '.join(missing)}")

    def test_every_carried_name_is_declared(self):
        stale = sorted(set(carried()) - declared())
        self.assertEqual(stale, [], f"{SYMBOLS} names what {HEADER} does not declare: {', '.join(stale)}")


if __name__ == "__main__":
    unittest.main()
