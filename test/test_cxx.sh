#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# Compiles the header as C++11, pedantic, and runs the check of PQDB_QUERY_ANY. Skipped, with a message, without g++.
# Usage: test_cxx.sh <build dir>
set -u
build=$1
if ! command -v g++ >/dev/null 2>&1; then
    echo "skip   PQDB_QUERY_ANY as C++11: no g++"
    exit 0
fi
g++ -std=c++11 -pedantic-errors -Wall -Wextra -Werror -Iinclude test/test_cxx.cc -o "$build/test_cxx" || { echo "not ok PQDB_QUERY_ANY as C++11: does not compile"; exit 1; }
"$build/test_cxx"
