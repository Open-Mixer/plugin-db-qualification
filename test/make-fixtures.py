#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""Builds the fixture stores of the reader's tests from schema/qualification.sql: a base, user layers, stores at
other versions, a user layer with a hot journal, and the figures a reader must give back, worked out here from the
fixture data by the rules of plugin-hostd's qualcost.h (not by the reader). Usage: make-fixtures.py <out dir>."""
import os, shutil, signal, sqlite3, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, "..", "schema", "qualification.sql")
VERSION = 1

def sha(c):
    return c * 64

P1, P1X, P2, P3 = sha("a"), sha("b"), sha("c"), sha("d")
SYS_SHA, HOME_SHA, XDG_SHA = sha("1"), sha("2"), sha("3")

# (table, column, domain, item): the word columns the fixtures fill, as section 3.4 names them
WORD_CHECK = [
    ("plugin", "format", "plugin-db", "PLUGIN_DB_ADDRESS_FORMATS"),
    ("record_set", "host_class", "qualification", "QUALIFICATION_HOST_CLASSES"),
    ("record", "host_class", "qualification", "QUALIFICATION_HOST_CLASSES"),
    ("record_set", "tier", "qualification", "QUALIFICATION_SET_TIERS"),
    ("record_set", "host_profile", "qualification", "QUALIFICATION_HOST_PROFILES"),
    ("verdict", "host", "qualification", "QUALIFICATION_HOST_PROFILES"),
    ("record", "adapter_host", "qualification", "QUALIFICATION_HOST_PROFILES"),
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
    ("verdict", "deciding", "hosting", "HOSTING_CODES"),
    ("record", "adapter_code", "qualification", "QUALIFICATION_HOST_PROFILES"),
    ("record", "adapter_code", "qualification", "QUALIFICATION_ADAPTER_CODE_KINDS"),
    ("record", "adapter_code", "probe", "PROBE_SIGNALS"),
    ("adapter_cell", "code", "qualification", "QUALIFICATION_HOST_PROFILES"),
    ("adapter_cell", "code", "qualification", "QUALIFICATION_ADAPTER_CODE_KINDS"),
    ("adapter_cell", "code", "probe", "PROBE_SIGNALS"),
]
DOMAINS = {"qualification": "1.1.0", "machine": "1.0.0", "probe": "1.0.0", "hosting": "1.0.0", "plugin-db": "1.0.0"}

def cell(rate, quantum, cost=None, lat=(None, None), mem=None, outcome="probe.ok"):
    """cost: (median, p, p value); lat: (declared, measured); mem: (first kb, per instance kb)."""
    return dict(rate=rate, quantum=quantum, cost=cost, lat=lat, mem=mem, outcome=outcome)

def rec(key, offer, cls, cells, set=None, pkg=None, adapter_code=None, cell_code=None, verdict_rating="qualified"):
    return dict(key=key, offer=offer, cls=cls, cells=cells, set=set, pkg=pkg, adapter_code=adapter_code,
                cell_code=cell_code, verdict_rating=verdict_rating)

BASE = [
    rec((P1, "clap", "urn:p1"), "default", "x86-64", set="fedora44-48000-256", adapter_code="omx-clap-host.signal-SIGSEGV",
        cell_code="omx-clap-host.resp-3", verdict_rating="conditional",
        cells=[cell(48000, 256, (100.5, 95, 150.25), (64, 128), (2048, 512)),
               cell(96000, 256, (200.0, 95, 300.0), (256, None), (4096, 1024))]),
    rec((P1, "clap", "urn:p1"), "custom", "x86-64", set="fedora44-48000-256",
        cells=[cell(48000, 256, (101.0, 95, 151.0), (64, 130), (2000, 500))]),
    rec((P1, "clap", "urn:p1"), "default", "rpi5", set="zynthian-vangelis",
        cells=[cell(48000, 256, (300.0, 95, 450.0), (None, 200), None)]),
    rec((P2, "clap", "urn:p2"), "default", "x86-64", set="fedora44-48000-256",
        cells=[cell(48000, 256, (80.0, None, None), (None, None), (1024, None))]),
    rec((P3, "lv2", "urn:p3"), "default", "x86-64", set="fedora44-48000-256",
        cells=[cell(48000, 256, (10.0, 95, 12.0), (32, 40), (512, 64), outcome="probe.crashed")]),
]
USER = [
    rec((P1, "clap", "urn:p1"), "default", "x86-64", pkg=("rpm", "clap-dexed", "1.1.0", "4.fc44", "fc44", "x86_64"),
        cells=[cell(48000, 256, (111.0, 95, 160.0), (64, 128), None)]),
    rec((P1X, "clap", "urn:p1"), "default", "x86-64", cells=[cell(48000, 256, (5.0, 95, 6.0), (1, 2), (3, 4))]),
    rec((P2, "clap", "urn:p2"), "custom", "x86-64", cells=[cell(48000, 256, (7.0, 95, 8.0), (1, 2), (3, 4))]),
    rec((P2, "clap", "urn:p2"), "default", "rpi5", cells=[cell(48000, 256, (9.0, 95, 10.0), (1, 2), (3, 4))]),
]

def word_checks(c):
    c.executemany("INSERT INTO store_domain VALUES (?, ?)", sorted(DOMAINS.items()))
    c.executemany("INSERT INTO word_check VALUES (?, ?, ?, ?)", WORD_CHECK)

def build(path, layer, records, version=VERSION, adapter_code_override=None, filler=False):
    if os.path.exists(path):
        os.unlink(path)
    c = sqlite3.connect(path)
    c.execute("PRAGMA journal_mode = DELETE")
    c.execute("PRAGMA page_size = 4096")
    c.executescript(open(SCHEMA).read())
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("INSERT INTO store_info VALUES (1, ?, 'plugin-qualify.qualification-record/1', ?)",
              (layer, None if layer else "0123456789abcdef0123456789abcdef01234567"))
    word_checks(c)
    plugin, sets = {}, {}
    for n, r in enumerate(records):
        pid = plugin.setdefault(r["key"], len(plugin) + 1)
        if pid == len(plugin) and c.execute("SELECT 1 FROM plugin WHERE plugin_id = ?", (pid,)).fetchone() is None:
            c.execute("INSERT INTO plugin VALUES (?, ?, ?, ?)", (pid, *r["key"]))
        set_id = None
        if r["set"] is not None:
            skey = (r["cls"], r["set"])
            if skey not in sets:
                sets[skey] = len(sets) + 1
                c.execute("INSERT INTO record_set VALUES (?, ?, ?, 'plugin-qualify.provenance/1', 'reference', "
                          "'omx-clap-host', 'fixture', '2026-11-19', 'plugin-qualification-records', '1')",
                          (sets[skey], r["cls"], r["set"]))
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
            VALUES (?, ?, ?, ?, ?, ?, 'plugin-qualify.qualification-record/1', ?, ?, ?, ?, ?, ?, '/usr/lib/p',
            '2026-11-19T00:00:00Z', 'run', 'runner', 'child', 'p.probe.json', ?, 10, 'probe', 1,
            'on-request', 'probe.ok', 1, 1, 0.5, 4, 'x86_64', 'zen4', 'cores-4', 'ghz-3', 0, 0,
            ?, ?, ?, ?, ?)""",
                  (rid, pid, set_id, r["cls"], r["offer"], "rec%d" % rid, *pkg, "e" * 64,
                   1 if code else None, "omx-clap-host" if code else None, 1 if code else None, code,
                   0 if code else None))
        c.execute("INSERT INTO verdict VALUES (?, 0, 'omx-clap-host', 1, ?, 1, 'isolated', 'run', NULL)",
                  (rid, r["verdict_rating"]))
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

def main(out):
    os.makedirs(out, exist_ok=True)
    p = lambda n: os.path.join(out, n)
    build(p("base.sqlite"), 0, BASE)
    build(p("user.sqlite"), 1, USER)
    build(p("base-v2.sqlite"), 0, BASE, version=2)
    build(p("user-v2.sqlite"), 1, USER, version=2)
    build(p("base-v0.sqlite"), 0, BASE, version=0)
    build(p("base-bad-adapter-code.sqlite"), 0, BASE, adapter_code_override="omx-clap-host.signal-SIGBUS")
    build(p("user-filler.sqlite"), 1, USER, filler=True)
    hot_journal(p("user-filler.sqlite"), p("user-hot.sqlite"))
    # the scopes: the system layer, the home's layer and a decoy under an XDG_DATA_HOME
    build(p("scope-system.sqlite"), 1, [rec((SYS_SHA, "clap", "urn:sys"), "default", "x86-64", [cell(48000, 256, (1.0, 95, 2.0), (1, 2), (3, 4))])])
    build(p("scope-home.sqlite"), 1, [rec((HOME_SHA, "clap", "urn:home"), "default", "x86-64", [cell(48000, 256, (1.0, 95, 2.0), (1, 2), (3, 4))])])
    build(p("scope-xdg.sqlite"), 1, [rec((XDG_SHA, "clap", "urn:xdg"), "default", "x86-64", [cell(48000, 256, (1.0, 95, 2.0), (1, 2), (3, 4))])])
    write_expect(p("expect-base.tsv"), reference([("base", BASE)]))
    write_expect(p("expect-merged.tsv"), reference([("user", USER), ("base", BASE)]))

if __name__ == "__main__":
    main(sys.argv[1])
