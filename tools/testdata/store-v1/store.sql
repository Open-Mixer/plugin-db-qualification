-- A user layer at user_version 1, as the writer of v2026112401 (a91a7bda3) wrote it: the four records of
-- records.json beside it, put with that tag's tools/qualification_db.py against the domains of plugin-hostd 8b97ffe,
-- plugin-hostd-protocol ab962df, plugin-db 6133872 and omx-clap-core 324cd12 (their main at 2026-11-24), dumped
-- with Python's sqlite3 iterdump. The migration tests load it (tools/test_qualification_db_write.py Migration).
PRAGMA user_version = 1;
BEGIN TRANSACTION;
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
INSERT INTO "adapter_cell" VALUES(3,0,48000,128,1,1,NULL,1);
INSERT INTO "adapter_cell" VALUES(3,1,48000,256,1,1,NULL,1);
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
CREATE TABLE adapter_param (               -- adapter.params
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  name      TEXT NOT NULL CHECK ((length(name) > 0 AND instr(name, ' ') = 0 AND instr(name, char(9)) = 0 AND instr(name, char(10)) = 0)),
  number    ANY CHECK (number IS NULL OR typeof(number) IN ('integer', 'real')),
  word      TEXT CHECK (word IS NULL OR (length(word) > 0 AND instr(word, ' ') = 0 AND instr(word, char(9)) = 0 AND instr(word, char(10)) = 0)),
  CHECK ((number IS NULL) <> (word IS NULL)),
  PRIMARY KEY (record_id, name)
) STRICT;
INSERT INTO "adapter_param" VALUES(4,'resp',-201,NULL);
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
INSERT INTO "cell" VALUES(1,0,48000,256,'probe.ok',480,480,NULL,NULL,NULL,1283.79,95,1288.26,512,64,NULL,NULL,NULL,4336,4352,4704,16,4704,16,NULL,NULL,NULL,NULL,NULL,1,1,1,1024,0,1024,0,0,0,NULL,NULL,NULL,NULL,0,NULL,NULL,NULL,NULL);
INSERT INTO "cell" VALUES(1,1,96000,256,'probe.ok',480,480,NULL,NULL,NULL,1283.78,95,1288.12,512,64,NULL,NULL,NULL,4448,4464,4848,16,4848,16,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cell" VALUES(1,2,48000,128,'probe.ok',NULL,NULL,NULL,'hosting.latency.unmeasured','not-attempted',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,4336,4336,4688,32,4688,32,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cell" VALUES(2,0,48000,256,'probe.ok',480,480,NULL,NULL,NULL,1283.78,95,1288.2,512,64,NULL,NULL,NULL,4448,4464,4848,16,4848,16,NULL,NULL,NULL,NULL,NULL,1,1,1,1024,0,1024,0,0,0,NULL,NULL,NULL,NULL,0,NULL,NULL,NULL,NULL);
INSERT INTO "cell" VALUES(2,1,96000,256,'probe.ok',480,480,NULL,NULL,NULL,1283.71,95,1288.41,512,64,NULL,NULL,NULL,4448,4464,4848,16,4848,16,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cell" VALUES(3,0,48000,256,'probe.ok',0,1,NULL,NULL,NULL,310.764,95,533.557,512,64,NULL,NULL,NULL,3568,3568,3568,480,3568,480,NULL,NULL,NULL,NULL,NULL,1,1,1,512,0,0,0,NULL,NULL,NULL,NULL,NULL,NULL,0,NULL,NULL,NULL,NULL);
INSERT INTO "cell" VALUES(3,1,96000,256,'probe.ok',0,1,NULL,NULL,NULL,315.395,95,534.504,512,64,NULL,NULL,NULL,3744,3744,3744,608,3744,608,NULL,NULL,NULL,NULL,NULL,1,1,1,512,0,0,0,NULL,NULL,NULL,NULL,NULL,NULL,0,NULL,NULL,NULL,NULL);
INSERT INTO "cell" VALUES(3,2,48000,128,'probe.ok',NULL,NULL,NULL,'hosting.latency.unmeasured','not-attempted',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,3552,3552,3552,480,3552,480,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cell" VALUES(4,0,48000,256,'probe.crashed',NULL,NULL,NULL,'hosting.latency.unmeasured','probe-crashed',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,7088,7088,7088,1968,7088,1968,7088,'probe',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cell" VALUES(4,1,96000,256,'probe.crashed',NULL,NULL,NULL,'hosting.latency.unmeasured','probe-crashed',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cell" VALUES(4,2,48000,128,'probe.ok',NULL,NULL,NULL,'hosting.latency.unmeasured','not-attempted',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,7088,7088,7088,1968,7088,1968,7088,'probe',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
CREATE TABLE cell_event (                  -- measurements.grid[].rtSafety.events[]
  record_id INTEGER NOT NULL,
  cell_ord  INTEGER NOT NULL,
  ord       INTEGER NOT NULL,
  event     TEXT NOT NULL,                 -- a symbol name as the interposer wrote it
  PRIMARY KEY (record_id, cell_ord, ord),
  FOREIGN KEY (record_id, cell_ord) REFERENCES cell (record_id, ord) ON DELETE CASCADE
) STRICT;
INSERT INTO "cell_event" VALUES(1,0,0,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(1,0,1,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(1,0,2,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(1,0,3,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(1,0,4,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(1,0,5,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(1,0,6,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(1,0,7,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(1,0,8,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(1,0,9,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(1,0,10,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(1,0,11,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(1,0,12,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(1,0,13,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(1,0,14,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(1,0,15,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,0,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,1,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,2,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,3,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,4,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,5,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,6,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,7,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,8,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,9,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,10,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,11,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,12,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,13,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,14,'pthread_mutex_trylock');
INSERT INTO "cell_event" VALUES(2,0,15,'pthread_mutex_trylock');
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
INSERT INTO "claim" VALUES(1,1,'custom','rpi5',48000,256);
INSERT INTO "claim" VALUES(1,1,'custom','rpi5',96000,256);
INSERT INTO "claim" VALUES(1,1,'custom','rpi5',48000,128);
INSERT INTO "claim" VALUES(2,1,'default','rpi5',48000,256);
INSERT INTO "claim" VALUES(2,1,'default','rpi5',96000,256);
INSERT INTO "claim" VALUES(3,2,'default','rpi5',48000,256);
INSERT INTO "claim" VALUES(3,2,'default','rpi5',96000,256);
INSERT INTO "claim" VALUES(3,2,'default','rpi5',48000,128);
INSERT INTO "claim" VALUES(4,3,'default','rpi5',48000,256);
INSERT INTO "claim" VALUES(4,3,'default','rpi5',96000,256);
INSERT INTO "claim" VALUES(4,3,'default','rpi5',48000,128);
CREATE TABLE cost_entry (                  -- cost[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord       INTEGER NOT NULL,
  host      TEXT NOT NULL CHECK ((length(host) > 0 AND instr(host, ' ') = 0 AND instr(host, char(9)) = 0 AND instr(host, char(10)) = 0)),
  rate      INTEGER NOT NULL,
  quantum   INTEGER NOT NULL,
  PRIMARY KEY (record_id, ord)
) STRICT;
INSERT INTO "cost_entry" VALUES(1,0,'omx-clap-host',48000,128);
INSERT INTO "cost_entry" VALUES(1,1,'openmixer-pi-4gb',48000,128);
INSERT INTO "cost_entry" VALUES(1,2,'openmixer-pi-8gb',48000,128);
INSERT INTO "cost_entry" VALUES(2,0,'openmixer-console',96000,1024);
INSERT INTO "cost_entry" VALUES(3,0,'omx-clap-host',48000,128);
INSERT INTO "cost_entry" VALUES(3,1,'openmixer-console',96000,1024);
INSERT INTO "cost_entry" VALUES(3,2,'openmixer-pi-4gb',48000,128);
INSERT INTO "cost_entry" VALUES(3,3,'openmixer-pi-8gb',48000,128);
INSERT INTO "cost_entry" VALUES(4,0,'omx-clap-host',48000,128);
INSERT INTO "cost_entry" VALUES(4,1,'openmixer-console',96000,1024);
INSERT INTO "cost_entry" VALUES(4,2,'openmixer-pi-4gb',48000,128);
INSERT INTO "cost_entry" VALUES(4,3,'openmixer-pi-8gb',48000,128);
CREATE TABLE feature_required (            -- measurements.behaviour.features.required[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL, feature TEXT NOT NULL,
  PRIMARY KEY (record_id, ord)
) STRICT;
INSERT INTO "feature_required" VALUES(3,0,'http://lv2plug.in/ns/ext/worker#schedule');
INSERT INTO "feature_required" VALUES(3,1,'http://lv2plug.in/ns/ext/urid#map');
INSERT INTO "feature_required" VALUES(3,2,'http://lv2plug.in/ns/ext/options#options');
CREATE TABLE history_blocked (             -- history[].verdicts[].blockedBy[]
  record_id INTEGER NOT NULL,
  history_ord INTEGER NOT NULL,
  verdict_ord INTEGER NOT NULL,
  ord       INTEGER NOT NULL,
  code      TEXT NOT NULL CHECK ((length(code) > 0 AND instr(code, ' ') = 0 AND instr(code, char(9)) = 0 AND instr(code, char(10)) = 0)),
  PRIMARY KEY (record_id, history_ord, verdict_ord, ord),
  FOREIGN KEY (record_id, history_ord, verdict_ord) REFERENCES history_verdict (record_id, history_ord, ord) ON DELETE CASCADE
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
  host      TEXT NOT NULL CHECK ((length(host) > 0 AND instr(host, ' ') = 0 AND instr(host, char(9)) = 0 AND instr(host, char(10)) = 0)),
  measured  TEXT CHECK (measured IS NULL OR (length(measured) > 0 AND instr(measured, ' ') = 0 AND instr(measured, char(9)) = 0 AND instr(measured, char(10)) = 0)),   -- NULL: null
  adjusted  TEXT CHECK (adjusted IS NULL OR (length(adjusted) > 0 AND instr(adjusted, ' ') = 0 AND instr(adjusted, char(9)) = 0 AND instr(adjusted, char(10)) = 0)),   -- NULL: null
  move      TEXT NOT NULL CHECK ((length(move) > 0 AND instr(move, ' ') = 0 AND instr(move, char(9)) = 0 AND instr(move, char(10)) = 0)),
  reason    TEXT NOT NULL CHECK ((length(reason) > 0 AND instr(reason, ' ') = 0 AND instr(reason, char(9)) = 0 AND instr(reason, char(10)) = 0)),
  blocked_by INTEGER CHECK (blocked_by IS NULL OR blocked_by = 1),   -- 1: blockedBy present (history_blocked, possibly none)
  PRIMARY KEY (record_id, history_ord, ord),
  FOREIGN KEY (record_id, history_ord) REFERENCES record_history (record_id, ord) ON DELETE CASCADE
) STRICT;
CREATE TABLE memory_run_cell (             -- memoryRun.cells[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  rate INTEGER NOT NULL, quantum INTEGER NOT NULL,
  outcome TEXT NOT NULL CHECK ((length(outcome) > 0 AND instr(outcome, ' ') = 0 AND instr(outcome, char(9)) = 0 AND instr(outcome, char(10)) = 0)),
  PRIMARY KEY (record_id, ord)
) STRICT;
INSERT INTO "memory_run_cell" VALUES(1,0,48000,128,'probe.ok');
INSERT INTO "memory_run_cell" VALUES(1,1,48000,256,'probe.ok');
INSERT INTO "memory_run_cell" VALUES(3,0,48000,128,'probe.ok');
INSERT INTO "memory_run_cell" VALUES(3,1,48000,256,'probe.ok');
INSERT INTO "memory_run_cell" VALUES(4,0,48000,128,'probe.ok');
INSERT INTO "memory_run_cell" VALUES(4,1,48000,256,'probe.ok');
CREATE TABLE not_measured (                -- notMeasured[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  dimension TEXT NOT NULL CHECK ((length(dimension) > 0 AND instr(dimension, ' ') = 0 AND instr(dimension, char(9)) = 0 AND instr(dimension, char(10)) = 0)),
  code TEXT NOT NULL CHECK ((length(code) > 0 AND instr(code, ' ') = 0 AND instr(code, char(9)) = 0 AND instr(code, char(10)) = 0)),
  PRIMARY KEY (record_id, ord)
) STRICT;
INSERT INTO "not_measured" VALUES(1,0,'stability','hosting.stability.unsoaked');
INSERT INTO "not_measured" VALUES(1,1,'memoryGrowth','hosting.stability.unsoaked');
INSERT INTO "not_measured" VALUES(2,0,'stability','hosting.stability.unsoaked');
INSERT INTO "not_measured" VALUES(3,0,'stability','hosting.stability.unsoaked');
INSERT INTO "not_measured" VALUES(3,1,'memoryGrowth','hosting.stability.unsoaked');
INSERT INTO "not_measured" VALUES(4,0,'stability','hosting.stability.unsoaked');
INSERT INTO "not_measured" VALUES(4,1,'memoryGrowth','hosting.stability.unsoaked');
CREATE TABLE plugin (
  plugin_id INTEGER PRIMARY KEY,
  sha256    TEXT NOT NULL CHECK (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
  format    TEXT NOT NULL CHECK ((length(format) > 0 AND instr(format, ' ') = 0 AND instr(format, char(9)) = 0 AND instr(format, char(10)) = 0)),
  uri       TEXT NOT NULL CHECK (length(uri) > 0),
  UNIQUE (sha256, format, uri)
) STRICT;
INSERT INTO "plugin" VALUES(1,'6d8dd5239ab38df8c4682d2f97681a5cf2d1d98c6b8390ec117151539cc71566','clap','com.zamaudio.ZaMaximX2');
INSERT INTO "plugin" VALUES(2,'dc8fb55c97a2f05125169a036113a7cceaf00de740d847b662f0990792dd1c38','lv2','http://aidadsp.cc/plugins/aidadsp-bundle/rt-neural-loader');
INSERT INTO "plugin" VALUES(3,'3f3fd8198cde3ac9962fe134053253b7320befc53e2e4ba91252ee0b644dfd81','lv2','http://calf.sourceforge.net/plugins/Wavetable');
CREATE TABLE probe_end (                   -- probe.ends[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  step TEXT NOT NULL CHECK ((length(step) > 0 AND instr(step, ' ') = 0 AND instr(step, char(9)) = 0 AND instr(step, char(10)) = 0)),
  outcome TEXT NOT NULL CHECK ((length(outcome) > 0 AND instr(outcome, ' ') = 0 AND instr(outcome, char(9)) = 0 AND instr(outcome, char(10)) = 0)),
  exit_status INTEGER,
  signal TEXT CHECK (signal IS NULL OR (length(signal) > 0 AND instr(signal, ' ') = 0 AND instr(signal, char(9)) = 0 AND instr(signal, char(10)) = 0)),
  PRIMARY KEY (record_id, ord)
) STRICT;
INSERT INTO "probe_end" VALUES(4,0,'lifecycle','probe.crashed',NULL,'SIGSEGV');
INSERT INTO "probe_end" VALUES(4,1,'lifecycle','probe.crashed',NULL,'SIGSEGV');
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
INSERT INTO "reason" VALUES(1,1,0,NULL,0,'rtSafety','conditional','hosting.rt-safety.violations-in-run');
INSERT INTO "reason" VALUES(2,1,1,NULL,0,'rtSafety','conditional','hosting.rt-safety.violations-in-run');
INSERT INTO "reason" VALUES(3,1,1,NULL,1,'memory','conditional','hosting.memory.within-provisional-ceiling');
INSERT INTO "reason" VALUES(4,1,2,NULL,0,'rtSafety','conditional','hosting.rt-safety.violations-in-run');
INSERT INTO "reason" VALUES(5,1,2,NULL,1,'memory','conditional','hosting.memory.within-provisional-ceiling');
INSERT INTO "reason" VALUES(6,1,NULL,0,0,'cost','unknown','hosting.cost.unmeasured-at-rate-and-quantum');
INSERT INTO "reason" VALUES(7,1,NULL,1,0,'cost','unknown','hosting.cost.unmeasured-at-rate-and-quantum');
INSERT INTO "reason" VALUES(8,1,NULL,2,0,'cost','unknown','hosting.cost.unmeasured-at-rate-and-quantum');
INSERT INTO "reason" VALUES(9,2,0,NULL,0,'rtSafety','conditional','hosting.rt-safety.violations-in-run');
INSERT INTO "reason" VALUES(10,2,0,NULL,1,'memory','unknown','hosting.memory.unmeasured');
INSERT INTO "reason" VALUES(11,2,NULL,0,0,'cost','unknown','hosting.cost.unmeasured-at-rate-and-quantum');
INSERT INTO "reason" VALUES(12,3,0,NULL,0,'rtSafety','suitable','hosting.rt-safety.clean-under-sweep');
INSERT INTO "reason" VALUES(13,3,1,NULL,0,'rtSafety','suitable','hosting.rt-safety.clean-under-sweep');
INSERT INTO "reason" VALUES(14,3,1,NULL,1,'memory','unknown','hosting.memory.unmeasured');
INSERT INTO "reason" VALUES(15,3,2,NULL,0,'rtSafety','suitable','hosting.rt-safety.clean-under-sweep');
INSERT INTO "reason" VALUES(16,3,2,NULL,1,'memory','conditional','hosting.memory.within-provisional-ceiling');
INSERT INTO "reason" VALUES(17,3,3,NULL,0,'rtSafety','suitable','hosting.rt-safety.clean-under-sweep');
INSERT INTO "reason" VALUES(18,3,3,NULL,1,'memory','conditional','hosting.memory.within-provisional-ceiling');
INSERT INTO "reason" VALUES(19,3,NULL,0,0,'cost','unknown','hosting.cost.unmeasured-at-rate-and-quantum');
INSERT INTO "reason" VALUES(20,3,NULL,1,0,'cost','unknown','hosting.cost.unmeasured-at-rate-and-quantum');
INSERT INTO "reason" VALUES(21,3,NULL,2,0,'cost','unknown','hosting.cost.unmeasured-at-rate-and-quantum');
INSERT INTO "reason" VALUES(22,3,NULL,3,0,'cost','unknown','hosting.cost.unmeasured-at-rate-and-quantum');
INSERT INTO "reason" VALUES(23,4,0,NULL,0,'rtSafety','unknown','probe.crashed');
INSERT INTO "reason" VALUES(24,4,1,NULL,0,'rtSafety','unknown','probe.crashed');
INSERT INTO "reason" VALUES(25,4,2,NULL,0,'rtSafety','unknown','probe.crashed');
INSERT INTO "reason" VALUES(26,4,3,NULL,0,'rtSafety','unknown','probe.crashed');
INSERT INTO "reason" VALUES(27,4,NULL,0,0,'cost','unknown','hosting.cost.unmeasured-at-rate-and-quantum');
INSERT INTO "reason" VALUES(28,4,NULL,1,0,'cost','unknown','hosting.cost.unmeasured-at-rate-and-quantum');
INSERT INTO "reason" VALUES(29,4,NULL,2,0,'cost','unknown','hosting.cost.unmeasured-at-rate-and-quantum');
INSERT INTO "reason" VALUES(30,4,NULL,3,0,'cost','unknown','hosting.cost.unmeasured-at-rate-and-quantum');
CREATE TABLE reason_param (                -- reasons[].params
  reason_id INTEGER NOT NULL REFERENCES reason ON DELETE CASCADE,
  name      TEXT NOT NULL CHECK ((length(name) > 0 AND instr(name, ' ') = 0 AND instr(name, char(9)) = 0 AND instr(name, char(10)) = 0)),
  number    ANY CHECK (number IS NULL OR typeof(number) IN ('integer', 'real')),
  word      TEXT CHECK (word IS NULL OR (length(word) > 0 AND instr(word, ' ') = 0 AND instr(word, char(9)) = 0 AND instr(word, char(10)) = 0)),
  CHECK ((number IS NULL) <> (word IS NULL)),
  PRIMARY KEY (reason_id, name)
) STRICT;
INSERT INTO "reason_param" VALUES(1,'allocations',0,NULL);
INSERT INTO "reason_param" VALUES(1,'syscalls',0,NULL);
INSERT INTO "reason_param" VALUES(1,'locks',1024,NULL);
INSERT INTO "reason_param" VALUES(2,'allocations',0,NULL);
INSERT INTO "reason_param" VALUES(2,'syscalls',0,NULL);
INSERT INTO "reason_param" VALUES(2,'locks',1024,NULL);
INSERT INTO "reason_param" VALUES(3,'perInstanceKb',32,NULL);
INSERT INTO "reason_param" VALUES(3,'firstInstanceKb',4688,NULL);
INSERT INTO "reason_param" VALUES(3,'ceilingKb',393216,NULL);
INSERT INTO "reason_param" VALUES(3,'consoleCeilingKb',3145728,NULL);
INSERT INTO "reason_param" VALUES(3,'provisional',NULL,'yes');
INSERT INTO "reason_param" VALUES(4,'allocations',0,NULL);
INSERT INTO "reason_param" VALUES(4,'syscalls',0,NULL);
INSERT INTO "reason_param" VALUES(4,'locks',1024,NULL);
INSERT INTO "reason_param" VALUES(5,'perInstanceKb',32,NULL);
INSERT INTO "reason_param" VALUES(5,'firstInstanceKb',4688,NULL);
INSERT INTO "reason_param" VALUES(5,'ceilingKb',917504,NULL);
INSERT INTO "reason_param" VALUES(5,'consoleCeilingKb',7340032,NULL);
INSERT INTO "reason_param" VALUES(5,'provisional',NULL,'yes');
INSERT INTO "reason_param" VALUES(6,'rate',48000,NULL);
INSERT INTO "reason_param" VALUES(6,'quantum',128,NULL);
INSERT INTO "reason_param" VALUES(7,'rate',48000,NULL);
INSERT INTO "reason_param" VALUES(7,'quantum',128,NULL);
INSERT INTO "reason_param" VALUES(8,'rate',48000,NULL);
INSERT INTO "reason_param" VALUES(8,'quantum',128,NULL);
INSERT INTO "reason_param" VALUES(9,'allocations',0,NULL);
INSERT INTO "reason_param" VALUES(9,'syscalls',0,NULL);
INSERT INTO "reason_param" VALUES(9,'locks',1024,NULL);
INSERT INTO "reason_param" VALUES(10,'rate',96000,NULL);
INSERT INTO "reason_param" VALUES(10,'quantum',1024,NULL);
INSERT INTO "reason_param" VALUES(11,'rate',96000,NULL);
INSERT INTO "reason_param" VALUES(11,'quantum',1024,NULL);
INSERT INTO "reason_param" VALUES(12,'blocks',1024,NULL);
INSERT INTO "reason_param" VALUES(13,'blocks',1024,NULL);
INSERT INTO "reason_param" VALUES(14,'rate',96000,NULL);
INSERT INTO "reason_param" VALUES(14,'quantum',1024,NULL);
INSERT INTO "reason_param" VALUES(15,'blocks',1024,NULL);
INSERT INTO "reason_param" VALUES(16,'perInstanceKb',480,NULL);
INSERT INTO "reason_param" VALUES(16,'firstInstanceKb',3552,NULL);
INSERT INTO "reason_param" VALUES(16,'ceilingKb',393216,NULL);
INSERT INTO "reason_param" VALUES(16,'consoleCeilingKb',3145728,NULL);
INSERT INTO "reason_param" VALUES(16,'provisional',NULL,'yes');
INSERT INTO "reason_param" VALUES(17,'blocks',1024,NULL);
INSERT INTO "reason_param" VALUES(18,'perInstanceKb',480,NULL);
INSERT INTO "reason_param" VALUES(18,'firstInstanceKb',3552,NULL);
INSERT INTO "reason_param" VALUES(18,'ceilingKb',917504,NULL);
INSERT INTO "reason_param" VALUES(18,'consoleCeilingKb',7340032,NULL);
INSERT INTO "reason_param" VALUES(18,'provisional',NULL,'yes');
INSERT INTO "reason_param" VALUES(19,'rate',48000,NULL);
INSERT INTO "reason_param" VALUES(19,'quantum',128,NULL);
INSERT INTO "reason_param" VALUES(20,'rate',96000,NULL);
INSERT INTO "reason_param" VALUES(20,'quantum',1024,NULL);
INSERT INTO "reason_param" VALUES(21,'rate',48000,NULL);
INSERT INTO "reason_param" VALUES(21,'quantum',128,NULL);
INSERT INTO "reason_param" VALUES(22,'rate',48000,NULL);
INSERT INTO "reason_param" VALUES(22,'quantum',128,NULL);
INSERT INTO "reason_param" VALUES(27,'rate',48000,NULL);
INSERT INTO "reason_param" VALUES(27,'quantum',128,NULL);
INSERT INTO "reason_param" VALUES(28,'rate',96000,NULL);
INSERT INTO "reason_param" VALUES(28,'quantum',1024,NULL);
INSERT INTO "reason_param" VALUES(29,'rate',48000,NULL);
INSERT INTO "reason_param" VALUES(29,'quantum',128,NULL);
INSERT INTO "reason_param" VALUES(30,'rate',48000,NULL);
INSERT INTO "reason_param" VALUES(30,'quantum',128,NULL);
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
INSERT INTO "record" VALUES(1,1,NULL,'rpi5','custom','com.zamaudio.ZaMaximX2@unversioned-6d8dd5239ab3','plugin-qualify.qualification-record/1',NULL,NULL,NULL,NULL,NULL,NULL,'ZaMaximX2.clap','omx-layout/1','9d1cbe79a0be05bdd4a98230327e3d66020889e8b80a6a0193b537ccc8e9e48f',NULL,1,NULL,NULL,'2026-11-05T23:34:54+00:00',NULL,NULL,'20261105T233454Z-2def66-14dbe39d','plugin-hostd-probe 0.18.0','clap-qualify','rt_interpose.so','com.zamaudio.ZaMaximX2@unversioned-6d8dd5239ab3.custom.probe.json','ccfe78dda6d2821c504780ef11e5d0f7e6b9e19a4aaff4a200cef83851e9b21d',5526,'plugin-hostd.probe-protocol',1,'on-request','probe.ok',1,0,0.54,4,'aarch64','arm','3-4','1.5-2.5GHz',0,0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'2026-11-06T05:48:52+00:00','20261106T054852Z-321b52-e181bbce','plugin-hostd-probe 0.18.0','clap-qualify','2026-11-06T16:34:37.320Z','plugin-qualify 0.19.1','2026-11-05T23:34:54+00:00','20261105T233454Z-2def66-14dbe39d','plugin-hostd-probe 0.18.0','clap-qualify','rt_interpose.so',NULL,'2026-11-06T05:48:52+00:00','plugin-hostd-probe 0.18.0','clap-qualify');
INSERT INTO "record" VALUES(2,1,NULL,'rpi5','default','com.zamaudio.ZaMaximX2@unversioned-6d8dd5239ab3','plugin-qualify.qualification-record/1',NULL,NULL,NULL,NULL,NULL,NULL,'ZaMaximX2.clap','omx-layout/1','9d1cbe79a0be05bdd4a98230327e3d66020889e8b80a6a0193b537ccc8e9e48f',NULL,1,NULL,NULL,'2026-11-05T23:34:55+00:00',NULL,NULL,'20261105T233455Z-2def6b-412cc88b','plugin-hostd-probe 0.18.0','clap-qualify','rt_interpose.so','com.zamaudio.ZaMaximX2@unversioned-6d8dd5239ab3.default.probe.json','f6f3543a87a184fda4900b87148de449b4fa5469b10b8a4ec20acf739d21f9bd',5456,'plugin-hostd.probe-protocol',1,'on-request','probe.ok',1,0,0.54,4,'aarch64','arm','3-4','1.5-2.5GHz',0,0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'2026-11-06T16:34:37.320Z','plugin-qualify 0.19.1','2026-11-05T23:34:55+00:00','20261105T233455Z-2def6b-412cc88b','plugin-hostd-probe 0.18.0','clap-qualify','rt_interpose.so',NULL,NULL,NULL,NULL);
INSERT INTO "record" VALUES(3,2,NULL,'rpi5','default','http___aidadsp.cc_plugins_aidadsp-bundle_rt-neural-loader@3.0-dc8fb55c97a2','plugin-qualify.qualification-record/1',NULL,NULL,NULL,NULL,NULL,NULL,'AIDA-X_dsp.so','omx-layout/1','c3e72d515bca682cfa18bc621e6ce55be93616cb5ea66497c123e86d194506b3',NULL,NULL,'3.0',NULL,'2026-11-06T01:45:39+00:00',NULL,NULL,'20261106T014539Z-2f35ea-4019ccb7','plugin-hostd-probe 0.18.0','lv2_measure','rt_interpose.so','http___aidadsp.cc_plugins_aidadsp-bundle_rt-neural-loader@3.0-dc8fb55c97a2.default.probe.json','2e599801e5603605424eace66de54174938a0480384593ca08f2c3caac14cbfd',8219,'plugin-hostd.probe-protocol',1,'on-request','probe.ok',1,0,0.5,4,'aarch64','arm','3-4','1.5-2.5GHz',0,0,30,0,30,1,2,1,1,'omx-clap-host',1,NULL,'2026-11-06T16:14:49.907Z',1,'2026-11-06T05:41:29+00:00','20261106T054129Z-320295-79d595a7','plugin-hostd-probe 0.18.0','lv2_measure','2026-11-06T16:34:37.320Z','plugin-qualify 0.19.1','2026-11-06T01:45:39+00:00','20261106T014539Z-2f35ea-4019ccb7','plugin-hostd-probe 0.18.0','lv2_measure','rt_interpose.so','2026-11-06T16:14:49.907Z','2026-11-06T05:41:29+00:00','plugin-hostd-probe 0.18.0','lv2_measure');
INSERT INTO "record" VALUES(4,3,NULL,'rpi5','default','http___calf.sourceforge.net_plugins_Wavetable@unversioned-3f3fd8198cde','plugin-qualify.qualification-record/1',NULL,NULL,NULL,NULL,NULL,NULL,'calf.so','omx-layout/1','19f58cd40ac157a29b3724468cd02c03638c9fbb3a094c09433ec7ad5489d59b',NULL,NULL,NULL,NULL,'2026-11-06T00:18:27+00:00',NULL,NULL,'20261106T001827Z-2e8ba0-7456fef2','plugin-hostd-probe 0.18.0','lv2_measure',NULL,'http___calf.sourceforge.net_plugins_Wavetable@unversioned-3f3fd8198cde.default.probe.json','21ee1895dc8b83f26556d11368fe8cb865201ac9c0b9c808deba368d05f1aa2b',5153,'plugin-hostd.probe-protocol',1,'on-request','probe.crashed',0,0,0.58,4,'aarch64','arm','3-4','1.5-2.5GHz',0,0,NULL,NULL,NULL,NULL,NULL,NULL,0,'omx-clap-host',0,'omx-clap-host.no-jack-client',NULL,1,'2026-11-06T05:38:54+00:00','20261106T053854Z-31f219-85d7c6b0','plugin-hostd-probe 0.18.0','lv2_measure','2026-11-06T16:34:37.320Z','plugin-qualify 0.19.1','2026-11-06T00:18:27+00:00','20261106T001827Z-2e8ba0-7456fef2','plugin-hostd-probe 0.18.0','lv2_measure',NULL,NULL,'2026-11-06T05:38:54+00:00','plugin-hostd-probe 0.18.0','lv2_measure');
CREATE TABLE record_extension (            -- hostExtensions[]: the CLAP host extensions the run offered the plugin (section 6.2)
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord       INTEGER NOT NULL,
  extension TEXT NOT NULL CHECK (length(extension) > 0),   -- a name as the prober wrote it, e.g. clap.log
  PRIMARY KEY (record_id, ord),
  UNIQUE (record_id, extension)
) STRICT;
INSERT INTO "record_extension" VALUES(1,0,'clap.log');
INSERT INTO "record_extension" VALUES(1,1,'clap.thread-check');
INSERT INTO "record_extension" VALUES(1,2,'clap.latency');
INSERT INTO "record_extension" VALUES(1,3,'clap.params');
INSERT INTO "record_extension" VALUES(1,4,'clap.audio-ports');
INSERT INTO "record_extension" VALUES(1,5,'clap.state');
INSERT INTO "record_extension" VALUES(1,6,'clap.note-ports');
INSERT INTO "record_extension" VALUES(1,7,'clap.note-name');
INSERT INTO "record_extension" VALUES(1,8,'clap.voice-info');
INSERT INTO "record_extension" VALUES(1,9,'clap.event-registry');
INSERT INTO "record_extension" VALUES(1,10,'clap.timer-support');
INSERT INTO "record_extension" VALUES(1,11,'clap.posix-fd-support');
INSERT INTO "record_extension" VALUES(1,12,'clap.thread-pool');
INSERT INTO "record_extension" VALUES(1,13,'clap.tail');
INSERT INTO "record_extension" VALUES(1,14,'clap.surround/4');
INSERT INTO "record_extension" VALUES(1,15,'clap.ambisonic/3');
INSERT INTO "record_extension" VALUES(1,16,'clap.audio-ports-config');
INSERT INTO "record_extension" VALUES(1,17,'clap.preset-load/2');
INSERT INTO "record_extension" VALUES(1,18,'clap.track-info/1');
INSERT INTO "record_extension" VALUES(1,19,'clap.remote-controls/2');
INSERT INTO "record_extension" VALUES(2,0,'clap.log');
INSERT INTO "record_extension" VALUES(2,1,'clap.thread-check');
INSERT INTO "record_extension" VALUES(2,2,'clap.latency');
INSERT INTO "record_extension" VALUES(2,3,'clap.params');
INSERT INTO "record_extension" VALUES(2,4,'clap.audio-ports');
INSERT INTO "record_extension" VALUES(2,5,'clap.state');
INSERT INTO "record_extension" VALUES(2,6,'clap.note-ports');
INSERT INTO "record_extension" VALUES(2,7,'clap.note-name');
INSERT INTO "record_extension" VALUES(2,8,'clap.voice-info');
INSERT INTO "record_extension" VALUES(2,9,'clap.event-registry');
INSERT INTO "record_extension" VALUES(2,10,'clap.timer-support');
INSERT INTO "record_extension" VALUES(2,11,'clap.posix-fd-support');
INSERT INTO "record_extension" VALUES(2,12,'clap.thread-pool');
INSERT INTO "record_extension" VALUES(2,13,'clap.tail');
INSERT INTO "record_extension" VALUES(2,14,'clap.surround/4');
INSERT INTO "record_extension" VALUES(2,15,'clap.ambisonic/3');
INSERT INTO "record_extension" VALUES(2,16,'clap.audio-ports-config');
CREATE TABLE record_file (                 -- binary.files[]: the per-file list the pin matches on (section 3.7)
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord       INTEGER NOT NULL,              -- the list's order: ascending by path, bytewise (section 3.7)
  path      TEXT NOT NULL CHECK (length(path) > 0 AND path NOT GLOB '/*' AND substr(path, -1) <> '/' AND instr(path, '//') = 0 AND instr('/' || path || '/', '/./') = 0 AND instr('/' || path || '/', '/../') = 0),   -- relative to the item's root, as the pin names it (section 3.7)
  sha256    TEXT NOT NULL CHECK (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
  PRIMARY KEY (record_id, ord),
  UNIQUE (record_id, path)
) STRICT;
INSERT INTO "record_file" VALUES(1,0,'ZaMaximX2.clap','6d8dd5239ab38df8c4682d2f97681a5cf2d1d98c6b8390ec117151539cc71566');
INSERT INTO "record_file" VALUES(2,0,'ZaMaximX2.clap','6d8dd5239ab38df8c4682d2f97681a5cf2d1d98c6b8390ec117151539cc71566');
INSERT INTO "record_file" VALUES(3,0,'AIDA-X_dsp.so','dc8fb55c97a2f05125169a036113a7cceaf00de740d847b662f0990792dd1c38');
INSERT INTO "record_file" VALUES(3,1,'AIDA-X_dsp.ttl','f5fa96fa5d92e3d8e19aac6efcdde132714ce453c9b52f53d66030352e99fc95');
INSERT INTO "record_file" VALUES(3,2,'manifest.ttl','433a4ace95e26daf0a83780cac04116ce95dfe943c2aa90e6d4c6c4b87165dc4');
INSERT INTO "record_file" VALUES(4,0,'Wavetable.ttl','0dab4315086b303a22678f27b39737aa77fd77dc36d2954d8f10e6502cf77ab7');
INSERT INTO "record_file" VALUES(4,1,'calf.so','3f3fd8198cde3ac9962fe134053253b7320befc53e2e4ba91252ee0b644dfd81');
INSERT INTO "record_file" VALUES(4,2,'manifest.ttl','6395f08c3539ec75120476b9c515d29d6e173d4d7ee65571e38e800ba38e5586');
INSERT INTO "record_file" VALUES(4,3,'presets-Wavetable.ttl','6b73549dad9cd8de1b82a4c716ff638f949ad3dc159111d12cee1c55de3531d8');
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
CREATE TABLE record_version (              -- adapter.versions, rejudged.figures.adapter.versions
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  rejudged  INTEGER NOT NULL CHECK (rejudged IN (0, 1)),   -- 0: adapter.versions, 1: rejudged.figures.adapter.versions
  name      TEXT NOT NULL,
  version   TEXT NOT NULL,
  PRIMARY KEY (record_id, rejudged, name)
) STRICT;
INSERT INTO "record_version" VALUES(3,0,'omx-clap-host','0.30.0');
INSERT INTO "record_version" VALUES(3,0,'plugin-hostd','0.19.0');
INSERT INTO "record_version" VALUES(3,1,'omx-clap-host','0.30.0');
INSERT INTO "record_version" VALUES(3,1,'plugin-hostd','0.19.0');
CREATE TABLE rejudged_owe (                -- rejudged.owes[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  code TEXT NOT NULL CHECK ((length(code) > 0 AND instr(code, ' ') = 0 AND instr(code, char(9)) = 0 AND instr(code, char(10)) = 0)),
  measurement TEXT NOT NULL CHECK ((length(measurement) > 0 AND instr(measurement, ' ') = 0 AND instr(measurement, char(9)) = 0 AND instr(measurement, char(10)) = 0)),
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
  pool_dsp_load_off REAL, pool_dsp_load_on REAL, pool_xruns_off INTEGER, pool_xruns_on INTEGER,   -- the pool step's graph load and xruns, off and on; NULL: absent
  PRIMARY KEY (record_id, ord)
) STRICT;
INSERT INTO "run_step" VALUES(1,0,'scan','ok',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(1,1,'describe','ok',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(1,2,'probe','probe.ok',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(1,3,'rt-safety','unsafe',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(1,4,'isolated','isolated',NULL,6.333333333333333,960,0,0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(1,5,'pool','not-asked',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(2,0,'scan','ok',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(2,1,'describe','ok',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(2,2,'probe','probe.ok',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(2,3,'rt-safety','safe',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(3,0,'scan','ok',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(3,1,'describe','ok',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(3,2,'probe','probe.ok',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(3,3,'rt-safety','safe',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(3,4,'isolated','isolated',NULL,3.0,0,0,0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(4,0,'scan','ok',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(4,1,'describe','ok',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(4,2,'probe','probe.crashed',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "run_step" VALUES(4,3,'isolated','isolated',NULL,7.666666666666667,0,1,2,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
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
CREATE TABLE store_domain (                -- each domain the words were checked against, at its info.version
  domain  TEXT PRIMARY KEY,                -- 'qualification', 'machine'
  version TEXT NOT NULL
) STRICT;
INSERT INTO "store_domain" VALUES('hosting','0.34.1');
INSERT INTO "store_domain" VALUES('machine','1.1.0');
INSERT INTO "store_domain" VALUES('plugin-db','1.0.0');
INSERT INTO "store_domain" VALUES('probe','1.0.0');
INSERT INTO "store_domain" VALUES('qualification','1.4.0');
CREATE TABLE store_info (
  one            INTEGER PRIMARY KEY CHECK (one = 1),
  user_layer     INTEGER NOT NULL CHECK (user_layer IN (0, 1)),   -- 0: the base, 1: a user layer
  record_schema  TEXT NOT NULL,            -- 'plugin-qualify.qualification-record/1'
  built_from     TEXT CHECK (built_from IS NULL OR (length(built_from) = 40 AND built_from NOT GLOB '*[^0-9a-f]*'))
                                           -- base: the commit of this repository (section 5); user: NULL
) STRICT;
INSERT INTO "store_info" VALUES(1,1,'plugin-qualify.qualification-record/1',NULL);
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
INSERT INTO "tier" VALUES(1,'isolated','omx-clap-host',1,0,'conditional','hosting.rt-safety.violations-in-run',1);
INSERT INTO "tier" VALUES(2,'inProcess','openmixer-console',1,0,'unknown','hosting.memory.unmeasured',NULL);
INSERT INTO "tier" VALUES(3,'inProcess','openmixer-console',1,0,'unknown','hosting.memory.unmeasured',NULL);
INSERT INTO "tier" VALUES(3,'isolated','omx-clap-host',1,1,'suitable',NULL,NULL);
INSERT INTO "tier" VALUES(4,'inProcess','openmixer-console',0,0,'unknown','probe.crashed',NULL);
INSERT INTO "tier" VALUES(4,'isolated','omx-clap-host',0,0,'unknown','probe.crashed',NULL);
CREATE TABLE tier_offered (                -- tiers.offeredOn[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord       INTEGER NOT NULL,
  tier      TEXT NOT NULL CHECK ((length(tier) > 0 AND instr(tier, ' ') = 0 AND instr(tier, char(9)) = 0 AND instr(tier, char(10)) = 0)),
  PRIMARY KEY (record_id, ord)
) STRICT;
INSERT INTO "tier_offered" VALUES(1,0,'isolated');
INSERT INTO "tier_offered" VALUES(3,0,'isolated');
CREATE TABLE unmeasured (                  -- measurements.unmeasured[]
  record_id INTEGER NOT NULL REFERENCES record ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  dimension TEXT NOT NULL CHECK ((length(dimension) > 0 AND instr(dimension, ' ') = 0 AND instr(dimension, char(9)) = 0 AND instr(dimension, char(10)) = 0)),
  code TEXT NOT NULL CHECK ((length(code) > 0 AND instr(code, ' ') = 0 AND instr(code, char(9)) = 0 AND instr(code, char(10)) = 0)),
  rate INTEGER NOT NULL, quantum INTEGER NOT NULL,
  PRIMARY KEY (record_id, ord)
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
INSERT INTO "verdict" VALUES(1,0,'omx-clap-host',1,'conditional',0,'isolated','declaration','hosting.rt-safety.violations-in-run');
INSERT INTO "verdict" VALUES(1,1,'openmixer-pi-4gb',1,'conditional',0,'isolated','declaration','hosting.rt-safety.violations-in-run');
INSERT INTO "verdict" VALUES(1,2,'openmixer-pi-8gb',1,'conditional',0,'isolated','declaration','hosting.rt-safety.violations-in-run');
INSERT INTO "verdict" VALUES(2,0,'openmixer-console',1,'unknown',0,'isolated','declaration','hosting.memory.unmeasured');
INSERT INTO "verdict" VALUES(3,0,'omx-clap-host',1,'suitable',1,'isolated','run',NULL);
INSERT INTO "verdict" VALUES(3,1,'openmixer-console',1,'unknown',0,'isolated','declaration','hosting.memory.unmeasured');
INSERT INTO "verdict" VALUES(3,2,'openmixer-pi-4gb',1,'conditional',0,'isolated','run','hosting.memory.within-provisional-ceiling');
INSERT INTO "verdict" VALUES(3,3,'openmixer-pi-8gb',1,'conditional',0,'isolated','run','hosting.memory.within-provisional-ceiling');
INSERT INTO "verdict" VALUES(4,0,'omx-clap-host',0,'unknown',0,'isolated','declaration','probe.crashed');
INSERT INTO "verdict" VALUES(4,1,'openmixer-console',0,'unknown',0,'isolated','declaration','probe.crashed');
INSERT INTO "verdict" VALUES(4,2,'openmixer-pi-4gb',0,'unknown',0,'isolated','declaration','probe.crashed');
INSERT INTO "verdict" VALUES(4,3,'openmixer-pi-8gb',0,'unknown',0,'isolated','declaration','probe.crashed');
CREATE TABLE word_check (                  -- the owner domain items that hold the words of a column
  tbl    TEXT NOT NULL,
  col    TEXT NOT NULL,
  domain TEXT NOT NULL REFERENCES store_domain,
  item   TEXT NOT NULL,                    -- a components.schemas name, e.g. QUALIFICATION_MEASUREMENT_VERDICT_RATINGS
  PRIMARY KEY (tbl, col, domain, item)     -- a word is valid when one of its column's items holds it
) STRICT;
INSERT INTO "word_check" VALUES('adapter_cell','code','probe','PROBE_SIGNALS');
INSERT INTO "word_check" VALUES('adapter_cell','code','qualification','QUALIFICATION_ADAPTER_CODE_KINDS');
INSERT INTO "word_check" VALUES('adapter_cell','code','qualification','QUALIFICATION_ADAPTER_HOSTS');
INSERT INTO "word_check" VALUES('adapter_cell_param','name','qualification','QUALIFICATION_REASON_PARAMS');
INSERT INTO "word_check" VALUES('adapter_cell_param','word','qualification','QUALIFICATION_REASON_PARAM_WORDS');
INSERT INTO "word_check" VALUES('adapter_param','name','qualification','QUALIFICATION_REASON_PARAMS');
INSERT INTO "word_check" VALUES('adapter_param','word','qualification','QUALIFICATION_REASON_PARAM_WORDS');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_CLAP_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_COST_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_FEATURES_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_IDLE_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_LATENCY_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_MEMORY_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_OUTPUT_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_OVERRIDE_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_PATCH_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_PRESET_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_PROVENANCE_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_REALISED_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_RESOURCE_HINTS_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_RT_SAFETY_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_STABILITY_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_STATE_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_TOPOLOGY_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_WINDOW_CODES');
INSERT INTO "word_check" VALUES('cell','latency_code','hosting','HOSTING_WORKER_CODES');
INSERT INTO "word_check" VALUES('cell','latency_unmeasured_reason','qualification','QUALIFICATION_MEASUREMENT_UNMEASURED_REASONS');
INSERT INTO "word_check" VALUES('cell','mem_basis','qualification','QUALIFICATION_MEASUREMENT_VOICE_BASES');
INSERT INTO "word_check" VALUES('cell','mem_limit_mechanism','qualification','QUALIFICATION_MEMORY_LIMIT_MECHANISMS');
INSERT INTO "word_check" VALUES('cell','mem_unmeasured_reason','qualification','QUALIFICATION_MEASUREMENT_UNMEASURED_REASONS');
INSERT INTO "word_check" VALUES('cell','note_sweep_dialect','qualification','QUALIFICATION_NOTE_SWEEP_DIALECTS');
INSERT INTO "word_check" VALUES('cell','outcome','probe','PROBE_OUTCOMES');
INSERT INTO "word_check" VALUES('cell','outcome','qualification','QUALIFICATION_MEMORY_BOUND_OUTCOMES');
INSERT INTO "word_check" VALUES('cell','voices_basis','qualification','QUALIFICATION_MEASUREMENT_VOICE_BASES');
INSERT INTO "word_check" VALUES('cost_entry','host','qualification','QUALIFICATION_HOST_PROFILES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_CLAP_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_COST_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_FEATURES_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_IDLE_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_LATENCY_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_MEMORY_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_OUTPUT_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_OVERRIDE_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_PATCH_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_PRESET_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_PROVENANCE_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_REALISED_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_RESOURCE_HINTS_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_RT_SAFETY_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_STABILITY_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_STATE_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_TOPOLOGY_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_WINDOW_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','hosting','HOSTING_WORKER_CODES');
INSERT INTO "word_check" VALUES('history_blocked','code','probe','PROBE_OUTCOMES');
INSERT INTO "word_check" VALUES('history_blocked','code','probe','PROBE_SIGNALS');
INSERT INTO "word_check" VALUES('history_blocked','code','qualification','QUALIFICATION_ADAPTER_CODE_KINDS');
INSERT INTO "word_check" VALUES('history_blocked','code','qualification','QUALIFICATION_ADAPTER_HOSTS');
INSERT INTO "word_check" VALUES('history_blocked','code','qualification','QUALIFICATION_HISTORY_BLOCKERS');
INSERT INTO "word_check" VALUES('history_blocked','code','qualification','QUALIFICATION_MEMORY_BOUND_OUTCOMES');
INSERT INTO "word_check" VALUES('history_verdict','adjusted','qualification','QUALIFICATION_PIN_VERDICTS');
INSERT INTO "word_check" VALUES('history_verdict','host','qualification','QUALIFICATION_HOST_PROFILES');
INSERT INTO "word_check" VALUES('history_verdict','measured','qualification','QUALIFICATION_PIN_VERDICTS');
INSERT INTO "word_check" VALUES('history_verdict','move','qualification','QUALIFICATION_HISTORY_MOVES');
INSERT INTO "word_check" VALUES('history_verdict','reason','qualification','QUALIFICATION_HISTORY_REASONS');
INSERT INTO "word_check" VALUES('memory_run_cell','outcome','probe','PROBE_OUTCOMES');
INSERT INTO "word_check" VALUES('memory_run_cell','outcome','qualification','QUALIFICATION_MEMORY_BOUND_OUTCOMES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_CLAP_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_COST_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_FEATURES_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_IDLE_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_LATENCY_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_MEMORY_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_OUTPUT_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_OVERRIDE_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_PATCH_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_PRESET_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_PROVENANCE_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_REALISED_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_RESOURCE_HINTS_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_RT_SAFETY_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_STABILITY_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_STATE_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_TOPOLOGY_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_WINDOW_CODES');
INSERT INTO "word_check" VALUES('not_measured','code','hosting','HOSTING_WORKER_CODES');
INSERT INTO "word_check" VALUES('not_measured','dimension','qualification','QUALIFICATION_MEASUREMENT_DIMENSIONS');
INSERT INTO "word_check" VALUES('plugin','format','plugin-db','PLUGIN_DB_ADDRESS_FORMATS');
INSERT INTO "word_check" VALUES('probe_end','outcome','probe','PROBE_OUTCOMES');
INSERT INTO "word_check" VALUES('probe_end','outcome','qualification','QUALIFICATION_MEMORY_BOUND_OUTCOMES');
INSERT INTO "word_check" VALUES('probe_end','signal','probe','PROBE_SIGNALS');
INSERT INTO "word_check" VALUES('probe_end','step','probe','PROBE_STEPS');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_CLAP_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_COST_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_FEATURES_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_IDLE_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_LATENCY_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_MEMORY_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_OUTPUT_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_OVERRIDE_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_PATCH_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_PRESET_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_PROVENANCE_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_REALISED_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_RESOURCE_HINTS_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_RT_SAFETY_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_STABILITY_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_STATE_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_TOPOLOGY_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_WINDOW_CODES');
INSERT INTO "word_check" VALUES('reason','code','hosting','HOSTING_WORKER_CODES');
INSERT INTO "word_check" VALUES('reason','code','probe','PROBE_OUTCOMES');
INSERT INTO "word_check" VALUES('reason','code','probe','PROBE_SIGNALS');
INSERT INTO "word_check" VALUES('reason','code','qualification','QUALIFICATION_ADAPTER_CODE_KINDS');
INSERT INTO "word_check" VALUES('reason','code','qualification','QUALIFICATION_ADAPTER_HOSTS');
INSERT INTO "word_check" VALUES('reason','code','qualification','QUALIFICATION_MEMORY_BOUND_OUTCOMES');
INSERT INTO "word_check" VALUES('reason','dimension','qualification','QUALIFICATION_MEASUREMENT_DIMENSIONS');
INSERT INTO "word_check" VALUES('reason','rating','qualification','QUALIFICATION_MEASUREMENT_VERDICT_RATINGS');
INSERT INTO "word_check" VALUES('reason_param','name','qualification','QUALIFICATION_REASON_PARAMS');
INSERT INTO "word_check" VALUES('reason_param','word','qualification','QUALIFICATION_REASON_PARAM_WORDS');
INSERT INTO "word_check" VALUES('record','adapter_code','probe','PROBE_SIGNALS');
INSERT INTO "word_check" VALUES('record','adapter_code','qualification','QUALIFICATION_ADAPTER_CODE_KINDS');
INSERT INTO "word_check" VALUES('record','adapter_code','qualification','QUALIFICATION_ADAPTER_HOSTS');
INSERT INTO "word_check" VALUES('record','adapter_host','qualification','QUALIFICATION_ADAPTER_HOSTS');
INSERT INTO "word_check" VALUES('record','host_class','qualification','QUALIFICATION_HOST_CLASSES');
INSERT INTO "word_check" VALUES('record','mc_arch','machine','MACHINE_ARCHES');
INSERT INTO "word_check" VALUES('record','mc_clock_band','machine','MACHINE_CLOCK_BANDS');
INSERT INTO "word_check" VALUES('record','mc_core_band','machine','MACHINE_CORE_BANDS');
INSERT INTO "word_check" VALUES('record','mc_family','machine','MACHINE_FAMILIES');
INSERT INTO "word_check" VALUES('record','offer','qualification','QUALIFICATION_OFFERS');
INSERT INTO "word_check" VALUES('record','pkg_arch','qualification','QUALIFICATION_PACKAGE_ARCHES');
INSERT INTO "word_check" VALUES('record','pkg_distro','qualification','QUALIFICATION_PACKAGE_DISTROS');
INSERT INTO "word_check" VALUES('record','pkg_format','qualification','QUALIFICATION_PACKAGE_FORMATS');
INSERT INTO "word_check" VALUES('record','probe_outcome','probe','PROBE_OUTCOMES');
INSERT INTO "word_check" VALUES('record','probe_outcome','qualification','QUALIFICATION_MEMORY_BOUND_OUTCOMES');
INSERT INTO "word_check" VALUES('record','probe_reason','probe','PROBE_REASONS');
INSERT INTO "word_check" VALUES('record_set','host_class','qualification','QUALIFICATION_HOST_CLASSES');
INSERT INTO "word_check" VALUES('record_set','host_profile','qualification','QUALIFICATION_HOST_PROFILES');
INSERT INTO "word_check" VALUES('record_set','tier','qualification','QUALIFICATION_SET_TIERS');
INSERT INTO "word_check" VALUES('rejudged_owe','code','qualification','QUALIFICATION_REJUDGE_OWES');
INSERT INTO "word_check" VALUES('rejudged_owe','measurement','qualification','QUALIFICATION_REJUDGE_MEASUREMENTS');
INSERT INTO "word_check" VALUES('run_step','code','qualification','QUALIFICATION_STEP_CODES');
INSERT INTO "word_check" VALUES('run_step','result','probe','PROBE_OUTCOMES');
INSERT INTO "word_check" VALUES('run_step','result','qualification','QUALIFICATION_MEMORY_BOUND_OUTCOMES');
INSERT INTO "word_check" VALUES('run_step','result','qualification','QUALIFICATION_STEP_RESULTS');
INSERT INTO "word_check" VALUES('run_step','step','qualification','QUALIFICATION_RUN_STEPS');
INSERT INTO "word_check" VALUES('set_setting','key','qualification','QUALIFICATION_SYNC_SETTINGS');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_CLAP_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_COST_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_FEATURES_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_IDLE_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_LATENCY_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_MEMORY_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_OUTPUT_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_OVERRIDE_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_PATCH_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_PRESET_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_PROVENANCE_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_REALISED_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_RESOURCE_HINTS_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_RT_SAFETY_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_STABILITY_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_STATE_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_TOPOLOGY_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_WINDOW_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','hosting','HOSTING_WORKER_CODES');
INSERT INTO "word_check" VALUES('tier','deciding','probe','PROBE_OUTCOMES');
INSERT INTO "word_check" VALUES('tier','deciding','probe','PROBE_SIGNALS');
INSERT INTO "word_check" VALUES('tier','deciding','qualification','QUALIFICATION_ADAPTER_CODE_KINDS');
INSERT INTO "word_check" VALUES('tier','deciding','qualification','QUALIFICATION_ADAPTER_HOSTS');
INSERT INTO "word_check" VALUES('tier','deciding','qualification','QUALIFICATION_MEMORY_BOUND_OUTCOMES');
INSERT INTO "word_check" VALUES('tier','host','qualification','QUALIFICATION_HOST_PROFILES');
INSERT INTO "word_check" VALUES('tier','rating','qualification','QUALIFICATION_MEASUREMENT_VERDICT_RATINGS');
INSERT INTO "word_check" VALUES('tier','tier','qualification','QUALIFICATION_RECORD_TIERS');
INSERT INTO "word_check" VALUES('tier_offered','tier','qualification','QUALIFICATION_VERDICT_HOSTINGS');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_CLAP_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_COST_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_FEATURES_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_IDLE_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_LATENCY_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_MEMORY_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_OUTPUT_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_OVERRIDE_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_PATCH_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_PRESET_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_PROVENANCE_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_REALISED_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_RESOURCE_HINTS_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_RT_SAFETY_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_STABILITY_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_STATE_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_TOPOLOGY_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_WINDOW_CODES');
INSERT INTO "word_check" VALUES('unmeasured','code','hosting','HOSTING_WORKER_CODES');
INSERT INTO "word_check" VALUES('unmeasured','dimension','qualification','QUALIFICATION_MEASUREMENT_DIMENSIONS');
INSERT INTO "word_check" VALUES('verdict','arm','qualification','QUALIFICATION_VERDICT_ARMS');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_CLAP_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_COST_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_FEATURES_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_IDLE_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_LATENCY_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_MEMORY_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_OUTPUT_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_OVERRIDE_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_PATCH_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_PRESET_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_PROVENANCE_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_REALISED_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_RESOURCE_HINTS_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_RT_SAFETY_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_STABILITY_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_STATE_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_TOPOLOGY_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_WINDOW_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','hosting','HOSTING_WORKER_CODES');
INSERT INTO "word_check" VALUES('verdict','deciding','probe','PROBE_OUTCOMES');
INSERT INTO "word_check" VALUES('verdict','deciding','probe','PROBE_SIGNALS');
INSERT INTO "word_check" VALUES('verdict','deciding','qualification','QUALIFICATION_ADAPTER_CODE_KINDS');
INSERT INTO "word_check" VALUES('verdict','deciding','qualification','QUALIFICATION_ADAPTER_HOSTS');
INSERT INTO "word_check" VALUES('verdict','deciding','qualification','QUALIFICATION_MEMORY_BOUND_OUTCOMES');
INSERT INTO "word_check" VALUES('verdict','host','qualification','QUALIFICATION_HOST_PROFILES');
INSERT INTO "word_check" VALUES('verdict','hosting','qualification','QUALIFICATION_VERDICT_HOSTINGS');
INSERT INTO "word_check" VALUES('verdict','rating','qualification','QUALIFICATION_MEASUREMENT_VERDICT_RATINGS');
CREATE INDEX record_plugin  ON record (plugin_id, offer, host_class);
CREATE INDEX record_package ON record (pkg_format, pkg_name, pkg_version, pkg_release, pkg_distro, pkg_arch);
CREATE INDEX record_binary  ON record (binary_path);
CREATE INDEX record_file_sha256 ON record_file (sha256);
CREATE UNIQUE INDEX reason_of_verdict ON reason (record_id, verdict_ord, ord) WHERE verdict_ord IS NOT NULL;
CREATE UNIQUE INDEX reason_of_cost    ON reason (record_id, cost_ord, ord)    WHERE cost_ord IS NOT NULL;
CREATE TRIGGER record_set_by_layer BEFORE INSERT ON record
WHEN (NEW.set_id IS NULL) <> ((SELECT user_layer FROM store_info) = 1)
BEGIN SELECT RAISE(ABORT, 'record.set_id: NULL exactly in the user layer'); END;
COMMIT;
