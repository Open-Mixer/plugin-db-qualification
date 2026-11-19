# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The qualification store's writer and exporter, one module (this repository's qualification store spec, sections 3
and 5): records and provenances to rows, and rows back to records.

One declarative description of a record (RECORD below) drives both directions, so a field is mapped in one place and the
writer and the exporter cannot disagree about it. tools/test_records_db.py holds the mapping to an independent,
hand-written table (tools/testdata/field-columns.tsv) as well as to the round trip.

The module reads no environment variable and knows no list of words: the words come from the contract directory the
caller passes.
"""
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCHEMA_SQL = os.path.join(ROOT, "schema", "qualification.sql")
HEADER = os.path.join(ROOT, "include", "plugin-qualification-db", "pqdb.h")
RECORD_SCHEMA = "plugin-qualify.qualification-record/1"
PROVENANCE_SCHEMA = "plugin-qualify.distributed-provenance/1"
DOMAINS = ("qualification", "machine", "probe", "plugin-db", "hosting")


class Refusal(Exception):
    """A refusal by name: the name is the first thing the command prints."""

    def __init__(self, name, message):
        super().__init__(f"{name}: {message}")
        self.name = name
        self.message = message


def schema_version():
    with open(HEADER, encoding="utf-8") as f:
        m = re.search(r"^#define\s+PQDB_SCHEMA_VERSION\s+(\d+)", f.read(), re.M)
    if not m:
        raise Refusal("schema-version", f"{HEADER} defines no PQDB_SCHEMA_VERSION")
    return int(m.group(1))


# ---------------------------------------------------------------------------------------------------------------------
# The description of a record: nodes. A node says how one JSON value maps to rows and back.
# ---------------------------------------------------------------------------------------------------------------------
ABSENT = object()


class Leaf:
    def __init__(self, table, col, kind="text", req=False):
        self.table, self.col, self.kind, self.req = table, col, kind, req


class Present:
    """A field whose presence is stored (1), not its text: binary.unpinnable, a sentence."""

    def __init__(self, table, col):
        self.table, self.col, self.req = table, col, False


class Sentence:
    """Prose for a person: not stored, and not exported."""
    req = False


class Obj:
    def __init__(self, fields, req=False, anchor=None):
        self.fields, self.req, self.anchor = fields, req, anchor


class Arr:
    """An array of rows of `table`, linked to the enclosing row by `by` ([(child column, parent column)]). `always`
    is the section 3.3 rule: present (maybe empty) with its parent, against present only with rows. `single` is one
    row, found by `const` (the tiers)."""

    def __init__(self, table, item, by=(("record_id", "record_id"),), always=False, ord=True, const=None, single=False):
        self.table, self.item, self.by, self.always, self.ord = table, item, tuple(by), always, ord
        self.const, self.single = const or {}, single
        self.req = always


class Map:
    """An object of named values: rows of (name, number | word) or (name, value)."""

    def __init__(self, table, by=(("record_id", "record_id"),), always=False, flag=None, kind="param", cols=("name", "version"),
                 const=None):
        self.table, self.by, self.always, self.flag, self.kind, self.cols = table, tuple(by), always, flag, kind, cols
        self.const = const or {}
        self.req = always


def L(table, col, kind="text", req=True):
    return Leaf(table, col, kind, req)


def O(table, col, kind="text"):
    return Leaf(table, col, kind, False)


def _reasons(parent_col):
    by = (("record_id", "record_id"), (parent_col, "ord"))
    return Arr("reason", Obj({
        "dimension": L("reason", "dimension"),
        "rating": L("reason", "rating"),
        "code": L("reason", "code"),
        "params": Map("reason_param", by=(("reason_id", "reason_id"),), always=True),
    }), by=by, always=True)


def _tier(name):
    return Arr("tier", Obj({
        "host": L("tier", "host"),
        "measured": L("tier", "measured", "bool"),
        "qualified": L("tier", "qualified", "bool"),
        "rating": L("tier", "rating"),
        "deciding": O("tier", "deciding"),
        "runsAlone": O("tier", "runs_alone", "bool"),
    }), ord=False, const={"tier": name}, single=True)


def _cell():
    c = "cell"
    return Obj({
        "rate": L(c, "rate", "int"),
        "quantum": L(c, "quantum", "int"),
        "outcome": L(c, "outcome"),
        "latency": Obj({
            "declaredFrames": O(c, "latency_declared_frames", "int"),
            "measuredFrames": O(c, "latency_measured_frames", "int"),
            "code": O(c, "latency_code"),
            "unmeasuredReason": O(c, "latency_unmeasured_reason"),
        }),
        "cost": Obj({
            "median": O(c, "cost_median", "real"),
            "percentile": Obj({"p": O(c, "cost_percentile_p", "int"), "value": O(c, "cost_percentile_value", "real")}),
            "blocks": O(c, "cost_blocks", "int"),
            "warmupBlocks": O(c, "cost_warmup_blocks", "int"),
            "voices": Obj({
                "basis": O(c, "voices_basis"),
                "capacity": O(c, "voices_capacity", "int"),
                "held": O(c, "voices_held", "int"),
            }),
        }),
        "memory": Obj({
            "afterInstantiateKb": O(c, "mem_after_instantiate_kb", "int"),
            "afterActivateKb": O(c, "mem_after_activate_kb", "int"),
            "atRestKb": O(c, "mem_at_rest_kb", "int"),
            "secondInstanceKb": O(c, "mem_second_instance_kb", "int"),
            "firstInstanceKb": O(c, "mem_first_instance_kb", "int"),
            "perInstanceKb": O(c, "mem_per_instance_kb", "int"),
            "notesHeldKb": O(c, "mem_notes_held_kb", "int"),
            "basis": O(c, "mem_basis"),
            "unmeasuredReason": O(c, "mem_unmeasured_reason"),
            "unmeasuredDetail": Sentence(),
        }),
        "memoryLimit": Obj({
            "bytes": O(c, "mem_limit_bytes", "int"),
            "mechanism": O(c, "mem_limit_mechanism"),
        }),
        "rtSafety": Obj({
            "interposer": L(c, "rt_interposer", "bool"),
            "swept": L(c, "rt_swept", "bool"),
            "sweepApplicable": L(c, "rt_sweep_applicable", "bool"),
            "blocks": L(c, "rt_blocks", "int"),
            "allocations": L(c, "rt_allocations", "int"),
            "locks": L(c, "rt_locks", "int"),
            "syscalls": L(c, "rt_syscalls", "int"),
            "threadViolations": O(c, "rt_thread_violations", "int"),
            "processErrors": O(c, "rt_process_errors", "int"),
            "events": Arr("cell_event", Leaf("cell_event", "event", "text", True),
                          by=(("record_id", "record_id"), ("cell_ord", "ord")), always=True),
        }, anchor=("cell", "rt_interposer")),
        "noteSweep": Obj({
            "applicable": O(c, "note_sweep_applicable", "bool"),
            "dialect": O(c, "note_sweep_dialect"),
            "allocations": O(c, "note_sweep_allocations", "int"),
            "locks": O(c, "note_sweep_locks", "int"),
            "syscalls": O(c, "note_sweep_syscalls", "int"),
        }),
    })


def _record():
    r = "record"
    return Obj({
        "schema": L(r, "schema"),
        "plugin": Obj({"format": L("plugin", "format"), "id": L("plugin", "uri")}, req=True),
        "binary": Obj({
            "path": L(r, "binary_path"),
            "sha256": L("plugin", "sha256"),
            "files": Arr("record_file", Obj({"path": L("record_file", "path"), "sha256": L("record_file", "sha256")}), always=True),
            "layout": Obj({"scheme": L(r, "layout_scheme"), "sha256": L(r, "layout_sha256")}),
            "unpinnable": Present(r, "unpinnable"),
        }, req=True),
        "testedVersion": O(r, "tested_version"),
        "measuredAt": L(r, "measured_at"),
        "run": Obj({
            "id": L(r, "run_id"),
            "steps": Arr("run_step", Obj({
                "step": L("run_step", "step"),
                "result": L("run_step", "result"),
                "code": O("run_step", "code"),
                "detail": Sentence(),
                "figures": Obj({
                    "cpuPercent": O("run_step", "cpu_percent", "real"),
                    "latencyFrames": O("run_step", "latency_frames", "int"),
                    "midiInputsLinked": O("run_step", "midi_inputs_linked", "int"),
                    "xruns": O("run_step", "xruns", "int"),
                }),
                "pool": Obj({
                    "allocationsOn": O("run_step", "pool_allocations_on", "int"),
                    "locksOn": O("run_step", "pool_locks_on", "int"),
                    "syscallsOn": O("run_step", "pool_syscalls_on", "int"),
                    "tasksOnHelpers": O("run_step", "pool_tasks_on_helpers", "int"),
                }),
            }), always=True),
        }, req=True),
        "tool": Obj({
            "runner": L(r, "tool_runner"), "child": L(r, "tool_child"), "interposer": O(r, "tool_interposer"),
        }, req=True),
        "probe": Obj({
            "file": L(r, "probe_file"),
            "sha256": L(r, "probe_sha256"),
            "bytes": L(r, "probe_bytes", "int"),
            "protocol": Obj({"name": L(r, "probe_protocol"), "version": L(r, "probe_protocol_version", "int")}, req=True),
            "reason": L(r, "probe_reason"),
            "outcome": L(r, "probe_outcome"),
            "complete": L(r, "probe_complete", "bool"),
            "meetsProtocol": L(r, "probe_meets_protocol", "bool"),
            "load": Obj({"loadavg1": L(r, "probe_loadavg1", "real"), "cores": L(r, "probe_cores", "int")}, req=True),
            "machineClass": Obj({
                "arch": L(r, "mc_arch"), "family": L(r, "mc_family"), "coreBand": L(r, "mc_core_band"),
                "clockBand": L(r, "mc_clock_band"), "preemptRt": L(r, "mc_preempt_rt", "bool"),
                "cstatesLimited": L(r, "mc_cstates_limited", "bool"),
            }, req=True),
            "ends": Arr("probe_end", Obj({
                "step": L("probe_end", "step"),
                "outcome": L("probe_end", "outcome"),
                "exitStatus": O("probe_end", "exit_status", "int"),
                "signal": O("probe_end", "signal"),
            })),
        }, req=True),
        "verdicts": Arr("verdict", Obj({
            "host": L("verdict", "host"),
            "measured": L("verdict", "measured", "bool"),
            "rating": L("verdict", "rating"),
            "qualified": L("verdict", "qualified", "bool"),
            "hosting": L("verdict", "hosting"),
            "arm": L("verdict", "arm"),
            "deciding": O("verdict", "deciding"),
            "reasons": _reasons("verdict_ord"),
        }), always=True),
        "cost": Arr("cost_entry", Obj({
            "host": L("cost_entry", "host"),
            "rate": L("cost_entry", "rate", "int"),
            "quantum": L("cost_entry", "quantum", "int"),
            "reasons": _reasons("cost_ord"),
        }), always=True),
        "tiers": Obj({
            "inProcess": _tier("inProcess"),
            "isolated": _tier("isolated"),
            "offeredOn": Arr("tier_offered", Leaf("tier_offered", "tier", "text", True), always=True),
            "dimmed": Sentence(),
        }, req=True),
        "measurements": Obj({
            "grid": Arr("cell", _cell(), always=True),
            "unmeasured": Arr("unmeasured", Obj({
                "dimension": L("unmeasured", "dimension"),
                "code": L("unmeasured", "code"),
                "rate": L("unmeasured", "rate", "int"),
                "quantum": L("unmeasured", "quantum", "int"),
                "detail": Sentence(),
            })),
            "behaviour": Obj({
                "lifecycle": Obj({
                    "cycles": L(r, "lifecycle_cycles", "int"), "failed": L(r, "lifecycle_failed", "int"),
                    "instantiated": L(r, "lifecycle_instantiated", "int"),
                }, req=True),
                "threads": Obj({
                    "before": L(r, "threads_before", "int"),
                    "afterFirstInstantiate": L(r, "threads_after_first_instantiate", "int"),
                    "afterAllFreed": L(r, "threads_after_all_freed", "int"),
                }, req=True),
                "features": Obj({
                    "required": Arr("feature_required", Leaf("feature_required", "feature", "text", True), always=True),
                }, req=True),
            }, anchor=(r, "lifecycle_cycles")),
        }, req=True),
        "notMeasured": Arr("not_measured", Obj({
            "dimension": L("not_measured", "dimension"), "code": L("not_measured", "code"),
        }), always=True),
        "adapter": Obj({
            "admitted": L(r, "adapter_admitted", "bool"),
            "host": L(r, "adapter_host"),
            "measured": L(r, "adapter_measured", "bool"),
            "code": O(r, "adapter_code"),
            "measuredAt": O(r, "adapter_measured_at"),
            "versions": Map("record_version", kind="text", cols=("name", "version"), const={"rejudged": 0}),
            "params": Map("adapter_param", flag=(r, "adapter_params")),
            "cells": Arr("adapter_cell", Obj({
                "rate": L("adapter_cell", "rate", "int"),
                "quantum": L("adapter_cell", "quantum", "int"),
                "admitted": L("adapter_cell", "admitted", "bool"),
                "measured": L("adapter_cell", "measured", "bool"),
                "code": O("adapter_cell", "code"),
                "params": Map("adapter_cell_param", by=(("record_id", "record_id"), ("ord", "ord")),
                              flag=("adapter_cell", "params")),
            })),
        }, anchor=(r, "adapter_admitted")),
        "memoryRun": Obj({
            "measuredAt": L(r, "memory_run_measured_at"),
            "runId": L(r, "memory_run_id"),
            "tool": Obj({"runner": L(r, "memory_run_runner"), "child": L(r, "memory_run_child")}, req=True),
            "cells": Arr("memory_run_cell", Obj({
                "rate": L("memory_run_cell", "rate", "int"),
                "quantum": L("memory_run_cell", "quantum", "int"),
                "outcome": L("memory_run_cell", "outcome"),
            }), always=True),
        }, anchor=(r, "memory_run_measured_at")),
        "rejudged": Obj({
            "at": L(r, "rejudged_at"),
            "by": L(r, "rejudged_by"),
            "figures": Obj({
                "measuredAt": L(r, "rejudged_measured_at"),
                "runId": L(r, "rejudged_run_id"),
                "tool": Obj({
                    "runner": L(r, "rejudged_runner"), "child": L(r, "rejudged_child"),
                    "interposer": O(r, "rejudged_interposer"),
                }, req=True),
                "adapter": Obj({
                    "measuredAt": L(r, "rejudged_adapter_measured_at"),
                    "versions": Map("record_version", kind="text", cols=("name", "version"), const={"rejudged": 1}),
                }),
                "memory": Obj({
                    "measuredAt": L(r, "rejudged_memory_measured_at"),
                    "tool": Obj({"runner": L(r, "rejudged_memory_runner"), "child": L(r, "rejudged_memory_child")}, req=True),
                }),
            }, req=True),
            "owes": Arr("rejudged_owe", Obj({
                "code": L("rejudged_owe", "code"), "measurement": L("rejudged_owe", "measurement"),
            })),
        }, anchor=(r, "rejudged_at")),
    }, req=True)


def _provenance():
    s = "record_set"
    return Obj({
        "schema": L(s, "schema"),
        "set": L(s, "name"),
        "hostClass": L(s, "host_class"),
        "hostProfile": L(s, "host_profile"),
        "tier": L(s, "tier"),
        "measured": L(s, "measured"),
        "date": L(s, "date"),
        "package": Obj({"name": L(s, "package_name"), "version": L(s, "package_version")}, req=True),
        "packages": Map("set_package", by=(("set_id", "set_id"),), kind="text", cols=("name", "version"),
                        const={"pass": 0}, always=True),
        "passes": Map("set_package", by=(("set_id", "set_id"),), kind="text", cols=("name", "version"),
                      const={"pass": 1}),
        # `settings` is handled by the caller: its keys are set_setting rows, its `note` a sentence
        "tierNote": Sentence(), "image": Sentence(), "board": Sentence(), "kernel": Sentence(), "realtime": Sentence(),
        "jack": Sentence(), "grid": Sentence(), "sources": Sentence(), "repositories": Sentence(),
    }, req=True)


RECORD = _record()
PROVENANCE = _provenance()


# ---------------------------------------------------------------------------------------------------------------------
# Words: the owner items of each word column (section 3.4). The item names are the table's; the words are the domains'.
# ---------------------------------------------------------------------------------------------------------------------
def _q(name):
    return ("qualification", "QUALIFICATION_" + name)


_ADAPTER_PARTS = [_q("HOST_PROFILES"), _q("ADAPTER_CODE_KINDS"), ("probe", "PROBE_SIGNALS")]
_HOSTING = ("hosting", "HOSTING_*CODES")  # every item of the hosting domain named HOSTING_<group>_CODES
_PROBE_OUT = [("probe", "PROBE_OUTCOMES"), _q("MEMORY_BOUND_OUTCOMES")]
_RATING = [_q("MEASUREMENT_VERDICT_RATINGS")]
_DIM = [_q("MEASUREMENT_DIMENSIONS")]
_PROFILE = [_q("HOST_PROFILES")]

WORDS = {
    ("plugin", "format"): [("plugin-db", "PLUGIN_DB_ADDRESS_FORMATS")],
    ("record_set", "host_class"): [_q("HOST_CLASSES")],
    ("record", "host_class"): [_q("HOST_CLASSES")],
    ("record_set", "tier"): [_q("SET_TIERS")],
    ("record_set", "host_profile"): _PROFILE,
    ("verdict", "host"): _PROFILE,
    ("cost_entry", "host"): _PROFILE,
    ("tier", "host"): _PROFILE,
    ("record", "adapter_host"): _PROFILE,
    ("set_setting", "key"): [_q("SYNC_SETTINGS")],
    ("record", "offer"): [_q("OFFERS")],
    ("record", "pkg_format"): [_q("PACKAGE_FORMATS")],
    ("record", "pkg_distro"): [_q("PACKAGE_DISTROS")],
    ("record", "pkg_arch"): [_q("PACKAGE_ARCHES")],
    ("record", "mc_arch"): [("machine", "MACHINE_ARCHES")],
    ("record", "mc_core_band"): [("machine", "MACHINE_CORE_BANDS")],
    ("record", "mc_clock_band"): [("machine", "MACHINE_CLOCK_BANDS")],
    ("record", "mc_family"): [("machine", "MACHINE_FAMILIES")],
    ("record", "probe_reason"): [("probe", "PROBE_REASONS")],
    ("record", "probe_outcome"): _PROBE_OUT,
    ("cell", "outcome"): _PROBE_OUT,
    ("probe_end", "outcome"): _PROBE_OUT,
    ("memory_run_cell", "outcome"): _PROBE_OUT,
    ("probe_end", "step"): [("probe", "PROBE_STEPS")],
    ("probe_end", "signal"): [("probe", "PROBE_SIGNALS")],
    ("record", "adapter_code"): _ADAPTER_PARTS,
    ("adapter_cell", "code"): _ADAPTER_PARTS,
    ("verdict", "rating"): _RATING,
    ("tier", "rating"): _RATING,
    ("reason", "rating"): _RATING,
    ("verdict", "hosting"): [_q("VERDICT_HOSTINGS")],
    ("tier_offered", "tier"): [_q("VERDICT_HOSTINGS")],
    ("verdict", "arm"): [_q("VERDICT_ARMS")],
    ("verdict", "deciding"): [_HOSTING] + _PROBE_OUT + _ADAPTER_PARTS,
    ("tier", "deciding"): [_HOSTING] + _PROBE_OUT + _ADAPTER_PARTS,
    ("reason", "code"): [_HOSTING] + _PROBE_OUT + _ADAPTER_PARTS,
    ("not_measured", "code"): [_HOSTING],
    ("unmeasured", "code"): [_HOSTING],
    ("cell", "latency_code"): [_HOSTING],
    ("reason", "dimension"): _DIM,
    ("unmeasured", "dimension"): _DIM,
    ("not_measured", "dimension"): _DIM,
    ("reason_param", "name"): [_q("REASON_PARAMS")],
    ("adapter_param", "name"): [_q("REASON_PARAMS")],
    ("adapter_cell_param", "name"): [_q("REASON_PARAMS")],
    ("reason_param", "word"): [_q("REASON_PARAM_WORDS")],
    ("adapter_param", "word"): [_q("REASON_PARAM_WORDS")],
    ("adapter_cell_param", "word"): [_q("REASON_PARAM_WORDS")],
    ("tier", "tier"): [_q("RECORD_TIERS")],
    ("cell", "latency_unmeasured_reason"): [_q("MEASUREMENT_UNMEASURED_REASONS")],
    ("cell", "mem_unmeasured_reason"): [_q("MEASUREMENT_UNMEASURED_REASONS")],
    ("cell", "voices_basis"): [_q("MEASUREMENT_VOICE_BASES")],
    ("cell", "mem_basis"): [_q("MEASUREMENT_VOICE_BASES")],
    ("cell", "mem_limit_mechanism"): [_q("MEMORY_LIMIT_MECHANISMS")],
    ("cell", "note_sweep_dialect"): [_q("NOTE_SWEEP_DIALECTS")],
    ("run_step", "step"): [_q("RUN_STEPS")],
    ("run_step", "result"): [_q("STEP_RESULTS")] + _PROBE_OUT,
    ("run_step", "code"): [_q("STEP_CODES")],
    ("rejudged_owe", "code"): [_q("REJUDGE_OWES")],
    ("rejudged_owe", "measurement"): [_q("REJUDGE_MEASUREMENTS")],
}
_ADAPTER_COLUMNS = {(t, c) for (t, c), items in WORDS.items() if _ADAPTER_PARTS[0] in items and _ADAPTER_PARTS[1] in items}


class Domains:
    """The domain documents of a contract directory, validated; items resolved to their words."""

    def __init__(self, contract_dir):
        if not contract_dir or not os.path.isdir(contract_dir):
            raise Refusal("contract.dir.absent", f"{contract_dir}: no such contract directory")
        import jsonschema
        self.version, self.items = {}, {}
        for dom in DOMAINS:
            path = os.path.join(contract_dir, dom, dom + ".json")
            if not os.path.isfile(path):
                raise Refusal("contract.domain.absent", f"{path}: the {dom} domain is not in the contract directory")
            try:
                with open(path, encoding="utf-8") as f:
                    doc = json.load(f)
                jsonschema.Draft202012Validator.check_schema(doc)
                self.version[dom] = doc["info"]["version"]
                schemas = doc["components"]["schemas"]
            except (OSError, ValueError, KeyError, jsonschema.SchemaError) as e:
                raise Refusal("contract.domain.invalid", f"{path}: {e}") from e
            for name, item in schemas.items():
                self.items[(dom, name)] = [o["const"] for o in item.get("oneOf", []) if "const" in o]

    def resolve(self, column_items):
        """[(domain, item)] of a column, the hosting pattern expanded; refused when an item is not in its domain."""
        out = []
        for dom, item in column_items:
            if "*" in item:
                rx = re.compile("^" + item.replace("*", ".*") + "$")
                found = sorted(n for (d, n) in self.items if d == dom and rx.match(n))
                if not found:
                    raise Refusal("contract.item.absent", f"the {dom} domain holds no item {item}")
                out += [(dom, n) for n in found]
            else:
                if (dom, item) not in self.items:
                    raise Refusal("contract.item.absent", f"the {dom} domain holds no item {item}")
                out.append((dom, item))
        return out


class Checker:
    def __init__(self, domains):
        self.domains = domains
        self.sets = {}
        for key, column_items in WORDS.items():
            resolved = domains.resolve(column_items)
            self.sets[key] = {(d, n): set(domains.items[(d, n)]) for d, n in resolved}

    def rows(self):
        out = set()
        for (tbl, col), s in self.sets.items():
            for d, n in s:
                out.add((tbl, col, d, n))
        return sorted(out)

    def ok(self, table, col, word):
        s = self.sets[(table, col)]
        if any(word in words for words in s.values()):
            return True
        if (table, col) in _ADAPTER_COLUMNS:
            return self._adapter_code(s, word)
        return False

    def _adapter_code(self, s, word):
        host, dot, rest = word.partition(".")
        if not dot or not any(host in w for (d, n), w in s.items() if n == "QUALIFICATION_HOST_PROFILES"):
            return False
        kinds = set().union(*[w for (d, n), w in s.items() if n == "QUALIFICATION_ADAPTER_CODE_KINDS"])
        signals = set().union(*[w for (d, n), w in s.items() if n == "PROBE_SIGNALS"])
        for kind in kinds:
            if rest == kind:
                return kind not in ("resp", "exit", "signal")
            if rest.startswith(kind + "-"):
                param = rest[len(kind) + 1:]
                if kind in ("resp", "exit") and param.isdigit() and param.isascii():
                    return True
                if kind == "signal" and param in signals:
                    return True
        return False

    def describe(self, table, col):
        return ", ".join(sorted(n for d, n in self.sets[(table, col)]))


# ---------------------------------------------------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------------------------------------------------
class Row:
    def __init__(self, table, cols, links=()):
        self.table, self.cols, self.links, self.kids = table, cols, links, []


class Scope:
    def __init__(self, rows):
        self.rows = rows  # table -> cols dict (the scalar leaves written into the row of that table)
        self.kids = []


def _type_ok(kind, v):
    if kind == "bool":
        return isinstance(v, bool)
    if kind == "int":
        return isinstance(v, int) and not isinstance(v, bool)
    if kind == "real":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(v, str)


class Emitter:
    """Turns one JSON value into a tree of Rows, refusing by name; `fname` is what a refusal names."""

    def __init__(self, checker, fname):
        self.checker, self.fname = checker, fname

    def refuse(self, name, path, msg):
        raise Refusal(name, f"{self.fname}: {path or '(root)'}: {msg}")

    def leaf(self, node, v, scope, path):
        if isinstance(node, Sentence):
            return
        if isinstance(node, Present):
            if not isinstance(v, str) or not v:
                self.refuse("field-type", path, "expected non-empty text")
            scope.rows[node.table][node.col] = 1
            return
        if not _type_ok(node.kind, v):
            self.refuse("field-type", path, f"expected {node.kind}, got {json.dumps(v)}")
        if (node.table, node.col) in WORDS and not self.checker.ok(node.table, node.col, v):
            self.refuse("word-unknown", path, f"{v!r} is no word of {self.checker.describe(node.table, node.col)}")
        scope.rows[node.table][node.col] = int(v) if node.kind == "bool" else v

    def emit(self, node, v, scope, path):
        if isinstance(node, Obj):
            return self.obj(node, v, scope, path)
        if isinstance(node, Arr):
            return self.one(node, v, scope, path) if node.single else self.arr(node, v, scope, path)
        if isinstance(node, Map):
            return self.map(node, v, scope, path)
        return self.leaf(node, v, scope, path)

    def obj(self, node, v, scope, path, extra=()):
        if not isinstance(v, dict):
            self.refuse("field-type", path, "expected an object")
        if not v:
            self.refuse("empty-object", path, "an empty object is refused")
        for k in v:
            if k not in node.fields and k not in extra:
                self.refuse("field-unmapped", f"{path}.{k}" if path else k, "no column holds this field")
        for k, child in node.fields.items():
            if k in v:
                self.emit(child, v[k], scope, f"{path}.{k}" if path else k)
            else:
                if child.req:
                    self.refuse("field-absent", f"{path}.{k}" if path else k, "a required field is absent")
                if isinstance(child, Map) and child.flag:
                    scope.rows[child.flag[0]][child.flag[1]] = 0

    def arr(self, node, v, scope, path):
        if not isinstance(v, list):
            self.refuse("field-type", path, "expected an array")
        if not v and not node.always:
            self.refuse("array-empty", path, "a present empty array is refused: this array is present only with rows")
        for i, el in enumerate(v):
            self.row(node, el, scope, f"{path}[{i}]", i)

    def row(self, node, el, scope, path, ord):
        cols = dict(node.const)
        if node.ord:
            cols["ord"] = ord
        child = Scope({node.table: cols})
        if isinstance(node.item, Obj):
            self.obj(node.item, el, child, path)
        else:
            self.leaf(node.item, el, child, path)
        r = Row(node.table, cols, node.by)
        r.kids = child.kids
        scope.kids.append(r)

    def one(self, node, v, scope, path):
        cols = dict(node.const)
        child = Scope({node.table: cols})
        self.obj(node.item, v, child, path)
        r = Row(node.table, cols, node.by)
        r.kids = child.kids
        scope.kids.append(r)

    def map(self, node, v, scope, path):
        if not isinstance(v, dict):
            self.refuse("field-type", path, "expected an object")
        if not v and not node.always and not node.flag:
            self.refuse("empty-object", path, "an empty object is refused")
        if node.flag:
            scope.rows[node.flag[0]][node.flag[1]] = 1
        for name, val in v.items():
            p = f"{path}.{name}"
            cols = dict(node.const)
            if node.kind == "param":
                cols["name"] = name
                if (node.table, "name") in WORDS and not self.checker.ok(node.table, "name", name):
                    self.refuse("word-unknown", p, f"{name!r} is no word of {self.checker.describe(node.table, 'name')}")
                if isinstance(val, bool) or val is None:
                    self.refuse("field-type", p, "a param is a number or a word")
                if isinstance(val, (int, float)):
                    cols["number"] = val
                elif isinstance(val, str):
                    if not self.checker.ok(node.table, "word", val):
                        self.refuse("word-unknown", p, f"{val!r} is no word of {self.checker.describe(node.table, 'word')}")
                    cols["word"] = val
                else:
                    self.refuse("field-type", p, "a param is a number or a word")
            else:
                if not isinstance(val, str):
                    self.refuse("field-type", p, "expected text")
                a, b = node.cols
                cols[a], cols[b] = name, val
                if (node.table, a) in WORDS and not self.checker.ok(node.table, a, name):
                    self.refuse("word-unknown", p, f"{name!r} is no word of {self.checker.describe(node.table, a)}")
            scope.kids.append(Row(node.table, cols, node.by))


def _insert(cur, table, cols):
    names = list(cols)
    cur.execute(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})", [cols[n] for n in names])
    return cur.lastrowid


def _insert_tree(cur, row, parent, record_id):
    """Inserts `row` and its kids; `parent` is {record_id, ord, reason_id, set_id} of the row it belongs to."""
    cols = dict(row.cols)
    for child_col, source in row.links:
        cols[child_col] = parent[source]
    rowid = _insert(cur, row.table, cols)
    me = dict(parent)
    me["ord"] = cols.get("ord")
    if row.table == "reason":
        me["reason_id"] = rowid
    for kid in row.kids:
        _insert_tree(cur, kid, me, record_id)


class Writer:
    """Builds a new base database file."""

    def __init__(self, contract_dir, built_from):
        self.domains = Domains(contract_dir)
        self.checker = Checker(self.domains)
        self.built_from = built_from
        self.version = schema_version()

    def build(self, sets, out):
        """`sets`: [(class, set, dir)] in byte order. Writes `out` (temp file and rename); a refusal leaves nothing."""
        outdir = os.path.dirname(os.path.abspath(out))
        if not os.path.isdir(outdir):
            raise Refusal("out.dir.absent", f"{outdir}: no such directory")
        fd, tmp = tempfile.mkstemp(prefix=".qualification-", suffix=".tmp", dir=outdir)
        os.close(fd)
        try:
            self._build(sets, tmp)
            os.replace(tmp, out)
        except BaseException:
            for p in (tmp, tmp + "-journal"):
                try:
                    os.unlink(p)
                except FileNotFoundError:
                    pass
            raise

    def _build(self, sets, path):
        os.unlink(path)
        db = sqlite3.connect(path, isolation_level=None)
        try:
            db.execute("PRAGMA page_size = 4096")
            db.execute("PRAGMA journal_mode = DELETE")
            db.execute("PRAGMA foreign_keys = ON")
            with open(SCHEMA_SQL, encoding="utf-8") as f:
                db.executescript(f.read())
            cur = db.cursor()
            cur.execute("BEGIN")
            cur.execute("INSERT INTO store_info (one, user_layer, record_schema, built_from) VALUES (1, 0, ?, ?)",
                        (RECORD_SCHEMA, self.built_from))
            for dom in sorted(self.domains.version):
                cur.execute("INSERT INTO store_domain (domain, version) VALUES (?, ?)", (dom, self.domains.version[dom]))
            for tbl, col, dom, item in self.checker.rows():
                cur.execute("INSERT INTO word_check (tbl, col, domain, item) VALUES (?, ?, ?, ?)", (tbl, col, dom, item))
            plugins, claims = {}, {}
            for cls, name, d in sets:
                self._set(cur, cls, name, d, plugins, claims)
            cur.execute("COMMIT")
            bad = db.execute("PRAGMA foreign_key_check").fetchall()
            if bad:
                raise Refusal("schema-refused", f"foreign key check failed: {bad[0]}")
            db.execute("VACUUM")
            db.execute(f"PRAGMA user_version = {self.version}")
        finally:
            db.close()

    def _set(self, cur, cls, name, d, plugins, claims):
        ppath = os.path.join(d, "provenance.json")
        if not os.path.isfile(ppath):
            raise Refusal("provenance-missing", f"{ppath}: a set has a provenance.json")
        prov = _load(ppath)
        em = Emitter(self.checker, f"{cls}/{name}/provenance.json")
        scope = Scope({"record_set": {}})
        if not isinstance(prov, dict):
            em.refuse("field-type", "", "expected an object")
        settings = prov.get("settings", {})
        if not isinstance(settings, dict) or ("settings" in prov and not settings):
            em.refuse("field-type" if not isinstance(settings, dict) else "empty-object", "settings", "expected a non-empty object")
        em.obj(PROVENANCE, {k: v for k, v in prov.items() if k != "settings"}, scope, "")
        s = scope.rows["record_set"]
        if s["name"] != name or s["host_class"] != cls:
            em.refuse("set-mismatch", "set", f"provenance names {s['host_class']}/{s['name']}, the directory is {cls}/{name}")
        if prov["schema"] != PROVENANCE_SCHEMA:
            em.refuse("field-unmapped", "schema", f"expected {PROVENANCE_SCHEMA}")
        sid = _insert(cur, "record_set", s)
        for k, v in settings.items():
            if k == "note":
                if not isinstance(v, str):
                    em.refuse("field-type", "settings.note", "a sentence is text")
                continue
            if not isinstance(v, str):
                em.refuse("field-type", f"settings.{k}", "expected text")
            if not self.checker.ok("set_setting", "key", k):
                em.refuse("word-unknown", f"settings.{k}", f"{k!r} is no word of {self.checker.describe('set_setting', 'key')}")
            cur.execute("INSERT INTO set_setting (set_id, key, value) VALUES (?, ?, ?)", (sid, k, v))
        for r in scope.kids:
            _insert_tree(cur, r, {"set_id": sid}, None)
        files = sorted((f for f in os.listdir(d) if f.endswith(".qualification.json")), key=os.fsencode)
        for f in files:
            self._record(cur, cls, name, d, sid, f, plugins, claims)

    def _record(self, cur, cls, setname, d, sid, fname, plugins, claims):
        label = f"{cls}/{setname}/{fname}"
        stem = fname[: -len(".qualification.json")]
        recname, dot, offer = stem.rpartition(".")
        if not dot or not recname:
            raise Refusal("file-name", f"{label}: the name is <name>.<offer>.qualification.json")
        rec = _load(os.path.join(d, fname))
        em = Emitter(self.checker, label)
        scope = Scope({"record": {}, "plugin": {}})
        em.obj(RECORD, rec, scope, "")
        if rec["schema"] != RECORD_SCHEMA:
            em.refuse("field-unmapped", "schema", f"expected {RECORD_SCHEMA}")
        r, p = scope.rows["record"], scope.rows["plugin"]
        if not self.checker.ok("record", "offer", offer):
            em.refuse("word-unknown", "(file name)", f"{offer!r} is no word of {self.checker.describe('record', 'offer')}")
        # the probe output the record judged
        pf = os.path.join(d, r["probe_file"])
        if os.path.basename(r["probe_file"]) != r["probe_file"] or not os.path.isfile(pf):
            em.refuse("probe-missing", "probe.file", f"{r['probe_file']}: no such probe output in the set")
        with open(pf, "rb") as f:
            data = f.read()
        if hashlib.sha256(data).hexdigest() != r["probe_sha256"] or len(data) != r["probe_bytes"]:
            em.refuse("probe-mismatch", "probe", f"{r['probe_file']} is not the probe output the record names (sha256 or bytes differ)")
        key = (p["sha256"], p["format"], p["uri"])
        try:
            if key not in plugins:
                plugins[key] = _insert(cur, "plugin", p)
            pid = plugins[key]
            cols = dict(r)
            cols.update(plugin_id=pid, set_id=sid, host_class=cls, offer=offer, name=recname)
            rid = _insert(cur, "record", cols)
            for kid in scope.kids:
                _insert_tree(cur, kid, {"record_id": rid}, rid)
            for cell in (k for k in scope.kids if k.table == "cell"):
                ck = (pid, offer, cls, cell.cols["rate"], cell.cols["quantum"])
                if ck in claims:
                    raise Refusal("claim-duplicate", f"{label}: the cell {cell.cols['rate']}/{cell.cols['quantum']} of this key, "
                                  f"offer and class is already claimed by {claims[ck]}")
                claims[ck] = label
                cur.execute("INSERT INTO claim (record_id, plugin_id, offer, host_class, rate, quantum) VALUES (?, ?, ?, ?, ?, ?)",
                            (rid,) + ck)
        except sqlite3.IntegrityError as e:
            raise Refusal("schema-refused", f"{label}: {e}") from e


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise Refusal("file-unreadable", f"{path}: {e}") from e


def walk(records_dir, classes=None):
    """[(class, set, dir)] in byte order of their paths."""
    if not os.path.isdir(records_dir):
        raise Refusal("records.dir.absent", f"{records_dir}: no such directory")
    found = []
    for cls in sorted(os.listdir(records_dir), key=os.fsencode):
        cdir = os.path.join(records_dir, cls)
        if not os.path.isdir(cdir) or (classes and cls not in classes):
            continue
        for s in sorted(os.listdir(cdir), key=os.fsencode):
            if os.path.isdir(os.path.join(cdir, s)):
                found.append((cls, s, os.path.join(cdir, s)))
    for c in classes or ():
        if not any(f[0] == c for f in found):
            raise Refusal("class-absent", f"{records_dir}/{c}: the class has no set")
    return found


def built_from(records_dir, built_from_file=None):
    """The commit the base is built from: BUILT_FROM when given, else git's HEAD; never guessed."""
    if built_from_file:
        try:
            with open(built_from_file, encoding="utf-8") as f:
                text = f.read().strip()
        except OSError as e:
            raise Refusal("built-from-unknown", f"{built_from_file}: {e}") from e
        if re.fullmatch(r"[0-9a-f]{40}", text):
            return text
        raise Refusal("built-from-unknown", f"{built_from_file} holds no commit ({text[:48]!r}: not substituted by git archive)")
    try:
        out = subprocess.run(["git", "-C", records_dir, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as e:
        raise Refusal("built-from-unknown", f"{records_dir} is no git checkout and no BUILT_FROM file was given") from e
    if not re.fullmatch(r"[0-9a-f]{40}", out):
        raise Refusal("built-from-unknown", f"git rev-parse HEAD gave {out!r}")
    return out


def build_base(records_dir, out, contract_dir, built_from_file=None, classes=None):
    sets = walk(records_dir, classes)
    # the contract directory is read first: an absent one is the first refusal
    writer = Writer(contract_dir, built_from(records_dir, built_from_file))
    writer.build(sets, out)


# ---------------------------------------------------------------------------------------------------------------------
# Exporting
# ---------------------------------------------------------------------------------------------------------------------
class Exporter:
    """Rows back to records, from the node description the writer used."""

    def __init__(self, db):
        db.row_factory = sqlite3.Row
        self.db = db
        self.index = {}
        self.tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    def lookup(self, table, key_cols, key):
        idx = self.index.get((table, key_cols))
        if idx is None:
            idx = {}
            for row in self.db.execute(f"SELECT * FROM {table} ORDER BY rowid"):
                d = dict(row)
                idx.setdefault(tuple(d[c] for c in key_cols), []).append(d)
            self.index[(table, key_cols)] = idx
        return idx.get(key, [])

    def export_record(self, record_id):
        rec = dict(self.db.execute("SELECT * FROM record WHERE record_id = ?", (record_id,)).fetchone())
        plug = dict(self.db.execute("SELECT * FROM plugin WHERE plugin_id = ?", (rec["plugin_id"],)).fetchone())
        v = self.build(RECORD, {"record": rec, "plugin": plug}, rec)
        return v

    def export_set(self, set_id):
        s = dict(self.db.execute("SELECT * FROM record_set WHERE set_id = ?", (set_id,)).fetchone())
        v = self.build(PROVENANCE, {"record_set": s}, s)
        settings = {r["key"]: r["value"] for r in self.db.execute("SELECT * FROM set_setting WHERE set_id = ? ORDER BY rowid", (set_id,))}
        if settings:
            v["settings"] = settings
        else:
            v.pop("settings", None)
        return v

    def build(self, node, scope, parent):
        if isinstance(node, (Sentence, Present)):
            return ABSENT
        if isinstance(node, Leaf):
            val = scope[node.table][node.col]
            if val is None:
                return ABSENT
            if node.kind == "bool":
                return bool(val)
            if node.kind == "real":
                return float(val)
            return val
        if isinstance(node, Obj):
            if node.anchor and scope[node.anchor[0]][node.anchor[1]] is None:
                return ABSENT
            out = {}
            for k, child in node.fields.items():
                v = self.build(child, scope, parent)
                if v is not ABSENT:
                    out[k] = v
            if not out and not node.anchor:
                return ABSENT
            return out
        if isinstance(node, Arr):
            key_cols = tuple(c for c, _ in node.by) + tuple(node.const)
            key = tuple(parent[p] for _, p in node.by) + tuple(node.const.values())
            rows = self.lookup(node.table, key_cols, key)
            if node.single:
                if not rows:
                    return ABSENT
                return self.build(node.item, {node.table: rows[0]}, rows[0])
            if not rows:
                return [] if node.always else ABSENT
            return [self.build(node.item, {node.table: r}, r) for r in rows]
        if isinstance(node, Map):
            if node.flag and scope[node.flag[0]][node.flag[1]] != 1:
                return ABSENT
            key_cols = tuple(c for c, _ in node.by) + tuple(node.const)
            key = tuple(parent[p] for _, p in node.by) + tuple(node.const.values())
            rows = self.lookup(node.table, key_cols, key)
            if not rows and not node.always and not node.flag:
                return ABSENT
            out = {}
            for r in rows:
                if node.kind == "param":
                    out[r["name"]] = r["number"] if r["number"] is not None else r["word"]
                else:
                    out[r[node.cols[0]]] = r[node.cols[1]]
            return out
        raise TypeError(node)
