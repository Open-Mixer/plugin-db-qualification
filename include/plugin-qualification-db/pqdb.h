/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com> */
/* The qualification store's reader (this repository's qualification store spec, section 6). */
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
   no record of its shadow key (section 4), in key order. A non-zero return of each stops the walk and is returned. */
int  pqdb_each(const pqdb *db, const pqdb_query *q, int (*each)(const pqdb_result *, void *), void *ctx);

/* The verdict of a result's record under one host profile: rating word, measured, qualified, deciding (NULL: none). */
typedef struct { const char *rating, *deciding; int measured, qualified; } pqdb_verdict;
int  pqdb_verdict_of(const pqdb *db, const pqdb_result *r, const char *host, pqdb_verdict *out);

#ifdef __cplusplus
}
#endif

#endif
