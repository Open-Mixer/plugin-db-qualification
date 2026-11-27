/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com> */
/* The qualification store's reader (this repository's qualification store spec, sections 2, 3, 4 and 6).
 * It reads no environment variable: the command and the tests do. Never called from a real-time path. */
#define _GNU_SOURCE
#include <plugin-qualification-db/pqdb.h>
#include "pqdb_record.h"
#include "pqdb_sql.h"   /* PQDB_DDL and the migrations, generated from schema/ by the Makefile */

#include <omxcontract/omx_domain.h>
#include <sqlite3.h>

#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <pwd.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define BASE_PATH "/usr/share/omx/qualification/qualification.sqlite"
#define SYSTEM_PATH "/var/lib/omx/qualification/qualification.sqlite"
#define USER_SUFFIX "/.local/share/omx/qualification/qualification.sqlite"
#define BUSY_MS 250

/* the statuses: negative, named by pqdb_code(); a callback of pqdb_each returns a positive value of its own */
enum { S_OK = 0, S_UNREADABLE = -1, S_NOT_A_STORE = -2, S_SCHEMA_MISMATCH = -3, S_SCHEMA_OTHER = -4,
       S_DOMAIN_TOO_OLD = -5, S_WORD_UNKNOWN = -6, S_HOT_JOURNAL = -7, S_BUSY = -8, S_CONTRACT = -9, S_LAYER = -10 };
static const char *const CODES[] = {
    NULL, "qualification-db.unreadable", "qualification-db.not-a-store",
    "qualification-db.schema-mismatch", "qualification-db.schema-other", "qualification-db.domain-too-old",
    "qualification-db.word-unknown", "qualification-db.hot-journal", "qualification-db.busy", NULL,
    "qualification-db.layer-unknown" };

struct pqdb {
    sqlite3 *base, *user;           /* base NULL: no base file, an empty base layer (pqdb_base_absent) */
    char verdict_rating[64], verdict_deciding[64];
    char msg[256];                  /* what the last refusal of pqdb_each said */
};

const char *pqdb_message(const pqdb *db)
{
    return db->msg[0] ? db->msg : NULL;
}

const char *pqdb_code(int status)
{
    if (status >= 0 || status < S_LAYER)
        return NULL;
    return CODES[-status];   /* NULL for S_CONTRACT: the loader's own code is in the error's code */
}

static int fail(pqdb_error *err, int status, const char *fmt, ...)
{
    va_list ap;
    if (err) {
        err->code = pqdb_code(status);
        va_start(ap, fmt);
        vsnprintf(err->message, sizeof err->message, fmt, ap);
        va_end(ap);
    }
    return status;
}

/* the status of a SQLite failure, by its extended code */
static int status_of(sqlite3 *db)
{
    switch (sqlite3_extended_errcode(db)) {
    case SQLITE_READONLY_ROLLBACK: return S_HOT_JOURNAL;
    case SQLITE_BUSY: case SQLITE_BUSY_RECOVERY: case SQLITE_BUSY_SNAPSHOT: case SQLITE_LOCKED: return S_BUSY;
    default: return S_UNREADABLE;
    }
}
static int fail_sql(pqdb_error *err, sqlite3 *db, const char *path, const char *what)
{
    int st = status_of(db);
    if (st == S_HOT_JOURNAL)
        return fail(err, st, "%s: the layer has a hot journal (%s-journal): its writer stopped inside a transaction; "
                    "a read-only reader cannot roll it back, so nothing was changed", path, path);
    if (st == S_BUSY)
        return fail(err, st, "%s: locked by its writer for more than %d ms", path, BUSY_MS);
    return fail(err, st, "%s: %s: %s", path, what, sqlite3_errmsg(db));
}

static int exists(const char *path, int *err_no)
{
    struct stat st;
    if (stat(path, &st) == 0)
        return 1;
    *err_no = errno;
    return 0;
}

static char *uri_of(const char *path, const char *query)
{
    size_t n = strlen(path) * 3 + strlen(query) + 16;
    char *u = malloc(n), *o;
    if (!u)
        return NULL;
    o = u + sprintf(u, "file:");
    for (const char *p = path; *p; p++) {
        if (*p == '%' || *p == '?' || *p == '#')
            o += sprintf(o, "%%%02X", (unsigned char)*p);
        else
            *o++ = *p;
    }
    sprintf(o, "?%s", query);
    return u;
}

static int one_int(sqlite3 *db, const char *sql, int *val, int *got)
{
    sqlite3_stmt *st;
    int rc = sqlite3_prepare_v2(db, sql, -1, &st, NULL);
    if (rc != SQLITE_OK)
        return rc;
    rc = sqlite3_step(st);
    *got = rc == SQLITE_ROW;
    if (rc == SQLITE_ROW) { *val = sqlite3_column_int(st, 0); rc = SQLITE_OK; }
    else if (rc == SQLITE_DONE) rc = SQLITE_OK;
    sqlite3_finalize(st);
    return rc;
}

/* open one layer and read its user_version */
static int open_layer(const char *path, int user, sqlite3 **out, int *version, pqdb_error *err)
{
    char *uri = uri_of(path, user ? "mode=ro" : "mode=ro&immutable=1");
    sqlite3 *db = NULL;
    int rc, got, st;
    if (!uri)
        return fail(err, S_UNREADABLE, "%s: out of memory", path);
    rc = sqlite3_open_v2(uri, &db, SQLITE_OPEN_READONLY | SQLITE_OPEN_URI, NULL);
    free(uri);
    if (rc != SQLITE_OK) {
        st = fail(err, S_UNREADABLE, "%s: SQLite cannot open it: %s", path, db ? sqlite3_errmsg(db) : "out of memory");
        sqlite3_close(db);
        return st;
    }
    sqlite3_extended_result_codes(db, 1);
    if (user)
        sqlite3_busy_timeout(db, BUSY_MS);
    rc = one_int(db, "PRAGMA user_version", version, &got);
    if (rc != SQLITE_OK) {
        st = fail_sql(err, db, path, "cannot read it");
        sqlite3_close(db);
        return st;
    }
    *out = db;
    return S_OK;
}

/* the layer's store_info: user_layer must be what the file's place says */
static int check_store(sqlite3 *db, const char *path, int want_user, pqdb_error *err)
{
    sqlite3_stmt *st;
    int rc = sqlite3_prepare_v2(db, "SELECT user_layer FROM store_info WHERE one = 1", -1, &st, NULL), have = -1;
    if (rc != SQLITE_OK) {
        if (status_of(db) != S_UNREADABLE)
            return fail_sql(err, db, path, "cannot read it");
        return fail(err, S_NOT_A_STORE, "%s: no store_info table: not a qualification store", path);
    }
    rc = sqlite3_step(st);
    if (rc == SQLITE_ROW)
        have = sqlite3_column_int(st, 0);
    sqlite3_finalize(st);
    if (rc != SQLITE_ROW && rc != SQLITE_DONE)
        return fail_sql(err, db, path, "cannot read store_info");
    if (have < 0)
        return fail(err, S_NOT_A_STORE, "%s: no store_info row: not a qualification store", path);
    if (have != want_user)
        return fail(err, S_NOT_A_STORE, "%s: it is a %s layer, opened as the %s", path, have ? "user" : "base",
                    want_user ? "user layer" : "base");
    return S_OK;
}

/* The hosting exception (section 3.4, this pass only): there is no `hosting` domain. The reader does not open its
 * store_domain row and does not check the words `hosting.*` of the word_check columns that have an item of it (the
 * writer checked them against the contract package omx-clap); the other words of such a column are checked as any. Removing the exception is this one function's removal (and its two calls). */
static int hosting_exception(const char *domain)
{
    return strcmp(domain, "hosting") == 0;
}

/* ---- the word check ---- */
typedef struct { omx_domain *d[16]; char name[16][64]; int n; } domains;

static omx_domain *domain_named(const domains *ds, const char *name)
{
    for (int i = 0; i < ds->n; i++)
        if (strcmp(ds->name[i], name) == 0)
            return ds->d[i];
    return NULL;
}
static void domains_close(domains *ds)
{
    for (int i = 0; i < ds->n; i++)
        omx_domain_close(ds->d[i]);
    ds->n = 0;
}

static int open_domains(sqlite3 *db, const char *path, const char *cdir, domains *ds, pqdb_error *err)
{
    sqlite3_stmt *st;
    int rc = sqlite3_prepare_v2(db, "SELECT domain, version FROM store_domain ORDER BY domain", -1, &st, NULL);
    if (rc != SQLITE_OK)
        return fail_sql(err, db, path, "cannot read store_domain");
    ds->n = 0;
    while ((rc = sqlite3_step(st)) == SQLITE_ROW) {
        const char *name = (const char *)sqlite3_column_text(st, 0), *ver = (const char *)sqlite3_column_text(st, 1);
        omx_domain_error e;
        int lrc;
        if (hosting_exception(name))
            continue;
        if (ds->n >= 16 || strlen(name) >= 64) {
            domains_close(ds); sqlite3_finalize(st);
            return fail(err, S_NOT_A_STORE, "%s: store_domain holds too many or too long domains", path);
        }
        lrc = cdir ? omx_domain_open_at(cdir, name, ver, &ds->d[ds->n], &e) : omx_domain_open(name, ver, &ds->d[ds->n], &e);
        if (lrc != 0) {
            int too_old = lrc == OMX_CONTRACT_CODE_PACKAGE_TOO_OLD;
            domains_close(ds); sqlite3_finalize(st);
            if (too_old)
                return fail(err, S_DOMAIN_TOO_OLD, "%s was checked against the domain %s at %s: %s", path, name, ver, e.message);
            if (err) {
                err->code = e.code;
                snprintf(err->message, sizeof err->message, "%s: %s", path, e.message);
            }
            return S_CONTRACT;
        }
        snprintf(ds->name[ds->n], 64, "%s", name);
        ds->n++;
    }
    sqlite3_finalize(st);
    if (rc != SQLITE_DONE) { domains_close(ds); return fail_sql(err, db, path, "cannot read store_domain"); }
    return S_OK;
}

typedef struct { omx_domain *d; char item[96]; } item_ref;
typedef struct { item_ref it[32]; int n; } item_set;

static int in_items(const item_set *s, const char *word, const char *suffix)
{
    omx_domain_word_info wi;
    for (int i = 0; i < s->n; i++) {
        size_t l = strlen(s->it[i].item), m = suffix ? strlen(suffix) : 0;
        if (suffix && (l < m || strcmp(s->it[i].item + l - m, suffix) != 0))
            continue;
        if (omx_domain_word(s->it[i].d, s->it[i].item, word, &wi) == 0)
            return 1;
    }
    return 0;
}
static int has_item(const item_set *s, const char *suffix)
{
    for (int i = 0; i < s->n; i++) {
        size_t l = strlen(s->it[i].item), m = strlen(suffix);
        if (l >= m && strcmp(s->it[i].item + l - m, suffix) == 0)
            return 1;
    }
    return 0;
}
static int all_digits(const char *s)
{
    if (!*s)
        return 0;
    for (; *s; s++)
        if (!isdigit((unsigned char)*s))
            return 0;
    return 1;
}

/* An adapter code is `<host>.<kind>` or `<host>.<kind>-<parameter>` (section 3.4): the host a word of the host
 * profiles, the kind a word of the adapter code kinds, the parameter what the kind takes. */
static int adapter_code_ok(const item_set *s, const char *word)
{
    const char *dot = strchr(word, '.');
    char host[96];
    if (!dot || (size_t)(dot - word) >= sizeof host || !has_item(s, "ADAPTER_CODE_KINDS"))
        return 0;
    snprintf(host, sizeof host, "%.*s", (int)(dot - word), word);
    if (!in_items(s, host, "ADAPTER_HOSTS"))
        return 0;
    for (int i = 0; i < s->n; i++) {
        size_t l = strlen(s->it[i].item);
        int count;
        if (l < 18 || strcmp(s->it[i].item + l - 18, "ADAPTER_CODE_KINDS") != 0)
            continue;
        count = omx_domain_word_count(s->it[i].d, s->it[i].item);
        for (int k = 0; k < count; k++) {
            omx_domain_word_info wi;
            const char *rest = dot + 1;
            size_t kl;
            if (omx_domain_word_at(s->it[i].d, s->it[i].item, k, &wi) != 0)
                continue;
            kl = strlen(wi.word);
            if (strncmp(rest, wi.word, kl) != 0)
                continue;
            if (rest[kl] == 0)
                return strcmp(wi.word, "resp") != 0 && strcmp(wi.word, "exit") != 0 && strcmp(wi.word, "signal") != 0;
            if (rest[kl] != '-')
                continue;
            if (strcmp(wi.word, "resp") == 0 || strcmp(wi.word, "exit") == 0) {
                if (all_digits(rest + kl + 1))
                    return 1;
            } else if (strcmp(wi.word, "signal") == 0) {
                if (in_items(s, rest + kl + 1, "PROBE_SIGNALS"))
                    return 1;
            }
        }
    }
    return 0;
}

static int ident_ok(const char *s)
{
    if (!*s)
        return 0;
    for (; *s; s++)
        if (!isalnum((unsigned char)*s) && *s != '_')
            return 0;
    return 1;
}

/* the distinct words of one column, each looked up in the column's items. A column that has an item of the hosting
 * domain (`hosting_col`) skips only the words that begin `hosting.`; any other word of it must be in its other items. */
static int check_column(sqlite3 *db, const char *path, const char *tbl, const char *col, const item_set *set, int hosting_col,
                        pqdb_error *err)
{
    sqlite3_stmt *words;
    char sql[300];
    int wrc, status = S_OK;
    snprintf(sql, sizeof sql, "SELECT DISTINCT %s FROM %s WHERE %s IS NOT NULL", col, tbl, col);
    if (sqlite3_prepare_v2(db, sql, -1, &words, NULL) != SQLITE_OK)
        return fail(err, S_NOT_A_STORE, "%s: word_check names %s.%s, which is no column of the store", path, tbl, col);
    while ((wrc = sqlite3_step(words)) == SQLITE_ROW) {
        const char *w = (const char *)sqlite3_column_text(words, 0);
        if (hosting_col && strncmp(w, "hosting.", 8) == 0)
            continue;
        if (!in_items(set, w, NULL) && !adapter_code_ok(set, w)) {
            status = fail(err, S_WORD_UNKNOWN, "%s: %s.%s holds the word %s, which none of its items in the "
                          "installed domains holds", path, tbl, col, w);
            break;
        }
    }
    if (status == S_OK && wrc != SQLITE_DONE)
        status = fail_sql(err, db, path, "cannot read the words");
    sqlite3_finalize(words);
    return status;
}

static int check_words(sqlite3 *db, const char *path, const domains *ds, pqdb_error *err)
{
    sqlite3_stmt *wc;
    int rc = sqlite3_prepare_v2(db, "SELECT tbl, col, domain, item FROM word_check ORDER BY tbl, col, domain, item", -1, &wc, NULL);
    int pending = 0, status = S_OK, skip = 0;
    char tbl[64] = "", col[64] = "";
    item_set set;
    if (rc != SQLITE_OK)
        return fail_sql(err, db, path, "cannot read word_check");
    set.n = 0;
    for (;;) {
        const char *t = NULL, *c = NULL;
        rc = sqlite3_step(wc);
        if (rc == SQLITE_ROW) {
            t = (const char *)sqlite3_column_text(wc, 0);
            c = (const char *)sqlite3_column_text(wc, 1);
        } else if (rc != SQLITE_DONE) {
            status = fail_sql(err, db, path, "cannot read word_check");
            break;
        }
        if (pending && (rc == SQLITE_DONE || strcmp(t, tbl) != 0 || strcmp(c, col) != 0)) {
            status = check_column(db, path, tbl, col, &set, skip, err);
            if (status != S_OK)
                break;
            skip = 0;
            set.n = 0;
            pending = 0;
        }
        if (rc == SQLITE_DONE)
            break;
        if (!ident_ok(t) || !ident_ok(c) || strlen(t) >= 64 || strlen(c) >= 64) {
            status = fail(err, S_NOT_A_STORE, "%s: word_check names a table or column that is no identifier", path);
            break;
        }
        {
            omx_domain *d = domain_named(ds, (const char *)sqlite3_column_text(wc, 2));
            if (hosting_exception((const char *)sqlite3_column_text(wc, 2))) {
                snprintf(tbl, sizeof tbl, "%s", t);
                snprintf(col, sizeof col, "%s", c);
                skip = 1;
                pending = 1;
                continue;
            }
            if (!d) {
                status = fail(err, S_NOT_A_STORE, "%s: word_check names the domain %s, which store_domain does not list",
                              path, sqlite3_column_text(wc, 2));
                break;
            }
            if (set.n >= 32) {
                status = fail(err, S_NOT_A_STORE, "%s: %s.%s has too many items", path, t, c);
                break;
            }
            snprintf(tbl, sizeof tbl, "%s", t);
            snprintf(col, sizeof col, "%s", c);
            set.it[set.n].d = d;
            snprintf(set.it[set.n].item, sizeof set.it[set.n].item, "%s", sqlite3_column_text(wc, 3));
            set.n++;
            pending = 1;
        }
    }
    sqlite3_finalize(wc);
    return status;
}

/* ---- the migration of a user layer (spec section 3.6) ---- */
#define SCHEMA_MARK "\n-- @schema\n"

static int exec_sql(sqlite3 *db, const char *sql, const char *path, const char *what, pqdb_error *err)
{
    char *msg = NULL;
    if (sqlite3_exec(db, sql, NULL, NULL, &msg) == SQLITE_OK)
        return S_OK;
    int st = fail(err, S_SCHEMA_OTHER, "%s: %s: %s", path, what, msg ? msg : sqlite3_errmsg(db));
    sqlite3_free(msg);
    return st;
}

/* the user layer at `from`, taken to PQDB_SCHEMA_VERSION in place: a backup copy beside it (<layer>.user_version-<from>),
 * then the step in one transaction, the DDL run at its line `-- @schema`, and the foreign keys, the store and every
 * word checked against the installed domains before COMMIT; any failure rolls back and leaves the layer as it was */
static int migrate_user(const char *path, int from, const char *cdir, pqdb_error *err)
{
    const char *step = from == 1 && PQDB_SCHEMA_VERSION == 2 ? PQDB_MIGRATION_1_TO_2 : NULL;
    const char *mark = step ? strstr(step, SCHEMA_MARK) : NULL;
    char bak[4200], *before = NULL;
    sqlite3 *db = NULL, *copy = NULL;
    sqlite3_backup *b;
    domains ds;
    int st, v = 0, got = 0, rc;
    if (!mark)
        return fail(err, S_SCHEMA_OTHER, "%s: user_version %d, this reader reads %d and has no migration from %d", path,
                    from, PQDB_SCHEMA_VERSION, from);
    if (snprintf(bak, sizeof bak, "%s.user_version-%d", path, from) >= (int)sizeof bak)
        return fail(err, S_UNREADABLE, "%s: the path is too long", path);
    if (sqlite3_open_v2(path, &db, SQLITE_OPEN_READWRITE, NULL) != SQLITE_OK) {
        st = fail(err, S_SCHEMA_OTHER, "%s: user_version %d, and this reader cannot open it to migrate it to %d: %s "
                  "(its writer migrates it)", path, from, PQDB_SCHEMA_VERSION, db ? sqlite3_errmsg(db) : "out of memory");
        sqlite3_close(db);
        return st;
    }
    sqlite3_extended_result_codes(db, 1);
    sqlite3_busy_timeout(db, BUSY_MS);
    if (sqlite3_open_v2(bak, &copy, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, NULL) != SQLITE_OK ||
        !(b = sqlite3_backup_init(copy, "main", db, "main"))) {
        st = fail(err, S_UNREADABLE, "%s: cannot write the backup %s: %s", path, bak, sqlite3_errmsg(copy));
        sqlite3_close(copy);
        sqlite3_close(db);
        return st;
    }
    rc = sqlite3_backup_step(b, -1);
    sqlite3_backup_finish(b);
    if (rc != SQLITE_DONE) {
        st = fail(err, S_UNREADABLE, "%s: cannot write the backup %s: %s", path, bak, sqlite3_errmsg(copy));
        sqlite3_close(copy);
        sqlite3_close(db);
        return st;
    }
    sqlite3_close(copy);
    if ((st = exec_sql(db, "PRAGMA foreign_keys = OFF; PRAGMA legacy_alter_table = ON; BEGIN EXCLUSIVE", path,
                       "cannot begin the migration", err)) != S_OK) {
        sqlite3_close(db);
        return st;
    }
    if (one_int(db, "PRAGMA user_version", &v, &got) != SQLITE_OK || !got) {
        st = fail_sql(err, db, path, "cannot read it");
        goto rollback;
    }
    if (v != from) {   /* another process migrated it meanwhile */
        sqlite3_exec(db, "ROLLBACK", NULL, NULL, NULL);
        sqlite3_close(db);
        return S_OK;
    }
    before = strndup(step, (size_t)(mark - step));
    if (!before) { st = fail(err, S_UNREADABLE, "out of memory"); goto rollback; }
    if ((st = exec_sql(db, before, path, "the migration's first part", err)) != S_OK ||
        (st = exec_sql(db, PQDB_DDL, path, "the DDL", err)) != S_OK ||
        (st = exec_sql(db, mark, path, "the migration's second part", err)) != S_OK)
        goto rollback;
    {
        sqlite3_stmt *fk;
        if (sqlite3_prepare_v2(db, "PRAGMA foreign_key_check", -1, &fk, NULL) != SQLITE_OK) {
            st = fail_sql(err, db, path, "cannot check the foreign keys");
            goto rollback;
        }
        rc = sqlite3_step(fk);
        sqlite3_finalize(fk);
        if (rc != SQLITE_DONE) {
            st = fail(err, S_NOT_A_STORE, "%s: the migration from %d leaves foreign keys unmet", path, from);
            goto rollback;
        }
    }
    if ((st = check_store(db, path, 1, err)) != S_OK || (st = open_domains(db, path, cdir, &ds, err)) != S_OK)
        goto rollback;
    st = check_words(db, path, &ds, err);
    domains_close(&ds);
    if (st != S_OK)
        goto rollback;
    {
        char sql[64];
        snprintf(sql, sizeof sql, "PRAGMA user_version = %d; COMMIT", PQDB_SCHEMA_VERSION);
        if ((st = exec_sql(db, sql, path, "cannot commit the migration", err)) != S_OK)
            goto rollback;
    }
    free(before);
    sqlite3_close(db);
    return S_OK;
rollback:
    free(before);
    sqlite3_exec(db, "ROLLBACK", NULL, NULL, NULL);
    sqlite3_close(db);
    return st;
}

/* ---- open ---- */
static int open_internal(const char *base, const char *user, const char *cdir, pqdb **out, pqdb_error *err)
{
    pqdb *db;
    int vb = 0, vu = 0, st, e, have_base;
    domains ds;
    *out = NULL;
    /* only ENOENT is an absent base, an empty layer; any other reason the file cannot be reached (ENOTDIR, EACCES, ...)
     * leaves it refused by name below */
    have_base = exists(base, &e);
    if (!have_base && e != ENOENT)
        return fail(err, S_UNREADABLE, "%s: the base database cannot be read: %s", base, strerror(e));
    db = calloc(1, sizeof *db);
    if (!db)
        return fail(err, S_UNREADABLE, "out of memory");
    if (have_base && (st = open_layer(base, 0, &db->base, &vb, err)) != S_OK)
        goto bad;
    if (user) {
        if (exists(user, &e)) {
            if ((st = open_layer(user, 1, &db->user, &vu, err)) != S_OK)
                goto bad;
            if (vu > 0 && vu < PQDB_SCHEMA_VERSION) {   /* an older user layer is migrated, then opened again */
                sqlite3_close(db->user);
                db->user = NULL;
                if ((st = migrate_user(user, vu, cdir, err)) != S_OK ||
                    (st = open_layer(user, 1, &db->user, &vu, err)) != S_OK)
                    goto bad;
            }
        } else if (e != ENOENT && e != ENOTDIR) {
            st = fail(err, S_UNREADABLE, "%s: %s", user, strerror(e));
            goto bad;
        }
    }
    if (db->base && db->user && vb != vu) {
        st = fail(err, S_SCHEMA_MISMATCH, "the base %s is at user_version %d and the user layer %s at %d", base, vb, user, vu);
        goto bad;
    }
    for (int i = 0; i < 2; i++) {
        int v = i ? vu : vb;
        const char *p = i ? user : base;
        if (!(i ? db->user : db->base))
            continue;
        if (v == 0) { st = fail(err, S_NOT_A_STORE, "%s: user_version 0: not a qualification store", p); goto bad; }
        if (v != PQDB_SCHEMA_VERSION) {
            st = fail(err, S_SCHEMA_OTHER, "%s: user_version %d, this reader reads %d", p, v, PQDB_SCHEMA_VERSION);
            goto bad;
        }
        if ((st = check_store(i ? db->user : db->base, p, i, err)) != S_OK)
            goto bad;
    }
    for (int i = 0; i < 2; i++) {
        sqlite3 *h = i ? db->user : db->base;
        if (!h)
            continue;
        if ((st = open_domains(h, i ? user : base, cdir, &ds, err)) != S_OK)
            goto bad;
        st = check_words(h, i ? user : base, &ds, err);
        domains_close(&ds);
        if (st != S_OK)
            goto bad;
    }
    *out = db;
    return S_OK;
bad:
    pqdb_close(db);
    return st;
}

int pqdb_open_at(const char *base, const char *user, const char *contract_dir, pqdb **out, pqdb_error *err)
{
    return open_internal(base, user, contract_dir, out, err);
}

int pqdb_open(pqdb_scope scope, pqdb **out, pqdb_error *err)
{
    char path[4096];
    const char *user = SYSTEM_PATH;
    *out = NULL;
    if (scope == PQDB_SCOPE_USER) {
        struct passwd *pw = getpwuid(geteuid());
        if (!pw || !pw->pw_dir || strlen(pw->pw_dir) + sizeof USER_SUFFIX > sizeof path)
            return fail(err, S_UNREADABLE, "no home directory in the password database for the effective user");
        snprintf(path, sizeof path, "%s" USER_SUFFIX, pw->pw_dir);
        user = path;
    } else if (scope != PQDB_SCOPE_SYSTEM) {
        return fail(err, S_UNREADABLE, "unknown scope %d", (int)scope);
    }
    return open_internal(BASE_PATH, user, NULL, out, err);
}

int pqdb_base_absent(const pqdb *db)
{
    return db && !db->base;
}

void pqdb_close(pqdb *db)
{
    if (!db)
        return;
    sqlite3_close(db->base);
    sqlite3_close(db->user);
    free(db);
}

/* ---- results ---- */
/* A layer answers for a cell with the record that claims it (section 4): a cell of a record without the claim is no
   result. In the base, when a set of the reference tier and a set of another tier both hold a key at a cell, the
   reference tier's record holds the claim; the join below reads it through claim's primary key. */
static const char *const SELECT =
    "SELECT p.sha256, p.format, p.uri, r.offer, r.host_class, s.name, "
    "r.pkg_format, r.pkg_name, r.pkg_version, r.pkg_release, r.pkg_distro, r.pkg_arch, "
    "c.rate, c.quantum, c.outcome, c.cost_median, c.cost_percentile_p, c.cost_percentile_value, "
    "c.latency_measured_frames, c.latency_declared_frames, c.mem_first_instance_kb, c.mem_per_instance_kb, "
    "r.binary_path, r.layout_scheme, r.layout_sha256, r.tested_version, r.unpinnable "
    "FROM cell c JOIN record r ON r.record_id = c.record_id JOIN plugin p ON p.plugin_id = r.plugin_id "
    "JOIN claim cl ON cl.plugin_id = r.plugin_id AND cl.offer = r.offer AND cl.host_class = r.host_class "
    "AND cl.rate = c.rate AND cl.quantum = c.quantum AND cl.record_id = r.record_id "
    "LEFT JOIN record_set s ON s.set_id = r.set_id "
    "WHERE (?1 IS NULL OR p.sha256 = ?1) AND (?2 IS NULL OR p.format = ?2) AND (?3 IS NULL OR p.uri = ?3) "
    "AND (?4 IS NULL OR r.offer = ?4) AND (?5 IS NULL OR r.host_class = ?5) AND (?6 < 0 OR c.rate = ?6) "
    "AND (?7 < 0 OR c.quantum = ?7) AND (?8 IS NULL OR r.pkg_format = ?8) AND (?9 IS NULL OR r.pkg_name = ?9) "
    "AND (?10 IS NULL OR r.pkg_version = ?10) AND (?11 IS NULL OR r.pkg_release = ?11) "
    "AND (?12 IS NULL OR r.pkg_distro = ?12) AND (?13 IS NULL OR r.pkg_arch = ?13) "
    "AND (?14 IS NULL OR r.binary_path = ?14) "
    "ORDER BY p.sha256, p.format, p.uri, r.offer, r.host_class, c.rate, c.quantum";

static const char *const SHADOWED =
    "SELECT 1 FROM record r JOIN plugin p ON p.plugin_id = r.plugin_id "
    "WHERE p.sha256 = ?1 AND p.format = ?2 AND p.uri = ?3 AND r.offer = ?4 AND r.host_class = ?5 LIMIT 1";

static int walk_layer(pqdb *owner, sqlite3 *h, const char *layer, sqlite3 *shadow_db, const pqdb_query *q,
                      int (*each)(const pqdb_result *, void *), void *ctx)
{
    sqlite3_stmt *st, *sh = NULL;
    const char *qs[11] = { q->sha256, q->format, q->uri, q->offer, q->host_class, NULL, NULL, q->pkg_format, q->pkg_name,
                           q->pkg_version, q->pkg_release };
    const char *qs2[2] = { q->pkg_distro, q->pkg_arch };
    int rc, ret = 0;
    if (sqlite3_prepare_v2(h, SELECT, -1, &st, NULL) != SQLITE_OK)
        return status_of(h);
    if (shadow_db && sqlite3_prepare_v2(shadow_db, SHADOWED, -1, &sh, NULL) != SQLITE_OK) {
        ret = status_of(shadow_db);
        sqlite3_finalize(st);
        return ret;
    }
    for (int i = 0; i < 11; i++)
        if (i != 5 && i != 6 && qs[i])
            sqlite3_bind_text(st, i + 1, qs[i], -1, SQLITE_STATIC);
    sqlite3_bind_int(st, 6, q->rate);
    sqlite3_bind_int(st, 7, q->quantum);
    for (int i = 0; i < 2; i++)
        if (qs2[i])
            sqlite3_bind_text(st, 12 + i, qs2[i], -1, SQLITE_STATIC);
    if (q->binary_path)
        sqlite3_bind_text(st, 14, q->binary_path, -1, SQLITE_STATIC);
    while ((rc = sqlite3_step(st)) == SQLITE_ROW) {
        pqdb_result r;
        const char *t[6];
        memset(&r, 0, sizeof r);
        for (int i = 0; i < 5; i++)
            t[i] = (const char *)sqlite3_column_text(st, i);
        if (sh) {
            int hit;
            sqlite3_reset(sh);
            for (int i = 0; i < 5; i++)
                sqlite3_bind_text(sh, i + 1, t[i], -1, SQLITE_STATIC);
            hit = sqlite3_step(sh);
            if (hit == SQLITE_ROW)
                continue;
            if (hit != SQLITE_DONE) { ret = status_of(shadow_db); break; }
        }
        r.layer = layer;
        r.sha256 = t[0]; r.format = t[1]; r.uri = t[2]; r.offer = t[3]; r.host_class = t[4];
        r.set = (const char *)sqlite3_column_text(st, 5);
        r.pkg_format = (const char *)sqlite3_column_text(st, 6); r.pkg_name = (const char *)sqlite3_column_text(st, 7);
        r.pkg_version = (const char *)sqlite3_column_text(st, 8); r.pkg_release = (const char *)sqlite3_column_text(st, 9);
        r.pkg_distro = (const char *)sqlite3_column_text(st, 10); r.pkg_arch = (const char *)sqlite3_column_text(st, 11);
        r.rate = sqlite3_column_int(st, 12);
        r.quantum = sqlite3_column_int(st, 13);
        r.outcome = (const char *)sqlite3_column_text(st, 14);
        if (sqlite3_column_type(st, 15) != SQLITE_NULL && sqlite3_column_type(st, 17) != SQLITE_NULL) {
            r.has_cost = 1;
            r.cost_median_ns = sqlite3_column_double(st, 15);
            r.cost_p = sqlite3_column_type(st, 16) == SQLITE_NULL ? 0 : sqlite3_column_int(st, 16);
            r.cost_p_ns = sqlite3_column_double(st, 17);
            if (!isfinite(r.cost_median_ns) || !isfinite(r.cost_p_ns)) {     /* JSON has no Infinity: refused by name */
                snprintf(owner->msg, sizeof owner->msg, "%s layer, %s %s (offer %s, class %s): the column %s holds a number that is not finite",
                         layer, r.format, r.uri, r.offer, r.host_class, isfinite(r.cost_median_ns) ? "cost_percentile_value" : "cost_median");
                ret = S_NOT_A_STORE;
                break;
            }
        }
        if (sqlite3_column_type(st, 18) != SQLITE_NULL || sqlite3_column_type(st, 19) != SQLITE_NULL) {
            r.has_latency = 1;
            r.latency_frames = (long)sqlite3_column_int64(st, sqlite3_column_type(st, 18) != SQLITE_NULL ? 18 : 19);
        }
        if (sqlite3_column_type(st, 20) != SQLITE_NULL && sqlite3_column_type(st, 21) != SQLITE_NULL) {
            r.has_memory = 1;
            r.mem_first_kb = (long)sqlite3_column_int64(st, 20);
            r.mem_per_instance_kb = (long)sqlite3_column_int64(st, 21);
        }
        r.binary_path = (const char *)sqlite3_column_text(st, 22);
        r.layout_scheme = (const char *)sqlite3_column_text(st, 23);
        r.layout_sha256 = (const char *)sqlite3_column_text(st, 24);
        r.tested_version = (const char *)sqlite3_column_text(st, 25);
        r.unpinnable = sqlite3_column_int(st, 26) == 1;
        if ((ret = each(&r, ctx)) != 0)
            break;
    }
    if (ret == 0 && rc != SQLITE_DONE && rc != SQLITE_ROW)
        ret = status_of(h);
    sqlite3_finalize(sh);
    sqlite3_finalize(st);
    return ret;
}

int pqdb_each(const pqdb *db, const pqdb_query *q, int (*each)(const pqdb_result *, void *), void *ctx)
{
    int ret = 0, want_user = 1, want_base = 1;
    sqlite3 *shadow = db->user;
    if (q->layer) {
        /* a named layer is that layer's records alone, none shadowed (section 8, change 3, case 19) */
        if (strcmp(q->layer, "user") == 0) want_base = 0;
        else if (strcmp(q->layer, "base") == 0) want_user = 0, shadow = NULL;
        else return S_LAYER;
    }
    if (want_user && db->user && (ret = walk_layer((pqdb *)db, db->user, "user", NULL, q, each, ctx)) != 0)
        return ret;
    return want_base && db->base ? walk_layer((pqdb *)db, db->base, "base", shadow, q, each, ctx) : 0;
}

/* the list of the record a result is a cell of: the record_file rows in ord order (section 3.7) */
int pqdb_files(const pqdb *db, const pqdb_result *r, int (*each)(const char *path, const char *sha256, void *), void *ctx)
{
    sqlite3 *h = strcmp(r->layer, "user") == 0 ? db->user : db->base;
    sqlite3_stmt *st;
    int rc, ret = 0;
    if (!h)
        return 0;
    if (sqlite3_prepare_v2(h, "SELECT f.path, f.sha256 FROM record_file f "
                           "JOIN claim cl ON cl.record_id = f.record_id JOIN plugin p ON p.plugin_id = cl.plugin_id "
                           "WHERE p.sha256 = ?1 AND p.format = ?2 AND p.uri = ?3 AND cl.offer = ?4 AND cl.host_class = ?5 "
                           "AND cl.rate = ?6 AND cl.quantum = ?7 ORDER BY f.ord", -1, &st, NULL) != SQLITE_OK)
        return status_of(h);
    sqlite3_bind_text(st, 1, r->sha256, -1, SQLITE_STATIC); sqlite3_bind_text(st, 2, r->format, -1, SQLITE_STATIC);
    sqlite3_bind_text(st, 3, r->uri, -1, SQLITE_STATIC); sqlite3_bind_text(st, 4, r->offer, -1, SQLITE_STATIC);
    sqlite3_bind_text(st, 5, r->host_class, -1, SQLITE_STATIC); sqlite3_bind_int(st, 6, r->rate);
    sqlite3_bind_int(st, 7, r->quantum);
    while ((rc = sqlite3_step(st)) == SQLITE_ROW)
        if ((ret = each((const char *)sqlite3_column_text(st, 0), (const char *)sqlite3_column_text(st, 1), ctx)) != 0)
            break;
    if (ret == 0 && rc != SQLITE_DONE && rc != SQLITE_ROW)
        ret = status_of(h);
    sqlite3_finalize(st);
    return ret;
}

int pqdb_verdicts(const pqdb *db, const pqdb_result *r, int (*each)(const char *host, const pqdb_verdict *, void *), void *ctx)
{
    sqlite3 *h = strcmp(r->layer, "user") == 0 ? db->user : db->base;
    sqlite3_stmt *st;
    int rc, ret = 0;
    if (!h)
        return 0;
    if (sqlite3_prepare_v2(h, "SELECT v.host, v.rating, v.deciding, v.measured, v.qualified FROM verdict v "
                           "JOIN claim cl ON cl.record_id = v.record_id JOIN plugin p ON p.plugin_id = cl.plugin_id "
                           "WHERE p.sha256 = ?1 AND p.format = ?2 AND p.uri = ?3 AND cl.offer = ?4 AND cl.host_class = ?5 "
                           "AND cl.rate = ?6 AND cl.quantum = ?7 ORDER BY v.ord", -1, &st, NULL) != SQLITE_OK)
        return status_of(h);
    sqlite3_bind_text(st, 1, r->sha256, -1, SQLITE_STATIC); sqlite3_bind_text(st, 2, r->format, -1, SQLITE_STATIC);
    sqlite3_bind_text(st, 3, r->uri, -1, SQLITE_STATIC); sqlite3_bind_text(st, 4, r->offer, -1, SQLITE_STATIC);
    sqlite3_bind_text(st, 5, r->host_class, -1, SQLITE_STATIC); sqlite3_bind_int(st, 6, r->rate);
    sqlite3_bind_int(st, 7, r->quantum);
    while ((rc = sqlite3_step(st)) == SQLITE_ROW) {
        pqdb_verdict v;
        v.rating = (const char *)sqlite3_column_text(st, 1);
        v.deciding = (const char *)sqlite3_column_text(st, 2);
        v.measured = sqlite3_column_int(st, 3);
        v.qualified = sqlite3_column_int(st, 4);
        if ((ret = each((const char *)sqlite3_column_text(st, 0), &v, ctx)) != 0)
            break;
    }
    if (ret == 0 && rc != SQLITE_DONE && rc != SQLITE_ROW)
        ret = status_of(h);
    sqlite3_finalize(st);
    return ret;
}

int pqdb_verdict_of(const pqdb *db, const pqdb_result *r, const char *host, pqdb_verdict *out)
{
    pqdb *w = (pqdb *)db;     /* the two text buffers are the handle's, valid until the next call */
    sqlite3 *h = strcmp(r->layer, "user") == 0 ? db->user : db->base;
    sqlite3_stmt *st;
    int rc;
    if (!h)
        return 1;
    if (sqlite3_prepare_v2(h, "SELECT v.rating, v.deciding, v.measured, v.qualified FROM verdict v "
                           "JOIN claim cl ON cl.record_id = v.record_id JOIN plugin p ON p.plugin_id = cl.plugin_id "
                           "WHERE p.sha256 = ?1 AND p.format = ?2 AND p.uri = ?3 AND cl.offer = ?4 AND cl.host_class = ?5 "
                           "AND cl.rate = ?6 AND cl.quantum = ?7 AND v.host = ?8", -1, &st, NULL) != SQLITE_OK)
        return status_of(h);
    sqlite3_bind_text(st, 1, r->sha256, -1, SQLITE_STATIC); sqlite3_bind_text(st, 2, r->format, -1, SQLITE_STATIC);
    sqlite3_bind_text(st, 3, r->uri, -1, SQLITE_STATIC); sqlite3_bind_text(st, 4, r->offer, -1, SQLITE_STATIC);
    sqlite3_bind_text(st, 5, r->host_class, -1, SQLITE_STATIC); sqlite3_bind_int(st, 6, r->rate);
    sqlite3_bind_int(st, 7, r->quantum); sqlite3_bind_text(st, 8, host, -1, SQLITE_STATIC);
    rc = sqlite3_step(st);
    if (rc == SQLITE_ROW) {
        snprintf(w->verdict_rating, sizeof w->verdict_rating, "%s", sqlite3_column_text(st, 0));
        out->rating = w->verdict_rating;
        if (sqlite3_column_type(st, 1) == SQLITE_NULL) {
            out->deciding = NULL;
        } else {
            snprintf(w->verdict_deciding, sizeof w->verdict_deciding, "%s", sqlite3_column_text(st, 1));
            out->deciding = w->verdict_deciding;
        }
        out->measured = sqlite3_column_int(st, 2);
        out->qualified = sqlite3_column_int(st, 3);
        rc = 0;
    } else {
        rc = rc == SQLITE_DONE ? 1 : status_of(h);
    }
    sqlite3_finalize(st);
    return rc;
}

/* ---- whole records ---- */
int pqdb_record_json(const pqdb *db, const pqdb_result *r, char **json, pqdb_error *err)
{
    sqlite3 *h = strcmp(r->layer, "user") == 0 ? db->user : db->base;
    sqlite3_stmt *st;
    long long rid = 0;
    int rc, found = 0;
    char why[200];
    *json = NULL;
    if (!h)
        return fail(err, S_UNREADABLE, "the %s layer is not open: no record to read", r->layer);
    if (sqlite3_prepare_v2(h, "SELECT cl.record_id FROM claim cl JOIN plugin p ON p.plugin_id = cl.plugin_id "
                           "WHERE p.sha256 = ?1 AND p.format = ?2 AND p.uri = ?3 AND cl.offer = ?4 AND cl.host_class = ?5 "
                           "AND cl.rate = ?6 AND cl.quantum = ?7", -1, &st, NULL) != SQLITE_OK) {
        rc = status_of(h);
        return fail(err, rc, "cannot read the record of %s: %s", r->uri, sqlite3_errmsg(h));
    }
    sqlite3_bind_text(st, 1, r->sha256, -1, SQLITE_STATIC); sqlite3_bind_text(st, 2, r->format, -1, SQLITE_STATIC);
    sqlite3_bind_text(st, 3, r->uri, -1, SQLITE_STATIC); sqlite3_bind_text(st, 4, r->offer, -1, SQLITE_STATIC);
    sqlite3_bind_text(st, 5, r->host_class, -1, SQLITE_STATIC); sqlite3_bind_int(st, 6, r->rate);
    sqlite3_bind_int(st, 7, r->quantum);
    rc = sqlite3_step(st);
    if (rc == SQLITE_ROW) { found = 1; rid = sqlite3_column_int64(st, 0); }
    sqlite3_finalize(st);
    if (!found)
        return fail(err, S_UNREADABLE, "no record of %s %s (offer %s, class %s) at %d/%d in the %s layer", r->format, r->uri,
                    r->offer, r->host_class, r->rate, r->quantum, r->layer);
    rc = pqdb_record_document(h, rid, json, why, sizeof why);
    if (rc == -2)     /* a value no document can hold: the store is not what the writer writes */
        return fail(err, S_NOT_A_STORE, "%s layer: %s", r->layer, why);
    if (rc != 0)
        return fail(err, S_UNREADABLE, "%s", why);
    return S_OK;
}

/* ---- counts ---- */
typedef struct { char *format, *uri; int offered; } plug;
typedef struct { plug *p; size_t n, cap; } plugs;

static int plug_cmp(const void *a, const void *b)
{
    const plug *x = a, *y = b;
    int c = strcmp(x->format, y->format);
    return c ? c : strcmp(x->uri, y->uri);
}
static int collect_plugins(sqlite3 *h, sqlite3 *shadow_db, plugs *out)
{
    sqlite3_stmt *st, *sh = NULL;
    int rc, ret = S_OK;
    if (sqlite3_prepare_v2(h, "SELECT p.format, p.uri, r.offer, r.host_class, p.sha256, "
                           "EXISTS (SELECT 1 FROM tier_offered t WHERE t.record_id = r.record_id) "
                           "FROM record r JOIN plugin p ON p.plugin_id = r.plugin_id "
                           /* a record that claims no cell answers for nothing and is not counted (section 4) */
                           "WHERE EXISTS (SELECT 1 FROM claim cl WHERE cl.plugin_id = r.plugin_id AND cl.offer = r.offer "
                           "AND cl.host_class = r.host_class AND cl.record_id = r.record_id)", -1, &st, NULL) != SQLITE_OK)
        return status_of(h);
    if (shadow_db && sqlite3_prepare_v2(shadow_db, SHADOWED, -1, &sh, NULL) != SQLITE_OK) {
        ret = status_of(shadow_db);
        sqlite3_finalize(st);
        return ret;
    }
    while ((rc = sqlite3_step(st)) == SQLITE_ROW) {
        plug *p;
        if (sh) {     /* a base record the user layer has a record of the shadow key for is hidden (section 4) */
            int hit;
            sqlite3_reset(sh);
            sqlite3_bind_text(sh, 1, (const char *)sqlite3_column_text(st, 4), -1, SQLITE_STATIC);
            sqlite3_bind_text(sh, 2, (const char *)sqlite3_column_text(st, 0), -1, SQLITE_STATIC);
            sqlite3_bind_text(sh, 3, (const char *)sqlite3_column_text(st, 1), -1, SQLITE_STATIC);
            sqlite3_bind_text(sh, 4, (const char *)sqlite3_column_text(st, 2), -1, SQLITE_STATIC);
            sqlite3_bind_text(sh, 5, (const char *)sqlite3_column_text(st, 3), -1, SQLITE_STATIC);
            hit = sqlite3_step(sh);
            if (hit == SQLITE_ROW)
                continue;
            if (hit != SQLITE_DONE) { ret = status_of(shadow_db); break; }
        }
        if (out->n == out->cap) {
            size_t cap = out->cap ? out->cap * 2 : 256;
            plug *np = realloc(out->p, cap * sizeof *np);
            if (!np) { ret = S_UNREADABLE; break; }
            out->p = np; out->cap = cap;
        }
        p = &out->p[out->n];
        p->format = strdup((const char *)sqlite3_column_text(st, 0));
        p->uri = strdup((const char *)sqlite3_column_text(st, 1));
        p->offered = sqlite3_column_int(st, 5);
        if (!p->format || !p->uri) { free(p->format); free(p->uri); ret = S_UNREADABLE; break; }
        out->n++;
    }
    if (ret == S_OK && rc != SQLITE_DONE && rc != SQLITE_ROW)
        ret = status_of(h);
    sqlite3_finalize(sh);
    sqlite3_finalize(st);
    return ret;
}

int pqdb_counts(const pqdb *db, const char *layer, int (*each)(const char *format, long plugins, long offered, long not_offered, void *),
                void *ctx)
{
    plugs all = { NULL, 0, 0 };
    int ret = S_OK, want_user = 1, want_base = 1;
    sqlite3 *shadow = db->user;
    if (layer) {
        if (strcmp(layer, "user") == 0) want_base = 0;
        else if (strcmp(layer, "base") == 0) want_user = 0, shadow = NULL;
        else return S_LAYER;
    }
    if (want_user && db->user)
        ret = collect_plugins(db->user, NULL, &all);
    if (ret == S_OK && want_base && db->base)
        ret = collect_plugins(db->base, shadow, &all);
    if (ret == S_OK && all.n > 0) {
        size_t i = 0, w = 0;
        qsort(all.p, all.n, sizeof *all.p, plug_cmp);
        /* a plugin is a format and a uri: records of one count once, and it is offered when any of them is */
        for (i = 0; i < all.n; i++) {
            if (w > 0 && plug_cmp(&all.p[w - 1], &all.p[i]) == 0) {
                all.p[w - 1].offered |= all.p[i].offered;
                free(all.p[i].format); free(all.p[i].uri);
            } else {
                all.p[w++] = all.p[i];
            }
        }
        for (i = 0; i < w && ret == S_OK;) {
            long plugins = 0, offered = 0;
            size_t j = i;
            while (j < w && strcmp(all.p[j].format, all.p[i].format) == 0) {
                plugins++;
                offered += all.p[j].offered != 0;
                j++;
            }
            ret = each(all.p[i].format, plugins, offered, plugins - offered, ctx);
            i = j;
        }
        for (i = 0; i < w; i++) { free(all.p[i].format); free(all.p[i].uri); }
    }
    free(all.p);
    return ret;
}
