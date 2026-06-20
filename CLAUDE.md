# CLAUDE.md — ThemeParkWaits

CircuitPython app for a Matrix Portal S3 (64×32 RGB LED matrix) that shows live theme-park ride wait times. Boots `code.py` → `src/themeparkwaits` → `src/main.py`.

## Active feature
**001 — Port to the refactored ScrollKit library** (`specs/001-this-project-is/`). Re-platform every subsystem the library provides onto `scrollkit.*`; keep only theme-park domain code. Staged: port → optimize → dead-code removal. See `plan.md`, `research.md`, `contracts/`.

## Tech stack
- **CircuitPython** (device) + **CPython 3.11+** (desktop simulation).
- **ScrollKit library** at `../ScrollKit Library` → `scrollkit.*`: `app` (`ScrollKitApp`), `display` (`UnifiedDisplay`, `ContentQueue`, `ScrollingText`/`StaticText`/`DisplayContent`), `effects` (`RevealEffect`), `network` (`WiFiManager`, `HttpClient`), `config` (`SettingsManager`), `ota` (`OTAClient`), `web` (`SLDKWebServer`, handlers), `utils` (`ErrorHandler`, `Timer`, `ColorUtils`, `set_system_clock`, `url_decode`).
- Adafruit CircuitPython `.mpy` bundle vendored in `src/lib/`; `scrollkit/` copied to device `/lib/`.
- Data: queue-times.com JSON (`parks.json`, `parks/{id}/queue_times.json`). Settings in `settings.json`; WiFi creds in `secrets.py`.

## Key migration facts
- The app's old `settings_manager`/`wifi_manager`/`http_client`/`unified_display`/`utils`/`ota`/`web_server` are **hand-rolled copies that diverged from the old library** — the refactor extracted clean versions into `scrollkit.*`. Port = replace app-local subsystem with the `scrollkit` import.
- **Stays app code (library gaps)**: queue-times.com client + `src/models/*`; sort/filter/group/multi-park rules; the **dual-zone ride screen** (scrolling name + 2× wait number + "Closed") as a custom `DisplayContent`; the config-page HTML/routes content; mDNS hostname; the OTA *release* glue.
- **App framework**: subclass `ScrollKitApp(enable_web=True, update_interval=300)`; `setup()` = boot sequence (splash→wifi→OTA-install→clock→fetch), `update_data()` = 5-min refresh, content via `self.content_queue`.

## Efficiency rules (Phase 2 — from the library's docs)
Reuse a `Label`, change `.text` only on value change; move `.x` for scrolling; never allocate `Label`/`Bitmap`/`Group` per frame; use `bitmap.fill`/`bitmaptools.blit` over per-pixel loops; keep `bit_depth=4`; chunk heavy work + paint a loading frame before the synchronous HTTP fetch. No numeric perf budget (no history of issues) — just don't regress.

## OTA (resolved 2026-06-20)
Use `scrollkit.ota.OTAClient.for_github(owner, repo, branch="releases", current_version=...)` against a **public `releases` branch + `manifest.json`** — no device-side token. Reproduce the "Installing… do not unplug" UX via `set_callbacks` + `reboot_device`. The only app-side delta is the release pipeline emitting `manifest.json` (version + per-file checksums). The old private-repo + GitHub-Releases-API + `next/`/`.version` flow is retired.

## Dev commands
- Simulator: `PYTHONPATH="../ScrollKit Library/src:src" python -m src.themeparkwaits --dev`
- Device-speed estimate: prefix `SCROLLKIT_HW_SIM=1` (feel the crawl: `SCROLLKIT_HW_THROTTLE=1`).
- Tests: `pytest tests/` (domain, mocked `HttpClient`) + `scrollkit.dev.run_headless/validate/capabilities`.

## Conventions
- `scrollkit/__init__.py` does no eager imports — import submodules on demand (RAM).
- Verify "unimported" with grep before deleting any module (dead-code list in `research.md`).
- HTTP (`adafruit_requests`) is synchronous — it pauses the display loop; chunk and show a loading frame.

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
