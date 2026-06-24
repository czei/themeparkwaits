# Contract: OTA release & update flow

Created from plan-gate review **B3** (and S8/S4). The OTA *direction* is settled: the device reads a **fixed public `live` channel branch** + `manifest.json` via `scrollkit.ota.OTAClient.for_github(branch="live")`, no device-side auth (research D8). `live` is the one branch the device reads; `release-MAJOR.MINOR` branches/tags are immutable archives that CI/script mirrors onto `live` (named distinctly to avoid a `releases`/`release-2.1` clash). This contract makes it **taskable and safe** before `/update` and the device OTA code are built. It changes the release-publishing process and the product's security posture, so the items below need explicit sign-off, not just implementation.

## Security / access posture (must be accepted explicitly)
- The `live` channel branch (and the repo) is **world-readable**. Confirm nothing private ships in release content.
- SHA-256 in the manifest verifies **file integrity**, not **publisher authenticity** — anyone who can write the public branch can publish an update. Access control now rests entirely on **who can push to the branch**. Document that this is acceptable, or add signing (out of current scope).

## Manifest (`manifest.json`)
- **Schema**: `{ "version": "<semver>", "files": { "<device_path>": { "size": <int>, "checksum": "<sha256>" }, ... }, "pre_update_scripts"?: [...], "post_update_scripts"?: [...] }`.
- **`version`** drives the semantic-version compare against the device's `current_version`.
- **Path semantics**: confirm how `OTAClient.for_github` maps each manifest `files{}` key to an on-device location (re-verify item, see `scrollkit-api-consumption.md`).

## Manifest generation (release pipeline — app/devops side, a real task)
- A repeatable command/script generates `manifest.json` from the release tree: enumerate files, compute sizes + SHA-256, stamp `version`.
- **Path allowlist + exclusions**: explicitly EXCLUDE device-local/private files — **`secrets.py`, `settings.json`, `error_log`/logs, any token**, and anything the device owns. An update must never overwrite WiFi credentials or user settings (ties to S4).
- Decide whether **`scrollkit/` itself is OTA-managed** (so library upgrades ship to fielded devices) or frozen at flash time. If managed, it is part of the file set and the RAM/flash budget.
- Define how the device's **`current_version`** is read and **bumped** after a successful apply.

## Device update flow
- **Check**: `OTAClient.for_github(owner, repo, branch="live", current_version=...)` → `check_for_updates()` (in `setup()` and/or via `/update`).
- **`/update` route semantics**: the POST **schedules + downloads**, then **reboots**; `apply_update()` runs in the next `setup()` (NOT inline in the request handler — avoids applying/rebooting mid-request). Mirrors the old `next/`→reboot→install intent on the library's backup/restore machinery.
- **Apply**: `apply_update()` backs up current files, installs, runs post scripts; on failure it **restores from backup**. Verify the device has enough free storage for the backup set (**storage headroom** check is a task).
- **UX**: "Installing… do not unplug" + progress via `OTAClient.set_callbacks(on_available, on_progress, on_complete, on_error)`; `reboot_device()` to finish.
- **Rollback test (required)**: simulate a failed/corrupt update and confirm backup-restore leaves a bootable device.

## `use_prerelease` (review S8)
- Orphaned under the public-branch model (the old token + GitHub-Releases-API prerelease channel is gone). Either **remove** the setting (defaults + bool_keys + web form), or **remap** it to a separate prerelease branch/manifest and document that mapping here. Do not leave it documented as "read by OTA" with no behavior.

## Acceptance (hardware — part of the B4 checklist)
- Fresh manifest published → device detects newer `version`, downloads, applies, reboots into it.
- Corrupt/failed update → restore path yields a bootable device, prior version intact.
- Credentials + settings survive an update (exclusion list works).
