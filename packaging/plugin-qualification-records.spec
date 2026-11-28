# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# The RPM side of the records: one package, plugin-qualification-records, per architecture, the same package the
# Debian side builds from debian/. It carries every set of the machine classes packaging/arch-classes gives its
# architecture, at /usr/share/omx/qualification/<class>/<set>/; plugin-qualify-sync chooses the set of the machine's
# class and cell. A set is per machine class, per sample rate and per quantum (fedora44-48000-512). The version is
# 0.MAJOR.MINOR, the one the tag (v<version>) and debian/changelog carry; the date stamp YYYYMMDDXX is the Release
# (owner 2026-11-24, #81): it orders builds, the version says what is compatible.
#
# x86_64 carries the x86-64 class (the fedora44 sets). aarch64 carries the rpi5 class, the same sets the arm64 deb
# carries: a package that depends on the records installs on Fedora aarch64 too, and a record applies only where the
# installed plugin's bytes are the measured ones.
#
# No OpenMixer package is named with a version written by hand: the build installs the lower levels' published
# packages, the library's runtime dependencies are rpm's generated soname dependencies and the devel package's are the
# ones rpm generates from plugin-qualification-db.pc; between subpackages of this spec, = %%{version}-%%{release}. The
# one floor kept is third-party: sqlite 3.37.0, the first with STRICT tables.

%global debug_package %{nil}
%global qual_dir %{_datadir}/omx/qualification

Name: plugin-qualification-records
Version: 0.1.2
Release: 2026112702%{?dist}
Summary: The qualification layer of plugin-db: records of OpenMixer plugin sets
License: GPL-3.0-or-later
URL: https://github.com/Open-Mixer/plugin-db-qualification
Source0: %{name}-%{version}.tar.gz
ExclusiveArch: x86_64 aarch64

# tools/sets.py in %%install and the record check in %%check
BuildRequires: python3
# the reader (the Makefile): sqlite 3.37.0 is the first with STRICT tables; libomx-domain is the contract loader
BuildRequires: gcc make pkgconfig binutils
BuildRequires: sqlite-devel >= 3.37.0
BuildRequires: libomx-domain-devel
# tools/records-db.py: the base database, its words checked against the owners' domains at the releases that publish them
BuildRequires: python3-jsonschema
# qualification and machine are plugin-hostd's domains, probe plugin-hostd-protocol's
BuildRequires: plugin-hostd-contract
BuildRequires: plugin-hostd-protocol-contract
BuildRequires: plugin-db-contract
BuildRequires: omx-clap-contract

# the sync that reads the records, a weak dependency: the records are inert data without it, and plugin-qualify builds
# on plugin-hostd, which builds on this source's reader, so a hard one would make the records uninstallable until a
# later layer of the wave is published (the staged install check of a merge to devel)
Recommends: plugin-qualify

%description
The qualification layer of the plugin database: the plugin-qualify records of
the plugin sets measured on a reference machine of a host class.
plugin-qualify-sync takes a plugin from them instead of measuring it, and only
when every file of the installed plugin hashes as the measured one did; any
other plugin is measured on the machine as before. The sync chooses the set of
the machine's class and cell.

On x86_64: the x86-64 class, the fedora44 sets (the OpenMixer worker image's
plugins on Fedora 44), one per sample rate and quantum. Provisional records:
measured on JACK's dummy driver without real-time priority; the crash, hang
and unmeasured verdicts hold, the cost, latency and xrun figures are not
reference figures. An x86_64 machine has no device tree to name its class: the
sync reads these records once /etc/omx/qualify.conf says "host_class x86-64",
and finds the CLAP plugins of /usr/lib64/clap once it says
"clap_extra /usr/lib64/clap".

%package -n libplugin-qualification-db
Summary: Reader of the OpenMixer qualification store
Requires: sqlite-libs >= 3.37.0

%description -n libplugin-qualification-db
The C library that reads the qualification store: the base database of
plugin-qualification-records and a user layer, merged by whole record, with
every word column checked against the contract domains that own its words.
It reads figures at start-up, never in a real-time path.

%package -n libplugin-qualification-db-devel
Summary: Reader of the OpenMixer qualification store, development files
Requires: libplugin-qualification-db%{?_isa} = %{version}-%{release}
Requires: plugin-qualification-db-schema = %{version}-%{release}
Requires: sqlite-devel >= 3.37.0

%description -n libplugin-qualification-db-devel
The header, the shared library link and plugin-qualification-db.pc, whose
variable schema names the DDL of plugin-qualification-db-schema.

%package -n plugin-qualification-db
Summary: Command to query the OpenMixer qualification store
Requires: libplugin-qualification-db%{?_isa} = %{version}-%{release}

%description -n plugin-qualification-db
plugin-qualification-db query --json prints the results of the base database
and the user layer, one JSON object per line; check opens both layers and the
words they hold.

%package -n plugin-qualification-db-schema
Summary: DDL of the OpenMixer qualification store
BuildArch: noarch

%description -n plugin-qualification-db-schema
The SQL that creates the qualification store, one copy, at
/usr/share/plugin-qualification-db/qualification.sql. The writer creates a user
layer from it, and test fixtures read it with no checkout.

%package -n plugin-qualification-db-write
Summary: Writer of the OpenMixer qualification store's user and system layers
BuildArch: noarch
Requires: python3
Requires: python3-jsonschema
Requires: sqlite-libs >= 3.37.0
Requires: plugin-qualification-db-schema = %{version}-%{release}

%description -n plugin-qualification-db-write
plugin-qualification-db-write put reads one qualification record on standard
input and replaces the record of its key in the layer of the scope; delete
removes one. Every word is checked against the installed contract domains and
the binary's path, file list and key against the rules of the store; a refusal
is named on standard error and writes nothing.

%prep
%autosetup

%build
# the records are data; the reader is built with its Makefile
%make_build PREFIX=%{_prefix} LIBDIR=%{_libdir} all

%install
# the sets of this architecture's classes, byte for byte, and a %%files line per class
python3 tools/sets.py install rpm %{_target_cpu} %{buildroot}%{qual_dir}
for class in $(ls %{buildroot}%{qual_dir}); do
    echo "%{qual_dir}/$class/"
done > records.files
# the base database of the same sets, beside them: its words are checked against the contract directory's domains
# (the contract packages of BuildRequires) and its commit is BUILT_FROM's (git archive substituted it)
classes=$(python3 tools/sets.py list rpm %{_target_cpu} | cut -d' ' -f1 | sort -u | sed 's/^/--class /')
python3 tools/records-db.py --records records $classes --contract-dir "$(pkg-config --variable=contractdir libomx-domain)" \
    --built-from-file BUILT_FROM --out %{buildroot}%{qual_dir}/qualification.sqlite
echo "%{qual_dir}/qualification.sqlite" >> records.files
%make_install PREFIX=%{_prefix} LIBDIR=%{_libdir}

%check
test -s %{buildroot}%{qual_dir}/qualification.sqlite
make PREFIX=%{_prefix} LIBDIR=%{_libdir} check
for dir in %{buildroot}%{qual_dir}/*/*/; do
    set=$(basename "$dir")
    class=$(basename "$(dirname "$dir")")
    python3 tools/check-records.py "$dir"
    # the package installs every file of the set, byte for byte
    (cd records/$class/$set && sha256sum *) | sort -k2 > in-tree.sha256
    (cd "$dir" && sha256sum *) | sort -k2 > installed.sha256
    cmp in-tree.sha256 installed.sha256
done

%files -f records.files
%license LICENSE
%dir %{_datadir}/omx
%dir %{qual_dir}

%files -n libplugin-qualification-db
%license LICENSE
%{_libdir}/libplugin-qualification-db.so.0

%files -n libplugin-qualification-db-devel
%{_includedir}/plugin-qualification-db/
%{_libdir}/libplugin-qualification-db.so
%{_libdir}/pkgconfig/plugin-qualification-db.pc

%files -n plugin-qualification-db
%license LICENSE
%{_bindir}/plugin-qualification-db
%{_mandir}/man1/plugin-qualification-db.1*

%files -n plugin-qualification-db-schema
%license LICENSE
%dir %{_datadir}/plugin-qualification-db
%{_datadir}/plugin-qualification-db/qualification.sql
%{_datadir}/plugin-qualification-db/migrations/

%files -n plugin-qualification-db-write
%license LICENSE
%{_bindir}/plugin-qualification-db-write
%dir %{_datadir}/plugin-qualification-db
%{_datadir}/plugin-qualification-db/qualification_db.py
%{_mandir}/man1/plugin-qualification-db-write.1*

%changelog
* Fri Nov 27 2026 Pau Aliagas <linuxnow@gmail.com> - 0.1.2-2026112702
- The writer takes a reason param's word from QUALIFICATION_MEASUREMENT_
  UNMEASURED_REASONS too: plugin-qualify 0.21.3 writes the memory reason it
  could not measure with unmeasuredReason, which the writer refused.
- The store is user_version 2: the DDL changed after the dated release at
  the same number. A user layer at 1 is migrated in place by the writer and
  the reader on open (schema/migrations/1-to-2.sql), a backup beside it.
- The hosting exception has ended: omx-clap ships its hosting domain, so the
  reader opens it and checks the hosting columns as every other.

* Fri Nov 27 2026 Pau Aliagas <linuxnow@gmail.com> - 0.1.1-2026112701
- The amd64 Debian package joins packaging/release-arches: the full matrix
  serves every package in every cell (owner ruling 2026-11-26), and plugin-
  hostd's amd64 cells build against libplugin-qualification-db-dev.

