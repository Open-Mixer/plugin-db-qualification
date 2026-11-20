<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com> -->
# Qualification records in SQLite: one base database, one user layer

Status: SPEC. Nothing here is built. Three changes follow it, in this repository:

1. this spec;
2. the migration: `schema/qualification.sql`, the writer module and the tool that builds the base database from
   `records/`, the round-trip test, and the package carrying the database beside today's files. It merges only after
   its preconditions (section 3.4): the owners publish the words it checks;
3. the reader: a C library and its command, `plugin-qualification-db`, with red-first tests.

The consumers switch to the database in one change in the same release pass as changes 2 and 3, before the console's
0.2.1 release (section 9, ruling 8); that change is made in the consumers' repositories. What this spec fixes of it is
what the store must carry and answer for `plugin-qualify-sync`, which the store REPLACES the distributed JSON layer
for (section 9, ruling 9): the binary identity and the pin (section 3.7), the sync's writing and its readers
(section 6.1), and the reader's widening (section 6). The sync's own code is not specified here.

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
- plugin-qualify PRODUCES the records and owns their format `plugin-qualify.qualification-record/1`
  (`src/qualification-record.ts`); the `qualification` domain of their words is plugin-hostd's
  (`contract.d/qualification/qualification.json`, `info.x-owner: plugin-hostd`), shipped in `plugin-hostd-contract`. It holds no record data of its own beyond test
  fixtures.

The spec is this repository's first design spec; each is named by its date and topic.

### Ownership of the words (producer, changer, owner domain)

| what | producer | who changes it | owner domain |
| --- | --- | --- | --- |
| record fields and their meaning | plugin-qualify (it writes each record) | plugin-qualify, in its record format | plugin-qualify |
| words a record holds (ratings, reasons, dimensions, bases) | plugin-qualify | plugin-qualify, in a minor of the `qualification` domain | `qualification` (plugin-qualify) |
| hosting codes in reasons (`hosting.*`) | omx-clap-core's hosting tables, copied by plugin-qualify | omx-clap-core | omx-clap-core's installed `data/hosting*.json` this pass, its `hosting` domain after it (precondition 5 and its exception) |
| probe outcomes, steps, reasons and signals (`probe.*`) | plugin-hostd's probe | plugin-hostd | the `probe` domain (plugin-hostd), read directly (precondition 4) |
| the outcome of plugin-qualify's own memory bound (`probe.oom`) | plugin-qualify | plugin-qualify | `qualification` (plugin-qualify) |
| adapter codes (`<host>.<kind>[-<parameter>]`) | plugin-qualify (it composes them) | plugin-qualify | `qualification`: the host profiles and the kinds; a signal parameter is a `probe` word |
| the machine class of a probe (arch, core band, clock band) | plugin-hostd's probe | plugin-hostd | the `machine` domain (plugin-hostd), read directly |
| plugin key (SHA-256, format, uri) | plugin-qualify, from the binary | nobody: it is the bytes | plugin-db: the formats are plugin-db's words, checked against plugin-db's own published item, never a copy (section 3.4) |
| package fields (format, distro, arch words) | the measuring run (none today) | plugin-qualify's record format | `qualification`, the `package` object precondition 1 adds |
| the database layout, `user_version`, the reader | this repository | this repository | plugin-db-qualification |

### Ownership of the store, the writer and the readers

Producer, changer and owner domain, for what the consumer switch adds (ruling (a), section 9):

- **The store DDL, the reader, the writer and the packages `plugin-qualification-db-write` and
  `plugin-qualification-db-schema`:** this repository produces them, changes them and owns them.
- **The record content** (the figures, verdicts, tiers and cost of a record, the key and the binary path of
  section 3.7): plugin-qualify (the judge and the sync) produces it, and this repository stores it. The layout of the
  store and the rule that the key is the binary entry's SHA-256 are this repository's; what a record says is
  plugin-qualify's.
- **The per-file list** (the files a pin holds, section 3.7): plugin-hostd produces it (`--pin-files`), and this
  repository stores it as given.
- **The words:** the `plugin-db`, `machine`, `probe`, `hosting` and `qualification` domains, each its owner's, as the
  table above says; the store checks against them and defines none.
- **The readers:** plugin-qualify (the match, `qualify-rejudge`, `pruneStale` and `pluginCounts`), plugin-hostd's
  `qualcost`, and omx-panel later. Each reads through `pqdb.h` or the command and is its own repository's; the answer
  is this repository's.

The database stores words and checks every word column against its owner's domain item; it never defines a word,
and its DDL holds no list of words.

## 2. Files and locations

| file | path | shipped or written by | opened |
| --- | --- | --- | --- |
| base database | `/usr/share/omx/qualification/qualification.sqlite` | the package `plugin-qualification-records`, one per architecture, built at package build from `records/` | read only, immutable |
| user layer, user scope | `<home>/.local/share/omx/qualification/qualification.sqlite`: the XDG data directory's default, `<home>` from `getpwuid(geteuid())`; `XDG_DATA_HOME` is not read | plugin-qualify-sync of that user, the only writer of its records (section 6.1); nobody before the consumer switch | read only by readers; read-write by the writer only |
| user layer, system scope | `/var/lib/omx/qualification/qualification.sqlite` (the place of today's system `qualification_dir`, whose files nothing reads after the switch) | `plugin-qualify-sync --system`, the only writer of its records (section 6.1) | the same |
| the DDL | `schema/qualification.sql` in this repository; installed as `<datadir>/plugin-qualification-db/qualification.sql` by `plugin-qualification-db-schema` (section 7), named by the `schema` variable of `plugin-qualification-db.pc` (`pkg-config --variable=schema plugin-qualification-db`) | read by the writer at build and when it creates a user layer, and by test fixtures, from the installed file, with no checkout | |

The base database sits beside today's `<host class>/<set>/` directories, which stay as they are until the consumer
switch stops installing them (section 5). After the switch nothing reads them: `plugin-qualify-sync`'s distributed
reader (`readDistributedLayer`, `matchDistributed`, `applyDistributed` of its `src/distributed-records.ts`) is
removed, and the sync reads the base through the reader of section 6.

**Scopes.** `PQDB_SCOPE_USER` reads the base and the home's user layer only; `PQDB_SCOPE_SYSTEM` reads the base and
`/var/lib/omx/qualification/qualification.sqlite` only. Neither reads the other's layer. plugin-hostd takes
`PQDB_SCOPE_SYSTEM` when it runs as root (a system service) and `PQDB_SCOPE_USER` otherwise: the rule it applies to its
`qualification_dir` today (its docs/guide.md). plugin-qualify-sync takes the scope of its `--system` flag.

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
  the table `word_check` names the owner domain item (or items) that hold its words: every word column has at least
  one row, filled at build from the domains (section 3.4). The writer refuses a word not in its items; the reader
  checks every distinct word at open (section 6). `WORD()` is only a shape check; no column is checked by shape alone.
- A NAME is an identifier written by a program: an id, a hash, a version, a time, a symbol. It is stored as written and
  is not checked against a domain.
- A RELATIVE PATH is a path below an install root (section 3.7): a name whose shape is checked.
  `RELPATH(c)` below is `length(c) > 0 AND c NOT GLOB '/*' AND substr(c, -1) <> '/' AND instr(c, '//') = 0 AND instr('/' || c || '/', '/./') = 0 AND instr('/' || c || '/', '/../') = 0`:
  not empty, not absolute, no empty, `.` or `..` segment. Its separator is `/`.
- A NUMBER is stored as INTEGER (counts, rates, quanta, frames, kilobytes, bytes) or REAL (figures that may be
  fractional). A param's number (`reason_param.number`, `adapter_param.number`, `adapter_cell_param.number`) is column type `ANY` checked to be `integer` or `real`, so the round trip keeps an integer an integer and a fraction a fraction as the JSON had it. Every table is `STRICT`, so a value of the wrong type is refused at insert.
- A SENTENCE, prose written for a person, is not stored. Section 3.5 lists every field of today's records and
  provenances that is one. The base database records the commit it was built from (`store_info.built_from`), where the
  text of every record stays.
- An optional JSON object is present when at least one of its columns is not NULL. The writer refuses an empty object
  (`{}`) by name, except a map of the always-present list of section 3.3 (`reasons[].params`) and the two params maps of the adapter pass (`adapter.params`, `adapter.cells[].params`), whose `{}` is data: present, no params (`record.adapter_params`, `adapter_cell.params`).
- A boolean is INTEGER with `CHECK (c IN (0, 1))`.

### 3.3 DDL

`schema/qualification.sql` holds exactly this, with `WORD(c)` and `RELPATH(c)` written out. Foreign keys are declared
`ON DELETE CASCADE`; the writer runs with `PRAGMA foreign_keys = ON`.

```sql
CREATE TABLE store_info (
  one            INTEGER PRIMARY KEY CHECK (one = 1),
  user_layer     INTEGER NOT NULL CHECK (user_layer IN (0, 1)),   -- 0: the base, 1: a user layer
  record_schema  TEXT NOT NULL,            -- 'plugin-qualify.qualification-record/1'
  built_from     TEXT CHECK (built_from IS NULL OR (length(built_from) = 40 AND built_from NOT GLOB '*[^0-9a-f]*'))
                                           -- base: the commit of this repository (section 5); user: NULL
) STRICT;

CREATE TABLE store_domain (                -- each domain the words were checked against, at its info.version
  domain  TEXT PRIMARY KEY,                -- 'qualification', 'machine'
  version TEXT NOT NULL
) STRICT;

CREATE TABLE word_check (                  -- the owner domain items that hold the words of a column
  tbl    TEXT NOT NULL,
  col    TEXT NOT NULL,
  domain TEXT NOT NULL REFERENCES store_domain,
  item   TEXT NOT NULL,                    -- a components.schemas name, e.g. QUALIFICATION_MEASUREMENT_VERDICT_RATINGS
  PRIMARY KEY (tbl, col, domain, item)     -- a word is valid when one of its column's items holds it
) STRICT;

CREATE TABLE plugin (
  plugin_id INTEGER PRIMARY KEY,
  sha256    TEXT NOT NULL CHECK (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
  format    TEXT NOT NULL CHECK (WORD(format)),
  uri       TEXT NOT NULL CHECK (length(uri) > 0),
  UNIQUE (sha256, format, uri)
) STRICT;

CREATE TABLE record_set (                  -- one provenance.json; base layer only
  set_id          INTEGER PRIMARY KEY,
  host_class      TEXT NOT NULL CHECK (WORD(host_class)),
  name            TEXT NOT NULL,           -- a name: the set's own (zynthian-vangelis, fedora44-48000-512)
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
  pass    INTEGER NOT NULL CHECK (pass IN (0, 1)),   -- 0: provenance.packages, 1: provenance.passes
  name    TEXT NOT NULL,
  version TEXT NOT NULL,
  PRIMARY KEY (set_id, pass, name)
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
  pkg_format  TEXT CHECK (pkg_format IS NULL OR WORD(pkg_format)),   -- deb, rpm
  pkg_name    TEXT,
  pkg_version TEXT,
  pkg_release TEXT,
  pkg_distro  TEXT CHECK (pkg_distro IS NULL OR WORD(pkg_distro)),   -- e.g. trixie, fc45
  pkg_arch    TEXT CHECK (pkg_arch IS NULL OR WORD(pkg_arch)),       -- the package's own arch word: arm64, x86_64, all, noarch
  -- binary: the main binary's path relative to its install root, and the identity rule of section 3.7
  binary_path    TEXT NOT NULL CHECK (RELPATH(binary_path)),
  layout_scheme  TEXT,
  layout_sha256  TEXT,
  unpinnable     INTEGER CHECK (unpinnable IN (0, 1)),               -- 1 when binary.unpinnable is present
  host_extensions INTEGER CHECK (host_extensions IS NULL OR host_extensions = 1),   -- 1: the hostExtensions list is present (record_extension, possibly empty); NULL: an LV2 record, or a CLAP probe that ended before the offer
  tested_version TEXT,
  plugin_name    TEXT,                     -- plugin.name, the name the plugin gives itself; NULL: absent
  measured_at    TEXT NOT NULL,
  latency_line_ms REAL,                    -- latencyLineMs: the line the cells' latency_ms stand against; NULL: absent (a record from before it)
  rules          TEXT CHECK (rules IS NULL OR rules GLOB 'plugin-qualify-rules/[0-9]*.[0-9]*'),   -- the rules the verdicts were judged by, a name; NULL: absent
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
  adapter_params   INTEGER CHECK (adapter_params IS NULL OR adapter_params IN (0, 1)),   -- NULL: no adapter object; 1: adapter.params present
  -- memory pass
  memory_run_measured_at TEXT, memory_run_id TEXT, memory_run_runner TEXT, memory_run_child TEXT,
  -- rejudgement
  rejudged_at TEXT, rejudged_by TEXT,
  rejudged_measured_at TEXT, rejudged_run_id TEXT,
  rejudged_runner TEXT, rejudged_child TEXT, rejudged_interposer TEXT,
  rejudged_adapter_measured_at TEXT,
  rejudged_memory_measured_at TEXT, rejudged_memory_runner TEXT, rejudged_memory_child TEXT,
  CHECK ((layout_scheme IS NULL) = (layout_sha256 IS NULL)),
  UNIQUE (record_id, plugin_id, offer, host_class)      -- the target of claim's foreign key
) STRICT;
CREATE INDEX record_plugin  ON record (plugin_id, offer, host_class);
CREATE INDEX record_package ON record (pkg_format, pkg_name, pkg_version, pkg_release, pkg_distro, pkg_arch);
CREATE INDEX record_binary  ON record (binary_path);

CREATE TABLE record_file (                 -- binary.files[]: the per-file list the pin matches on (section 3.7)
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord       INTEGER NOT NULL,              -- the list's order: ascending by path, bytewise (section 3.7)
  path      TEXT NOT NULL CHECK (RELPATH(path)),   -- relative to the item's root, as the pin names it (section 3.7)
  sha256    TEXT NOT NULL CHECK (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
  PRIMARY KEY (record_id, ord),
  UNIQUE (record_id, path)
) STRICT;
CREATE INDEX record_file_sha256 ON record_file (sha256);

CREATE TABLE record_extension (            -- hostExtensions[]: the CLAP host extensions the run offered the plugin (section 6.2)
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord       INTEGER NOT NULL,
  extension TEXT NOT NULL CHECK (length(extension) > 0),   -- a name as the prober wrote it, e.g. clap.log
  PRIMARY KEY (record_id, ord),
  UNIQUE (record_id, extension)
) STRICT;

CREATE TABLE record_version (              -- adapter.versions, rejudged.figures.adapter.versions
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  rejudged  INTEGER NOT NULL CHECK (rejudged IN (0, 1)),   -- 0: adapter.versions, 1: rejudged.figures.adapter.versions
  name      TEXT NOT NULL,
  version   TEXT NOT NULL,
  PRIMARY KEY (record_id, rejudged, name)
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
  verdict_ord INTEGER,                     -- the verdict it is a reason of, or
  cost_ord    INTEGER,                     -- the cost entry it is a reason of: exactly one is set
  ord       INTEGER NOT NULL,
  dimension TEXT NOT NULL CHECK (WORD(dimension)),
  rating    TEXT NOT NULL CHECK (WORD(rating)),
  code      TEXT NOT NULL CHECK (WORD(code)),
  CHECK ((verdict_ord IS NULL) <> (cost_ord IS NULL)),
  FOREIGN KEY (record_id, verdict_ord) REFERENCES verdict (record_id, ord) ON DELETE CASCADE,
  FOREIGN KEY (record_id, cost_ord) REFERENCES cost_entry (record_id, ord) ON DELETE CASCADE
) STRICT;
CREATE UNIQUE INDEX reason_of_verdict ON reason (record_id, verdict_ord, ord) WHERE verdict_ord IS NOT NULL;
CREATE UNIQUE INDEX reason_of_cost    ON reason (record_id, cost_ord, ord)    WHERE cost_ord IS NOT NULL;

CREATE TABLE reason_param (                -- reasons[].params
  reason_id INTEGER NOT NULL REFERENCES reason ON DELETE CASCADE,
  name      TEXT NOT NULL CHECK (WORD(name)),
  number    ANY CHECK (number IS NULL OR typeof(number) IN ('integer', 'real')),
  word      TEXT CHECK (word IS NULL OR WORD(word)),
  CHECK ((number IS NULL) <> (word IS NULL)),
  PRIMARY KEY (reason_id, name)
) STRICT;

CREATE TABLE tier (                        -- tiers.inProcess, tiers.isolated
  record_id  INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  tier       TEXT NOT NULL CHECK (WORD(tier)),          -- inProcess, isolated
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
  latency_ms REAL,                          -- latencyMs: the measured latency in ms at the cell's rate, as written; NULL: absent
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
  rt_own_threads INTEGER,                  -- threads the plugin started itself (judged under hosting.rt-safety.own-threads); NULL: not taken
  rt_other_allocations INTEGER, rt_other_locks INTEGER, rt_other_syscalls INTEGER,   -- what threads other than the audio thread did; all three or none
  note_sweep_applicable INTEGER CHECK (note_sweep_applicable IN (0, 1)),
  note_sweep_dialect TEXT CHECK (note_sweep_dialect IS NULL OR WORD(note_sweep_dialect)),
  note_sweep_allocations INTEGER, note_sweep_locks INTEGER, note_sweep_syscalls INTEGER,
  CHECK ((rt_other_allocations IS NULL) = (rt_other_locks IS NULL) AND (rt_other_locks IS NULL) = (rt_other_syscalls IS NULL)),
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
  PRIMARY KEY (plugin_id, offer, host_class, rate, quantum),
  -- the claim repeats the record's key, offer and class and the cell's rate and quantum: these tie them
  FOREIGN KEY (record_id, plugin_id, offer, host_class)
    REFERENCES record (record_id, plugin_id, offer, host_class) ON DELETE CASCADE,
  FOREIGN KEY (record_id, rate, quantum) REFERENCES cell (record_id, rate, quantum) ON DELETE CASCADE
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

CREATE TABLE record_history (              -- history[]: the adjust --history blocks
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord       INTEGER NOT NULL,
  host_class TEXT NOT NULL,                -- hostClass, arch/cores/clock: a name
  file      TEXT NOT NULL,                 -- the history file as it was named
  at        TEXT NOT NULL,
  key_uri   TEXT, key_digest TEXT,         -- key; both NULL: absent
  found     INTEGER NOT NULL CHECK (found IN (0, 1)),
  windows_solo INTEGER, windows_grouped INTEGER,             -- windows; both NULL: absent
  summary_crashed INTEGER CHECK (summary_crashed IS NULL OR summary_crashed IN (0, 1)),
  summary_raises_xruns INTEGER CHECK (summary_raises_xruns IS NULL OR summary_raises_xruns IN (0, 1)),   -- summary; both NULL: absent
  unknown_keys INTEGER CHECK (unknown_keys IS NULL OR unknown_keys = 1),   -- 1: unknownKeys present (history_unknown_key, possibly none)
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE history_unknown_key (         -- history[].unknownKeys.<name>
  record_id INTEGER NOT NULL,
  history_ord INTEGER NOT NULL,
  name      TEXT NOT NULL,
  value     TEXT NOT NULL,                 -- as written in the history file
  PRIMARY KEY (record_id, history_ord, name),
  FOREIGN KEY (record_id, history_ord) REFERENCES record_history (record_id, ord) ON DELETE CASCADE
) STRICT;

CREATE TABLE history_verdict (             -- history[].verdicts[]
  record_id INTEGER NOT NULL,
  history_ord INTEGER NOT NULL,
  ord       INTEGER NOT NULL,
  host      TEXT NOT NULL CHECK (WORD(host)),
  measured  TEXT CHECK (measured IS NULL OR WORD(measured)),   -- NULL: null
  adjusted  TEXT CHECK (adjusted IS NULL OR WORD(adjusted)),   -- NULL: null
  move      TEXT NOT NULL CHECK (WORD(move)),
  reason    TEXT NOT NULL CHECK (WORD(reason)),
  blocked_by INTEGER CHECK (blocked_by IS NULL OR blocked_by = 1),   -- 1: blockedBy present (history_blocked, possibly none)
  PRIMARY KEY (record_id, history_ord, ord),
  FOREIGN KEY (record_id, history_ord) REFERENCES record_history (record_id, ord) ON DELETE CASCADE
) STRICT;

CREATE TABLE history_blocked (             -- history[].verdicts[].blockedBy[]
  record_id INTEGER NOT NULL,
  history_ord INTEGER NOT NULL,
  verdict_ord INTEGER NOT NULL,
  ord       INTEGER NOT NULL,
  code      TEXT NOT NULL CHECK (WORD(code)),
  PRIMARY KEY (record_id, history_ord, verdict_ord, ord),
  FOREIGN KEY (record_id, history_ord, verdict_ord) REFERENCES history_verdict (record_id, history_ord, ord) ON DELETE CASCADE
) STRICT;

CREATE TABLE run_step (                    -- run.steps[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  step TEXT NOT NULL CHECK (WORD(step)),
  result TEXT NOT NULL CHECK (WORD(result)),
  code TEXT CHECK (code IS NULL OR WORD(code)),
  cpu_percent REAL, latency_frames INTEGER, midi_inputs_linked INTEGER, xruns INTEGER,
  pool_allocations_on INTEGER, pool_locks_on INTEGER, pool_syscalls_on INTEGER, pool_tasks_on_helpers INTEGER,
  pool_dsp_load_off REAL, pool_dsp_load_on REAL, pool_xruns_off INTEGER, pool_xruns_on INTEGER,   -- the pool step's graph load and xruns, off and on; NULL: absent
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
  params INTEGER NOT NULL CHECK (params IN (0, 1)),   -- 1 when this cell's params is present
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE adapter_param (               -- adapter.params
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  name      TEXT NOT NULL CHECK (WORD(name)),
  number    ANY CHECK (number IS NULL OR typeof(number) IN ('integer', 'real')),
  word      TEXT CHECK (word IS NULL OR WORD(word)),
  CHECK ((number IS NULL) <> (word IS NULL)),
  PRIMARY KEY (record_id, name)
) STRICT;

CREATE TABLE adapter_cell_param (          -- adapter.cells[].params
  record_id INTEGER NOT NULL,
  ord       INTEGER NOT NULL,
  name      TEXT NOT NULL CHECK (WORD(name)),
  number    ANY CHECK (number IS NULL OR typeof(number) IN ('integer', 'real')),
  word      TEXT CHECK (word IS NULL OR WORD(word)),
  CHECK ((number IS NULL) <> (word IS NULL)),
  PRIMARY KEY (record_id, ord, name),
  FOREIGN KEY (record_id, ord) REFERENCES adapter_cell (record_id, ord) ON DELETE CASCADE
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

- ALWAYS PRESENT with its parent, empty when it has no rows: `verdicts`, `verdicts[].reasons`,
  `cost`, `cost[].reasons`, `reasons[].params` (empty in 516 reasons today), `tiers.offeredOn` (empty in 4,856
  records), `measurements.grid`, `measurements.grid[].rtSafety.events` (present with `rtSafety`, empty in 9,015
  cells), `measurements.behaviour.features.required` (present with `behaviour`, empty in 3,077 records),
  `notMeasured`, `run.steps`, `memoryRun.cells`;
- A CLAP record's `hostExtensions` is present (empty when the run offered none) when its probe reached the offer, and absent when the probe ended before it (a crash or a timeout: 254 of today's CLAP records); an LV2 record has none. `record.host_extensions` is 1 when the list is present and NULL otherwise. The row judge reads such a CLAP record's NULL as an empty list, exactly as the probe judge reads the absent `offer.clapExtensions` today (`hostExtensions: output.offer.clapExtensions ?? []`), so a storage move changes no verdict (section 6.2; ruling 11).
- PRESENT ONLY WITH ROWS: `adapter.cells`, `probe.ends`, `measurements.unmeasured`, `rejudged.owes`.

`binary.files` is in neither list: it is always present and never empty (section 3.7; every record of today holds at
least one file). The writer refuses a record that breaks the rule (an absent array of the first list, a present empty
array of the second, an absent or empty `binary.files`), naming the file and the path.

The user-layer rule for `set_id` (NULL exactly when `store_info.user_layer` is 1) needs a subquery, which a `CHECK`
cannot hold, so the DDL states it as a trigger:

```sql
CREATE TRIGGER record_set_by_layer BEFORE INSERT ON record
WHEN (NEW.set_id IS NULL) <> ((SELECT user_layer FROM store_info) = 1)
BEGIN SELECT RAISE(ABORT, 'record.set_id: NULL exactly in the user layer'); END;
```

### 3.4 Domain words and their check

**Preconditions of change 2.** The words of section 3.3 that no readable domain item holds today are published by
their owners before change 2 merges:

1. **plugin-qualify: the `qualification` domain's minors** that add every `qualification` item marked "added" below:
   the missing qualification words, the words of the record's `package` object (package format `deb` and `rpm`,
   distro, arch), the kinds of an adapter code and the outcome its own memory bound writes. Each item holds only
   plugin-qualify's own words; another owner's words are checked against that owner's domain, never a copy.
2. **plugin-db: its address formats as a domain item.** The formats `clap` and `lv2` stay plugin-db's words; the store
   checks them against plugin-db's own published list. `PLUGIN_DB_ADDRESS_FORMATS` moves from `data/db.json` (the
   older rendered layout, `contract.d/3/plugin-db`) to a `plugin-db` domain, its one source, which the loader opens.
3. **plugin-hostd: `MACHINE_FAMILIES`** in its `machine` domain (the CPU families the probe writes).
4. **plugin-hostd: a `probe` domain** with the probe's reasons, outcomes, steps and signals, which the probe reads.
5. **omx-clap-core: a `hosting` domain** with its hosting codes, moved from `data/hosting*.json` to the domain as their
   one source. Not in this pass: see the exception below.

**The hosting exception, this pass only (owner ruling, 2026-11-19).** omx-contract's domain render emits index macros
only, while omx-clap-core's consumers need the hosting code strings, their sentences and the TypeScript module that
`data/hosting*.json` renders today. So this pass omx-clap-core keeps `data/hosting*.json` as the one source of the
hosting codes, and there is no `hosting` domain:

- **The writer** reads the hosting words from the installed omx-clap-core contract package (each `kind: codes` item of
  `<contractdir>/3/omx-clap-core/hosting.json` and `hosting/*.json` (the schema major 3), as omx-contract's installer lays
  it out; its words are the `code` of each entry), refuses a hosting word none of them holds exactly as for any other
  column, writes the `store_domain` row `hosting` at that package's version (its `MANIFEST.json` `version`), and fills `word_check` for the hosting columns as for the others.
- **The C reader** does not open `hosting` and does not check the hosting words: libomx-domain opens domain documents
  only. A column whose only items are `hosting` items is not checked; in a column that also has other owners' items
  (`verdict.deciding`, `tier.deciding`, `reason.code`), only a word beginning `hosting.` is passed over, and every
  other word must be in one of the column's other items. Every other column is checked at open as below. A store's
  hosting words are therefore checked once, by the writer, against the package it was built with.
- **Its end.** Right after this pass, an omx-contract change lets a domain render the code strings, sentences and
  TypeScript module, omx-clap-core moves the hosting codes to its `hosting` domain with byte-identical rendered
  output, and the reader checks the hosting columns like every other column; this exception is then removed. The check
  `hosting-skip-ends` holds the end: it fails when omx-clap-core's main ships a `hosting` domain document, or a
  contract directory the tests read holds one, while the reader still skips the hosting words.

Change 2's build floors are the contract packages that ship these. Until they are released, change 2 stays red. The
item names below are proposed; each owner's change names them.

The writer reads each domain from the installed contract directory (as docs/runtime-data.md says for Python: the
installed JSON, validated with `jsonschema` against Draft 2020-12, `info.version` at least the floor), records each
domain's `info.version` in `store_domain`, and fills `word_check` from the table below. It refuses a word that none of
its column's items holds, naming the record file, the JSON path and the word.

| column(s) | owner | domain | item | today |
| --- | --- | --- | --- | --- |
| `plugin.format` | plugin-db | `plugin-db` | `PLUGIN_DB_ADDRESS_FORMATS` (`clap`, `lv2`) | published by the plugin-db precondition; today only in `data/db.json` |
| `record_set.host_class`, `record.host_class` | plugin-hostd | `qualification` | `QUALIFICATION_HOST_CLASSES` (`rpi5`, `x86-64`) | added; the existing `QUALIFICATION_MACHINE_CLASSES` holds `desk`, `raspberry-pi-4`, `raspberry-pi-5`, words no record holds |
| `record_set.tier` | plugin-hostd | `qualification` (plugin-hostd's domain) | `QUALIFICATION_SET_TIERS` (`reference`, `provisional`, `hardware`) | added |
| `record_set.host_profile`, `verdict.host`, `cost_entry.host`, `tier.host` | plugin-hostd | `qualification` | `QUALIFICATION_HOST_PROFILES` (`omx-clap-host`, `openmixer-console`, ...) | added |
| `record.adapter_host` | plugin-hostd | `qualification` | `QUALIFICATION_ADAPTER_HOSTS`: the hosts an adapter runs a plugin under (`omx-clap-host`, `mod-host`, `jalv`), not the judge's profiles; plugin-qualify names its words | added |
| `set_setting.key` | plugin-hostd | `qualification` | `QUALIFICATION_SYNC_SETTINGS` (plugin-qualify-sync's setting keys) | added |
| `record.offer` | plugin-hostd | `qualification` | `QUALIFICATION_OFFERS` (`default`, `custom`) | added |
| `record.pkg_format` | plugin-hostd | `qualification` | `QUALIFICATION_PACKAGE_FORMATS` (`deb`, `rpm`) | added (the `package` object) |
| `record.pkg_distro` | plugin-hostd | `qualification` | `QUALIFICATION_PACKAGE_DISTROS` (`trixie`, `fc44`, `fc45`, ...) | added (the `package` object) |
| `record.pkg_arch` | plugin-hostd | `qualification` | `QUALIFICATION_PACKAGE_ARCHES` (`arm64`, `amd64`, `all`, `aarch64`, `x86_64`, `noarch`) | added (the `package` object) |
| `record.mc_arch` | plugin-hostd | `machine` | `MACHINE_ARCHES` | exists (1.0.0) |
| `record.mc_core_band` | plugin-hostd | `machine` | `MACHINE_CORE_BANDS` | exists |
| `record.mc_clock_band` | plugin-hostd | `machine` | `MACHINE_CLOCK_BANDS` | exists |
| `record.mc_family` | plugin-hostd | `machine` | `MACHINE_FAMILIES` | added by plugin-hostd in the same wave |
| `record.probe_reason` | plugin-hostd | `probe` | `PROBE_REASONS` (`on-request`, ...) | added (precondition 4) |
| `record.probe_outcome`, `cell.outcome`, `probe_end.outcome`, `memory_run_cell.outcome` | plugin-hostd | `probe`, `qualification` | `PROBE_OUTCOMES` (the probe's: `probe.ok`, `probe.crashed`, `probe.memory-limit`, ...) and `QUALIFICATION_MEMORY_BOUND_OUTCOMES` (`probe.oom`, which plugin-qualify writes when its own RLIMIT_DATA bound ends a run) | added (preconditions 4 and 1) |
| `probe_end.step` | plugin-hostd | `probe` | `PROBE_STEPS` | added (precondition 4) |
| `probe_end.signal` | plugin-hostd | `probe` | `PROBE_SIGNALS` (`SIGSEGV`, `SIGABRT`, ...) | added (precondition 4) |
| `record.adapter_code`, `adapter_cell.code` | plugin-hostd | `qualification`, `probe` | an adapter code, checked in parts (below): `QUALIFICATION_ADAPTER_HOSTS`, `QUALIFICATION_ADAPTER_CODE_KINDS` (`resp`, `signal`, `no-jack-client`, `silent-under-note`, ...) and, for `signal`, `PROBE_SIGNALS` | added (preconditions 1 and 4) |
| `verdict.rating`, `tier.rating`, `reason.rating` | plugin-hostd | `qualification` | `QUALIFICATION_MEASUREMENT_VERDICT_RATINGS` | exists (1.1.0) |
| `verdict.hosting`, `tier_offered.tier` | plugin-hostd | `qualification` | `QUALIFICATION_VERDICT_HOSTINGS` (`isolated`, `in-process`: the hosting paths, as `verdict.hosting` and `tiers.offeredOn[]` write them) | added |
| `verdict.arm` | plugin-hostd | `qualification` | `QUALIFICATION_VERDICT_ARMS` (`declaration`, `run`) | added |
| `verdict.deciding`, `tier.deciding`, `reason.code` | omx-clap-core, plugin-hostd | `hosting`, `probe`, `qualification` | the `HOSTING_*` codes items, `PROBE_OUTCOMES`, `QUALIFICATION_MEMORY_BOUND_OUTCOMES`, and an adapter code checked in parts: today's values come from all of them | added (preconditions 1, 4 and 5) |
| `not_measured.code`, `unmeasured.code`, `cell.latency_code` | omx-clap-core | `hosting` | the `HOSTING_*` codes items | added (precondition 5) |
| `reason.dimension`, `unmeasured.dimension`, `not_measured.dimension` | plugin-hostd | `qualification` | `QUALIFICATION_MEASUREMENT_DIMENSIONS` | exists; the move adds `memory`, `hostAdmission` and `memoryGrowth` (`not_measured.dimension` holds the last) |
| `reason_param.name`, `adapter_param.name`, `adapter_cell_param.name` | plugin-hostd | `qualification` | `QUALIFICATION_REASON_PARAMS` (`rate`, `quantum`, `blocks`, ...; the adapter params' keys `notes`, `peak`, `quantum`, `rate`, `resp`, `step` are in it too) | added |
| `reason_param.word`, `adapter_param.word`, `adapter_cell_param.word` | plugin-hostd | `qualification` | `QUALIFICATION_REASON_PARAM_WORDS` (`yes`, `perInstance`, `add`) | added |
| `tier.tier` | plugin-hostd | `qualification` | `QUALIFICATION_RECORD_TIERS` (`inProcess`, `isolated`: the keys of `tiers`) | added |
| `cell.latency_unmeasured_reason`, `cell.mem_unmeasured_reason` | plugin-hostd | `qualification` | `QUALIFICATION_MEASUREMENT_UNMEASURED_REASONS` | exists; it holds every value of both columns today (`voices-unknown`, `probe-error`, `not-attempted`, ...). `QUALIFICATION_RESOURCE_UNMEASURED_REASONS` (`unmeasured-on-class`, `limit-exceeded`) is the resource budget's, and no record holds its words |
| `cell.voices_basis`, `cell.mem_basis` | plugin-hostd | `qualification` | `QUALIFICATION_MEASUREMENT_VOICE_BASES` | exists |
| `cell.mem_limit_mechanism` | plugin-hostd | `qualification` | `QUALIFICATION_MEMORY_LIMIT_MECHANISMS` (`rlimit-data`) | added |
| `cell.note_sweep_dialect` | plugin-hostd | `qualification` | `QUALIFICATION_NOTE_SWEEP_DIALECTS` (`midi`, `clap`) | added |
| `run_step.step` | plugin-hostd | `qualification` | `QUALIFICATION_RUN_STEPS` (`scan`, `describe`, `probe`, `rt-safety`, `isolated`, `pool`) | added |
| `run_step.result` | plugin-hostd | `qualification`, `probe` | `QUALIFICATION_STEP_RESULTS` (`ok`, `safe`, `unsafe`, `refused`, `not-asked`, ...), `PROBE_OUTCOMES` and `QUALIFICATION_MEMORY_BOUND_OUTCOMES` (a step ends `probe.oom` when plugin-qualify's own bound stops it) | added |
| `run_step.code` | plugin-hostd | `qualification` | `QUALIFICATION_STEP_CODES` (`isolated.not-added`, `pool.not-watched`, ...) | added |
| `rejudged_owe.code` | plugin-hostd | `qualification` | `QUALIFICATION_REJUDGE_OWES` | added |
| `rejudged_owe.measurement` | plugin-hostd | `qualification` | `QUALIFICATION_REJUDGE_MEASUREMENTS` | added |
| `history_verdict.host` | plugin-hostd | `qualification` | `QUALIFICATION_HOST_PROFILES` | exists |
| `history_verdict.measured`, `.adjusted` | plugin-hostd | `qualification` | `QUALIFICATION_PIN_VERDICTS` (the `PIN_VERDICTS` of `pins-file.ts`: `in-process`, `isolated`, `refused`) | added |
| `history_verdict.move` | plugin-hostd | `qualification` | `QUALIFICATION_HISTORY_MOVES` (`demote`, `promote`, `none`) | added |
| `history_verdict.reason` | plugin-hostd | `qualification` | `QUALIFICATION_HISTORY_REASONS` (`history.crashed`, `history.steady`, `history.no-record`, ...: `HISTORY_REASON`) | added |
| `history_blocked.code` | plugin-hostd, omx-clap-core | `qualification`, `hosting`, `probe` | `QUALIFICATION_HISTORY_BLOCKERS` (the words `blockers()` of `history-adjust.ts` writes that are no reason code: `refused`, `unknown`, `no-deciding-reason`; plugin-qualify names them) and the items of `reason.code` | added |

An adapter code is written `<host>.<kind>` or `<host>.<kind>-<parameter>` and stored as written. Its check splits it:
`<host>` is a word of `QUALIFICATION_ADAPTER_HOSTS`, `<kind>` a word of `QUALIFICATION_ADAPTER_CODE_KINDS`, and the
parameter is what the kind takes: a decimal integer for `resp` and `exit`, a word of `PROBE_SIGNALS` for `signal`,
none for the others. A code that does not split this way is refused like any other word, naming the part.

`claim.offer` and `claim.host_class` are not checked on their own: their foreign key ties them to the record's. The
columns this table does not name are names or numbers (section 3.2). The words in parentheses are today's values, given
to show what each item holds; the DDL and the writer hold none of them.

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
| `plugin.name` | `record.plugin_name` (NULL when absent): a name, per record, since the key does not fix it |
| `provenance` | not stored: a record's provenance is its set's (`record_set`, `set_package`, `set_setting`), and a record of the user layer has none; the writer refuses it as `field-unmapped`, and the sync writes none |
| (none) | `record.pkg_format`, `pkg_name`, `pkg_version`, `pkg_release`, `pkg_distro`, `pkg_arch`: NULL (below) |
| `binary.path` | `record.binary_path`: the path RELATIVE TO THE INSTALL ROOT (section 3.7). An absolute one is refused (`path-absolute`); `records/` is rewritten once, not read in two forms (section 3.7) |
| `binary.files[].path`, `.sha256` | `record_file.path`, `record_file.sha256`, in the list order of section 3.7 |
| `binary.layout.scheme`, `.sha256` | `record.layout_scheme`, `record.layout_sha256` |
| `binary.unpinnable` | `record.unpinnable` = 1 (its sentence: see below) |
| `testedVersion` | `record.tested_version` |
| `measuredAt` | `record.measured_at` |
| `latencyLineMs` | `record.latency_line_ms` (NULL when absent) |
| `rules` | `record.rules` (NULL when absent); a name, `plugin-qualify-rules/<major>.<minor>`, not a word |
| `run.id` | `record.run_id` |
| `run.steps[].step`, `.result`, `.code` | `run_step.step`, `.result`, `.code` |
| `run.steps[].figures.cpuPercent`, `.latencyFrames`, `.midiInputsLinked`, `.xruns` | `run_step.cpu_percent`, `.latency_frames`, `.midi_inputs_linked`, `.xruns` |
| `run.steps[].pool.allocationsOn`, `.locksOn`, `.syscallsOn`, `.tasksOnHelpers` | `run_step.pool_allocations_on`, `.pool_locks_on`, `.pool_syscalls_on`, `.pool_tasks_on_helpers` |
| `run.steps[].pool.dspLoadOff`, `.dspLoadOn`, `.xrunsOff`, `.xrunsOn` | `run_step.pool_dsp_load_off`, `.pool_dsp_load_on`, `.pool_xruns_off`, `.pool_xruns_on` (NULL when absent) |
| `tool.runner`, `.child`, `.interposer` | `record.tool_runner`, `.tool_child`, `.tool_interposer` |
| `probe.file`, `.sha256`, `.bytes` | `record.probe_file`, `.probe_sha256`, `.probe_bytes` |
| `probe.protocol.name`, `.version` | `record.probe_protocol`, `.probe_protocol_version` |
| `probe.reason`, `.outcome`, `.complete`, `.meetsProtocol` | `record.probe_reason`, `.probe_outcome`, `.probe_complete`, `.probe_meets_protocol` |
| `probe.load.loadavg1`, `.cores` | `record.probe_loadavg1`, `.probe_cores` |
| `probe.machineClass.arch`, `.family`, `.coreBand`, `.clockBand`, `.preemptRt`, `.cstatesLimited` | `record.mc_arch`, `.mc_family`, `.mc_core_band`, `.mc_clock_band`, `.mc_preempt_rt`, `.mc_cstates_limited` |
| `probe.ends[].step`, `.outcome`, `.exitStatus`, `.signal` | `probe_end.step`, `.outcome`, `.exit_status`, `.signal` |
| `verdicts[].host`, `.measured`, `.rating`, `.qualified`, `.hosting`, `.arm`, `.deciding` | `verdict.*` of the same names |
| `verdicts[].reasons[].dimension`, `.rating`, `.code` | `reason.*` with `verdict_ord` = the verdict's `ord` |
| `verdicts[].reasons[].params.<name>` | `reason_param.name`, `.number` or `.word` |
| `cost[].host`, `.rate`, `.quantum` | `cost_entry.*` |
| `cost[].reasons[]` and their `params` | `reason`, `reason_param` with `cost_ord` = the cost entry's `ord` |
| `tiers.inProcess.*`, `tiers.isolated.*` (`host`, `measured`, `qualified`, `rating`, `deciding`, `runsAlone`) | `tier` row with `tier` = `inProcess` or `isolated` |
| `tiers.offeredOn[]` | `tier_offered.tier` |
| `measurements.grid[].rate`, `.quantum`, `.outcome` | `cell.rate`, `.quantum`, `.outcome`; and one `claim` row |
| `measurements.grid[].latency.declaredFrames`, `.measuredFrames`, `.code`, `.unmeasuredReason` | `cell.latency_declared_frames`, `.latency_measured_frames`, `.latency_code`, `.latency_unmeasured_reason` |
| `measurements.grid[].latencyMs` | `cell.latency_ms` (NULL when absent): stored as written, never recomputed from the frames, and read back as the shortest decimal that gives the same double (as `JSON.stringify` writes it) |
| `measurements.grid[].cost.median`, `.percentile.p`, `.percentile.value`, `.blocks`, `.warmupBlocks` | `cell.cost_median`, `.cost_percentile_p`, `.cost_percentile_value`, `.cost_blocks`, `.cost_warmup_blocks` |
| `measurements.grid[].cost.voices.basis`, `.capacity`, `.held` | `cell.voices_basis`, `.voices_capacity`, `.voices_held` |
| `measurements.grid[].memory.afterInstantiateKb`, `.afterActivateKb`, `.atRestKb`, `.secondInstanceKb`, `.firstInstanceKb`, `.perInstanceKb`, `.notesHeldKb`, `.basis`, `.unmeasuredReason` | `cell.mem_after_instantiate_kb`, `.mem_after_activate_kb`, `.mem_at_rest_kb`, `.mem_second_instance_kb`, `.mem_first_instance_kb`, `.mem_per_instance_kb`, `.mem_notes_held_kb`, `.mem_basis`, `.mem_unmeasured_reason` |
| `measurements.grid[].memoryLimit.bytes`, `.mechanism` | `cell.mem_limit_bytes`, `.mem_limit_mechanism` |
| `measurements.grid[].rtSafety.interposer`, `.swept`, `.sweepApplicable`, `.blocks`, `.allocations`, `.locks`, `.syscalls`, `.threadViolations`, `.processErrors`, `.ownThreads` | `cell.rt_*` of the same names (`ownThreads` as `rt_own_threads`) |
| `measurements.grid[].rtSafety.otherThreads.allocations`, `.locks`, `.syscalls` | `cell.rt_other_allocations`, `.rt_other_locks`, `.rt_other_syscalls` (the record's grid carries the probe point's names for these counts) |
| `hostExtensions[]` (a CLAP record's; the probe output's `offer.clapExtensions`, section 6.2) | `record_extension.extension`; presence: `record.host_extensions` |
| `measurements.grid[].rtSafety.events[]` | `cell_event.event` |
| `measurements.grid[].noteSweep.applicable`, `.dialect`, `.allocations`, `.locks`, `.syscalls` | `cell.note_sweep_*` |
| `measurements.unmeasured[].dimension`, `.code`, `.rate`, `.quantum` | `unmeasured.*` |
| `measurements.behaviour.lifecycle.cycles`, `.failed`, `.instantiated` | `record.lifecycle_*` |
| `measurements.behaviour.threads.before`, `.afterFirstInstantiate`, `.afterAllFreed` | `record.threads_*` |
| `measurements.behaviour.features.required[]` | `feature_required.feature` |
| `notMeasured[].dimension`, `.code` | `not_measured.*` |
| `history[].hostClass`, `.file`, `.at`, `.key.uri`, `.key.digest`, `.found`, `.windows.solo`, `.windows.grouped`, `.summary.crashed`, `.summary.raisesXruns` | `record_history.*` (NULL when the object is absent) |
| `history[].unknownKeys.<name>` | `history_unknown_key.name`, `.value`; presence: `record_history.unknown_keys` |
| `history[].verdicts[].host`, `.measured`, `.adjusted`, `.move`, `.reason` | `history_verdict.*` (`measured`, `adjusted` NULL for a JSON null) |
| `history[].verdicts[].blockedBy[]` | `history_blocked.code`; presence: `history_verdict.blocked_by` |
| `adapter.admitted`, `.host`, `.measured`, `.code`, `.measuredAt` | `record.adapter_*` |
| `adapter.versions.<name>` | `record_version` with `rejudged` = 0 |
| `adapter.params.<name>` | `adapter_param.name`, `.number` or `.word`; presence: `record.adapter_params` (NULL with no `adapter` object, 1 when `params` is present, 0 when absent) |
| `adapter.cells[].rate`, `.quantum`, `.admitted`, `.measured`, `.code` | `adapter_cell.*` |
| `adapter.cells[].params.<name>` | `adapter_cell_param.name`, `.number` or `.word`; presence: `adapter_cell.params` |
| `memoryRun.measuredAt`, `.runId`, `.tool.runner`, `.tool.child` | `record.memory_run_measured_at`, `.memory_run_id`, `.memory_run_runner`, `.memory_run_child` |
| `memoryRun.cells[].rate`, `.quantum`, `.outcome` | `memory_run_cell.*` |
| `rejudged.at`, `.by` | `record.rejudged_at`, `.rejudged_by` |
| `rejudged.figures.measuredAt`, `.runId`, `.tool.runner`, `.tool.child`, `.tool.interposer` | `record.rejudged_measured_at`, `.rejudged_run_id`, `.rejudged_runner`, `.rejudged_child`, `.rejudged_interposer` |
| `rejudged.figures.adapter.measuredAt`, `.adapter.versions.<name>` | `record.rejudged_adapter_measured_at`; `record_version` with `rejudged` = 1 |
| `rejudged.figures.memory.measuredAt`, `.tool.runner`, `.tool.child` | `record.rejudged_memory_measured_at`, `.rejudged_memory_runner`, `.rejudged_memory_child` |
| `rejudged.owes[].code`, `.measurement` | `rejudged_owe.*` |

`provenance.json` of a set: `schema`, `set`, `hostClass`, `hostProfile`, `tier`, `measured`, `date`, `package.name`,
`package.version` → `record_set`; `packages.<name>` and `passes.<name>` → `set_package` (`pass` 0 and 1); `settings.<key>` (but `note`)
→ `set_setting`. `cell` (`{rate, quantum}`, written by plugin-qualify for a set of one cell) is checked, not stored: it
must be two integers equal to the cell of the set's name (`<set>-<rate>-<quantum>`), else the set is refused
(`field-type`, `cell-mismatch`); `record_set.name` and the set's `cell` rows hold it.

**The console key is held back** (issue #5's ruling, 2026-11-11: the console key waits for its desk run; applied to
the store 2026-11-20). The base holds no judgment of the `openmixer-console` profile. A record judged under
`omx-clap-host` that also carries one is kept, and its `verdicts[]` and `cost[]` entries whose `host` is
`openmixer-console`, and a `tiers.inProcess` or `tiers.isolated` that profile hosts, are left out as the migration reads
the file: the record file is not edited, and the rest of the record is stored whole. A record whose only verdict is the
console's is kept as a row with no verdict (ruling 2026-11-20: nothing is dropped; its console verdict is held back
like any other, and it answers with no verdict until the console key's desk run). A set whose `provenance.hostProfile` is `openmixer-console` is refused
(`console-profile`). `tiers.dimmed`, a sentence, is not stored either way. The round trip compares each record with
its file less those judgments.

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
(`run.memoryLock.reason`, step details). The record keeps the probe's file name, SHA-256 and size. The owner decided both
lists (section 9, ruling 1).

### 3.6 `user_version`

`PRAGMA user_version = 1` for this schema, set by the writer as the last statement of a build. The rule:

- There is ONE version, `PQDB_SCHEMA_VERSION` (1). It is written in two places, the header line of
  `schema/qualification.sql` (`user_version 1`), which the writer reads, and `pqdb.h`, which the reader compiles; a
  test holds the two equal. Any change of the DDL after a release is +1. No release carries a store yet (changes 2
  and 3 release with the consumer switch, section 9, ruling 8), so the DDL of section 3.7's amendment is version 1, and
  no store of an earlier shape exists to refuse. This holds only if no release of this repository ships a store before
  the code of this amendment lands (section 9, ruling 10; section 10): that code must land before this pass's
  release of this repository, or the DDL is version 2. A reader reads exactly its version; there is no range
  and no reader of an older version.
- The reader refuses, by name: a file whose `user_version` is not `PQDB_SCHEMA_VERSION` (`schema-other`, naming the
  file, its version and the reader's); a base and a user layer at different versions (`schema-mismatch`, naming both
  files and both versions, checked first); 0, a file that is no store (`not-a-store`).
- The base database is never upgraded: each build writes it new, at the writer's version. A package whose base is at a
  new version depends on the reader at the floor that reads it.
- The user layer is not upgraded in place in this pass: there is one version. A later version states its own rule,
  with the owner (section 10).

### 3.7 Binary identity, the key's SHA-256 and the pin

This section is what `plugin-qualify-sync` matches a binary on. The store carries it, so the sync needs no other source:
neither the distributed JSON files nor a probe output (section 9, ruling 9).

**The item and its root.** An ITEM is what plugin-qualify-sync qualifies as a unit (`SyncItem` of its
`src/qualify-sync.ts`): one `.clap` file, or one LV2 plugin. Its INSTALL ROOT (`SyncItem.root`) is the directory the
item's files are named relative to: for a `.clap`, the directory that holds the `.clap` file; for an LV2 plugin, its
bundle. The install root is not stored and is not a search-path entry: the same record matches the same bytes under
`/usr/lib/clap`, `/usr/lib64/clap`, `/usr/local/lib/clap` and `<home>/.clap`, and under a bundle directory of any
name, so a system install and a user install find the same record.

**The per-file list** (`record_file`, `binary.files[]` of the record):

- one entry for every file the pin of the item holds, as plugin-hostd names them (`plugin-hostd --pin-files`, which
  the sync already asks: `hostdPinFiles`, `withHostdFiles`). For a `.clap`: the `.clap` file alone (9,262 of today's
  CLAP records hold exactly one). For an LV2 plugin: what plugin-hostd's pin holds, which today is the bundle's
  `manifest.ttl`, the plugin's `.ttl` files and its binary (2 to 5 files in today's records). The store keeps the list
  as it is given and holds no rule of its own about which files belong in it; the producer's is plugin-hostd's;
- the PATH of an entry is relative to the install root, as the pin writes it: `/` as the separator, no leading `/`, no
  `.` or `..` segment (`RELPATH`, section 3.2), and an LV2 name stays in the IRI form the pin keeps
  (`libSurge%20XT.so`); the store compares paths as written and never decodes them (the sync decodes a name only to
  open the file, as `digestFiles` does);
- the SHA-256 of an entry is the 64 lower-case hex digits of the file's bytes, the digest `pin.h` takes;
- the ORDER is ascending by path, compared as UTF-8 bytes, with no locale. `ord` is the place in that order. Every
  record of today is in it, and `integrityOfProbeOutput` already sorts a pin's files so. The writer refuses a list out
  of order (`files-unordered`), with a path twice (`files-duplicate`) or empty (`files-empty`), naming the file and the
  path.

**The binary path** (`record.binary_path`) is the main binary's path relative to the install root, in the same form.
It is always the path of one entry of the list (the writer refuses one that is not: `binary-not-in-files`). For a
`.clap` it is the file's own name (`Surge.clap`), whatever directory the file is in. For an LV2 plugin it is the
bundle's binary as the bundle names it (`AutoFilter.so`); a binary lilv takes from outside the bundle (a complement's,
`SyncItem.binary`) is named by the bundle's link to it, the entry `discoverSyncItems` adds to the list for it.

**The key's SHA-256** (`plugin.sha256`) is the SHA-256 of the list's entry whose path is `binary_path`: the main
binary's. Fixed, so it can be recomputed from the list alone:

1. take the list in the order above;
2. take the entry whose path equals `binary_path`; there is exactly one (paths are unique);
3. the key's SHA-256 is that entry's SHA-256.

A list of one file therefore reduces to that file's own SHA-256 (every CLAP key of today), and an LV2 bundle reduces to
its binary's, as `binary.sha256` is today (all 3,691 LV2 records hold it among their entries). The other entries do not
change the key: they are the pin's match (below). The writer refuses a record whose key is not that value
(`key-not-the-binary`), and `plugin-qualification-db check` verifies it for every record of both layers
(section 6). No hash over the whole list is the key, because that would give each of today's 2,278 plugins a new key,
and with it every record file name, descriptor name and stem that carries the key's first 12 digits; the whole list is
matched instead, by the pin.

**The pin** is the key plus a per-file hash match, and no probe bytes:

- an installed item MATCHES a stored record when (1) the formats are the same and the plugin is: for LV2 the same uri
  (`plugin.uri`), for a `.clap` the same `binary_path` and the same plugin id (`plugin.uri` is the CLAP id); (2) the
  item's files are exactly the record's list, the same paths and, hashed on this machine (`digestFiles`, which skips
  rereading a file whose size, modification time and inode are unchanged), the same SHA-256 for every one, none
  missing and none beside them. Then the key is the installed binary's, by the rule above. The match is decided on
  the hashes alone: the record's name, its set, its host class and the path it was measured at never decide it. This
  is today's rule of `matchDistributed` ("every file the record names hashes, here, as it did where it was
  measured"), with two changes: the lookup is by `binary_path` and not by the absolute path the measuring machine had,
  so a record measured under `/usr/lib64/clap` was never found for the same file under `/usr/lib/clap`; and a file the item holds that
  the list lacks is a binary that differs (today only the listed files are checked);
- the PIN a match gives plugin-hostd is built from the record: hostd's uri for the item as it is installed here
  (`clapPinUri` of the local path and the id, or the LV2 uri), the list (replaced by plugin-hostd's own list when it
  names one, as `withHostdFiles` does), the layout (`layout_scheme`, `layout_sha256`) and the version
  (`tested_version`), when the record holds them. A record with `unpinnable` set or no layout gives no whole pin: the
  plugin is pinned on its first add, and the log says why, as today;
- the pin REPLACES `probe.sha256` for what the sync does with it. Today `probe.sha256` is the hash of the probe
  output's bytes, and three things read those bytes: `applyDistributed` (it copies the probe output beside the record
  and checks the bytes against `probe.sha256`), `rejudgeRecord` (it refuses a probe output whose bytes differ), and the
  pin itself (`integrityOfProbeOutput(output)` takes the files and the layout from the probe output). After the switch
  nothing matches on, checks against or builds a pin from `probe.sha256` or the probe output. The columns
  `probe_file`, `probe_sha256` and `probe_bytes` stay as evidence of which output the figures came from (section 9,
  ruling 1), and no consumer reads them to decide anything;
- the pin set's OWNER is plugin-hostd. The match is exact set equality on the list plugin-hostd's `--pin-files` names,
  so if plugin-hostd changes which files a pin holds (a preset file, another `.ttl`), the list of every stored LV2
  record differs from what its bundle's pin now holds, no record matches, and every LV2 plugin is qualified again:
  that change is a requalification of everything, and plugin-hostd's change says so. A list with one file more or one
  file fewer than the installed pin does not match, whatever else agrees;
- the pin has no probe bytes: the store holds none (section 9, ruling 1), the sync copies none beside the store, and
  the reader (section 6) hands the list, the layout and the version, which are all the pin takes.

**Records of today: one rewrite, no conversion.** 9,262 CLAP record files of `records/` hold an absolute `binary.path`
(`/usr/lib64/clap/...` 8,100, `/usr/lib/clap/...` 1,160, `/usr/local/lib/...` 2); the 3,691 LV2 files hold the relative
form already. `records/` is REWRITTEN ONCE, in the change that lands this amendment's code: a commit of its own that
sets each CLAP file's `binary.path` to the file's own name (its single list entry's path) and adds the fields of
section 6.2 that the probe outputs beside the records hold (`hostExtensions`), and nothing else. No file name changes
and no key changes. After that commit:

- the builder (`tools/records-db.py`) and the writer (`put`) REFUSE an absolute `binary.path` by name,
  `path-absolute`, naming the file and the path, and write nothing. Neither makes a path relative, on any run, for any
  caller: the sync writes relative paths itself, and a record of the old form is a refused record;
- `tools/check-records.py`, the repository's gate on the text, refuses the same, so no record of the old form can be
  added to `records/` again;
- the list of every record is in the order above.

## 4. Merge semantics

- **Per whole record.** A reader's result is one record at one cell. The SHADOW KEY is (`sha256`, `format`, `uri`,
  `offer`, `host_class`). When the user layer holds a record for a shadow key, that user record shadows EVERY base
  record of the key, at every cell, including cells the user record does not hold: the results for the key are the user
  record's cells only, every field of them from the user record. When the user layer holds none, the results are the
  base records' cells. Why whole: a record's verdicts, figures and probe come from one run. A field taken from the
  base beside fields from the user's run would be a combination nobody measured; a NULL in a user record (a figure not
  measured) means "not measured here", never "take the base's".
- **User first, base never overwritten.** The base file is read only and immutable. The user layer is a separate file;
  nothing is ever written to the base by a reader or by the user writer.
- **No tombstone.** A user cannot hide a base record except by measuring the same key, which shadows it. Removing a
  user record brings the base records back. Hiding without measuring would need a new word and a new
  rule; nothing asks for it today.
- **Conflicts.** Within one layer, the `claim` primary key allows one record per key, offer, class and cell, and a layer
  answers for a cell with the record that claims it: `pqdb_each` (and so `query` and every reader on it, plugin-hostd's
  among them), the files and verdicts of a result, and `pqdb_counts` read claimed records only; a cell of a record
  that does not claim it is no result, and a record that claims no cell is not counted.
- **Two tiers at one cell: the reference tier answers** (ruling 2026-11-20). In the base, a set of the reference tier
  (`record_set.tier` `reference`: measured with real-time priority) and a set of another tier (`provisional`, measured
  without it) may hold one key, offer and class at one cell: the x86-64 sets `fedora44-rt-<rate>-<quantum>` beside
  `fedora44-<rate>-<quantum>`. The migration gives the claim to the record of the reference tier, whichever set comes
  first in byte order, and keeps the other record whole in the base, without the claim at that cell. So every read
  answers with the reference tier's record; nothing is dropped and no record changes. The rule lives in the claim the
  base build writes, and the reader follows the claim (the query of `pqdb_each` joins `claim` on its primary key); no
  column is added. A claim at one key and cell from two tiers neither of which is `reference` is refused
  (`claim-duplicate`), naming both files.
- **One tier at one cell: the set measured later answers** (ruling 2026-11-20). Two sets of one tier may hold one key,
  offer and class at one cell: the rpi5 set `zynthian-vangelis`, measured 2026-11-06 over its whole grid, beside
  `zynthian-vangelis-48000-256` and `-96000-256`, samplv1 and drumkv1 measured again on 2026-11-08. The migration gives
  the claim to the record of the set whose provenance `measured` (`record_set.measured`, `YYYY-MM-DD`) is later,
  whichever set comes first in byte order, and keeps the other record whole without the claim; every read answers
  with the newer record. An equal `measured` is refused (`claim-duplicate`, "measured on one date", naming both
  files), and a contending set whose `measured` is not a date is refused (`claim-undated`); neither is guessed. No
  column is added. In the user layer, a newer
  user record for a shadow key replaces the user's earlier record for that key, whole, in one transaction, even when it
  holds fewer cells. Decided (#17): a newer user record shadows the whole base record (the user-first merge), and the
  base is never deleted. Across layers there is no conflict: the user's record wins and each result says its `layer`.
- A different SHA-256 is a different plugin: a user record for other bytes never shadows a base record.

## 5. Migration (change 2)

- **Input.** `records/<class>/<set>/*.qualification.json` and `records/<class>/<set>/provenance.json`, as section 3.5
  maps them, for the classes of one architecture (`packaging/arch-classes`, the same selection as
  `tools/sets.py install`). The probe outputs are read only to check that each record's `probe.sha256` and
  `probe.bytes` match its file; a mismatch is refused by name. The writer also applies section 3.7 to every record:
  `binary_path` relative (an absolute one is refused, `path-absolute`; `records/` is rewritten once, section 3.7), the
  list in order, the key's SHA-256 the binary's entry; a record that breaks it is refused by the name given there.
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
- **`built_from`, the commit.** In a git checkout the tool takes `git rev-parse HEAD`. A source tarball (the `.orig`
  tarball of the deb source and the RPM's `Source0`) is made with `git archive`, and carries the file `BUILT_FROM`,
  whose content is `$Format:%H$` and which `.gitattributes` marks `export-subst`: `git archive` writes the commit into
  it. The tool takes `--built-from-file BUILT_FROM` from `debian/rules` and the spec file. A tree with neither a `.git`
  nor a substituted `BUILT_FROM` (the file still holding `$Format:%H$`) is refused (`built-from-unknown`); the commit is
  never guessed and never left NULL in the base. In a git checkout `BUILT_FROM` still holds the placeholder: the tool
  then takes `git rev-parse HEAD`, and outside one it refuses.
- **Domain floors.** `--min-domain <domain>=<version>` (repeatable) refuses a domain whose `info.version` is lower
  (`qualification-db.domain-too-old`, naming the domain and both versions). The spec names no floor value: the
  package's floors are its Build-Depends on the contract packages (section 7), which is what guarantees the
  `info.version` the words need, so the packaging does not pass the flag; it is for a caller with a contract directory
  of its own.
- **The round-trip proof** (`tools/test_records_db.py`, `unittest` like the repository's other tools):
  - build the base database of every set of `records/` (both classes, not one architecture);
  - for every record file, export the record from the database and compare it with the parsed file as JSON values,
    every field, after removing the sentence paths of section 3.5 from the file's value; numbers compare by value
    (a REAL 40.0 equals 40);
  - the package fields of every migrated record read back as NULL, and every optional field absent in a file reads
    back absent;
  - counts are equal: record files per set = `record` rows per set, and for every array of section 3.5 the number of
    elements across the files = the rows of its table; sets = `record_set` rows; distinct (format, SHA-256, id) =
    `plugin` rows (2,278 today);
  - an INDEPENDENT check, which does not use the module's mapping: `tools/testdata/field-columns.tsv`, written by hand
    from the table of section 3.5, one line per leaf (`<JSON path>\t<table>.<column>`). For fixture records chosen to
    hold every leaf at least once, the test reads each path's value from the JSON and the column's value with its own
    SQL, and compares them. A mapping that is wrong in both directions (two columns swapped by the writer and the
    exporter alike) passes the round trip and fails this check.
- **The old package and files.** Changes 1 to 3 remove nothing: `plugin-qualification-records` keeps installing every
  `<class>/<set>/` file byte for byte, and adds `qualification.sqlite` beside them, until the consumer switch, later in
  this pass, stops installing them. The package's name, its
  Provides, Replaces and Breaks, and its dependencies stay as they are. The switch is one change, made in the same
  release pass as this one, before the console's 0.2.1 release (section 9, ruling 8). That change, the consumer switch,
  is the one that stops installing the JSON files: in the same change the consumers read the database, the sync's
  distributed JSON reader is removed with no fallback to it, and the package ships only `qualification.sqlite`. `records/` stays in this repository as the source the database is built
  from.

## 6. Reader API (change 3)

**Language: C**, with a command over it. The consumers that read records today are:

- plugin-hostd (C): `src/qualcost.c` reads the cost, latency and memory figures of `qualification_dir`'s records for
  its planner and its estimate verb. It is a daemon; it must not start a process to read a figure.
- plugin-qualify-sync (TypeScript, Node.js): today `src/distributed-records.ts` reads the shipped records of its class
  and cell, and its own records live as JSON files in `qualification_dir`. The store replaces both (section 9, ruling
  9): it reads the database the way it already runs plugin-db's command for plugin-db's store (`src/plugin-db-cli.ts`),
  through `plugin-qualification-db` (`query --json`, `query --json --records`, `counts --json`), a few calls per
  run (section 6.1), and it WRITES its records through this repository's writer module (section 6.1). Node.js 18, the
  package's floor, and Debian trixie's Node.js have no built-in SQLite (section 9, ruling 4).
- The console does not read records; it reads what plugin-hostd and plugin-db answer.

One implementation, in C, so the two consumers cannot answer differently.

**Header** `<plugin-qualification-db/pqdb.h>`, library `libplugin-qualification-db.so.0`, pkg-config
`plugin-qualification-db`, whose `schema` variable names the installed DDL (`<datadir>/plugin-qualification-db/qualification.sql`, section 2). Errors are strings by name: `pqdb_error.code` and `pqdb_code(status)` give `qualification-db.*`; the header defines no numeric error constants, the names are the contract. `pqdb_verdicts` walks every verdict of a result's record (the command prints them):

```c
typedef struct pqdb pqdb;                          /* an opened base and user layer; opaque */
typedef enum { PQDB_SCOPE_USER, PQDB_SCOPE_SYSTEM } pqdb_scope;

typedef struct { const char *code; char message[256]; } pqdb_error;  /* names the code, the file and the reason */

/* 0, or a PQDB_ERR_* value. Production: the installed base and the scope's user layer; no path, no environment. */
int  pqdb_open(pqdb_scope scope, pqdb **out, pqdb_error *err);
/* TEST AND COMMAND ONLY: the base, the user layer (NULL: none) and the contract directory, given. */
int  pqdb_open_at(const char *base, const char *user, const char *contract_dir, pqdb **out, pqdb_error *err);
/* 1 when the open found no base file: the base layer is empty, every answer is the user layer's alone (section 6). */
int  pqdb_base_absent(const pqdb *db);
void pqdb_close(pqdb *db);
const char *pqdb_code(int status);                 /* "qualification-db.unreadable" ... */

/* every field optional: a string of NULL, and a rate or quantum of -1, is "any"; 0 is not. Start from PQDB_QUERY_ANY. */
#define PQDB_QUERY_ANY { NULL, NULL, NULL, NULL, NULL, -1, -1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL }
typedef struct {
    const char *sha256, *format, *uri, *offer, *host_class;
    int rate, quantum;
    const char *pkg_format, *pkg_name, *pkg_version, *pkg_release, *pkg_distro, *pkg_arch;
    const char *binary_path;                        /* section 3.7: the main binary's path below its install root, as stored */
    const char *layer;                              /* "user": the scope's user layer only, no shadowing; "base": the base only; NULL: both, merged (section 4) */
} pqdb_query;

typedef struct {
    const char *layer;                              /* "user" or "base" */
    const char *sha256, *format, *uri, *offer, *host_class, *set;   /* set: NULL in the user layer */
    const char *pkg_format, *pkg_name, *pkg_version, *pkg_release, *pkg_distro, *pkg_arch;  /* NULL: not known */
    const char *binary_path;                        /* the record's, section 3.7 */
    const char *layout_scheme, *layout_sha256;      /* NULL: the record holds no layout */
    const char *tested_version;                     /* NULL: not known */
    int unpinnable;                                 /* 1 when the record's binary is unpinnable, else 0 */
    int rate, quantum;
    const char *outcome;                            /* the cell's outcome word */
    double cost_median_ns, cost_p_ns;  int cost_p; int has_cost;
    long latency_frames; int has_latency;           /* measured frames, else declared */
    long mem_first_kb, mem_per_instance_kb; int has_memory;
} pqdb_result;

/* Calls each(result, ctx) for every result the query matches, user first, a base result only when the user layer has
   no record of its shadow key (section 4), in key order. A non-zero return of each stops the walk and is returned. */
int  pqdb_each(const pqdb *db, const pqdb_query *q, int (*each)(const pqdb_result *, void *), void *ctx);

/* The per-file list of a result's record (section 3.7), in its order, as each(path, sha256, ctx); the strings are valid
   until each returns. The reader hashes nothing: the caller compares the list with what it hashed. A non-zero return
   of each stops the walk and is returned. 0, or a refusal status. */
int  pqdb_files(const pqdb *db, const pqdb_result *r, int (*each)(const char *path, const char *sha256, void *), void *ctx);

/* The record of a result as one JSON document of `plugin-qualify.qualification-record/1`, as section 5's exporter writes it
   (the sentences of section 3.5 absent), in memory the caller frees with free(). */
int  pqdb_record_json(const pqdb *db, const pqdb_result *r, char **json, pqdb_error *err);

/* What a layer holds per plugin (a plugin: a format and a uri), by format: each(format, plugins, offered, not_offered, ctx).
   `layer` is "user", "base" or NULL (both, merged as section 4). A plugin is offered when any of its records has a
   `tier_offered` row. The strings are valid until each returns; a non-zero return stops the walk and is returned. */
int  pqdb_counts(const pqdb *db, const char *layer, int (*each)(const char *format, long plugins, long offered, long not_offered, void *), void *ctx);
const char *pqdb_message(const pqdb *db);     /* the last refusal of pqdb_each: layer, record, column; NULL if none */
int  pqdb_number(double value, char *out, size_t n);   /* a number as JSON.stringify writes it, C locale; -1: not finite or too long */

/* The verdict of a result's record under one host profile: rating word, measured, qualified, deciding (NULL: none). */
typedef struct { const char *rating, *deciding; int measured, qualified; } pqdb_verdict;
int  pqdb_verdict_of(const pqdb *db, const pqdb_result *r, const char *host, pqdb_verdict *out);
/* Every verdict of the result's record, in the record's order. */
int  pqdb_verdicts(const pqdb *db, const pqdb_result *r, int (*each)(const char *host, const pqdb_verdict *, void *), void *ctx);
```

- **From an installed package to its results:** `pqdb_each` with the `pkg_*` fields of the query set (format, name,
  version, release, distro, arch, as the package manager states them). Only stored values match: a record whose
  package fields are NULL, every migrated record today, is never returned for a package query.
- **From an installed binary to its record** (section 3.7): `pqdb_each` with `format` and `uri` (LV2), or `format`,
  `binary_path` and `uri` (a `.clap`: the CLAP id), then `pqdb_files` of each result, compared with the files the caller
  hashed. The merged answer shadows whole records (section 4), so the caller compares the records it gets; a result
  whose list does not equal what is installed is not the installed binary's.
- **Numbers and non-finite values.** Every reader path (`pqdb_each`, `pqdb_record_json`, the command's `query --json`)
  writes a REAL through `pqdb_number`: the layout of `JSON.stringify`, under the C locale whatever the program's. A
  non-finite REAL is refused as `qualification-db.not-a-store` by every path; `pqdb_message` names the layer, the
  record and the column of `pqdb_each`'s last refusal, and the command prints the code and message and exits 1.
- **Every cell of a record** is one result; `pqdb_files` and `pqdb_record_json` give the same answer for each of a
  record's results. `pqdb_record_json` is the exporter of section 5 in C: its output equals the Python exporter's, byte
  for byte after JSON normalisation, for every record of the fixtures (section 8, change 3).
- **Pointers** in a result are valid until the callback returns; a caller copies what it keeps.
- **Refused, by name** (`pqdb_code` gives the string; each refusal names the file):
  - an ABSENT base is not a refusal (ruling of 2026-11-20): the store has no base records until the records migration
    ships, and the sync writes the user and system layers from day one, so a base file that does not exist is a valid
    EMPTY base layer, as an absent user layer is. Only `ENOENT` is absent. `pqdb_base_absent(db)` is 1 for it, and the
    command's answers say it (below); nothing fakes a base, and no layer or record is invented. `qualification-db.absent`
    is retired from the code list: nothing refuses with it;
  - `qualification-db.unreadable`: the base or the user layer exists, or its path cannot be walked (`ENOTDIR`, a
    path through a file, is a wrong path, not an absent base; `EACCES` likewise), and SQLite cannot open or read it: a
    directory, a file with no read permission, a file that is no SQLite database (a short or corrupt one);
  - `qualification-db.not-a-store`: `user_version` 0, or no `store_info` row, or a `user_layer` that is not the
    file's (a user file opened as the base), or a REAL column of a record holding a value that is not finite (no
    JSON number writes it; the message names the layer, the record and the column);
  - `qualification-db.schema-mismatch`: the base and the user layer are at different `user_version`s;
  - `qualification-db.schema-other`: a file's `user_version` is not the reader's `PQDB_SCHEMA_VERSION`;
  - `qualification-db.layer-unknown`: a query's `layer` is not `user` or `base`;
  - `qualification-db.domain-too-old`: an installed domain's `info.version` is below the `store_domain.version` the
    file was checked against;
  - `qualification-db.word-unknown`: a word of a `word_check` column is in none of its items of the installed
    domains; the message names the table, the column and the word;
  - `qualification-db.key-mismatch` (the command's `check` only; `pqdb_open` does not scan every record): a record whose
    `plugin.sha256` is not the SHA-256 of its list's entry at its `binary_path` (section 3.7); the message names the
    key and the path;
  - `qualification-db.hot-journal`: the user layer has a hot journal (its writer stopped inside a transaction). A
    read-only reader cannot roll it back (SQLite answers `SQLITE_READONLY_ROLLBACK`), so it refuses, names the file
    and the journal, and changes nothing; the next write by the writer rolls it back;
  - `qualification-db.busy`: the user layer stayed locked by its writer past the busy timeout (250 ms);
  - the loader's own codes (`contract.dir.absent`, `contract.file.invalid`, `contract.package.too-old` and the rest),
    passed through when the domain cannot be opened.
- **Word check at open.** `pqdb_open` opens each domain of `store_domain` through omx-contract's loader
  (`omx_domain_open(domain, floor)`), then for each column of `word_check` reads its distinct words and looks each up
  in the column's items (`omx_domain_word`). It is done once, at open; no lookup checks a word again. This pass the
  `hosting` row and its columns are skipped (section 3.4, the hosting exception); `hosting-skip-ends` fails once a
  `hosting` domain exists and the skip is still there.
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
    [--pkg-format .. --pkg-name .. --pkg-version .. --pkg-release .. --pkg-distro .. --pkg-arch ..]
    [--binary-path ..] [--layer user|base] --json`: one JSON object per line per result, words and numbers only. Its
    keys, in this order: `layer`, `sha256`, `format`, `uri`, `offer`, `host_class`, `set`, `pkg_format`, `pkg_name`,
    `pkg_version`, `pkg_release`, `pkg_distro`, `pkg_arch`, `binary_path` (string), `layout_scheme`, `layout_sha256`,
    `tested_version` (string or `null`), `unpinnable` (0 or 1), `files`, `rate`, `quantum`, `outcome`, the cost,
    latency and memory keys of `pqdb_result` as today, and `verdicts`: an array, in the record's order, of
    `{"host": ..., "rating": ..., "measured": 0|1, "qualified": 0|1, "deciding": ...}`, the fields of `pqdb_verdict`
    (`deciding` a string or `null`). `files` is the record's list in its order: an
    array of `{"path": "...", "sha256": "..."}`, never empty. No other key; an absent figure is `null`, as today;
  - `query ... --json --records`: one JSON object per line per RECORD (the results of one record are one line):
    `{"layer": ..., "sha256": ..., "format": ..., "uri": ..., "offer": ..., "host_class": ..., "record": <the record of
    pqdb_record_json>}`. The same filters apply; `--rate` and `--quantum` are refused with `--records` (a usage error,
    exit 2), because a record is not a cell;
  - `counts [--layer user|base] --json`: one JSON object per line per format, in format order:
    `{"format": "clap", "plugins": 248, "offered": 224, "not_offered": 24}`;
  - an absent base is told, never silent, and stdout stays records only (a reader parses each line as a record, and a
    box with no base must not meet a line a box with a base never prints): when `pqdb_base_absent` is 1, `query --json`
    and `counts --json` exit 0, print the user layer's lines alone (none when it has none) and write ONE line to
    stderr, `plugin-qualification-db: base-absent: <path>: the base layer is empty`; a present base writes nothing to
    stderr;
  - `check`: opens both layers, verifies section 3.7's key rule for every record of both, and prints `ok` (`ok base-absent` when the base is absent), or the code and message; exit 0, or 1 with the code;
  - `--base`, `--user`, `--contract-dir` and their variables, as section 2 says; and `--scope user|system` (default
    `user`), which opens the production places of that scope (`pqdb_open`) when neither `--base` nor `--user` is given.
    `--scope` with either of them is a usage error. Exit 2 on a usage error.

### 6.1 plugin-qualify-sync on the store (the consumer switch)

The store REPLACES the distributed JSON layer and the JSON files of `qualification_dir`. The switch is whole
(section 9, ruling 9): after it the sync reads no `<dir>/<host class>/<set>/` file and no `*.qualification.json`,
`*.probe.json` or `*.unmeasured.json` of a `qualification_dir`; no function falls back to them, and none reads the
store and a directory together (section 10).

**Scope.** `plugin-qualify-sync --system` uses `PQDB_SCOPE_SYSTEM` (`--scope system` of the command, the writer's
`--scope system`); without it, the user scope (section 2). The settings `qualification_dir` and `distributed_dir` are
removed with no alias: the places are section 2's.

**The writer.** The sync is the WRITER of its own records, and the only writer of the scope's user layer. It writes
through this repository's writer module (`tools/qualification_db.py`, the module that builds the base, section 5),
installed with a command, `plugin-qualification-db-write` (section 7), which it runs the way it runs plugin-db's and
the reader's commands:

- `put --scope user|system --offer .. --host-class ..`: one record, the JSON document of
  `plugin-qualify.qualification-record/1` on standard input, in one transaction. The offer and the host class are
  arguments, as `delete` takes them, because the record document carries neither; its `probe.file` must be
  `<name>.<offer>.probe.json` for that offer, or it is refused as `file-name`. It creates the layer from the installed DDL when the file is absent (section 2), checks
  every word against the installed domains, applies section 3.7 (`path-absolute`, `binary-not-in-files`, `key-not-the-binary`,
  `files-unordered`, `files-duplicate`, `files-empty`) and replaces, whole, the layer's record of the same shadow key
  (section 4). A refusal names the code, the path and the word, and writes nothing;
- `delete --scope user|system --sha256 .. --format .. --uri .. --offer .. --host-class ..`: the layer's record of that
  shadow key, in one transaction; a key the layer does not hold is not an error. Nothing deletes from the base.

The record document is the interchange between the sync's judge and the writer; it is not a layer, nothing keeps it,
and nothing reads it back from a file.

**What each function reads and writes.** Names are those of plugin-qualify's `src` today (`qualify-sync.ts`,
`qualify-rejudge.ts`, `distributed-records.ts`, `qualification-record.ts`):

| function | reads today | reads and writes after |
| --- | --- | --- |
| `readDistributedLayer`, `matchDistributed` | `<dir>/<host class>/<set>/*.qualification.json` by `resolve(binary.path)` (CLAP) or the LV2 uri | removed. The match is `pqdb_each` / `query --json` with the item's `format`, `uri` (and `binary_path` for a `.clap`) and `host_class`, then the per-file comparison of section 3.7 on each result's `files`, then the cells and the host's verdict of the results as `matchDistributed` takes them (`syncCells`, `verdicts`) |
| `applyDistributed`, `takeDistributed` | copies the record and its probe output into `qualification_dir`, after `rejudgeRecord` of the probe bytes | the base record is read whole (`query --json --records`), judged again under today's rules, and written by `put` into the scope's layer: no copy of a probe output and no `provenance` block (the user layer has no set, section 3.3) |
| `writeQualification`, `judgedPlugins` | writes `<stem>.<offer>.qualification.json` and the probe copy into `qualification_dir` | `put` of the record the run judged, its `binary_path` and list as section 3.7 gives them; the probe output is not kept |
| `writeUnmeasuredRecord` | writes `<stem>.unmeasured.json` | removed: it has no table, it holds no figure, and the plugin's outcome, code and detail are in the sync state (`SyncPlugin`) |
| `rejudgeState` (`qualify-rejudge`) | `readdirSync(qualification_dir)` for `*.qualification.json` and, per record, its probe output (`rejudgeRecord`, which refuses bytes whose SHA-256 differs from `probe.sha256`) | every record of the scope's USER layer, by `query --json --records --layer user`, one line a record; no directory and no probe output. It judges again from the record's rows alone, by the table of section 6.2 (every field `judgeProbeOutput`, `rejudgeProfiles` and `runsOwed` read, and its column), and `put`s each record that changed. A record whose rows lack a figure the judge needs owes `figures-unreadable`, as a record whose probe output does not read does today. The changed-bytes test (`changedStems`) compares the state's entry with the record's key and list. Base records are not re-judged in place: the base is read only |
| `memoryPass`, `isolatedPass`, `poolPass`, the adapter pass | each reads the record of a state entry by file name and writes it whole | each reads the record of the entry's shadow key (`query --json --records --layer user`) and `put`s it extended |
| `pruneStale` | `readdirSync(qualification_dir)` for the stems of records and `readdirSync(descriptor_dir)` | the user layer's records as the reader lists them (`query --json --layer user`, deduplicated by shadow key), and the descriptor directory as today. A record is stale when the state before holds its key and the state after does not, or when its `uri` is a kept plugin's and its `sha256` is not one the state after keeps (the other bytes of a kept plugin). A stale record is removed by `delete`; a record another plugin of the state still names, two copies of one binary, is kept. The descriptor half is unchanged: a descriptor `<id>@<version>-<first 12 digits of the key>.json` is dropped by its id and those 12 digits, as `idAndHash` does. It returns the shadow keys removed, and the descriptor files removed, to log |
| `pluginCounts` | `readdirSync(qualification_dir)`, parses each `*.qualification.json` for `plugin.format`, `plugin.id` and `tiers.offeredOn` | `counts --layer user --json` (system scope: the system layer, the sync's own records). A plugin is offered when any record of it has a `tier_offered` row, as `offeredOn` non-empty is today; the line `pluginCountsLine` prints is unchanged |
| `adjust` (`adjust-cli`) | `--qualification-dir <dir>`: every `*.qualification.json` there | the records of the scope through the reader (`query --json --records`, the user layer over the base, `--scope user\|system`); `--qualification-dir` is removed with no alias, and no file is read. History is keyed by the main binary's absolute path: adjust joins the INSTALL ROOT of the installed item that holds the record's key (`SyncItem.root`, from plugin-db's list, as the sync finds it; section 3.7) with `binary_path`. The root is never stored and never an argument; a record whose key no installed item holds is not adjusted, under a code plugin-qualify names |
| `judge` (`judge-cli`) | `--qualification-dir <dir>`: where the judged record and the probe copy go | `put` of the judged record through the writer (`--scope user\|system`); `--qualification-dir` is removed with no alias, and no probe copy is written (section 3.7: the store keeps no probe bytes) |
| `checkStderrKept` (`refused-stderr-kept`) | every `*.qualification.json` of a directory, refused rows only, the probe copy's `logs[]` byte counts and SHA-256, and the children's stderr copies | removed: it checked the probe copy and the stderr copies, and after the switch neither exists (the store keeps no probe bytes, section 9 ruling 1, and the sync writes no copy). Nothing replaces it; a refused record keeps its outcome, reason and `probe_end` rows |
| `judged-layer` (`judged-layer`) | `<record.qualification.json>`, a file argument | the record of a shadow key (`--sha256 --format --uri --offer --host-class`, `--layer` optional) through the reader (`query --json --records`); no file argument |
| the distributed records' documentation (`distributed-records`) | describes the copy of the distributed records into `qualification_dir` | describes the base and the user layer of this section; no copy is described |

**What does not move.** The measuring run's output (`plugin-qualify --out <dir>`) and this repository's `records/`
stay record documents in a directory: `records/` is the corpus the base is built from (section 5), reviewed and
versioned as JSON, and `--out` is how a measuring pass adds to it. The store replaces what a DEVICE keeps (the sync's
layer and its `qualification_dir`), not the corpus; the base is built from `records/` and nothing builds `records/` from
a store.

**The state.** `SyncPlugin.record` is the shadow key of the record (`sha256`, `format`, `uri`, `offer`,
`host_class`), not a file path, and `SYNC_STATE_SCHEMA` becomes `plugin-qualify.sync-state/2`. A state of the older
schema is moved aside as `readSyncState` already moves an unreadable one, and every plugin is qualified again: no
conversion. The records of an older `qualification_dir` are not read, imported or removed by the sync (section 9).

### 6.2 Rejudge from rows: what the judge reads, and where the store holds it

`qualify-rejudge` judges from the store's rows alone. Probe bytes are never kept beside the store (section 9, ruling 11),
so every field the judge reads has a column, and a field with none is added. Today `rejudgeRecord` of plugin-qualify's
`src/qualify-rejudge.ts` hands the whole probe output to `judgeProbeOutput` (`src/probe-judge.ts`), to `rejudgeProfiles`
and to `runsOwed`. This table lists EVERY probe-output field those three, and what they call, read. "Reads" names the
function that does; a field the table says nothing decides is carried into the judge's documents and read by no reason.

| probe-output field | read by | store column or rows |
| --- | --- | --- |
| `run.outcome` | `failedOutcome` (judge, `runsOwed`) | `record.probe_outcome` |
| `run.id` | `rejudgeRecord` (`figures.runId`) | `record.run_id` |
| `plugin.format`, `plugin.id` | the judge's uri and branch, `rejudgeProfiles`, `runsOwed` | `plugin.format`, `plugin.uri` |
| `plugin.version` | the pin's `integrity` only; no reason | `record.tested_version` |
| `offer.id` | `rejudgeProfiles` (a CLAP host joins only its own offer) | `record.offer` |
| `offer.clapExtensions` | `rtSafetyDocument` (a profile is judged only against the extensions it offers; any other list reads `unknown`, `hosting.clap.extensions-not-covered`), as `hostExtensions` | NEW: `record_extension` rows, in order, and `record.host_extensions` = 1 for a CLAP record whose probe reached the offer (an empty list is data); NULL for an LV2 record and for a CLAP probe that ended before the offer, which the row judge reads as `[]`, as the probe judge reads the absent `offer.clapExtensions` today. Not stored before this amendment |
| `grid[]` (its points, in order) | every function below; `blockFrames` is the first rt point's quantum | `cell` rows in `ord`, every cell of the record (the probe's points are a subset in the same order in every record of `records/`; the cells a memory-only pass added carry a footprint and no other figure) |
| `grid[].rate`, `.quantum`, `.outcome` | `okPoints`, `cellOf`, `costOf`, `failedOutcome`, `isOutOfMemory` | `cell.rate`, `.quantum`, `.outcome` |
| `grid[].latency.declaredFrames`, `.measuredFrames` | the CLAP line's `latency`; no reason | `cell.latency_declared_frames`, `.latency_measured_frames` |
| `grid[].cost.median`, `.percentile.p`, `.percentile.value` | `gridCostReadings`, `hostingCostReasons` (only `p` = 95 counts; the core fraction is computed from `value` and `rate`) | `cell.cost_median`, `.cost_percentile_p`, `.cost_percentile_value` |
| `grid[].cost.voices.held`, `.basis`, `.capacity` | `costOf` (kept beside the cost) | `cell.voices_held`, `.voices_basis`, `.voices_capacity` |
| `grid[].cost.blocks`, `.warmupBlocks`, `.voiceCurve` | nothing | `cell.cost_blocks`, `.cost_warmup_blocks`; `voiceCurve` not stored, and not read |
| `grid[].rtSafety.interposer`, `.swept`, `.sweepApplicable`, `.blocks`, `.allocations`, `.locks`, `.syscalls` | `rtSafetyOfProbeOutput`, `rtSafetyReasons`, `processCalls` | `cell.rt_interposer`, `.rt_swept`, `.rt_sweep_applicable`, `.rt_blocks`, `.rt_allocations`, `.rt_locks`, `.rt_syscalls` |
| `grid[].rtSafety.threadViolations`, `.processErrors` | `clapRtReasons` | `cell.rt_thread_violations`, `.rt_process_errors` |
| `grid[].rtSafety.ownThreads`, `.otherThreads.allocations`, `.locks`, `.syscalls` | not read on plugin-qualify's `main`; read by the judge once plugin-qualify#119 merges (`hosting.rt-safety.own-threads` is conditional, and the other-thread counts are a figure, never the verdict) | NEW: `cell.rt_own_threads`, `.rt_other_allocations`, `.rt_other_locks`, `.rt_other_syscalls` (NULL where not taken; the three counts all or none; the record's grid carries the probe point's names for them). Records of today hold none |
| `grid[].rtSafety.events[]` | carried into the document; no reason | `cell_event` rows |
| `grid[].noteSweep.applicable`, `.dialect`, `.allocations`, `.locks`, `.syscalls` | `noteSweepOfProbeOutput`, `noteSweepReasons` | `cell.note_sweep_applicable`, `.note_sweep_dialect`, `.note_sweep_allocations`, `.note_sweep_locks`, `.note_sweep_syscalls` |
| `grid[].memory.afterInstantiateKb`, `.afterActivateKb`, `.atRestKb`, `.secondInstanceKb`, `.notesHeldKb`, `.unmeasuredReason` | `gridMemoryReadings`, `hostingMemoryReasons` (`firstInstanceKb` and `perInstanceKb` are computed from these by `memory-budget.ts`) | `cell.mem_after_instantiate_kb`, `.mem_after_activate_kb`, `.mem_at_rest_kb`, `.mem_second_instance_kb`, `.mem_notes_held_kb`, `.mem_unmeasured_reason` |
| `grid[].memory.basis`, `.notesHeld`, `.unmeasuredDetail` | nothing | `cell.mem_basis`; `notesHeld` and the sentence `unmeasuredDetail` not stored, and not read |
| `grid[].memoryLimit.bytes`, `.mechanism` | `costOf`, `memoryParams` | `cell.mem_limit_bytes`, `.mem_limit_mechanism` |
| `steps[]` (`instantiate`, `probe.non-finite-output`) | the CLAP line's `headlessOk` and `nonFinite`; no reason of the judge reads either (`clapFeatureReasons` is the descriptor path's) | not stored, and not read by a verdict |
| `binary.path`, `.sha256`, `.files`, `.layout`, `.unpinnable` | the line's `binary` and `integrity`; no reason | `record.binary_path`, `plugin.sha256`, `record_file`, `record.layout_*`, `record.unpinnable` |
| `machine.*`, `behaviour`, `tool`, `measuredAt` | nothing | stored as section 3.5 says |

What `rejudgeRecord` reads of the RECORD itself is already rows: the verdicts and their `host`, `arm`, reasons and params
(`rejudgeProfiles`, `admissionsOf`, `runsOwed`: `verdict`, `reason`, `reason_param`), the adapter pass
(`record.adapter_*`, `adapter_param`), the memory pass (`memory_run_*`, whose footprints are already in the `cell` rows),
and the tool, `measuredAt` and `rejudged_*` columns. `withMemoryRun`'s merge is therefore a no-op on rows.

A record whose rows lack a figure the judge needs (a NULL where the judge reads a figure) owes `figures-unreadable`
and is not judged again. Nothing is guessed from a missing field, with one exception that is today's behaviour, not a
guess: a CLAP record's NULL `host_extensions` reads as `[]`, as the probe judge reads an absent `offer.clapExtensions`
(`?? []`). A storage move must not change a verdict.

The grid of the judge is the record's `cell` rows in `ord` order, so `blockFrames` and the order of the interposer's
counts are the probe's. The store's proof is section 8, change 3, case 25, which compares the row judge with today's
probe judge over every record of `records/`.

## 7. Packaging

| package | ships | built how | new dependencies (floors only) |
| --- | --- | --- | --- |
| `plugin-qualification-records` (change 2) | `/usr/share/omx/qualification/qualification.sqlite` beside today's files | generated at package build by `tools/records-db.py` from `records/`, for the classes of the architecture | Build-Depends: `python3:native` (with its `sqlite3` module), `python3-jsonschema:native`, `libsqlite3-0 (>= 3.37.0)`, `plugin-hostd-contract (>= <the release carrying the `qualification` domain and MACHINE_FAMILIES>~)`, `plugin-db-contract (>= <the release publishing its formats as a domain item>~)`, `omx-clap-core-contract (>= <the release publishing the `hosting` domain>~)`, `pkg-config` and the contract directory's path (the `contractdir` variable of `libomx-domain.pc`, which the reader's Build-Depends already carry); RPM BuildRequires: `python3`, `python3-jsonschema`, `sqlite-libs >= 3.37.0`, and the same four contract floors. Run time: none |
| `libplugin-qualification-db0` (change 3) | the C library | built from `src/` | `libsqlite3-0 (>= 3.37.0)` stated explicitly (RPM: `sqlite-libs >= 3.37.0`), `libomx-domain0` at the floor its symbols file gives (`${shlibs:Depends}`), and the same three contract floors |
| `libplugin-qualification-db-dev` (change 3) | header, `.so`, `.pc` (its `schema` variable names the DDL of `plugin-qualification-db-schema`) | | `libplugin-qualification-db0 (= ${binary:Version})`, `plugin-qualification-db-schema (= ${source:Version})` |
| `plugin-qualification-db` (change 3) | the command | | `${shlibs:Depends}` |
| `plugin-qualification-db-schema` (change 3, with the writer) | the DDL, at `<datadir>/plugin-qualification-db/qualification.sql`, one copy; architecture independent | | none; `libplugin-qualification-db-dev` and `plugin-qualification-db-write` depend on it, and the `.pc`'s `schema` variable names its file |
| `plugin-qualification-db-write` (change 3, with the writer) | `tools/qualification_db.py` and the command `plugin-qualification-db-write` (`put`, `delete`, section 6.1), the module that builds the base | | `python3`, `python3-jsonschema`, `libsqlite3-0 (>= 3.37.0)`, the three contract floors, `plugin-qualification-db-schema (= ${source:Version})`; RPM: the same names |

**Generated, not committed.** Today's records are text (JSON, 248 MB unpacked), reviewed as text and never rewritten.
A committed database would be a second copy of them that a diff cannot show and that can drift from `records/`.
Generating it at build from the text keeps one source; the build is cheap (one pass over the files) and its output is
held by the round-trip test. `sets.py check` and `tools/check-records.py` stay the gate on the text.

**SQLite floor.** 3.37.0 is the first SQLite with `STRICT` tables, which every table of section 3.3 is. It is stated
as an explicit floor in both formats, at build and at run time: `libsqlite3-0 (>= 3.37.0)` and `sqlite-libs >= 3.37.0`.

No version ceiling is added anywhere.

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
8. **Store info.** `user_version` = `PQDB_SCHEMA_VERSION`, `store_info.user_layer` = 0, one `store_domain` row per
   domain at its installed `info.version` (`hosting` at the installed omx-clap-core contract package's version, this
   pass), and a `word_check` row for every word column of section 3.4. Fails when any
   is missing, a word column has no item, or the pragma is not set last.
9. **Refusals leave nothing.** An absent contract directory (`contract.dir.absent`), a probe file whose SHA-256 differs
   from the record's, an empty object, and a second claim on one key and cell from two sets of one tier each refuse by
   name and leave no output file; so do two sets of one tier measured on one date at one key and cell
   (`claim-duplicate`), and such a set without a date (`claim-undated`). A reference-tier set and a provisional set at
   one key and cell give the claim to the reference record, and two sets of one tier to the one measured later, in
   either byte order of the sets (section 4). Fails when a partial file is left at `--out`.
10. **Key constraints.** A record with a 63-character SHA-256 or a format `vst3` is refused by the schema. Fails when
    the `CHECK`s are dropped.
11. **Package contents.** The built `plugin-qualification-records` (deb and rpm) holds `qualification.sqlite` and every
    file of today's sets, byte for byte equal to `records/`. Fails when a file is dropped or rewritten.
12. **`built_from` from a tarball.** A build from a `git archive` tarball of a fixture commit gives `built_from` =
    that commit; a build from a copied tree with an unsubstituted `BUILT_FROM` and no `.git` is refused as
    `built-from-unknown`. Fails when the tool falls back to NULL or to a date.
13. **Independent field check.** `field-columns.tsv` against the fixtures, path by path. Fails when the writer and the
    exporter swap `cell.mem_first_instance_kb` and `cell.mem_per_instance_kb` together (sabotage), which the round
    trip alone does not see.
14. **Claim tied to its record and cell.** Inserting a `claim` whose offer, class or plugin differs from its record's,
    or whose rate and quantum are no cell of its record, is refused by the foreign keys. Fails when the composite
    foreign keys are dropped.
15. **`mem_unmeasured_reason` checked.** A fixture cell with `memory.unmeasuredReason: "limit-exceeded"` (a word of
    `QUALIFICATION_RESOURCE_UNMEASURED_REASONS`, not of `QUALIFICATION_MEASUREMENT_UNMEASURED_REASONS`) is refused as
    `word-unknown`. Fails when the column is checked against the wrong item or by shape only.
16. **Formats against plugin-db's own item.** With a fixture `plugin-db` domain whose `PLUGIN_DB_ADDRESS_FORMATS`
    holds `clap` only, an LV2 record is refused as `word-unknown`, naming `plugin.format` and `lv2`. Fails when the
    writer checks the formats against a list of its own or of the `qualification` domain.
17. **No word list in the DDL.** `schema/qualification.sql` holds no `IN (` with a quoted string, apart from the SQLite
    type names of `typeof(c) IN ('integer', 'real')` (the param numbers of section 3.3), which the check skips: only a
    list of words is refused. Fails when a word list is written into a `CHECK`.
18. **Fractional reason param.** A fixture reason with `params.coreFractionP95: 0.37` and another with `params.blocks: 40` read back as 0.37 and 40, the second an integer (`typeof` `integer`, `real` for the first). Fails when `reason_param.number` is `INTEGER` (the fraction is refused or rounded) or when the exporter writes 40 as 40.0.
19. **Adapter params round trip.** A fixture record with `adapter.params: {}`, one with `adapter.params: {"resp": 3, "step": "add"}`, one without `params`, and an adapter cell with `params: {"peak": 0.5}` and one with `params: {}` read back exactly, `{}` staying `{}` and absence staying absent. Fails when presence is not stored (`record.adapter_params`, `adapter_cell.params`) or a param is dropped.
20. **Binary path relative, and no conversion.** After the one-time rewrite, every CLAP record of `records/` has a relative
    `binary.path` (the file's own name) and the builder reads it as written. A fixture CLAP record whose `binary.path` is
    `/usr/lib/clap/X.clap/Contents/x86_64-linux/X.clap` is refused as `path-absolute` by the builder, by `put` and by
    `tools/check-records.py`, each naming the file and the path, and no file is written; a `binary_path` that is
    absolute, empty or holds `..` is refused by the schema. A test that diffs `records/` before and after the rewrite
    commit sees only `binary.path` and the section 6.2 fields change. Fails when any of them makes the path relative
    itself (sabotage: strip the directory in the builder), or when the `CHECK` is dropped.
21. **The key is the binary's entry.** For every record of `records/`, the test's own SQL finds
    `record_file.sha256` at `binary_path` and it equals `plugin.sha256`. A fixture LV2 record whose key is the
    SHA-256 of its first entry (`manifest.ttl`) is refused as `key-not-the-binary`; one whose `binary_path` is no
    entry is refused as `binary-not-in-files`. Fails when the writer takes the first entry or none (sabotage).
22. **The list is ordered, unique and non-empty.** A fixture list out of byte order (`b.ttl` before `a.ttl`; `Z.so`
    before `a.so`), with a path twice, empty, with an absolute path or with a `..` segment is refused by name
    (`files-unordered`, `files-duplicate`, `files-empty`, and the schema's `RELPATH`), each naming the file and the
    path, and no file is written. Fails when the writer sorts or dedupes instead of refusing (sabotage), or compares
    by locale.
23. **Order read back.** A fixture LV2 list with an IRI-form name (`libSurge%20XT.so`) reads back as written, in `ord`
    order, byte for byte. Fails when the exporter decodes a name or orders by anything but `ord`.
24. **The columns of the row judge.** A fixture CLAP record round-trips with `hostExtensions` `["clap.log", "clap.params"]`, one
    with `[]`, and an LV2 record with none; a cell with `ownThreads: 2` and `otherThreads` of three counts reads back
    exactly, one with `otherThreads` of one count only is refused by the schema, and a CLAP record without
    `hostExtensions` (a probe that ended before the offer) is stored with `host_extensions` NULL, which the row judge
    reads as `[]`; C6b holds byte-equal on all 254 such records of `records/`. Fails when presence of an empty list is lost, or the all-or-none `CHECK` is
    dropped.

### Change 3: the reader

1. **Absent base** → open succeeds, `pqdb_base_absent` is 1, the results are the user layer's alone, a `base`-layer query and `pqdb_counts` give none, no file is created; the command exits 0 with records only on stdout and the one `base-absent` line on stderr (`ok base-absent` for `check`), and a present base writes no such line. Fails when open is refused, when the base is said present, when stdout holds a line that is no record, or when a base appears. A base that exists and cannot be used is still refused by name, one arm each: a permission-denied file (skipped as root) and a directory and a short non-SQLite file (`qualification-db.unreadable`), a file at another `user_version` (`schema-other`), an empty file (`not-a-store`), a path through a file (`ENOTDIR`, `unreadable`). Fails when any of them reads as absent. The writer puts the user and the system layer with no base anywhere.
2. **Absent user layer** → open succeeds; results are the base's. Fails when an absent user file is refused or created.
3. **One schema version.** A base at `user_version` 2 (and a reader at 1) → `schema-other`; a base at 1 with a user
   layer at 2 → `schema-mismatch`, naming both files; **0** → `not-a-store`; a user file opened as the base →
   `not-a-store`. Fails when the reader accepts a range.
4. **Word not in the domain.** A fixture domain without `conditional` → `word-unknown` naming `verdict.rating` and
   `conditional`. Fails when the open skips the word check.
5. **Domain too old.** A fixture domain at `info.version` 1.0.0 against a store at 1.1.0 → `domain-too-old`.
6. **Whole-record merge.** A user record without memory figures and a base record with them, same key and cell: the
   result has `layer` `user` and `has_memory` 0. Fails under a per-field merge (sabotage: fill missing user figures
   from the base).
7. **A user record shadows the whole base record (#17).** A base record holding 48000/256 and 96000/256 and a user
   record of the same SHA-256, format, uri, offer and class holding only 48000/256: the results are the user's
   48000/256 alone; the base's 96000/256 is hidden, and the base file is unchanged. Fails when shadowing is per cell
   (sabotage: let base cells the user record does not hold through).
8. **Another key is not shadowed.** A user record for another SHA-256, offer or class leaves the base results visible.
   Fails when the shadow key drops one of its fields.
9. **Package lookup.** A user record with `rpm`, `clap-dexed`, `1.1.0`, `4.fc44`, `fc44`, `x86_64` is found by that
   package; a migrated record (all NULL) is found by no package query. Fails when NULL matches any value.
10. **Read only.** Opening and querying both layers leaves their size, mtime and directory listing unchanged (no
   `-journal`, `-wal` or `-shm` file). Fails when a layer is opened read-write.
11. **No environment in production.** The library's dynamic symbols import no `getenv` or `secure_getenv`, and
    `pqdb_open` with `PLUGIN_QUALIFICATION_DB_BASE` set to a fixture still opens the installed path. Fails when the
    library reads a variable.
12. **Busy.** A writer holding an exclusive lock on the user layer gives `qualification-db.busy` within 250 ms plus a
    margin, never a hang. Fails without a busy timeout.
13. **Figures agree with today's reader.** For every record of a fixture set, `pqdb_each` at each cell gives the cost
    median, the 95th percentile, the latency frames and the memory figures computed from the same JSON by the test's
    own reference (the rules of plugin-hostd's `qualcost.h`). Fails when a column is mapped to the wrong figure.
14. **The command.** `query --json` prints words and numbers only; `--base` and `PLUGIN_QUALIFICATION_DB_BASE` are
    honoured by the command; a usage error exits 2. Fails when the command and the library disagree on a fixture.
15. **Scopes.** With `XDG_DATA_HOME` set to a fixture directory holding a user layer, `pqdb_open(PQDB_SCOPE_USER)`
    reads the layer under the home from the password database, not the fixture's (the test runs as a user whose
    home is a fixture). `PQDB_SCOPE_SYSTEM` never opens the home's layer, and `PQDB_SCOPE_USER` never opens
    `/var/lib/omx/qualification/` (checked by the test's `open` trace, or by fixtures at both places). Fails when the
    library reads `XDG_DATA_HOME` or a scope reads the other's layer.
16. **Hot journal.** A user layer with a hot journal (a writer killed inside a transaction) → `hot-journal`, naming
    the file; the layer and its journal are unchanged afterwards. Fails when the reader opens it read-write to roll
    back, or reads it as if no journal were there.
17. **The identity fields.** For each result of a fixture set, `binary_path`, `layout_scheme`, `layout_sha256`,
    `tested_version` and `unpinnable` equal the test's own SQL read of the record, a record with no layout giving NULL
    for both layout fields and `unpinnable` 0 (1 for a record that holds it). Fails when two columns are swapped
    (sabotage: `layout_scheme` and `layout_sha256`).
18. **`pqdb_files`.** The list of a result is the record's `record_file` rows in `ord` order, paths and hashes equal to
    the test's own read; every cell of one record gives the same list; the strings are valid in the callback only. A
    non-zero return stops the walk and is returned. Fails when the order is the rowid's or the path's by a locale
    (sabotage: `ORDER BY path COLLATE NOCASE`).
19. **`binary_path` and `layer` filters.** `binary_path` returns only records of that path and is exact (`X.clap` finds no
    `Y/X.clap`, none of another case). `layer` `user` returns every user record of the filters, including one that
    shadows a base record, and none of the base; `layer` `base` returns the base record the user one shadows; NULL
    is the merged answer of section 4, unchanged. Fails when `user` applies shadowing, when `base` is empty for a
    shadowed key, or when a filter is ignored.
20. **`pqdb_counts`.** A fixture user layer of three plugins (two `clap`, one `lv2`), the first with a `default` record
    that has a `tier_offered` row and a `custom` one that has none, the second with no row, the third with one: the
    counts are clap 2 plugins, 1 offered, 1 not offered; lv2 1, 1, 0. Two records of one plugin count once, offered
    when either is. `layer` `base` and NULL count their own sets. Fails when records are counted, or a plugin with
    only an unoffered record counts as offered.
21. **`pqdb_record_json`.** For every record of a fixture set the document equals the Python exporter's, as JSON
    values, and holds none of the sentence paths of section 3.5; the caller's `free` releases it; an error gives
    `pqdb_error`. Fails when a column is missing or a number changes type (sabotage: a fraction read as an integer).
22. **The command's widened shape.** `query --json` prints exactly the keys of section 6 in that order (a test checks
    the key list), `files` a non-empty array of `path` and `sha256`, `unpinnable` 0 or 1, absent figures `null`.
    `query --json --records` prints one line per record, with the record document; with `--rate` it exits 2.
    `counts --json` prints one line per format. `--scope` with `--base` or `--user` exits 2; `--scope system` reads the
    system place and never the home's (the test's `open` trace, as 15). Fails when a key is added, dropped or
    reordered, or `--records` prints one line per cell.
23. **`check` verifies the key.** A store whose `plugin.sha256` is not the SHA-256 at its `binary_path` makes `check`
    print `qualification-db.key-mismatch`, naming the key, and exit 1; a store that holds the rule prints `ok`.
    Fails when `check` skips the comparison.
24. **Read only still.** `pqdb_files`, `pqdb_record_json`, `pqdb_counts` and `--records` leave both layers' size,
    mtime and directory listing unchanged (test 10's check). Fails when any opens a layer read-write.
25. **The row judge, from the reader.** The case C6b, run over the reader: a base built from `records/` is read through
    `pqdb_record_json` and judged; every record's verdicts, tiers and cost equal the probe judge's. Fails with the same
    sabotages as C6b, and when `pqdb_record_json` drops a cell, a column of section 6.2 or the cells' order.
26. **The reference tier answers where two tiers hold a cell.** Two fixture bases hold one plugin at 48000/256 from a
    provisional set and from a reference set, the sets in both orders, each record with its own figures, verdict,
    file list and offer, the claim on the reference record (section 4). `pqdb_each` (no filter, the key at its cell,
    the base layer by name), `query --json`, `pqdb_files` and `pqdb_verdict_of` of the result, and `pqdb_counts` answer
    with the reference record alone, in both orders. Fails when the reader reads a cell without its claim (two
    results, and in one order the provisional set's first) or counts a record that claims no cell.
27. **The newer set answers where two sets of one tier hold a cell.** Two fixture bases hold one plugin at 48000/256
    from two rpi5 sets of tier hardware, measured 2026-11-06 and 2026-11-08, the sets in both orders, the claim on
    the newer record (section 4). `pqdb_each` (no filter, the key at its cell), `query --json`, and `pqdb_files` and
    `pqdb_verdict_of` of the result answer with the newer record alone, once. Fails when the claim follows the order of
    the sets or the reader reads a cell without its claim.

### The consumer switch (red-first tests of plugin-qualify's repository)

The sync's tests belong to the sync's repository; the contract they hold is this spec's, and each fails first:

C1. **Install root does not decide.** One record, the same bytes installed under `/usr/lib/clap`, under `/usr/lib64/clap`
    and under a home's `.clap`: the sync takes the record for each. Fails when the lookup uses an absolute path.
C2. **One file differs.** An LV2 bundle with the binary of the record and a changed `.ttl`; a bundle whose pin holds one
    file MORE than the record's list; and a bundle whose pin holds one file FEWER (the list names a file the installed
    pin lacks): each is measured, not taken. Fails when only the binary is compared, or when the match is a subset
    either way.
C3. **`probe.sha256` decides nothing.** The record's `probe_sha256` altered in the store, and no probe output anywhere:
    the record is still taken, and a pin is built from the list, the layout and `tested_version`. Fails when the pin or
    the match reads the probe columns or a probe file.
C4. **The sync writes the store.** After a run in a fixture home, the user layer holds the run's records
    (`binary_path` relative, list in order, key rule held) and no `*.qualification.json`, `*.probe.json` or
    `*.unmeasured.json` exists under any directory the sync used. Fails when any file is written.
C5. **No directory is read.** With a directory of valid old `*.qualification.json` and `*.probe.json` files present, and
    with no base file (an empty base layer, section 6) the sync takes nothing from the files and writes its layer; with the
    store present, `qualify-rejudge`, `pruneStale` and `pluginCounts` give the store's answers and the open trace shows
    no read of that directory. Fails when any function falls back, or reads both.
C6. **`qualify-rejudge` on the store.** It judges the user layer's records again with no probe output on disk, `put`s only
    the records that changed, leaves the base unchanged, and owes `figures-unreadable` for a record whose rows lack a
    figure (a CLAP record without `host_extensions`; a NULL `cell.rt_syscalls` under an interposer). Fails when it reads
    `probe_file`.
C6b. **The row judge equals the probe judge, over the corpus.** For every record of `records/` (both classes), the
    verdicts, the tiers and the cost that `rejudgeRecord` gives from the store's rows (`query --json --records` of a base
    built from `records/`) are byte-equal, as the JSON text the record writes, to the ones it gives from the probe
    output beside the record (the probe outputs stay in `records/` as this test's oracle; the store holds none). The
    test names the record and the first field that differs. Sabotage, one case for each mapped column of section 6.2
    (the builder leaves one out): dropping `cell.rt_syscalls`, `cell.note_sweep_allocations`, `cell.cost_percentile_value`,
    `cell.mem_second_instance_kb`, `cell.mem_limit_bytes`, `cell.voices_held` or `record_extension` makes the test red on
    a record that reads it. Fails when any mapped column is missing from the build or the export.
C7. **`pruneStale` on the store.** A plugin gone from the state, and a kept plugin with other bytes, each lose their user
    record by `delete`; a record named by another plugin of the state, and every base record, stay; the descriptor files
    go as today. Fails when a base record is touched, or a kept key is dropped.
C8. **`pluginCounts` on the store.** The line equals the one the fixture's records give by hand, for the system layer
    under `--system` and the user layer otherwise. Fails when it counts the base's records or reads a directory.
C9. **The old settings and state are gone.** `qualification_dir` and `distributed_dir` are refused as unknown settings; a
    state of `plugin-qualify.sync-state/1` is moved aside and every plugin is qualified again. Fails when either is
    accepted or converted.

## 9. Owner rulings

Decided by the owner (2026-11-19):

1. **DECIDED: codes, not prose.** The database stores codes, presence, and the probe output's name, hash and size; not
   the prose fields of section 3.5 and not the raw probe outputs. The round trip proves every field but those, by name.
2. **DECIDED: the missing words first.** plugin-qualify adds the missing qualification words and the package words in
   one `qualification` domain minor BEFORE change 2 merges (section 3.4, precondition 1).
3. **DECIDED: a package object.** plugin-qualify's record gains a `package` object (format, name, version, release,
   distro, arch), filled at measurement time from the package manager's owner of `binary.path` (`dpkg-query -S`,
   `rpm -qf`). No back-fill: a NULL stays NULL.
4. **DECIDED: one reader.** The reader is the C library and its command `plugin-qualification-db query --json`;
   TypeScript (plugin-qualify-sync) reads through the command, so there is one implementation. Node's `node:sqlite` is
   revisited only if a measured need appears after Node 26.
5. **DECIDED: the system user layer.** The system scope's user layer is in `/var/lib/omx/qualification`
   (`qualification.sqlite`, section 2).
6. **DECIDED: formats stay plugin-db's.** `clap` and `lv2` are checked against plugin-db's own published list, never a
   copy, and never move into plugin-qualify; plugin-db publishes them as a domain item first (section 3.4,
   precondition 2).
7. **DECIDED (#17): whole-record shadowing.** A newer user record shadows the whole base record, at every cell, and the
   base is never deleted (section 4).
8. **DECIDED (2026-11-19 17:10Z): the consumer switch is in this pass.** plugin-qualify-sync, plugin-hostd and any other
   reader move to the database in one change, in the same release pass as changes 2 and 3, before the console's 0.2.1
   release. plugin-qualify's release line and plugin-hostd's wait for it and tag once, with it.

9. **DECIDED (ruling (a), 2026-11-19): the store replaces the distributed JSON layer.** `plugin-qualify-sync` switches
   fully in this pass. The store carries what the sync matches on: the binary path and the per-file SHA-256 list, the key
   being the SHA-256 of the list's entry at the binary path (section 3.7). The pin is the key plus a per-file match and
   replaces `probe.sha256` (section 3.7). The sync is the writer of its own records into the user or system layer;
   `qualify-rejudge`, `pruneStale` and `pluginCounts` read the store and not `qualification_dir`; the reader answers
   them (section 6, section 6.1). There is no dual read and no fallback.
10. **DECIDED (%7, ruling (a)): the key is the binary entry's own SHA-256.** The key's SHA-256 is the SHA-256 of the list's
    entry at `binary_path`, as the key is today. No re-key: no file name, descriptor name or stem changes (section 3.7).
    Order: `user_version` stays 1 only if no release of this repository ships a store before the code of this amendment
    lands, so that code lands before this pass's release of this repository.
11. **DECIDED (%7, ruling (a)): rejudge works from rows only.** Probe bytes are never kept beside the store. Any field
    the judge needs gets a column, including `ownThreads` and `otherThreads` (section 6.2).

The records a device already holds in its `qualification_dir` are not migrated, imported or read by the switch: the
sync measures a plugin that the base does not hold, and the old files stay on the device unread. No program converts
them (section 10).

## 10. Out of scope

- Any compatibility mechanism: no dual read of the old files and the database, no fallback from one to the other, no
  alias, no shim, no second format. If the switch seems to need one, it stops and asks the owner. In particular no
  consumer (`readDistributedLayer`, `matchDistributed`, `applyDistributed`, `qualify-rejudge`, `pruneStale`,
  `pluginCounts`, the passes of the sync) reads the distributed JSON or a `qualification_dir` once the switch is made,
  and no importer turns the files of a device's `qualification_dir` into rows.
- A release of this repository that ships a store before the code of this amendment lands: it would fix `user_version`
  1 on a shape this amendment changes (section 3.6, section 9, ruling 10).
- A hash over the whole list as the key's SHA-256, a store of probe outputs, and a probe-bytes pin (section 3.7).
- Removing the old package names. The JSON files stop being installed with the consumer switch (section 5), not before.
- An upgrade path for a user layer at another `user_version`.
- plugin-db's store and its judged and reference layers.
