#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# The run behind records/x86-64/fedora44: in a fedora:44 container (job.yaml, a Job in the cluster's omx-worker
# namespace), the OpenMixer channel's plugin-qualify, plugin-hostd and omx-clap-host, the worker image's plugin set
# (platform k8s/omx-worker/images/openmixer/baked-versions.yml: omx-plugins clap and lv2, rpms lv2-plugins and
# clap-plugins, handed over as PLUGINS), and plugin-qualify-sync --system against a dummy-driver JACK server of the
# pod's own, once per base.
#
# What it measures, in what order. BASES are the cells (rate/quantum) it measures, each with its own settings, state
# and JACK server: the Zynthian cell 48000/512 and the console's 96000/256. The stages are two: INCLUDED (the omx
# effects and the instruments the console ships, installed alone and measured first) and then the rest of PLUGINS.
# Stage by stage, base by base, so a run cut short already holds the plugins that matter at both bases.
#
# What it keeps and delivers. State lives on the node-cache volume (CACHE, /cache/omx-qualify/<SET>), one directory per
# base: plugin-qualify-sync's own state file stamps every plugin it finished, so a Job started again with the same SET
# continues where the last one stopped, and a finished stage leaves a stamp that skips it. After every stage and base
# the records are committed to the branch records/fedora44/<SET> of the repository (the deploy key in /keys), under
# <SET>/<base>/qualification, with the run's package list, versions and log tail under <SET>/meta. A Job that cannot
# push, or that measured no record, ends red: complete means delivered. The records on the branch go to
# tools/build-package.sh --from.
#
#   SET (the set's name)   BASES "48000/512 96000/256"   INCLUDED (packages)   PLUGINS (packages)   HOST_CLASS x86-64
#   MEMORY_LIMIT 6G   REPO (ssh url)   DRY (a number: measure only that many plugins of the included stage, and push
#   to records/fedora44/dry-<SET>)
set -uo pipefail
: "${SET:?}" "${BASES:?}" "${REPO:?}"
out=/out; mkdir -p $out; exec > >(tee -a $out/job.log) 2>&1
cache=${CACHE:-/cache/omx-qualify}/$SET; mkdir -p "$cache" /work
BRANCH=records/fedora44/$SET; [ -n "${DRY:-}" ] && BRANCH=records/fedora44/dry-$SET
echo "start $(date -u +%FT%TZ) on $NODE_NAME set $SET bases $BASES branch $BRANCH"
set -e
dnf -y -q install https://www.openmixer.org/rpm/openmixer-release.noarch.rpm
gpg --show-keys --with-subkey-fingerprints /etc/pki/rpm-gpg/RPM-GPG-KEY-openmixer | grep -qi 6AF1C62F
rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-openmixer
cat > /etc/yum.repos.d/copr-audinux.repo <<R
[copr-ycollet-audinux]
name=audinux
baseurl=https://download.copr.fedorainfracloud.org/results/ycollet/audinux/fedora-\$releasever-\$basearch/
gpgkey=https://download.copr.fedorainfracloud.org/results/ycollet/audinux/pubkey.gpg
gpgcheck=1
repo_gpgcheck=0
enabled=1
# the channel's mod-host build (11.3.omx, socket_set_bind_address) is the one plugin-hostd links; the COPR's sorts above it
exclude=mod-host mod-host-protocol mod-host-protocol-devel
R
# pipewire's libjack replaces jackd's libjackserver through ld.so.conf, and every jackd (the pod's and the sync's
# private ones) then refuses the dummy driver ("not a master"): every adapter run fails with ERR_JACK_CLIENT_CREATION
echo 'excludepkgs=pipewire-jack-audio-connection-kit*' >> /etc/dnf/dnf.conf
dnf -y -q makecache
dnf -y install plugin-qualify omx-clap-host plugin-hostd jack-audio-connection-kit lilv-devel util-linux procps-ng tar xz \
  mod-host mod-host-protocol git openssh-clients curl omx-plugins-clap omx-plugins-lv2 ${INCLUDED:-}
bash /script/channel-check.sh || exit 1
plugin-hostd --version
! rpm -q pipewire-jack-audio-connection-kit-libs
python3 -c 'import lilv; print("lilv", lilv.World)'
timeout 10 jackd -n omxprobe -d dummy -r 48000 -p 512 & sleep 3; JACK_DEFAULT_SERVER=omxprobe jack_wait -c || true; kill %1 2>/dev/null; wait
# GitHub's host keys from its own API, not trusted on first use
curl -fsS https://api.github.com/meta | python3 -c 'import json,sys; [print("github.com", k) for k in json.load(sys.stdin)["ssh_keys"]]' > /work/known_hosts
test -s /work/known_hosts
export GIT_SSH_COMMAND="ssh -i /keys/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=/work/known_hosts -o StrictHostKeyChecking=yes"
# the delivery has to work before hours are spent: a write the deploy key may not make fails here, not at the end
git ls-remote --heads "$REPO" >/dev/null
set +e

host_facts() {
  dnf repoquery --installed --qf '%{name} %{evr} %{from_repo}\n' | sort > $out/installed.txt
  # the packages that own a plugin directory's entries: the set's package list for provenance.json
  rpm -qf --qf '%{NAME}\t%{EPOCH}:%{VERSION}-%{RELEASE}\n' $(find /usr/lib/clap /usr/lib64/clap /usr/lib64/lv2 /usr/lib/lv2 -mindepth 1 -maxdepth 1 2>/dev/null) | sed 's/(none)://' | sort -u > $out/plugin-packages.tsv
  for p in $PLUGINS ${INCLUDED:-}; do rpm -q $p >/dev/null || echo "$p"; done > $out/not-installed.txt
  echo "not installed: $(wc -l < $out/not-installed.txt)"
  cat /etc/os-release > $out/os-release
  uname -a > $out/uname; lscpu > $out/lscpu; nproc >> $out/lscpu
  echo "ulimit -r $(ulimit -r) -l $(ulimit -l)" > $out/rt.txt
  chrt -f 10 true && echo "SCHED_FIFO: yes" >> $out/rt.txt || echo "SCHED_FIFO: refused" >> $out/rt.txt
  grep Cap /proc/self/status >> $out/rt.txt
  rpm -q plugin-qualify plugin-hostd omx-clap-host omx-clap-core mod-host-protocol omx-plugins-clap omx-plugins-lv2 jack-audio-connection-kit > $out/versions.txt; plugin-hostd --version >> $out/versions.txt 2>&1; omx-clap-host --version >> $out/versions.txt 2>&1
  cat $out/versions.txt
}

# Commit what the bases hold to the branch and push it. Returns 0 only when the push went through.
deliver() {
  local label=$1 d=/work/deliver b n
  rm -rf $d
  if git ls-remote --exit-code --heads "$REPO" "$BRANCH" >/dev/null 2>&1; then
    git clone -q --depth 1 -b "$BRANCH" "$REPO" $d || return 1
  else
    git init -q $d && git -C $d checkout -q --orphan "$BRANCH" && git -C $d remote add origin "$REPO" || return 1
  fi
  for b in $BASES; do
    n=b${b%/*}-${b#*/}
    [ -d $cache/$n/qualification ] || continue
    rm -rf "$d/$SET/$n"; mkdir -p "$d/$SET/$n"
    cp -a $cache/$n/qualification "$d/$SET/$n/qualification"
    cp $cache/$n/qualify-sync.json "$d/$SET/$n/" 2>/dev/null
  done
  mkdir -p $d/$SET/meta
  for f in installed.txt plugin-packages.tsv not-installed.txt os-release uname lscpu rt.txt versions.txt; do cp $out/$f $d/$SET/meta/ 2>/dev/null; done
  tail -n 3000 $out/job.log > $d/$SET/meta/job.log.tail
  git -C $d add -A
  if git -C $d diff --cached --quiet; then echo "deliver $label: nothing new"; return 0; fi
  GIT_AUTHOR_NAME="Pau Aliagas" GIT_AUTHOR_EMAIL=linuxnow@gmail.com GIT_COMMITTER_NAME="Pau Aliagas" GIT_COMMITTER_EMAIL=commits@openmixer.org \
    git -C $d commit -q -m "fedora44 $SET: records after $label" || return 1
  local t
  for t in 1 2 3 4; do
    git -C $d push -q origin "$BRANCH" && { echo "deliver $label: pushed $(git -C $d rev-parse --short HEAD) to $BRANCH"; return 0; }
    sleep $((t * ${PUSH_WAIT:-20}))
  done
  echo "deliver $label: PUSH FAILED; the records stay in $cache"
  return 1
}

# One base: its settings, its JACK server at its rate and period, and up to three passes of the sync.
measure_base() {
  local stage=$1 cell=$2 rate per n dir pass bad sup
  rate=${cell%/*}; per=${cell#*/}; n=b$rate-$per; dir=$cache/$n; mkdir -p $dir
  if [ -e $dir/stamp-$stage ]; then echo "stage $stage at $cell: stamped done, skipped"; return 0; fi
  mkdir -p /etc/omx
  cat > /etc/omx/qualify.conf <<C
host_class $HOST_CLASS
hostd_port 0
grid $cell
memory_limit $MEMORY_LIMIT
pin_file $dir/qualified.pins
qualification_dir $dir/qualification
descriptor_dir $dir/descriptors
state_file $dir/qualify-sync.json
$( if [ -n "${DRY:-}" ]; then echo "lv2_path /work/dry/lv2"; echo "clap_path /work/dry/clap"; else echo "clap_extra /usr/lib64/clap"; fi )
C
  # the JACK server a device runs: the admission under omx-clap-host adds each LV2 plugin as a client of the default
  # server. Private to this pod, dummy driver, the cell the grid measures; started again whenever it ends, since an
  # admission without a server answers ERR_JACK_CLIENT_CREATION for a plugin that never ran
  ( while :; do echo "jackd start $(date -u +%FT%T.%NZ)"; jackd -r -d dummy -r $rate -p $per; echo "jackd exit $? $(date -u +%FT%T.%NZ)"; sleep 1; done ) > $out/jackd-$n.log 2>&1 &
  sup=$!
  sleep 3
  # a plugin whose admission or isolated step found no JACK server (resp -201, isolated.no-host) is dropped from the
  # state and measured again by the next pass; what still fails after three passes stays as measured
  for pass in 1 2 3; do
    echo "stage $stage $cell pass $pass start $(date -u +%FT%TZ)"
    plugin-qualify-sync --system --no-distributed > $out/sync-$stage-$n-$pass.log 2>&1
    echo "pass $pass exit $?"
    tail -2 $out/sync-$stage-$n-$pass.log
    bad=$(python3 -I - "$dir/qualify-sync.json" "$out/redo-$stage-$n-$pass.txt" <<'P'
import json,sys
st=sys.argv[1]
try: d=json.load(open(st))
except Exception: print(0); sys.exit(0)
bad=[k for k,e in d['entries'].items() if any('resp-201' in str(p.get('code','')) or 'no-host' in str(p.get('code','')) for p in e.get('plugins',[]))]
for k in bad: del d['entries'][k]
json.dump(d,open(st,'w'))
open(sys.argv[2],'w').write(''.join(k+'\n' for k in bad))
print(len(bad))
P
)
    echo "pass $pass: $bad plugins to measure again"
    [ "$bad" -eq 0 ] && break
  done
  echo "jackd exits: $(grep -c 'jackd exit' $out/jackd-$n.log)"
  kill $sup; pkill -x jackd; sleep 1
  local recs; recs=$(ls $dir/qualification/*.qualification.json 2>/dev/null | wc -l)
  echo "stage $stage $cell: $recs records"
  [ "$recs" -gt 0 ] || { echo "stage $stage $cell measured no record"; return 1; }
  touch $dir/stamp-$stage
}

red=0
if [ -n "${DRY:-}" ]; then
  # two plugins only: links to the first DRY files of the omx effects, in directories of their own
  mkdir -p /work/dry/clap /work/dry/lv2
  for f in $(ls /usr/lib/clap/omx-*.clap | head -n "$DRY"); do ln -s $f /work/dry/clap/; done
  stages="included"
else
  stages="included rest"
fi
host_facts
for stage in $stages; do
  if [ "$stage" = rest ]; then
    dnf -y install --skip-unavailable --skip-broken $PLUGINS
    host_facts
  fi
  for cell in $BASES; do
    measure_base $stage $cell || red=1
    deliver "$stage $cell" || red=1
  done
done
echo "$(date -u +%FT%TZ) red=$red" > $out/done
if [ "$red" -ne 0 ]; then echo "NOT DELIVERED: the Job ends red"; exit 1; fi
echo "done; every stage delivered to $BRANCH"
