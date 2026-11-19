/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com> */
/** @file
 * The qualification store's reader (this repository's qualification store spec, section 6).
 *
 * NEVER IN A REAL-TIME PATH. Every function here allocates, reads files and takes locks. A program reads a plugin's
 * figures when the plugin is added, outside its audio thread, and copies them. A handle is used by one thread at a
 * time; a program with several threads opens one handle each.
 *
 * Errors are strings by name: a refusal gives `pqdb_error.code` (`qualification-db.absent`, ... or a code of the
 * contract loader, passed through) and a message naming the file. A status is 0 or non-zero; `pqdb_code(status)`
 * gives the name of a refusal of this library.
 */
#ifndef PLUGIN_QUALIFICATION_DB_PQDB_H
#define PLUGIN_QUALIFICATION_DB_PQDB_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PQDB_SCHEMA_VERSION 1

typedef struct pqdb pqdb;                          /* an opened base and user layer; opaque */
typedef enum { PQDB_SCOPE_USER, PQDB_SCOPE_SYSTEM } pqdb_scope;

typedef struct { const char *code; char message[256]; } pqdb_error;  /* names the code, the file and the reason */

/* 0, or a refusal (non-zero; err->code names it). Production: the installed base and the scope's user layer; no path, no environment. */
int  pqdb_open(pqdb_scope scope, pqdb **out, pqdb_error *err);
/* TEST AND COMMAND ONLY: the base, the user layer (NULL: none) and the contract directory, given (NULL: the installed one). */
int  pqdb_open_at(const char *base, const char *user, const char *contract_dir, pqdb **out, pqdb_error *err);
void pqdb_close(pqdb *db);
const char *pqdb_code(int status);                 /* the name of a refusal: "qualification-db.absent" ...; NULL for 0 and for a
                                                      status that carries the loader's own code (err->code) */

/* A query with every field optional: a string of NULL, and a rate or quantum of -1, is "any". 0 is not "any": a zeroed
   query asks for rate 0 and quantum 0 and matches nothing. Start from PQDB_QUERY_ANY and set the fields you filter on:
   pqdb_query q = PQDB_QUERY_ANY; q.sha256 = ...; */
#define PQDB_QUERY_ANY { .rate = -1, .quantum = -1 }
typedef struct {
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
   no record of its shadow key (section 4), in key order. A non-zero return of each stops the walk and is returned. */
int  pqdb_each(const pqdb *db, const pqdb_query *q, int (*each)(const pqdb_result *, void *), void *ctx);

/* The verdict of a result's record under one host profile: rating word, measured, qualified, deciding (NULL: none).
   0; 1 when the record has no verdict of that host; a refusal status otherwise. The strings are valid until the next
   pqdb_verdict_of or pqdb_close of the handle. */
typedef struct { const char *rating, *deciding; int measured, qualified; } pqdb_verdict;
int  pqdb_verdict_of(const pqdb *db, const pqdb_result *r, const char *host, pqdb_verdict *out);
/* Every verdict of a result's record, in the record's order, as each(host, verdict, ctx); the strings are valid until each
   returns. A non-zero return of each stops the walk and is returned. 0, or a refusal status. */
int  pqdb_verdicts(const pqdb *db, const pqdb_result *r, int (*each)(const char *host, const pqdb_verdict *, void *), void *ctx);

#ifdef __cplusplus
}
#endif

#endif
