# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# The RPM side of the records: one binary package per Fedora record set under records/x86-64/<set>/. A set is per
# machine class, per sample rate and per quantum: a run that measured several cells gives one set per cell, named
# <set>-<rate>-<quantum> (fedora44-48000-512), packaged as plugin-db-qualification-x86-64-<set name>. The Debian sets
# are built from debian/. The version is the dated one the tag and debian/changelog carry (vYYYYMMDDXX).
#
# The sets are the one list in %%global sets below. Every per-set section (%%package, %%description, %%files) is
# generated from it by the two %%{lua:} blocks, and %%install and %%check loop over it. It is a list, not a look into
# records/, because the spec is read before %%prep unpacks the tree. tools/build-package.sh keeps it: a set it builds
# is added, and no other is removed. tools/sets.py check (the check workflow) holds it equal to the x86-64 sets the
# tree holds. An empty list (%%{nil}) builds no package, and the release then skips the RPM.

%global host_class x86-64
%global sets %{nil}
%global qual_dir %{_datadir}/omx/qualification/%{host_class}
# the plugin-qualify that measured the sets, up to its next minor
%global qualify_requires (plugin-qualify >= 0.19.0 with plugin-qualify < 0.20)

Name: plugin-db-qualification
Version: 2026110602
Release: 1%{?dist}
Summary: The qualification layer of plugin-db: records of OpenMixer plugin sets
License: GPL-3.0-or-later
URL: https://github.com/FreeMixer/plugin-db-qualification
Source0: %{url}/archive/v%{version}/%{name}-%{version}.tar.gz
BuildArch: noarch

# the record check in %%check
BuildRequires: python3

%description
The qualification layer of the plugin database: the plugin-qualify records of
plugin sets measured on a reference machine of a host class, packaged so that
plugin-qualify-sync on a machine of the same class takes a plugin from them
instead of measuring it.

%{lua:
-- a %package and its %description per set; a set named <set>-<rate>-<quantum> says its cell
local class = rpm.expand("%{host_class}")
for set in string.gmatch(rpm.expand("%{sets}"), "%S+") do
  local base, rate, quantum = string.match(set, "^(.-)%-(%d+)%-(%d+)$")
  local cell = ""
  if base then cell = " at " .. rate .. "/" .. quantum else base = set end
  local pkg = "plugin-db-qualification-" .. class .. "-" .. set
  print("%package -n " .. pkg .. "\n")
  print("Summary: Qualification records of the " .. base .. " plugin set for " .. class .. cell .. "\n")
  print("Requires: " .. rpm.expand("%{qualify_requires}") .. "\n\n")
  print("%description -n " .. pkg .. "\n")
  print("The plugin-qualify records of the " .. base .. " plugin set (the OpenMixer worker\n")
  print("image's plugins on Fedora 44), measured on a " .. class .. " machine")
  if rate then print("\nat " .. rate .. " Hz and a quantum of " .. quantum .. " frames") end
  print(". plugin-qualify-sync\n")
  print("takes a plugin from them instead of measuring it, and only when every file\n")
  print("of the installed plugin hashes as the measured one did; any other plugin is\n")
  print("measured on the machine as before. An x86_64 machine has no device tree to\n")
  print("name its class: the sync reads these records once /etc/omx/qualify.conf says\n")
  print("\"host_class " .. class .. "\", and finds the CLAP plugins of /usr/lib64/clap once\n")
  print("it says \"clap_extra /usr/lib64/clap\".\n\n")
end
}

%prep
%autosetup

%build
# the records are data: nothing to build

%install
for set in %{sets}; do
    mkdir -p %{buildroot}%{qual_dir}/$set
    cp -p records/%{host_class}/$set/* %{buildroot}%{qual_dir}/$set/
done

%check
for set in %{sets}; do
    python3 tools/check-records.py %{buildroot}%{qual_dir}/$set
    # the package installs every file of the set, byte for byte
    (cd records/%{host_class}/$set && sha256sum *) | sort -k2 > in-tree.sha256
    (cd %{buildroot}%{qual_dir}/$set && sha256sum *) | sort -k2 > installed.sha256
    cmp in-tree.sha256 installed.sha256
done

%{lua:
-- a %files per set
local class = rpm.expand("%{host_class}")
local share = rpm.expand("%{_datadir}")
local qual = rpm.expand("%{qual_dir}")
for set in string.gmatch(rpm.expand("%{sets}"), "%S+") do
  print("%files -n plugin-db-qualification-" .. class .. "-" .. set .. "\n")
  print("%license LICENSE\n")
  print("%dir " .. share .. "/omx\n")
  print("%dir " .. share .. "/omx/qualification\n")
  print("%dir " .. qual .. "\n")
  print(qual .. "/" .. set .. "/\n\n")
end
}

%changelog
