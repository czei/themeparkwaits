# Releasing ThemeParkWaits (OTA)

How a new firmware version reaches fielded Matrix Portal S3 devices over the air.

## The model (hybrid "Option C")

The device reads **one fixed, public branch — `live`** — over
`raw.githubusercontent.com` (no on-device token, no GitHub API calls). It fetches
`manifest.json`, compares the manifest `version` against its own
`src/.version`, and if newer, downloads `files/<device-path>/...` and applies them.
This is deliberate: an ESP32-S3 can't safely enumerate branches (unauthenticated
GitHub REST is 60 req/hr/IP, `json.loads` needs contiguous RAM) — see
`SCROLLKIT_NOTES.md` #3 for the full rationale.

So the device never discovers releases. Instead:

```
cut a release  ──>  release-MAJOR.MINOR branch   (immutable archive, history/rollback)
                          │
                  publish.sh / GitHub Action      (off-device automation)
                          │
                          ▼
                    live branch                   (manifest.json + files/, the ONE branch the device reads)
                          │
                  raw.githubusercontent.com
                          ▼
                    Matrix Portal S3
```

`live` is named distinctly from `release-*` to avoid a `releases` / `release-2.1`
name clash. `live` always holds a single squashed commit (the publisher
force-pushes an orphan) — its only job is to serve the current channel content.
History and rollback targets live in the `release-*` archive branches.

## Security posture — accept this before publishing

- **`live` and the repo are world-readable.** Confirm nothing private ships. The
  publisher (`scripts/publish.sh`) excludes `secrets.py`, `settings.json`,
  `error_log`, caches, and the dead untracked dirs, and **re-verifies** the payload
  before pushing — but the policy is yours to own.
- **SHA-256 in the manifest is integrity, not authenticity.** Anyone who can push
  to `live` can publish an update. Access control rests entirely on **who can push
  to the `live` branch.** Protect it (branch protection / restricted pushers).
  Code signing is out of current scope.

## What ships vs. what's frozen

| Path                         | Ships via OTA?            | Why |
|------------------------------|---------------------------|-----|
| `code.py`                    | yes (`/code.py`)          | app entry |
| `boot.py`                    | **no** — flash-frozen     | the recovery anchor; a power cut rewriting it would be an unrecoverable brick. USB deploy only. |
| `src/**` (app code, www, fonts, images) | yes (`/src/**`) | the app |
| `src/.version`               | yes — **stamped at publish** | this is how the device records its new `current_version` |
| `scrollkit/` (the library)   | **yes** (`/lib/scrollkit/**`) | bundled from the sibling repo at publish; ships as `.py` source so a release that changed both repos lands atomically |
| `src/lib/**` (Adafruit `.mpy` bundle) | **no, by default** | flash-frozen; `INCLUDE_LIB=1` to ship it |
| `secrets.py`, `settings.json`, `error_log`, caches | **never** | device-owned / private |

**Why `scrollkit` now ships (and why the Adafruit bundle still doesn't):** features
are often "universal" — the app imports something that only exists in the updated
library, so shipping app source alone would `ImportError` on boot. `scrollkit` is
bundled into the payload under `/lib/scrollkit/**`. Two things make this safe that
weren't true of a naive full-bundle push:

- **Delta apply.** The device downloads / backs up / installs only the files whose
  on-device sha256 differs from the manifest, so the "Installing… do not unplug!"
  window and the on-device backup set stay small — a handful of changed files, not
  the whole tree — regardless of total manifest size. A full-manifest download would
  not even fit the device's thin free space (`2 ×` the combined app+library manifest
  exceeds it); the delta does.
- **`scrollkit` ships as `.py` source, not `.mpy`.** So it has no "must match the
  CircuitPython core" constraint — that constraint is what keeps the **Adafruit
  `src/lib` bundle** (`.mpy`) frozen: bumping it needs a supervised USB reflash, so
  `INCLUDE_LIB` stays `0`. An interrupted apply still rolls back via `boot.py` +
  `/backup` (created files are deleted so no orphans remain).

## Versioning

- The version is **the `release-MAJOR.MINOR` branch name** (e.g. `release-1.96` →
  `1.96`). `src/.version` is *not* tracked in git, so it can't be the source of
  truth — the branch name is. `publish.sh` stamps the resolved version into the
  shipped `src/.version`.
- After a successful apply, the device's `/src/.version` becomes the new version;
  `OTAGlue.read_current_version()` reads it on the next boot, so the next check
  compares correctly. That closes the loop — **no manual version bump on the
  device.**
- For a non-`release-*` ref (e.g. a tag), pass `--version X.Y` explicitly.

## Prerequisites (one-time)

1. **A public `live` branch must exist.** Create an empty one if needed:
   ```bash
   git switch --orphan live && git commit --allow-empty -m "init live channel" \
     && git push -u origin live && git switch -
   ```
   (The first `publish.sh` run force-pushes over it anyway, but the device's first
   OTA check needs the branch to resolve.)
2. **The repo / `live` branch must be public** (the device fetches without a token).
3. The GitHub Action only auto-fires once it's on the **default branch (`main`)** —
   `create`-triggered workflows run from the default branch's copy. Until merged,
   use the manual path below.

## Cutting a release

### Option A — automated (after the workflow is on `main`)

```bash
# from the commit you want to release:
git switch -c release-1.96
git push -u origin release-1.96
```

Creating the `release-1.96` branch triggers `.github/workflows/publish-live.yml`,
which runs `scripts/publish.sh release-1.96` and force-pushes the built
`manifest.json` + `files/` onto `live`. Devices pick it up on their next check.

### Option B — manual (local), or before the workflow lands

```bash
git switch -c release-1.96 && git push -u origin release-1.96   # the archive branch
scripts/publish.sh release-1.96 --dry-run                       # inspect first
scripts/publish.sh release-1.96                                 # build + force-push to live
```

`--dry-run` builds and verifies the manifest/payload and prints the file list
**without pushing** — always do this first.

## Rollback

`live` is disposable; the `release-*` branches are the durable record. To roll
back, just re-publish an older archive:

```bash
scripts/publish.sh release-1.95            # locally, or…
```
…or run the **workflow_dispatch** trigger with `ref: release-1.95`. Either way the
older manifest/payload is force-pushed back onto `live`; devices that already
applied 1.96 will *not* downgrade automatically (semver compare only moves forward),
so a rollback also means cutting a higher version from the good code if you need
fielded devices to move.

## How apply / restore behaves on the device (for reference)

- `/update` (web) or a boot check → `OTAGlue.schedule_update()` checks, computes the
  **delta** (only files whose on-device sha256 differs from the manifest), downloads
  just those to the staging dir, then reboots. The free-space guard is sized to the
  delta (`2 × delta + headroom`), not the whole manifest.
- Next `setup()` → `install_pending()` shows **"Installing… do not unplug!"**, backs
  up the changed files, installs them (writing `/src/.version` last as the commit
  marker), verifies the **whole** tree against the manifest, and reboots into the new
  version. On failure — or a power cut, via `boot.py` — it restores the changed files
  from `/backup` **and deletes any files the update newly created** (they have no
  backup), so a rolled-back tree has no orphans. `secrets.py` / `settings.json` are
  untouched (never in the payload).
- Verify on hardware: success path (T041), corrupt/restore path (T042),
  credentials+settings survive (T042) — see `specs/001-this-project-is/tasks.md`.

## Files

- `scripts/publish.sh` — the publisher (shared by local use and the Action).
- `scripts/make_manifest.py` — builds `manifest.json` + `files/` from a source tree.
- `.github/workflows/publish-live.yml` — `on: create` for `release-*` → `publish.sh`.

> When the ScrollKit library ships a desktop `scrollkit.ota.publish` tool, retire
> `scripts/make_manifest.py` and point `publish.sh` at it (see tasks.md).
