#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# The records package proven where it is used: installed once, then for every set it carries, plugin-qualify-sync
# --system with that set's class (and, for a set of one cell, that cell as its grid) takes plugins from that set's
# records and measures none of them; the sync's state is cleared between sets. tools/sets.py prove runs the three
# steps for the package of the machine's architecture; the release runs that in a Debian trixie arm64 container
# (deb) and a Fedora 45 x86_64 container (rpm), with plugin-qualify from the channel; every set of the machine's host class (the class packaging/arch-classes gives its architecture) is proven, whatever the
# image it was measured on is called; a set of another class is named and reported as not proven.
#
#   tools/prove-set.sh install deb|rpm <pkg dir> <arch>    the one package of <arch> from the build artifact
#   tools/prove-set.sh set deb|rpm <class> <set> <rate/quantum or ->
#   tools/prove-set.sh remove deb|rpm
#
# deb: the package from <pkg dir>/trixie/, with Debian's own lv2vocoder, whose bytes are the ones the Zynthian image
#      holds (if Debian rebuilds it this fails with "binary differs": pick another plugin whose installed files still
#      hash as a record's).
# rpm: the package from <pkg dir>/; each set installs the channel's omx-plugins at the version it measured (its
#      provenance.json), removed again after it; when the channel's omx-plugins of that version is rebuilt with other
#      bytes this fails with "binary differs", and that is reported; the set stays, as qualification results are stable. python3 must be installed.
# A container has no device tree, so the host class is the settings file's. No plugin-hostd listens. PROVE_ROOT
# prefixes every system path (the tests).
set -euo pipefail

pkg=plugin-qualification-records
step=$1 kind=$2
r=${PROVE_ROOT:-}

clear_state() {
    rm -rf "$r/var/lib/omx/qualification" "$r/var/lib/omx/qualify-sync.json" "$r/var/lib/omx/qualified.pins" "$r/etc/omx/qualify.conf" "$r/etc/omx/plugin-hostd.conf"
}

case $kind in deb|rpm) ;; *) echo "deb or rpm, not $kind" >&2; exit 2 ;; esac

case $step in
    install)
        pkgs=$3 arch=$4
        case $kind in
            deb)
                chmod -R a+rX "$pkgs"
                apt-get install -y --no-install-recommends "./$pkgs/trixie/${pkg}_"*"_$arch.deb" lv2vocoder
                have=$(dpkg-query -W -f '${Version}' plugin-qualify)
                ;;
            rpm)
                dnf install -y --setopt=install_weak_deps=False "./$pkgs/$pkg-"[0-9]*".$arch.rpm"
                have=$(rpm -q --qf '%{VERSION}' plugin-qualify)
                ;;
        esac
        echo "$pkg ($arch): plugin-qualify $have"
        ;;
    set)
        class=$3 set_=$4 cell=${5:--}
        installed=$r/usr/share/omx/qualification/$class/$set_
        tree=records/$class/$set_
        # the next set starts from nothing, whether this one passed or not: no record the sync copied from this one
        trap 'clear_state; [ "$kind" = rpm ] && { dnf remove -y omx-plugins-clap omx-plugins-lv2 >/dev/null 2>&1 || true; }' EXIT
        clear_state
        case $kind in
            deb) hostd='' ;; # no extra folder: plugin-hostd's own LV2 list holds the standard ones
            rpm)
                ver=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["packages"]["omx-plugins-clap"].split(":")[-1].rsplit("-",1)[0])' "$tree/provenance.json")
                dnf install -y --setopt=install_weak_deps=False "omx-plugins-clap-$ver" "omx-plugins-lv2-$ver"
                rpm -q omx-plugins-clap omx-plugins-lv2
                hostd='clap_path /usr/lib64/clap' # plugin-hostd has no clap_extra
                ;;
        esac
        test -f "$installed/provenance.json"
        n=$(find "$installed" -maxdepth 1 -name '*.qualification.json' | wc -l)
        want=$(find "$tree" -maxdepth 1 -name '*.qualification.json' | wc -l)
        echo "$class/$set_: $n records installed, the tree holds $want"
        [ "$n" -eq "$want" ] || { echo "::error::$class/$set_: $n records installed, records/$class/$set_ holds $want"; exit 1; }

        mkdir -p "$r/etc/omx"
        # the folders scanned are plugin-hostd's (plugin-qualify 0.20.7 refuses lv2_path, lv2_extra, clap_path, clap_extra in qualify.conf)
        printf '%s' "${hostd:+$hostd$'\n'}" > "$r/etc/omx/plugin-hostd.conf"
        {
            printf 'host_class %s\nhostd_conf %s\nhostd_port 0\n' "$class" "$r/etc/omx/plugin-hostd.conf"
            [ "$cell" = - ] || printf 'grid %s\n' "$cell"
        } > "$r/etc/omx/qualify.conf"
        log=$(mktemp)
        plugin-qualify-sync --system 2>&1 | tee "$log"
        # every plugin taken comes from this set: the class's other sets are installed beside it
        applied=$(grep -c "distributed: .*: applied ($set_)\$" "$log" || true)
        other=$(grep 'distributed: .*: applied (' "$log" | grep -vc "applied ($set_)\$" || true)
        echo "$class/$set_: applied $applied, from another set $other"
        [ "$applied" -gt 0 ] || { echo "::error::$class/$set_: no plugin was taken from its records"; exit 1; }
        [ "$other" -eq 0 ] || { echo "::error::$class/$set_: the sync took plugins from another set"; exit 1; }
        if grep -E 'distributed: .*(binary differs|not applied|measured here)' "$log"; then
            echo "::error::$class/$set_: a plugin of the set was measured instead of taken from the records"; exit 1
        fi
        rm -f "$log"
        ;;
    remove)
        case $kind in
            deb) apt-get remove -y "$pkg" >/dev/null 2>&1 || true ;;
            rpm) dnf remove -y "$pkg" >/dev/null 2>&1 || true ;;
        esac
        clear_state
        ;;
    *) echo "install, set or remove, not $step" >&2; exit 2 ;;
esac
