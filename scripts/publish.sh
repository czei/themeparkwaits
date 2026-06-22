#!/usr/bin/env bash
# Publish a ThemeParkWaits OTA release to the device-read `live` channel branch.
#
# Hybrid OTA model (research D8 / SCROLLKIT_NOTES.md #3): the device reads ONE
# fixed public branch (`live`) via raw.githubusercontent. A release is cut by
# creating an immutable `release-MAJOR.MINOR` archive branch; this script mirrors
# that ref's app source onto `live` as `manifest.json` + `files/<device-path>`.
#
# It is the shared core used by BOTH:
#   * a human running it locally:   scripts/publish.sh release-1.96
#   * .github/workflows/publish-live.yml (on a release-* branch being created)
#
# Design constraints learned the hard way (see RELEASING.md):
#   * Build from a CLEAN tracked tree (`git archive <ref>`), NEVER the working
#     dir — the working dir holds untracked dead code (src/config, src/network,
#     src/ota, src/utils), error_log, caches that must NOT ship.
#   * `src/.version` is untracked, so the version comes from the release ref name
#     and is stamped into the shipped tree (this is how the device records its new
#     current_version after a successful apply).
#   * Private/device-local files (secrets.py, settings.json, error_log) are never
#     published; make_manifest.py excludes them and we re-verify before pushing.
#
# Usage:
#   scripts/publish.sh <release-ref> [--version X.Y] [--dry-run]
#   scripts/publish.sh release-1.96                 # version 1.96 from the ref name
#   scripts/publish.sh release-1.96 --dry-run       # build + verify, do NOT push
#   VERSION=1.96 scripts/publish.sh some-tag        # explicit version for any ref
#
# Env knobs (all optional):
#   VERSION          override the version (else derived from a release-X.Y ref)
#   INCLUDE_LIB=1    also ship src/lib (the Adafruit .mpy bundle); default 0
#                    (flash-frozen: bundled libs + scrollkit are matched to the
#                     CircuitPython core and updated by USB reflash, not OTA)
#   LIVE_BRANCH      channel branch to publish to (default: live)
#   PUBLISH_REMOTE   git URL to push to (default: this repo's `origin` URL)
#   DRY_RUN=1        same as --dry-run
#
# Copyright 2024 3DUPFitters LLC
set -euo pipefail

# --- locate repo / script ---------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MAKE_MANIFEST="$SCRIPT_DIR/make_manifest.py"

# --- args --------------------------------------------------------------------
REF="${1:-}"
[ -n "$REF" ] && shift || true
VERSION="${VERSION:-}"
DRY_RUN="${DRY_RUN:-0}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --version) VERSION="${2:?--version needs a value}"; shift 2 ;;
    --version=*) VERSION="${1#*=}"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "publish.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$REF" ]; then
  echo "usage: scripts/publish.sh <release-ref> [--version X.Y] [--dry-run]" >&2
  exit 2
fi

INCLUDE_LIB="${INCLUDE_LIB:-0}"
LIVE_BRANCH="${LIVE_BRANCH:-live}"
PUBLISH_REMOTE="${PUBLISH_REMOTE:-$(git -C "$REPO_ROOT" remote get-url origin)}"

# --- derive + validate version ----------------------------------------------
if [ -z "$VERSION" ]; then
  case "$REF" in
    release-*) VERSION="${REF#release-}" ;;
    *) echo "publish.sh: ref '$REF' is not release-* — pass --version X.Y" >&2; exit 2 ;;
  esac
fi
if ! printf '%s' "$VERSION" | grep -Eq '^[0-9]+\.[0-9]+(\.[0-9]+)?$'; then
  echo "publish.sh: version '$VERSION' is not a MAJOR.MINOR[.PATCH] semver" >&2
  exit 2
fi

# --- resolve the ref to a concrete commit (fail loudly if missing) ----------
if ! SHA="$(git -C "$REPO_ROOT" rev-parse --verify --quiet "${REF}^{commit}")"; then
  echo "publish.sh: ref '$REF' not found in $REPO_ROOT" >&2
  exit 2
fi

echo "==> Publishing $REF ($SHA) as version $VERSION to '$LIVE_BRANCH'"
[ "$INCLUDE_LIB" = "1" ] && echo "    including src/lib (Adafruit bundle)" \
                         || echo "    src/lib + scrollkit are flash-frozen (not shipped)"

# --- work in a temp dir (cleaned on exit) -----------------------------------
WORK="$(mktemp -d "${TMPDIR:-/tmp}/tpw-publish.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
TREE="$WORK/tree"
OUT="$WORK/out"
mkdir -p "$TREE" "$OUT"

# 1) extract a CLEAN tree from the release ref (tracked files only)
git -C "$REPO_ROOT" archive "$SHA" | tar -x -C "$TREE"

# 2) decide library policy
if [ "$INCLUDE_LIB" != "1" ]; then
  rm -rf "$TREE/src/lib"
fi

# 3) stamp the version into the shipped tree so the device records it post-apply
printf '%s\n' "$VERSION" > "$TREE/src/.version"

# 4) build the manifest + payload for each device tree
#    src/** -> /src/**, plus top-level code.py + boot.py -> /
python3 "$MAKE_MANIFEST" "$TREE/src"     "$OUT" --root /src --version "$VERSION"
python3 "$MAKE_MANIFEST" "$TREE/code.py" "$OUT" --root /    --version "$VERSION"
python3 "$MAKE_MANIFEST" "$TREE/boot.py" "$OUT" --root /    --version "$VERSION"

# 5) defense-in-depth: refuse to publish if anything private slipped in
LEAK="$(cd "$OUT" && find files -type f \( -name secrets.py -o -name settings.json \
        -o -name 'error_log*' -o -name credentials.json -o -name secrets.json \) 2>/dev/null || true)"
if [ -n "$LEAK" ]; then
  echo "publish.sh: ABORT — private file(s) in payload:" >&2
  printf '  %s\n' $LEAK >&2
  exit 1
fi

FILE_COUNT="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["files"]))' "$OUT/manifest.json")"
PAYLOAD_SIZE="$(du -sh "$OUT/files" | cut -f1)"
echo "==> manifest v$VERSION: $FILE_COUNT files, payload $PAYLOAD_SIZE"

if [ "$DRY_RUN" = "1" ]; then
  echo "==> DRY RUN — not pushing. Built tree at:"
  (cd "$OUT" && find . -maxdepth 2 -type f | sort | sed 's/^/    /')
  echo "    (re-run without --dry-run to publish to '$LIVE_BRANCH' on $PUBLISH_REMOTE)"
  exit 0
fi

# 6) publish: a fresh single-commit orphan so `live` holds ONLY channel content
#    (history lives in the release-* archives; raw.githubusercontent serves HEAD)
PUB="$WORK/pub"
mkdir -p "$PUB"
cp "$OUT/manifest.json" "$PUB/"
cp -R "$OUT/files" "$PUB/"
cd "$PUB"
git init -q
git checkout -q -b "$LIVE_BRANCH"
git config user.name  "${GIT_AUTHOR_NAME:-themeparkwaits-publish}"
git config user.email "${GIT_AUTHOR_EMAIL:-publish@themeparkwaits.local}"
git add -A
git commit -q -m "Publish v$VERSION to $LIVE_BRANCH (from $REF @ ${SHA:0:9})"
echo "==> pushing to $LIVE_BRANCH"
git push --force "$PUBLISH_REMOTE" "$LIVE_BRANCH"
echo "==> done: v$VERSION is live on '$LIVE_BRANCH'"
