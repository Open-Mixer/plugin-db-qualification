-- SPDX-License-Identifier: GPL-3.0-or-later
-- Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
-- The qualification store, user_version 1 (this repository's qualification store spec, section 3.3, verbatim, with
-- WORD(c) and RELPATH(c) written out as section 3.2 defines them). The writer sets PRAGMA user_version last.
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
  format    TEXT NOT NULL CHECK ((length(format) > 0 AND instr(format, ' ') = 0 AND instr(format, char(9)) = 0 AND instr(format, char(10)) = 0)),
  uri       TEXT NOT NULL CHECK (length(uri) > 0),
  UNIQUE (sha256, format, uri)
) STRICT;

CREATE TABLE record_set (                  -- one provenance.json; base layer only
  set_id          INTEGER PRIMARY KEY,
  host_class      TEXT NOT NULL CHECK ((length(host_class) > 0 AND instr(host_class, ' ') = 0 AND instr(host_class, char(9)) = 0 AND instr(host_class, char(10)) = 0)),
  name            TEXT NOT NULL,           -- a name: the set's own (zynthian-vangelis, fedora44-48000-512)
  schema          TEXT NOT NULL,
  tier            TEXT NOT NULL CHECK ((length(tier) > 0 AND instr(tier, ' ') = 0 AND instr(tier, char(9)) = 0 AND instr(tier, char(10)) = 0)),
  host_profile    TEXT NOT NULL CHECK ((length(host_profile) > 0 AND instr(host_profile, ' ') = 0 AND instr(host_profile, char(9)) = 0 AND instr(host_profile, char(10)) = 0)),
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
  key    TEXT NOT NULL CHECK ((length(key) > 0 AND instr(key, ' ') = 0 AND instr(key, char(9)) = 0 AND instr(key, char(10)) = 0)),
  value  TEXT NOT NULL,
  PRIMARY KEY (set_id, key)
) STRICT;

CREATE TABLE record (
  record_id   INTEGER PRIMARY KEY,
  plugin_id   INTEGER NOT NULL REFERENCES plugin,
  set_id      INTEGER REFERENCES record_set ON DELETE CASCADE,  -- NULL in the user layer
  host_class  TEXT NOT NULL CHECK ((length(host_class) > 0 AND instr(host_class, ' ') = 0 AND instr(host_class, char(9)) = 0 AND instr(host_class, char(10)) = 0)),
  offer       TEXT NOT NULL CHECK ((length(offer) > 0 AND instr(offer, ' ') = 0 AND instr(offer, char(9)) = 0 AND instr(offer, char(10)) = 0)),
  name        TEXT NOT NULL,               -- the file name without .<offer>.qualification.json
  schema      TEXT NOT NULL,
  -- the package the binary came from: NULL when not known, never guessed
  pkg_format  TEXT CHECK (pkg_format IS NULL OR (length(pkg_format) > 0 AND instr(pkg_format, ' ') = 0 AND instr(pkg_format, char(9)) = 0 AND instr(pkg_format, char(10)) = 0)),   -- deb, rpm
  pkg_name    TEXT,
  pkg_version TEXT,
  pkg_release TEXT,
  pkg_distro  TEXT CHECK (pkg_distro IS NULL OR (length(pkg_distro) > 0 AND instr(pkg_distro, ' ') = 0 AND instr(pkg_distro, char(9)) = 0 AND instr(pkg_distro, char(10)) = 0)),   -- e.g. trixie, fc45
  pkg_arch    TEXT CHECK (pkg_arch IS NULL OR (length(pkg_arch) > 0 AND instr(pkg_arch, ' ') = 0 AND instr(pkg_arch, char(9)) = 0 AND instr(pkg_arch, char(10)) = 0)),       -- the package's own arch word: arm64, x86_64, all, noarch
  -- binary
  binary_path    TEXT NOT NULL CHECK (length(binary_path) > 0 AND binary_path NOT GLOB '/*' AND substr(binary_path, -1) <> '/' AND instr(binary_path, '//') = 0 AND instr('/' || binary_path || '/', '/./') = 0 AND instr('/' || binary_path || '/', '/../') = 0),
  layout_scheme  TEXT,
  layout_sha256  TEXT,
  unpinnable     INTEGER CHECK (unpinnable IN (0, 1)),               -- 1 when binary.unpinnable is present
  host_extensions INTEGER CHECK (host_extensions IS NULL OR host_extensions = 1),   -- 1: the hostExtensions list is present (record_extension, possibly empty); NULL: an LV2 record, or a CLAP probe that ended before the offer
  tested_version TEXT,
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
  probe_reason    TEXT NOT NULL CHECK ((length(probe_reason) > 0 AND instr(probe_reason, ' ') = 0 AND instr(probe_reason, char(9)) = 0 AND instr(probe_reason, char(10)) = 0)),
  probe_outcome   TEXT NOT NULL CHECK ((length(probe_outcome) > 0 AND instr(probe_outcome, ' ') = 0 AND instr(probe_outcome, char(9)) = 0 AND instr(probe_outcome, char(10)) = 0)),
  probe_complete  INTEGER NOT NULL CHECK (probe_complete IN (0, 1)),
  probe_meets_protocol INTEGER NOT NULL CHECK (probe_meets_protocol IN (0, 1)),
  probe_loadavg1  REAL NOT NULL,
  probe_cores     INTEGER NOT NULL,
  mc_arch         TEXT NOT NULL CHECK ((length(mc_arch) > 0 AND instr(mc_arch, ' ') = 0 AND instr(mc_arch, char(9)) = 0 AND instr(mc_arch, char(10)) = 0)),               -- the measuring machine's, not the package's
  mc_family       TEXT NOT NULL CHECK ((length(mc_family) > 0 AND instr(mc_family, ' ') = 0 AND instr(mc_family, char(9)) = 0 AND instr(mc_family, char(10)) = 0)),
  mc_core_band    TEXT NOT NULL CHECK ((length(mc_core_band) > 0 AND instr(mc_core_band, ' ') = 0 AND instr(mc_core_band, char(9)) = 0 AND instr(mc_core_band, char(10)) = 0)),
  mc_clock_band   TEXT NOT NULL CHECK ((length(mc_clock_band) > 0 AND instr(mc_clock_band, ' ') = 0 AND instr(mc_clock_band, char(9)) = 0 AND instr(mc_clock_band, char(10)) = 0)),
  mc_preempt_rt   INTEGER NOT NULL CHECK (mc_preempt_rt IN (0, 1)),
  mc_cstates_limited INTEGER NOT NULL CHECK (mc_cstates_limited IN (0, 1)),
  -- behaviour
  lifecycle_cycles INTEGER, lifecycle_failed INTEGER, lifecycle_instantiated INTEGER,
  threads_before INTEGER, threads_after_first_instantiate INTEGER, threads_after_all_freed INTEGER,
  -- adapter pass
  adapter_admitted INTEGER CHECK (adapter_admitted IN (0, 1)),
  adapter_host     TEXT CHECK (adapter_host IS NULL OR (length(adapter_host) > 0 AND instr(adapter_host, ' ') = 0 AND instr(adapter_host, char(9)) = 0 AND instr(adapter_host, char(10)) = 0)),
  adapter_measured INTEGER CHECK (adapter_measured IN (0, 1)),
  adapter_code     TEXT CHECK (adapter_code IS NULL OR (length(adapter_code) > 0 AND instr(adapter_code, ' ') = 0 AND instr(adapter_code, char(9)) = 0 AND instr(adapter_code, char(10)) = 0)),
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
  path      TEXT NOT NULL CHECK (length(path) > 0 AND path NOT GLOB '/*' AND substr(path, -1) <> '/' AND instr(path, '//') = 0 AND instr('/' || path || '/', '/./') = 0 AND instr('/' || path || '/', '/../') = 0),   -- relative to the item's root, as the pin names it (section 3.7)
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
  host      TEXT NOT NULL CHECK ((length(host) > 0 AND instr(host, ' ') = 0 AND instr(host, char(9)) = 0 AND instr(host, char(10)) = 0)),
  measured  INTEGER NOT NULL CHECK (measured IN (0, 1)),
  rating    TEXT NOT NULL CHECK ((length(rating) > 0 AND instr(rating, ' ') = 0 AND instr(rating, char(9)) = 0 AND instr(rating, char(10)) = 0)),
  qualified INTEGER NOT NULL CHECK (qualified IN (0, 1)),
  hosting   TEXT NOT NULL CHECK ((length(hosting) > 0 AND instr(hosting, ' ') = 0 AND instr(hosting, char(9)) = 0 AND instr(hosting, char(10)) = 0)),
  arm       TEXT NOT NULL CHECK ((length(arm) > 0 AND instr(arm, ' ') = 0 AND instr(arm, char(9)) = 0 AND instr(arm, char(10)) = 0)),
  deciding  TEXT CHECK (deciding IS NULL OR (length(deciding) > 0 AND instr(deciding, ' ') = 0 AND instr(deciding, char(9)) = 0 AND instr(deciding, char(10)) = 0)),
  PRIMARY KEY (record_id, ord),
  UNIQUE (record_id, host)
) STRICT;

CREATE TABLE cost_entry (                  -- cost[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord       INTEGER NOT NULL,
  host      TEXT NOT NULL CHECK ((length(host) > 0 AND instr(host, ' ') = 0 AND instr(host, char(9)) = 0 AND instr(host, char(10)) = 0)),
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
  dimension TEXT NOT NULL CHECK ((length(dimension) > 0 AND instr(dimension, ' ') = 0 AND instr(dimension, char(9)) = 0 AND instr(dimension, char(10)) = 0)),
  rating    TEXT NOT NULL CHECK ((length(rating) > 0 AND instr(rating, ' ') = 0 AND instr(rating, char(9)) = 0 AND instr(rating, char(10)) = 0)),
  code      TEXT NOT NULL CHECK ((length(code) > 0 AND instr(code, ' ') = 0 AND instr(code, char(9)) = 0 AND instr(code, char(10)) = 0)),
  CHECK ((verdict_ord IS NULL) <> (cost_ord IS NULL)),
  FOREIGN KEY (record_id, verdict_ord) REFERENCES verdict (record_id, ord) ON DELETE CASCADE,
  FOREIGN KEY (record_id, cost_ord) REFERENCES cost_entry (record_id, ord) ON DELETE CASCADE
) STRICT;
CREATE UNIQUE INDEX reason_of_verdict ON reason (record_id, verdict_ord, ord) WHERE verdict_ord IS NOT NULL;
CREATE UNIQUE INDEX reason_of_cost    ON reason (record_id, cost_ord, ord)    WHERE cost_ord IS NOT NULL;

CREATE TABLE reason_param (                -- reasons[].params
  reason_id INTEGER NOT NULL REFERENCES reason ON DELETE CASCADE,
  name      TEXT NOT NULL CHECK ((length(name) > 0 AND instr(name, ' ') = 0 AND instr(name, char(9)) = 0 AND instr(name, char(10)) = 0)),
  number    ANY CHECK (number IS NULL OR typeof(number) IN ('integer', 'real')),
  word      TEXT CHECK (word IS NULL OR (length(word) > 0 AND instr(word, ' ') = 0 AND instr(word, char(9)) = 0 AND instr(word, char(10)) = 0)),
  CHECK ((number IS NULL) <> (word IS NULL)),
  PRIMARY KEY (reason_id, name)
) STRICT;

CREATE TABLE tier (                        -- tiers.inProcess, tiers.isolated
  record_id  INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  tier       TEXT NOT NULL CHECK ((length(tier) > 0 AND instr(tier, ' ') = 0 AND instr(tier, char(9)) = 0 AND instr(tier, char(10)) = 0)),          -- inProcess, isolated
  host       TEXT NOT NULL CHECK ((length(host) > 0 AND instr(host, ' ') = 0 AND instr(host, char(9)) = 0 AND instr(host, char(10)) = 0)),
  measured   INTEGER NOT NULL CHECK (measured IN (0, 1)),
  qualified  INTEGER NOT NULL CHECK (qualified IN (0, 1)),
  rating     TEXT NOT NULL CHECK ((length(rating) > 0 AND instr(rating, ' ') = 0 AND instr(rating, char(9)) = 0 AND instr(rating, char(10)) = 0)),
  deciding   TEXT CHECK (deciding IS NULL OR (length(deciding) > 0 AND instr(deciding, ' ') = 0 AND instr(deciding, char(9)) = 0 AND instr(deciding, char(10)) = 0)),
  runs_alone INTEGER CHECK (runs_alone IN (0, 1)),
  PRIMARY KEY (record_id, tier)
) STRICT;

CREATE TABLE tier_offered (                -- tiers.offeredOn[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord       INTEGER NOT NULL,
  tier      TEXT NOT NULL CHECK ((length(tier) > 0 AND instr(tier, ' ') = 0 AND instr(tier, char(9)) = 0 AND instr(tier, char(10)) = 0)),
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE cell (                        -- measurements.grid[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord       INTEGER NOT NULL,
  rate      INTEGER NOT NULL,
  quantum   INTEGER NOT NULL,
  outcome   TEXT NOT NULL CHECK ((length(outcome) > 0 AND instr(outcome, ' ') = 0 AND instr(outcome, char(9)) = 0 AND instr(outcome, char(10)) = 0)),
  latency_declared_frames INTEGER, latency_measured_frames INTEGER,
  latency_ms REAL,                          -- latencyMs: the measured latency in ms at the cell's rate, as written; NULL: absent
  latency_code TEXT CHECK (latency_code IS NULL OR (length(latency_code) > 0 AND instr(latency_code, ' ') = 0 AND instr(latency_code, char(9)) = 0 AND instr(latency_code, char(10)) = 0)),
  latency_unmeasured_reason TEXT CHECK (latency_unmeasured_reason IS NULL OR (length(latency_unmeasured_reason) > 0 AND instr(latency_unmeasured_reason, ' ') = 0 AND instr(latency_unmeasured_reason, char(9)) = 0 AND instr(latency_unmeasured_reason, char(10)) = 0)),
  cost_median REAL, cost_percentile_p INTEGER, cost_percentile_value REAL,
  cost_blocks INTEGER, cost_warmup_blocks INTEGER,
  voices_basis TEXT CHECK (voices_basis IS NULL OR (length(voices_basis) > 0 AND instr(voices_basis, ' ') = 0 AND instr(voices_basis, char(9)) = 0 AND instr(voices_basis, char(10)) = 0)),
  voices_capacity INTEGER, voices_held INTEGER,
  mem_after_instantiate_kb INTEGER, mem_after_activate_kb INTEGER, mem_at_rest_kb INTEGER,
  mem_second_instance_kb INTEGER, mem_first_instance_kb INTEGER, mem_per_instance_kb INTEGER,
  mem_notes_held_kb INTEGER,
  mem_basis TEXT CHECK (mem_basis IS NULL OR (length(mem_basis) > 0 AND instr(mem_basis, ' ') = 0 AND instr(mem_basis, char(9)) = 0 AND instr(mem_basis, char(10)) = 0)),
  mem_unmeasured_reason TEXT CHECK (mem_unmeasured_reason IS NULL OR (length(mem_unmeasured_reason) > 0 AND instr(mem_unmeasured_reason, ' ') = 0 AND instr(mem_unmeasured_reason, char(9)) = 0 AND instr(mem_unmeasured_reason, char(10)) = 0)),
  mem_limit_bytes INTEGER,
  mem_limit_mechanism TEXT CHECK (mem_limit_mechanism IS NULL OR (length(mem_limit_mechanism) > 0 AND instr(mem_limit_mechanism, ' ') = 0 AND instr(mem_limit_mechanism, char(9)) = 0 AND instr(mem_limit_mechanism, char(10)) = 0)),
  rt_interposer INTEGER CHECK (rt_interposer IN (0, 1)), rt_swept INTEGER CHECK (rt_swept IN (0, 1)),
  rt_sweep_applicable INTEGER CHECK (rt_sweep_applicable IN (0, 1)),
  rt_blocks INTEGER, rt_allocations INTEGER, rt_locks INTEGER, rt_syscalls INTEGER,
  rt_thread_violations INTEGER, rt_process_errors INTEGER,
  rt_own_threads INTEGER,                  -- threads the plugin started itself (judged under hosting.rt-safety.own-threads); NULL: not taken
  rt_other_allocations INTEGER, rt_other_locks INTEGER, rt_other_syscalls INTEGER,   -- what threads other than the audio thread did; all three or none
  note_sweep_applicable INTEGER CHECK (note_sweep_applicable IN (0, 1)),
  note_sweep_dialect TEXT CHECK (note_sweep_dialect IS NULL OR (length(note_sweep_dialect) > 0 AND instr(note_sweep_dialect, ' ') = 0 AND instr(note_sweep_dialect, char(9)) = 0 AND instr(note_sweep_dialect, char(10)) = 0)),
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
  dimension TEXT NOT NULL CHECK ((length(dimension) > 0 AND instr(dimension, ' ') = 0 AND instr(dimension, char(9)) = 0 AND instr(dimension, char(10)) = 0)),
  code TEXT NOT NULL CHECK ((length(code) > 0 AND instr(code, ' ') = 0 AND instr(code, char(9)) = 0 AND instr(code, char(10)) = 0)),
  rate INTEGER NOT NULL, quantum INTEGER NOT NULL,
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE not_measured (                -- notMeasured[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  dimension TEXT NOT NULL CHECK ((length(dimension) > 0 AND instr(dimension, ' ') = 0 AND instr(dimension, char(9)) = 0 AND instr(dimension, char(10)) = 0)),
  code TEXT NOT NULL CHECK ((length(code) > 0 AND instr(code, ' ') = 0 AND instr(code, char(9)) = 0 AND instr(code, char(10)) = 0)),
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE run_step (                    -- run.steps[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  step TEXT NOT NULL CHECK ((length(step) > 0 AND instr(step, ' ') = 0 AND instr(step, char(9)) = 0 AND instr(step, char(10)) = 0)),
  result TEXT NOT NULL CHECK ((length(result) > 0 AND instr(result, ' ') = 0 AND instr(result, char(9)) = 0 AND instr(result, char(10)) = 0)),
  code TEXT CHECK (code IS NULL OR (length(code) > 0 AND instr(code, ' ') = 0 AND instr(code, char(9)) = 0 AND instr(code, char(10)) = 0)),
  cpu_percent REAL, latency_frames INTEGER, midi_inputs_linked INTEGER, xruns INTEGER,
  pool_allocations_on INTEGER, pool_locks_on INTEGER, pool_syscalls_on INTEGER, pool_tasks_on_helpers INTEGER,
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE probe_end (                   -- probe.ends[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  step TEXT NOT NULL CHECK ((length(step) > 0 AND instr(step, ' ') = 0 AND instr(step, char(9)) = 0 AND instr(step, char(10)) = 0)),
  outcome TEXT NOT NULL CHECK ((length(outcome) > 0 AND instr(outcome, ' ') = 0 AND instr(outcome, char(9)) = 0 AND instr(outcome, char(10)) = 0)),
  exit_status INTEGER,
  signal TEXT CHECK (signal IS NULL OR (length(signal) > 0 AND instr(signal, ' ') = 0 AND instr(signal, char(9)) = 0 AND instr(signal, char(10)) = 0)),
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE adapter_cell (                -- adapter.cells[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  rate INTEGER NOT NULL, quantum INTEGER NOT NULL,
  admitted INTEGER NOT NULL CHECK (admitted IN (0, 1)),
  measured INTEGER NOT NULL CHECK (measured IN (0, 1)),
  code TEXT CHECK (code IS NULL OR (length(code) > 0 AND instr(code, ' ') = 0 AND instr(code, char(9)) = 0 AND instr(code, char(10)) = 0)),
  params INTEGER NOT NULL CHECK (params IN (0, 1)),   -- 1 when this cell's params is present
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE adapter_param (               -- adapter.params
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  name      TEXT NOT NULL CHECK ((length(name) > 0 AND instr(name, ' ') = 0 AND instr(name, char(9)) = 0 AND instr(name, char(10)) = 0)),
  number    ANY CHECK (number IS NULL OR typeof(number) IN ('integer', 'real')),
  word      TEXT CHECK (word IS NULL OR (length(word) > 0 AND instr(word, ' ') = 0 AND instr(word, char(9)) = 0 AND instr(word, char(10)) = 0)),
  CHECK ((number IS NULL) <> (word IS NULL)),
  PRIMARY KEY (record_id, name)
) STRICT;

CREATE TABLE adapter_cell_param (          -- adapter.cells[].params
  record_id INTEGER NOT NULL,
  ord       INTEGER NOT NULL,
  name      TEXT NOT NULL CHECK ((length(name) > 0 AND instr(name, ' ') = 0 AND instr(name, char(9)) = 0 AND instr(name, char(10)) = 0)),
  number    ANY CHECK (number IS NULL OR typeof(number) IN ('integer', 'real')),
  word      TEXT CHECK (word IS NULL OR (length(word) > 0 AND instr(word, ' ') = 0 AND instr(word, char(9)) = 0 AND instr(word, char(10)) = 0)),
  CHECK ((number IS NULL) <> (word IS NULL)),
  PRIMARY KEY (record_id, ord, name),
  FOREIGN KEY (record_id, ord) REFERENCES adapter_cell (record_id, ord) ON DELETE CASCADE
) STRICT;

CREATE TABLE memory_run_cell (             -- memoryRun.cells[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  rate INTEGER NOT NULL, quantum INTEGER NOT NULL,
  outcome TEXT NOT NULL CHECK ((length(outcome) > 0 AND instr(outcome, ' ') = 0 AND instr(outcome, char(9)) = 0 AND instr(outcome, char(10)) = 0)),
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TABLE rejudged_owe (                -- rejudged.owes[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  code TEXT NOT NULL CHECK ((length(code) > 0 AND instr(code, ' ') = 0 AND instr(code, char(9)) = 0 AND instr(code, char(10)) = 0)),
  measurement TEXT NOT NULL CHECK ((length(measurement) > 0 AND instr(measurement, ' ') = 0 AND instr(measurement, char(9)) = 0 AND instr(measurement, char(10)) = 0)),
  PRIMARY KEY (record_id, ord)
) STRICT;

CREATE TRIGGER record_set_by_layer BEFORE INSERT ON record
WHEN (NEW.set_id IS NULL) <> ((SELECT user_layer FROM store_info) = 1)
BEGIN SELECT RAISE(ABORT, 'record.set_id: NULL exactly in the user layer'); END;
