#!/usr/bin/env bash
# Deploy ThemeParkWaits to a USB-connected Matrix Portal S3 (CIRCUITPY drive).
#
# On-device layout the bootstrap expects (src/themeparkwaits.py sys.path):
#   /code.py /boot.py            entry + hardware init
#   /src/**                      the app (incl. the Adafruit bundle at /src/lib)
#   /src/.version                shipped version (read by OTAGlue)
#   /lib/scrollkit/**            the ScrollKit library
#   /secrets.py /settings.json   device-owned (WiFi creds + user settings)
#
# Like scripts/publish.sh this deploys a CLEAN `git archive HEAD` tree, so the
# untracked dead dirs (src/config, src/network, src/ota, src/utils), error_log,
# and caches in the working copy are NEVER pushed to the board. scrollkit is not
# in this repo, so it is synced from the sibling library checkout.
#
# Device-owned files (secrets.py, settings.json) are SEEDED only if absent — a
# re-deploy never overwrites your WiFi creds or saved settings.
#
# Usage:
#   scripts/deploy.sh --dry-run     # show exactly what would copy, touch nothing
#   scripts/deploy.sh               # deploy for real
#
# Env:
#   CIRCUITPY       mount point (default: /Volumes/CIRCUITPY)
#   SCROLLKIT_SRC   path to the scrollkit package (default: ../ScrollKit Library/src/scrollkit)
#
# Copyright (c) 2024-2026 Michael Czeiszperger
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${CIRCUITPY:-/Volumes/CIRCUITPY}"
LIB_SRC="${SCROLLKIT_SRC:-$REPO_ROOT/../ScrollKit Library/src/scrollkit}"

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

[ -d "$DEST" ] || { echo "deploy: CIRCUITPY not mounted at '$DEST' — plug in the board." >&2; exit 1; }
[ -f "$DEST/boot_out.txt" ] || echo "deploy: warning — '$DEST' has no boot_out.txt; is it really CIRCUITPY?" >&2
[ -d "$LIB_SRC" ] || { echo "deploy: scrollkit not found at '$LIB_SRC' (set SCROLLKIT_SRC)." >&2; exit 1; }

RSYNC_OPTS=(-rt --no-perms --no-owner --no-group --modify-window=2
            --exclude=__pycache__ --exclude='*.pyc' --exclude='.DS_Store' --exclude='._*')
[ "$DRY" = 1 ] && RSYNC_OPTS+=(-n -v) && echo "== DRY RUN — nothing will be written =="

# Clean tracked app tree from git (no dead code / error_log / caches).
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
git -C "$REPO_ROOT" archive HEAD | tar -x -C "$WORK"

echo "==> app: code.py, boot.py, src/  ->  $DEST"
rsync "${RSYNC_OPTS[@]}" "$WORK/code.py" "$WORK/boot.py" "$DEST/"
# Clean MIRROR of the tracked src/ tree: --delete prunes files removed from the repo
# (retired modules, the old dead src/config|network|ota|utils dirs) and
# --delete-excluded clears stale __pycache__/.pyc/._* AppleDouble cruft, so the board
# never accumulates orphaned code. /src holds no device-owned state except .version
# (untracked, so not in the archive); it is deleted here and re-copied immediately
# below. Device-owned files (secrets.py, settings.json, error_log) live at the ROOT,
# outside /src, so this never touches them.
rsync "${RSYNC_OPTS[@]}" --delete --delete-excluded "$WORK/src/" "$DEST/src/"

# src/.version is untracked (not in the archive) — copy the local one explicitly
# so OTAGlue.read_current_version() reports a real version on the device.
if [ -f "$REPO_ROOT/src/.version" ]; then
  echo "==> version: src/.version ($(cat "$REPO_ROOT/src/.version"))  ->  $DEST/src/.version"
  [ "$DRY" = 0 ] && cp "$REPO_ROOT/src/.version" "$DEST/src/.version"
fi

# scrollkit/simulator (pygame) and scrollkit/dev (test harness) are desktop-only
# — the board never imports them (scrollkit does no eager imports). Excluding them
# drops the sync from ~2.9M to ~1M and saves device flash. --delete prunes any that
# a previous run already copied.
echo "==> library: scrollkit  ->  $DEST/lib/scrollkit  (excl simulator/ + dev/; --delete prunes stale)"
[ "$DRY" = 0 ] && mkdir -p "$DEST/lib/scrollkit"
# --delete-excluded (not just --delete): rsync PROTECTS excluded paths from plain
# --delete, so simulator/dev already on the device would survive. This prunes them.
rsync "${RSYNC_OPTS[@]}" --delete --delete-excluded --exclude=/simulator --exclude=/dev "$LIB_SRC/" "$DEST/lib/scrollkit/"

# Seed device-owned files only if absent (never clobber on re-deploy).
for f in secrets.py settings.json; do
  if [ ! -e "$DEST/$f" ] && [ -f "$REPO_ROOT/$f" ]; then
    echo "==> seed: $f (absent on device)  ->  $DEST/$f"
    [ "$DRY" = 0 ] && cp "$REPO_ROOT/$f" "$DEST/$f"
  elif [ -e "$DEST/$f" ]; then
    echo "    keep: $f already on device (left untouched)"
  fi
done

if [ "$DRY" = 1 ]; then
  echo "== DRY RUN complete — re-run without --dry-run to deploy =="
  exit 0
fi
sync
echo "==> done. Let the board finish reloading, then open the serial console to watch boot:"
echo "    screen /dev/cu.usbmodem* 115200    (or:  tio /dev/cu.usbmodem*)"
