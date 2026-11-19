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
        "           --pkg-distro D --pkg-arch A] --json [common options]\n"
        "       plugin-qualification-db check [common options]\n"
        "common options: --base PATH --user PATH --contract-dir DIR\n"
        "  (absent: PLUGIN_QUALIFICATION_DB_BASE, PLUGIN_QUALIFICATION_DB_USER, OMX_CONTRACT_PATH, then the installed\n"
        "  places; --user '' reads no user layer)\n");
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

typedef struct { pqdb *db; int bad; } printer;

static int print_verdict(const char *host, const pqdb_verdict *v, void *ctx)
{
    int *n = ctx;
    printf("%s{\"host\":", (*n)++ ? "," : ""); json_string(host);
    printf(",\"rating\":"); json_string(v->rating);
    printf(",\"measured\":%d,\"qualified\":%d,\"deciding\":", v->measured, v->qualified); json_string(v->deciding);
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
        { "pkg_arch", r->pkg_arch } };
    int first = 1;
    putchar('{');
    for (size_t i = 0; i < sizeof words / sizeof *words; i++)
        field(words[i].name, words[i].v, &first);
    printf(",\"rate\":%d,\"quantum\":%d", r->rate, r->quantum);
    printf(",\"outcome\":"); json_string(r->outcome);
    printf(",\"cost_median_ns\":%.17g,\"cost_p_ns\":%.17g,\"cost_p\":%d,\"has_cost\":%d", r->cost_median_ns, r->cost_p_ns,
           r->cost_p, r->has_cost);
    printf(",\"latency_frames\":%ld,\"has_latency\":%d", r->latency_frames, r->has_latency);
    printf(",\"mem_first_kb\":%ld,\"mem_per_instance_kb\":%ld,\"has_memory\":%d", r->mem_first_kb, r->mem_per_instance_kb,
           r->has_memory);
    printf(",\"verdicts\":[");
    {
        int n = 0;
        if (pqdb_verdicts(p->db, r, print_verdict, &n) != 0)
            p->bad = 1;
    }
    puts("]}");
    return 0;
}

int main(int argc, char **argv)
{
    const char *base = NULL, *user = NULL, *cdir = NULL;
    const char *sha = NULL, *format = NULL, *uri = NULL, *offer = NULL, *cls = NULL;
    const char *pk[6] = { NULL };
    int rate = -1, quantum = -1, json = 0, have_user = 0;
    pqdb_query q;
    pqdb *db = NULL;
    pqdb_error err;
    const char *verb;
    char homepath[4096];

    if (argc < 2) { usage(); return 2; }
    verb = argv[1];
    if (strcmp(verb, "query") != 0 && strcmp(verb, "check") != 0) { usage(); return 2; }
    for (int i = 2; i < argc; i++) {
        const char *a = argv[i];
        const char **target = NULL;
        int *num = NULL;
        if (strcmp(a, "--json") == 0) { json = 1; continue; }
        if (strcmp(a, "--base") == 0) target = &base;
        else if (strcmp(a, "--user") == 0) { target = &user; have_user = 1; }
        else if (strcmp(a, "--contract-dir") == 0) target = &cdir;
        else if (strcmp(verb, "query") != 0) { usage(); return 2; }
        else if (strcmp(a, "--sha256") == 0) target = &sha;
        else if (strcmp(a, "--format") == 0) target = &format;
        else if (strcmp(a, "--uri") == 0) target = &uri;
        else if (strcmp(a, "--offer") == 0) target = &offer;
        else if (strcmp(a, "--host-class") == 0) target = &cls;
        else if (strcmp(a, "--rate") == 0) num = &rate;
        else if (strcmp(a, "--quantum") == 0) num = &quantum;
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
    if (strcmp(verb, "query") == 0 && !json) { usage(); return 2; }

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
        if (strcmp(verb, "check") == 0)
            printf("%s %s\n", err.code, err.message);
        else
            fprintf(stderr, "%s %s\n", err.code, err.message);
        return 1;
    }
    if (strcmp(verb, "check") == 0) {
        puts("ok");
        pqdb_close(db);
        return 0;
    }
    memset(&q, 0, sizeof q);
    q.sha256 = sha; q.format = format; q.uri = uri; q.offer = offer; q.host_class = cls;
    q.rate = rate; q.quantum = quantum;
    q.pkg_format = pk[0]; q.pkg_name = pk[1]; q.pkg_version = pk[2]; q.pkg_release = pk[3]; q.pkg_distro = pk[4]; q.pkg_arch = pk[5];
    {
        printer p = { db, 0 };
        int rc = pqdb_each(db, &q, print_result, &p);
        pqdb_close(db);
        if (rc == 0 && p.bad) rc = -2;
        if (rc != 0) {
            fprintf(stderr, "%s\n", pqdb_code(rc) ? pqdb_code(rc) : "qualification-db.unreadable");
            return 1;
        }
    }
    return 0;
}
