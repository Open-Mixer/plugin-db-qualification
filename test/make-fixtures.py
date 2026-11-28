#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""Builds the fixture stores of the reader's tests from schema/qualification.sql: a base, user layers, stores at
other versions, a user layer with a hot journal, and the figures a reader must give back, worked out here from the
fixture data by the rules of plugin-hostd's qualcost.h (not by the reader). Usage: make-fixtures.py <out dir>."""
import os, re, shutil, signal, sqlite3, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, "..", "schema", "qualification.sql")
# the store's version, as the DDL's header gives it (the writer reads it there too)
with open(SCHEMA, encoding="utf-8") as _f:
    VERSION = int(re.search(r"^-- The qualification store, user_version (\d+)", _f.read(), re.M).group(1))

def sha(c):
    return c * 64

P1, P1X, P2, P3, P4, P5 = sha("a"), sha("b"), sha("c"), sha("d"), sha("7"), sha("8")
SYS_SHA, HOME_SHA, XDG_SHA = sha("1"), sha("2"), sha("3")

# (table, column, domain, item): the word columns the fixtures fill, as section 3.4 names them
WORD_CHECK = [
    ("plugin", "format", "plugin-db", "PLUGIN_DB_ADDRESS_FORMATS"),
    ("record_set", "host_class", "qualification", "QUALIFICATION_HOST_CLASSES"),
    ("record", "host_class", "qualification", "QUALIFICATION_HOST_CLASSES"),
    ("record_set", "tier", "qualification", "QUALIFICATION_SET_TIERS"),
    ("record_set", "host_profile", "qualification", "QUALIFICATION_HOST_PROFILES"),
    ("verdict", "host", "qualification", "QUALIFICATION_HOST_PROFILES"),
    ("record", "adapter_host", "qualification", "QUALIFICATION_ADAPTER_HOSTS"),
    ("record", "offer", "qualification", "QUALIFICATION_OFFERS"),
    ("record", "pkg_format", "qualification", "QUALIFICATION_PACKAGE_FORMATS"),
    ("record", "pkg_distro", "qualification", "QUALIFICATION_PACKAGE_DISTROS"),
    ("record", "pkg_arch", "qualification", "QUALIFICATION_PACKAGE_ARCHES"),
    ("record", "mc_arch", "machine", "MACHINE_ARCHES"),
    ("record", "mc_family", "machine", "MACHINE_FAMILIES"),
    ("record", "mc_core_band", "machine", "MACHINE_CORE_BANDS"),
    ("record", "mc_clock_band", "machine", "MACHINE_CLOCK_BANDS"),
    ("record", "probe_reason", "probe", "PROBE_REASONS"),
    ("record", "probe_outcome", "probe", "PROBE_OUTCOMES"),
    ("cell", "outcome", "probe", "PROBE_OUTCOMES"),
    ("cell", "outcome", "qualification", "QUALIFICATION_MEMORY_BOUND_OUTCOMES"),
    ("verdict", "rating", "qualification", "QUALIFICATION_MEASUREMENT_VERDICT_RATINGS"),
    ("verdict", "hosting", "qualification", "QUALIFICATION_VERDICT_HOSTINGS"),
    ("verdict", "arm", "qualification", "QUALIFICATION_VERDICT_ARMS"),
    ("verdict", "deciding", "probe", "PROBE_OUTCOMES"),
    ("verdict", "deciding", "hosting", "HOSTING_COST_CODES"),
    ("verdict", "deciding", "hosting", "HOSTING_MEMORY_CODES"),
    ("verdict", "deciding", "hosting", "HOSTING_LATENCY_CODES"),
    ("record", "adapter_code", "qualification", "QUALIFICATION_ADAPTER_HOSTS"),
    ("record", "adapter_code", "qualification", "QUALIFICATION_ADAPTER_CODE_KINDS"),
    ("record", "adapter_code", "probe", "PROBE_SIGNALS"),
    # the hosting columns (section 3.4), checked as any: mixed with probe words, or hosting words only
    ("history_verdict", "host", "qualification", "QUALIFICATION_HOST_PROFILES"),
    ("history_verdict", "measured", "qualification", "QUALIFICATION_PIN_VERDICTS"),
    ("history_verdict", "adjusted", "qualification", "QUALIFICATION_PIN_VERDICTS"),
    ("history_verdict", "move", "qualification", "QUALIFICATION_HISTORY_MOVES"),
    ("history_verdict", "reason", "qualification", "QUALIFICATION_HISTORY_REASONS"),
    ("history_blocked", "code", "qualification", "QUALIFICATION_HISTORY_BLOCKERS"),
    ("history_blocked", "code", "hosting", "HOSTING_COST_CODES"),
    ("history_blocked", "code", "hosting", "HOSTING_MEMORY_CODES"),
    ("history_blocked", "code", "hosting", "HOSTING_LATENCY_CODES"),
    ("tier", "deciding", "probe", "PROBE_OUTCOMES"),
    ("tier", "deciding", "hosting", "HOSTING_COST_CODES"),
    ("tier", "deciding", "hosting", "HOSTING_MEMORY_CODES"),
    ("tier", "deciding", "hosting", "HOSTING_LATENCY_CODES"),
    ("reason", "code", "hosting", "HOSTING_COST_CODES"),
    ("reason", "code", "hosting", "HOSTING_MEMORY_CODES"),
    ("reason", "code", "hosting", "HOSTING_LATENCY_CODES"),
    ("not_measured", "code", "hosting", "HOSTING_COST_CODES"),
    ("not_measured", "code", "hosting", "HOSTING_MEMORY_CODES"),
    ("not_measured", "code", "hosting", "HOSTING_LATENCY_CODES"),
    ("adapter_cell", "code", "qualification", "QUALIFICATION_ADAPTER_HOSTS"),
    ("adapter_cell", "code", "qualification", "QUALIFICATION_ADAPTER_CODE_KINDS"),
    ("adapter_cell", "code", "probe", "PROBE_SIGNALS"),
]
DOMAINS = {"qualification": "1.1.0", "machine": "1.0.0", "probe": "1.0.0", "hosting": "0.1.0", "plugin-db": "1.0.0"}

def cell(rate, quantum, cost=None, lat=(None, None), mem=None, outcome="probe.ok"):
    """cost: (median, p, p value); lat: (declared, measured); mem: (first kb, per instance kb)."""
    return dict(rate=rate, quantum=quantum, cost=cost, lat=lat, mem=mem, outcome=outcome)

def rec(key, offer, cls, cells, set=None, pkg=None, adapter_code=None, cell_code=None, verdict_rating="qualified",
        bpath=None, files=None, layout=None, unpinnable=None, tested=None, offered=False, tier="reference",
        measured="2026-11-09", reasons=(), steps=(), verdict_measured=1, history=()):
    """bpath: the binary's path below its install root (default: the file's own name); files: the per-file list as
    (path, sha256) in byte order of the path, which holds bpath at the key's SHA-256 (default: that one entry);
    layout: (scheme, sha256); unpinnable: 1 for a record that holds it; tested: testedVersion;
    offered: the record has a tier_offered row (a tier the plugin is offered on); tier: the tier of the record's set
    (record_set.tier); measured: its set's measurement date (record_set.measured); reasons: the (rating, code) of the
    omx-clap-host verdict's reasons; steps: the run's (step, result) in order; verdict_measured: that verdict's measured; history: the adjust blocks, each
    (host class, [(host, measured word, adjusted word or None)])."""
    bpath = bpath or key[2].split(":")[-1] + (".clap" if key[1] == "clap" else ".so")
    return dict(key=key, offer=offer, cls=cls, cells=cells, set=set, pkg=pkg, adapter_code=adapter_code,
                cell_code=cell_code, verdict_rating=verdict_rating, bpath=bpath, files=files or [(bpath, key[0])],
                layout=layout or (None, None), unpinnable=unpinnable, tested=tested, offered=offered, tier=tier,
                measured=measured, reasons=reasons, steps=steps, verdict_measured=verdict_measured, history=history)

BASE = [
    rec((P1, "clap", "urn:p1"), "default", "x86-64", set="fedora44-48000-256", adapter_code="omx-clap-host.signal-SIGSEGV",
        cell_code="omx-clap-host.resp-3", verdict_rating="conditional", layout=("elf-sections", sha("f")), tested="1.2.3",
        offered=True, cells=[cell(48000, 256, (100.5, 95, 150.25), (64, 128), (2048, 512)),
                             cell(96000, 256, (200.0, 95, 300.0), (256, None), (4096, 1024))]),
    rec((P1, "clap", "urn:p1"), "custom", "x86-64", set="fedora44-48000-256",
        cells=[cell(48000, 256, (101.0, 95, 151.0), (64, 130), (2000, 500))]),
    rec((P1, "clap", "urn:p1"), "default", "rpi5", set="zynthian-vangelis",
        cells=[cell(48000, 256, (300.0, 95, 450.0), (None, 200), None)]),
    rec((P2, "clap", "urn:p2"), "default", "x86-64", set="fedora44-48000-256", unpinnable=1,
        cells=[cell(48000, 256, (80.0, None, None), (None, None), (1024, None))]),
    # an LV2 bundle: the list in byte order (a capital before a lower-case letter), the key the binary's entry
    rec((P3, "lv2", "urn:p3"), "default", "x86-64", set="fedora44-48000-256", bpath="p3.so", offered=True,
        files=[("Z-extra.ttl", sha("5")), ("manifest.ttl", sha("6")), ("p3.so", P3), ("p3.ttl", sha("7"))],
        cells=[cell(48000, 256, (10.0, 95, 12.0), (32, 40), (512, 64), outcome="probe.crashed")]),
    # the same file name below another directory, for the exact filter of binary_path
    rec((P4, "clap", "urn:p4"), "default", "x86-64", set="fedora44-48000-256", bpath="Sub/p1.clap",
        cells=[cell(48000, 256, (20.0, 95, 21.0), (1, 2), (3, 4))]),
]
USER = [
    rec((P1, "clap", "urn:p1"), "default", "x86-64", pkg=("rpm", "clap-dexed", "1.1.0", "4.fc44", "fc44", "x86_64"),
        cells=[cell(48000, 256, (111.0, 95, 160.0), (64, 128), None)]),
    rec((P1X, "clap", "urn:p1"), "default", "x86-64", cells=[cell(48000, 256, (5.0, 95, 6.0), (1, 2), (3, 4))]),
    rec((P2, "clap", "urn:p2"), "custom", "x86-64", offered=True, cells=[cell(48000, 256, (7.0, 95, 8.0), (1, 2), (3, 4))]),
    rec((P2, "clap", "urn:p2"), "default", "rpi5", cells=[cell(48000, 256, (9.0, 95, 10.0), (1, 2), (3, 4))]),
    # the same name in another case: a different path
    rec((P5, "clap", "urn:p5"), "default", "x86-64", bpath="P1.clap", cells=[cell(48000, 256, (30.0, 95, 31.0), (1, 2), (3, 4))]),
]

def word_checks(c, unchecked=()):
    """unchecked: the (table, column) pairs left out of the check, for a fixture of words the fixture contract lacks"""
    c.executemany("INSERT INTO store_domain VALUES (?, ?)", sorted(DOMAINS.items()))
    c.executemany("INSERT INTO word_check VALUES (?, ?, ?, ?)", [w for w in WORD_CHECK if (w[0], w[1]) not in unchecked])

def claimants(records):
    """{record index: the cells it claims} by the base's rule (the store spec, section 4): one record per key, offer, class
    and cell; when a set of the reference tier and a set of another tier both hold a cell, the reference tier's record
    claims it, whichever comes first; when two sets of one tier hold it, the record of the set measured later claims it
    (an equal date is refused, claim-duplicate)."""
    held = {}
    for n, r in enumerate(records):
        for ce in r["cells"]:
            held.setdefault((r["key"], r["offer"], r["cls"], ce["rate"], ce["quantum"]), []).append(n)
    out = {n: set() for n in range(len(records))}
    for (key, offer, cls, rate, quantum), ns in held.items():
        ref = [n for n in ns if records[n]["tier"] == "reference"]
        pool = ref or ns
        if len({records[n]["tier"] for n in pool}) > 1:
            raise SystemExit("claim-duplicate: %s %s %s at %d/%d" % (key[2], offer, cls, rate, quantum))
        newest = max(records[n]["measured"] for n in pool)
        top = [n for n in pool if records[n]["measured"] == newest]
        if len(top) != 1:
            raise SystemExit("claim-duplicate: %s %s %s at %d/%d" % (key[2], offer, cls, rate, quantum))
        out[top[0]].add((rate, quantum))
    return out

def build(path, layer, records, version=VERSION, adapter_code_override=None, filler=False, unchecked=()):
    if os.path.exists(path):
        os.unlink(path)
    c = sqlite3.connect(path)
    c.execute("PRAGMA journal_mode = DELETE")
    c.execute("PRAGMA page_size = 4096")
    c.executescript(open(SCHEMA).read())
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("INSERT INTO store_info VALUES (1, ?, 'plugin-qualify.qualification-record/1', ?)",
              (layer, None if layer else "0123456789abcdef0123456789abcdef01234567"))
    word_checks(c, unchecked)
    plugin, sets = {}, {}
    claims = claimants(records)
    for n, r in enumerate(records):
        pid = plugin.setdefault(r["key"], len(plugin) + 1)
        if pid == len(plugin) and c.execute("SELECT 1 FROM plugin WHERE plugin_id = ?", (pid,)).fetchone() is None:
            c.execute("INSERT INTO plugin VALUES (?, ?, ?, ?)", (pid, *r["key"]))
        set_id = None
        if r["set"] is not None:
            skey = (r["cls"], r["set"])
            if skey not in sets:
                sets[skey] = len(sets) + 1
                c.execute("INSERT INTO record_set VALUES (?, ?, ?, 'plugin-qualify.provenance/1', ?, "
                          "'omx-clap-host', ?, '2026-11-19', 'plugin-qualification-records', '1')",
                          (sets[skey], r["cls"], r["set"], r["tier"], r["measured"]))
            set_id = sets[skey]
        pkg = r["pkg"] or (None,) * 6
        code = adapter_code_override or r["adapter_code"]
        rid = n + 1
        c.execute("""INSERT INTO record (record_id, plugin_id, set_id, host_class, offer, name, schema,
            pkg_format, pkg_name, pkg_version, pkg_release, pkg_distro, pkg_arch, binary_path, measured_at, run_id,
            tool_runner, tool_child, probe_file, probe_sha256, probe_bytes, probe_protocol, probe_protocol_version,
            probe_reason, probe_outcome, probe_complete, probe_meets_protocol, probe_loadavg1, probe_cores,
            mc_arch, mc_family, mc_core_band, mc_clock_band, mc_preempt_rt, mc_cstates_limited,
            adapter_admitted, adapter_host, adapter_measured, adapter_code, adapter_params)
            VALUES (?, ?, ?, ?, ?, ?, 'plugin-qualify.qualification-record/1', ?, ?, ?, ?, ?, ?, ?,
            '2026-11-19T00:00:00Z', 'run', 'runner', 'child', 'p.probe.json', ?, 10, 'probe', 1,
            'on-request', 'probe.ok', 1, 1, 0.5, 4, 'x86_64', 'zen4', 'cores-4', 'ghz-3', 0, 0,
            ?, ?, ?, ?, ?)""",
                  (rid, pid, set_id, r["cls"], r["offer"], "rec%d" % rid, *pkg, r["bpath"], "e" * 64,
                   1 if code else None, "omx-clap-host" if code else None, 1 if code else None, code,
                   0 if code else None))
        # section 3.7: the list holds the binary's entry, and the key is that entry's SHA-256
        if r["offered"]:
            c.execute("INSERT INTO tier_offered VALUES (?, 0, 'isolated')", (rid,))
        for o, (path, digest) in enumerate(r["files"]):
            c.execute("INSERT INTO record_file VALUES (?, ?, ?, ?)", (rid, o, path, digest))
        c.execute("UPDATE record SET layout_scheme = ?, layout_sha256 = ?, unpinnable = ?, tested_version = ? WHERE record_id = ?",
                  (*r["layout"], r["unpinnable"], r["tested"], rid))
        c.execute("INSERT INTO verdict VALUES (?, 0, 'omx-clap-host', ?, ?, 1, 'isolated', 'run', NULL)",
                  (rid, r["verdict_measured"], r["verdict_rating"]))
        for o, (rating, code) in enumerate(r["reasons"]):
            c.execute("INSERT INTO reason (record_id, verdict_ord, cost_ord, ord, dimension, rating, code) "
                      "VALUES (?, 0, NULL, ?, 'rtSafety', ?, ?)", (rid, o, rating, code))
        for o, (step, result) in enumerate(r["steps"]):
            c.execute("INSERT INTO run_step (record_id, ord, step, result) VALUES (?, ?, ?, ?)", (rid, o, step, result))
        for h, (klass, verdicts) in enumerate(r["history"]):
            c.execute("INSERT INTO record_history (record_id, ord, host_class, file, at, found) VALUES (?, ?, ?, 'history', "
                      "'2026-11-28T00:00:00Z', 1)", (rid, h, klass))
            for o, (host, measured_word, adjusted) in enumerate(verdicts):
                c.execute("INSERT INTO history_verdict (record_id, history_ord, ord, host, measured, adjusted, move, reason) "
                          "VALUES (?, ?, ?, ?, ?, ?, 'demote', 'history.crashed')", (rid, h, o, host, measured_word, adjusted))
        c.execute("INSERT INTO verdict VALUES (?, 1, 'openmixer-console', 1, 'qualified', 1, 'in-process', "
                  "'declaration', 'probe.crashed')", (rid,))
        for o, ce in enumerate(r["cells"]):
            co = ce["cost"] or (None, None, None)
            me = ce["mem"] or (None, None)
            c.execute("""INSERT INTO cell (record_id, ord, rate, quantum, outcome, latency_declared_frames,
                latency_measured_frames, cost_median, cost_percentile_p, cost_percentile_value,
                mem_first_instance_kb, mem_per_instance_kb) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (rid, o, ce["rate"], ce["quantum"], ce["outcome"], ce["lat"][0], ce["lat"][1],
                       co[0], co[1], co[2], me[0], me[1]))
            if (ce["rate"], ce["quantum"]) in claims[n]:
                c.execute("INSERT INTO claim VALUES (?, ?, ?, ?, ?, ?)", (rid, pid, r["offer"], r["cls"], ce["rate"], ce["quantum"]))
        if r["cell_code"]:
            c.execute("INSERT INTO adapter_cell VALUES (?, 0, 48000, 256, 1, 1, ?, 0)", (rid, r["cell_code"]))
    if filler:
        c.execute("CREATE TABLE filler (b BLOB)")
        c.executemany("INSERT INTO filler VALUES (zeroblob(3000))", [() for _ in range(300)])
    c.commit()
    c.execute("VACUUM")
    c.execute("PRAGMA user_version = %d" % version)
    c.commit()
    c.close()

# ---- the records store: rich records, to read back whole (spec section 8, change 3, case 21) ----
# the tier pick: the same key, offer, class and cell from a provisional set and from a reference set
TIERS = [
    rec((P1, "clap", "urn:p1"), "default", "x86-64", set="fedora44-48000-256", tier="provisional", verdict_rating="conditional",
        offered=True, bpath="prov/p1.clap", files=[("prov/p1.clap", P1)], cells=[cell(48000, 256, (900.0, 95, 990.0), (64, 640), (8192, 4096))]),
    rec((P1, "clap", "urn:p1"), "default", "x86-64", set="fedora44-rt-48000-256", tier="reference", verdict_rating="qualified",
        bpath="ref/p1.clap", files=[("ref/p1.clap", P1)], cells=[cell(48000, 256, (100.0, 95, 110.0), (64, 128), (2048, 512))]),
]

# the newer pick (ruling 2026-11-20): the same key, offer, class and cell from two sets of one tier (hardware), the
# whole-grid set measured 2026-11-06 and the one-cell set measured again on 2026-11-08
NEWER = [
    rec((P1, "clap", "urn:p1"), "default", "rpi5", set="zynthian-vangelis", tier="hardware", measured="2026-11-06",
        verdict_rating="conditional", bpath="old/p1.clap", files=[("old/p1.clap", P1)],
        cells=[cell(48000, 256, (300.0, 95, 450.0), (None, 200), None)]),
    rec((P1, "clap", "urn:p1"), "default", "rpi5", set="zynthian-vangelis-48000-256", tier="hardware", measured="2026-11-08",
        verdict_rating="qualified", bpath="new/p1.clap", files=[("new/p1.clap", P1)],
        cells=[cell(48000, 256, (120.0, 95, 130.0), (None, 64), None)]),
]

# the claimant of each cell (the store spec, section 4), with two cells a key: the sets hold one key at two cells, and
# the winner of the first cell is not the winner of the second. The winner is named to sort LAST in byte order of the
# sets' names, so no order of names picks it: for the tier pair the provisional set claims 96000/256 alone and the
# reference set 48000/256; for the re-measure the old set claims 96000/256 alone and the newer one 48000/256
CLAIMANTS = [
    rec((P1, "clap", "urn:p1"), "default", "x86-64", set="fedora44-48000-256", tier="provisional", bpath="prov/p1.clap",
        files=[("prov/p1.clap", P1)], verdict_rating="conditional",
        cells=[cell(48000, 256, (900.0, 95, 990.0), (64, 640), (8192, 4096)), cell(96000, 256, (950.0, 95, 995.0), (64, 640), (8192, 4096))]),
    rec((P1, "clap", "urn:p1"), "default", "x86-64", set="fedora44-rt-48000-256", tier="reference", bpath="ref/p1.clap",
        files=[("ref/p1.clap", P1)], cells=[cell(48000, 256, (100.0, 95, 110.0), (64, 128), (2048, 512))]),
    rec((P2, "clap", "urn:p2"), "default", "x86-64", set="a-old", tier="hardware", measured="2026-11-06", bpath="old/p2.clap",
        files=[("old/p2.clap", P2)], verdict_rating="conditional",
        cells=[cell(48000, 256, (70.0, 95, 80.0), (None, 70), None), cell(96000, 256, (71.0, 95, 81.0), (None, 71), None)]),
    rec((P2, "clap", "urn:p2"), "default", "x86-64", set="z-new", tier="hardware", measured="2026-11-08", bpath="new/p2.clap",
        files=[("new/p2.clap", P2)], cells=[cell(48000, 256, (60.0, 95, 65.0), (None, 60), None)]),
]

RICH = [
    rec((P1, "clap", "urn:p1"), "default", "x86-64", set="fedora44-48000-256", adapter_code="omx-clap-host.signal-SIGSEGV",
        cell_code="omx-clap-host.resp-3", verdict_rating="conditional", layout=("elf-sections", sha("f")), tested="1.2.3",
        unpinnable=1, cells=[cell(48000, 256, (100.5, 95, 150.25), (64, 128), (2048, 512)),
                             cell(96000, 256, (200.0, 95, 300.0), (256, None), (4096, 1024))]),
    rec((P3, "lv2", "urn:p3"), "default", "x86-64", set="fedora44-48000-256", bpath="p3.so",
        files=[("Z-extra.ttl", sha("5")), ("manifest.ttl", sha("6")), ("libSurge%20XT.so", sha("9")), ("p3.so", P3)],
        cells=[cell(48000, 256, (10.0, 95, 12.0), (32, 40), (512, 64), outcome="probe.crashed")]),
    rec((P2, "clap", "urn:p2"), "default", "x86-64", set="fedora44-48000-256",
        cells=[cell(48000, 256, (80.0, None, None), (None, None), (1024, None))]),
]
RICH[1]["files"].sort(key=lambda f: f[0].encode())

def fill_nulls(c, table, where, skip=(), flags=(), bools=()):
    """Gives every NULL column of one row of `table` a value of its own (a number or a word named after its
    column), so that every column reaches the exported record and a swapped pair of columns is seen."""
    checked = {col for t, col, _, _ in WORD_CHECK if t == table}
    cols = c.execute("PRAGMA table_info(%s)" % table).fetchall()
    n = 10
    sets = {}
    for _, name, typ, notnull, _, pk in cols:
        v = c.execute("SELECT %s FROM %s WHERE %s" % (name, table, where)).fetchone()[0]
        if v is not None or name in skip or name in checked or pk:
            continue
        n += 1
        val = (1 if name in bools else n * 7 + 1) if typ == "INTEGER" else (n + 0.25 if typ == "REAL" else "w_" + name)
        if name in flags:
            val = 1
        sets[name] = val
    # one UPDATE, so a CHECK over several columns (all three counts or none) sees them together
    if sets:
        c.execute("UPDATE %s SET %s WHERE %s" % (table, ", ".join("%s = ?" % k for k in sets), where), list(sets.values()))

# numbers as JSON.stringify writes them (the cell's latencyMs, the record's latencyLineMs): what is stored, in the order of
# the cells, and what the document must hold for each
NUMBERS = [1e-7, 0.000001, 123e-20, 1e21, 1.5e300, 5e-324, -0.0, 100.0, 0.1, 2 / 3]

def build_numbers(path):
    build(path, 0, [rec((P1, "clap", "urn:p1"), "default", "x86-64", set="fedora44-48000-256",
                        cells=[cell(48000, 64 + i, (1.0, 95, 2.0), (1, 2), (3, 4)) for i in range(len(NUMBERS))])])
    c = sqlite3.connect(path)
    for i, v in enumerate(NUMBERS):
        c.execute("UPDATE cell SET latency_ms = ? WHERE record_id = 1 AND ord = ?", (v, i))
    c.commit(); c.close()

def build_nonfinite(path, table_sql):
    """A store holding a REAL that is not finite (SQLite keeps 1e999 as Infinity): the reader must refuse it by name."""
    build(path, 0, [rec((P1, "clap", "urn:p1"), "default", "x86-64", set="fedora44-48000-256",
                        cells=[cell(48000, 256, (1.0, 95, 2.0), (1, 2), (3, 4))])])
    c = sqlite3.connect(path)
    c.execute(table_sql)
    c.commit(); c.close()

def build_records(path):
    build(path, 0, RICH)
    c = sqlite3.connect(path)
    c.execute("PRAGMA foreign_keys = ON")
    # record 1 holds every column; 2 is an LV2 record with none of the CLAP-only parts; 3 a CLAP record with an empty extension list
    fill_nulls(c, "record", "record_id = 1", skip=("pkg_format", "pkg_name", "pkg_version", "pkg_release", "pkg_distro", "pkg_arch", "rules", "latency_line_ms"),
               flags=("host_extensions", "adapter_params", "unpinnable"))
    # strings the JSON must escape or pass through exactly: a non-ASCII letter (2 bytes) and a 4-byte character, the
    # control characters U+0001 and U+001F, the named escapes, a quote and a backslash, and DEL, which is not escaped
    c.execute("UPDATE record SET run_id = ?, tool_interposer = ?, tested_version = ? WHERE record_id = 1",
              ("run-\u00e9-\u0001-\u001f", "q\"b\\n\n\t\r\b\f\x7f", "1.2.3-\u00e9\U0001d11e"))
    # latencyLineMs, rules and a cell's latencyMs (section 3.5): shortest decimals that read back the same double
    c.execute("UPDATE record SET latency_line_ms = 0.1, rules = 'plugin-qualify-rules/1.2' WHERE record_id = 1")
    c.execute("UPDATE record SET latency_line_ms = 10, rules = 'plugin-qualify-rules/2.0' WHERE record_id = 3")
    c.execute("UPDATE cell SET latency_ms = 1.3333333333333333 WHERE record_id = 1 AND ord = 0")
    c.execute("UPDATE cell SET latency_ms = 0.30000000000000004 WHERE record_id = 1 AND ord = 1")
    c.execute("UPDATE cell SET latency_ms = 2.0 WHERE record_id = 3 AND ord = 0")
    c.execute("UPDATE record SET host_extensions = 1 WHERE record_id = 3")
    c.execute("UPDATE record SET adapter_params = NULL WHERE record_id = 3")
    # record 1's adapter.params is present: its rows (resp, step, gain) and its content names reach the document
    c.execute("UPDATE record SET adapter_params = 1 WHERE record_id = 1")
    for rid in (1, 2, 3):
        c.execute("UPDATE record SET layout_scheme = NULL, layout_sha256 = NULL WHERE record_id = ? AND ? <> 1", (rid, rid))
    fill_nulls(c, "cell", "record_id = 1 AND ord = 0", skip=("rt_other_allocations", "rt_other_locks", "rt_other_syscalls", "latency_ms"), bools=("rt_interposer", "rt_swept", "rt_sweep_applicable", "note_sweep_applicable"), flags=("rt_events",))
    c.execute("UPDATE cell SET rt_other_allocations = 11, rt_other_locks = 12, rt_other_syscalls = 13 WHERE record_id = 1 AND ord = 0")
    c.execute("UPDATE cell SET rt_own_threads = 2 WHERE record_id = 1 AND ord = 1")   # own threads, and no other-thread counts
    c.execute("UPDATE cell SET rt_interposer = 0, rt_swept = 0, rt_sweep_applicable = 0, rt_blocks = 0, rt_allocations = 0, rt_locks = 0, rt_syscalls = 0, rt_events = 1 WHERE record_id = 1 AND ord = 1")
    c.executemany("INSERT INTO record_extension VALUES (1, ?, ?)", [(0, "clap.log"), (1, "clap.params")])
    c.executemany("INSERT INTO cell_event VALUES (1, 0, ?, ?)", [(0, "malloc"), (1, "pthread_mutex_lock")])
    c.executemany("INSERT INTO record_version VALUES (1, ?, ?, ?)", [(0, "omx-clap-host", "1.0"), (0, "other", "2.0"), (1, "omx-clap-host", "1.1")])
    c.executemany("INSERT INTO adapter_param VALUES (1, ?, ?, ?)", [("resp", 3, None), ("step", None, "add"), ("gain", 0.5, None)])
    c.execute("INSERT INTO adapter_cell_param VALUES (1, 0, 'peak', 0.5, NULL)")
    c.execute("INSERT INTO adapter_cell VALUES (1, 1, 96000, 256, 0, 0, NULL, 1)")   # params present and empty
    c.execute("UPDATE adapter_cell SET params = 1 WHERE record_id = 1 AND ord = 0")
    c.executemany("INSERT INTO run_step VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  [(0, "instantiate", "ok", None, None, None, None, None, None, None, None, None, None, None, None, None),
                   (1, "process", "ok", "probe.ok", 12.5, 64, 2, 3, 4, 5, 6, 7, 31.25, 18.5, 3, 0)])
    # history (adjust --history): a full block, and a block of a class the history has no line for
    c.execute("UPDATE record SET plugin_name = 'The P1 \u00e9' WHERE record_id = 1")
    c.execute("INSERT INTO record_history VALUES (1, 0, 'x86_64/8/ghz-3', 'history-1.json', '2026-11-19T20:00:00Z', 'urn:p1', 'dd', 1, 400, 40, 0, 1, 1)")
    c.execute("INSERT INTO record_history VALUES (1, 1, 'aarch64/4/ghz-2', 'history-2.json', '2026-11-19T20:01:00Z', NULL, NULL, 0, NULL, NULL, NULL, NULL, NULL)")
    c.executemany("INSERT INTO history_unknown_key VALUES (1, 0, ?, ?)", [("extra", "1"), ("zeta", "two")])
    c.executemany("INSERT INTO history_verdict VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)",
                  [(0, 0, "omx-clap-host", "isolated", "refused", "demote", "history.crashed", None),
                   (0, 1, "openmixer-console", None, None, "none", "history.not-liftable", 1),
                   (1, 0, "omx-clap-host", "in-process", "in-process", "none", "history.no-record", None)])
    c.executemany("INSERT INTO history_blocked VALUES (1, 0, 1, ?, ?)", [(0, "refused"), (1, "hosting.cost.above-ceiling"), (2, "no-deciding-reason")])
    c.executemany("INSERT INTO probe_end VALUES (1, ?, ?, ?, ?, ?)", [(0, "process", "probe.ok", 0, None), (1, "exit", "probe.crashed", None, "SIGSEGV")])
    c.executemany("INSERT INTO cost_entry (record_id, ord, host, rate, quantum) VALUES (1, ?, ?, ?, ?)", [(0, "omx-clap-host", 48000, 256)])
    fill_nulls(c, "cost_entry", "record_id = 1 AND ord = 0")   # the voices an instrument's entry was taken with (ruling 12)
    # an instrument's cost at each count of notes held, in ord (ruling 12)
    c.executemany("INSERT INTO cell_voice_point VALUES (1, 0, ?, ?, ?, 95, ?)", [(0, 1, 11.5752, 11.7705), (1, 16, 11.8682, 12.3027)])
    c.executemany("INSERT INTO reason (reason_id, record_id, verdict_ord, cost_ord, ord, dimension, rating, code) VALUES (?, 1, ?, ?, ?, ?, ?, ?)",
                  [(1, 0, None, 0, "cost", "conditional", "hosting.cost.above-ceiling"), (2, 0, None, 1, "memory", "qualified", "hosting.memory.within-ceiling"),
                   (3, None, 0, 0, "cost", "conditional", "hosting.cost.above-ceiling")])
    c.executemany("INSERT INTO reason_param VALUES (?, ?, ?, ?)", [(1, "coreFractionP95", 0.37, None), (1, "blocks", 40, None), (1, "basis", None, "median"), (3, "blocks", 40, None)])
    c.executemany("INSERT INTO tier VALUES (1, ?, 'omx-clap-host', 1, 1, 'qualified', ?, ?)", [("inProcess", None, None), ("isolated", "probe.crashed", 1)])
    c.executemany("INSERT INTO tier_offered VALUES (1, ?, ?)", [(0, "isolated"), (1, "inProcess")])
    c.execute("INSERT INTO unmeasured VALUES (1, 0, 'memory', 'limit-exceeded', 96000, 256)")
    c.executemany("INSERT INTO feature_required VALUES (1, ?, ?)", [(0, "state"), (1, "params")])
    c.executemany("INSERT INTO not_measured VALUES (1, ?, ?, ?)", [(0, "latency", "hosting.latency.unmeasured")])
    c.executemany("INSERT INTO memory_run_cell VALUES (1, ?, ?, ?, ?)", [(0, 48000, 256, "probe.ok")])
    c.executemany("INSERT INTO rejudged_owe VALUES (1, ?, ?, ?)", [(0, "figures-unreadable", "cost")])
    c.commit()
    c.execute("VACUUM")
    c.close()

def reference(layers):
    """The results a reader must give: the rules of qualcost.h applied to the fixture data, the shadow rule of
    section 4 applied here separately. layers: [(name, records)], user first."""
    rows, shadow = [], set()
    for name, records in layers:
        out = []
        for r in records:
            skey = (*r["key"], r["offer"], r["cls"])
            if name == "base" and skey in shadow:
                continue
            for ce in r["cells"]:
                cost = ce["cost"] or (None, None, None)
                has_cost = cost[0] is not None and cost[2] is not None
                lat = ce["lat"][1] if ce["lat"][1] is not None else ce["lat"][0]
                mem = ce["mem"] or (None, None)
                has_mem = mem[0] is not None and mem[1] is not None
                out.append((*skey[:3], r["offer"], r["cls"], ce["rate"], ce["quantum"], name, r["set"] or "-",
                            ce["outcome"], cost[0] if has_cost else 0.0, cost[2] if has_cost else 0.0,
                            cost[1] if has_cost else 0, int(has_cost), lat if lat is not None else 0,
                            int(lat is not None), mem[0] if has_mem else 0, mem[1] if has_mem else 0, int(has_mem)))
        out.sort(key=lambda t: t[:7])
        rows += out
        if name == "user":
            shadow = {(*r["key"], r["offer"], r["cls"]) for r in records}
    return rows

def counts(layers):
    """What a layer holds per plugin (a format and a uri), by format: (format, plugins, offered, not offered). A plugin
    is offered when any of its records has a tier_offered row. layers: [(name, records)], user first; a base record
    its user layer shadows is not counted (section 4)."""
    plugins, shadow = {}, set()
    for name, records in layers:
        for r in records:
            skey = (*r["key"], r["offer"], r["cls"])
            if name == "base" and skey in shadow:
                continue
            k = (r["key"][1], r["key"][2])
            plugins[k] = plugins.get(k, False) or bool(r["offered"])
        if name == "user":
            shadow = {(*r["key"], r["offer"], r["cls"]) for r in records}
    out = []
    for fmt in sorted({k[0] for k in plugins}):
        flags = [v for k, v in plugins.items() if k[0] == fmt]
        out.append((fmt, len(flags), sum(flags), len(flags) - sum(flags)))
    return out

def write_expect(path, rows):
    with open(path, "w") as f:
        for t in rows:
            f.write("\t".join(repr(v) if isinstance(v, float) else str(v) for v in t) + "\n")

def hot_journal(src, dst):
    """A user layer whose writer was killed inside a transaction: the file and its -journal."""
    shutil.copy(src, dst)
    code = ("import os, signal, sqlite3, sys\n"
            "c = sqlite3.connect(sys.argv[1], isolation_level=None)\n"
            "c.execute('PRAGMA cache_size = 2')\nc.execute('BEGIN')\n"
            "c.execute('UPDATE filler SET b = zeroblob(3001)')\n"
            "os.kill(os.getpid(), signal.SIGKILL)\n")
    subprocess.run([sys.executable, "-c", code, dst])
    j = dst + "-journal"
    assert os.path.exists(j) and os.path.getsize(j) > 0, "no hot journal was left"

V1 = os.path.join(HERE, "..", "tools", "testdata", "store-v1", "store.sql")

def at_version_1(src, dst, edit=None):
    """A user layer at user_version 1, the dated writer's DDL (tools/testdata/store-v1/store.sql, its CREATE statements),
    holding the rows of `src` in the columns version 1 has: what the reader migrates on open (spec section 3.6)."""
    with open(V1, encoding="utf-8") as f:
        ddl = [l for l in f.read().split(";\n") if l.lstrip().startswith("CREATE ")]
    c = sqlite3.connect(dst)
    for stmt in ddl:
        c.execute(stmt)
    c.execute("ATTACH ? AS src", (src,))
    tables = [r[0] for r in c.execute("SELECT name FROM main.sqlite_master WHERE type = 'table' ORDER BY rowid")]
    c.execute("PRAGMA foreign_keys = OFF")
    for t in tables:
        cols = [r[0] for r in c.execute("SELECT name FROM pragma_table_info(?, 'main')", (t,))]
        have = {r[0] for r in c.execute("SELECT name FROM pragma_table_info(?, 'src')", (t,))}
        cols = [x for x in cols if x in have]
        c.execute('INSERT INTO main."%s" (%s) SELECT %s FROM src."%s"' % (t, ", ".join(cols), ", ".join(cols), t))
    c.commit()
    c.execute("DETACH src")
    if edit:
        c.execute(edit)
    c.execute("PRAGMA user_version = 1")
    c.commit(); c.close()

# ---- the pin's words (section 3.7, pqdb_pin_of): one plugin per case, its omx-clap-host verdict, reasons and steps; the
# expected words in the uri: urn:pin-<case>. The ratings are the qualification domain's (suitable, unsuitable, unknown),
# which the fixture contract does not hold: verdict.rating and reason.code are left out of this fixture's word check ----
OWN = "hosting.rt-safety.own-threads"
PINS = [
    ("suitable", "suitable", (), ()),
    ("conditional-groupable", "conditional", (("conditional", OWN),), ()),
    ("conditional-other", "conditional", (("conditional", OWN), ("conditional", "hosting.rt-safety.allocations")), ()),
    ("conditional-none", "conditional", (("suitable", OWN),), ()),
    ("unsuitable", "unsuitable", (), ()),
    ("unknown", "unknown", (), ()),
    ("isolated-step", "suitable", (), (("probe", "ok"), ("isolated", "isolated"), ("pool", "cores"))),
    ("refused-step", "suitable", (), (("isolated", "refused"), ("pool", "cores"))),
    ("not-run-step", "suitable", (), (("isolated", "not-run"),)),
    ("pool-off", "suitable", (), (("pool", "off"),)),
    ("pool-not-asked", "suitable", (), (("pool", "not-asked"),)),
    ("unsuitable-pool", "unsuitable", (), (("pool", "cores"),)),
    ("conditional-isolated-step", "conditional", (("conditional", "hosting.rt-safety.allocations"),), (("isolated", "isolated"),)),
]
X86_CLASS, PI_CLASS = "x86_64/5-8/2.5-3.5GHz", "aarch64/4/2-2.5GHz"
# the history adjustment (adjust --history): (case, blocks), each block (host class, [(host, measured, adjusted)])
ADJUSTED = [
    ("adjusted-demote", ((X86_CLASS, (("omx-clap-host", "in-process", "isolated"),)),)),
    ("adjusted-null", ((X86_CLASS, (("omx-clap-host", "in-process", None),)),)),
    ("adjusted-other-class", ((PI_CLASS, (("omx-clap-host", "in-process", "refused"),)),)),
    ("adjusted-latest", ((X86_CLASS, (("omx-clap-host", "in-process", "refused"),)), (X86_CLASS, (("omx-clap-host", "in-process", "isolated"),)))),
    ("adjusted-other-host", ((X86_CLASS, (("openmixer-console", "in-process", "refused"),)),)),
]
def pins_records():
    out = []
    for n, (case, rating, reasons, steps) in enumerate(PINS):
        out.append(rec(("%02x" % (n + 1) * 32, "clap", "urn:pin-" + case), "default", "x86-64",
                       [cell(48000, 256, (1.0, 95, 2.0), (1, 2), (3, 4))], set="fedora44-48000-256", verdict_rating=rating,
                       layout=("omx-layout/1", sha("c")), reasons=reasons, steps=steps))
    for n, (case, blocks) in enumerate(ADJUSTED):
        out.append(rec(("b%x" % (n + 1) * 32, "clap", "urn:pin-" + case), "default", "x86-64", [cell(48000, 256, (1.0, 95, 2.0), (1, 2), (3, 4))],
                       set="fedora44-48000-256", verdict_rating="suitable", layout=("omx-layout/1", sha("c")), history=blocks))
    out.append(rec(("a1" * 32, "clap", "urn:pin-not-measured"), "default", "x86-64", [cell(48000, 256, (1.0, 95, 2.0), (1, 2), (3, 4))],
                   set="fedora44-48000-256", verdict_rating="suitable", layout=("omx-layout/1", sha("c")), verdict_measured=0))
    out.append(rec(("a2" * 32, "clap", "urn:pin-unpinnable"), "default", "x86-64", [cell(48000, 256, (1.0, 95, 2.0), (1, 2), (3, 4))],
                   set="fedora44-48000-256", verdict_rating="suitable", layout=("omx-layout/1", sha("c")), unpinnable=1))
    out.append(rec(("a3" * 32, "clap", "urn:pin-no-layout"), "default", "x86-64", [cell(48000, 256, (1.0, 95, 2.0), (1, 2), (3, 4))],
                   set="fedora44-48000-256", verdict_rating="suitable"))
    return out

def main(out):
    os.makedirs(out, exist_ok=True)
    p = lambda n: os.path.join(out, n)
    build(p("base.sqlite"), 0, BASE)
    build(p("pins.sqlite"), 0, pins_records(), unchecked={("verdict", "rating"), ("reason", "code")})
    build(p("user.sqlite"), 1, USER)
    at_version_1(p("user.sqlite"), p("user-v1.sqlite"))
    # the later dated builds wrote the DDL of 2 at user_version 1 (a device's layer): the same rows, at 1
    shutil.copy(p("user.sqlite"), p("user-v1-later.sqlite"))
    c = sqlite3.connect(p("user-v1-later.sqlite")); c.execute("PRAGMA user_version = 1"); c.commit(); c.close()
    at_version_1(p("user.sqlite"), p("user-v1-bad-rating.sqlite"),
                 "UPDATE verdict SET rating = 'excellent' WHERE record_id = (SELECT min(record_id) FROM verdict)")
    build(p("base-v3.sqlite"), 0, BASE, version=VERSION + 1)
    build(p("user-v3.sqlite"), 1, USER, version=VERSION + 1)
    build(p("base-v0.sqlite"), 0, BASE, version=0)
    build(p("base-bad-adapter-code.sqlite"), 0, BASE, adapter_code_override="omx-clap-host.signal-SIGBUS")
    # the hosting columns are checked like any other (section 3.4): in each of the three mixed columns and the hosting-only
    # one, a hosting word of the package opens, a hosting word no package holds is refused, and so is any other unknown word
    extra = {"verdict": "UPDATE verdict SET deciding = '%s' WHERE record_id = 1 AND ord = 1",
             "not-measured": "INSERT INTO not_measured VALUES (1, 0, 'latency', '%s')",
             "tier": "INSERT INTO tier VALUES (1, 'inProcess', 'omx-clap-host', 1, 1, 'qualified', '%s', NULL)",
             "reason": "INSERT INTO reason (record_id, verdict_ord, cost_ord, ord, dimension, rating, code) VALUES (1, 0, NULL, 0, 'cost', 'conditional', '%s')"}
    for kind, sql in extra.items():
        for word, tag in (("probe.no-such-word", "bad"), ("hosting.held-by-no-package", "unknown"), ("hosting.cost.above-ceiling", "ok")):
            build(p("base-%s-%s.sqlite" % (tag, kind)), 0, BASE)
            c = sqlite3.connect(p("base-%s-%s.sqlite" % (tag, kind)))
            c.execute(sql % word)
            c.commit(); c.close()
    build(p("base-bad-rating.sqlite"), 0, BASE)
    c = sqlite3.connect(p("base-bad-rating.sqlite"))
    c.execute("UPDATE verdict SET rating = 'excellent' WHERE record_id = 1 AND ord = 0")
    c.commit(); c.close()
    build(p("user-filler.sqlite"), 1, USER, filler=True)
    hot_journal(p("user-filler.sqlite"), p("user-hot.sqlite"))
    # the scopes: the system layer, the home's layer and a decoy under an XDG_DATA_HOME
    build(p("scope-system.sqlite"), 1, [rec((SYS_SHA, "clap", "urn:sys"), "default", "x86-64", [cell(48000, 256, (1.0, 95, 2.0), (1, 2), (3, 4))])])
    build(p("scope-home.sqlite"), 1, [rec((HOME_SHA, "clap", "urn:home"), "default", "x86-64", [cell(48000, 256, (1.0, 95, 2.0), (1, 2), (3, 4))])])
    build(p("scope-xdg.sqlite"), 1, [rec((XDG_SHA, "clap", "urn:xdg"), "default", "x86-64", [cell(48000, 256, (1.0, 95, 2.0), (1, 2), (3, 4))])])
    build_records(p("records.sqlite"))
    build_numbers(p("numbers.sqlite"))
    build_nonfinite(p("nonfinite-pos.sqlite"), "UPDATE cell SET latency_ms = 1e999")
    build_nonfinite(p("nonfinite-neg.sqlite"), "UPDATE cell SET latency_ms = -1e999")
    build_nonfinite(p("nonfinite-line.sqlite"), "UPDATE record SET latency_line_ms = 1e999")
    build_nonfinite(p("nonfinite-cpu.sqlite"), "UPDATE cell SET cost_median = -1e999, cost_percentile_value = 1e999")
    write_expect(p("expect-base.tsv"), reference([("base", BASE)]))
    write_expect(p("expect-merged.tsv"), reference([("user", USER), ("base", BASE)]))
    write_expect(p("expect-user.tsv"), reference([("user", USER)]))
    write_expect(p("expect-counts-merged.tsv"), counts([("user", USER), ("base", BASE)]))
    write_expect(p("expect-counts-user.tsv"), counts([("user", USER)]))
    write_expect(p("expect-counts-base.tsv"), counts([("base", BASE)]))
    # three plugins (two clap, one lv2): the first has a record with a tier_offered row and one without, the second
    # none, the third one: clap 2 plugins, 1 offered, 1 not; lv2 1, 1, 0
    one = lambda uri, fmt, offer, offered: rec(({"cx": sha("4"), "cy": sha("5"), "cz": sha("6")}[uri[-2:]], fmt, uri), offer, "x86-64",
                                              [cell(48000, 256, (1.0, 95, 2.0), (1, 2), (3, 4))], offered=offered)
    build(p("counts-user.sqlite"), 1, [one("urn:cx", "clap", "default", True), one("urn:cx", "clap", "custom", False),
                                       one("urn:cy", "clap", "default", False), one("urn:cz", "lv2", "default", True)])
    # two sets hold one plugin at one cell: a non-real-time set (tier provisional) and a real-time one (tier reference),
    # each record with its own figures, verdict, file list and offer; built in both orders. The reference tier's record
    # claims the cell (the store spec, section 4), and every read answers with it alone
    for order, recs in (("ref-last", TIERS), ("ref-first", TIERS[::-1])):
        build(p("base-tiers-%s.sqlite" % order), 0, recs)
    # two sets of one tier at one cell, built in both orders: the newer set's record claims it
    for order, recs in (("new-last", NEWER), ("new-first", NEWER[::-1])):
        build(p("base-newer-%s.sqlite" % order), 0, recs)
    # the claimant of each of two cells, the sets in both orders (the command's --records at a cell)
    for order, recs in (("winner-last", CLAIMANTS), ("winner-first", CLAIMANTS[::-1])):
        build(p("base-claimants-%s.sqlite" % order), 0, recs)
    # stores whose key is not the binary's entry (section 3.7): opened fine, refused by check
    for name, sql in (("key-mismatch", "UPDATE record_file SET sha256 = '%s' WHERE record_id = 1" % sha("9")),
                      ("key-no-entry", "UPDATE record SET binary_path = 'other.clap' WHERE record_id = 1")):
        build(p("base-%s.sqlite" % name), 0, BASE)
        c = sqlite3.connect(p("base-%s.sqlite" % name))
        c.execute(sql)
        c.commit(); c.close()

if __name__ == "__main__":
    main(sys.argv[1])
