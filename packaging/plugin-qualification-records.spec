# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# The RPM side of the records: one package, plugin-qualification-records, per architecture, the same package the
# Debian side builds from debian/. It carries every set of the machine classes packaging/arch-classes gives its
# architecture, at /usr/share/omx/qualification/<class>/<set>/; plugin-qualify-sync chooses the set of the machine's
# class and cell. A set is per machine class, per sample rate and per quantum (fedora44-48000-512). The version is the
# dated one the tag and debian/changelog carry (vYYYYMMDDXX).
#
# x86_64 carries the x86-64 class (the fedora44 sets). There is no aarch64 build: no Fedora machine of an arm64
# class (rpi5) is measured, so ExclusiveArch names x86_64 alone.
#
# The block between BEGIN and END per-architecture is written by tools/sets.py spec: each architecture's
# plugin-qualify range (packaging/arch-classes) and the older package names it takes over (one package per set, the
# names derived from records/), and tools/sets.py check holds it to them. The spec is read before %%prep unpacks the
# tree, so that part is written here; %%install and %%files read the tree.

%global debug_package %{nil}
%global qual_dir %{_datadir}/omx/qualification

Name: plugin-qualification-records
Version: 2026110901
Release: 1%{?dist}
Summary: The qualification layer of plugin-db: records of OpenMixer plugin sets
License: GPL-3.0-or-later
URL: https://github.com/FreeMixer/plugin-db-qualification
Source0: %{name}-%{version}.tar.gz
ExclusiveArch: x86_64

# tools/sets.py in %%install and the record check in %%check
BuildRequires: python3

# BEGIN per-architecture: written by tools/sets.py spec from packaging/arch-classes and records/
%ifarch x86_64
Requires: (plugin-qualify >= 0.20.1 with plugin-qualify < 0.21)
Provides: omx-qualification-x86-64-fedora44 = %{version}-%{release}
Obsoletes: omx-qualification-x86-64-fedora44 < %{version}-%{release}
Provides: plugin-db-qualification-x86-64-fedora44 = %{version}-%{release}
Obsoletes: plugin-db-qualification-x86-64-fedora44 < %{version}-%{release}
Provides: plugin-db-qualification-x86-64-fedora44-192000-256 = %{version}-%{release}
Obsoletes: plugin-db-qualification-x86-64-fedora44-192000-256 < %{version}-%{release}
Provides: plugin-db-qualification-x86-64-fedora44-192000-512 = %{version}-%{release}
Obsoletes: plugin-db-qualification-x86-64-fedora44-192000-512 < %{version}-%{release}
Provides: plugin-db-qualification-x86-64-fedora44-48000-128 = %{version}-%{release}
Obsoletes: plugin-db-qualification-x86-64-fedora44-48000-128 < %{version}-%{release}
Provides: plugin-db-qualification-x86-64-fedora44-48000-256 = %{version}-%{release}
Obsoletes: plugin-db-qualification-x86-64-fedora44-48000-256 < %{version}-%{release}
Provides: plugin-db-qualification-x86-64-fedora44-48000-512 = %{version}-%{release}
Obsoletes: plugin-db-qualification-x86-64-fedora44-48000-512 < %{version}-%{release}
Provides: plugin-db-qualification-x86-64-fedora44-48000-64 = %{version}-%{release}
Obsoletes: plugin-db-qualification-x86-64-fedora44-48000-64 < %{version}-%{release}
Provides: plugin-db-qualification-x86-64-fedora44-96000-128 = %{version}-%{release}
Obsoletes: plugin-db-qualification-x86-64-fedora44-96000-128 < %{version}-%{release}
Provides: plugin-db-qualification-x86-64-fedora44-96000-256 = %{version}-%{release}
Obsoletes: plugin-db-qualification-x86-64-fedora44-96000-256 < %{version}-%{release}
Provides: plugin-db-qualification-x86-64-fedora44-96000-512 = %{version}-%{release}
Obsoletes: plugin-db-qualification-x86-64-fedora44-96000-512 < %{version}-%{release}
Provides: plugin-db-qualification-x86-64-fedora44-96000-64 = %{version}-%{release}
Obsoletes: plugin-db-qualification-x86-64-fedora44-96000-64 < %{version}-%{release}
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

%prep
%autosetup

%build
# the records are data: nothing to build

%install
# the sets of this architecture's classes, byte for byte, and a %%files line per class
python3 tools/sets.py install rpm %{_target_cpu} %{buildroot}%{qual_dir}
for class in $(ls %{buildroot}%{qual_dir}); do
    echo "%{qual_dir}/$class/"
done > records.files

%check
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

%changelog
