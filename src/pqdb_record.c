/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com> */
/* A record read back as the document it was written from (this repository's qualification store spec, sections 3.5 and
 * 5): the exporter of the spec in C. The same document the Python exporter writes, byte for byte: compact JSON, the
 * keys in the order of the record's description, a NULL column an absent key, an object with no key left absent
 * unless its anchor column is set, and none of the sentences of section 3.5 (they are not stored). Floats are written
 * the way Python's repr writes them. Never called from a real-time path. */
#define _GNU_SOURCE
#include "pqdb_record.h"

#include <sqlite3.h>

#include <errno.h>
#include <locale.h>
#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { char *p; size_t n, cap; int oom; const char *bad, *nonfinite; } buf;

static void bput(buf *b, const char *s, size_t n)
{
    if (b->oom)
        return;
    if (b->n + n + 1 > b->cap) {
        size_t cap = b->cap ? b->cap : 4096;
        char *np;
        while (cap < b->n + n + 1)
            cap *= 2;
        np = realloc(b->p, cap);
        if (!np) { b->oom = 1; return; }
        b->p = np; b->cap = cap;
    }
    memcpy(b->p + b->n, s, n);
    b->n += n;
    b->p[b->n] = 0;
}
static void bs(buf *b, const char *s) { bput(b, s, strlen(s)); }
static void bc(buf *b, char c) { bput(b, &c, 1); }
static char last(const buf *b) { return b->n ? b->p[b->n - 1] : 0; }
static void trunc_to(buf *b, size_t n) { b->n = n; if (b->p) b->p[n] = 0; }

static void jstr(buf *b, const char *s)
{
    bc(b, '"');
    for (; *s; s++) {
        unsigned char c = (unsigned char)*s;
        switch (c) {
        case '"': bs(b, "\\\""); break;
        case '\\': bs(b, "\\\\"); break;
        case '\b': bs(b, "\\b"); break;
        case '\f': bs(b, "\\f"); break;
        case '\n': bs(b, "\\n"); break;
        case '\r': bs(b, "\\r"); break;
        case '\t': bs(b, "\\t"); break;
        default:
            if (c < 0x20) { char u[8]; snprintf(u, sizeof u, "\\u%04x", c); bs(b, u); }
            else bc(b, (char)c);
        }
    }
    bc(b, '"');
}
static void jint(buf *b, long long v) { char t[32]; snprintf(t, sizeof t, "%lld", v); bs(b, t); }

/* Python's repr of a float: the shortest digits that read back the same, fixed from 1e-4 up to 1e16, else with an exponent */
static void jreal(buf *b, double v)
{
    char t[40], digits[24], out[64];
    int p, e10, nd = 0, neg = v < 0, decpt, o = 0;
    char *e;
    if (neg) v = -v;
    for (p = 1; p <= 17; p++) {
        snprintf(t, sizeof t, "%.*e", p - 1, v);
        if (strtod(t, NULL) == v)
            break;
    }
    e = strchr(t, 'e');
    e10 = atoi(e + 1);
    for (char *c = t; c < e; c++)
        if (*c != '.')
            digits[nd++] = *c;
    digits[nd] = 0;
    decpt = e10 + 1;
    if (neg) out[o++] = '-';
    if (e10 >= -4 && e10 < 16) {
        if (decpt <= 0) {
            o += snprintf(out + o, sizeof out - (size_t)o, "0.");
            for (int i = 0; i < -decpt; i++) out[o++] = '0';
            o += snprintf(out + o, sizeof out - (size_t)o, "%s", digits);
        } else if (decpt >= nd) {
            o += snprintf(out + o, sizeof out - (size_t)o, "%s", digits);
            for (int i = 0; i < decpt - nd; i++) out[o++] = '0';
            o += snprintf(out + o, sizeof out - (size_t)o, ".0");
        } else {
            o += snprintf(out + o, sizeof out - (size_t)o, "%.*s.%s", decpt, digits, digits + decpt);
        }
    } else {
        o += snprintf(out + o, sizeof out - (size_t)o, "%c", digits[0]);
        if (nd > 1) o += snprintf(out + o, sizeof out - (size_t)o, ".%s", digits + 1);
        o += snprintf(out + o, sizeof out - (size_t)o, "e%c%02d", e10 < 0 ? '-' : '+', e10 < 0 ? -e10 : e10);
    }
    out[o] = 0;
    bs(b, out);
}

/* a number as JSON.stringify writes it (ECMAScript Number::toString): the shortest digits that read back the same double,
 * then laid out as the standard has it: plain from 1e-6 up to (not including) 1e21, else d[.ddd]e(+|-)x with no padding;
 * 2.0 is 2, -0 is 0 */
/* `out` holds 64 bytes */
static void js_number(double v, char *out)
{
    char t[40], digits[24];
    int p, nd = 0, e10, n, o = 0;
    char *e;
    if (v == 0) { strcpy(out, "0"); return; }
    if (v < 0) { out[o++] = '-'; v = -v; }
    for (p = 1; p <= 17; p++) {                     /* the first that reads back equal is the shortest */
        snprintf(t, sizeof t, "%.*e", p - 1, v);
        if (strtod(t, NULL) == v)
            break;
    }
    e = strchr(t, 'e');
    e10 = atoi(e + 1);
    for (char *c = t; c < e; c++)
        if (*c != '.')
            digits[nd++] = *c;
    digits[nd] = 0;
    n = e10 + 1;                                    /* the value is 0.digits x 10^n */
    if (nd <= n && n <= 21) {
        o += snprintf(out + o, 64 - (size_t)o, "%s", digits);
        for (int i = 0; i < n - nd; i++) out[o++] = '0';
    } else if (0 < n && n <= 21) {
        o += snprintf(out + o, 64 - (size_t)o, "%.*s.%s", n, digits, digits + n);
    } else if (-6 < n && n <= 0) {
        o += snprintf(out + o, 64 - (size_t)o, "0.");
        for (int i = 0; i < -n; i++) out[o++] = '0';
        o += snprintf(out + o, 64 - (size_t)o, "%s", digits);
    } else {
        o += snprintf(out + o, 64 - (size_t)o, "%c", digits[0]);
        if (nd > 1) o += snprintf(out + o, 64 - (size_t)o, ".%s", digits + 1);
        o += snprintf(out + o, 64 - (size_t)o, "e%c%d", n - 1 < 0 ? '-' : '+', n - 1 < 0 ? 1 - n : n - 1);
    }
    out[o] = 0;
}

static void jnum(buf *b, double v)
{
    char out[64];
    js_number(v, out);
    bs(b, out);
}

/* a key of the object or array being written: a comma unless it is the first */
static void key(buf *b, const char *k)
{
    char l = last(b);
    if (l != '{' && l != '[')
        bc(b, ',');
    bc(b, '"'); bs(b, k); bs(b, "\":");
}
static void elem(buf *b)
{
    if (last(b) != '[')
        bc(b, ',');
}
/* An object is absent unless it has a key or it is anchored by a column that is set; one anchored by a column that is
 * NULL is absent whatever it holds (the Python exporter's rule): the anchor is 0 (none), 1 (set) or -1 (NULL). */
static int obj_close(buf *b, int anchored)
{
    if (last(b) == '{' && !anchored) { trunc_to(b, b->n - 1); return 0; }
    bc(b, '}');
    return 1;
}
#define OBJ(b, name, anchor, ...) do { int a_ = (anchor); if (a_ >= 0) { size_t m_ = (b)->n; key(b, name); bc(b, '{'); __VA_ARGS__; \
        if (!obj_close(b, a_)) trunc_to(b, m_); } } while (0)
#define ARR(b, name, always, ...) do { size_t m_ = (b)->n; int e_; key(b, name); bc(b, '['); __VA_ARGS__; e_ = last(b) == '['; bc(b, ']'); \
        if (e_ && !(always)) trunc_to(b, m_); } while (0)

/* ---- rows ---- */
static int ci(sqlite3_stmt *st, const char *col, buf *b)
{
    int n = sqlite3_column_count(st);
    for (int i = 0; i < n; i++)
        if (strcmp(sqlite3_column_name(st, i), col) == 0)
            return i;
    if (!b->bad) b->bad = col;
    return -1;
}
static int null_of(sqlite3_stmt *st, const char *col, buf *b)
{
    int i = ci(st, col, b);
    return i < 0 || sqlite3_column_type(st, i) == SQLITE_NULL;
}
#define ANCHOR(st, col, b) (null_of(st, col, b) ? -1 : 1)
/* kinds: T text, I integer, R real (as Python writes a float), N number (as JSON.stringify writes it), B boolean (the columns of section 3.3 by the Python description's kinds) */
static void leaf(buf *b, sqlite3_stmt *st, const char *jk, const char *col, char kind)
{
    int i = ci(st, col, b);
    if (i < 0 || sqlite3_column_type(st, i) == SQLITE_NULL)
        return;
    if ((kind == 'R' || kind == 'N') && !isfinite(sqlite3_column_double(st, i))) {   /* JSON has no Infinity: refused by name */
        if (!b->nonfinite) b->nonfinite = col;
        return;
    }
    key(b, jk);
    switch (kind) {
    case 'I': jint(b, sqlite3_column_int64(st, i)); break;
    case 'R': jreal(b, sqlite3_column_double(st, i)); break;
    case 'N': jnum(b, sqlite3_column_double(st, i)); break;
    case 'B': bs(b, sqlite3_column_int64(st, i) ? "true" : "false"); break;
    default: jstr(b, (const char *)sqlite3_column_text(st, i));
    }
}
typedef struct { const char *jk, *col; char kind; } leafdef;
static void leaves(buf *b, sqlite3_stmt *st, const leafdef *d, size_t n)
{
    for (size_t i = 0; i < n; i++)
        leaf(b, st, d[i].jk, d[i].col, d[i].kind);
}
#define LEAVES(b, st, ...) do { static const leafdef d_[] = { __VA_ARGS__ }; leaves(b, st, d_, sizeof d_ / sizeof *d_); } while (0)

typedef struct { sqlite3 *h; long long rid; char msg[200]; } ctx;
static sqlite3_stmt *prep(buf *b, ctx *c, const char *sql, int nbind, long long a1, long long a2)
{
    sqlite3_stmt *st;
    if (sqlite3_prepare_v2(c->h, sql, -1, &st, NULL) != SQLITE_OK) {
        if (!b->bad) { snprintf(c->msg, sizeof c->msg, "%s", sqlite3_errmsg(c->h)); b->bad = c->msg; }
        return NULL;
    }
    if (nbind > 0) sqlite3_bind_int64(st, 1, a1);
    if (nbind > 1) sqlite3_bind_int64(st, 2, a2);
    return st;
}
#define ROWS(b, c, st, sql, nbind, a1, a2) for (sqlite3_stmt *st = prep(b, c, sql, nbind, a1, a2); st; sqlite3_finalize(st), st = NULL) \
    for (; sqlite3_step(st) == SQLITE_ROW;)

/* an object of named values: rows of (name, number, word), the number an integer or a real as stored */
static void params(buf *b, ctx *c, const char *sql, int nbind, long long a1, long long a2)
{
    bc(b, '{');
    ROWS(b, c, st, sql, nbind, a1, a2) {
        key(b, (const char *)sqlite3_column_text(st, 0));
        if (sqlite3_column_type(st, 1) == SQLITE_INTEGER) jint(b, sqlite3_column_int64(st, 1));
        else if (sqlite3_column_type(st, 1) == SQLITE_FLOAT) {
            if (!isfinite(sqlite3_column_double(st, 1))) { if (!b->nonfinite) b->nonfinite = "number"; bs(b, "0"); }
            else jreal(b, sqlite3_column_double(st, 1));
        }
        else jstr(b, (const char *)sqlite3_column_text(st, 2));
    }
    bc(b, '}');
}
/* an object of named texts: rows of (name, value) */
static void params_text(buf *b, ctx *c, const char *sql, long long a1, long long a2)
{
    bc(b, '{');
    ROWS(b, c, st, sql, 2, a1, a2) {
        key(b, (const char *)sqlite3_column_text(st, 0));
        jstr(b, (const char *)sqlite3_column_text(st, 1));
    }
    bc(b, '}');
}
static void reasons(buf *b, ctx *c, const char *by, long long ord)
{
    char sql[200];
    snprintf(sql, sizeof sql, "SELECT * FROM reason WHERE record_id = ?1 AND %s = ?2 ORDER BY ord", by);
    ARR(b, "reasons", 1, {
        ROWS(b, c, st, sql, 2, c->rid, ord) {
            elem(b); bc(b, '{');
            LEAVES(b, st, { "dimension", "dimension", 'T' }, { "rating", "rating", 'T' }, { "code", "code", 'T' });
            key(b, "params");
            params(b, c, "SELECT name, number, word FROM reason_param WHERE reason_id = ?1 ORDER BY rowid", 1, sqlite3_column_int64(st, ci(st, "reason_id", b)), 0);
            bc(b, '}');
        }
    });
}
static void strings(buf *b, ctx *c, const char *name, int always, const char *sql, int nbind, long long a1, long long a2)
{
    ARR(b, name, always, { ROWS(b, c, st, sql, nbind, a1, a2) { elem(b); jstr(b, (const char *)sqlite3_column_text(st, 0)); } });
}

static void cell(buf *b, ctx *c, sqlite3_stmt *st)
{
    long long ord = sqlite3_column_int64(st, ci(st, "ord", b));
    LEAVES(b, st, { "rate", "rate", 'I' }, { "quantum", "quantum", 'I' }, { "outcome", "outcome", 'T' });
    OBJ(b, "latency", 0, LEAVES(b, st, { "declaredFrames", "latency_declared_frames", 'I' }, { "measuredFrames", "latency_measured_frames", 'I' },
                                 { "code", "latency_code", 'T' }, { "unmeasuredReason", "latency_unmeasured_reason", 'T' }));
    leaf(b, st, "latencyMs", "latency_ms", 'N');
    OBJ(b, "cost", 0, {
        leaf(b, st, "median", "cost_median", 'R');
        OBJ(b, "percentile", 0, LEAVES(b, st, { "p", "cost_percentile_p", 'I' }, { "value", "cost_percentile_value", 'R' }));
        LEAVES(b, st, { "blocks", "cost_blocks", 'I' }, { "warmupBlocks", "cost_warmup_blocks", 'I' });
        OBJ(b, "voices", 0, LEAVES(b, st, { "basis", "voices_basis", 'T' }, { "capacity", "voices_capacity", 'I' }, { "held", "voices_held", 'I' }));
        ARR(b, "voiceCurve", 0, {
            ROWS(b, c, vp, "SELECT * FROM cell_voice_point WHERE record_id = ?1 AND cell_ord = ?2 ORDER BY ord", 2, c->rid, ord) {
                elem(b); bc(b, '{');
                LEAVES(b, vp, { "held", "held", 'I' }, { "median", "median", 'R' });
                OBJ(b, "percentile", 1, LEAVES(b, vp, { "p", "percentile_p", 'I' }, { "value", "percentile_value", 'R' }));
                bc(b, '}');
            }
        });
    });
    OBJ(b, "memory", 0, LEAVES(b, st, { "afterInstantiateKb", "mem_after_instantiate_kb", 'I' }, { "afterActivateKb", "mem_after_activate_kb", 'I' },
                                { "atRestKb", "mem_at_rest_kb", 'I' }, { "secondInstanceKb", "mem_second_instance_kb", 'I' },
                                { "firstInstanceKb", "mem_first_instance_kb", 'I' }, { "perInstanceKb", "mem_per_instance_kb", 'I' },
                                { "notesHeldKb", "mem_notes_held_kb", 'I' }, { "basis", "mem_basis", 'T' },
                                { "unmeasuredReason", "mem_unmeasured_reason", 'T' }));
    OBJ(b, "memoryLimit", 0, LEAVES(b, st, { "bytes", "mem_limit_bytes", 'I' }, { "mechanism", "mem_limit_mechanism", 'T' }));
    OBJ(b, "rtSafety", ANCHOR(st, "rt_interposer", b), {
        LEAVES(b, st, { "interposer", "rt_interposer", 'B' }, { "swept", "rt_swept", 'B' }, { "sweepApplicable", "rt_sweep_applicable", 'B' },
               { "blocks", "rt_blocks", 'I' }, { "allocations", "rt_allocations", 'I' }, { "locks", "rt_locks", 'I' }, { "syscalls", "rt_syscalls", 'I' },
               { "threadViolations", "rt_thread_violations", 'I' }, { "processErrors", "rt_process_errors", 'I' }, { "ownThreads", "rt_own_threads", 'I' });
        OBJ(b, "otherThreads", 0, LEAVES(b, st, { "allocations", "rt_other_allocations", 'I' }, { "locks", "rt_other_locks", 'I' },
                                          { "syscalls", "rt_other_syscalls", 'I' }));
        if (!null_of(st, "rt_events", b))
            strings(b, c, "events", 1, "SELECT event FROM cell_event WHERE record_id = ?1 AND cell_ord = ?2 ORDER BY ord", 2, c->rid, ord);
    });
    OBJ(b, "noteSweep", 0, LEAVES(b, st, { "applicable", "note_sweep_applicable", 'B' }, { "dialect", "note_sweep_dialect", 'T' },
                                   { "allocations", "note_sweep_allocations", 'I' }, { "locks", "note_sweep_locks", 'I' },
                                   { "syscalls", "note_sweep_syscalls", 'I' }));
}

static void tier(buf *b, ctx *c, const char *name)
{
    ROWS(b, c, st, "SELECT * FROM tier WHERE record_id = ?1 ORDER BY rowid", 1, c->rid, 0) {
        const char *t = (const char *)sqlite3_column_text(st, ci(st, "tier", b));
        if (strcmp(t, name) != 0)
            continue;
        key(b, name); bc(b, '{');
        LEAVES(b, st, { "host", "host", 'T' }, { "measured", "measured", 'B' }, { "qualified", "qualified", 'B' }, { "rating", "rating", 'T' },
               { "deciding", "deciding", 'T' }, { "runsAlone", "runs_alone", 'B' });
        bc(b, '}');
    }
}

/* history[]: the adjust --history blocks, in plugin-qualify's order (HistoryBlock, Adjustment) */
static void history(buf *b, ctx *c)
{
    ARR(b, "history", 0, {
        ROWS(b, c, st, "SELECT * FROM record_history WHERE record_id = ?1 ORDER BY ord", 1, c->rid, 0) {
            long long ho = sqlite3_column_int64(st, ci(st, "ord", b));
            elem(b); bc(b, '{');
            LEAVES(b, st, { "hostClass", "host_class", 'T' }, { "file", "file", 'T' }, { "at", "at", 'T' });
            if (!null_of(st, "key_uri", b) || !null_of(st, "key_digest", b))
                OBJ(b, "key", 1, LEAVES(b, st, { "uri", "key_uri", 'T' }, { "digest", "key_digest", 'T' }));
            leaf(b, st, "found", "found", 'B');
            if (!null_of(st, "windows_solo", b) || !null_of(st, "windows_grouped", b))
                OBJ(b, "windows", 1, LEAVES(b, st, { "solo", "windows_solo", 'I' }, { "grouped", "windows_grouped", 'I' }));
            if (!null_of(st, "summary_crashed", b) || !null_of(st, "summary_raises_xruns", b))
                OBJ(b, "summary", 1, LEAVES(b, st, { "crashed", "summary_crashed", 'B' }, { "raisesXruns", "summary_raises_xruns", 'B' }));
            if (!null_of(st, "unknown_keys", b)) {
                key(b, "unknownKeys");
                params_text(b, c, "SELECT name, value FROM history_unknown_key WHERE record_id = ?1 AND history_ord = ?2 ORDER BY rowid", c->rid, ho);
            }
            ARR(b, "verdicts", 1, {
                ROWS(b, c, vs, "SELECT * FROM history_verdict WHERE record_id = ?1 AND history_ord = ?2 ORDER BY ord", 2, c->rid, ho) {
                    long long vo = sqlite3_column_int64(vs, ci(vs, "ord", b));
                    elem(b); bc(b, '{');
                    leaf(b, vs, "host", "host", 'T');
                    key(b, "measured");
                    if (null_of(vs, "measured", b)) bs(b, "null"); else jstr(b, (const char *)sqlite3_column_text(vs, ci(vs, "measured", b)));
                    key(b, "adjusted");
                    if (null_of(vs, "adjusted", b)) bs(b, "null"); else jstr(b, (const char *)sqlite3_column_text(vs, ci(vs, "adjusted", b)));
                    LEAVES(b, vs, { "move", "move", 'T' }, { "reason", "reason", 'T' });
                    if (!null_of(vs, "blocked_by", b)) {
                        char sql[200];
                        snprintf(sql, sizeof sql, "SELECT code FROM history_blocked WHERE record_id = ?1 AND history_ord = ?2 AND verdict_ord = %lld ORDER BY ord", vo);
                        ARR(b, "blockedBy", 1, { ROWS(b, c, bs_, sql, 2, c->rid, ho) { elem(b); jstr(b, (const char *)sqlite3_column_text(bs_, 0)); } });
                    }
                    bc(b, '}');
                }
            });
            bc(b, '}');
        }
    });
}

static void record(buf *b, ctx *c, sqlite3_stmt *r)
{
    long long rid = c->rid;
    bc(b, '{');
    leaf(b, r, "schema", "schema", 'T');
    OBJ(b, "plugin", 0, LEAVES(b, r, { "format", "p_format", 'T' }, { "id", "p_uri", 'T' }, { "name", "plugin_name", 'T' }));
    OBJ(b, "binary", 0, {
        LEAVES(b, r, { "path", "binary_path", 'T' }, { "sha256", "p_sha256", 'T' });
        ARR(b, "files", 1, {
            ROWS(b, c, st, "SELECT path, sha256 FROM record_file WHERE record_id = ?1 ORDER BY ord", 1, rid, 0) {
                elem(b); bc(b, '{');
                LEAVES(b, st, { "path", "path", 'T' }, { "sha256", "sha256", 'T' });
                bc(b, '}');
            }
        });
        OBJ(b, "layout", 0, LEAVES(b, r, { "scheme", "layout_scheme", 'T' }, { "sha256", "layout_sha256", 'T' }));
    });
    leaf(b, r, "testedVersion", "tested_version", 'T');
    if (!null_of(r, "host_extensions", b))
        strings(b, c, "hostExtensions", 1, "SELECT extension FROM record_extension WHERE record_id = ?1 ORDER BY ord", 1, rid, 0);
    leaf(b, r, "measuredAt", "measured_at", 'T');
    leaf(b, r, "latencyLineMs", "latency_line_ms", 'N');
    leaf(b, r, "rules", "rules", 'T');
    history(b, c);
    OBJ(b, "run", 0, {
        leaf(b, r, "id", "run_id", 'T');
        ARR(b, "steps", 1, {
            ROWS(b, c, st, "SELECT * FROM run_step WHERE record_id = ?1 ORDER BY ord", 1, rid, 0) {
                elem(b); bc(b, '{');
                LEAVES(b, st, { "step", "step", 'T' }, { "result", "result", 'T' }, { "code", "code", 'T' });
                OBJ(b, "figures", 0, LEAVES(b, st, { "cpuPercent", "cpu_percent", 'R' }, { "latencyFrames", "latency_frames", 'I' },
                                             { "midiInputsLinked", "midi_inputs_linked", 'I' }, { "xruns", "xruns", 'I' }));
                OBJ(b, "pool", 0, LEAVES(b, st, { "allocationsOn", "pool_allocations_on", 'I' }, { "locksOn", "pool_locks_on", 'I' },
                                          { "syscallsOn", "pool_syscalls_on", 'I' }, { "tasksOnHelpers", "pool_tasks_on_helpers", 'I' },
                                          { "dspLoadOff", "pool_dsp_load_off", 'N' }, { "dspLoadOn", "pool_dsp_load_on", 'N' },
                                          { "xrunsOff", "pool_xruns_off", 'I' }, { "xrunsOn", "pool_xruns_on", 'I' }));
                bc(b, '}');
            }
        });
    });
    OBJ(b, "tool", 0, LEAVES(b, r, { "runner", "tool_runner", 'T' }, { "child", "tool_child", 'T' }, { "interposer", "tool_interposer", 'T' }));
    OBJ(b, "probe", 0, {
        LEAVES(b, r, { "file", "probe_file", 'T' }, { "sha256", "probe_sha256", 'T' }, { "bytes", "probe_bytes", 'I' });
        OBJ(b, "protocol", 0, LEAVES(b, r, { "name", "probe_protocol", 'T' }, { "version", "probe_protocol_version", 'I' }));
        LEAVES(b, r, { "reason", "probe_reason", 'T' }, { "outcome", "probe_outcome", 'T' }, { "complete", "probe_complete", 'B' },
               { "meetsProtocol", "probe_meets_protocol", 'B' });
        OBJ(b, "load", 0, LEAVES(b, r, { "loadavg1", "probe_loadavg1", 'R' }, { "cores", "probe_cores", 'I' }));
        OBJ(b, "machineClass", 0, LEAVES(b, r, { "arch", "mc_arch", 'T' }, { "family", "mc_family", 'T' }, { "coreBand", "mc_core_band", 'T' },
                                          { "clockBand", "mc_clock_band", 'T' }, { "preemptRt", "mc_preempt_rt", 'B' },
                                          { "cstatesLimited", "mc_cstates_limited", 'B' }));
        ARR(b, "ends", 0, {
            ROWS(b, c, st, "SELECT * FROM probe_end WHERE record_id = ?1 ORDER BY ord", 1, rid, 0) {
                elem(b); bc(b, '{');
                LEAVES(b, st, { "step", "step", 'T' }, { "outcome", "outcome", 'T' }, { "exitStatus", "exit_status", 'I' }, { "signal", "signal", 'T' });
                bc(b, '}');
            }
        });
    });
    ARR(b, "verdicts", 1, {
        ROWS(b, c, st, "SELECT * FROM verdict WHERE record_id = ?1 ORDER BY ord", 1, rid, 0) {
            elem(b); bc(b, '{');
            LEAVES(b, st, { "host", "host", 'T' }, { "measured", "measured", 'B' }, { "rating", "rating", 'T' }, { "qualified", "qualified", 'B' },
                   { "hosting", "hosting", 'T' }, { "arm", "arm", 'T' }, { "deciding", "deciding", 'T' });
            reasons(b, c, "verdict_ord", sqlite3_column_int64(st, ci(st, "ord", b)));
            bc(b, '}');
        }
    });
    ARR(b, "cost", 1, {
        ROWS(b, c, st, "SELECT * FROM cost_entry WHERE record_id = ?1 ORDER BY ord", 1, rid, 0) {
            elem(b); bc(b, '{');
            LEAVES(b, st, { "host", "host", 'T' }, { "rate", "rate", 'I' }, { "quantum", "quantum", 'I' });
            OBJ(b, "voices", 0, LEAVES(b, st, { "basis", "voices_basis", 'T' }, { "capacity", "voices_capacity", 'I' }, { "held", "voices_held", 'I' }));
            reasons(b, c, "cost_ord", sqlite3_column_int64(st, ci(st, "ord", b)));
            bc(b, '}');
        }
    });
    OBJ(b, "tiers", 0, {
        tier(b, c, "inProcess");
        tier(b, c, "isolated");
        strings(b, c, "offeredOn", 1, "SELECT tier FROM tier_offered WHERE record_id = ?1 ORDER BY ord", 1, rid, 0);
    });
    OBJ(b, "measurements", 0, {
        ARR(b, "grid", 1, {
            ROWS(b, c, st, "SELECT * FROM cell WHERE record_id = ?1 ORDER BY ord", 1, rid, 0) {
                elem(b); bc(b, '{');
                cell(b, c, st);
                bc(b, '}');
            }
        });
        ARR(b, "unmeasured", 0, {
            ROWS(b, c, st, "SELECT * FROM unmeasured WHERE record_id = ?1 ORDER BY ord", 1, rid, 0) {
                elem(b); bc(b, '{');
                LEAVES(b, st, { "dimension", "dimension", 'T' }, { "code", "code", 'T' }, { "rate", "rate", 'I' }, { "quantum", "quantum", 'I' });
                bc(b, '}');
            }
        });
        OBJ(b, "behaviour", ANCHOR(r, "lifecycle_cycles", b), {
            OBJ(b, "lifecycle", 0, LEAVES(b, r, { "cycles", "lifecycle_cycles", 'I' }, { "failed", "lifecycle_failed", 'I' },
                                           { "instantiated", "lifecycle_instantiated", 'I' }));
            OBJ(b, "threads", 0, LEAVES(b, r, { "before", "threads_before", 'I' }, { "afterFirstInstantiate", "threads_after_first_instantiate", 'I' },
                                         { "afterAllFreed", "threads_after_all_freed", 'I' }));
            OBJ(b, "features", 0, strings(b, c, "required", 1, "SELECT feature FROM feature_required WHERE record_id = ?1 ORDER BY ord", 1, rid, 0));
        });
    });
    ARR(b, "notMeasured", 1, {
        ROWS(b, c, st, "SELECT * FROM not_measured WHERE record_id = ?1 ORDER BY ord", 1, rid, 0) {
            elem(b); bc(b, '{');
            LEAVES(b, st, { "dimension", "dimension", 'T' }, { "code", "code", 'T' });
            bc(b, '}');
        }
    });
    OBJ(b, "adapter", ANCHOR(r, "adapter_admitted", b), {
        LEAVES(b, r, { "admitted", "adapter_admitted", 'B' }, { "host", "adapter_host", 'T' }, { "measured", "adapter_measured", 'B' },
               { "code", "adapter_code", 'T' }, { "measuredAt", "adapter_measured_at", 'T' });
        {
            size_t m = b->n;
            key(b, "versions"); bc(b, '{');
            ROWS(b, c, st, "SELECT name, version FROM record_version WHERE record_id = ?1 AND rejudged = 0 ORDER BY rowid", 1, rid, 0) {
                key(b, (const char *)sqlite3_column_text(st, 0)); jstr(b, (const char *)sqlite3_column_text(st, 1));
            }
            if (!obj_close(b, 0)) trunc_to(b, m);
        }
        if (!null_of(r, "adapter_params", b) && sqlite3_column_int(r, ci(r, "adapter_params", b)) == 1) {
            key(b, "params");
            params(b, c, "SELECT name, number, word FROM adapter_param WHERE record_id = ?1 ORDER BY rowid", 1, rid, 0);
            /* the content, names as written, after the figures (section 9, ruling 12) */
            trunc_to(b, b->n - 1);
            LEAVES(b, r, { "content", "adapter_content", 'T' }, { "loaded", "adapter_loaded", 'T' }, { "refused", "adapter_refused", 'T' });
            bc(b, '}');
        }
        ARR(b, "cells", 0, {
            ROWS(b, c, st, "SELECT * FROM adapter_cell WHERE record_id = ?1 ORDER BY ord", 1, rid, 0) {
                elem(b); bc(b, '{');
                LEAVES(b, st, { "rate", "rate", 'I' }, { "quantum", "quantum", 'I' }, { "admitted", "admitted", 'B' }, { "measured", "measured", 'B' },
                       { "code", "code", 'T' });
                if (sqlite3_column_int(st, ci(st, "params", b)) == 1) {
                    key(b, "params");
                    params(b, c, "SELECT name, number, word FROM adapter_cell_param WHERE record_id = ?1 AND ord = ?2 ORDER BY rowid", 2, rid,
                           sqlite3_column_int64(st, ci(st, "ord", b)));
                }
                bc(b, '}');
            }
        });
    });
    OBJ(b, "memoryRun", ANCHOR(r, "memory_run_measured_at", b), {
        LEAVES(b, r, { "measuredAt", "memory_run_measured_at", 'T' }, { "runId", "memory_run_id", 'T' });
        OBJ(b, "tool", 0, LEAVES(b, r, { "runner", "memory_run_runner", 'T' }, { "child", "memory_run_child", 'T' }));
        ARR(b, "cells", 1, {
            ROWS(b, c, st, "SELECT * FROM memory_run_cell WHERE record_id = ?1 ORDER BY ord", 1, rid, 0) {
                elem(b); bc(b, '{');
                LEAVES(b, st, { "rate", "rate", 'I' }, { "quantum", "quantum", 'I' }, { "outcome", "outcome", 'T' });
                bc(b, '}');
            }
        });
    });
    OBJ(b, "rejudged", ANCHOR(r, "rejudged_at", b), {
        LEAVES(b, r, { "at", "rejudged_at", 'T' }, { "by", "rejudged_by", 'T' });
        OBJ(b, "figures", 0, {
            LEAVES(b, r, { "measuredAt", "rejudged_measured_at", 'T' }, { "runId", "rejudged_run_id", 'T' });
            OBJ(b, "tool", 0, LEAVES(b, r, { "runner", "rejudged_runner", 'T' }, { "child", "rejudged_child", 'T' }, { "interposer", "rejudged_interposer", 'T' }));
            OBJ(b, "adapter", 0, {
                leaf(b, r, "measuredAt", "rejudged_adapter_measured_at", 'T');
                {
                    size_t m = b->n;
                    key(b, "versions"); bc(b, '{');
                    ROWS(b, c, st, "SELECT name, version FROM record_version WHERE record_id = ?1 AND rejudged = 1 ORDER BY rowid", 1, rid, 0) {
                        key(b, (const char *)sqlite3_column_text(st, 0)); jstr(b, (const char *)sqlite3_column_text(st, 1));
                    }
                    if (!obj_close(b, 0)) trunc_to(b, m);
                }
            });
            OBJ(b, "memory", 0, {
                leaf(b, r, "measuredAt", "rejudged_memory_measured_at", 'T');
                OBJ(b, "tool", 0, LEAVES(b, r, { "runner", "rejudged_memory_runner", 'T' }, { "child", "rejudged_memory_child", 'T' }));
            });
        });
        ARR(b, "owes", 0, {
            ROWS(b, c, st, "SELECT * FROM rejudged_owe WHERE record_id = ?1 ORDER BY ord", 1, rid, 0) {
                elem(b); bc(b, '{');
                LEAVES(b, st, { "code", "code", 'T' }, { "measurement", "measurement", 'T' });
                bc(b, '}');
            }
        });
    });
    bc(b, '}');
}

static locale_t c_locale;
static pthread_once_t c_locale_once = PTHREAD_ONCE_INIT;
static void make_c_locale(void) { c_locale = newlocale(LC_ALL_MASK, "C", (locale_t)0); }

/* The document is written under the C locale, whatever the program's: snprintf and strtod follow LC_NUMERIC, and a decimal
 * comma is not JSON. uselocale is per thread, so a thread of the program is not touched. */
static int document(sqlite3 *h, long long record_id, char **json, char *why, size_t why_n);
int pqdb_record_document(sqlite3 *h, long long record_id, char **json, char *why, size_t why_n)
{
    locale_t old;
    int rc;
    pthread_once(&c_locale_once, make_c_locale);
    if (!c_locale) { snprintf(why, why_n, "cannot make the C locale"); *json = NULL; return -1; }
    old = uselocale(c_locale);
    rc = document(h, record_id, json, why, why_n);
    uselocale(old);
    return rc;
}

static int document(sqlite3 *h, long long record_id, char **json, char *why, size_t why_n)
{
    buf b = { 0 };
    ctx c = { h, record_id, "" };
    sqlite3_stmt *r;
    int found = 0;
    *json = NULL;
    if (sqlite3_prepare_v2(h, "SELECT r.*, p.format AS p_format, p.uri AS p_uri, p.sha256 AS p_sha256 FROM record r "
                           "JOIN plugin p ON p.plugin_id = r.plugin_id WHERE r.record_id = ?1", -1, &r, NULL) != SQLITE_OK) {
        snprintf(why, why_n, "cannot read the record: %s", sqlite3_errmsg(h));
        return -1;
    }
    sqlite3_bind_int64(r, 1, record_id);
    if (sqlite3_step(r) == SQLITE_ROW) {
        found = 1;
        record(&b, &c, r);
    }
    sqlite3_finalize(r);
    if (!found) { snprintf(why, why_n, "no record %lld", record_id); free(b.p); return -1; }
    if (b.oom) { snprintf(why, why_n, "out of memory"); free(b.p); return -1; }
    if (b.bad) { snprintf(why, why_n, "cannot read the record: %s", b.bad); free(b.p); return -1; }
    if (b.nonfinite) {
        snprintf(why, why_n, "record %lld: the column %s holds a number that is not finite (JSON has none)", record_id, b.nonfinite);
        free(b.p);
        return -2;
    }
    *json = b.p;
    return 0;
}

/* A number as JSON.stringify writes it, under the C locale whatever the program's (the command's figures and the
 * document's use this one writer). 0, or -1 for a value that is not finite or does not fit in `n` bytes. */
int pqdb_number(double v, char *out, size_t n)
{
    char t[64];
    locale_t old;
    if (!isfinite(v) || !out || n == 0)
        return -1;
    pthread_once(&c_locale_once, make_c_locale);
    if (!c_locale)
        return -1;
    old = uselocale(c_locale);
    js_number(v, t);
    uselocale(old);
    if (strlen(t) + 1 > n)
        return -1;
    memcpy(out, t, strlen(t) + 1);
    return 0;
}
