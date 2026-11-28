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
MANDIR   ?= $(DATADIR)/man
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
all: lib cmd

$(BUILD):
	mkdir -p $(BUILD)

# the DDL and the migration of a user layer, as C strings: the reader migrates a user layer with the same files the writer
# runs (spec section 3.6), and links no file of the schema package
MIGRATION := schema/migrations/1-to-3.sql schema/migrations/2-to-3.sql
$(BUILD)/pqdb_sql.h: schema/qualification.sql $(MIGRATION) | $(BUILD)
	{ printf 'static const char PQDB_DDL[] =\n'; sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/^/"/' -e 's/$$/\\n"/' schema/qualification.sql; \
	  printf ';\nstatic const char PQDB_MIGRATION_1_TO_3[] =\n'; sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/^/"/' -e 's/$$/\\n"/' schema/migrations/1-to-3.sql; \
	  printf ';\nstatic const char PQDB_MIGRATION_2_TO_3[] =\n'; sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/^/"/' -e 's/$$/\\n"/' schema/migrations/2-to-3.sql; \
	  printf ';\n'; } > $@.tmp && mv $@.tmp $@

# only pqdb_* is exported: src/pqdb.map names it and hides the rest
$(BUILD)/$(SONAME): src/pqdb.c src/pqdb_record.c src/pqdb_record.h src/pqdb.map include/plugin-qualification-db/pqdb.h $(BUILD)/pqdb_sql.h | $(BUILD)
	$(CC) $(WARN) $(CFLAGS) $(CPPFLAGS) -fPIC $(INC) -I$(BUILD) $(SQLITE_CFLAGS) $(DOMAIN_CFLAGS) -shared \
	  -Wl,-soname,$(SONAME) -Wl,--version-script=src/pqdb.map $(LDFLAGS) src/pqdb.c src/pqdb_record.c -o $@ $(SQLITE_LIBS) $(DOMAIN_LIBS)
	ln -sf $(SONAME) $(BUILD)/libplugin-qualification-db.so

$(BUILD)/plugin-qualification-db: src/plugin-qualification-db.c $(BUILD)/$(SONAME)
	$(CC) $(WARN) $(CFLAGS) $(CPPFLAGS) $(INC) $(LDFLAGS) src/plugin-qualification-db.c -o $@ \
	  -L$(BUILD) -lplugin-qualification-db -Wl,-rpath,'$$ORIGIN'

# the .pc is made from the template at install time, with that install's own PREFIX, LIBDIR and DATADIR: no copy
# built earlier (a staged test install) can carry another prefix
# the DDL (plugin-qualification-db-schema) and the writer's module and command (-write) share one directory: the module
# finds the DDL beside itself
install: all
	install -d $(DESTDIR)$(MANDIR)/man1 $(DESTDIR)$(LIBDIR)/pkgconfig $(DESTDIR)$(BINDIR) $(DESTDIR)$(INCLUDEDIR)/plugin-qualification-db \
	  $(DESTDIR)$(DATADIR)/plugin-qualification-db
	install -m 0755 $(BUILD)/$(SONAME) $(DESTDIR)$(LIBDIR)/
	ln -sf $(SONAME) $(DESTDIR)$(LIBDIR)/libplugin-qualification-db.so
	install -m 0755 $(BUILD)/plugin-qualification-db $(DESTDIR)$(BINDIR)/
	install -m 0644 man/plugin-qualification-db.1 $(DESTDIR)$(MANDIR)/man1/
	install -m 0644 include/plugin-qualification-db/pqdb.h $(DESTDIR)$(INCLUDEDIR)/plugin-qualification-db/
	install -m 0644 schema/qualification.sql $(DESTDIR)$(DATADIR)/plugin-qualification-db/
	install -d $(DESTDIR)$(DATADIR)/plugin-qualification-db/migrations
	install -m 0644 $(MIGRATION) $(DESTDIR)$(DATADIR)/plugin-qualification-db/migrations/
	install -m 0644 tools/qualification_db.py $(DESTDIR)$(DATADIR)/plugin-qualification-db/
	sed -e 's|@MODULEDIR@|$(DATADIR)/plugin-qualification-db|' tools/plugin-qualification-db-write \
	  > $(DESTDIR)$(BINDIR)/plugin-qualification-db-write
	chmod 0755 $(DESTDIR)$(BINDIR)/plugin-qualification-db-write
	install -m 0644 man/plugin-qualification-db-write.1 $(DESTDIR)$(MANDIR)/man1/
	sed -e 's|@PREFIX@|$(PREFIX)|' -e 's|@LIBDIR@|$(LIBDIR)|' -e 's|@INCLUDEDIR@|$(INCLUDEDIR)|' \
	  -e 's|@DATADIR@|$(DATADIR)|' -e 's|@VERSION@|$(VERSION)|' plugin-qualification-db.pc.in \
	  > $(DESTDIR)$(LIBDIR)/pkgconfig/plugin-qualification-db.pc
	chmod 0644 $(DESTDIR)$(LIBDIR)/pkgconfig/plugin-qualification-db.pc

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
	sh tools/hosting-skip-ends.sh --self-test
	sh test/test_no_copy.sh src
	sh test/test_pool_round_trip.sh $(BUILD)/test_reader $(CONTRACTDIR)
	sh test/test_no_figures.sh $(BUILD)/test_reader $(CONTRACTDIR)
	sh test/test_nm.sh $(BUILD)/$(SONAME)
	sh test/test_cxx.sh $(BUILD)
	PQDB_TEST_CONTRACTDIR=$(CONTRACTDIR) sh test/test_command.sh $(BUILD)/plugin-qualification-db $(BUILD)/fixtures test/fixtures $(abspath $(BUILD)/shim.so)
	rm -rf $(BUILD)/stage
	$(MAKE) install DESTDIR=$(abspath $(BUILD)/stage) PREFIX=/usr
	sh test/test_install.sh $(abspath $(BUILD)/stage) $(LIBDIR)
	rm -rf $(BUILD)/stage2
	$(MAKE) install DESTDIR=$(abspath $(BUILD)/stage2) PREFIX=/usr/local LIBDIR=/usr/local/lib DATADIR=/usr/local/share
	sh test/test_prefix.sh $(abspath $(BUILD)/stage2)

clean:
	rm -rf $(BUILD)

.PHONY: lib cmd all install check clean
