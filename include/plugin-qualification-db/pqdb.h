/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com> */
/** @file
 * The qualification store's reader (this repository's qualification store spec, section 6).
 *
 * NEVER IN A REAL-TIME PATH. Every function here allocates, reads files and takes locks. A program reads a plugin's
 * figures when the plugin is added, outside its audio thread, and copies them. A handle is used by one thread at a
 * time; a program with several threads opens one handle each.
 *
 * Errors are strings by name: a refusal gives `pqdb_error.code` (`qualification-db.unreadable`, ... or a code of the
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

#define PQDB_SCHEMA_VERSION 2

typedef struct pqdb pqdb;                          /* an opened base and user layer; opaque */
typedef enum { PQDB_SCOPE_USER, PQDB_SCOPE_SYSTEM } pqdb_scope;

typedef struct { const char *code; char message[256]; } pqdb_error;  /* names the code, the file and the reason */

/* 0, or a refusal (non-zero; err->code names it). Production: the installed base and the scope's user layer; no path, no environment. */
int  pqdb_open(pqdb_scope scope, pqdb **out, pqdb_error *err);
/* TEST AND COMMAND ONLY: the base, the user layer (NULL: none) and the contract directory, given (NULL: the installed one). */
int  pqdb_open_at(const char *base, const char *user, const char *contract_dir, pqdb **out, pqdb_error *err);
/* 1 when the open found no base file: the base layer is empty (the store has no base records until the records migration
   ships), and every answer is the user layer's alone. Only ENOENT is absent: a base that exists and cannot be used is a refusal. */
int  pqdb_base_absent(const pqdb *db);
void pqdb_close(pqdb *db);
const char *pqdb_code(int status);                 /* the name of a refusal: "qualification-db.unreadable" ...; NULL for 0 and for a
                                                      status that carries the loader's own code (err->code) */

/* A query with every field optional: a string of NULL, and a rate or quantum of -1, is "any". 0 is not "any": a zeroed
   query asks for rate 0 and quantum 0 and matches nothing. Start from PQDB_QUERY_ANY and set the fields you filter on:
   pqdb_query q = PQDB_QUERY_ANY; q.sha256 = ...; */
/* positional, in the struct's order: valid C and C++11 (designated initializers are C++20); tests check the fields */
#define PQDB_QUERY_ANY { NULL, NULL, NULL, NULL, NULL, -1, -1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL }
typedef struct {
    const char *sha256, *format, *uri, *offer, *host_class;
    int rate, quantum;
    const char *pkg_format, *pkg_name, *pkg_version, *pkg_release, *pkg_distro, *pkg_arch;
    const char *binary_path;                        /* the main binary's path below its install root, as stored (exact) */
    const char *layer;                              /* "user": the scope's user layer only, no shadowing; "base": the base only;
                                                       NULL: both, merged (section 4). Any other name is refused:
                                                       qualification-db.layer-unknown */
} pqdb_query;

typedef struct {
    const char *layer;                              /* "user" or "base" */
    const char *sha256, *format, *uri, *offer, *host_class, *set;   /* set: NULL in the user layer */
    const char *pkg_format, *pkg_name, *pkg_version, *pkg_release, *pkg_distro, *pkg_arch;  /* NULL: not known */
    const char *binary_path;                        /* the record's, below its install root */
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

/* The per-file list of a result's record (what a pin matches on), in its order (ascending by path, bytewise), as
   each(path, sha256, ctx). Every cell of a record gives the same list. The strings are valid until each returns; the
   reader hashes nothing, the caller compares the list with what it hashed. A non-zero return of each stops the walk
   and is returned. 0, or a refusal status. */
int  pqdb_files(const pqdb *db, const pqdb_result *r, int (*each)(const char *path, const char *sha256, void *), void *ctx);

/* What the last refusal of pqdb_each said (the layer, the record, the column), or NULL; valid until the next call on the
   handle. pqdb_each refuses a figure that is not finite (a REAL of Infinity) as qualification-db.not-a-store. */
const char *pqdb_message(const pqdb *db);

/* A number as JSON.stringify writes it (2 for 2.0, 1e-7, 0.1, 0 for -0), under the C locale whatever the program's, as
   pqdb_record_json writes its numbers. 0, or -1 for a value that is not finite or does not fit in `n` bytes. */
int  pqdb_number(double value, char *out, size_t n);

/* The record of a result as one JSON document of `plugin-qualify.qualification-record/1`, as this repository's
   qualification store spec (section 5) has its exporter write it: the same bytes as the Python exporter's, the sentences
   of section 3.5 absent. `*json` is memory the caller frees with free(). 0, or a refusal status with `err` filled; on a
   refusal `*json` is NULL. Every cell of a record gives the same document. */
int  pqdb_record_json(const pqdb *db, const pqdb_result *r, char **json, pqdb_error *err);

/* What a layer holds per plugin (a plugin: a format and a uri), by format in format order, as
   each(format, plugins, offered, not_offered, ctx). `layer` is "user", "base" or NULL (both, merged as section 4). A
   plugin is offered when any of its records has a tier_offered row; two records of one plugin count once. The strings
   are valid until each returns; a non-zero return of each stops the walk and is returned. 0, or a refusal status. */
int  pqdb_counts(const pqdb *db, const char *layer,
                 int (*each)(const char *format, long plugins, long offered, long not_offered, void *), void *ctx);

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
