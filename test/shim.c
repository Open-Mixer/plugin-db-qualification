/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com> */
/* A test-only LD_PRELOAD shim: it lets the reader's production entry point run on a machine whose installed places
 * are not there. PQDB_SHIM_MAP="from=to:from=to" rewrites a path that starts with `from` to start with `to`;
 * PQDB_SHIM_HOME is the home getpwuid() reports; PQDB_SHIM_TRACE is a file every path the process opens, stats or
 * lists is appended to (before the rewrite). Never linked into the library or the command. */
#define _GNU_SOURCE
#include <dirent.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <pwd.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static void trace(const char *path)
{
    const char *t = getenv("PQDB_SHIM_TRACE");
    FILE *f;
    if (!t || !path || !(f = fopen(t, "a")))
        return;
    fprintf(f, "%s\n", path);
    fclose(f);
}

static const char *map(const char *path, char *buf, size_t n)
{
    const char *m = getenv("PQDB_SHIM_MAP");
    if (!path)
        return path;
    trace(path);
    while (m && *m) {
        const char *eq = strchr(m, '='), *end = strchr(m, ':');
        size_t flen, tlen;
        if (!eq)
            break;
        if (!end)
            end = m + strlen(m);
        flen = (size_t)(eq - m);
        tlen = (size_t)(end - eq - 1);
        if (strncmp(path, m, flen) == 0 && (path[flen] == '/' || path[flen] == 0)) {
            snprintf(buf, n, "%.*s%s", (int)tlen, eq + 1, path + flen);
            return buf;
        }
        m = *end ? end + 1 : end;
    }
    return path;
}

#define REAL(name, ret, args) static ret (*real_##name) args; if (!real_##name) real_##name = dlsym(RTLD_NEXT, #name)
#define P char b[4096]; path = map(path, b, sizeof b)

int open(const char *path, int flags, ...)
{
    mode_t mode = 0;
    P;
    if (flags & (O_CREAT | O_TMPFILE)) { va_list ap; va_start(ap, flags); mode = va_arg(ap, mode_t); va_end(ap); }
    REAL(open, int, (const char *, int, ...));
    return real_open(path, flags, mode);
}
int open64(const char *path, int flags, ...)
{
    mode_t mode = 0;
    P;
    if (flags & (O_CREAT | O_TMPFILE)) { va_list ap; va_start(ap, flags); mode = va_arg(ap, mode_t); va_end(ap); }
    REAL(open64, int, (const char *, int, ...));
    return real_open64(path, flags, mode);
}
FILE *fopen(const char *path, const char *mode) { P; REAL(fopen, FILE *, (const char *, const char *)); return real_fopen(path, mode); }
FILE *fopen64(const char *path, const char *mode) { P; REAL(fopen64, FILE *, (const char *, const char *)); return real_fopen64(path, mode); }
DIR *opendir(const char *path) { P; REAL(opendir, DIR *, (const char *)); return real_opendir(path); }
int stat(const char *path, struct stat *st) { P; REAL(stat, int, (const char *, struct stat *)); return real_stat(path, st); }
int stat64(const char *path, struct stat64 *st) { P; REAL(stat64, int, (const char *, struct stat64 *)); return real_stat64(path, st); }
int lstat(const char *path, struct stat *st) { P; REAL(lstat, int, (const char *, struct stat *)); return real_lstat(path, st); }
int lstat64(const char *path, struct stat64 *st) { P; REAL(lstat64, int, (const char *, struct stat64 *)); return real_lstat64(path, st); }
int access(const char *path, int mode) { P; REAL(access, int, (const char *, int)); return real_access(path, mode); }

struct passwd *getpwuid(uid_t uid)
{
    static struct passwd pw;
    const char *home = getenv("PQDB_SHIM_HOME");
    REAL(getpwuid, struct passwd *, (uid_t));
    if (!home)
        return real_getpwuid(uid);
    pw.pw_name = (char *)"fixture";
    pw.pw_uid = uid;
    pw.pw_dir = (char *)home;
    pw.pw_shell = (char *)"/bin/false";
    return &pw;
}
