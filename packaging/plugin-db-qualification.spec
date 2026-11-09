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
%global sets fedora44-192000-256 fedora44-192000-512 fedora44-48000-128 fedora44-48000-256 fedora44-48000-512 fedora44-48000-64 fedora44-96000-128 fedora44-96000-256 fedora44-96000-512 fedora44-96000-64
%global qual_dir %{_datadir}/omx/qualification/%{host_class}
# the plugin-qualify that reads the sets by their cell, up to its next minor
%global qualify_requires (plugin-qualify >= 0.20.1 with plugin-qualify < 0.21)
# what kind of measurement the sets of this release are (tools/set-tier.py writes the same word into each set's
# provenance.json): reference (dummy JACK driver, real-time priority), provisional (dummy driver, no real-time
# priority: the verdicts hold, the figures are not reference figures) or hardware (the machine's own interface)
%global tier provisional

Name: plugin-db-qualification
Version: 2026110901
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
  print("Requires: " .. rpm.expand("%{qualify_requires}") .. "\n")
  print("Provides: plugin-qualification-records\n\n")
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
  local notes = {
    reference = "Reference records: measured in a container on JACK's dummy driver with real-time priority (SCHED_FIFO, memory locked). Every figure is a reference figure, comparable across machines.",
    provisional = "Provisional records: measured on JACK's dummy driver without real-time priority. The crash, hang and unmeasured verdicts hold; the cost, latency and xrun figures are not reference figures. A newer reference set, measured with real-time priority, supersedes this one.",
    hardware = "Hardware records: measured on the machine's own audio interface. The verdicts hold; the figures describe that interface and are not compared with the reference tier.",
  }
  local line = ""
  for word in string.gmatch(notes[rpm.expand("%{tier}")], "%S+") do
    if #line + #word + 1 > 76 then print(line .. "\n"); line = word
    elseif line == "" then line = word else line = line .. " " .. word end
  end
  print(line .. "\n\n")
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
