-- SPDX-License-Identifier: GPL-3.0-or-later
-- Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
-- The qualification store from user_version 1 to 2 (this repository's qualification store spec, section 3.6).
--
-- user_version 1 is the DDL of v2026112401, the dated packages a device holds. Its tables are those of 2 less
-- cell_voice_point, and its columns those of 2 less record.adapter_content, .adapter_loaded, .adapter_refused,
-- cost_entry.voices_basis, .voices_capacity, .voices_held and cell.rt_events; cell gains two table CHECKs. No column
-- of 1 is gone or renamed. The runner (tools/qualification_db.py migrate, the reader's migrate_user) takes a backup
-- copy first, sets foreign_keys OFF and legacy_alter_table ON, and runs this script in one transaction: the part
-- before the line `-- @schema` moves every table of 1 aside, the runner then runs schema/qualification.sql, the part
-- after it copies every row into the tables of 2 and drops the tables of 1. Before COMMIT the runner checks the
-- foreign keys and every word against the installed domains; a word none of its column's items holds is refused by
-- name and the layer is left as it was.
--
-- The words. No word of 1 is renamed in 2: every word the items of a word column held at user_version 1 (the
-- domains of plugin-hostd, plugin-hostd-protocol, plugin-db and omx-clap-core main at 2026-11-24) is a word of the
-- same items in the domains of 2; 2 only adds words. So the mapping below is empty, and word_check gains the four
-- items 2 reads that 1 did not. store_domain names each domain at 0.1.0: every domain started again at 0.1.0
-- (owner, 2026-11-25), and the words of 1 are all words of each domain at 0.1.0.

DROP INDEX record_plugin;
DROP INDEX record_package;
DROP INDEX record_binary;
DROP INDEX record_file_sha256;
DROP INDEX reason_of_verdict;
DROP INDEX reason_of_cost;
DROP TRIGGER record_set_by_layer;
ALTER TABLE store_info RENAME TO v1_store_info;
ALTER TABLE store_domain RENAME TO v1_store_domain;
ALTER TABLE word_check RENAME TO v1_word_check;
ALTER TABLE plugin RENAME TO v1_plugin;
ALTER TABLE record_set RENAME TO v1_record_set;
ALTER TABLE set_package RENAME TO v1_set_package;
ALTER TABLE set_setting RENAME TO v1_set_setting;
ALTER TABLE record RENAME TO v1_record;
ALTER TABLE record_file RENAME TO v1_record_file;
ALTER TABLE record_extension RENAME TO v1_record_extension;
ALTER TABLE record_version RENAME TO v1_record_version;
ALTER TABLE verdict RENAME TO v1_verdict;
ALTER TABLE cost_entry RENAME TO v1_cost_entry;
ALTER TABLE reason RENAME TO v1_reason;
ALTER TABLE reason_param RENAME TO v1_reason_param;
ALTER TABLE tier RENAME TO v1_tier;
ALTER TABLE tier_offered RENAME TO v1_tier_offered;
ALTER TABLE cell RENAME TO v1_cell;
ALTER TABLE cell_event RENAME TO v1_cell_event;
ALTER TABLE claim RENAME TO v1_claim;
ALTER TABLE feature_required RENAME TO v1_feature_required;
ALTER TABLE unmeasured RENAME TO v1_unmeasured;
ALTER TABLE not_measured RENAME TO v1_not_measured;
ALTER TABLE record_history RENAME TO v1_record_history;
ALTER TABLE history_unknown_key RENAME TO v1_history_unknown_key;
ALTER TABLE history_verdict RENAME TO v1_history_verdict;
ALTER TABLE history_blocked RENAME TO v1_history_blocked;
ALTER TABLE run_step RENAME TO v1_run_step;
ALTER TABLE probe_end RENAME TO v1_probe_end;
ALTER TABLE adapter_cell RENAME TO v1_adapter_cell;
ALTER TABLE adapter_param RENAME TO v1_adapter_param;
ALTER TABLE adapter_cell_param RENAME TO v1_adapter_cell_param;
ALTER TABLE memory_run_cell RENAME TO v1_memory_run_cell;
ALTER TABLE rejudged_owe RENAME TO v1_rejudged_owe;

-- @schema

INSERT INTO store_info (one, user_layer, record_schema, built_from)
  SELECT one, user_layer, record_schema, built_from FROM v1_store_info;
INSERT INTO store_domain (domain, version) VALUES
  ('hosting', '0.1.0'),   ('machine', '0.1.0'),   ('plugin-db', '0.1.0'),   ('probe', '0.1.0'),   ('qualification',
      '0.1.0');
INSERT INTO word_check (tbl, col, domain, item)
  SELECT tbl, col, domain, item FROM v1_word_check;
INSERT INTO word_check (tbl, col, domain, item) VALUES
  ('adapter_cell_param', 'word', 'qualification', 'QUALIFICATION_MEASUREMENT_UNMEASURED_REASONS'),   ('adapter_param',
      'word', 'qualification', 'QUALIFICATION_MEASUREMENT_UNMEASURED_REASONS'),   ('reason_param', 'word',
      'qualification', 'QUALIFICATION_MEASUREMENT_UNMEASURED_REASONS'),   ('cost_entry', 'voices_basis',
      'qualification', 'QUALIFICATION_MEASUREMENT_VOICE_BASES');
INSERT INTO plugin (plugin_id, sha256, format, uri)
  SELECT plugin_id, sha256, format, uri FROM v1_plugin;
INSERT INTO record_set (set_id, host_class, name, schema, tier, host_profile, measured, date, package_name,
    package_version)
  SELECT set_id, host_class, name, schema, tier, host_profile, measured, date, package_name, package_version FROM
      v1_record_set;
INSERT INTO set_package (set_id, pass, name, version)
  SELECT set_id, pass, name, version FROM v1_set_package;
INSERT INTO set_setting (set_id, key, value)
  SELECT set_id, key, value FROM v1_set_setting;
INSERT INTO record (record_id, plugin_id, set_id, host_class, offer, name, schema, pkg_format, pkg_name, pkg_version,
    pkg_release, pkg_distro, pkg_arch, binary_path, layout_scheme, layout_sha256, unpinnable, host_extensions,
    tested_version, plugin_name, measured_at, latency_line_ms, rules, run_id, tool_runner, tool_child, tool_interposer,
    probe_file, probe_sha256, probe_bytes, probe_protocol, probe_protocol_version, probe_reason, probe_outcome,
    probe_complete, probe_meets_protocol, probe_loadavg1, probe_cores, mc_arch, mc_family, mc_core_band, mc_clock_band,
    mc_preempt_rt, mc_cstates_limited, lifecycle_cycles, lifecycle_failed, lifecycle_instantiated, threads_before,
    threads_after_first_instantiate, threads_after_all_freed, adapter_admitted, adapter_host, adapter_measured,
    adapter_code, adapter_measured_at, adapter_params, memory_run_measured_at, memory_run_id, memory_run_runner,
    memory_run_child, rejudged_at, rejudged_by, rejudged_measured_at, rejudged_run_id, rejudged_runner, rejudged_child,
    rejudged_interposer, rejudged_adapter_measured_at, rejudged_memory_measured_at, rejudged_memory_runner,
    rejudged_memory_child)
  SELECT record_id, plugin_id, set_id, host_class, offer, name, schema, pkg_format, pkg_name, pkg_version, pkg_release,
      pkg_distro, pkg_arch, binary_path, layout_scheme, layout_sha256, unpinnable, host_extensions, tested_version,
      plugin_name, measured_at, latency_line_ms, rules, run_id, tool_runner, tool_child, tool_interposer, probe_file,
      probe_sha256, probe_bytes, probe_protocol, probe_protocol_version, probe_reason, probe_outcome, probe_complete,
      probe_meets_protocol, probe_loadavg1, probe_cores, mc_arch, mc_family, mc_core_band, mc_clock_band, mc_preempt_rt,
      mc_cstates_limited, lifecycle_cycles, lifecycle_failed, lifecycle_instantiated, threads_before,
      threads_after_first_instantiate, threads_after_all_freed, adapter_admitted, adapter_host, adapter_measured,
      adapter_code, adapter_measured_at, adapter_params, memory_run_measured_at, memory_run_id, memory_run_runner,
      memory_run_child, rejudged_at, rejudged_by, rejudged_measured_at, rejudged_run_id, rejudged_runner,
      rejudged_child, rejudged_interposer, rejudged_adapter_measured_at, rejudged_memory_measured_at,
      rejudged_memory_runner, rejudged_memory_child FROM v1_record;
INSERT INTO record_file (record_id, ord, path, sha256)
  SELECT record_id, ord, path, sha256 FROM v1_record_file;
INSERT INTO record_extension (record_id, ord, extension)
  SELECT record_id, ord, extension FROM v1_record_extension;
INSERT INTO record_version (record_id, rejudged, name, version)
  SELECT record_id, rejudged, name, version FROM v1_record_version;
INSERT INTO verdict (record_id, ord, host, measured, rating, qualified, hosting, arm, deciding)
  SELECT record_id, ord, host, measured, rating, qualified, hosting, arm, deciding FROM v1_verdict;
INSERT INTO cost_entry (record_id, ord, host, rate, quantum)
  SELECT record_id, ord, host, rate, quantum FROM v1_cost_entry;
INSERT INTO reason (reason_id, record_id, verdict_ord, cost_ord, ord, dimension, rating, code)
  SELECT reason_id, record_id, verdict_ord, cost_ord, ord, dimension, rating, code FROM v1_reason;
INSERT INTO reason_param (reason_id, name, number, word)
  SELECT reason_id, name, number, word FROM v1_reason_param;
INSERT INTO tier (record_id, tier, host, measured, qualified, rating, deciding, runs_alone)
  SELECT record_id, tier, host, measured, qualified, rating, deciding, runs_alone FROM v1_tier;
INSERT INTO tier_offered (record_id, ord, tier)
  SELECT record_id, ord, tier FROM v1_tier_offered;
INSERT INTO cell (record_id, ord, rate, quantum, outcome, latency_declared_frames, latency_measured_frames, latency_ms,
    latency_code, latency_unmeasured_reason, cost_median, cost_percentile_p, cost_percentile_value, cost_blocks,
    cost_warmup_blocks, voices_basis, voices_capacity, voices_held, mem_after_instantiate_kb, mem_after_activate_kb,
    mem_at_rest_kb, mem_second_instance_kb, mem_first_instance_kb, mem_per_instance_kb, mem_notes_held_kb, mem_basis,
    mem_unmeasured_reason, mem_limit_bytes, mem_limit_mechanism, rt_interposer, rt_swept, rt_sweep_applicable,
    rt_blocks, rt_allocations, rt_locks, rt_syscalls, rt_thread_violations, rt_process_errors, rt_own_threads,
    rt_other_allocations, rt_other_locks, rt_other_syscalls, note_sweep_applicable, note_sweep_dialect,
    note_sweep_allocations, note_sweep_locks, note_sweep_syscalls, rt_events)
  SELECT record_id, ord, rate, quantum, outcome, latency_declared_frames, latency_measured_frames, latency_ms,
      latency_code, latency_unmeasured_reason, cost_median, cost_percentile_p, cost_percentile_value, cost_blocks,
      cost_warmup_blocks, voices_basis, voices_capacity, voices_held, mem_after_instantiate_kb, mem_after_activate_kb,
      mem_at_rest_kb, mem_second_instance_kb, mem_first_instance_kb, mem_per_instance_kb, mem_notes_held_kb, mem_basis,
      mem_unmeasured_reason, mem_limit_bytes, mem_limit_mechanism, rt_interposer, rt_swept, rt_sweep_applicable,
      rt_blocks, rt_allocations, rt_locks, rt_syscalls, rt_thread_violations, rt_process_errors, rt_own_threads,
      rt_other_allocations, rt_other_locks, rt_other_syscalls, note_sweep_applicable, note_sweep_dialect,
      note_sweep_allocations, note_sweep_locks, note_sweep_syscalls,
         CASE WHEN rt_allocations IS NULL THEN NULL ELSE 1 END   -- 1 wrote rtSafety.events with its counts, always
  FROM v1_cell;
INSERT INTO cell_event (record_id, cell_ord, ord, event)
  SELECT record_id, cell_ord, ord, event FROM v1_cell_event;
INSERT INTO claim (record_id, plugin_id, offer, host_class, rate, quantum)
  SELECT record_id, plugin_id, offer, host_class, rate, quantum FROM v1_claim;
INSERT INTO feature_required (record_id, ord, feature)
  SELECT record_id, ord, feature FROM v1_feature_required;
INSERT INTO unmeasured (record_id, ord, dimension, code, rate, quantum)
  SELECT record_id, ord, dimension, code, rate, quantum FROM v1_unmeasured;
INSERT INTO not_measured (record_id, ord, dimension, code)
  SELECT record_id, ord, dimension, code FROM v1_not_measured;
INSERT INTO record_history (record_id, ord, host_class, file, at, key_uri, key_digest, found, windows_solo,
    windows_grouped, summary_crashed, summary_raises_xruns, unknown_keys)
  SELECT record_id, ord, host_class, file, at, key_uri, key_digest, found, windows_solo, windows_grouped,
      summary_crashed, summary_raises_xruns, unknown_keys FROM v1_record_history;
INSERT INTO history_unknown_key (record_id, history_ord, name, value)
  SELECT record_id, history_ord, name, value FROM v1_history_unknown_key;
INSERT INTO history_verdict (record_id, history_ord, ord, host, measured, adjusted, move, reason, blocked_by)
  SELECT record_id, history_ord, ord, host, measured, adjusted, move, reason, blocked_by FROM v1_history_verdict;
INSERT INTO history_blocked (record_id, history_ord, verdict_ord, ord, code)
  SELECT record_id, history_ord, verdict_ord, ord, code FROM v1_history_blocked;
INSERT INTO run_step (record_id, ord, step, result, code, cpu_percent, latency_frames, midi_inputs_linked, xruns,
    pool_allocations_on, pool_locks_on, pool_syscalls_on, pool_tasks_on_helpers, pool_dsp_load_off, pool_dsp_load_on,
    pool_xruns_off, pool_xruns_on)
  SELECT record_id, ord, step, result, code, cpu_percent, latency_frames, midi_inputs_linked, xruns,
      pool_allocations_on, pool_locks_on, pool_syscalls_on, pool_tasks_on_helpers, pool_dsp_load_off, pool_dsp_load_on,
      pool_xruns_off, pool_xruns_on FROM v1_run_step;
INSERT INTO probe_end (record_id, ord, step, outcome, exit_status, signal)
  SELECT record_id, ord, step, outcome, exit_status, signal FROM v1_probe_end;
INSERT INTO adapter_cell (record_id, ord, rate, quantum, admitted, measured, code, params)
  SELECT record_id, ord, rate, quantum, admitted, measured, code, params FROM v1_adapter_cell;
INSERT INTO adapter_param (record_id, name, number, word)
  SELECT record_id, name, number, word FROM v1_adapter_param;
INSERT INTO adapter_cell_param (record_id, ord, name, number, word)
  SELECT record_id, ord, name, number, word FROM v1_adapter_cell_param;
INSERT INTO memory_run_cell (record_id, ord, rate, quantum, outcome)
  SELECT record_id, ord, rate, quantum, outcome FROM v1_memory_run_cell;
INSERT INTO rejudged_owe (record_id, ord, code, measurement)
  SELECT record_id, ord, code, measurement FROM v1_rejudged_owe;

-- the words renamed from 1 to 2, one UPDATE a word: none (see the header)

DROP TABLE v1_rejudged_owe;
DROP TABLE v1_memory_run_cell;
DROP TABLE v1_adapter_cell_param;
DROP TABLE v1_adapter_param;
DROP TABLE v1_adapter_cell;
DROP TABLE v1_probe_end;
DROP TABLE v1_run_step;
DROP TABLE v1_history_blocked;
DROP TABLE v1_history_verdict;
DROP TABLE v1_history_unknown_key;
DROP TABLE v1_record_history;
DROP TABLE v1_not_measured;
DROP TABLE v1_unmeasured;
DROP TABLE v1_feature_required;
DROP TABLE v1_claim;
DROP TABLE v1_cell_event;
DROP TABLE v1_cell;
DROP TABLE v1_tier_offered;
DROP TABLE v1_tier;
DROP TABLE v1_reason_param;
DROP TABLE v1_reason;
DROP TABLE v1_cost_entry;
DROP TABLE v1_verdict;
DROP TABLE v1_record_version;
DROP TABLE v1_record_extension;
DROP TABLE v1_record_file;
DROP TABLE v1_record;
DROP TABLE v1_set_setting;
DROP TABLE v1_set_package;
DROP TABLE v1_record_set;
DROP TABLE v1_plugin;
DROP TABLE v1_word_check;
DROP TABLE v1_store_domain;
DROP TABLE v1_store_info;
