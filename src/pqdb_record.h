/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com> */
/* The record exporter of the reader (internal; the library exports pqdb_* only). */
#ifndef PQDB_RECORD_H
#define PQDB_RECORD_H
#include <stddef.h>
typedef struct sqlite3 sqlite3;
/* The record `record_id` of `h` as one JSON document, in memory the caller frees. 0, or -1 with `why` naming the reason. */
int pqdb_record_document(sqlite3 *h, long long record_id, char **json, char *why, size_t why_n);
#endif
