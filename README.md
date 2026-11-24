# plugin-db-qualification

The qualification layer of plugin-db. It holds what plugin-qualify measured about plugins, as a SQLite store, and the
tools that read and write it.

[plugin-qualify](https://github.com/Open-Mixer/plugin-qualify) measures every LV2 and CLAP plugin of a machine before
the machine hosts it. That takes hours on a small board. A machine of the same class with the same plugin files does
not need to measure again. This repository ships the records of the qualification runs, so `plugin-qualify-sync` can
take a plugin from them and measure only what they do not hold.

The design is this repository's qualification store spec. Read it for every rule below.

## What is offered

These binary packages come from this source. The names are the Debian ones; the RPM names differ only where noted.

| package | what it ships |
| --- | --- |
| `plugin-qualification-records` | The base layer: `/usr/share/omx/qualification/qualification.sqlite`. It is built from `records/` when the package is built, one per architecture. It also installs the records as files, until the consumers have switched to the store. |
| `libplugin-qualification-db0` | The reader library, `libplugin-qualification-db.so.0`. It reads the base layer and a user layer and merges them. |
| `libplugin-qualification-db-dev` (RPM: `-devel`) | The header, the `.so` link and `plugin-qualification-db.pc`. The `.pc` variable `schema` names the DDL. |
| `plugin-qualification-db` | The command. `plugin-qualification-db query --json` prints results; `check` opens both layers and the words they hold. |
| `plugin-qualification-db-write` | The writer: `plugin-qualification-db-write put` and `delete`, and the Python module behind them. It writes the user layer and the system layer. |
| `plugin-qualification-db-schema` | The DDL, once, at `/usr/share/plugin-qualification-db/qualification.sql`. The writer and test fixtures read it from there. |

The records package is per architecture. The library, the command and `-dev` are built for each. The writer and the
schema package are the same on every architecture. Every package is versioned together.

`packaging/arch-classes` maps each architecture to a machine class and to the plugin-qualify version its package needs.
`tools/sets.py check` holds the packaging to it.

## The store

One SQLite file format, two kinds of file.

| layer | path | written by |
| --- | --- | --- |
| base | `/usr/share/omx/qualification/qualification.sqlite` | the records package; read only |
| user, user scope | `~/.local/share/omx/qualification/qualification.sqlite` | `plugin-qualify-sync` of that user, through the writer |
| user, system scope | `/var/lib/omx/qualification/qualification.sqlite` | `plugin-qualify-sync --system`, through the writer |

A reader opens the base and one user layer. A record in the user layer shadows the whole base record of the same key.
The base is never changed. A scope reads its own layer and not the other's. The command and the tests may name other
places; the library's `pqdb_open(scope)` does not.

Qualification results are stable. They are stored once and never measured again per release or per operating system.
The base is built from the existing records under `records/`, every set with its provenance: the x86-64 sets, which are
named for the Fedora 44 image they were measured on, and the rpi5 sets. A set stays valid on later releases: x86-64 is a
host class, not an operating system. Each record keeps the plugin's verdicts, its cost and latency figures, memory, real-time
safety, and the name and hash of the probe output it judged. It keeps codes, never sentences.

### The record key

A record is the judgement of one plugin binary under one offer on one machine class. Its key is:

- the SHA-256 of the main binary, the plugin format (`clap` or `lv2`) and the plugin id (the CLAP id or the LV2 uri);
- the offer, `default` or `custom`;
- the host class, such as `rpi5` or `x86-64`.

The SHA-256 is the identity. The package fields beside it say which installed package the binary came from. They help to
find results and are never part of the key.

A plugin matches a record when its files are exactly the record's file list, by relative path and SHA-256. The record
keeps the binary's path relative to the plugin's install root. The same record therefore matches the same bytes under
`/usr/lib/clap`, `/usr/lib64/clap` or a home directory.

### Where the words come from

The store owns no words. A word is a rating, a reason, a dimension, a code. The writer and the reader check every word
column against the owner's installed domain. Nothing is copied into this repository.

- `qualification`: plugin-qualify.
- `machine` and `probe`: plugin-hostd.
- plugin-db's own domain: the plugin formats.

The hosting words are the one exception, until omx-clap-core publishes a `hosting` domain.
They are the codes of the installed contract package omx-clap, which omx-clap-contract ships
(`hosting.json` and `hosting/*.json` under `<contractdir>/3/omx-clap/`). The writer reads them from there and refuses a hosting
word that package does not hold. The store records them as the domain `hosting`, at that package's version. The reader
passes over the hosting columns this pass.

The contract directory is the one omx-contract installs. The writer takes `--contract-dir`, then `OMX_CONTRACT_PATH`,
then the `contractdir` of `libomx-domain.pc`.

## Writing the user layer

```
plugin-qualification-db-write put --scope user --offer default --host-class x86-64 < record.json
plugin-qualification-db-write delete --scope user --sha256 <hash> --format clap --uri <id> --offer default --host-class x86-64
```

`put` takes one record on standard input and replaces the layer's record of the same key. It creates the layer when
there is none. A refusal is named on standard error, nothing is written, and the exit code is 1. The names are in the
spec: `path-absolute`, `binary-not-in-files`, `key-not-the-binary`, `files-unordered`, `files-duplicate`, `files-empty`,
`word-unknown`, `field-unmapped`, and others.

## Building

The reader is built with `make` and tested with `make check`. It needs a C compiler, `sqlite3` 3.37.0 or later and
`libomx-domain` from omx-contract 3.20.0 or later, found by `pkg-config`. `make install DESTDIR=... PREFIX=/usr`
installs the library, the command, the header, the `.pc`, the DDL and the writer.

The base is built by `tools/records-db.py --records records --out qualification.sqlite --contract-dir <dir>`. The
packages run it. It needs Python 3, its `sqlite3` module and `python3-jsonschema`. Building the same records twice gives
the same database.

`records/` holds the sets. A set is per machine class, per sample rate and per quantum, named
`<set>-<rate>-<quantum>`. `tools/check-records.py` checks every set the way `plugin-qualify-sync` reads it, and refuses
an absolute `binary.path`. The records are rewritten once to the relative form, by `tools/rewrite-records.py`.

The x86-64 sets are of two tiers. `fedora44-<rate>-<quantum>` (tier `provisional`) were measured without real-time
priority; `fedora44-rt-<rate>-<quantum>` (tier `reference`) were measured with SCHED_FIFO granted. Both are kept. Where
both hold one plugin at one cell, the base gives the claim to the reference tier and the reader answers with it (the
store spec, section 4). A set is marked `rt` only when it is of the reference tier.

The console key waits for its desk run (issue #5's ruling): a set of the `openmixer-console` profile is refused, and
the base holds no openmixer-console verdict. The record files keep them; the base build leaves them out.

## Packaging rules

- A package states its dependencies as floors. No upper limit is set anywhere.
- No package of this source has Provides, Replaces, Breaks, Conflicts or Obsoletes. Not on another package of this
  source, and not on the older per-set package names. Those names are pruned from the channel. `tools/sets.py check` and
  `tools/test_no_relations.py` refuse a relation.
- The writer package does not depend on a contract package. It reads the installed contract directory when it runs.

## Release

A tag `v<version>` runs `.github/workflows/release.yml`. It builds the packages for the architectures
`packaging/release-arches` names and publishes them into the OpenMixer channel. The version is the date and the day's
serial, `YYYYMMDDXX`, for example `2026103001`. A number is never used twice. The tag, the spec's `Version` and the top
`debian/changelog` entry are the same number, and `tools/sets.py check` holds them together.

A manual run with `publish=false` builds everything and publishes nothing.

## Adding measurements

The records change only when new measurements are added, never per release. A new measurement is a new set. Import a
`plugin-qualify --out` directory (its `*.qualification.json` and `*.probe.json` files) with its provenance:

```
tools/sets.py import <class> <set> <out-dir> --provenance <file>
```

The import adds `records/<class>/<set>/` and runs `tools/check-records.py` on it. It refuses a set that already exists
(`set-exists`), an unknown class, and any file or set that fails the check; a refusal leaves the tree as it was. Then run
`tools/sets.py spec`, and release the records package under a new date version.

`tools/build-package.sh` builds such a set from a run's qualification directories:

```
tools/build-package.sh --from-run <run> --provenance provenance.json \
    --version <YYYYMMDDXX> --host-class <class> --set <set>
```

Every `b<rate>-<quantum>/qualification` of the run becomes the set `<set>-<rate>-<quantum>`. `provenance.json` holds what
the tool cannot know: the image, the board, the package versions. A record file and a probe file are never edited; they
are the bytes the device wrote.

## License

GPL-3.0-or-later, as plugin-qualify. See `LICENSE`.
