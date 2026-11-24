# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# The RPM side of the records: one package, plugin-qualification-records, per architecture, the same package the
# Debian side builds from debian/. It carries every set of the machine classes packaging/arch-classes gives its
# architecture, at /usr/share/omx/qualification/<class>/<set>/; plugin-qualify-sync chooses the set of the machine's
# class and cell. A set is per machine class, per sample rate and per quantum (fedora44-48000-512). The version is the
# dated one the tag and debian/changelog carry (vYYYYMMDDXX).
#
# x86_64 carries the x86-64 class (the fedora44 sets). aarch64 carries the rpi5 class, the same sets the arm64 deb
# carries: a package that depends on the records installs on Fedora aarch64 too, and a record applies only where the
# installed plugin's bytes are the measured ones.
#
# The block between BEGIN and END per-architecture is written by tools/sets.py spec: each architecture's
# plugin-qualify floor (packaging/arch-classes) and the older package names it takes over (one package per set, the
# names derived from records/), and tools/sets.py check holds it to them. The spec is read before %%prep unpacks the
# tree, so that part is written here; %%install and %%files read the tree.

%global debug_package %{nil}
%global qual_dir %{_datadir}/omx/qualification

Name: plugin-qualification-records
Version: 2026112401
Release: 1%{?dist}
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
BuildRequires: libomx-domain-devel >= 3.20.0
# tools/records-db.py: the base database, its words checked against the owners' domains at the releases that publish them
BuildRequires: python3-jsonschema
BuildRequires: plugin-qualify-contract >= 0.20.7
BuildRequires: plugin-hostd-contract >= 0.20.8
BuildRequires: plugin-db-contract >= 0.4.7
BuildRequires: omx-clap-contract >= 0.34.0

# BEGIN per-architecture: written by tools/sets.py spec from packaging/arch-classes and records/
%ifarch x86_64
Requires: plugin-qualify >= 0.20.7
%endif
%ifarch aarch64
Requires: plugin-qualify >= 0.20.7
%endif
# END per-architecture

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
Requires: libomx-domain >= 3.20.0

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
Requires: libomx-domain-devel >= 3.20.0

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

%files -n plugin-qualification-db-write
%license LICENSE
%{_bindir}/plugin-qualification-db-write
%dir %{_datadir}/plugin-qualification-db
%{_datadir}/plugin-qualification-db/qualification_db.py
%{_mandir}/man1/plugin-qualification-db-write.1*

%changelog
