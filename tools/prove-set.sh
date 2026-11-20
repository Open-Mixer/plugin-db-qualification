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
#   tools/prove-set.sh set deb|rpm <class> <set> <rate/quantum or -> <winner>
#
# <winner> is the set the store's claim rule gives that cell: of the class's sets that hold it, the one settled on by
# tier, then date (tools/sets.py expected_winner, which calls tools/records-db.py's rule). plugin-qualify 0.20.7 does
# not apply that rule: it takes the first set by name that holds the cell (fixed in plugin-qualify#152, 0.20.8). The
# proof records what the sync took, and does not require the winner:
#   - the sync took a set other than the winner: a WRONG WINNER, named (appended to $PROVE_NOTES as "wrong|<text>");
#   - the sync never took this set: the set is UNPROVEN, named ("unproven-set|<text>"), exit 3;
#   - the sync took the winner: noted ("pick|<text>"). Every run notes the set the sync picked per cell.
# A sync that takes nothing, and every other refusal, fails.
#   tools/prove-set.sh remove deb|rpm
#
# deb: the package from <pkg dir>/trixie/, with Debian's own lv2vocoder, whose bytes are the ones the Zynthian image
#      holds (if Debian rebuilds it this fails with "binary differs": pick another plugin whose installed files still
#      hash as a record's).
# rpm: the package from <pkg dir>/; each set installs the channel's current omx-plugins (the channel keeps the newest
#      only), removed again after it, and logs the omx-plugins version the set measured (its provenance.json) beside
#      the one installed. A record the sync reports "binary differs" for, where the installed version differs from the
#      measured one, is UNPROVEN: the bytes the record names are no longer published, and the record stays as measured.
#      It is named (a line "UNPROVEN record ..." and a note "unproven-record|<text>" for the release notes), not
#      failed; a set none of whose plugins applied for that reason is UNPROVEN too (exit 3). A "binary differs" at the
#      same version, and every other refusal, still fails. python3 must be installed.
# A container has no device tree, so the host class is the settings file's. No plugin-hostd listens. PROVE_ROOT
# prefixes every system path (the tests).
set -euo pipefail

pkg=plugin-qualification-records
step=$1 kind=$2
r=${PROVE_ROOT:-}

# a line of what the proof found, for the release notes (PROVE_NOTES names the file; the proof's caller reads it)
note() {
    [ -z "${PROVE_NOTES:-}" ] || printf '%s|%s\n' "$1" "$2" >> "$PROVE_NOTES"
}

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
        class=$3 set_=$4 cell=${5:--} winner=${6:?the expected winner set}
        installed=$r/usr/share/omx/qualification/$class/$set_
        tree=records/$class/$set_
        # the next set starts from nothing, whether this one passed or not: no record the sync copied from this one
        trap 'clear_state; [ "$kind" = rpm ] && { dnf remove -y omx-plugins-clap omx-plugins-lv2 >/dev/null 2>&1 || true; }' EXIT
        clear_state
        case $kind in
            deb) hostd='' ;; # no extra folder: plugin-hostd's own LV2 list holds the standard ones
            rpm)
                measured=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["packages"]["omx-plugins-clap"].split(":")[-1])' "$tree/provenance.json")
                dnf install -y --setopt=install_weak_deps=False omx-plugins-clap omx-plugins-lv2
                rpm -q omx-plugins-clap omx-plugins-lv2
                have_omx=$(rpm -q --qf '%{VERSION}-%{RELEASE}' omx-plugins-clap)
                echo "$class/$set_: omx-plugins measured $measured, installed $have_omx"
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
        # the sets the sync took plugins from
        taken=$(sed -n 's/.*distributed: .*: applied (\(.*\))$/\1/p' "$log" | sort -u | paste -sd,)
        applied=$(grep -c 'distributed: .*: applied (' "$log" || true)
        echo "$class/$set_: applied $applied from $taken; the store's rule gives the cell to $winner"
        # a record of other bytes: UNPROVEN when the omx-plugins installed is another version than the one measured
        # (rpm only: those bytes are no longer published), a failure at the same version or for a deb
        unproven=0
        if grep -q 'distributed: .*: binary differs' "$log"; then
            if [ "$kind" = rpm ] && [ "${have_omx%-*}" != "${measured%-*}" ]; then
                while IFS= read -r uri; do
                    echo "UNPROVEN record $class/$set_: $uri: binary differs (omx-plugins measured $measured, installed $have_omx)"
                    note unproven-record "$class/$set_: $uri (omx-plugins measured $measured, the channel serves $have_omx)"
                    unproven=$((unproven + 1))
                done < <(sed -n 's/.*distributed: \(.*\): binary differs.*/\1/p' "$log" | sort -u)
            else
                grep 'distributed: .*: binary differs' "$log"
                echo "::error::$class/$set_: a plugin of the set was measured instead of taken from the records"; exit 1
            fi
        fi
        if [ "$applied" -eq 0 ]; then
            [ "$unproven" -gt 0 ] || { echo "::error::$class/$set_: no plugin was taken from its records"; exit 1; }
            note unproven-set "$class/$set_: every record is of omx-plugins bytes the channel no longer serves (measured $measured, the channel serves $have_omx)"
            echo "UNPROVEN $class/$set_: every record is of bytes the channel no longer serves"
            rm -f "$log"; exit 3
        fi
        where=$class
        [ "$cell" = - ] && where="$class, the cells of $set_" || where="$class $cell"
        if [ "$taken" = "$winner" ]; then
            note pick "$where: plugin-qualify takes $taken, the store's rule's winner"
        else
            echo "WRONG WINNER $where: the sync takes $taken, the store's rule gives the cell to $winner"
            note wrong "$where: plugin-qualify takes $taken; the store's rule's winner is $winner"
        fi
        case ",$taken," in
            *",$set_,"*) ;;
            *) echo "UNPROVEN $class/$set_: the sync never took it ($taken)"
               note unproven-set "$class/$set_: never taken by the sync at its cell ($where: it takes $taken)"
               unproven_set=1 ;;
        esac
        if grep -E 'distributed: .*(not applied|measured here)' "$log"; then
            echo "::error::$class/$set_: a plugin of the set was measured instead of taken from the records"; exit 1
        fi
        rm -f "$log"
        [ -z "${unproven_set:-}" ] || exit 3
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
