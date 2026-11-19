<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com> -->
# Qualification records in SQLite: one base database, one user layer

Status: SPEC. Nothing here is built. Three changes follow it, in this repository:

1. this spec;
2. the migration: `schema/qualification.sql`, the writer module and the tool that builds the base database from
   `records/`, the round-trip test, and the package carrying the database beside today's files;
3. the reader: a C library and its command, `plugin-qualification-db`, with red-first tests.

No consumer reads the database during the current release pass. The consumers switch in one change right after the
console's 0.2.1 release; that change is not specified here.

## 1. Owner, and where this spec lives

**Owner: plugin-db-qualification** (Open-Mixer/plugin-db-qualification). The base database, the migration and the
reader are this repository's.

The evidence:

- Every current record is here and nowhere else: `records/<host class>/<set>/`, 12,953 records and 12,953 probe outputs
  in 11 sets of 2 host classes (`rpi5`: one set, 1,863 records; `x86-64`: ten sets of one cell each, 1,109 records
  each), with one `provenance.json` per set. They cover 2,278 distinct plugins by (format, SHA-256, id).
- This repository builds and ships them: the package `plugin-qualification-records` (`debian/`,
  `packaging/plugin-qualification-records.spec`), its checks (`tools/check-records.py`, `tools/sets.py check`) and
  its measurement jobs (`tools/fedora44/`, `tools/rpi5/`).
- plugin-db names this repository as the writer of its shipped layer: `data/db.json` of plugin-db describes the
  `reference` layer as "a record from a reference machine, installed by plugin-db-qualification, read only".
- plugin-db's store (`/var/lib/plugin-db`, `$XDG_STATE_HOME/plugin-db`) holds a machine's own layers as one JSON file
  per layer and per entry, and names no place for shipped records. It is a different store with its own grammar; the
  judged layer plugin-qualify writes into it is derived from a record, not the record.
- plugin-qualify PRODUCES the records and OWNS THEIR WORDS: the record format `plugin-qualify.qualification-record/1`
  (`src/qualification-record.ts`) and the `qualification` domain (`contract.d/qualification/qualification.json`,
  `info.x-owner: plugin-qualify`), shipped in `plugin-qualify-contract`. It holds no record data of its own beyond test
  fixtures.

The spec is this repository's first design spec; each is named by its date and topic.

### Ownership of the words (producer, changer, owner domain)

| what | producer | who changes it | owner domain |
| --- | --- | --- | --- |
| record fields and their meaning | plugin-qualify (it writes each record) | plugin-qualify, in its record format | plugin-qualify |
| words a record holds (ratings, reasons, dimensions, bases) | plugin-qualify | plugin-qualify, in a minor of the `qualification` domain | `qualification` (plugin-qualify) |
| hosting codes in reasons (`hosting.*`) | omx-clap-core's hosting tables, copied by plugin-qualify | omx-clap-core | omx-clap-core (no domain document yet; open question 2) |
| probe outcomes (`probe.*`) | plugin-hostd's probe | plugin-hostd | plugin-hostd (no domain document yet; open question 2) |
| plugin key (SHA-256, format, uri) | plugin-qualify, from the binary | nobody: it is the bytes | plugin-db's address formats (`clap`, `lv2`) |
| package fields | the measuring run (none today) | plugin-qualify's record format | plugin-qualify (open question 3) |
| the database layout, `user_version`, the reader | this repository | this repository | plugin-db-qualification |

The database stores words and checks them against their domain; it never defines a word.

## 2. Files and locations

| file | path | shipped or written by | opened |
| --- | --- | --- | --- |
| base database | `/usr/share/omx/qualification/qualification.sqlite` | the package `plugin-qualification-records`, one per architecture, built at package build from `records/` | read only, immutable |
| user layer, user scope | `~/.local/share/omx/qualification/qualification.sqlite` (the XDG data directory's default, with the home from the password database) | plugin-qualify-sync of that user, after the consumer switch; nobody before it | read only by readers; read-write by the writer only |
| user layer, system scope | `/var/lib/omx/qualification/qualification.sqlite` (the system sync's `qualification_dir`) | `plugin-qualify-sync --system`, after the consumer switch | the same |
| the DDL | `schema/qualification.sql` in this repository | read by the writer at build and when it creates a user layer | |

The base database sits beside today's `<host class>/<set>/` directories, which stay as they are (section 5). A
database file in that directory is no `<host class>` directory, so `plugin-qualify-sync`'s distributed reader, which
reads `<dir>/<host class>/` by name, does not see it.

**Pointing elsewhere** follows omx-contract's docs/runtime-data.md:

- The production entry point, `pqdb_open(scope)`, takes no path and reads no environment variable: not
  `XDG_DATA_HOME`, not `HOME`, not `OMX_CONTRACT_PATH`. The user scope's home comes from `getpwuid(geteuid())`. A stray
  variable in a service's environment does not change which records it runs on.
- `pqdb_open_at(base, user, contract_dir)` takes the three places. It is for test harnesses and the command only;
  the header says TEST AND COMMAND ONLY, and a production binary does not call it.
- The command `plugin-qualification-db` takes `--base <path>`, `--user <path>` and `--contract-dir <dir>`, and when a
  flag is absent reads `PLUGIN_QUALIFICATION_DB_BASE`, `PLUGIN_QUALIFICATION_DB_USER` and `OMX_CONTRACT_PATH`, then
  falls back to the installed places. Only the command and the tests read these variables.
- The migration tool (`tools/records-db.py`) is a build tool: it takes `--records <dir>`, `--out <file>` and
  `--contract-dir <dir>` as required flags and reads no variable.

## 3. Schema

### 3.1 What a record is

A RECORD is one `*.qualification.json` file of today: the judgement of one plugin binary (its key), under one offer
(`default` or `custom`), measured on one host class, holding one or more grid cells (rate and quantum). A RESULT is one
record at one of its grid cells: that is what a reader returns.

A record's PLUGIN KEY is (`sha256`, `format`, `uri`): `binary.sha256`, `plugin.format`, and `plugin.id` (the CLAP id or
the LV2 URI). The SHA-256 is the identity. The PACKAGE FIELDS beside it (format, name, version, release, distro, arch)
say which installed package the binary came from; they let an installed package find its results and keep the data
readable, and they are never part of the key.

### 3.2 Values: words, names, numbers, and no sentences

- A WORD is a value of a closed set: a rating, a reason, a dimension, a basis. A word column holds no whitespace
  (`WORD(c)` below is `length(c) > 0 AND instr(c, ' ') = 0 AND instr(c, char(9)) = 0 AND instr(c, char(10)) = 0`), and
  the table `word_check` names the domain item that holds its words. The writer refuses a word not in its item; the
  reader checks every distinct word at open (section 6).
- A NAME is an identifier written by a program: an id, a path, a hash, a version, a time, a symbol. It is stored as
  written and is not checked against a domain.
- A NUMBER is stored as INTEGER (counts, rates, quanta, frames, kilobytes, bytes) or REAL (figures that may be
  fractional). Every table is `STRICT`, so a value of the wrong type is refused at insert.
- A SENTENCE, prose written for a person, is not stored. Section 3.5 lists every field of today's records and
  provenances that is one. The base database records the commit it was built from (`store_info.built_from`), where the
  text of every record stays.
- An optional JSON object is present when at least one of its columns is not NULL. The writer refuses an empty object
  (`{}`) by name, except a map of the always-present list of section 3.3 (`reasons[].params`).
- A boolean is INTEGER with `CHECK (c IN (0, 1))`.

### 3.3 DDL

`schema/qualification.sql` holds exactly this, with `WORD(c)` written out. Foreign keys are declared
`ON DELETE CASCADE`; the writer runs with `PRAGMA foreign_keys = ON`.

```sql
CREATE TABLE store_info (
  one            INTEGER PRIMARY KEY CHECK (one = 1),
  layer          TEXT NOT NULL CHECK (layer IN ('base', 'user')),
  domain         TEXT NOT NULL CHECK (domain = 'qualification'),
  domain_version TEXT NOT NULL,            -- info.version of the domain the words were checked against
  record_schema  TEXT NOT NULL,            -- 'plugin-qualify.qualification-record/1'
  built_from     TEXT CHECK (built_from IS NULL OR (length(built_from) = 40 AND built_from NOT GLOB '*[^0-9a-f]*'))
                                           -- base: the commit of this repository; user: NULL
) STRICT;

CREATE TABLE word_check (                  -- which domain item holds the words of a column
  tbl  TEXT NOT NULL,
  col  TEXT NOT NULL,
  item TEXT NOT NULL,                      -- a components.schemas name of the domain, e.g. QUALIFICATION_MEASUREMENT_VERDICT_RATINGS
  PRIMARY KEY (tbl, col)
) STRICT;

CREATE TABLE plugin (
  plugin_id INTEGER PRIMARY KEY,
  sha256    TEXT NOT NULL CHECK (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
  format    TEXT NOT NULL CHECK (format IN ('clap', 'lv2')),     -- plugin-db's address formats
  uri       TEXT NOT NULL CHECK (length(uri) > 0),
  UNIQUE (sha256, format, uri)
) STRICT;

CREATE TABLE record_set (                  -- one provenance.json; base layer only
  set_id          INTEGER PRIMARY KEY,
  host_class      TEXT NOT NULL CHECK (WORD(host_class)),
  name            TEXT NOT NULL CHECK (WORD(name)),
  schema          TEXT NOT NULL,
  tier            TEXT NOT NULL CHECK (WORD(tier)),
  host_profile    TEXT NOT NULL CHECK (WORD(host_profile)),
  measured        TEXT NOT NULL,
  date            TEXT NOT NULL,
  package_name    TEXT NOT NULL,           -- the records package the set was published as
  package_version TEXT NOT NULL,
  UNIQUE (host_class, name)
) STRICT;

CREATE TABLE set_package (                 -- provenance.packages and provenance.passes
  set_id  INTEGER NOT NULL REFERENCES record_set ON DELETE CASCADE,
  kind    TEXT NOT NULL CHECK (kind IN ('packages', 'passes')),
  name    TEXT NOT NULL,
  version TEXT NOT NULL,
  PRIMARY KEY (set_id, kind, name)
) STRICT;

CREATE TABLE set_setting (                 -- provenance.settings, its note left out
  set_id INTEGER NOT NULL REFERENCES record_set ON DELETE CASCADE,
  key    TEXT NOT NULL CHECK (WORD(key)),
  value  TEXT NOT NULL,
  PRIMARY KEY (set_id, key)
) STRICT;

CREATE TABLE record (
  record_id   INTEGER PRIMARY KEY,
  plugin_id   INTEGER NOT NULL REFERENCES plugin,
  set_id      INTEGER REFERENCES record_set ON DELETE CASCADE,  -- NULL in the user layer
  host_class  TEXT NOT NULL CHECK (WORD(host_class)),
  offer       TEXT NOT NULL CHECK (WORD(offer)),
  name        TEXT NOT NULL,               -- the file name without .<offer>.qualification.json
  schema      TEXT NOT NULL,
  -- the package the binary came from: NULL when not known, never guessed
  pkg_format  TEXT CHECK (pkg_format IS NULL OR pkg_format IN ('deb', 'rpm')),
  pkg_name    TEXT,
  pkg_version TEXT,
  pkg_release TEXT,
  pkg_distro  TEXT CHECK (pkg_distro IS NULL OR WORD(pkg_distro)),   -- e.g. trixie, fc45
  pkg_arch    TEXT CHECK (pkg_arch IS NULL OR WORD(pkg_arch)),       -- the package's own arch word: arm64, x86_64, all, noarch
  -- binary
  binary_path    TEXT NOT NULL,
  layout_scheme  TEXT,
  layout_sha256  TEXT,
  unpinnable     INTEGER CHECK (unpinnable IN (0, 1)),               -- 1 when binary.unpinnable is present
  tested_version TEXT,
  measured_at    TEXT NOT NULL,
  run_id         TEXT NOT NULL,
  tool_runner    TEXT NOT NULL,
  tool_child     TEXT NOT NULL,
  tool_interposer TEXT,
  -- probe: the probe output the record judged, by name, hash and size
  probe_file      TEXT NOT NULL,
  probe_sha256    TEXT NOT NULL CHECK (length(probe_sha256) = 64 AND probe_sha256 NOT GLOB '*[^0-9a-f]*'),
  probe_bytes     INTEGER NOT NULL,
  probe_protocol  TEXT NOT NULL,
  probe_protocol_version INTEGER NOT NULL,
  probe_reason    TEXT NOT NULL CHECK (WORD(probe_reason)),
  probe_outcome   TEXT NOT NULL CHECK (WORD(probe_outcome)),
  probe_complete  INTEGER NOT NULL CHECK (probe_complete IN (0, 1)),
  probe_meets_protocol INTEGER NOT NULL CHECK (probe_meets_protocol IN (0, 1)),
  probe_loadavg1  REAL NOT NULL,
  probe_cores     INTEGER NOT NULL,
  mc_arch         TEXT NOT NULL CHECK (WORD(mc_arch)),               -- the measuring machine's, not the package's
  mc_family       TEXT NOT NULL CHECK (WORD(mc_family)),
  mc_core_band    TEXT NOT NULL CHECK (WORD(mc_core_band)),
  mc_clock_band   TEXT NOT NULL CHECK (WORD(mc_clock_band)),
  mc_preempt_rt   INTEGER NOT NULL CHECK (mc_preempt_rt IN (0, 1)),
  mc_cstates_limited INTEGER NOT NULL CHECK (mc_cstates_limited IN (0, 1)),
  -- behaviour
  lifecycle_cycles INTEGER, lifecycle_failed INTEGER, lifecycle_instantiated INTEGER,
  threads_before INTEGER, threads_after_first_instantiate INTEGER, threads_after_all_freed INTEGER,
  -- adapter pass
  adapter_admitted INTEGER CHECK (adapter_admitted IN (0, 1)),
  adapter_host     TEXT CHECK (adapter_host IS NULL OR WORD(adapter_host)),
  adapter_measured INTEGER CHECK (adapter_measured IN (0, 1)),
  adapter_code     TEXT CHECK (adapter_code IS NULL OR WORD(adapter_code)),
  adapter_measured_at TEXT,
  -- memory pass
  memory_run_measured_at TEXT, memory_run_id TEXT, memory_run_runner TEXT, memory_run_child TEXT,
  -- rejudgement
  rejudged_at TEXT, rejudged_by TEXT,
  rejudged_measured_at TEXT, rejudged_run_id TEXT,
  rejudged_runner TEXT, rejudged_child TEXT, rejudged_interposer TEXT,
  rejudged_adapter_measured_at TEXT,
  rejudged_memory_measured_at TEXT, rejudged_memory_runner TEXT, rejudged_memory_child TEXT,
  CHECK ((layout_scheme IS NULL) = (layout_sha256 IS NULL))
) STRICT;
CREATE INDEX record_plugin  ON record (plugin_id, offer, host_class);
CREATE INDEX record_package ON record (pkg_format, pkg_name, pkg_version, pkg_release, pkg_distro, pkg_arch);

CREATE TABLE record_file (                 -- binary.files[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord       INTEGER NOT NULL,
  path      TEXT NOT NULL,
  sha256    TEXT NOT NULL CHECK (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE record_version (              -- adapter.versions, rejudged.figures.adapter.versions
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  scope     TEXT NOT NULL CHECK (scope IN ('adapter', 'rejudged-adapter')),
  name      TEXT NOT NULL,
  version   TEXT NOT NULL,
  PRIMARY KEY (record_id, scope, name)
) STRICT;

CREATE TABLE verdict (                     -- verdicts[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord       INTEGER NOT NULL,
  host      TEXT NOT NULL CHECK (WORD(host)),
  measured  INTEGER NOT NULL CHECK (measured IN (0, 1)),
  rating    TEXT NOT NULL CHECK (WORD(rating)),
  qualified INTEGER NOT NULL CHECK (qualified IN (0, 1)),
  hosting   TEXT NOT NULL CHECK (WORD(hosting)),
  arm       TEXT NOT NULL CHECK (WORD(arm)),
  deciding  TEXT CHECK (deciding IS NULL OR WORD(deciding)),
  PRIMARY KEY (record_id, ord),
  UNIQUE (record_id, host)
) STRICT;

CREATE TABLE cost_entry (                  -- cost[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord       INTEGER NOT NULL,
  host      TEXT NOT NULL CHECK (WORD(host)),
  rate      INTEGER NOT NULL,
  quantum   INTEGER NOT NULL,
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE reason (                      -- verdicts[].reasons[] and cost[].reasons[]
  reason_id INTEGER PRIMARY KEY,
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  owner     TEXT NOT NULL CHECK (owner IN ('verdict', 'cost')),
  owner_ord INTEGER NOT NULL,              -- verdict.ord or cost_entry.ord
  ord       INTEGER NOT NULL,
  dimension TEXT NOT NULL CHECK (WORD(dimension)),
  rating    TEXT NOT NULL CHECK (WORD(rating)),
  code      TEXT NOT NULL CHECK (WORD(code)),
  UNIQUE (record_id, owner, owner_ord, ord)
) STRICT;

CREATE TABLE reason_param (                -- reasons[].params
  reason_id INTEGER NOT NULL REFERENCES reason ON DELETE CASCADE,
  name      TEXT NOT NULL CHECK (WORD(name)),
  number    INTEGER,
  word      TEXT CHECK (word IS NULL OR WORD(word)),
  CHECK ((number IS NULL) <> (word IS NULL)),
  PRIMARY KEY (reason_id, name)
) STRICT;

CREATE TABLE tier (                        -- tiers.inProcess, tiers.isolated
  record_id  INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  tier       TEXT NOT NULL CHECK (tier IN ('inProcess', 'isolated')),
  host       TEXT NOT NULL CHECK (WORD(host)),
  measured   INTEGER NOT NULL CHECK (measured IN (0, 1)),
  qualified  INTEGER NOT NULL CHECK (qualified IN (0, 1)),
  rating     TEXT NOT NULL CHECK (WORD(rating)),
  deciding   TEXT CHECK (deciding IS NULL OR WORD(deciding)),
  runs_alone INTEGER CHECK (runs_alone IN (0, 1)),
  PRIMARY KEY (record_id, tier)
) STRICT;

CREATE TABLE tier_offered (                -- tiers.offeredOn[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord       INTEGER NOT NULL,
  tier      TEXT NOT NULL CHECK (WORD(tier)),
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE cell (                        -- measurements.grid[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord       INTEGER NOT NULL,
  rate      INTEGER NOT NULL,
  quantum   INTEGER NOT NULL,
  outcome   TEXT NOT NULL CHECK (WORD(outcome)),
  latency_declared_frames INTEGER, latency_measured_frames INTEGER,
  latency_code TEXT CHECK (latency_code IS NULL OR WORD(latency_code)),
  latency_unmeasured_reason TEXT CHECK (latency_unmeasured_reason IS NULL OR WORD(latency_unmeasured_reason)),
  cost_median REAL, cost_percentile_p INTEGER, cost_percentile_value REAL,
  cost_blocks INTEGER, cost_warmup_blocks INTEGER,
  voices_basis TEXT CHECK (voices_basis IS NULL OR WORD(voices_basis)),
  voices_capacity INTEGER, voices_held INTEGER,
  mem_after_instantiate_kb INTEGER, mem_after_activate_kb INTEGER, mem_at_rest_kb INTEGER,
  mem_second_instance_kb INTEGER, mem_first_instance_kb INTEGER, mem_per_instance_kb INTEGER,
  mem_notes_held_kb INTEGER,
  mem_basis TEXT CHECK (mem_basis IS NULL OR WORD(mem_basis)),
  mem_unmeasured_reason TEXT CHECK (mem_unmeasured_reason IS NULL OR WORD(mem_unmeasured_reason)),
  mem_limit_bytes INTEGER,
  mem_limit_mechanism TEXT CHECK (mem_limit_mechanism IS NULL OR WORD(mem_limit_mechanism)),
  rt_interposer INTEGER CHECK (rt_interposer IN (0, 1)), rt_swept INTEGER CHECK (rt_swept IN (0, 1)),
  rt_sweep_applicable INTEGER CHECK (rt_sweep_applicable IN (0, 1)),
  rt_blocks INTEGER, rt_allocations INTEGER, rt_locks INTEGER, rt_syscalls INTEGER,
  rt_thread_violations INTEGER, rt_process_errors INTEGER,
  note_sweep_applicable INTEGER CHECK (note_sweep_applicable IN (0, 1)),
  note_sweep_dialect TEXT CHECK (note_sweep_dialect IS NULL OR WORD(note_sweep_dialect)),
  note_sweep_allocations INTEGER, note_sweep_locks INTEGER, note_sweep_syscalls INTEGER,
  PRIMARY KEY (record_id, ord),
  UNIQUE (record_id, rate, quantum)
) STRICT;

CREATE TABLE cell_event (                  -- measurements.grid[].rtSafety.events[]
  record_id INTEGER NOT NULL,
  cell_ord  INTEGER NOT NULL,
  ord       INTEGER NOT NULL,
  event     TEXT NOT NULL,                 -- a symbol name as the interposer wrote it
  PRIMARY KEY (record_id, cell_ord, ord),
  FOREIGN KEY (record_id, cell_ord) REFERENCES cell (record_id, ord) ON DELETE CASCADE
) STRICT;

CREATE TABLE claim (                       -- the cells a layer answers for: one record per key, offer, class and cell
  record_id  INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  plugin_id  INTEGER NOT NULL REFERENCES plugin,
  offer      TEXT NOT NULL,
  host_class TEXT NOT NULL,
  rate       INTEGER NOT NULL,
  quantum    INTEGER NOT NULL,
  PRIMARY KEY (plugin_id, offer, host_class, rate, quantum)
) STRICT;

CREATE TABLE feature_required (            -- measurements.behaviour.features.required[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL, feature TEXT NOT NULL,
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE unmeasured (                  -- measurements.unmeasured[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  dimension TEXT NOT NULL CHECK (WORD(dimension)),
  code TEXT NOT NULL CHECK (WORD(code)),
  rate INTEGER NOT NULL, quantum INTEGER NOT NULL,
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE not_measured (                -- notMeasured[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  dimension TEXT NOT NULL CHECK (WORD(dimension)),
  code TEXT NOT NULL CHECK (WORD(code)),
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE run_step (                    -- run.steps[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  step TEXT NOT NULL CHECK (WORD(step)),
  result TEXT NOT NULL CHECK (WORD(result)),
  code TEXT CHECK (code IS NULL OR WORD(code)),
  cpu_percent REAL, latency_frames INTEGER, midi_inputs_linked INTEGER, xruns INTEGER,
  pool_allocations_on INTEGER, pool_locks_on INTEGER, pool_syscalls_on INTEGER, pool_tasks_on_helpers INTEGER,
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE probe_end (                   -- probe.ends[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  step TEXT NOT NULL CHECK (WORD(step)),
  outcome TEXT NOT NULL CHECK (WORD(outcome)),
  exit_status INTEGER,
  signal TEXT CHECK (signal IS NULL OR WORD(signal)),
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE adapter_cell (                -- adapter.cells[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  rate INTEGER NOT NULL, quantum INTEGER NOT NULL,
  admitted INTEGER NOT NULL CHECK (admitted IN (0, 1)),
  measured INTEGER NOT NULL CHECK (measured IN (0, 1)),
  code TEXT CHECK (code IS NULL OR WORD(code)),
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE memory_run_cell (             -- memoryRun.cells[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  rate INTEGER NOT NULL, quantum INTEGER NOT NULL,
  outcome TEXT NOT NULL CHECK (WORD(outcome)),
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE rejudged_owe (                -- rejudged.owes[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  code TEXT NOT NULL CHECK (WORD(code)),
  measurement TEXT NOT NULL CHECK (WORD(measurement)),
  PRIMARY KEY (record_id, ord)
) STRICT;
```

`ord` is the element's place in its JSON array, from 0, so an array reads back in its order.

A present empty array or map is told from an absent one by one rule, which every current record follows:

- ALWAYS PRESENT with its parent, empty when it has no rows: `binary.files`, `verdicts`, `verdicts[].reasons`,
  `cost`, `cost[].reasons`, `reasons[].params` (empty in 516 reasons today), `tiers.offeredOn` (empty in 4,856
  records), `measurements.grid`, `measurements.grid[].rtSafety.events` (present with `rtSafety`, empty in 9,015
  cells), `measurements.behaviour.features.required` (present with `behaviour`, empty in 3,077 records),
  `notMeasured`, `run.steps`, `memoryRun.cells`;
- PRESENT ONLY WITH ROWS: `adapter.cells`, `probe.ends`, `measurements.unmeasured`, `rejudged.owes`.

The writer refuses a record that breaks the rule (an absent array of the first list, a present empty array of the
second), naming the file and the path.

The user-layer rule for `set_id` (NULL exactly when `store_info.layer` is `user`) needs a subquery, which a `CHECK`
cannot hold, so the DDL states it as a trigger:

```sql
CREATE TRIGGER record_set_by_layer BEFORE INSERT ON record
WHEN (NEW.set_id IS NULL) <> ((SELECT layer FROM store_info) = 'user')
BEGIN SELECT RAISE(ABORT, 'record.set_id: NULL exactly in the user layer'); END;
```

### 3.4 Domain words and their check

The writer reads the `qualification` domain from the installed contract directory (as docs/runtime-data.md says for
Python: the installed JSON, validated with `jsonschema` against Draft 2020-12, `info.version` at least the floor) and
records its `info.version` in `store_info.domain_version`. Each word column with a domain item has a row in
`word_check`; the writer refuses a word outside its item, naming the record file, the JSON path and the word. Today:

| column(s) | domain item |
| --- | --- |
| `verdict.rating`, `tier.rating`, `reason.rating` | `QUALIFICATION_MEASUREMENT_VERDICT_RATINGS` |
| `cell.latency_unmeasured_reason`, `cell.mem_unmeasured_reason` | `QUALIFICATION_MEASUREMENT_UNMEASURED_REASONS` |
| `cell.voices_basis`, `cell.mem_basis` | `QUALIFICATION_MEASUREMENT_VOICE_BASES` |

Every other word column holds words no domain item holds today: the dimensions `memory` and `hostAdmission` (the
domain's `QUALIFICATION_MEASUREMENT_DIMENSIONS` holds `latency`, `cost`, `stability`, `rtSafety`, `features`), host
classes (`rpi5`, `x86-64`; the domain's `QUALIFICATION_MACHINE_CLASSES` holds `desk`, `raspberry-pi-4`,
`raspberry-pi-5`), host profiles, offers, hosting and arm words, tiers, run steps and their results, `hosting.*`
codes and `probe.*` outcomes. Open question 2 decides where those words live; the word columns of section 3.3 carry
`WORD()` until then.

### 3.5 Old field to column

Every leaf of `plugin-qualify.qualification-record/1` as today's records hold it. `[]` is an array element (one row,
`ord` its place). A path not in this table and not in the sentence list below is refused by the writer
(`field-unmapped`, naming the file and the path).

| old field | column |
| --- | --- |
| directory `records/<class>/<set>/` | `record.host_class`; `record.set_id` → `record_set` |
| file name `<name>.<offer>.qualification.json` | `record.name`, `record.offer` |
| `schema` | `record.schema` |
| `plugin.format`, `plugin.id`, `binary.sha256` | `plugin.format`, `plugin.uri`, `plugin.sha256` (the key) |
| (none) | `record.pkg_format`, `pkg_name`, `pkg_version`, `pkg_release`, `pkg_distro`, `pkg_arch`: NULL (below) |
| `binary.path` | `record.binary_path` |
| `binary.files[].path`, `.sha256` | `record_file.path`, `record_file.sha256` |
| `binary.layout.scheme`, `.sha256` | `record.layout_scheme`, `record.layout_sha256` |
| `binary.unpinnable` | `record.unpinnable` = 1 (its sentence: see below) |
| `testedVersion` | `record.tested_version` |
| `measuredAt` | `record.measured_at` |
| `run.id` | `record.run_id` |
| `run.steps[].step`, `.result`, `.code` | `run_step.step`, `.result`, `.code` |
| `run.steps[].figures.cpuPercent`, `.latencyFrames`, `.midiInputsLinked`, `.xruns` | `run_step.cpu_percent`, `.latency_frames`, `.midi_inputs_linked`, `.xruns` |
| `run.steps[].pool.allocationsOn`, `.locksOn`, `.syscallsOn`, `.tasksOnHelpers` | `run_step.pool_allocations_on`, `.pool_locks_on`, `.pool_syscalls_on`, `.pool_tasks_on_helpers` |
| `tool.runner`, `.child`, `.interposer` | `record.tool_runner`, `.tool_child`, `.tool_interposer` |
| `probe.file`, `.sha256`, `.bytes` | `record.probe_file`, `.probe_sha256`, `.probe_bytes` |
| `probe.protocol.name`, `.version` | `record.probe_protocol`, `.probe_protocol_version` |
| `probe.reason`, `.outcome`, `.complete`, `.meetsProtocol` | `record.probe_reason`, `.probe_outcome`, `.probe_complete`, `.probe_meets_protocol` |
| `probe.load.loadavg1`, `.cores` | `record.probe_loadavg1`, `.probe_cores` |
| `probe.machineClass.arch`, `.family`, `.coreBand`, `.clockBand`, `.preemptRt`, `.cstatesLimited` | `record.mc_arch`, `.mc_family`, `.mc_core_band`, `.mc_clock_band`, `.mc_preempt_rt`, `.mc_cstates_limited` |
| `probe.ends[].step`, `.outcome`, `.exitStatus`, `.signal` | `probe_end.step`, `.outcome`, `.exit_status`, `.signal` |
| `verdicts[].host`, `.measured`, `.rating`, `.qualified`, `.hosting`, `.arm`, `.deciding` | `verdict.*` of the same names |
| `verdicts[].reasons[].dimension`, `.rating`, `.code` | `reason.*` with `owner` = `verdict` |
| `verdicts[].reasons[].params.<name>` | `reason_param.name`, `.number` or `.word` |
| `cost[].host`, `.rate`, `.quantum` | `cost_entry.*` |
| `cost[].reasons[]` and their `params` | `reason`, `reason_param` with `owner` = `cost` |
| `tiers.inProcess.*`, `tiers.isolated.*` (`host`, `measured`, `qualified`, `rating`, `deciding`, `runsAlone`) | `tier` row with `tier` = `inProcess` or `isolated` |
| `tiers.offeredOn[]` | `tier_offered.tier` |
| `measurements.grid[].rate`, `.quantum`, `.outcome` | `cell.rate`, `.quantum`, `.outcome`; and one `claim` row |
| `measurements.grid[].latency.declaredFrames`, `.measuredFrames`, `.code`, `.unmeasuredReason` | `cell.latency_declared_frames`, `.latency_measured_frames`, `.latency_code`, `.latency_unmeasured_reason` |
| `measurements.grid[].cost.median`, `.percentile.p`, `.percentile.value`, `.blocks`, `.warmupBlocks` | `cell.cost_median`, `.cost_percentile_p`, `.cost_percentile_value`, `.cost_blocks`, `.cost_warmup_blocks` |
| `measurements.grid[].cost.voices.basis`, `.capacity`, `.held` | `cell.voices_basis`, `.voices_capacity`, `.voices_held` |
| `measurements.grid[].memory.afterInstantiateKb`, `.afterActivateKb`, `.atRestKb`, `.secondInstanceKb`, `.firstInstanceKb`, `.perInstanceKb`, `.notesHeldKb`, `.basis`, `.unmeasuredReason` | `cell.mem_after_instantiate_kb`, `.mem_after_activate_kb`, `.mem_at_rest_kb`, `.mem_second_instance_kb`, `.mem_first_instance_kb`, `.mem_per_instance_kb`, `.mem_notes_held_kb`, `.mem_basis`, `.mem_unmeasured_reason` |
| `measurements.grid[].memoryLimit.bytes`, `.mechanism` | `cell.mem_limit_bytes`, `.mem_limit_mechanism` |
| `measurements.grid[].rtSafety.interposer`, `.swept`, `.sweepApplicable`, `.blocks`, `.allocations`, `.locks`, `.syscalls`, `.threadViolations`, `.processErrors` | `cell.rt_*` of the same names |
| `measurements.grid[].rtSafety.events[]` | `cell_event.event` |
| `measurements.grid[].noteSweep.applicable`, `.dialect`, `.allocations`, `.locks`, `.syscalls` | `cell.note_sweep_*` |
| `measurements.unmeasured[].dimension`, `.code`, `.rate`, `.quantum` | `unmeasured.*` |
| `measurements.behaviour.lifecycle.cycles`, `.failed`, `.instantiated` | `record.lifecycle_*` |
| `measurements.behaviour.threads.before`, `.afterFirstInstantiate`, `.afterAllFreed` | `record.threads_*` |
| `measurements.behaviour.features.required[]` | `feature_required.feature` |
| `notMeasured[].dimension`, `.code` | `not_measured.*` |
| `adapter.admitted`, `.host`, `.measured`, `.code`, `.measuredAt` | `record.adapter_*` |
| `adapter.versions.<name>` | `record_version` with `scope` = `adapter` |
| `adapter.cells[].rate`, `.quantum`, `.admitted`, `.measured`, `.code` | `adapter_cell.*` |
| `memoryRun.measuredAt`, `.runId`, `.tool.runner`, `.tool.child` | `record.memory_run_measured_at`, `.memory_run_id`, `.memory_run_runner`, `.memory_run_child` |
| `memoryRun.cells[].rate`, `.quantum`, `.outcome` | `memory_run_cell.*` |
| `rejudged.at`, `.by` | `record.rejudged_at`, `.rejudged_by` |
| `rejudged.figures.measuredAt`, `.runId`, `.tool.runner`, `.tool.child`, `.tool.interposer` | `record.rejudged_measured_at`, `.rejudged_run_id`, `.rejudged_runner`, `.rejudged_child`, `.rejudged_interposer` |
| `rejudged.figures.adapter.measuredAt`, `.adapter.versions.<name>` | `record.rejudged_adapter_measured_at`; `record_version` with `scope` = `rejudged-adapter` |
| `rejudged.figures.memory.measuredAt`, `.tool.runner`, `.tool.child` | `record.rejudged_memory_measured_at`, `.rejudged_memory_runner`, `.rejudged_memory_child` |
| `rejudged.owes[].code`, `.measurement` | `rejudged_owe.*` |

`provenance.json` of a set: `schema`, `set`, `hostClass`, `hostProfile`, `tier`, `measured`, `date`, `package.name`,
`package.version` → `record_set`; `packages.<name>` and `passes.<name>` → `set_package`; `settings.<key>` (but `note`)
→ `set_setting`.

**The package fields, field by field.** No current record or provenance holds the package of a binary, so the
migration writes NULL in all six for every one of the 12,953 records:

| column | where today's records hold it | migrated value |
| --- | --- | --- |
| `pkg_format` | nowhere: no record names how its binary was installed | NULL |
| `pkg_name` | nowhere per binary; `provenance.packages` lists what was installed on the measuring machine, with no file of any package, so matching a `binary_path` to one would be a guess | NULL |
| `pkg_version` | nowhere per binary (the same list) | NULL |
| `pkg_release` | nowhere per binary (the same list) | NULL |
| `pkg_distro` | only inside the prose `provenance.image` | NULL |
| `pkg_arch` | nowhere: `probe.machineClass.arch` (`aarch64`, `x86_64`) is the measuring machine's, kept in `mc_arch`, not the package's arch word | NULL |

**Sentences, not stored.** Each is prose for a person; the code or the presence beside it is stored:

- `run.steps[].detail` (the step's `code` and `result` are stored);
- `measurements.grid[].memory.unmeasuredDetail` (`mem_unmeasured_reason` is stored);
- `measurements.unmeasured[].detail` (`code` and `dimension` are stored);
- `binary.unpinnable` (its presence is stored as `record.unpinnable` = 1);
- `tiers.dimmed` (a joined string `<host>: <deciding>; ...`, each part of which is in `tier` and `verdict`);
- of each `provenance.json`: `image`, `board`, `kernel`, `realtime`, `jack`, `grid`, `tierNote`, `settings.note`,
  `sources`, `repositories`.

The probe outputs (`*.probe.json`) are not stored either: they are plugin-hostd's documents, and they hold prose
(`run.memoryLock.reason`, step details). The record keeps the probe's file name, SHA-256 and size. Open question 1
asks the owner to confirm both lists.

### 3.6 `user_version`

`PRAGMA user_version = 1` for this schema, set by the writer as the last statement of a build. The rule:

- The reader is built for one range, `PQDB_SCHEMA_MIN` to `PQDB_SCHEMA_MAX` (both 1 now). It refuses a database above
  the range (`schema-too-new`) and below it (`schema-too-old`); 0 is a file that is no store (`not-a-store`).
- The base database is never upgraded: each build writes it new, at the writer's version. A package whose base is at a
  new version depends on the reader at the floor that reads it.
- The user layer is not upgraded in place in this pass: there is one version. A later version states its own rule,
  with the owner (section 10).

## 4. Merge semantics

- **Per whole record.** A reader's result is one record at one cell. Its key is (`sha256`, `format`, `uri`, `offer`,
  `host_class`, `rate`, `quantum`): the `claim` key. When the user layer has a claim on that key, the result is the
  user record, every field of it; the base record for that key is not consulted. When the user layer has none, the
  result is the base record. Why whole: a record's verdicts, figures and probe come from one run. A field taken from the
  base beside fields from the user's run would be a combination nobody measured; a NULL in a user record (a figure not
  measured) means "not measured here", never "take the base's".
- **User first, base never overwritten.** The base file is read only and immutable. The user layer is a separate file;
  nothing is ever written to the base by a reader or by the user writer.
- **No tombstone.** A user cannot hide a base result except by measuring the same key at the same cell, which shadows
  it. Removing a user record brings the base result back. Hiding without measuring would need a new word and a new
  rule; nothing asks for it today.
- **Conflicts.** Within one layer, the `claim` primary key allows one record per key, offer, class and cell. In the
  base, the migration refuses a second claim, naming both files (no current set has one). In the user layer, the writer
  replaces the user's own earlier record for that claim in one transaction (a newer measurement of the same bytes).
  Across layers there is no conflict: the user's record wins and each result says its `layer`.
- A different SHA-256 is a different plugin: a user record for other bytes never shadows a base record.

## 5. Migration (change 2)

- **Input.** `records/<class>/<set>/*.qualification.json` and `records/<class>/<set>/provenance.json`, as section 3.5
  maps them, for the classes of one architecture (`packaging/arch-classes`, the same selection as
  `tools/sets.py install`). The probe outputs are read only to check that each record's `probe.sha256` and
  `probe.bytes` match its file; a mismatch is refused by name.
- **Tool and place.** Python 3, standard library `sqlite3` and `json`, plus `jsonschema` for the domain document:
  `tools/qualification_db.py` (the record-to-rows writer and the rows-to-record exporter, one module) and
  `tools/records-db.py` (its command). The module is the one writer: the user layer's writer, after the switch, is the
  same module. It writes to a temporary file in the output directory and renames it over `--out` only when every
  record is in and `user_version` is set; a refusal leaves no file.
- **Re-runnable, and identical.** The tool never updates a database: each run builds a new file. Records are inserted in
  byte order of their paths, rows in JSON order, ids assigned from 1 in that order, `journal_mode` `DELETE`,
  `page_size` 4096, and a `VACUUM` before `user_version` is set. The same input gives a ROW-IDENTICAL database
  everywhere (the sorted `iterdump()` text is equal), and a BYTE-IDENTICAL file with the same SQLite library version.
  The test checks both in one environment.
- **The round-trip proof** (`tools/test_records_db.py`, `unittest` like the repository's other tools):
  - build the base database of every set of `records/` (both classes, not one architecture);
  - for every record file, export the record from the database and compare it with the parsed file as JSON values,
    every field, after removing the sentence paths of section 3.5 from the file's value; numbers compare by value
    (a REAL 40.0 equals 40);
  - the package fields of every migrated record read back as NULL, and every optional field absent in a file reads
    back absent;
  - counts are equal: record files per set = `record` rows per set, and for every array of section 3.5 the number of
    elements across the files = the rows of its table; sets = `record_set` rows; distinct (format, SHA-256, id) =
    `plugin` rows (2,278 today).
- **The old package and files.** Nothing is removed in this pass. `plugin-qualification-records` keeps installing
  every `<class>/<set>/` file byte for byte, and adds `qualification.sqlite` beside them. The package's name, its
  Provides, Replaces and Breaks, and its dependencies stay as they are.

## 6. Reader API (change 3)

**Language: C**, with a command over it. The consumers that read records today are:

- plugin-hostd (C): `src/qualcost.c` reads the cost, latency and memory figures of `qualification_dir`'s records for
  its planner and its estimate verb. It is a daemon; it must not start a process to read a figure.
- plugin-qualify-sync (TypeScript, Node.js): `src/distributed-records.ts` reads the shipped records of its class and
  cell. It already runs plugin-db's command for plugin-db's store (`src/plugin-db-cli.ts`). It reads the
  database the same way, through `plugin-qualification-db query --json`, in one call per run: Node.js 18, the
  package's floor, and Debian trixie's Node.js have no built-in SQLite (open question 4).
- The console does not read records; it reads what plugin-hostd and plugin-db answer.

One implementation, in C, so the two consumers cannot answer differently.

**Header** `<plugin-qualification-db/pqdb.h>`, library `libplugin-qualification-db.so.0`, pkg-config
`plugin-qualification-db`:

```c
typedef struct pqdb pqdb;                          /* an opened base and user layer; opaque */
typedef enum { PQDB_SCOPE_USER, PQDB_SCOPE_SYSTEM } pqdb_scope;

typedef struct { const char *code; char message[256]; } pqdb_error;  /* names the code, the file and the reason */

/* 0, or a PQDB_ERR_* value. Production: the installed base and the scope's user layer; no path, no environment. */
int  pqdb_open(pqdb_scope scope, pqdb **out, pqdb_error *err);
/* TEST AND COMMAND ONLY: the base, the user layer (NULL: none) and the contract directory, given. */
int  pqdb_open_at(const char *base, const char *user, const char *contract_dir, pqdb **out, pqdb_error *err);
void pqdb_close(pqdb *db);
const char *pqdb_code(int status);                 /* "qualification-db.absent" ... */

typedef struct {                                    /* every field optional: NULL or -1 is "any" */
    const char *sha256, *format, *uri, *offer, *host_class;
    int rate, quantum;
    const char *pkg_format, *pkg_name, *pkg_version, *pkg_release, *pkg_distro, *pkg_arch;
} pqdb_query;

typedef struct {
    const char *layer;                              /* "user" or "base" */
    const char *sha256, *format, *uri, *offer, *host_class, *set;   /* set: NULL in the user layer */
    const char *pkg_format, *pkg_name, *pkg_version, *pkg_release, *pkg_distro, *pkg_arch;  /* NULL: not known */
    int rate, quantum;
    const char *outcome;                            /* the cell's outcome word */
    double cost_median_ns, cost_p_ns;  int cost_p; int has_cost;
    long latency_frames; int has_latency;           /* measured frames, else declared */
    long mem_first_kb, mem_per_instance_kb; int has_memory;
} pqdb_result;

/* Calls each(result, ctx) for every result the query matches, user first, a base result only when the user layer has
   no claim on its key (section 4), in key order. A non-zero return of each stops the walk and is returned. */
int  pqdb_each(const pqdb *db, const pqdb_query *q, int (*each)(const pqdb_result *, void *), void *ctx);

/* The verdict of a result's record under one host profile: rating word, measured, qualified, deciding (NULL: none). */
typedef struct { const char *rating, *deciding; int measured, qualified; } pqdb_verdict;
int  pqdb_verdict_of(const pqdb *db, const pqdb_result *r, const char *host, pqdb_verdict *out);
```

- **From an installed package to its results:** `pqdb_each` with the `pkg_*` fields of the query set (format, name,
  version, release, distro, arch, as the package manager states them). Only stored values match: a record whose
  package fields are NULL, every migrated record today, is never returned for a package query.
- **Pointers** in a result are valid until the callback returns; a caller copies what it keeps.
- **Refused, by name** (`pqdb_code` gives the string; each refusal names the file):
  - `qualification-db.absent`: the base file does not exist. An absent USER layer is not an error: it is an empty
    layer;
  - `qualification-db.unreadable`: it exists and SQLite cannot open or read it;
  - `qualification-db.not-a-store`: `user_version` 0, or no `store_info` row, or a `layer` that is not the file's
    (a user file opened as the base);
  - `qualification-db.schema-too-new`, `qualification-db.schema-too-old`: `user_version` outside the reader's range;
  - `qualification-db.domain-too-old`: the installed `qualification` domain's `info.version` is below the
    `store_info.domain_version` the file was checked against;
  - `qualification-db.word-unknown`: a word of a `word_check` column is not in its item of the installed domain; the
    message names the table, the column and the word;
  - `qualification-db.busy`: the user layer stayed locked by its writer past the busy timeout (250 ms);
  - the loader's own codes (`contract.dir.absent`, `contract.file.invalid`, `contract.package.too-old` and the rest),
    passed through when the domain cannot be opened.
- **Word check at open.** `pqdb_open` opens the domain through omx-contract's loader (`omx_domain_open("qualification",
  floor)`), then for each `word_check` row reads the column's distinct words and looks each up
  (`omx_domain_word`). It is done once, at open; no lookup checks a word again.
- **Concurrency.** The base is opened `file:<path>?mode=ro&immutable=1`: no lock, no journal, nothing written. A package
  upgrade renames a new file over it; an open handle keeps reading the old one until it is closed. The user layer is
  opened `mode=ro` with `busy_timeout` 250 ms; it uses the rollback journal (`journal_mode` `DELETE`), not WAL, because a
  WAL reader must be able to write the `-shm` file, and a reader of the system scope's layer does not own it. Its
  writer keeps each transaction to one record. A handle is used by one thread at a time; a program with several
  threads opens one handle each.
- **Never in a real-time path.** Every function allocates, reads files and takes locks. The header says so in its
  `@file` block. plugin-hostd reads a plugin's figures when the plugin is added, outside the audio thread, and copies
  them, as `qualcost` does today.
- **The command** `plugin-qualification-db`:
  - `query [--sha256 ..] [--format ..] [--uri ..] [--offer ..] [--host-class ..] [--rate ..] [--quantum ..]
    [--pkg-format .. --pkg-name .. --pkg-version .. --pkg-release .. --pkg-distro .. --pkg-arch ..] --json`: one JSON
    object per line per result, the fields of `pqdb_result` and every verdict of its record, words and numbers only;
  - `check`: opens both layers and prints `ok`, or the code and message; exit 0, or 1 with the code;
  - `--base`, `--user`, `--contract-dir` and their variables, as section 2 says; exit 2 on a usage error.

## 7. Packaging

| package | ships | built how | new dependencies (floors only) |
| --- | --- | --- | --- |
| `plugin-qualification-records` (change 2) | `/usr/share/omx/qualification/qualification.sqlite` beside today's files | generated at package build by `tools/records-db.py` from `records/`, for the classes of the architecture | Build-Depends: `python3:native` (with its `sqlite3` module), `python3-jsonschema:native`, `libsqlite3-0 (>= 3.37.0)` for `STRICT` tables, `plugin-qualify-contract (>= 0.20.6~)` (the `qualification` domain, `info.version` 1.1.0), `pkg-config` and `libomx-contract-dev` for the contract directory's path; RPM: `python3`, `python3-jsonschema`, `sqlite-libs >= 3.37.0`, `plugin-qualify-contract >= 0.20.6`. Run time: none |
| `libplugin-qualification-db0` (change 3) | the C library | built from `src/` | `libsqlite3-0` and `libomx-domain0` at the floors their symbols files give (`${shlibs:Depends}`), `plugin-qualify-contract (>= 0.20.6~)` |
| `libplugin-qualification-db-dev` (change 3) | header, `.so`, `.pc` | | `libplugin-qualification-db0 (= ${binary:Version})` |
| `plugin-qualification-db` (change 3) | the command | | `${shlibs:Depends}` |

**Generated, not committed.** Today's records are text (JSON, 248 MB unpacked), reviewed as text and never rewritten.
A committed database would be a second copy of them that a diff cannot show and that can drift from `records/`.
Generating it at build from the text keeps one source; the build is cheap (one pass over the files) and its output is
held by the round-trip test. `sets.py check` and `tools/check-records.py` stay the gate on the text.

No version ceiling is added anywhere. The records package's existing plugin-qualify ranges are not touched by this work
(section 10).

## 8. Red-first tests

Each change lands a red commit first (the tests, failing), then the commits that turn it green. Each arm says what
makes it fail.

### Change 2: the migration

1. **Round trip, field for field.** Fails while no tool exists; and after it, when any column of section 3.5 is not
   written or not exported (sabotage: drop `cell.mem_per_instance_kb`; the test names a record and the path).
2. **Counts equal.** Fails when a record is skipped or an array element is lost (sabotage: skip records whose grid
   has three cells; the test names the set and both counts).
3. **NULLs read back as NULL.** Fails when the writer stores `''` or a guessed value for a package field, or for an
   absent `testedVersion` or `tool.interposer` (sabotage: fill `pkg_arch` from `mc_arch`).
4. **Re-run identity.** Two builds give the same sorted `iterdump()` and the same bytes. Fails when the walk is not
   sorted or ids depend on time (sabotage: `os.listdir` order unsorted, or no `VACUUM`).
5. **Domain word refused.** A fixture record with `rating: "excellent"` is refused as `word-unknown`, naming the file,
   the path and the word, and no file is written. Fails when the check is removed.
6. **Unmapped field refused.** A fixture record with an extra field `verdicts[].mood` is refused as `field-unmapped`.
   Fails when the writer ignores unknown fields.
7. **Sentence not stored.** No TEXT value in the database holds a field of the sentence list (search for their exact
   strings from the fixtures). Fails when a detail is written into a column.
8. **Store info.** `user_version` = 1, `store_info.layer` = `base`, `domain_version` = the installed domain's
   `info.version`, `built_from` = the build's commit. Fails when any is missing or the pragma is not set last.
9. **Refusals leave nothing.** An absent contract directory (`contract.dir.absent`), a probe file whose SHA-256 differs
   from the record's, an empty object, and a second claim on one key and cell each refuse by name and leave no output
   file. Fails when a partial file is left at `--out`.
10. **Key constraints.** A record with a 63-character SHA-256 or a format `vst3` is refused by the schema. Fails when
    the `CHECK`s are dropped.
11. **Package contents.** The built `plugin-qualification-records` (deb and rpm) holds `qualification.sqlite` and every
    file of today's sets, byte for byte equal to `records/`. Fails when a file is dropped or rewritten.

### Change 3: the reader

1. **Absent base** → `qualification-db.absent` with the path. Fails when open succeeds on an empty layer.
2. **Absent user layer** → open succeeds; results are the base's. Fails when an absent user file is refused or created.
3. **`user_version` 2** → `schema-too-new`; **0** → `not-a-store`; a user file opened as the base → `not-a-store`.
4. **Word not in the domain.** A fixture domain without `conditional` → `word-unknown` naming `verdict.rating` and
   `conditional`. Fails when the open skips the word check.
5. **Domain too old.** A fixture domain at `info.version` 1.0.0 against a store at 1.1.0 → `domain-too-old`.
6. **Whole-record merge.** A user record without memory figures and a base record with them, same key and cell: the
   result has `layer` `user` and `has_memory` 0. Fails under a per-field merge (sabotage: fill missing user figures
   from the base).
7. **Shadowing is per key and cell.** A user record at another cell, or for another SHA-256, leaves the base result
   visible. Fails when shadowing ignores the cell or the SHA-256.
8. **Package lookup.** A user record with `rpm`, `clap-dexed`, `1.1.0`, `4.fc44`, `fc44`, `x86_64` is found by that
   package; a migrated record (all NULL) is found by no package query. Fails when NULL matches any value.
9. **Read only.** Opening and querying both layers leaves their size, mtime and directory listing unchanged (no
   `-journal`, `-wal` or `-shm` file). Fails when a layer is opened read-write.
10. **No environment in production.** The library's dynamic symbols import no `getenv` or `secure_getenv`, and
    `pqdb_open` with `PLUGIN_QUALIFICATION_DB_BASE` set to a fixture still opens the installed path. Fails when the
    library reads a variable.
11. **Busy.** A writer holding an exclusive lock on the user layer gives `qualification-db.busy` within 250 ms plus a
    margin, never a hang. Fails without a busy timeout.
12. **Figures agree with today's reader.** For every record of a fixture set, `pqdb_each` at each cell gives the cost
    median, the 95th percentile, the latency frames and the memory figures computed from the same JSON by the test's
    own reference (the rules of plugin-hostd's `qualcost.h`). Fails when a column is mapped to the wrong figure.
13. **The command.** `query --json` prints words and numbers only; `--base` and `PLUGIN_QUALIFICATION_DB_BASE` are
    honoured by the command; a usage error exits 2. Fails when the command and the library disagree on a fixture.

## 9. Open questions for the owner

1. **Sentences and probe outputs are not stored.** Section 3.5 lists the prose fields of today's records and
   provenances, and the probe outputs; the database keeps codes, presence, and the probe's name, hash and size, and
   `built_from` points at the text. *Recommendation:* confirm. The round trip then proves every field but those, by
   name, and plugin-qualify gives `binary.unpinnable` a code in its next record format.
2. **Words no domain holds.** Dimensions `memory` and `hostAdmission`, host classes (`rpi5`, `x86-64` against the
   domain's `desk`, `raspberry-pi-4`, `raspberry-pi-5`), host profiles, offers, hosting and arm words, set tiers, run
   steps and results, and the `hosting.*` and `probe.*` codes other repositories own. *Recommendation:* plugin-qualify
   adds the record's items to the `qualification` domain in one minor (with `x-from` for the words omx-clap-core and
   plugin-hostd own) before change 2 merges, so every word column has a `word_check` row and change 2's floor is that
   domain version.
3. **The package fields are NULL for every current record.** *Recommendation:* plugin-qualify's record gains a
   `package` object (format, name, version, release, distro, arch), filled at measurement time from the package
   manager's owner of `binary.path` (`dpkg-query -S`, `rpm -qf`), NULL when no package owns it; the next measured
   sets fill the base. No back-fill from a provenance's package list, which would be a guess.
4. **How plugin-qualify-sync reads.** *Recommendation:* through `plugin-qualification-db query --json`, one call per
   run, as it reads plugin-db; not Node's built-in `node:sqlite` (absent from Node.js 18, the package's floor, and
   from Debian trixie's Node.js), and not a native npm binding.
5. **The system scope's user layer and the device's existing records.** *Recommendation:* the system sync's user layer
   is `/var/lib/omx/qualification/qualification.sqlite`, beside its `qualification_dir`. The records a device already
   holds in its `qualification_dir` are not migrated by this work; the consumer switch decides whether the device
   re-measures them or runs the same writer over that directory.

## 10. Out of scope

- The consumer switch: plugin-qualify-sync, plugin-hostd and any other reader move to the database in one change right
  after the console's 0.2.1 release. Until then no consumer opens it.
- Any compatibility mechanism: no dual read of the old files and the database, no fallback from one to the other, no
  alias, no shim, no second format. If the switch seems to need one, it stops and asks the owner.
- Removing the old files or the old package names: nothing is removed in this pass.
- An upgrade path for a user layer at another `user_version`.
- The records package's existing plugin-qualify version ranges.
- plugin-db's store and its judged and reference layers.
