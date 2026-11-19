/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com> */
/* The reader's tests (this repository's qualification store spec, section 8, change 3). The numbers are the spec's;
 * 17 and 18 are the adapter code's parts and the verdict lookup. 11's symbol check and 14, the command, are in
 * test_nm.sh and test_command.sh.
 *   test_reader <fixture dir> <contract fixtures dir>           every test but the scopes
 *   test_reader <fixture dir> <contract fixtures dir> scopes    11 (no environment) and 15, under test/shim.so */
#define _GNU_SOURCE
#include <plugin-qualification-db/pqdb.h>

#include <dirent.h>
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static const char *FX, *CT;
static int checks, failures;

#define CHECK(cond, ...) do { checks++; if (!(cond)) { failures++; \
    printf("  FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); printf("       " __VA_ARGS__); printf("\n"); } } while (0)

static char *fx(const char *name)
{
    static char b[8][1024];
    static int n;
    char *p = b[n++ & 7];
    snprintf(p, 1024, "%s/%s", FX, name);
    return p;
}
static char *contract(const char *name)
{
    static char b[4][1024];
    static int n;
    char *p = b[n++ & 3];
    snprintf(p, 1024, "%s/%s", CT, name);
    return p;
}
#define GOOD contract("contract-good")

static const char *sha_of(char c)
{
    static char b[4][65];
    static int n;
    char *p = b[n++ & 3];
    memset(p, c, 64);
    p[64] = 0;
    return p;
}
#define SHA(c) sha_of(c)

static char *slurp(const char *path, size_t *len)
{
    FILE *f = fopen(path, "rb");
    char *b;
    long n;
    if (!f) { *len = 0; return NULL; }
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    b = malloc((size_t)n + 1);
    *len = fread(b, 1, (size_t)n, f);
    fclose(f);
    return b;
}
static void copy(const char *from, const char *to)
{
    size_t n;
    char *b = slurp(from, &n);
    FILE *f = fopen(to, "wb");
    if (b && f) fwrite(b, 1, n, f);
    if (f) fclose(f);
    free(b);
}
static int same_file(const char *a, const char *b)
{
    size_t na, nb;
    char *x = slurp(a, &na), *y = slurp(b, &nb);
    int eq = x && y && na == nb && memcmp(x, y, na) == 0;
    free(x); free(y);
    return eq;
}
static char tmp_made[64][256];
static int tmp_n;
static char *tmpdir(void)
{
    const char *base = getenv("TMPDIR");
    char *p = tmp_made[tmp_n++];
    snprintf(p, 256, "%s/pqdb-test-XXXXXX", base && *base ? base : "/tmp");
    if (!mkdtemp(p)) { perror("mkdtemp"); exit(2); }
    return p;
}
static void tmp_clean(void)
{
    char cmd[300];
    for (int i = 0; i < tmp_n; i++) {
        snprintf(cmd, sizeof cmd, "rm -rf '%s'", tmp_made[i]);
        if (system(cmd)) perror("rm");
    }
}
static char *under(const char *dir, const char *name)
{
    static char b[8][512];
    static int n;
    char *p = b[n++ & 7];
    snprintf(p, 512, "%s/%s", dir, name);
    return p;
}
static void mkdirs(const char *path)
{
    char cmd[1200];
    snprintf(cmd, sizeof cmd, "mkdir -p '%s'", path);
    if (system(cmd)) exit(2);
}

/* the rows a walk gives */
typedef struct {
    char layer[8], sha[65], format[8], uri[64], offer[16], cls[16], set[64], outcome[32];
    char pkg[6][32];
    int rate, quantum, cost_p, has_cost, has_latency, has_memory;
    double median, p_ns;
    long latency, mem_first, mem_per;
} row;
typedef struct { row r[64]; int n; } rows;

static void cp(char *d, size_t n, const char *s) { if (s) snprintf(d, n, "%s", s); else d[0] = 0; }
static int collect(const pqdb_result *x, void *ctx)
{
    rows *o = ctx;
    row *r = &o->r[o->n++];
    const char *const *pk[6] = { &x->pkg_format, &x->pkg_name, &x->pkg_version, &x->pkg_release, &x->pkg_distro, &x->pkg_arch };
    cp(r->layer, 8, x->layer); cp(r->sha, 65, x->sha256); cp(r->format, 8, x->format); cp(r->uri, 64, x->uri);
    cp(r->offer, 16, x->offer); cp(r->cls, 16, x->host_class); cp(r->set, 64, x->set); cp(r->outcome, 32, x->outcome);
    for (int i = 0; i < 6; i++) { if (*pk[i]) cp(r->pkg[i], 32, *pk[i]); else strcpy(r->pkg[i], "(null)"); }
    r->rate = x->rate; r->quantum = x->quantum; r->cost_p = x->cost_p; r->has_cost = x->has_cost;
    r->has_latency = x->has_latency; r->has_memory = x->has_memory; r->median = x->cost_median_ns; r->p_ns = x->cost_p_ns;
    r->latency = x->latency_frames; r->mem_first = x->mem_first_kb; r->mem_per = x->mem_per_instance_kb;
    return 0;
}
static pqdb_query any(void)
{
    pqdb_query q = PQDB_QUERY_ANY;
    return q;
}
static int walk(pqdb *db, const pqdb_query *q, rows *o)
{
    o->n = 0;
    return pqdb_each(db, q, collect, o);
}
static int open_ok(const char *base, const char *user, const char *cdir, pqdb **db)
{
    pqdb_error e;
    int rc = pqdb_open_at(base, user, cdir, db, &e);
    if (rc) printf("  open_at(%s) refused %s: %s\n", base, e.code, e.message);
    return rc;
}
static int expect_refusal(const char *base, const char *user, const char *cdir, const char *code, pqdb_error *e)
{
    pqdb *db = (pqdb *)1;
    int rc;
    memset(e, 0, sizeof *e);
    rc = pqdb_open_at(base, user, cdir, &db, e);
    CHECK(rc != 0, "open succeeded, wanted %s", code);
    CHECK(e->code && strcmp(e->code, code) == 0, "code %s, wanted %s (%s)", e->code ? e->code : "(null)", code, e->message);
    if (strncmp(code, "qualification-db.", 17) == 0)
        CHECK(pqdb_code(rc) && strcmp(pqdb_code(rc), code) == 0, "pqdb_code(%d) is not %s", rc, code);
    if (rc) { CHECK(db == NULL, "out not cleared"); }
    else pqdb_close(db);
    return rc;
}

/* the reference rows of make-fixtures.py */
static int matches_expect(const rows *o, const char *file)
{
    FILE *f = fopen(file, "r");
    char line[1024];
    int i = 0, ok = 1;
    if (!f) { printf("  no %s\n", file); return 0; }
    while (fgets(line, sizeof line, f)) {
        char sha[80], fmt[16], uri[64], offer[16], cls[16], layer[8], set[64], out[32];
        int rate, quantum, p, hc, hl, hm;
        double med, pn;
        long lat, mf, mp;
        const row *r = &o->r[i];
        if (sscanf(line, "%79s %15s %63s %15s %15s %d %d %7s %63s %31s %lf %lf %d %d %ld %d %ld %ld %d",
                   sha, fmt, uri, offer, cls, &rate, &quantum, layer, set, out, &med, &pn, &p, &hc, &lat, &hl, &mf, &mp, &hm) != 19)
            { printf("  bad expect line %s", line); ok = 0; break; }
        if (i >= o->n) { printf("  fewer rows than expected at %d\n", i); ok = 0; break; }
        if (strcmp(r->sha, sha) || strcmp(r->format, fmt) || strcmp(r->uri, uri) || strcmp(r->offer, offer) ||
            strcmp(r->cls, cls) || r->rate != rate || r->quantum != quantum || strcmp(r->layer, layer) ||
            strcmp(r->set, strcmp(set, "-") ? set : "") || strcmp(r->outcome, out) || r->median != med || r->p_ns != pn ||
            r->cost_p != p || r->has_cost != hc || r->latency != lat || r->has_latency != hl || r->mem_first != mf ||
            r->mem_per != mp || r->has_memory != hm) {
            printf("  row %d differs: got %s %s %s %d/%d %s median %g p_ns %g p %d has_cost %d lat %ld/%d mem %ld,%ld/%d; want line %s",
                   i, r->layer, r->offer, r->cls, r->rate, r->quantum, r->uri, r->median, r->p_ns, r->cost_p, r->has_cost,
                   r->latency, r->has_latency, r->mem_first, r->mem_per, r->has_memory, line);
            ok = 0;
        }
        i++;
    }
    fclose(f);
    if (i != o->n) { printf("  %d rows, expected %d\n", o->n, i); ok = 0; }
    return ok;
}

static void t01_absent_base(void)
{
    pqdb_error e;
    expect_refusal(fx("missing.sqlite"), NULL, GOOD, "qualification-db.absent", &e);
    CHECK(strstr(e.message, "missing.sqlite") != NULL, "message does not name the file: %s", e.message);
}
static void t02_absent_user(void)
{
    pqdb *db;
    rows o;
    pqdb_query q = any();
    if (open_ok(fx("base.sqlite"), fx("no-such-user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    CHECK(walk(db, &q, &o) == 0, "walk");
    CHECK(matches_expect(&o, fx("expect-base.tsv")), "results are not the base's");
    pqdb_close(db);
    CHECK(access(fx("no-such-user.sqlite"), F_OK) != 0, "the absent user layer was created");
}
static void t03_versions(void)
{
    pqdb_error e;
    expect_refusal(fx("base-v2.sqlite"), NULL, GOOD, "qualification-db.schema-other", &e);
    CHECK(strstr(e.message, "base-v2.sqlite") && strstr(e.message, "2") && strstr(e.message, "1"), "%s", e.message);
    expect_refusal(fx("base.sqlite"), fx("user-v2.sqlite"), GOOD, "qualification-db.schema-mismatch", &e);
    CHECK(strstr(e.message, "base.sqlite") && strstr(e.message, "user-v2.sqlite"), "%s", e.message);
    expect_refusal(fx("base-v2.sqlite"), fx("user.sqlite"), GOOD, "qualification-db.schema-mismatch", &e);  /* checked first */
    expect_refusal(fx("base-v0.sqlite"), NULL, GOOD, "qualification-db.not-a-store", &e);
    CHECK(strstr(e.message, "base-v0.sqlite") != NULL, "%s", e.message);
    expect_refusal(fx("user.sqlite"), NULL, GOOD, "qualification-db.not-a-store", &e);
}
static void t04_word_unknown(void)
{
    pqdb_error e;
    expect_refusal(fx("base.sqlite"), NULL, contract("contract-no-conditional"), "qualification-db.word-unknown", &e);
    CHECK(strstr(e.message, "verdict.rating") && strstr(e.message, "conditional"), "%s", e.message);
}
static void t05_domain_too_old(void)
{
    pqdb_error e;
    expect_refusal(fx("base.sqlite"), NULL, contract("contract-old"), "qualification-db.domain-too-old", &e);
    CHECK(strstr(e.message, "qualification") != NULL, "%s", e.message);
    expect_refusal(fx("base.sqlite"), NULL, contract("no-such-contract-dir"), "contract.dir.absent", &e);
}
static void t06_whole_record_merge(void)
{
    pqdb *db;
    rows o;
    pqdb_query q = any();
    q.sha256 = SHA('a'); q.offer = "default"; q.host_class = "x86-64";
    q.rate = 48000; q.quantum = 256;
    if (open_ok(fx("base.sqlite"), fx("user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    CHECK(walk(db, &q, &o) == 0 && o.n == 1, "%d results", o.n);
    CHECK(o.n == 1 && strcmp(o.r[0].layer, "user") == 0, "layer %s", o.n ? o.r[0].layer : "-");
    CHECK(o.n == 1 && o.r[0].has_memory == 0, "memory taken from the base");
    pqdb_close(db);
}
static void t07_shadows_whole(void)
{
    pqdb *db;
    rows o;
    pqdb_query q = any();
    q.sha256 = SHA('a'); q.format = "clap"; q.uri = "urn:p1";
    q.offer = "default"; q.host_class = "x86-64";
    char *tmp = tmpdir();
    copy(fx("base.sqlite"), under(tmp, "base.sqlite"));
    if (open_ok(under(tmp, "base.sqlite"), fx("user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    CHECK(walk(db, &q, &o) == 0 && o.n == 1, "%d results", o.n);
    CHECK(o.n == 1 && o.r[0].rate == 48000 && o.r[0].quantum == 256 && strcmp(o.r[0].layer, "user") == 0, "wrong result");
    q.rate = 96000; q.quantum = 256;
    CHECK(walk(db, &q, &o) == 0 && o.n == 0, "the base's 96000/256 shows through: %d", o.n);
    pqdb_close(db);
    CHECK(same_file(fx("base.sqlite"), under(tmp, "base.sqlite")), "the base changed");
}
static void t08_other_key_not_shadowed(void)
{
    pqdb *db;
    rows o;
    pqdb_query q = any();
    if (open_ok(fx("base.sqlite"), fx("user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    q.sha256 = SHA('c'); q.offer = "default"; q.host_class = "x86-64";
    CHECK(walk(db, &q, &o) == 0 && o.n == 1 && strcmp(o.r[0].layer, "base") == 0, "other offer or class shadowed: %d", o.n);
    q = any();
    q.sha256 = SHA('a'); q.offer = "custom";
    CHECK(walk(db, &q, &o) == 0 && o.n == 1 && strcmp(o.r[0].layer, "base") == 0, "offer in the key: %d", o.n);
    q.offer = "default"; q.host_class = "rpi5";
    CHECK(walk(db, &q, &o) == 0 && o.n == 1 && strcmp(o.r[0].layer, "base") == 0, "class in the key: %d", o.n);
    q = any();
    q.sha256 = SHA('b');
    CHECK(walk(db, &q, &o) == 0 && o.n == 1 && strcmp(o.r[0].layer, "user") == 0, "user record of other bytes");
    q = any();
    q.uri = "urn:p1"; q.offer = "default"; q.host_class = "x86-64";
    CHECK(walk(db, &q, &o) == 0 && o.n == 2, "the user's other bytes shadow the base: %d", o.n);
    pqdb_close(db);
}
static void t09_package_lookup(void)
{
    pqdb *db;
    rows o;
    pqdb_query q = any();
    if (open_ok(fx("base.sqlite"), fx("user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    q.pkg_format = "rpm"; q.pkg_name = "clap-dexed"; q.pkg_version = "1.1.0"; q.pkg_release = "4.fc44";
    q.pkg_distro = "fc44"; q.pkg_arch = "x86_64";
    CHECK(walk(db, &q, &o) == 0 && o.n == 1 && strcmp(o.r[0].layer, "user") == 0, "package not found: %d", o.n);
    CHECK(o.n == 1 && strcmp(o.r[0].pkg[1], "clap-dexed") == 0 && strcmp(o.r[0].pkg[3], "4.fc44") == 0, "package fields");
    q = any();
    q.pkg_arch = "x86_64";
    CHECK(walk(db, &q, &o) == 0 && o.n == 1, "NULL package fields matched a package query: %d", o.n);
    q = any();
    q.pkg_format = "deb";
    CHECK(walk(db, &q, &o) == 0 && o.n == 0, "deb: %d", o.n);
    q = any();
    CHECK(walk(db, &q, &o) == 0 && o.n > 0, "walk");
    for (int i = 0; i < o.n; i++)
        if (strcmp(o.r[i].layer, "base") == 0) CHECK(strcmp(o.r[i].pkg[0], "(null)") == 0, "base package not NULL");
    pqdb_close(db);
}

typedef struct { char name[256]; long size; long long mtime; } ent;
static int snapshot(const char *dir, ent *e)
{
    DIR *d = opendir(dir);
    struct dirent *de;
    int n = 0;
    while (d && (de = readdir(d))) {
        struct stat st;
        char p[600];
        snprintf(p, sizeof p, "%s/%s", dir, de->d_name);
        stat(p, &st);
        snprintf(e[n].name, 256, "%s", de->d_name);
        e[n].size = st.st_size;
        e[n].mtime = st.st_mtim.tv_sec * 1000000000LL + st.st_mtim.tv_nsec;
        n++;
    }
    if (d) closedir(d);
    return n;
}
static int by_name(const void *a, const void *b) { return strcmp(((const ent *)a)->name, ((const ent *)b)->name); }
static void t10_read_only(void)
{
    char *t = tmpdir();
    ent a[32], b[32];
    int na, nb;
    pqdb *db;
    rows o;
    pqdb_query q = any();
    pqdb_verdict v;
    copy(fx("base.sqlite"), under(t, "base.sqlite"));
    copy(fx("user.sqlite"), under(t, "user.sqlite"));
    na = snapshot(t, a); qsort(a, (size_t)na, sizeof *a, by_name);
    if (open_ok(under(t, "base.sqlite"), under(t, "user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    CHECK(walk(db, &q, &o) == 0 && o.n > 0, "walk");
    {
        pqdb_result r;
        memset(&r, 0, sizeof r);
        r.layer = o.r[0].layer; r.sha256 = o.r[0].sha; r.format = o.r[0].format; r.uri = o.r[0].uri;
        r.offer = o.r[0].offer; r.host_class = o.r[0].cls; r.rate = o.r[0].rate; r.quantum = o.r[0].quantum;
        pqdb_verdict_of(db, &r, "omx-clap-host", &v);
    }
    pqdb_close(db);
    nb = snapshot(t, b); qsort(b, (size_t)nb, sizeof *b, by_name);
    CHECK(na == nb, "directory listing changed: %d -> %d entries", na, nb);
    for (int i = 0; i < na && i < nb; i++)
        CHECK(strcmp(a[i].name, b[i].name) == 0 && a[i].size == b[i].size && a[i].mtime == b[i].mtime, "%s changed", a[i].name);
}
static void t12_busy(void)
{
    char *t = tmpdir();
    sqlite3 *w;
    pqdb_error e;
    pqdb *db = NULL;
    struct timespec t0, t1;
    long ms;
    copy(fx("user.sqlite"), under(t, "user.sqlite"));
    CHECK(sqlite3_open(under(t, "user.sqlite"), &w) == SQLITE_OK, "writer open");
    CHECK(sqlite3_exec(w, "BEGIN EXCLUSIVE", NULL, NULL, NULL) == SQLITE_OK, "writer lock");
    clock_gettime(CLOCK_MONOTONIC, &t0);
    int rc = pqdb_open_at(fx("base.sqlite"), under(t, "user.sqlite"), GOOD, &db, &e);
    clock_gettime(CLOCK_MONOTONIC, &t1);
    ms = (t1.tv_sec - t0.tv_sec) * 1000 + (t1.tv_nsec - t0.tv_nsec) / 1000000;
    CHECK(rc != 0 && e.code && strcmp(e.code, "qualification-db.busy") == 0, "code %s (%s)", e.code ? e.code : "-", e.message);
    CHECK(ms < 1500, "open took %ld ms", ms);
    CHECK(strstr(e.message, "user.sqlite") != NULL, "%s", e.message);
    if (!rc) pqdb_close(db);
    sqlite3_exec(w, "ROLLBACK", NULL, NULL, NULL);
    sqlite3_close(w);
}
static void t13_figures(void)
{
    pqdb *db;
    rows o;
    pqdb_query q = any();
    if (open_ok(fx("base.sqlite"), NULL, GOOD, &db)) { CHECK(0, "open"); return; }
    CHECK(walk(db, &q, &o) == 0, "walk");
    CHECK(matches_expect(&o, fx("expect-base.tsv")), "base figures");
    pqdb_close(db);
    if (open_ok(fx("base.sqlite"), fx("user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    CHECK(walk(db, &q, &o) == 0, "walk");
    CHECK(matches_expect(&o, fx("expect-merged.tsv")), "merged figures");
    pqdb_close(db);
}
static void t16_hot_journal(void)
{
    char *t = tmpdir();
    pqdb_error e;
    char j1[1100], j2[1100];
    copy(fx("user-hot.sqlite"), under(t, "user.sqlite"));
    snprintf(j1, sizeof j1, "%s-journal", fx("user-hot.sqlite"));
    snprintf(j2, sizeof j2, "%s-journal", under(t, "user.sqlite"));
    copy(j1, j2);
    expect_refusal(fx("base.sqlite"), under(t, "user.sqlite"), GOOD, "qualification-db.hot-journal", &e);
    CHECK(strstr(e.message, "user.sqlite") && strstr(e.message, "journal"), "%s", e.message);
    CHECK(same_file(fx("user-hot.sqlite"), under(t, "user.sqlite")), "the layer changed");
    CHECK(same_file(j1, j2), "the journal changed or is gone");
}
static void t19_query_any(void)
{
    pqdb *db;
    rows o;
    pqdb_query q = PQDB_QUERY_ANY, zero;
    memset(&zero, 0, sizeof zero);
    if (open_ok(fx("base.sqlite"), fx("user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    CHECK(walk(db, &q, &o) == 0, "walk");
    CHECK(matches_expect(&o, fx("expect-merged.tsv")), "PQDB_QUERY_ANY does not give every row");
    /* 0 keeps its meaning: a zeroed query asks for rate 0 and quantum 0, which no cell has */
    CHECK(walk(db, &zero, &o) == 0 && o.n == 0, "a zeroed query matched %d rows", o.n);
    pqdb_close(db);
}
static void t17_adapter_code(void)
{
    pqdb_error e;
    pqdb *db;
    expect_refusal(fx("base-bad-adapter-code.sqlite"), NULL, GOOD, "qualification-db.word-unknown", &e);
    CHECK(strstr(e.message, "record.adapter_code") && strstr(e.message, "omx-clap-host.signal-SIGBUS"), "%s", e.message);
    CHECK(open_ok(fx("base.sqlite"), NULL, GOOD, &db) == 0, "a code that splits into words of the domains is refused");
    if (db) pqdb_close(db);
}
static void t18_verdict(void)
{
    pqdb *db;
    rows o;
    pqdb_query q = any();
    pqdb_result r;
    pqdb_verdict v;
    if (open_ok(fx("base.sqlite"), NULL, GOOD, &db)) { CHECK(0, "open"); return; }
    q.offer = "default"; q.host_class = "x86-64"; q.rate = 48000; q.uri = "urn:p1";
    CHECK(walk(db, &q, &o) == 0 && o.n == 1, "walk");
    memset(&r, 0, sizeof r);
    r.layer = o.r[0].layer; r.sha256 = o.r[0].sha; r.format = o.r[0].format; r.uri = o.r[0].uri; r.offer = o.r[0].offer;
    r.host_class = o.r[0].cls; r.rate = o.r[0].rate; r.quantum = o.r[0].quantum;
    CHECK(pqdb_verdict_of(db, &r, "omx-clap-host", &v) == 0, "verdict");
    CHECK(strcmp(v.rating, "conditional") == 0 && v.measured == 1 && v.qualified == 1 && v.deciding == NULL, "verdict fields");
    CHECK(pqdb_verdict_of(db, &r, "openmixer-console", &v) == 0 && strcmp(v.deciding, "probe.crashed") == 0, "deciding");
    CHECK(pqdb_verdict_of(db, &r, "no-such-host", &v) != 0, "unknown host");
    pqdb_close(db);
}

/* ---- under test/shim.so ---- */
static int has_sha(const rows *o, const char *c)
{
    for (int i = 0; i < o->n; i++) if (o->r[i].sha[0] == c[0]) return 1;
    return 0;
}
static int trace_has(const char *file, const char *needle)
{
    size_t n;
    char *b = slurp(file, &n);
    int r = b && strstr(b, needle) != NULL;
    free(b);
    return r;
}
static void setup_root(const char *root, const char *compiled)
{
    char map[3000];
    mkdirs(under(root, "usr/share/omx/qualification")); mkdirs(under(root, "var/lib/omx/qualification"));
    mkdirs(under(root, "home/u/.local/share/omx/qualification")); mkdirs(under(root, "xdg/omx/qualification"));
    copy(fx("base.sqlite"), under(root, "usr/share/omx/qualification/qualification.sqlite"));
    copy(fx("scope-system.sqlite"), under(root, "var/lib/omx/qualification/qualification.sqlite"));
    copy(fx("scope-home.sqlite"), under(root, "home/u/.local/share/omx/qualification/qualification.sqlite"));
    copy(fx("scope-xdg.sqlite"), under(root, "xdg/omx/qualification/qualification.sqlite"));
    snprintf(map, sizeof map, "/usr/share/omx/qualification=%s:/var/lib/omx/qualification=%s:%s=%s",
             under(root, "usr/share/omx/qualification"), under(root, "var/lib/omx/qualification"), compiled, GOOD);
    setenv("PQDB_SHIM_MAP", map, 1);
    setenv("PQDB_SHIM_HOME", under(root, "home/u"), 1);
    setenv("XDG_DATA_HOME", under(root, "xdg"), 1);
    setenv("HOME", under(root, "xdg"), 1);
}
static void t11_no_environment(void)
{
    char *root = tmpdir();
    const char *compiled = getenv("PQDB_TEST_CONTRACTDIR");
    pqdb *db = NULL;
    pqdb_error e;
    char map[2000];
    /* the installed base is not there: an environment variable naming a fixture must not stand in for it */
    mkdirs(under(root, "empty"));
    snprintf(map, sizeof map, "/usr/share/omx/qualification=%s:%s=%s", under(root, "empty"), compiled, GOOD);
    setenv("PQDB_SHIM_MAP", map, 1);
    setenv("PQDB_SHIM_HOME", under(root, "empty"), 1);
    setenv("PLUGIN_QUALIFICATION_DB_BASE", fx("base.sqlite"), 1);
    setenv("PLUGIN_QUALIFICATION_DB_USER", fx("user.sqlite"), 1);
    setenv("OMX_CONTRACT_PATH", CT, 1);
    int rc = pqdb_open(PQDB_SCOPE_USER, &db, &e);
    CHECK(rc != 0 && strcmp(e.code, "qualification-db.absent") == 0, "open with a variable set: %s", rc ? e.code : "succeeded");
    CHECK(strstr(e.message, "/usr/share/omx/qualification/qualification.sqlite") != NULL, "%s", e.message);
    if (!rc) pqdb_close(db);
    unsetenv("PLUGIN_QUALIFICATION_DB_BASE"); unsetenv("PLUGIN_QUALIFICATION_DB_USER"); unsetenv("OMX_CONTRACT_PATH");
}
static void t15_scopes(void)
{
    char *root = tmpdir();
    const char *compiled = getenv("PQDB_TEST_CONTRACTDIR");
    char trace[512];
    pqdb *db;
    pqdb_error e;
    rows o;
    pqdb_query q = any();
    setup_root(root, compiled);
    snprintf(trace, sizeof trace, "%s/trace.txt", root);
    setenv("PQDB_SHIM_TRACE", trace, 1);
    CHECK(pqdb_open(PQDB_SCOPE_USER, &db, &e) == 0, "%s: %s", e.code, e.message);
    CHECK(walk(db, &q, &o) == 0, "walk");
    CHECK(has_sha(&o, "2"), "the home's layer is not read");
    CHECK(!has_sha(&o, "3"), "XDG_DATA_HOME's layer was read");
    CHECK(!has_sha(&o, "1"), "the system layer was read by the user scope");
    CHECK(has_sha(&o, "a"), "the base is not read");
    pqdb_close(db);
    CHECK(!trace_has(trace, "/var/lib/omx/qualification"), "the user scope touched the system layer");
    CHECK(trace_has(trace, "/.local/share/omx/qualification/qualification.sqlite"), "the home layer was not opened");
    unlink(trace);
    CHECK(pqdb_open(PQDB_SCOPE_SYSTEM, &db, &e) == 0, "%s: %s", e.code, e.message);
    CHECK(walk(db, &q, &o) == 0, "walk");
    CHECK(has_sha(&o, "1") && !has_sha(&o, "2") && !has_sha(&o, "3") && has_sha(&o, "a"), "system scope results");
    pqdb_close(db);
    CHECK(!trace_has(trace, "/.local/share"), "the system scope touched the home");
    CHECK(!trace_has(trace, "/xdg/"), "the system scope touched XDG_DATA_HOME");
}

typedef struct { const char *name; void (*fn)(void); int scoped; } test;
static const test TESTS[] = {
    { "01 absent base", t01_absent_base, 0 }, { "02 absent user layer", t02_absent_user, 0 },
    { "03 one schema version", t03_versions, 0 }, { "04 word not in the domain", t04_word_unknown, 0 },
    { "05 domain too old", t05_domain_too_old, 0 }, { "06 whole-record merge", t06_whole_record_merge, 0 },
    { "07 a user record shadows the whole base record", t07_shadows_whole, 0 },
    { "08 another key is not shadowed", t08_other_key_not_shadowed, 0 }, { "09 package lookup", t09_package_lookup, 0 },
    { "10 read only", t10_read_only, 0 }, { "12 busy", t12_busy, 0 }, { "13 figures agree with qualcost", t13_figures, 0 },
    { "16 hot journal", t16_hot_journal, 0 }, { "17 adapter code in parts", t17_adapter_code, 0 },
    { "18 verdict of a result", t18_verdict, 0 }, { "19 PQDB_QUERY_ANY", t19_query_any, 0 },
    { "11 no environment in production", t11_no_environment, 1 }, { "15 scopes", t15_scopes, 1 },
};

int main(int argc, char **argv)
{
    int scoped = argc > 3 && strcmp(argv[3], "scopes") == 0, ran = 0, bad = 0;
    if (argc < 3) { fprintf(stderr, "usage: test_reader <fixture dir> <contract fixtures dir> [scopes]\n"); return 2; }
    FX = argv[1]; CT = argv[2];
    for (size_t i = 0; i < sizeof TESTS / sizeof *TESTS; i++) {
        int before = failures;
        if (TESTS[i].scoped != scoped) continue;
        TESTS[i].fn();
        printf("%s %s\n", failures == before ? "ok    " : "not ok", TESTS[i].name);
        ran++; bad += failures != before;
    }
    tmp_clean();
    printf("%d tests, %d failed, %d checks\n", ran, bad, checks);
    return bad ? 1 : 0;
}
