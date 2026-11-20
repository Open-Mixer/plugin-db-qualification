# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
"""The qualification store's record writer and exporter, one module (this repository's qualification store spec, sections
3, 5 and 6.1): a record to rows, rows back to a record, and `put` and `delete` of a record in a user or system layer.

One declarative description of a record (RECORD below) drives both directions, so a field is mapped in one place and the
writer and the exporter cannot disagree about it. It is the module `plugin-qualification-db-write` ships and the base
builder (tools/records-db.py) imports.

The module reads no environment variable and knows no list of words: the words come from the contract directory the
caller passes.
"""
import glob
import json
import os
import pwd
import re
import sqlite3
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# the DDL: beside the module when it is installed (plugin-qualification-db-schema's file is the one copy, the package
# links nothing else), in schema/ of a checkout
SCHEMA_SQL = os.path.join(HERE, "qualification.sql")
if not os.path.exists(SCHEMA_SQL):
    SCHEMA_SQL = os.path.join(ROOT, "schema", "qualification.sql")
RECORD_SCHEMA = "plugin-qualify.qualification-record/1"
DOMAINS = ("qualification", "machine", "probe", "plugin-db", "hosting")
# the first four are domain documents: <contractdir>/<domain>/<domain>.json. `hosting` is the one exception (the owner froze
# vocabulary moves on 2026-11-19): its words are the codes of the package omx-clap (its data/hosting.json and
# data/hosting/*.json, items of kind codes), installed by its `make install-contract` as
# <contractdir>/<schema major>/omx-clap/; store_domain holds hosting at the version of that package's MANIFEST.json.
HOSTING = "hosting"
HOSTING_PACKAGE = "omx-clap"
DOCUMENT_DOMAINS = tuple(d for d in DOMAINS if d != HOSTING)


class Refusal(Exception):
    """A refusal by name: the name is the first thing the command prints."""

    def __init__(self, name, message):
        super().__init__(f"{name}: {message}")
        self.name = name
        self.message = message


def schema_version(schema=None):
    """PQDB_SCHEMA_VERSION, as the DDL's header gives it ("The qualification store, user_version N"): the DDL is the one
    place the writer reads it from, and tools/test_qualification_db_write.py holds it equal to the reader's header."""
    path = schema or SCHEMA_SQL
    try:
        with open(path, encoding="utf-8") as f:
            m = re.search(r"^-- The qualification store, user_version (\d+)", f.read(), re.M)
    except OSError as e:
        raise Refusal("schema-unreadable", f"{path}: {e}") from e
    if not m:
        raise Refusal("schema-version", f"{path} names no user_version in its header")
    return int(m.group(1))


# ---------------------------------------------------------------------------------------------------------------------
# The description of a record: nodes. A node says how one JSON value maps to rows and back.
# ---------------------------------------------------------------------------------------------------------------------
ABSENT = object()


class Leaf:
    """`nullable`: a JSON null is a value (stored as NULL, exported as null), as the measured and adjusted verdicts of a
    history block are; any other leaf is absent when NULL."""

    def __init__(self, table, col, kind="text", req=False, nullable=False):
        self.table, self.col, self.kind, self.req, self.nullable = table, col, kind, req, nullable


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
    row, found by `const` (the tiers). `flag` (table, column) stores the list's presence as 1, so an empty list is data
    (hostExtensions); such a list is not required by the node: the caller says for which records it is."""

    def __init__(self, table, item, by=(("record_id", "record_id"),), always=False, ord=True, const=None, single=False,
                 flag=None):
        self.table, self.item, self.by, self.always, self.ord = table, item, tuple(by), always or bool(flag), ord
        self.const, self.single, self.flag = const or {}, single, flag
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
        "latencyMs": O(c, "latency_ms", "real"),
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
            "ownThreads": O(c, "rt_own_threads", "int"),
            "otherThreads": Obj({
                "allocations": O(c, "rt_other_allocations", "int"),
                "locks": O(c, "rt_other_locks", "int"),
                "syscalls": O(c, "rt_other_syscalls", "int"),
            }),
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
        "plugin": Obj({"format": L("plugin", "format"), "id": L("plugin", "uri"), "name": O(r, "plugin_name")}, req=True),
        "binary": Obj({
            "path": L(r, "binary_path"),
            "sha256": L("plugin", "sha256"),
            "files": Arr("record_file", Obj({"path": L("record_file", "path"), "sha256": L("record_file", "sha256")}), always=True),
            "layout": Obj({"scheme": L(r, "layout_scheme"), "sha256": L(r, "layout_sha256")}),
            "unpinnable": Present(r, "unpinnable"),
        }, req=True),
        "hostExtensions": Arr("record_extension", Leaf("record_extension", "extension", "text", True),
                              flag=(r, "host_extensions")),
        "testedVersion": O(r, "tested_version"),
        "measuredAt": L(r, "measured_at"),
        "latencyLineMs": O(r, "latency_line_ms", "real"),
        "rules": O(r, "rules"),
        "history": Arr("record_history", Obj({
            "hostClass": L("record_history", "host_class"),
            "file": L("record_history", "file"),
            "at": L("record_history", "at"),
            "key": Obj({"uri": L("record_history", "key_uri"), "digest": L("record_history", "key_digest")}),
            "found": L("record_history", "found", "bool"),
            "windows": Obj({"solo": L("record_history", "windows_solo", "int"), "grouped": L("record_history", "windows_grouped", "int")}),
            "summary": Obj({"crashed": L("record_history", "summary_crashed", "bool"),
                            "raisesXruns": L("record_history", "summary_raises_xruns", "bool")}),
            "unknownKeys": Map("history_unknown_key", by=(("record_id", "record_id"), ("history_ord", "ord")),
                               flag=("record_history", "unknown_keys"), kind="text", cols=("name", "value")),
            "verdicts": Arr("history_verdict", Obj({
                "host": L("history_verdict", "host"),
                "measured": Leaf("history_verdict", "measured", "text", True, True),
                "adjusted": Leaf("history_verdict", "adjusted", "text", True, True),
                "move": L("history_verdict", "move"),
                "reason": L("history_verdict", "reason"),
                "blockedBy": Arr("history_blocked", Leaf("history_blocked", "code", "text", True),
                                 by=(("record_id", "record_id"), ("history_ord", "history_ord"), ("verdict_ord", "ord")),
                                 flag=("history_verdict", "blocked_by")),
            }), by=(("record_id", "record_id"), ("history_ord", "ord")), always=True),
        })),
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
                    "dspLoadOff": O("run_step", "pool_dsp_load_off", "real"),
                    "dspLoadOn": O("run_step", "pool_dsp_load_on", "real"),
                    "xrunsOff": O("run_step", "pool_xruns_off", "int"),
                    "xrunsOn": O("run_step", "pool_xruns_on", "int"),
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




RECORD = _record()


# ---------------------------------------------------------------------------------------------------------------------
# Words: the owner items of each word column (section 3.4). The item names are the table's; the words are the domains'.
# ---------------------------------------------------------------------------------------------------------------------
def _q(name):
    return ("qualification", "QUALIFICATION_" + name)


_ADAPTER_PARTS = [_q("ADAPTER_HOSTS"), _q("ADAPTER_CODE_KINDS"), ("probe", "PROBE_SIGNALS")]
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
    ("record", "adapter_host"): [_q("ADAPTER_HOSTS")],
    ("history_verdict", "host"): _PROFILE,
    ("history_verdict", "measured"): [_q("PIN_VERDICTS")],
    ("history_verdict", "adjusted"): [_q("PIN_VERDICTS")],
    ("history_verdict", "move"): [_q("HISTORY_MOVES")],
    ("history_verdict", "reason"): [_q("HISTORY_REASONS")],
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
    ("history_blocked", "code"): [_q("HISTORY_BLOCKERS"), _HOSTING] + _PROBE_OUT + _ADAPTER_PARTS,
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
        for dom in DOCUMENT_DOMAINS:
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
        self._hosting(contract_dir)

    def _hosting(self, contract_dir):
        """The package's own files: <contractdir>/<schema major>/omx-clap/{hosting.json, hosting/*.json, MANIFEST.json}.
        An item of kind codes holds its words as the `code` of each of its `codes`; the version is the MANIFEST's."""
        found = sorted(glob.glob(os.path.join(glob.escape(contract_dir), "[0-9]*", HOSTING_PACKAGE, "MANIFEST.json")))
        if not found:
            raise Refusal("contract.domain.absent", f"{contract_dir}: the package {HOSTING_PACKAGE} is not in the contract "
                          f"directory (<schema major>/{HOSTING_PACKAGE}/MANIFEST.json): the hosting words are its codes")
        if len(found) > 1:
            raise Refusal("contract.domain.invalid", f"{found[0]} and {found[1]}: the package {HOSTING_PACKAGE} is installed twice")
        pkg = os.path.dirname(found[0])
        try:
            with open(found[0], encoding="utf-8") as f:
                self.version[HOSTING] = json.load(f)["version"]
            files = [os.path.join(pkg, "hosting.json")] + sorted(glob.glob(os.path.join(glob.escape(pkg), "hosting", "*.json")))
            for path in files:
                with open(path, encoding="utf-8") as f:
                    doc = json.load(f)
                for name, item in doc.items():
                    if isinstance(item, dict) and item.get("kind") == "codes":
                        self.items[(HOSTING, name)] = [c["code"] for c in item["codes"].values()]
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            raise Refusal("contract.domain.invalid", f"{pkg}: {e}") from e

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
        if not dot or not any(host in w for (d, n), w in s.items() if n == "QUALIFICATION_ADAPTER_HOSTS"):
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
        if v is None and node.nullable:
            scope.rows[node.table][node.col] = None
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
        if node.flag:
            scope.rows[node.flag[0]][node.flag[1]] = 1
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
    if row.table == "record_history":
        me["history_ord"] = me["ord"]
    if row.table == "reason":
        me["reason_id"] = rowid
    for kid in row.kids:
        _insert_tree(cur, kid, me, record_id)




def _insert_record(cur, scope, pid, extra):
    """The record row and its tree, from the rows `parse_record` made; `extra` holds set_id, host_class, offer, name."""
    cols = dict(scope.rows["record"])
    cols.update(extra, plugin_id=pid)
    rid = _insert(cur, "record", cols)
    for kid in scope.kids:
        _insert_tree(cur, kid, {"record_id": rid}, rid)
    return rid


def parse_record(checker, label, rec):
    """A record's value to its rows, refusing by name: section 3.5 (words, fields) and section 3.7 (the binary)."""
    em = Emitter(checker, label)
    scope = Scope({"record": {}, "plugin": {}})
    em.obj(RECORD, rec, scope, "")
    if rec["schema"] != RECORD_SCHEMA:
        em.refuse("field-unmapped", "schema", f"expected {RECORD_SCHEMA}")
    r, p = scope.rows["record"], scope.rows["plugin"]
    # section 6.2: a CLAP record holds the host extensions the run offered (an empty list is data; a probe that ended without
    # one gives the record none, nothing guessed); an LV2 record none
    if p["format"] != "clap" and "host_extensions" in r:
        em.refuse("field-unmapped", "hostExtensions", f"no column holds this field of a {p['format']} record")
    check_binary(em, rec["binary"])
    return em, scope


def check_binary(em, binary):
    """Section 3.7: the path relative, the list ordered, unique and not empty, the binary one of its entries, and the key
    the SHA-256 of that entry. Each refusal names the path; nothing is made relative, sorted or removed."""
    path = binary["path"]
    if path.startswith("/"):
        em.refuse("path-absolute", "binary.path", f"{path!r} is not relative to the item's install root")
    files = binary["files"]
    if not files:
        em.refuse("files-empty", "binary.files", "the list holds no file")
    seen = set()
    for i, f in enumerate(files):
        if f["path"] in seen:
            em.refuse("files-duplicate", f"binary.files[{i}].path", f"{f['path']!r} is in the list twice")
        seen.add(f["path"])
    for i in range(1, len(files)):
        if os.fsencode(files[i - 1]["path"]) > os.fsencode(files[i]["path"]):
            em.refuse("files-unordered", f"binary.files[{i}].path",
                      f"{files[i]['path']!r} comes after {files[i - 1]['path']!r}: the list is ascending by path, as bytes")
    entry = next((f for f in files if f["path"] == path), None)
    if entry is None:
        em.refuse("binary-not-in-files", "binary.path", f"{path!r} is no entry of binary.files")
    if entry["sha256"] != binary["sha256"]:
        em.refuse("key-not-the-binary", "binary.sha256",
                  f"{binary['sha256']} is not the SHA-256 of the entry {path!r} ({entry['sha256']})")














# ---------------------------------------------------------------------------------------------------------------------
# The layer writer (section 6.1): put and delete into the user or the system layer file
# ---------------------------------------------------------------------------------------------------------------------
LAYER_FILE = "qualification.sqlite"
SYSTEM_LAYER = "/var/lib/omx/qualification/" + LAYER_FILE
USER_LAYER = ".local/share/omx/qualification/" + LAYER_FILE


def layer_path(scope, root=None):
    """The layer file of a scope (section 2). `root`, for tests, names the directory that holds the file instead."""
    if scope not in ("user", "system"):
        raise Refusal("scope-unknown", f"{scope!r} is not a scope: user or system")
    if root is not None:
        return os.path.join(root, LAYER_FILE)
    if scope == "system":
        return SYSTEM_LAYER
    return os.path.join(pwd.getpwuid(os.geteuid()).pw_dir, USER_LAYER)


def _open_layer(path, version):
    """An existing layer, opened read-write with foreign keys on, and checked: a store of this version, a user layer."""
    try:
        db = sqlite3.connect(path, isolation_level=None)
        db.execute("PRAGMA foreign_keys = ON")
        got = db.execute("PRAGMA user_version").fetchone()[0]
        if got == 0:
            db.close()
            raise Refusal("not-a-store", f"{path}: user_version 0: not a qualification store")
        if got != version:
            db.close()
            raise Refusal("schema-other", f"{path}: user_version {got}, this writer writes {version}")
        layer = db.execute("SELECT user_layer FROM store_info").fetchone()
    except sqlite3.DatabaseError as e:
        raise Refusal("not-a-store", f"{path}: {e}") from e
    if not layer or layer[0] != 1:
        db.close()
        raise Refusal("not-a-user-layer", f"{path}: store_info does not say a user layer")
    return db


def _words(cur, domains, checker):
    """The domains the words were checked against, and the items of each word column (the layer holds the ones of its
    last write)."""
    cur.execute("DELETE FROM word_check")
    cur.execute("DELETE FROM store_domain")
    for dom in sorted(domains.version):
        cur.execute("INSERT INTO store_domain (domain, version) VALUES (?, ?)", (dom, domains.version[dom]))
    for tbl, col, dom, item in checker.rows():
        cur.execute("INSERT INTO word_check (tbl, col, domain, item) VALUES (?, ?, ?, ?)", (tbl, col, dom, item))


def _plugin(cur, p):
    row = cur.execute("SELECT plugin_id FROM plugin WHERE sha256 = ? AND format = ? AND uri = ?",
                      (p["sha256"], p["format"], p["uri"])).fetchone()
    return row[0] if row else None


def put(rec, *, scope, offer, host_class, contract_dir, root=None, schema=None):
    """One record into the scope's layer, in one transaction: the layer's record of the same shadow key (sha256, format,
    uri, offer, host_class) is replaced whole. `offer` and `host_class` are the key's other words; the name of the record
    is its probe file's name without `.<offer>.probe.json`. A missing layer is created from the DDL. A refusal writes
    nothing, not even the file."""
    path = layer_path(scope, root)
    schema = schema or SCHEMA_SQL
    version = schema_version(schema)
    domains = Domains(contract_dir)
    checker = Checker(domains)
    label = "record"
    em = Emitter(checker, label)
    for col, word in (("offer", offer), ("host_class", host_class)):
        if not isinstance(word, str) or not checker.ok("record", col, word):
            em.refuse("word-unknown", col, f"{word!r} is no word of {checker.describe('record', col)}")
    if not isinstance(rec, dict):
        em.refuse("field-type", "", "expected an object")
    em, rows = parse_record(checker, label, rec)
    r, p = rows.rows["record"], rows.rows["plugin"]
    suffix = f".{offer}.probe.json"
    pf = r["probe_file"]
    if os.path.basename(pf) != pf or not pf.endswith(suffix) or pf == suffix:
        em.refuse("file-name", "probe.file", f"{pf!r}: the name is <name>{suffix}")
    extra = dict(set_id=None, host_class=host_class, offer=offer, name=pf[: -len(suffix)])
    outdir = os.path.dirname(os.path.abspath(path))
    if os.path.exists(path):
        db = _open_layer(path, version)
        try:
            db.execute("BEGIN IMMEDIATE")
            try:
                _write(db.cursor(), domains, checker, rows, p, extra, label)
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        finally:
            db.close()
        return
    made = not os.path.isdir(outdir)
    os.makedirs(outdir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".qualification-", suffix=".tmp", dir=outdir)
    os.close(fd)
    try:
        os.unlink(tmp)
        db = sqlite3.connect(tmp, isolation_level=None)
        try:
            db.execute("PRAGMA page_size = 4096")
            db.execute("PRAGMA journal_mode = DELETE")
            db.execute("PRAGMA foreign_keys = ON")
            with open(schema, encoding="utf-8") as f:
                db.executescript(f.read())
            cur = db.cursor()
            cur.execute("BEGIN")
            cur.execute("INSERT INTO store_info (one, user_layer, record_schema, built_from) VALUES (1, 1, ?, NULL)", (RECORD_SCHEMA,))
            _write(cur, domains, checker, rows, p, extra, label)
            cur.execute("COMMIT")
            db.execute(f"PRAGMA user_version = {version}")
        finally:
            db.close()
        os.replace(tmp, path)
    except BaseException:
        for t in (tmp, tmp + "-journal"):
            try:
                os.unlink(t)
            except FileNotFoundError:
                pass
        if made:
            try:
                os.rmdir(outdir)
            except OSError:
                pass
        raise


def _write(cur, domains, checker, rows, p, extra, label):
    try:
        _words(cur, domains, checker)
        pid = _plugin(cur, p)
        if pid is None:
            pid = _insert(cur, "plugin", p)
        else:
            cur.execute("DELETE FROM record WHERE plugin_id = ? AND offer = ? AND host_class = ?",
                        (pid, extra["offer"], extra["host_class"]))
        rid = _insert_record(cur, rows, pid, extra)
        for cell in (k for k in rows.kids if k.table == "cell"):
            cur.execute("INSERT INTO claim (record_id, plugin_id, offer, host_class, rate, quantum) VALUES (?, ?, ?, ?, ?, ?)",
                        (rid, pid, extra["offer"], extra["host_class"], cell.cols["rate"], cell.cols["quantum"]))
    except sqlite3.IntegrityError as e:
        raise Refusal("schema-refused", f"{label}: {e}") from e


def delete(*, scope, sha256, format, uri, offer, host_class, root=None, schema=None):
    """The layer's record of a shadow key, in one transaction. A key the layer does not hold, and a layer that is not
    there, are no error and change nothing. Nothing is deleted from the base: it is no layer of a scope."""
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise Refusal("field-type", f"--sha256: {sha256!r} is not 64 lower-case hex digits")
    path = layer_path(scope, root)
    if not os.path.exists(path):
        return
    db = _open_layer(path, schema_version(schema or SCHEMA_SQL))
    try:
        db.execute("BEGIN IMMEDIATE")
        try:
            cur = db.cursor()
            pid = _plugin(cur, {"sha256": sha256, "format": format, "uri": uri})
            if pid is not None:
                cur.execute("DELETE FROM record WHERE plugin_id = ? AND offer = ? AND host_class = ?", (pid, offer, host_class))
                if not cur.execute("SELECT 1 FROM record WHERE plugin_id = ? LIMIT 1", (pid,)).fetchone():
                    cur.execute("DELETE FROM plugin WHERE plugin_id = ?", (pid,))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    finally:
        db.close()


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

    def build(self, node, scope, parent):
        if isinstance(node, (Sentence, Present)):
            return ABSENT
        if isinstance(node, Leaf):
            val = scope[node.table][node.col]
            if val is None:
                return None if node.nullable else ABSENT
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
            if node.flag and scope[node.flag[0]][node.flag[1]] != 1:
                return ABSENT
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
