/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com> */
/* plugin-qualification-db: the command over the reader (this repository's qualification store spec, sections 2 and 6).
 * The only program that reads PLUGIN_QUALIFICATION_DB_BASE, PLUGIN_QUALIFICATION_DB_USER and OMX_CONTRACT_PATH. */
#define _GNU_SOURCE
#include <plugin-qualification-db/pqdb.h>

#include <pwd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define INSTALLED_BASE "/usr/share/omx/qualification/qualification.sqlite"
#define HOME_SUFFIX "/.local/share/omx/qualification/qualification.sqlite"

static void usage(void)
{
    fprintf(stderr,
        "usage: plugin-qualification-db query [--sha256 H] [--format F] [--uri U] [--offer O] [--host-class C]\n"
        "           [--rate N] [--quantum N] [--pkg-format F --pkg-name N --pkg-version V --pkg-release R\n"
        "           --pkg-distro D --pkg-arch A] [--binary-path P] [--layer user|base] [--records] --json [common options]\n"
        "       plugin-qualification-db counts [--layer user|base] --json [common options]\n"
        "       plugin-qualification-db check [common options]\n"
        "common options: --base PATH --user PATH --contract-dir DIR | --scope user|system\n"
        "  (absent: PLUGIN_QUALIFICATION_DB_BASE, PLUGIN_QUALIFICATION_DB_USER, OMX_CONTRACT_PATH, then the installed\n"
        "  places; --user '' reads no user layer; --scope opens the production places of that scope and takes neither\n"
        "  --base, --user nor --contract-dir; --records takes neither --rate nor --quantum)\n");
}

static void json_string(const char *s)
{
    if (!s) { fputs("null", stdout); return; }
    putchar('"');
    for (; *s; s++) {
        unsigned char c = (unsigned char)*s;
        if (c == '"' || c == '\\') printf("\\%c", c);
        else if (c < 0x20) printf("\\u%04x", c);
        else putchar(c);
    }
    putchar('"');
}
static void field(const char *name, const char *v, int *first)
{
    printf("%s\"%s\":", *first ? "" : ",", name);
    json_string(v);
    *first = 0;
}

typedef struct { pqdb *db; int bad; int records; char last[600]; } printer;

static int print_verdict(const char *host, const pqdb_verdict *v, void *ctx)
{
    int *n = ctx;
    printf("%s{\"host\":", (*n)++ ? "," : ""); json_string(host);
    printf(",\"rating\":"); json_string(v->rating);
    printf(",\"measured\":%d,\"qualified\":%d,\"deciding\":", v->measured, v->qualified); json_string(v->deciding);
    putchar('}');
    return 0;
}
static int print_file(const char *path, const char *sha256, void *ctx)
{
    int *n = ctx;
    printf("%s{\"path\":", (*n)++ ? "," : ""); json_string(path);
    printf(",\"sha256\":"); json_string(sha256);
    putchar('}');
    return 0;
}

static int print_result(const pqdb_result *r, void *ctx)
{
    printer *p = ctx;
    const struct { const char *name; const char *v; } words[] = {
        { "layer", r->layer }, { "sha256", r->sha256 }, { "format", r->format }, { "uri", r->uri }, { "offer", r->offer },
        { "host_class", r->host_class }, { "set", r->set }, { "pkg_format", r->pkg_format }, { "pkg_name", r->pkg_name },
        { "pkg_version", r->pkg_version }, { "pkg_release", r->pkg_release }, { "pkg_distro", r->pkg_distro },
        { "pkg_arch", r->pkg_arch }, { "binary_path", r->binary_path }, { "layout_scheme", r->layout_scheme },
        { "layout_sha256", r->layout_sha256 }, { "tested_version", r->tested_version } };
    int first = 1, n = 0;
    putchar('{');
    for (size_t i = 0; i < sizeof words / sizeof *words; i++)
        field(words[i].name, words[i].v, &first);
    printf(",\"unpinnable\":%d,\"files\":[", r->unpinnable);
    if (pqdb_files(p->db, r, print_file, &n) != 0 || n == 0)
        p->bad = 1;
    printf("],\"rate\":%d,\"quantum\":%d", r->rate, r->quantum);
    printf(",\"outcome\":"); json_string(r->outcome);
    {
        char m[64], q[64];
        if (pqdb_number(r->cost_median_ns, m, sizeof m) != 0 || pqdb_number(r->cost_p_ns, q, sizeof q) != 0) {
            p->bad = 1;
            strcpy(m, "0"); strcpy(q, "0");
        }
        printf(",\"cost_median_ns\":%s,\"cost_p_ns\":%s,\"cost_p\":%d,\"has_cost\":%d", m, q, r->cost_p, r->has_cost);
    }
    printf(",\"latency_frames\":%ld,\"has_latency\":%d", r->latency_frames, r->has_latency);
    printf(",\"mem_first_kb\":%ld,\"mem_per_instance_kb\":%ld,\"has_memory\":%d", r->mem_first_kb, r->mem_per_instance_kb,
           r->has_memory);
    printf(",\"verdicts\":[");
    n = 0;
    if (pqdb_verdicts(p->db, r, print_verdict, &n) != 0)
        p->bad = 1;
    puts("]}");
    return 0;
}

/* one line a record: the results of one record are cells of one shadow key, in a row */
static int print_record(const pqdb_result *r, void *ctx)
{
    printer *p = ctx;
    char key[600], *json = NULL;
    pqdb_error e;
    snprintf(key, sizeof key, "%s/%s/%s/%s/%s/%s", r->layer, r->sha256, r->format, r->uri, r->offer, r->host_class);
    if (strcmp(key, p->last) == 0)
        return 0;
    snprintf(p->last, sizeof p->last, "%s", key);
    if (pqdb_record_json(p->db, r, &json, &e) != 0) {
        fprintf(stderr, "%s %s\n", e.code ? e.code : "qualification-db.unreadable", e.message);
        p->bad = 1;
        return 0;
    }
    printf("{\"layer\":"); json_string(r->layer);
    printf(",\"sha256\":"); json_string(r->sha256);
    printf(",\"format\":"); json_string(r->format);
    printf(",\"uri\":"); json_string(r->uri);
    printf(",\"offer\":"); json_string(r->offer);
    printf(",\"host_class\":"); json_string(r->host_class);
    printf(",\"record\":%s}\n", json);
    free(json);
    return 0;
}

static int print_count(const char *format, long plugins, long offered, long not_offered, void *ctx)
{
    (void)ctx;
    printf("{\"format\":"); json_string(format);
    printf(",\"plugins\":%ld,\"offered\":%ld,\"not_offered\":%ld}\n", plugins, offered, not_offered);
    return 0;
}

/* check: the key's SHA-256 is the SHA-256 of the list's entry at binary_path (section 3.7), for every record */
typedef struct { const char *path; char sha[65]; int found; } entry_probe;
static int find_entry(const char *path, const char *sha256, void *ctx)
{
    entry_probe *e = ctx;
    if (strcmp(path, e->path) == 0) { e->found = 1; snprintf(e->sha, sizeof e->sha, "%s", sha256); }
    return 0;
}
typedef struct { pqdb *db; char last[600]; int bad; pqdb_error err; } checker;
static int check_key(const pqdb_result *r, void *ctx)
{
    checker *c = ctx;
    entry_probe e;
    char key[600];
    snprintf(key, sizeof key, "%s/%s/%s/%s/%s/%s", r->layer, r->sha256, r->format, r->uri, r->offer, r->host_class);
    if (strcmp(key, c->last) == 0)
        return 0;
    snprintf(c->last, sizeof c->last, "%s", key);
    e.path = r->binary_path; e.sha[0] = 0; e.found = 0;
    if (pqdb_files(c->db, r, find_entry, &e) != 0) {
        c->err.code = "qualification-db.unreadable";
        snprintf(c->err.message, sizeof c->err.message, "the list of %s %s (%s layer) cannot be read", r->format, r->uri, r->layer);
        return 1;
    }
    if (!e.found || strcmp(e.sha, r->sha256) != 0) {
        c->err.code = "qualification-db.key-mismatch";
        snprintf(c->err.message, sizeof c->err.message, "%s layer, %s %s (offer %s, class %s): the key %s is not the SHA-256 of the list's entry at %s (%s)",
                 r->layer, r->format, r->uri, r->offer, r->host_class, r->sha256, r->binary_path, e.found ? e.sha : "no such entry");
        c->bad = 1;
        return 1;
    }
    return 0;
}

int main(int argc, char **argv)
{
    const char *base = NULL, *user = NULL, *cdir = NULL, *scope = NULL, *layer = NULL;
    const char *sha = NULL, *format = NULL, *uri = NULL, *offer = NULL, *cls = NULL, *bpath = NULL;
    const char *pk[6] = { NULL };
    int rate = -1, quantum = -1, json = 0, have_user = 0, records = 0;
    pqdb_query q = PQDB_QUERY_ANY;
    pqdb *db = NULL;
    pqdb_error err;
    const char *verb;
    char homepath[4096];
    int is_query, is_counts, is_check;

    if (argc < 2) { usage(); return 2; }
    verb = argv[1];
    is_query = strcmp(verb, "query") == 0; is_counts = strcmp(verb, "counts") == 0; is_check = strcmp(verb, "check") == 0;
    if (!is_query && !is_counts && !is_check) { usage(); return 2; }
    for (int i = 2; i < argc; i++) {
        const char *a = argv[i];
        const char **target = NULL;
        int *num = NULL;
        if (strcmp(a, "--json") == 0 && !is_check) { json = 1; continue; }
        if (strcmp(a, "--records") == 0 && is_query) { records = 1; continue; }
        if (strcmp(a, "--base") == 0) target = &base;
        else if (strcmp(a, "--user") == 0) { target = &user; have_user = 1; }
        else if (strcmp(a, "--contract-dir") == 0) target = &cdir;
        else if (strcmp(a, "--scope") == 0) target = &scope;
        else if (strcmp(a, "--layer") == 0 && !is_check) target = &layer;
        else if (!is_query) { usage(); return 2; }
        else if (strcmp(a, "--sha256") == 0) target = &sha;
        else if (strcmp(a, "--format") == 0) target = &format;
        else if (strcmp(a, "--uri") == 0) target = &uri;
        else if (strcmp(a, "--offer") == 0) target = &offer;
        else if (strcmp(a, "--host-class") == 0) target = &cls;
        else if (strcmp(a, "--rate") == 0) num = &rate;
        else if (strcmp(a, "--quantum") == 0) num = &quantum;
        else if (strcmp(a, "--binary-path") == 0) target = &bpath;
        else if (strcmp(a, "--pkg-format") == 0) target = &pk[0];
        else if (strcmp(a, "--pkg-name") == 0) target = &pk[1];
        else if (strcmp(a, "--pkg-version") == 0) target = &pk[2];
        else if (strcmp(a, "--pkg-release") == 0) target = &pk[3];
        else if (strcmp(a, "--pkg-distro") == 0) target = &pk[4];
        else if (strcmp(a, "--pkg-arch") == 0) target = &pk[5];
        else { usage(); return 2; }
        if (++i >= argc) { usage(); return 2; }
        if (num) {
            char *end;
            long v = strtol(argv[i], &end, 10);
            if (!*argv[i] || *end || v < 0 || v > 100000000) { fprintf(stderr, "%s wants a number\n", a); return 2; }
            *num = (int)v;
        } else {
            *target = argv[i];
        }
    }
    if (!is_check && !json) { usage(); return 2; }
    if (layer && strcmp(layer, "user") != 0 && strcmp(layer, "base") != 0) { fprintf(stderr, "--layer is user or base\n"); return 2; }
    if (records && (rate >= 0 || quantum >= 0)) { fprintf(stderr, "--records is a record, not a cell: it takes neither --rate nor --quantum\n"); return 2; }
    if (scope) {
        if (strcmp(scope, "user") != 0 && strcmp(scope, "system") != 0) { fprintf(stderr, "--scope is user or system\n"); return 2; }
        if (base || have_user || cdir) { fprintf(stderr, "--scope opens the production places: it takes neither --base, --user nor --contract-dir\n"); return 2; }
        if (pqdb_open(strcmp(scope, "system") == 0 ? PQDB_SCOPE_SYSTEM : PQDB_SCOPE_USER, &db, &err) != 0) {
            if (is_check) printf("%s %s\n", err.code, err.message);
            else fprintf(stderr, "%s %s\n", err.code, err.message);
            return 1;
        }
    } else {
        if (!base) base = getenv("PLUGIN_QUALIFICATION_DB_BASE");
        if (!base || !*base) base = INSTALLED_BASE;
        if (!have_user) user = getenv("PLUGIN_QUALIFICATION_DB_USER");
        if (!user) {
            struct passwd *pw = getpwuid(geteuid());
            if (pw && pw->pw_dir && strlen(pw->pw_dir) + sizeof HOME_SUFFIX <= sizeof homepath) {
                snprintf(homepath, sizeof homepath, "%s" HOME_SUFFIX, pw->pw_dir);
                user = homepath;
            }
        }
        if (user && !*user) user = NULL;
        if (!cdir) cdir = getenv("OMX_CONTRACT_PATH");
        if (cdir && !*cdir) cdir = NULL;

        if (pqdb_open_at(base, user, cdir, &db, &err) != 0) {
            if (is_check)
                printf("%s %s\n", err.code, err.message);
            else
                fprintf(stderr, "%s %s\n", err.code, err.message);
            return 1;
        }
    }
    if (is_check) {
        checker c;
        const char *layers[2] = { "user", "base" };
        int rc = 0;
        memset(&c, 0, sizeof c);
        c.db = db;
        for (int i = 0; i < 2 && rc == 0; i++) {
            pqdb_query lq = PQDB_QUERY_ANY;
            lq.layer = layers[i];
            c.last[0] = 0;
            rc = pqdb_each(db, &lq, check_key, &c);
        }
        if (rc != 0 && !c.err.code) {
            printf("%s the records could not be read\n", pqdb_code(rc) ? pqdb_code(rc) : "qualification-db.unreadable");
            pqdb_close(db);
            return 1;
        }
        if (rc != 0) {
            printf("%s %s\n", c.err.code, c.err.message);
            pqdb_close(db);
            return 1;
        }
        puts("ok");
        pqdb_close(db);
        return 0;
    }
    if (is_counts) {
        int rc = pqdb_counts(db, layer, print_count, NULL);
        pqdb_close(db);
        if (rc != 0) {
            fprintf(stderr, "%s\n", pqdb_code(rc) ? pqdb_code(rc) : "qualification-db.unreadable");
            return 1;
        }
        return 0;
    }
    q.sha256 = sha; q.format = format; q.uri = uri; q.offer = offer; q.host_class = cls;
    q.rate = rate; q.quantum = quantum; q.binary_path = bpath; q.layer = layer;
    q.pkg_format = pk[0]; q.pkg_name = pk[1]; q.pkg_version = pk[2]; q.pkg_release = pk[3]; q.pkg_distro = pk[4]; q.pkg_arch = pk[5];
    {
        printer p;
        int rc;
        memset(&p, 0, sizeof p);
        p.db = db;
        rc = pqdb_each(db, &q, records ? print_record : print_result, &p);
        if (rc == 0 && p.bad) rc = -2;
        if (rc != 0) {
            fprintf(stderr, "%s%s%s\n", pqdb_code(rc) ? pqdb_code(rc) : "qualification-db.unreadable", pqdb_message(db) ? " " : "",
                    pqdb_message(db) ? pqdb_message(db) : "");
            pqdb_close(db);
            return 1;
        }
        pqdb_close(db);
    }
    return 0;
}
