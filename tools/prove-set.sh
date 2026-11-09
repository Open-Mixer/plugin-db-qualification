#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# One set's package proven where it is used: installed alone, plugin-qualify-sync --system takes plugins from its
# records and measures none of the set's, then the package and the sync's state are removed so the next set starts
# clean. tools/sets.py prove runs it for every set of a release; the release runs that in a Debian trixie arm64
# container (deb) and a Fedora 44 x86_64 container (rpm), with plugin-qualify from the channel.
#
#   tools/prove-set.sh deb|rpm <pkg dir> <package> <host class> <set> <rate/quantum or ->
#
# deb: the package from <pkg dir>/trixie/, with Debian's own lv2vocoder, whose bytes are the ones the Zynthian image
#      holds (if Debian rebuilds it this fails with "binary differs": pick another plugin whose installed files still
#      hash as a record's).
# rpm: the package from <pkg dir>/, with the channel's omx-plugins at the version the set measured (its
#      provenance.json); when the channel's omx-plugins of that version is rebuilt with other bytes this fails with
#      "binary differs", and the set is due to be measured again. python3 must be installed.
# A container has no device tree, so the host class is the settings file's; a set of one cell sets the sync's grid
# to that cell. No plugin-hostd listens. PROVE_ROOT prefixes every system path (the tests).
set -euo pipefail

kind=$1 pkgs=$2 pkg=$3 class=$4 set_=$5 cell=${6:--}
r=${PROVE_ROOT:-}
installed=$r/usr/share/omx/qualification/$class/$set_
tree=records/$class/$set_

# the next set starts from nothing, whether this one passed or not: no package of this one, no record the sync
# copied from it
cleanup() {
    case $kind in
        deb) apt-get remove -y "$pkg" >/dev/null 2>&1 || true ;;
        rpm) dnf remove -y "$pkg" >/dev/null 2>&1 || true ;;
    esac
    rm -rf "$r/var/lib/omx/qualification" "$r/var/lib/omx/qualify-sync.json" "$r/var/lib/omx/qualified.pins" "$r/etc/omx/qualify.conf"
}
trap cleanup EXIT

case $kind in
    deb)
        chmod -R a+rX "$pkgs"
        apt-get install -y --no-install-recommends "./$pkgs/trixie/${pkg}_"*_all.deb lv2vocoder
        have=$(dpkg-query -W -f '${Version}' plugin-qualify)
        dpkg --compare-versions "$have" ge 0.19.0
        conf='lv2_extra'
        ;;
    rpm)
        ver=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["packages"]["omx-plugins-clap"].split(":")[-1].rsplit("-",1)[0])' "$tree/provenance.json")
        dnf install -y --setopt=install_weak_deps=False "./$pkgs/$pkg-"[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-*.noarch.rpm "omx-plugins-clap-$ver" "omx-plugins-lv2-$ver"
        rpm -q plugin-qualify omx-plugins-clap omx-plugins-lv2
        have=$(rpm -q --qf '%{VERSION}' plugin-qualify)
        conf='clap_extra /usr/lib64/clap'
        ;;
    *) echo "deb or rpm, not $kind" >&2; exit 2 ;;
esac
echo "$pkg: plugin-qualify $have"
test -f "$installed/provenance.json"
n=$(find "$installed" -maxdepth 1 -name '*.qualification.json' | wc -l)
want=$(find "$tree" -maxdepth 1 -name '*.qualification.json' | wc -l)
echo "$pkg: $n records installed, the tree holds $want"
[ "$n" -eq "$want" ] || { echo "::error::$pkg installs $n records, records/$class/$set_ holds $want"; exit 1; }

mkdir -p "$r/etc/omx"
{
    printf 'host_class %s\n%s\nhostd_port 0\n' "$class" "$conf"
    [ "$cell" = - ] || printf 'grid %s\n' "$cell"
} > "$r/etc/omx/qualify.conf"
log=$(mktemp)
plugin-qualify-sync --system 2>&1 | tee "$log"
applied=$(grep -c 'distributed: .*: applied' "$log" || true)
echo "$pkg: applied $applied"
[ "$applied" -gt 0 ] || { echo "::error::$pkg: no plugin was taken from the records"; exit 1; }
if grep -E 'distributed: .*(binary differs|not applied|measured here)' "$log"; then
    echo "::error::$pkg: a plugin of the set was measured instead of taken from the records"; exit 1
fi
rm -f "$log"
