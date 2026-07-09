#!/usr/bin/env bash
# Fetch the Adafruit-built mpy-cross matching the device's CircuitPython core.
#
# .mpy bytecode must come from CIRCUITPYTHON's mpy-cross (magic byte 'C'). The
# PyPI `mpy-cross` package is MICROPYTHON's compiler (magic 'M') — the device
# rejects its output with "incompatible .mpy file". Adafruit publishes static
# binaries per CP release; this script pins one version + per-platform sha256.
#
# THE PIN MUST MATCH THE CIRCUITPYTHON CORE ON THE DEVICE (currently 10.2.1).
# The .mpy format is stable across CP 9.x/10.x; moving the device past 10.x
# means updating MPY_CROSS_VERSION + URLs + sha256s here, then re-publishing.
# Binary index: https://adafruit-circuit-python.s3.amazonaws.com/index.html?prefix=bin/mpy-cross/
#
# Prints the verified binary's path on STDOUT (all chatter goes to stderr).
# Caches under ~/.cache/tpw-mpy-cross/ — one download per version/platform.
#
# Copyright (c) 2024-2026 Michael Czeiszperger
set -euo pipefail

MPY_CROSS_VERSION="10.2.1"
S3="https://adafruit-circuit-python.s3.amazonaws.com/bin/mpy-cross"

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)
    URL="$S3/macos/mpy-cross-macos-${MPY_CROSS_VERSION}-arm64"
    SHA256="7c5c3f4c85be14a552ddc3d84ec9339af3a1e4a0a43196750a00baa642da5c85"
    ;;
  Linux-x86_64)
    URL="$S3/linux-amd64/mpy-cross-linux-amd64-${MPY_CROSS_VERSION}.static"
    SHA256="c85a9bdb3db06d8e77b600d1d025686b753448be89bb14082ee6e3a01e3c13fe"
    ;;
  *)
    echo "fetch_mpy_cross: no pinned binary for $(uname -s)-$(uname -m) — add a" >&2
    echo "                 (URL, sha256) row for it (see the S3 index in the header)." >&2
    exit 1
    ;;
esac

hash_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi | awk '{print $1}'
}

CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/tpw-mpy-cross"
BIN="$CACHE_DIR/$(basename "$URL")"
mkdir -p "$CACHE_DIR"

# Re-verify the cached copy every run (cheap; catches a corrupt/tampered cache).
if [ ! -f "$BIN" ] || [ "$(hash_of "$BIN")" != "$SHA256" ]; then
  echo "fetch_mpy_cross: downloading $URL" >&2
  curl -fsSL "$URL" -o "$BIN.tmp"
  GOT="$(hash_of "$BIN.tmp")"
  if [ "$GOT" != "$SHA256" ]; then
    rm -f "$BIN.tmp"
    echo "fetch_mpy_cross: ABORT — sha256 mismatch for $URL" >&2
    echo "                 expected $SHA256" >&2
    echo "                 got      $GOT" >&2
    exit 1
  fi
  chmod +x "$BIN.tmp"
  mv "$BIN.tmp" "$BIN"
fi

echo "$BIN"
