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
#   MPY=0            ship scrollkit as .py source instead of compiled .mpy
#                    (default 1: compile with the pinned CircuitPython mpy-cross
#                     from scripts/fetch_mpy_cross.sh — halves the library's
#                     flash footprint and every future OTA delta)
#
# Copyright (c) 2024-2026 Michael Czeiszperger
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
echo "    bundling scrollkit under /lib/scrollkit (delta-apply ships only changed files)"
[ "$INCLUDE_LIB" = "1" ] && echo "    including src/lib (Adafruit .mpy bundle)" \
                         || echo "    src/lib (Adafruit .mpy bundle) flash-frozen (not shipped)"

# --- work in a temp dir (cleaned on exit) -----------------------------------
WORK="$(mktemp -d "${TMPDIR:-/tmp}/tpw-publish.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
TREE="$WORK/tree"
OUT="$WORK/out"
mkdir -p "$TREE" "$OUT"

# 1) extract a CLEAN tree from the release ref (tracked files only)
git -C "$REPO_ROOT" archive "$SHA" | tar -x -C "$TREE"

# 2) decide library policy
#    The 276 KB Adafruit .mpy bundle is device-resident and rarely changes, so
#    it is NOT shipped by default. EXCEPTION: vendored modules the app IMPORTS
#    at runtime must always ride along, or an update lands code whose import
#    fails on any box that predates the vendoring (adafruit_json_stream is the
#    streaming parse's hard dependency — 10 KB, added 2026-07-19). Keep this
#    list in step with every `import` of a src/lib module in app code.
VENDORED_REQUIRED="adafruit_json_stream.py"
if [ "$INCLUDE_LIB" != "1" ]; then
  KEEP="$WORK/keep-lib"
  mkdir -p "$KEEP"
  for f in $VENDORED_REQUIRED; do
    if [ -f "$TREE/src/lib/$f" ]; then
      cp "$TREE/src/lib/$f" "$KEEP/$f"
    else
      echo "publish.sh: ABORT — required vendored module missing: src/lib/$f" >&2
      exit 1
    fi
  done
  rm -rf "$TREE/src/lib"
  mkdir -p "$TREE/src/lib"
  for f in $VENDORED_REQUIRED; do cp "$KEEP/$f" "$TREE/src/lib/$f"; done
fi

# 3) stamp the version into the shipped tree so the device records it post-apply
printf '%s\n' "$VERSION" > "$TREE/src/.version"

# 3b) resolve the sibling ScrollKit library — bundled into the payload below and
#     used by the preflight (its real device-side parser). Fail loudly if absent.
#     NOTE: publish.sh's SCROLLKIT_SRC is the library's `src/` (parent of
#     `scrollkit/`); deploy.sh's same-named var points AT `src/scrollkit`.
SCROLLKIT_SRC="${SCROLLKIT_SRC:-$REPO_ROOT/../ScrollKit Library/src}"
if [ ! -d "$SCROLLKIT_SRC/scrollkit" ]; then
  echo "publish.sh: ABORT — scrollkit library not found at $SCROLLKIT_SRC" >&2
  echo "            set SCROLLKIT_SRC to the library's src/ dir (parent of scrollkit/)." >&2
  exit 1
fi

# 4) build the manifest + payload for each device tree
#    src/** -> /src/**, plus top-level code.py -> /
#    boot.py is deliberately NOT shipped: it is the flash-frozen recovery anchor
#    (it restores /backup if power is lost mid-install, BEFORE the possibly-torn
#    app code runs). A power cut while OTA rewrote boot.py itself would be an
#    unrecoverable brick — update it only via a supervised USB deploy.
python3 "$MAKE_MANIFEST" "$TREE/src"     "$OUT" --root /src --version "$VERSION"
python3 "$MAKE_MANIFEST" "$TREE/code.py" "$OUT" --root /    --version "$VERSION"

# 4a) /safemode.py — the CircuitPython-safe-mode escape hatch — is OTA-deliverable
#     only by clients whose scrollkit allowlist includes it (added 2026-07-19).
#     A fielded client with the OLD allowlist rejects the WHOLE manifest if the
#     file appears ("Unsafe manifest path(s)"), stranding it on its current
#     version. Two-stage rollout: release N ships the new scrollkit (allowlist
#     update) with SHIP_SAFEMODE unset; once the fleet runs it, release N+1
#     sets SHIP_SAFEMODE=1. USB deploys/zips ship the file unconditionally
#     (deploy.sh), so bench boxes are covered either way.
if [ "${SHIP_SAFEMODE:-0}" = "1" ]; then
  python3 "$MAKE_MANIFEST" "$TREE/safemode.py" "$OUT" --root / --version "$VERSION"
fi

# 4b) bundle the ScrollKit library under /lib/scrollkit so a release that changed
#     BOTH repos lands ATOMICALLY (the app may import a class that only exists in
#     the updated library — ImportError otherwise). scrollkit ships as compiled
#     .mpy (see 4b-mpy below); the device's delta-apply downloads only the files
#     whose checksum changed, so an unchanged library costs nothing and a changed
#     one ships just its diff.
#     Mirror deploy.sh's excludes (simulator/ + dev/ are desktop-only) via a temp
#     copy — the same idiom as `rm -rf src/lib` above. Accumulates into the same
#     manifest; the leak-check + preflight below then cover the scrollkit files.
SK_TMP="$WORK/scrollkit"
mkdir -p "$SK_TMP"
cp -R "$SCROLLKIT_SRC/scrollkit/." "$SK_TMP/"
rm -rf "$SK_TMP/simulator" "$SK_TMP/dev"
# ota/publish.py is the desktop/CI-side publisher (raises ImportError on the
# device) — it has no business in the payload.
rm -f "$SK_TMP/ota/publish.py"
find "$SK_TMP" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

# 4b-mpy) compile scrollkit .py -> .mpy with the PINNED CircuitPython mpy-cross
#     (scripts/fetch_mpy_cross.sh — the pin must match the device's CP core).
#     Roughly halves the library's bytes on flash AND every future OTA delta.
#     MPY=0 is the escape hatch to ship plain .py source.
MPY="${MPY:-1}"
if [ "$MPY" = "1" ]; then
  MPY_CROSS_BIN="$("$SCRIPT_DIR/fetch_mpy_cross.sh")"
  PY_BYTES="$(du -sk "$SK_TMP" | cut -f1)"
  PY_COUNT="$(find "$SK_TMP" -name '*.py' | wc -l | tr -d ' ')"
  while IFS= read -r -d '' f; do
    # -s embeds a STABLE source name (the on-device path) instead of the temp
    # build path — without it every build produces different .mpy bytes and the
    # device's delta-apply would re-download the whole library each release.
    "$MPY_CROSS_BIN" -s "lib/scrollkit/${f#"$SK_TMP"/}" "$f" -o "${f%.py}.mpy"
    rm "$f"
  done < <(find "$SK_TMP" -name '*.py' -print0)
  # Sanity: nothing un-compiled, count parity, and every file carries
  # CircuitPython's .mpy header b'C\x06' — a MicroPython-built mpy-cross
  # (e.g. the PyPI package) emits b'M...' and would brick the import.
  python3 - "$SK_TMP" "$PY_COUNT" <<'PY'
import os, sys
root, want = sys.argv[1], int(sys.argv[2])
mpy = []
for dirpath, _dirs, files in os.walk(root):
    for name in files:
        path = os.path.join(dirpath, name)
        if name.endswith('.py'):
            sys.exit("mpy sanity FAILED: source survived the compile: %s" % path)
        if name.endswith('.mpy'):
            mpy.append(path)
if len(mpy) != want:
    sys.exit("mpy sanity FAILED: %d .py in, %d .mpy out" % (want, len(mpy)))
for path in mpy:
    with open(path, 'rb') as f:
        head = f.read(2)
    if head != b'C\x06':
        sys.exit("mpy sanity FAILED: %s header %r is not CircuitPython bytecode "
                 "(magic 'C', MPY_VERSION 6) — wrong mpy-cross?" % (path, head))
print("==> mpy OK: %d modules compiled" % len(mpy))
PY
  echo "==> scrollkit payload: ${PY_BYTES}K of .py -> $(du -sk "$SK_TMP" | cut -f1)K of .mpy"
fi

python3 "$MAKE_MANIFEST" "$SK_TMP" "$OUT" --root /lib/scrollkit --version "$VERSION"

# 4c) preflight: run the built manifest through the REAL device-side parser +
#     the same path-safety allowlist the device enforces. Generator (this repo)
#     and validator (scrollkit, frozen on device) have no shared schema — this is
#     the check whose absence shipped the missing-`required` outage.
PYTHONPATH="$SCROLLKIT_SRC" python3 - "$OUT/manifest.json" <<'PY'
import json, sys
from scrollkit.ota.manifest import UpdateManifest
data = json.load(open(sys.argv[1]))
manifest = UpdateManifest.from_dict(data)
ok, err = manifest.validate()
if not ok:
    sys.exit("preflight FAILED: device validator rejects the manifest: %s" % err)
if manifest.compare_version("0.0.0") <= 0:
    sys.exit("preflight FAILED: manifest version %r does not compare as newer "
             "than 0.0.0" % manifest.version)
def allowed(k):
    # Mirrors the CURRENT device-side allowlist (scrollkit ota/client.py
    # _key_allowed, incl. /safemode.py since 2026-07-19). The SHIP_SAFEMODE
    # gate above — not this check — is what sequences the two-stage rollout
    # for fielded clients still running the old allowlist.
    if not k or ".." in k.split("/"):
        return False
    if k in ("/code.py", "/boot.py", "/safemode.py"):
        return True
    return k.startswith("/src/") or k.startswith("/lib/scrollkit/")
bad = [k for k in data["files"] if not allowed(k)]
if bad:
    sys.exit("preflight FAILED: unsafe manifest path(s): %s" % ", ".join(sorted(bad)[:5]))
print("==> preflight OK: device validator accepts manifest v%s (%d files)"
      % (manifest.version, len(manifest.files)))
PY

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
# version.txt: the ~6-byte fast path for the device's update CHECK. Fetching the
# full manifest (~31 KB, flash-streamed, JSON-parsed) just to compare a version
# number was wasteful and slow; the client reads this first and only fetches the
# manifest when the version is actually newer (with a 404 fallback for channels
# published before this existed).
printf '%s\n' "$VERSION" > "$PUB/version.txt"
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

# 7) update-check endpoint: devices CHECK against themeparkwaits.com/ota/version.txt
#    (ECDSA chain — cheap handshake), never raw.githubusercontent.com (RSA-2048
#    chain: mbedtls PK_ALLOC_FAILED / OSError -16256 on a running box; see
#    docs/ota-check-failure-ledger.md attempt #5). Same bytes as the live
#    branch's version.txt. The site deploy's rsync --delete excludes /ota, so
#    this survives website deploys. A failure here FAILS the release: a stale
#    check endpoint makes every device silently believe it is up to date.
OTA_HOST="${OTA_CHECK_HOST:-ec2-user@webperformance.com}"
OTA_KEY="${OTA_CHECK_KEY:-$HOME/.ssh/michael-2.pem}"
OTA_DIR="/opt/themeparkwaits.com/ota"
if [ ! -f "$OTA_KEY" ]; then
  # A release is NOT done until the check endpoint matches the payload: exiting
  # 0 here (the pre-3.5.17 behavior) let CI mirror the live branch while every
  # fielded device kept answering "up to date" against the stale version.txt —
  # the same silent split-brain class as the 3.5.13 incident. Fail the release.
  echo "ERROR: no server key at $OTA_KEY — cannot publish version.txt." >&2
  echo "       The live branch may already be mirrored, but the release FAILED:" >&2
  echo "       devices check version.txt and will not see v$VERSION." >&2
  echo "       From a machine with the key, finish the release with:" >&2
  echo "       printf '%s\n' \"$VERSION\" | ssh -i \"$OTA_KEY\" \"$OTA_HOST\" \"cat > $OTA_DIR/version.txt\"" >&2
  exit 1
fi
echo "==> publishing version.txt to themeparkwaits.com/ota/"
if ssh -i "$OTA_KEY" "$OTA_HOST" "sudo mkdir -p '$OTA_DIR' && sudo chown ec2-user: '$OTA_DIR'" \
   && printf '%s\n' "$VERSION" | ssh -i "$OTA_KEY" "$OTA_HOST" "cat > '$OTA_DIR/version.txt' && chmod 644 '$OTA_DIR/version.txt'"; then
  echo "==> check endpoint updated: https://themeparkwaits.com/ota/version.txt = $VERSION"
else
  echo "ERROR: version.txt publish to the website FAILED — devices would check against a stale endpoint." >&2
  echo "       Fix and re-run, or publish manually:" >&2
  echo "       printf '%s\n' \"$VERSION\" | ssh -i \"$OTA_KEY\" \"$OTA_HOST\" \"cat > $OTA_DIR/version.txt\"" >&2
  exit 1
fi

# 8) trust nothing: read the endpoint back the way a DEVICE does and require an
#    exact match. Catches a wrong vhost/docroot, an Apache alias eating /ota,
#    or a permissions miss — every failure mode ends as "the fleet silently
#    believes it is up to date", so it must fail the release here instead.
PUBLISHED="$(curl -fsS --max-time 15 "https://themeparkwaits.com/ota/version.txt" | tr -d '[:space:]')" || {
  echo "ERROR: could not read back https://themeparkwaits.com/ota/version.txt" >&2
  exit 1
}
if [ "$PUBLISHED" != "$VERSION" ]; then
  echo "ERROR: check endpoint verification FAILED: published '$PUBLISHED' != release '$VERSION'." >&2
  exit 1
fi
echo "==> check endpoint verified: version.txt reads back exactly '$VERSION'"
