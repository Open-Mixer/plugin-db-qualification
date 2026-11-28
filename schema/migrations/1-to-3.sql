-- SPDX-License-Identifier: GPL-3.0-or-later
-- Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
-- The qualification store from user_version 1 to 3 (this repository's qualification store spec, section 3.6): the step
-- from 1 to 2, below, and 3's two new tables (no_figures, no_figures_file), which the DDL creates empty.
--
-- user_version 1 is every layer the dated writers wrote: the DDL of v2026112401, and the later dated builds, which
-- added cell_voice_point, record.adapter_content, .adapter_loaded, .adapter_refused, cost_entry.voices_basis,
-- .voices_capacity, .voices_held and cell.rt_events (and two table CHECKs of cell) at the same number. No column of 1
-- is gone or renamed in 2.
--
-- The runner (tools/qualification_db.py migrate, the reader's migrate_user) does the part every step shares, in one
-- transaction after a backup copy, foreign keys off: it drops the layer's indexes and triggers, renames every table T
-- to v1_T, and adds to v1_T each column of 2's T it lacks (NULL in every row). Then this script runs, over the v1_
-- tables. Then the runner runs schema/qualification.sql, copies every row of v1_T into T, column by column, drops the
-- v1_ tables, checks the foreign keys and every word against the installed domains, and commits. A word no item of its
-- column holds is refused by name and the layer is left as it was.
--
-- The words. No word of 1 is renamed in 2: every word the items of a word column held at 1 (the domains of
-- plugin-hostd, plugin-hostd-protocol, plugin-db and omx-clap-core main at 2026-11-24) is a word of the same items at
-- 2; 2 only adds words. So the renames below are none.

-- a layer of v2026112401 wrote rtSafety.events with the audio thread's counts, always: the flag 2 keeps of it
UPDATE v1_cell SET rt_events = 1 WHERE rt_allocations IS NOT NULL AND rt_events IS NULL;

-- every domain started again at 0.1.0 (owner, 2026-11-25), and the words of 1 are words of each at 0.1.0
DELETE FROM v1_store_domain;
INSERT INTO v1_store_domain (domain, version) VALUES
  ('hosting', '0.1.0'),
  ('machine', '0.1.0'),
  ('plugin-db', '0.1.0'),
  ('probe', '0.1.0'),
  ('qualification', '0.1.0');

-- the items 2 reads that the writer of v2026112401 did not
INSERT OR IGNORE INTO v1_word_check (tbl, col, domain, item) VALUES
  ('adapter_cell_param', 'word', 'qualification', 'QUALIFICATION_MEASUREMENT_UNMEASURED_REASONS'),
  ('adapter_param', 'word', 'qualification', 'QUALIFICATION_MEASUREMENT_UNMEASURED_REASONS'),
  ('reason_param', 'word', 'qualification', 'QUALIFICATION_MEASUREMENT_UNMEASURED_REASONS'),
  ('cost_entry', 'voices_basis', 'qualification', 'QUALIFICATION_MEASUREMENT_VOICE_BASES');

-- the words renamed from 1 to 2, one UPDATE a word: none (see the header)
