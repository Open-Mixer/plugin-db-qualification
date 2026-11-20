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
#include <locale.h>
#include <math.h>
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static const char *FX, *CT;
static const char *skip_reason;
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
    char bpath[64], layout_scheme[32], layout_sha[65], tested[32];
    int unpinnable;
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
    cp(r->bpath, 64, x->binary_path);
    if (x->layout_scheme) cp(r->layout_scheme, 32, x->layout_scheme); else strcpy(r->layout_scheme, "(null)");
    if (x->layout_sha256) cp(r->layout_sha, 65, x->layout_sha256); else strcpy(r->layout_sha, "(null)");
    if (x->tested_version) cp(r->tested, 32, x->tested_version); else strcpy(r->tested, "(null)");
    r->unpinnable = x->unpinnable;
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

static int count_formats(const char *format, long plugins, long offered, long not_offered, void *ctx)
{
    (void)format; (void)plugins; (void)offered; (void)not_offered;
    ++*(int *)ctx;
    return 0;
}
static void write_file(const char *path, const char *bytes, size_t n)
{
    FILE *f = fopen(path, "wb");
    if (!f) { perror(path); exit(2); }
    if (n) fwrite(bytes, 1, n, f);
    fclose(f);
}

/* ruling 2026-11-20: an absent base is a valid empty base layer; the answer says so, the user layer answers alone */
static void t01_absent_base(void)
{
    pqdb *db;
    rows o;
    pqdb_query q = any();
    int n = 0;
    if (open_ok(fx("missing.sqlite"), fx("user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    CHECK(pqdb_base_absent(db) == 1, "the handle does not say the base is absent");
    CHECK(walk(db, &q, &o) == 0 && o.n > 0, "walk");
    CHECK(matches_expect(&o, fx("expect-user.tsv")), "results are not the user layer's alone");
    q.layer = "base";
    CHECK(walk(db, &q, &o) == 0 && o.n == 0, "the absent base gave %d rows", o.n);
    CHECK(pqdb_counts(db, "base", count_formats, &n) == 0 && n == 0, "counts of the absent base: %d formats", n);
    pqdb_close(db);
    CHECK(access(fx("missing.sqlite"), F_OK) != 0, "the absent base was created");
    if (open_ok(fx("missing.sqlite"), NULL, GOOD, &db)) { CHECK(0, "open with no user layer"); return; }
    CHECK(pqdb_base_absent(db) == 1, "no user layer: base not said absent");
    q = any();
    CHECK(walk(db, &q, &o) == 0 && o.n == 0, "no layer at all gave %d rows", o.n);
    pqdb_close(db);
    if (open_ok(fx("base.sqlite"), fx("user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    CHECK(pqdb_base_absent(db) == 0, "a present base is said absent");
    pqdb_close(db);
}
/* a base path that exists but cannot be used is still refused by name, one arm each */
static void t01_base_is_a_directory(void)
{
    pqdb_error e;
    char *root = tmpdir();
    mkdirs(under(root, "base.sqlite"));
    expect_refusal(under(root, "base.sqlite"), NULL, GOOD, "qualification-db.unreadable", &e);
    CHECK(strstr(e.message, "base.sqlite") != NULL, "%s", e.message);
}
static void t01_base_is_junk(void)
{
    pqdb_error e;
    char *root = tmpdir();
    write_file(under(root, "short.sqlite"), "not sqlite", 10);
    expect_refusal(under(root, "short.sqlite"), NULL, GOOD, "qualification-db.unreadable", &e);
    CHECK(strstr(e.message, "short.sqlite") != NULL, "%s", e.message);
    write_file(under(root, "empty.sqlite"), "", 0);
    expect_refusal(under(root, "empty.sqlite"), NULL, GOOD, "qualification-db.not-a-store", &e);
}
static void t01_base_wrong_version(void)
{
    pqdb_error e;
    expect_refusal(fx("base-v2.sqlite"), fx("user.sqlite"), GOOD, "qualification-db.schema-mismatch", &e);
    expect_refusal(fx("base-v2.sqlite"), NULL, GOOD, "qualification-db.schema-other", &e);
    CHECK(strstr(e.message, "base-v2.sqlite") != NULL, "%s", e.message);
}
static void t01_base_not_readable(void)
{
    pqdb_error e;
    char *root = tmpdir();
    if (geteuid() == 0) { skip_reason = "running as root: a mode 000 file is readable"; return; }
    copy(fx("base.sqlite"), under(root, "denied.sqlite"));
    CHECK(chmod(under(root, "denied.sqlite"), 0) == 0, "chmod");
    expect_refusal(under(root, "denied.sqlite"), NULL, GOOD, "qualification-db.unreadable", &e);
    CHECK(strstr(e.message, "denied.sqlite") != NULL, "%s", e.message);
}
/* only ENOENT is absent: a path through a file (ENOTDIR) is a wrong path, refused */
static void t01_base_under_a_file(void)
{
    pqdb_error e;
    char *root = tmpdir();
    write_file(under(root, "afile"), "x", 1);
    expect_refusal(under(root, "afile/qualification.sqlite"), NULL, GOOD, "qualification-db.unreadable", &e);
    CHECK(strstr(e.message, "afile") != NULL, "%s", e.message);
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
        if (strcmp(de->d_name, "..") == 0)      /* the parent is the shared temporary directory: not this store's */
            continue;
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

/* The read-only checks (10, spec 24) compare a snapshot of the directory a store sits in. The listing of a directory is
 * not changed by a neighbour: another process making or removing a file beside it, in the shared temporary directory,
 * must not fail them. */
static void snapshot_neighbours(void)
{
    char *t = tmpdir(), *other;
    ent a[32], b[32];
    int na, nb, same = 1;
    copy(fx("base.sqlite"), under(t, "base.sqlite"));
    na = snapshot(t, a); qsort(a, (size_t)na, sizeof *a, by_name);
    other = tmpdir();                       /* a neighbour: it changes the modification time of the temporary directory */
    (void)other;
    nb = snapshot(t, b); qsort(b, (size_t)nb, sizeof *b, by_name);
    CHECK(na == nb, "directory listing changed: %d -> %d entries", na, nb);
    for (int i = 0; i < na && i < nb; i++)
        if (strcmp(a[i].name, b[i].name) != 0 || a[i].size != b[i].size || a[i].mtime != b[i].mtime) {
            same = 0;
            printf("       %s changed with only a neighbour beside it\n", a[i].name);
        }
    CHECK(same, "a neighbour in the temporary directory changed the snapshot");
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
static void t20_query_any_fields(void)
{
    pqdb_query q = PQDB_QUERY_ANY;
    const char *s[] = { q.sha256, q.format, q.uri, q.offer, q.host_class, q.pkg_format, q.pkg_name, q.pkg_version,
                        q.pkg_release, q.pkg_distro, q.pkg_arch, q.binary_path, q.layer };
    /* positional, in the field order of section 6: each position lands in its field (a struct's order is its contract) */
    pqdb_query p = { "s", "f", "u", "o", "h", 1, 2, "pf", "pn", "pv", "pr", "pd", "pa", "bp", "ly" };
    CHECK(strcmp(p.sha256, "s") == 0 && strcmp(p.host_class, "h") == 0 && p.rate == 1 && p.quantum == 2 &&
          strcmp(p.pkg_arch, "pa") == 0 && strcmp(p.binary_path, "bp") == 0 && strcmp(p.layer, "ly") == 0,
          "the positional order of pqdb_query is not the spec's");
    for (size_t i = 0; i < sizeof s / sizeof *s; i++)
        CHECK(s[i] == NULL, "string field %zu of PQDB_QUERY_ANY is not NULL", i);
    CHECK(q.rate == -1 && q.quantum == -1, "rate %d quantum %d", q.rate, q.quantum);
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

/* ---- change 3, the cases 17 to 19 of section 8: identity, per-file lists, the filters ---- */
static const char *txt(sqlite3_stmt *st, int i)
{
    return sqlite3_column_type(st, i) == SQLITE_NULL ? "(null)" : (const char *)sqlite3_column_text(st, i);
}
static sqlite3 *raw(const char *path)
{
    sqlite3 *h = NULL;
    if (sqlite3_open_v2(path, &h, SQLITE_OPEN_READONLY, NULL) != SQLITE_OK) { fprintf(stderr, "cannot open %s\n", path); exit(2); }
    return h;
}
static void spec17_identity(void)
{
    pqdb *db;
    rows o;
    pqdb_query q = any();
    sqlite3 *h[2] = { raw(fx("user.sqlite")), raw(fx("base.sqlite")) };
    int seen_layout = 0, seen_unpinnable = 0, seen_tested = 0;
    if (open_ok(fx("base.sqlite"), fx("user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    for (int pass = 0; pass < 2; pass++) {     /* the merged answer, then the base whole: the user layer shadows the one with a layout */
    q.layer = pass ? "base" : NULL;
    CHECK(walk(db, &q, &o) == 0 && o.n > 0, "walk");
    for (int i = 0; i < o.n; i++) {
        const row *r = &o.r[i];
        sqlite3_stmt *st;
        sqlite3 *l = strcmp(r->layer, "user") == 0 ? h[0] : h[1];
        CHECK(sqlite3_prepare_v2(l, "SELECT r.binary_path, r.layout_scheme, r.layout_sha256, r.tested_version, "
              "COALESCE(r.unpinnable, 0) FROM record r JOIN plugin p ON p.plugin_id = r.plugin_id WHERE p.sha256 = ?1 AND "
              "p.format = ?2 AND p.uri = ?3 AND r.offer = ?4 AND r.host_class = ?5", -1, &st, NULL) == SQLITE_OK, "prepare");
        sqlite3_bind_text(st, 1, r->sha, -1, SQLITE_STATIC); sqlite3_bind_text(st, 2, r->format, -1, SQLITE_STATIC);
        sqlite3_bind_text(st, 3, r->uri, -1, SQLITE_STATIC); sqlite3_bind_text(st, 4, r->offer, -1, SQLITE_STATIC);
        sqlite3_bind_text(st, 5, r->cls, -1, SQLITE_STATIC);
        CHECK(sqlite3_step(st) == SQLITE_ROW, "no record for result %d", i);
        CHECK(strcmp(r->bpath, txt(st, 0)) == 0, "binary_path %s, the record's %s", r->bpath, txt(st, 0));
        CHECK(strcmp(r->layout_scheme, txt(st, 1)) == 0, "layout_scheme %s, the record's %s", r->layout_scheme, txt(st, 1));
        CHECK(strcmp(r->layout_sha, txt(st, 2)) == 0, "layout_sha256 %s, the record's %s", r->layout_sha, txt(st, 2));
        CHECK(strcmp(r->tested, txt(st, 3)) == 0, "tested_version %s, the record's %s", r->tested, txt(st, 3));
        CHECK(r->unpinnable == sqlite3_column_int(st, 4), "unpinnable %d, the record's %d", r->unpinnable, sqlite3_column_int(st, 4));
        seen_layout += strcmp(r->layout_scheme, "(null)") != 0; seen_unpinnable += r->unpinnable; seen_tested += strcmp(r->tested, "(null)") != 0;
        if (strcmp(r->layout_scheme, "(null)") == 0) CHECK(strcmp(r->layout_sha, "(null)") == 0, "a record with no layout gives NULL for both");
        sqlite3_finalize(st);
    }
    }
    CHECK(seen_layout > 0 && seen_unpinnable > 0 && seen_tested > 0, "the fixtures hold no layout, no unpinnable record or no tested version to read");
    pqdb_close(db);
    sqlite3_close(h[0]); sqlite3_close(h[1]);
}

typedef struct { char path[8][64], sha[8][65]; int n, stop_at; } flist;
static int collect_file(const char *path, const char *sha, void *ctx)
{
    flist *f = ctx;
    if (f->n < 8) { snprintf(f->path[f->n], 64, "%s", path); snprintf(f->sha[f->n], 65, "%s", sha); }
    f->n++;
    return f->stop_at && f->n == f->stop_at ? 7 : 0;
}
typedef struct { pqdb *db; sqlite3 *h[2]; int results, lists, bad; flist first_of_record; char last_key[200]; } fwalk;
static int check_files(const pqdb_result *x, void *ctx)
{
    fwalk *w = ctx;
    flist f;
    char key[200];
    sqlite3_stmt *st;
    int i = 0;
    memset(&f, 0, sizeof f);
    w->results++;
    if (pqdb_files(w->db, x, collect_file, &f) != 0) { w->bad++; printf("  pqdb_files refused %s %s\n", x->uri, x->offer); return 0; }
    sqlite3_prepare_v2(w->h[strcmp(x->layer, "user") == 0 ? 0 : 1],
        "SELECT f.path, f.sha256 FROM record_file f JOIN record r ON r.record_id = f.record_id JOIN plugin p ON p.plugin_id = r.plugin_id "
        "WHERE p.sha256 = ?1 AND p.format = ?2 AND p.uri = ?3 AND r.offer = ?4 AND r.host_class = ?5 ORDER BY f.ord", -1, &st, NULL);
    sqlite3_bind_text(st, 1, x->sha256, -1, SQLITE_STATIC); sqlite3_bind_text(st, 2, x->format, -1, SQLITE_STATIC);
    sqlite3_bind_text(st, 3, x->uri, -1, SQLITE_STATIC); sqlite3_bind_text(st, 4, x->offer, -1, SQLITE_STATIC);
    sqlite3_bind_text(st, 5, x->host_class, -1, SQLITE_STATIC);
    while (sqlite3_step(st) == SQLITE_ROW) {
        if (i >= f.n || i >= 8 || strcmp(f.path[i], (const char *)sqlite3_column_text(st, 0)) || strcmp(f.sha[i], (const char *)sqlite3_column_text(st, 1))) {
            w->bad++; printf("  list of %s %s differs at %d: got %s\n", x->uri, x->offer, i, i < f.n && i < 8 ? f.path[i] : "(none)");
        }
        i++;
    }
    sqlite3_finalize(st);
    if (i != f.n) { w->bad++; printf("  list of %s %s has %d entries, the record %d\n", x->uri, x->offer, f.n, i); }
    if (i == 0) { w->bad++; printf("  list of %s is empty\n", x->uri); }
    w->lists++;
    /* the cells of one record give one list */
    snprintf(key, sizeof key, "%s/%s/%s/%s/%s", x->layer, x->sha256, x->uri, x->offer, x->host_class);
    if (strcmp(key, w->last_key) == 0) {
        if (f.n != w->first_of_record.n || (f.n > 0 && strcmp(f.path[0], w->first_of_record.path[0]))) { w->bad++; printf("  the cells of %s give other lists\n", key); }
    } else {
        w->first_of_record = f;
        snprintf(w->last_key, sizeof w->last_key, "%s", key);
    }
    return 0;
}
static void spec18_files(void)
{
    pqdb *db;
    pqdb_query q = any();
    fwalk w;
    flist f;
    pqdb_result lv2 = { 0 };
    memset(&w, 0, sizeof w);
    if (open_ok(fx("base.sqlite"), fx("user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    w.db = db; w.h[0] = raw(fx("user.sqlite")); w.h[1] = raw(fx("base.sqlite"));
    CHECK(pqdb_each(db, &q, check_files, &w) == 0, "walk");
    CHECK(w.results > 0 && w.lists == w.results && w.bad == 0, "%d results, %d lists, %d wrong", w.results, w.lists, w.bad);
    /* the LV2 bundle: byte order puts a capital before a lower-case letter, which no case-folding order does */
    q.format = "lv2";
    memset(&f, 0, sizeof f);
    {
        rows o;
        CHECK(walk(db, &q, &o) == 0 && o.n == 1, "the lv2 result");
        if (o.n == 1) {
            lv2.layer = o.r[0].layer; lv2.sha256 = o.r[0].sha; lv2.format = o.r[0].format; lv2.uri = o.r[0].uri;
            lv2.offer = o.r[0].offer; lv2.host_class = o.r[0].cls; lv2.rate = o.r[0].rate; lv2.quantum = o.r[0].quantum;
            CHECK(pqdb_files(db, &lv2, collect_file, &f) == 0 && f.n == 4, "%d entries", f.n);
            CHECK(f.n == 4 && strcmp(f.path[0], "Z-extra.ttl") == 0 && strcmp(f.path[1], "manifest.ttl") == 0 &&
                  strcmp(f.path[2], "p3.so") == 0 && strcmp(f.path[3], "p3.ttl") == 0, "the list is not in the record's order");
            memset(&f, 0, sizeof f); f.stop_at = 2;
            CHECK(pqdb_files(db, &lv2, collect_file, &f) == 7 && f.n == 2, "a non-zero return does not stop the walk and come back: %d", f.n);
        }
    }
    pqdb_close(db);
    sqlite3_close(w.h[0]); sqlite3_close(w.h[1]);
}

static void spec19_filters(void)
{
    pqdb *db;
    rows o;
    pqdb_query q = any();
    if (open_ok(fx("base.sqlite"), fx("user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    q.binary_path = "p1.clap";
    CHECK(walk(db, &q, &o) == 0 && o.n > 0, "p1.clap finds nothing");
    for (int i = 0; i < o.n; i++) CHECK(strcmp(o.r[i].bpath, "p1.clap") == 0, "binary_path %s is not p1.clap", o.r[i].bpath);
    q.binary_path = "Sub/p1.clap";
    CHECK(walk(db, &q, &o) == 0 && o.n == 1 && strcmp(o.r[0].uri, "urn:p4") == 0, "Sub/p1.clap: %d results", o.n);
    q.binary_path = "P1.clap";
    CHECK(walk(db, &q, &o) == 0 && o.n == 1 && strcmp(o.r[0].uri, "urn:p5") == 0, "P1.clap: %d results", o.n);
    q.binary_path = "p1.CLAP";
    CHECK(walk(db, &q, &o) == 0 && o.n == 0, "another case matched: %d", o.n);
    q.binary_path = "1.clap";
    CHECK(walk(db, &q, &o) == 0 && o.n == 0, "a suffix matched: %d", o.n);

    q = any(); q.layer = "user";
    CHECK(walk(db, &q, &o) == 0 && matches_expect(&o, fx("expect-user.tsv")), "layer user is not every user record, unshadowed");
    q = any(); q.layer = "base";
    CHECK(walk(db, &q, &o) == 0 && matches_expect(&o, fx("expect-base.tsv")), "layer base is not the whole base, shadowed or not");
    q = any(); q.layer = "user"; q.uri = "urn:p1"; q.offer = "default"; q.host_class = "x86-64";
    CHECK(walk(db, &q, &o) == 0 && o.n == 2, "the user records that shadow the base: %d", o.n);
    q.layer = "base";
    CHECK(walk(db, &q, &o) == 0 && o.n == 2 && strcmp(o.r[0].layer, "base") == 0, "the base record the user one shadows: %d", o.n);
    q = any(); q.layer = NULL;
    CHECK(walk(db, &q, &o) == 0 && matches_expect(&o, fx("expect-merged.tsv")), "NULL is not the merged answer");
    q.layer = "system";
    CHECK(pqdb_each(db, &q, collect, &o) != 0, "an unknown layer name was accepted");
    pqdb_close(db);
    /* no user layer: layer user is empty, base is the base */
    if (open_ok(fx("base.sqlite"), NULL, GOOD, &db)) { CHECK(0, "open"); return; }
    q = any(); q.layer = "user";
    CHECK(walk(db, &q, &o) == 0 && o.n == 0, "an absent user layer gave %d results", o.n);
    pqdb_close(db);
}

/* ---- change 3, cases 20, 21 and 24 of section 8: counts, whole records, read only ---- */
typedef struct { char fmt[8][8]; long plugins[8], offered[8], not_offered[8]; int n; } tally;
static int collect_count(const char *format, long plugins, long offered, long not_offered, void *ctx)
{
    tally *t = ctx;
    if (t->n < 8) {
        snprintf(t->fmt[t->n], 8, "%s", format);
        t->plugins[t->n] = plugins; t->offered[t->n] = offered; t->not_offered[t->n] = not_offered;
    }
    t->n++;
    return 0;
}
/* the counts the fixtures' own model worked out (make-fixtures.py), one line a format */
static int counts_match(const tally *t, const char *file)
{
    FILE *f = fopen(file, "r");
    char line[128], fmt[16];
    long p, o, n;
    int i = 0, ok = 1;
    if (!f) { printf("  no %s\n", file); return 0; }
    while (fgets(line, sizeof line, f)) {
        if (sscanf(line, "%15s %ld %ld %ld", fmt, &p, &o, &n) != 4) { ok = 0; break; }
        if (i >= t->n || strcmp(t->fmt[i], fmt) || t->plugins[i] != p || t->offered[i] != o || t->not_offered[i] != n) {
            printf("  format %d: got %s %ld %ld %ld (of %d formats); want %s", i, i < t->n ? t->fmt[i] : "-",
                   i < t->n ? t->plugins[i] : -1, i < t->n ? t->offered[i] : -1, i < t->n ? t->not_offered[i] : -1, t->n, line);
            ok = 0;
        }
        i++;
    }
    fclose(f);
    return ok && i == t->n;
}
static void spec20_counts(void)
{
    pqdb *db;
    tally t;
    memset(&t, 0, sizeof t);
    /* the case of the spec: three plugins, two clap and one lv2 */
    if (open_ok(fx("base.sqlite"), fx("counts-user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    CHECK(pqdb_counts(db, "user", collect_count, &t) == 0 && t.n == 2, "%d formats", t.n);
    CHECK(t.n == 2 && strcmp(t.fmt[0], "clap") == 0 && t.plugins[0] == 2 && t.offered[0] == 1 && t.not_offered[0] == 1,
          "clap: %ld plugins, %ld offered, %ld not (two records of one plugin count once, offered when either is)", t.plugins[0], t.offered[0], t.not_offered[0]);
    CHECK(t.n == 2 && strcmp(t.fmt[1], "lv2") == 0 && t.plugins[1] == 1 && t.offered[1] == 1 && t.not_offered[1] == 0,
          "lv2: %ld plugins, %ld offered, %ld not", t.plugins[1], t.offered[1], t.not_offered[1]);
    pqdb_close(db);
    /* a layer, the other layer and both merged count their own sets */
    if (open_ok(fx("base.sqlite"), fx("user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    memset(&t, 0, sizeof t);
    CHECK(pqdb_counts(db, "user", collect_count, &t) == 0 && counts_match(&t, fx("expect-counts-user.tsv")), "layer user");
    memset(&t, 0, sizeof t);
    CHECK(pqdb_counts(db, "base", collect_count, &t) == 0 && counts_match(&t, fx("expect-counts-base.tsv")), "layer base");
    memset(&t, 0, sizeof t);
    CHECK(pqdb_counts(db, NULL, collect_count, &t) == 0 && counts_match(&t, fx("expect-counts-merged.tsv")), "merged");
    CHECK(pqdb_counts(db, "system", collect_count, &t) != 0, "an unknown layer name was accepted");
    pqdb_close(db);
}

/* ruling 2026-11-20: when the base holds one plugin at one cell from a set of the reference tier and from a set of
 * another tier, every read answers with the reference tier's record (the store spec, section 4). The fixtures hold the
 * provisional record and the reference one in both orders; neither the order of the sets nor of the records decides. */
static void tier_pick(void)
{
    static const char *const files[] = { "base-tiers-ref-last.sqlite", "base-tiers-ref-first.sqlite" };
    for (int i = 0; i < 2; i++) {
        pqdb *db;
        rows o;
        tally t;
        flist f;
        pqdb_verdict v;
        pqdb_result r;
        pqdb_query q = any();
        const char *in = files[i];
        memset(&v, 0, sizeof v);
        if (open_ok(fx(in), NULL, GOOD, &db)) { CHECK(0, "open %s", in); continue; }
        /* pqdb_each, as plugin-hostd reads: no filter, the cell's filter, the key's filter, the base layer by name */
        CHECK(walk(db, &q, &o) == 0 && o.n == 1, "%s: %d results for one plugin at one cell", in, o.n);
        CHECK(o.n >= 1 && strcmp(o.r[0].set, "fedora44-rt-48000-256") == 0 && o.r[0].median == 100.0 && o.r[0].p_ns == 110.0 &&
              o.r[0].latency == 128 && o.r[0].mem_first == 2048 && strcmp(o.r[0].bpath, "ref/p1.clap") == 0,
              "%s: the first result is set %s (median %g, binary %s), not the reference tier's", in, o.n ? o.r[0].set : "-",
              o.n ? o.r[0].median : 0.0, o.n ? o.r[0].bpath : "-");
        q.sha256 = SHA('a'); q.format = "clap"; q.uri = "urn:p1"; q.offer = "default"; q.host_class = "x86-64";
        q.rate = 48000; q.quantum = 256;
        CHECK(walk(db, &q, &o) == 0 && o.n == 1 && strcmp(o.r[0].set, "fedora44-rt-48000-256") == 0,
              "%s: the key at its cell gives %d results, the first of set %s", in, o.n, o.n ? o.r[0].set : "-");
        q.layer = "base";
        CHECK(walk(db, &q, &o) == 0 && o.n == 1 && strcmp(o.r[0].set, "fedora44-rt-48000-256") == 0,
              "%s: the base layer by name gives %d results", in, o.n);
        /* what a result leads to is the same record: its file list and its verdict */
        if (o.n >= 1) {
            memset(&r, 0, sizeof r);
            r.layer = o.r[0].layer; r.sha256 = o.r[0].sha; r.format = o.r[0].format; r.uri = o.r[0].uri;
            r.offer = o.r[0].offer; r.host_class = o.r[0].cls; r.rate = o.r[0].rate; r.quantum = o.r[0].quantum;
            memset(&f, 0, sizeof f);
            CHECK(pqdb_files(db, &r, collect_file, &f) == 0 && f.n == 1 && strcmp(f.path[0], "ref/p1.clap") == 0,
                  "%s: the file list is %s (%d entries), not the reference record's", in, f.n ? f.path[0] : "-", f.n);
            CHECK(pqdb_verdict_of(db, &r, "omx-clap-host", &v) == 0 && strcmp(v.rating, "qualified") == 0,
                  "%s: the verdict is %s, not the reference record's", in, v.rating ? v.rating : "-");
        }
        /* the counts: one plugin, offered only by the provisional record, which answers for no cell */
        memset(&t, 0, sizeof t);
        CHECK(pqdb_counts(db, "base", collect_count, &t) == 0 && t.n == 1 && strcmp(t.fmt[0], "clap") == 0 &&
              t.plugins[0] == 1 && t.offered[0] == 0 && t.not_offered[0] == 1,
              "%s: counts %d formats, clap %ld plugins, %ld offered, %ld not", in, t.n, t.plugins[0], t.offered[0], t.not_offered[0]);
        pqdb_close(db);
    }
}

/* ruling 2026-11-20: when the base holds one plugin at one cell from two sets of one tier, every read answers with the
 * record of the set measured later (record_set.measured; the store spec, section 4), in either order of the sets. */
static void newer_pick(void)
{
    static const char *const files[] = { "base-newer-new-last.sqlite", "base-newer-new-first.sqlite" };
    for (int i = 0; i < 2; i++) {
        pqdb *db;
        rows o;
        flist f;
        pqdb_verdict v;
        pqdb_result r;
        pqdb_query q = any();
        const char *in = files[i];
        memset(&v, 0, sizeof v);
        if (open_ok(fx(in), NULL, GOOD, &db)) { CHECK(0, "open %s", in); continue; }
        CHECK(walk(db, &q, &o) == 0 && o.n == 1, "%s: %d results for one plugin at one cell", in, o.n);
        CHECK(o.n >= 1 && strcmp(o.r[0].set, "zynthian-vangelis-48000-256") == 0 && o.r[0].median == 120.0 &&
              strcmp(o.r[0].bpath, "new/p1.clap") == 0,
              "%s: the result is set %s (median %g), not the newer set's", in, o.n ? o.r[0].set : "-", o.n ? o.r[0].median : 0.0);
        q.sha256 = SHA('a'); q.format = "clap"; q.uri = "urn:p1"; q.offer = "default"; q.host_class = "rpi5";
        q.rate = 48000; q.quantum = 256;
        CHECK(walk(db, &q, &o) == 0 && o.n == 1 && strcmp(o.r[0].set, "zynthian-vangelis-48000-256") == 0,
              "%s: the key at its cell gives %d results, the first of set %s", in, o.n, o.n ? o.r[0].set : "-");
        if (o.n >= 1) {
            memset(&r, 0, sizeof r);
            r.layer = o.r[0].layer; r.sha256 = o.r[0].sha; r.format = o.r[0].format; r.uri = o.r[0].uri;
            r.offer = o.r[0].offer; r.host_class = o.r[0].cls; r.rate = o.r[0].rate; r.quantum = o.r[0].quantum;
            memset(&f, 0, sizeof f);
            CHECK(pqdb_files(db, &r, collect_file, &f) == 0 && f.n == 1 && strcmp(f.path[0], "new/p1.clap") == 0,
                  "%s: the file list is %s, not the newer record's", in, f.n ? f.path[0] : "-");
            CHECK(pqdb_verdict_of(db, &r, "omx-clap-host", &v) == 0 && strcmp(v.rating, "qualified") == 0,
                  "%s: the verdict is %s, not the newer record's", in, v.rating ? v.rating : "-");
        }
        pqdb_close(db);
    }
}

typedef struct { pqdb *db; int docs, bad, last_n; char last_key[200]; char *last_doc; } jwalk;
static int check_json(const pqdb_result *x, void *ctx)
{
    jwalk *w = ctx;
    char name[300], path[400], key[200], *json = NULL, *want;
    const char *tail = strrchr(x->uri, ':');
    size_t n;
    pqdb_error e;
    snprintf(name, sizeof name, "records/%s-%s.%s.%s.json", x->format, tail ? tail + 1 : x->uri, x->offer, x->host_class);
    snprintf(path, sizeof path, "%s/%s", CT, name);
    want = slurp(path, &n);
    if (!want) { printf("  no expected document %s\n", path); w->bad++; return 0; }
    want[n] = 0;
    if (pqdb_record_json(w->db, x, &json, &e) != 0 || !json) {
        printf("  pqdb_record_json refused %s: %s\n", name, e.message); w->bad++; free(want); return 0;
    }
    if (strcmp(json, want) != 0) {
        size_t i = 0;
        while (json[i] && json[i] == want[i]) i++;
        printf("  %s differs at byte %zu: got ...%.60s\n                          want ...%.60s\n", name, i, json + (i > 20 ? i - 20 : 0), want + (i > 20 ? i - 20 : 0));
        w->bad++;
    }
    if (strstr(json, "\"detail\"") || strstr(json, "\"unmeasuredDetail\"") || strstr(json, "\"dimmed\"") || strstr(json, "\"unpinnable\"")) {
        printf("  %s holds a sentence path\n", name); w->bad++;
    }
    snprintf(key, sizeof key, "%s/%s/%s/%s", x->layer, x->sha256, x->offer, x->host_class);
    if (w->last_doc && strcmp(key, w->last_key) == 0 && strcmp(json, w->last_doc) != 0) {
        printf("  the cells of %s give other documents\n", key); w->bad++;
    }
    free(w->last_doc);
    w->last_doc = json;
    snprintf(w->last_key, sizeof w->last_key, "%s", key);
    w->docs++;
    free(want);
    return 0;
}
static void spec21_record_json(void)
{
    pqdb *db;
    jwalk w;
    pqdb_query q = any();
    pqdb_result none;
    pqdb_error e;
    char *json = (char *)1;
    memset(&w, 0, sizeof w);
    if (open_ok(fx("records.sqlite"), NULL, GOOD, &db)) { CHECK(0, "open"); return; }
    w.db = db;
    CHECK(pqdb_each(db, &q, check_json, &w) == 0, "walk");
    CHECK(w.docs >= 4 && w.bad == 0, "%d documents, %d wrong", w.docs, w.bad);
    free(w.last_doc);
    memset(&none, 0, sizeof none);
    none.layer = "base"; none.sha256 = SHA('0'); none.format = "clap"; none.uri = "urn:none"; none.offer = "default";
    none.host_class = "x86-64"; none.rate = 48000; none.quantum = 256;
    memset(&e, 0, sizeof e);
    CHECK(pqdb_record_json(db, &none, &json, &e) != 0 && e.code != NULL && e.message[0] != 0 && json == NULL, "a result of no record gave a document");
    pqdb_close(db);
}

static int touch_file(const char *path, const char *sha, void *ctx) { (void)path; (void)sha; (void)ctx; return 0; }
static int touch_count(const char *f, long a, long b, long c, void *ctx) { (void)f; (void)a; (void)b; (void)c; (void)ctx; return 0; }
static int touch_json(const pqdb_result *x, void *ctx)
{
    pqdb *db = ctx;
    char *json = NULL;
    pqdb_error e;
    pqdb_files(db, x, touch_file, NULL);
    if (pqdb_record_json(db, x, &json, &e) == 0) free(json);
    return 0;
}
static void spec24_read_only(void)
{
    char *t = tmpdir();
    ent a[32], b[32];
    int na, nb;
    pqdb *db;
    pqdb_query q = any();
    copy(fx("base.sqlite"), under(t, "base.sqlite"));
    copy(fx("user.sqlite"), under(t, "user.sqlite"));
    na = snapshot(t, a); qsort(a, (size_t)na, sizeof *a, by_name);
    if (open_ok(under(t, "base.sqlite"), under(t, "user.sqlite"), GOOD, &db)) { CHECK(0, "open"); return; }
    CHECK(pqdb_each(db, &q, touch_json, db) == 0, "walk");
    q.layer = "base";
    CHECK(pqdb_each(db, &q, touch_json, db) == 0, "walk base");
    CHECK(pqdb_counts(db, NULL, touch_count, NULL) == 0 && pqdb_counts(db, "user", touch_count, NULL) == 0, "counts");
    pqdb_close(db);
    nb = snapshot(t, b); qsort(b, (size_t)nb, sizeof *b, by_name);
    CHECK(na == nb, "directory listing changed: %d -> %d entries", na, nb);
    for (int i = 0; i < na && i < nb; i++)
        CHECK(strcmp(a[i].name, b[i].name) == 0 && a[i].size == b[i].size && a[i].mtime == b[i].mtime, "%s changed", a[i].name);
}

/* ---- the hosting exception (section 3.4): hosting words are passed over, every other word is checked ---- */
static void hosting_columns(void)
{
    pqdb *db;
    pqdb_error e;
    const struct { const char *kind, *column; } cols[] = { { "verdict", "verdict.deciding" }, { "not-measured", "not_measured.code" },
                                                            { "tier", "tier.deciding" }, { "reason", "reason.code" } };
    /* the store names `hosting` in store_domain and the contract directory holds no such domain: it opens */
    CHECK(open_ok(fx("base.sqlite"), fx("user.sqlite"), GOOD, &db) == 0, "a store with a hosting row is refused");
    if (db) pqdb_close(db);
    for (size_t i = 0; i < sizeof cols / sizeof *cols; i++) {
        char f[80];
        /* a hosting word: passed over, whether or not any package holds it (the writer checked it) */
        snprintf(f, sizeof f, "base-ok-%s.sqlite", cols[i].kind);
        CHECK(open_ok(fx(f), NULL, GOOD, &db) == 0, "a hosting word was refused in %s", cols[i].column);
        if (db) pqdb_close(db);
        snprintf(f, sizeof f, "base-unknown-%s.sqlite", cols[i].kind);
        CHECK(open_ok(fx(f), NULL, GOOD, &db) == 0, "a hosting word no package holds was refused in %s", cols[i].column);
        if (db) pqdb_close(db);
        /* any other word that no non-hosting item holds is refused, naming the column and the word */
        snprintf(f, sizeof f, "base-bad-%s.sqlite", cols[i].kind);
        expect_refusal(fx(f), NULL, GOOD, "qualification-db.word-unknown", &e);
        CHECK(strstr(e.message, cols[i].column) && strstr(e.message, "probe.no-such-word"), "%s", e.message);
    }
    expect_refusal(fx("base-bad-rating.sqlite"), NULL, GOOD, "qualification-db.word-unknown", &e);
    CHECK(strstr(e.message, "verdict.rating") && strstr(e.message, "excellent"), "%s", e.message);
}
/* hosting-skip-ends: while the reader skips the hosting columns, no contract directory the tests read may hold a hosting
 * domain document: once one exists the skip is to be removed (section 3.4). */
static void hosting_skip_ends(void)
{
    const char *dirs[] = { "contract-good", "contract-no-conditional", "contract-old" };
    for (size_t i = 0; i < sizeof dirs / sizeof *dirs; i++) {
        char path[1100];
        snprintf(path, sizeof path, "%s/hosting/hosting.json", contract(dirs[i]));
        CHECK(access(path, F_OK) != 0, "%s exists: a hosting domain is there while the reader still skips the hosting columns; remove the skip", path);
    }
}

/* ---- numbers as JSON.stringify writes them (ECMAScript Number::toString): cell.latency_ms of numbers.sqlite ---- */
static void number_edges(void)
{
    static const char *const want[] = { "1e-7", "0.000001", "1.23e-18", "1e+21", "1.5e+300", "5e-324", "0", "100", "0.1",
                                        "0.6666666666666666" };
    pqdb *db;
    pqdb_query q = any();
    rows o;
    char *json = NULL;
    pqdb_error e;
    const char *at;
    if (open_ok(fx("numbers.sqlite"), NULL, GOOD, &db)) { CHECK(0, "open"); return; }
    CHECK(walk(db, &q, &o) == 0 && o.n == 10, "%d cells", o.n);
    if (o.n == 10) {
        pqdb_result r;
        memset(&r, 0, sizeof r);
        r.layer = o.r[0].layer; r.sha256 = o.r[0].sha; r.format = o.r[0].format; r.uri = o.r[0].uri; r.offer = o.r[0].offer;
        r.host_class = o.r[0].cls; r.rate = o.r[0].rate; r.quantum = o.r[0].quantum;
        CHECK(pqdb_record_json(db, &r, &json, &e) == 0 && json, "%s", e.message);
    }
    at = json;
    for (size_t i = 0; json && i < sizeof want / sizeof *want; i++) {
        char got[64];
        size_t n;
        at = strstr(at, "\"latencyMs\":");
        CHECK(at != NULL, "no latencyMs for cell %zu", i);
        if (!at) break;
        at += strlen("\"latencyMs\":");
        n = strcspn(at, ",}");
        snprintf(got, sizeof got, "%.*s", (int)(n < 63 ? n : 63), at);
        CHECK(strcmp(got, want[i]) == 0, "cell %zu: got %s, JSON.stringify writes %s", i, got, want[i]);
    }
    free(json);
    pqdb_close(db);
}

/* ---- the document does not depend on the host's locale: a program that called setlocale(LC_ALL, "") under a comma
 * locale gets the same bytes ---- */
static void comma_locale(void)
{
    static const char *const cands[] = { "ca_ES.UTF-8", "ca_ES.utf8", "de_DE.UTF-8", "de_DE.utf8", "fr_FR.UTF-8", "fr_FR.utf8" };
    char old[128], probe[16];
    int set = 0;
    snprintf(old, sizeof old, "%s", setlocale(LC_NUMERIC, NULL));
    for (size_t i = 0; i < sizeof cands / sizeof *cands && !set; i++)
        set = setlocale(LC_NUMERIC, cands[i]) != NULL;
    if (!set) { skip_reason = "no comma locale (ca_ES, de_DE or fr_FR, UTF-8) is installed on this machine"; return; }
    snprintf(probe, sizeof probe, "%.1f", 2.5);
    if (probe[1] != ',') { setlocale(LC_NUMERIC, old); skip_reason = "the locale found has no decimal comma"; return; }
    spec21_record_json();
    number_edges();
    setlocale(LC_NUMERIC, old);
}

/* ---- a REAL that is not finite (SQLite keeps 1e999 as Infinity) is refused by name, never written and never a crash ---- */
static void non_finite(void)
{
    static const struct { const char *file, *column; } stores[] = { { "nonfinite-pos.sqlite", "latency_ms" },
        { "nonfinite-neg.sqlite", "latency_ms" }, { "nonfinite-line.sqlite", "latency_line_ms" }, { "nonfinite-cpu.sqlite", "cost_median" } };
    for (size_t i = 0; i < sizeof stores / sizeof *stores; i++) {
        pqdb *db;
        rows o;
        pqdb_query q = any();
        pqdb_result r;
        pqdb_error e;
        char *json = (char *)1;
        if (open_ok(fx(stores[i].file), NULL, GOOD, &db)) { CHECK(0, "open"); continue; }
        (void)q; (void)o;     /* the result by hand: pqdb_each itself refuses an infinite cost figure */
        memset(&r, 0, sizeof r);
        r.layer = "base"; r.sha256 = SHA('a'); r.format = "clap"; r.uri = "urn:p1"; r.offer = "default"; r.host_class = "x86-64";
        r.rate = 48000; r.quantum = 256;
        memset(&e, 0, sizeof e);
        CHECK(pqdb_record_json(db, &r, &json, &e) != 0 && json == NULL, "%s: a document was written", stores[i].file);
        CHECK(e.code && strcmp(e.code, "qualification-db.not-a-store") == 0 && strstr(e.message, stores[i].column), "%s: %s %s",
              stores[i].file, e.code ? e.code : "(no code)", e.message);
        pqdb_close(db);
    }
}

/* ---- pqdb_each refuses a non-finite figure, and pqdb_number writes one as JSON.stringify does ---- */
static int ignore_row(const pqdb_result *x, void *ctx) { (void)x; (void)ctx; return 0; }
static void each_non_finite(void)
{
    pqdb *db;
    pqdb_query q = any();
    int rc;
    if (open_ok(fx("nonfinite-cpu.sqlite"), NULL, GOOD, &db)) { CHECK(0, "open"); return; }
    rc = pqdb_each(db, &q, ignore_row, NULL);
    CHECK(rc != 0 && pqdb_code(rc) && strcmp(pqdb_code(rc), "qualification-db.not-a-store") == 0, "pqdb_each gave %d (%s)", rc, pqdb_code(rc) ? pqdb_code(rc) : "no code");
    CHECK(pqdb_message(db) != NULL && strstr(pqdb_message(db), "cost_median") != NULL, "message: %s", pqdb_message(db) ? pqdb_message(db) : "(none)");
    pqdb_close(db);
}
static void number_writer(void)
{
    char t[64];
    const struct { double v; const char *want; } c[] = { { 12.5, "12.5" }, { 2.0, "2" }, { 1e-7, "1e-7" }, { 0.1, "0.1" }, { -0.0, "0" } };
    for (size_t i = 0; i < sizeof c / sizeof *c; i++)
        CHECK(pqdb_number(c[i].v, t, sizeof t) == 0 && strcmp(t, c[i].want) == 0, "%g: got %s, want %s", c[i].v, t, c[i].want);
    CHECK(pqdb_number(INFINITY, t, sizeof t) != 0 && pqdb_number(-INFINITY, t, sizeof t) != 0, "a non-finite number was written");
    CHECK(pqdb_number(0.30000000000000004, t, 8) != 0, "a number too long for the buffer was written");
    {   /* under a comma locale, when one is installed */
        char old[128];
        snprintf(old, sizeof old, "%s", setlocale(LC_NUMERIC, NULL));
        if (setlocale(LC_NUMERIC, "ca_ES.UTF-8") || setlocale(LC_NUMERIC, "de_DE.UTF-8") || setlocale(LC_NUMERIC, "fr_FR.UTF-8")) {
            CHECK(pqdb_number(12.5, t, sizeof t) == 0 && strcmp(t, "12.5") == 0, "under a comma locale: %s", t);
            setlocale(LC_NUMERIC, old);
        } else skip_reason = "no comma locale is installed on this machine";
    }
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
    CHECK(rc == 0, "open with a variable set: %s", rc ? e.code : "succeeded");
    if (rc) return;
    {
        rows o;
        pqdb_query q = any();
        CHECK(pqdb_base_absent(db) == 1, "the installed base is not there: the handle must say so");
        CHECK(walk(db, &q, &o) == 0 && o.n == 0, "a variable stood in for the installed places: %d rows", o.n);
    }
    pqdb_close(db);
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
    { "01 absent base is an empty base layer", t01_absent_base, 0 }, { "01 a base that is a directory", t01_base_is_a_directory, 0 },
    { "01 a base that is junk", t01_base_is_junk, 0 }, { "01 a base of another version", t01_base_wrong_version, 0 },
    { "01 a base that cannot be read", t01_base_not_readable, 0 }, { "01 a base path through a file", t01_base_under_a_file, 0 }, { "02 absent user layer", t02_absent_user, 0 },
    { "03 one schema version", t03_versions, 0 }, { "04 word not in the domain", t04_word_unknown, 0 },
    { "05 domain too old", t05_domain_too_old, 0 }, { "06 whole-record merge", t06_whole_record_merge, 0 },
    { "07 a user record shadows the whole base record", t07_shadows_whole, 0 },
    { "08 another key is not shadowed", t08_other_key_not_shadowed, 0 }, { "09 package lookup", t09_package_lookup, 0 },
    { "10 read only", t10_read_only, 0 }, { "10 snapshots ignore neighbours", snapshot_neighbours, 0 }, { "12 busy", t12_busy, 0 }, { "13 figures agree with qualcost", t13_figures, 0 },
    { "16 hot journal", t16_hot_journal, 0 }, { "17 adapter code in parts", t17_adapter_code, 0 },
    { "18 verdict of a result", t18_verdict, 0 },
    { "spec 17 the identity fields", spec17_identity, 0 }, { "spec 18 pqdb_files", spec18_files, 0 },
    { "spec 19 binary_path and layer filters", spec19_filters, 0 },
    { "spec 20 pqdb_counts", spec20_counts, 0 }, { "spec 21 pqdb_record_json", spec21_record_json, 0 },
    { "spec 24 read only still", spec24_read_only, 0 },
    { "the reference tier answers where two tiers hold a cell", tier_pick, 0 },
    { "the newer set answers where two sets of one tier hold a cell", newer_pick, 0 },
    { "hosting words passed over, nothing else narrowed", hosting_columns, 0 }, { "hosting-skip-ends", hosting_skip_ends, 0 }, { "numbers as JSON.stringify writes them", number_edges, 0 },
    { "the document under a comma locale", comma_locale, 0 }, { "a non-finite number is refused", non_finite, 0 },
    { "pqdb_each refuses a non-finite figure", each_non_finite, 0 }, { "pqdb_number", number_writer, 0 }, { "19 PQDB_QUERY_ANY", t19_query_any, 0 }, { "20 PQDB_QUERY_ANY fields", t20_query_any_fields, 0 },
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
        if (skip_reason) { printf("skip   %s: %s\n", TESTS[i].name, skip_reason); skip_reason = NULL; continue; }
        printf("%s %s\n", failures == before ? "ok    " : "not ok", TESTS[i].name);
        ran++; bad += failures != before;
    }
    tmp_clean();
    printf("%d tests, %d failed, %d checks\n", ran, bad, checks);
    return bad ? 1 : 0;
}
