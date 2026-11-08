# plugin-db-qualification

The qualification layer of plugin-db: plugin-qualify's records of the plugin sets of each machine class, as Debian
and RPM packages.

plugin-db keeps the plugin database in layers; plugin-qualify writes this one, and plugin-hostd only hosts.
[plugin-qualify](https://github.com/FreeMixer/plugin-qualify) measures every LV2 and CLAP plugin of a machine before
the machine hosts it. A Raspberry Pi 5 takes hours to measure a full Zynthian image. A machine of the same class and
the same plugin set does not need to measure it again: this repository holds the records one such machine wrote, and
publishes them as `plugin-db-qualification-<host class>-<set>`, which `plugin-qualify-sync` reads before it measures
anything.

## What is offered

One current set per machine class, measured by the latest plugin-qualify, and packaged only for the architecture and
distribution that class runs. A set measured by an older plugin-qualify is dropped, not kept: the class ships nothing
until it is measured again.

| host class | machine | arch | distribution | package | records | plugin-qualify |
| --- | --- | --- | --- | --- | --- | --- |
| `rpi5` | Raspberry Pi 5 (ZynthianOS Vangelis) | arm64 | Debian trixie and bookworm | `plugin-db-qualification-rpi5-zynthian-vangelis` (deb) | 1863 | 0.19.0, with the adapter, isolated, pool and memory steps under 0.19.1 |
| `x86-64` | the OpenMixer worker image, and a desk | x86_64 | Fedora 44 | `plugin-db-qualification-x86-64-fedora44` (rpm) | 1109, at 96000/256 | 0.19.1 |

There is no Debian x86-64 class and no Fedora rpi5 class, so there is no `.deb` for x86-64 and no `.rpm` for rpi5.

plugin-qualify knows a class by the board's device tree (`rpi5` on a Raspberry Pi 5) or by `host_class` in
`/etc/omx/qualify.conf`; it does not tell machines apart by CPU or kernel. The worker image and a desk are both
`x86-64`. The class's set is the worker image's, because it is measured in the cluster from the channel's packages
and no live machine is touched; a desk that wants it sets `host_class x86-64`, and takes the records whose plugins it
has with the same bytes.

### How a class is measured again

| class | where | command | time |
| --- | --- | --- | --- |
| `rpi5` | a Raspberry Pi 5 with the ZynthianOS image, plugin-qualify from the channel | `plugin-qualify-sync --system --force --no-distributed --grid 48000/256,96000/256`, then the copy below | about 6 hours per rate (2026-10-28: 6 h at 48 kHz) |
| `x86-64` | the cluster, a Job (`tools/fedora44/job.yaml`, a fedora:44 pod on an AMD Ryzen 7 PRO 8700GE node) | `kubectl -n omx-worker create configmap omx-qualify-fedora44-script --from-file=tools/fedora44/measure.sh && kubectl apply -f tools/fedora44/job.yaml` | hours; the Job stops at 14 h (`activeDeadlineSeconds`) |

A desk can measure the class too (`plugin-qualify-sync --system --force --no-distributed` with `host_class x86-64`),
but only when nothing else runs on it: the measurement plays every plugin on the audio server.

## Install path

```
/usr/share/omx/qualification/<host class>/<set>/
    <plugin>@<version>-<sha256 first 12>.<offer>.qualification.json   # the record
    <same name>.probe.json                                              # the probe output the record judged, byte for byte
    provenance.json                                                     # where the set comes from
```

plugin-db's store (`/var/lib/plugin-db`) holds a machine's own layers and names no place for shipped records, so the
records stay where plugin-qualify-sync reads them (`distributed_dir`, `/usr/share/omx/qualification`). Each package
is architecture-independent (`Architecture: all`, `BuildArch: noarch`) and depends on the plugin-qualify that measured
its set, up to the next minor: `plugin-qualify (>= 0.19.0~), plugin-qualify (<< 0.20~)` and
`(plugin-qualify >= 0.19.0 with plugin-qualify < 0.20)`.

Each record is held with its probe output. Both are the files the measuring machine wrote, unchanged. The plugins
that could not be measured (`*.unmeasured.json`) are not here: an unmeasured record never applies.

## The matching rule

A record is found by the plugin's name (an LV2 uri, a CLAP path). The name only finds it. It applies to a plugin
on the device when, and only when:

- every file of the record's `binary.files` is installed at that path relative to the plugin's root, with that
  SHA-256, computed on the device at the time of the sync;
- the probe output beside the record is intact (its SHA-256 is the one the record names) and one this plugin-qualify
  reads;
- the record holds a verdict for the sync's `host_profile` that ended `qualified`, `refused`, `crashed` or `hung`.

Anything else is measured on the device as before, and the sync says so (`distributed: <uri>: binary differs`).
A package version that ships different bytes, a plugin the user added, or a plugin built for another
architecture therefore never takes a measurement that is not its own.

## Use on a device

```
apt install plugin-db-qualification-rpi5-zynthian-vangelis      # from the OpenMixer channel
plugin-qualify-sync --system
```

```
plugin-qualify-sync: distributed: http://distrho.sf.net/plugins/3BandEQ: applied (zynthian-vangelis)
```

The host class is the board's own, read from the device tree (`rpi5` on a Raspberry Pi 5), or `host_class` in
`/etc/omx/qualify.conf`. A plugin taken from the records is not measured; the sync copies the record into the
device's `qualification_dir` with this set's `provenance` added, and treats it afterwards like one it measured
(skipped while its files are unchanged, measured when they change). `--no-distributed` keeps the layer out of a
run; `--force` measures everything.

The channel is `https://www.openmixer.org/deb/debian/trixie/`; add it with the `openmixer-release` package.

On Fedora 44 x86_64:

```
dnf install https://www.openmixer.org/rpm/openmixer-release.noarch.rpm
dnf install plugin-db-qualification-x86-64-fedora44
printf 'host_class x86-64\nclap_extra /usr/lib64/clap\n' >> /etc/omx/qualify.conf
plugin-qualify-sync --system
```

An x86_64 machine has no device tree, so it has no class of its own: plugin-qualify-sync reads no distributed record
until `host_class` names one. Fedora's CLAP packages (and the audinux ones) install into `/usr/lib64/clap`, which
the sync's default CLAP path (`~/.clap`, `/usr/lib/clap`) leaves out; `clap_extra` adds it, as on the machine that
measures the set.

## Rebuild from a device run

On the device (same class, a new image or new plugin versions), run `plugin-qualify-sync --system --force`, or
`plugin-qualify --all --isolate --out <dir>`, then copy its `qualification_dir` here and:

```
tools/build-package.sh --from <qualification dir> --provenance provenance.json \
    --version <YYYY.MM.DD> --host-class rpi5 --set zynthian-vangelis
git diff --stat
```

`plugin-qualify-records-package` judges which records go in, builds the package, and the
script replaces `records/`, `debian/control`, `debian/install` and the top `debian/changelog` entry with what it
holds. `provenance.json` is a JSON file of what the tool cannot know: the image, the board, the package versions
and the source revisions of the device; the tool adds the schema, the set, the host class, the package and the
date. Commit, then tag `v<version>`: the tag must equal the `debian/changelog` version.

`tools/build-package.sh` without arguments builds the package of `records/` with the tool, to compare with what
`debian/` builds.

The x86-64 set is measured in a pod, not on a desk: `tools/fedora44/job.yaml` is a Job in the cluster's
`omx-worker` namespace, and `tools/fedora44/measure.sh` installs the channel's plugin-qualify, plugin-hostd and
omx-clap-host with the worker image's plugin set (platform `baked-versions.yml`) in `fedora:44`, starts a JACK
server of the pod's own per base (dummy driver; 48000/512, then 96000/256) and runs `plugin-qualify-sync --system`. Copy `/out` out of the pod
and feed the qualification directory of its `var-lib-omx.tar.xz` to

```
tools/build-package.sh --from <qualification dir> --provenance provenance.json \
    --version <YYYYMMDDXX> --host-class x86-64 --set fedora44
```

For the set the RPM spec builds, the script replaces only `records/x86-64/fedora44/` and the spec's `Version`. The
release builds the RPM only while that set is in the tree.

`tools/check-records.py` reads every set as plugin-qualify-sync will: the provenance names its set and class, every
record has its probe output beside it with the size and SHA-256 it names, and nothing else is shipped. The `check`
workflow runs it on every pull request, and the RPM's `%check` runs it on the installed tree.

## The host comparison

A set can also hold how its plugins fare under four hosts: our two (omx-clap-host, with the LV2 adapter, and
plugin-hostd) and the two references, mod-host and jalv. `plugin-qualify compare` runs every plugin through each host
with the same checks (it loads, it instantiates, it gives output under a tone or notes, it survives the load cycles and
the soak, its audio thread allocates, locks or makes a system call or not, its CPU and the latency the host reports) on
one private JACK server at one rate and quantum, and writes one `<plugin>-<format>-<hash>.comparison.json` per plugin
(`plugin-qualify.comparison-record/1`, a row per host, each with its version) and `comparison-summary.json`
(`plugin-qualify.comparison-summary/1`: per host the plugins it loads, runs clean, runs real-time safe and crashes on,
and the plugins where each host does better than the others). A check a host does not let us observe is
`not-observable`, never a failure; a host that is not installed is a `skipped` row with its reason.

On a machine of the set's class, with mod-host and jalv installed (`--publish` refuses to run without them, naming
what is missing):

```
plugin-qualify compare --all --publish --host-class <class> --set <set> --out <dir>
cp <dir>/*.comparison.json <dir>/comparison-summary.json records/<class>/<set>/
python3 tools/check-records.py records/<class>/<set>
```

`tools/check-records.py` holds a set's comparison to the rules: every record is one, a set with comparison records has
their summary, the summary is publishable, mod-host and jalv ran, and its counts are the ones its records give. The
packages ship the files; plugin-qualify-sync reads only the qualification records. The comparison is not bound to the
plugins' bytes as a record is, so a rebuild of the set from a device run drops it (`tools/build-package.sh` says so),
and the new set's comparison is added after. The site's plugin pages show it per machine class.

## Release

A tag `v*` runs `.github/workflows/release.yml`: it builds the package from `debian/`, runs lintian (warnings fail),
installs it in Debian trixie on arm64 with plugin-qualify from the channel and Debian's own arm64 lv2vocoder
(its bytes are the set's), asserts that `plugin-qualify-sync --system` takes plugins from the records
(`distributed: ... applied`), signs the apt index and publishes into the channel.

While the x86-64 set is in the tree, the same tag builds the RPM from `packaging/plugin-db-qualification.spec` through FreeMixer/.github's
`build-rpm.yml` (one noarch build, signed and published into the channel's `rpm/` tree, attached to the same
GitHub release), then installs it in Fedora 44 with plugin-qualify and the omx-plugins version the set measured from
the channel, and asserts that `plugin-qualify-sync --system` takes them from the records. The spec's `Version` and
the top `debian/changelog` entry are the same number, and the tag must equal both (the `check` workflow holds them
together). A manual run (`workflow_dispatch`) does everything except publishing.

## Versions

A records package is versioned by the date its records are published: `YYYYMMDDXX`, the year, month and day
followed by the day's serial, `01` for the first release of the day. A number is never used twice, even for a
release that did not publish: the next one takes the next serial. No dots or other separators: `2026103001`.
The tag is `v` and the version (`v2026103001`). These numbers sort in time order for both dpkg and rpm, so a
machine always upgrades to the newer set.

## Provenance of the Zynthian set

| | |
| --- | --- |
| Image | ZynthianOS Vangelis-2610.1, built 2026-10-15 from Raspberry Pi OS Trixie (aarch64) |
| Board | Raspberry Pi 5 Model B Rev 1.0, a real board |
| Measured | host profile `omx-clap-host`, at 48000/256 and 96000/256; the adapter, isolated, pool and memory steps at 48000/128 and 48000/256 |
| zynthian-ui | `76e325ea9ddfee20c84aa6a9d17782cb9b4c86b1` |
| zynthian-sys | `31e8524328103ed0ab0ad61924431d477bdd448c` |
| Packages | plugin-qualify 0.19.0, plugin-hostd 0.18.0, omx-clap-host 0.29.0, omx-plugins 0.18.0, omx-contract-data 3.9.1, omx-panel 0.10.1, distrho-plugin-ports-lv2 5:20210315; the steps under plugin-qualify 0.19.1, plugin-hostd 0.19.0, omx-clap-host 0.30.0 (the full list is in `provenance.json`) |

## License

GPL-3.0-or-later, as plugin-qualify. See `LICENSE`.
