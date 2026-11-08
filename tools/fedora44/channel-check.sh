#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
#
# The records are measured against OUR channel's mod-host-protocol, which plugin-hostd links, not a distro or COPR
# build of the same name. The fact tested is where the installed package came from: the OpenMixer channel's repository
# ids (openmixer-release's openmixer and openmixer-noarch). It used to test for "omx" in the version, the old fork's
# release tag; the channel's builds since 0.10.9 carry plain versions, so that text is no longer a fact of the channel.
# FROM_REPO overrides the dnf query (tools/test_fedora44_channel_check.py).
set -u
from=${FROM_REPO-$(dnf -q repoquery --installed --qf '%{from_repo}\n' mod-host-protocol 2>/dev/null | head -1)}
case $from in
  openmixer|openmixer-noarch) exit 0 ;;
esac
echo "mod-host-protocol is not the channel build (installed from '${from}')" >&2
exit 1
