# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# The reader of the qualification store: libplugin-qualification-db.so.0, its command plugin-qualification-db and
# plugin-qualification-db.pc (this repository's qualification store spec, sections 6 and 7). `make check` builds them
# and runs the reader's tests against fixture stores built from schema/qualification.sql.
#
# SQLITE_* and DOMAIN_* are the compile and link flags of sqlite3 (3.37.0 or later) and libomx-domain; they default
# to what pkg-config says.

CC       ?= cc
CFLAGS   ?= -O2 -g
# messages are bounded by pqdb_error.message: a long path truncates, by design
WARN     := -Wall -Wextra -Werror -Wno-format-truncation -std=c11
PREFIX   ?= /usr
LIBDIR   ?= $(PREFIX)/lib
BINDIR   ?= $(PREFIX)/bin
INCLUDEDIR ?= $(PREFIX)/include
DATADIR  ?= $(PREFIX)/share
DESTDIR  ?=
SQLITE_CFLAGS ?= $(shell pkg-config --cflags sqlite3)
SQLITE_LIBS   ?= $(shell pkg-config --libs sqlite3)
DOMAIN_CFLAGS ?= $(shell pkg-config --cflags libomx-domain)
DOMAIN_LIBS   ?= $(shell pkg-config --libs libomx-domain)
# the contract directory libomx-domain was built for: omx_domain_open() reads it, and the scope tests redirect it
CONTRACTDIR   ?= $(shell pkg-config --variable=contractdir libomx-domain)
VERSION  ?= $(shell sed -n '1s/^[^(]*(\([^)]*\)).*/\1/p' debian/changelog)

SONAME  := libplugin-qualification-db.so.0
BUILD   := build
INC     := -Iinclude

lib: $(BUILD)/$(SONAME)
cmd: $(BUILD)/plugin-qualification-db
all: lib cmd $(BUILD)/plugin-qualification-db.pc

$(BUILD):
	mkdir -p $(BUILD)

# only pqdb_* is exported: src/pqdb.map names it and hides the rest
$(BUILD)/$(SONAME): src/pqdb.c src/pqdb.map include/plugin-qualification-db/pqdb.h | $(BUILD)
	$(CC) $(WARN) $(CFLAGS) $(CPPFLAGS) -fPIC $(INC) $(SQLITE_CFLAGS) $(DOMAIN_CFLAGS) -shared \
	  -Wl,-soname,$(SONAME) -Wl,--version-script=src/pqdb.map $(LDFLAGS) src/pqdb.c -o $@ $(SQLITE_LIBS) $(DOMAIN_LIBS)
	ln -sf $(SONAME) $(BUILD)/libplugin-qualification-db.so

$(BUILD)/plugin-qualification-db: src/plugin-qualification-db.c $(BUILD)/$(SONAME)
	$(CC) $(WARN) $(CFLAGS) $(CPPFLAGS) $(INC) $(LDFLAGS) src/plugin-qualification-db.c -o $@ \
	  -L$(BUILD) -lplugin-qualification-db -Wl,-rpath,'$$ORIGIN'

$(BUILD)/plugin-qualification-db.pc: plugin-qualification-db.pc.in
	sed -e 's|@PREFIX@|$(PREFIX)|' -e 's|@LIBDIR@|$(LIBDIR)|' -e 's|@INCLUDEDIR@|$(INCLUDEDIR)|' \
	  -e 's|@DATADIR@|$(DATADIR)|' -e 's|@VERSION@|$(VERSION)|' $< > $@

# the DDL is installed beside the header (-dev): writers and test fixtures read it from there, with no checkout
install: all
	install -d $(DESTDIR)$(LIBDIR)/pkgconfig $(DESTDIR)$(BINDIR) $(DESTDIR)$(INCLUDEDIR)/plugin-qualification-db \
	  $(DESTDIR)$(DATADIR)/plugin-qualification-db
	install -m 0755 $(BUILD)/$(SONAME) $(DESTDIR)$(LIBDIR)/
	ln -sf $(SONAME) $(DESTDIR)$(LIBDIR)/libplugin-qualification-db.so
	install -m 0755 $(BUILD)/plugin-qualification-db $(DESTDIR)$(BINDIR)/
	install -m 0644 include/plugin-qualification-db/pqdb.h $(DESTDIR)$(INCLUDEDIR)/plugin-qualification-db/
	install -m 0644 schema/qualification.sql $(DESTDIR)$(DATADIR)/plugin-qualification-db/
	install -m 0644 $(BUILD)/plugin-qualification-db.pc $(DESTDIR)$(LIBDIR)/pkgconfig/

# ---- tests ----
$(BUILD)/test_reader: test/test_reader.c $(BUILD)/$(SONAME)
	$(CC) $(WARN) $(CFLAGS) $(INC) $(SQLITE_CFLAGS) $(LDFLAGS) test/test_reader.c -o $@ \
	  -L$(BUILD) -lplugin-qualification-db -Wl,-rpath,'$$ORIGIN' $(SQLITE_LIBS)

$(BUILD)/shim.so: test/shim.c | $(BUILD)
	$(CC) -Wall -Wextra -O1 -fPIC -shared test/shim.c -o $@ -ldl

check: $(BUILD)/test_reader $(BUILD)/plugin-qualification-db $(BUILD)/shim.so
	rm -rf $(BUILD)/fixtures
	python3 test/make-fixtures.py $(BUILD)/fixtures
	$(BUILD)/test_reader $(BUILD)/fixtures test/fixtures
	LD_PRELOAD=$(abspath $(BUILD)/shim.so) PQDB_TEST_CONTRACTDIR=$(CONTRACTDIR) \
	  $(BUILD)/test_reader $(BUILD)/fixtures $(abspath test/fixtures) scopes
	sh test/test_nm.sh $(BUILD)/$(SONAME)
	sh test/test_command.sh $(BUILD)/plugin-qualification-db $(BUILD)/fixtures test/fixtures
	rm -rf $(BUILD)/stage
	$(MAKE) install DESTDIR=$(abspath $(BUILD)/stage) PREFIX=/usr
	sh test/test_install.sh $(abspath $(BUILD)/stage) $(LIBDIR)

clean:
	rm -rf $(BUILD)

.PHONY: lib cmd all install check clean
