// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
// The header is C++11: PQDB_QUERY_ANY is a valid initializer there (no designated initializers, which C++ has only
// from C++20), and it is what it says: every string NULL, rate and quantum -1.
#include <plugin-qualification-db/pqdb.h>

#include <cstdio>

int main()
{
    pqdb_query q = PQDB_QUERY_ANY;
    const char *const *strings[] = { &q.sha256, &q.format, &q.uri, &q.offer, &q.host_class, &q.pkg_format, &q.pkg_name,
                                     &q.pkg_version, &q.pkg_release, &q.pkg_distro, &q.pkg_arch, &q.binary_path, &q.layer };
    int bad = 0;
    for (const char *const *s : strings)
        if (*s != nullptr)
            bad = 1;
    if (q.rate != -1 || q.quantum != -1)
        bad = 1;
    // positional, in the field order of section 6
    pqdb_query p = { "s", "f", "u", "o", "h", 1, 2, "pf", "pn", "pv", "pr", "pd", "pa", "bp", "ly" };
    if (p.sha256[0] != 's' || p.host_class[0] != 'h' || p.rate != 1 || p.quantum != 2 || p.pkg_arch[1] != 'a' ||
        p.binary_path[0] != 'b' || p.layer[0] != 'l')
        bad = 1;
    std::printf("%s     PQDB_QUERY_ANY as C++11\n", bad ? "not ok" : "ok");
    return bad;
}
