# CLAUDE.md — ThemeParkWaits

CircuitPython app for a Matrix Portal S3 (64×32 RGB LED matrix) that shows live theme-park ride wait times. Boots `code.py` → `src/themeparkwaits` → `src/main.py`.

## Active feature
**002 — Source wait times from themeparks.wiki** (`specs/002-themeparks-wiki-api/`). Replaced queue-times.com with the themeparks.wiki API (catalog + live data); no queue-times anywhere. Domain-layer change only (`theme_park_service`, `models/*`, `content_builder` attribution, `config_server` park selection). Simulator-validated against the live API (139 parks; Magic Kingdom 35 attractions); hardware free-heap check (R1) pending. See its `plan.md`, `research.md`, `data-model.md`, `contracts/`.

**Prior: 001 — Port to the refactored ScrollKit library** (`specs/001-this-project-is/`). Re-platform every subsystem the library provides onto `scrollkit.*`; keep only theme-park domain code.

**Status (simulator-complete):** Milestone A done on the desktop simulator — boots, fetches live data, reveal splash, ride screens (scrolling name + 2× number), config web UI (:8080), OTA glue, resilience guards. 26 tests pass; dead code removed; hardware feasibility ~135 FPS / 1 KB RAM, no warnings. **Remaining: on-device verification (hardware checklist T035–T043), first-boot AP onboarding (device-only), and the boot-state-machine reboot branches.**

### Final source layout (everything else runs on `scrollkit.*`)
```
boot.py, code.py, src/themeparkwaits.py, src/main.py   # entry / bootstrap
src/app.py                 # ThemeParkApp(ScrollKitApp): setup/update_data/show_loading/create_*
src/settings_schema.py     # DEFAULTS + bool_keys for scrollkit.config.SettingsManager
src/ota_glue.py            # GitHub channel config (owner/repo/branch + .version) over scrollkit.ota.display_progress
src/diagnostics.py         # re-export shim -> scrollkit.utils.diagnostics (kept for back-compat/rollback)
src/api/theme_park_service.py   # themeparks.wiki fetch/parse on scrollkit HttpClient
src/models/*               # ThemePark / Ride / List / Vacation (domain)
src/ui/ride_screen_content.py   # RideScreenContent + ClosedRideContent (dual-zone)
src/ui/tpw_display.py      # ThemeParkDisplay(UnifiedDisplay) + draw_text_scaled (2x number)
src/ui/content_builder.py  # sort/group/filter/vacation/attribution -> ContentQueue
src/ui/reveal_splash.py    # opening reveal (all LEDs on -> wink off -> THEME PARK WAITS)
src/web/config_server.py   # SLDKWebServer + config form handler
scripts/make_manifest.py   # OTA release manifest generator (devops)
tools/sim_shot.py          # headless screenshot helper for layout iteration
```
mDNS advertising, NVM boot diagnostics, the OTA display-progress/staged-install
flow, render-suspend, and palette-text completion now live in `scrollkit.*`
(`scrollkit.network.mdns`, `scrollkit.utils.diagnostics`,
`scrollkit.ota.display_progress`, `ScrollKitApp.suspended_render()`,
`BitmapText(complete_after_passes=...)`). The app keeps only its config/policy.

## Tech stack
- **CircuitPython** (device) + **CPython 3.11+** (desktop simulation).
- **ScrollKit library** at `../ScrollKit Library` → `scrollkit.*`: `app` (`ScrollKitApp`), `display` (`UnifiedDisplay`, `ContentQueue`, `ScrollingText`/`StaticText`/`DisplayContent`, `GradientTextLayer`), `effects` (`transition_factory`/`supported_names`, `SwarmReveal`), `network` (`WiFiManager`, `HttpClient`), `config` (`SettingsManager`), `ota` (`OTAClient`), `web` (`SettingsWebServer`), `utils` (`ErrorHandler`, `ColorUtils`, `set_system_clock`, `url_decode`).
- Adafruit CircuitPython `.mpy` bundle vendored in `src/lib/`; `scrollkit/` copied to device `/lib/`.
- Data: **themeparks.wiki** API (no auth) — `GET /v1/destinations` (catalog) + `GET /v1/entity/{parkId}/live` (wait times; `queue.STANDBY.waitTime`, status `OPERATING`/`DOWN`/`CLOSED`/`REFURBISHMENT`). Park ids are UUID strings. Per-park `/live` is ~90 KB, so selected parks are fetched **sequentially** with `gc.collect()` between them (one payload in RAM at a time). Settings in `settings.json`; WiFi creds in `secrets.py`.

## Key migration facts
- The app's old `settings_manager`/`wifi_manager`/`http_client`/`unified_display`/`utils`/`ota`/`web_server` are **hand-rolled copies that diverged from the old library** — the refactor extracted clean versions into `scrollkit.*`. Port = replace app-local subsystem with the `scrollkit` import.
- **Stays app code (library gaps)**: themeparks.wiki client + `src/models/*`; sort/filter/group/multi-park rules; the **dual-zone ride screen** (scrolling name + 2× wait number + "Closed") as a custom `DisplayContent`; the config-page HTML/routes content; the OTA GitHub channel config (`src/ota_glue.py` — owner/repo/branch + `.version`). (mDNS, NVM diagnostics, OTA display-progress, render-suspend, and palette-text completion were extracted UP into `scrollkit.*` in the 0.9.0 refactor.)
- **App framework**: subclass `ScrollKitApp(enable_web=True, update_interval=300)`; `setup()` = boot sequence (splash→wifi→OTA-install→clock→fetch), `update_data()` = 5-min refresh, content via `self.content_queue`.

## Efficiency rules (Phase 2 — from the library's docs)
Reuse a `Label`, change `.text` only on value change; move `.x` for scrolling; never allocate `Label`/`Bitmap`/`Group` per frame; use `bitmap.fill`/`bitmaptools.blit` over per-pixel loops; keep `bit_depth=4`; chunk heavy work + paint a loading frame before the synchronous HTTP fetch. No numeric perf budget (no history of issues) — just don't regress.

## OTA (resolved 2026-06-20)
Device reads a **fixed public `live` channel branch**: `scrollkit.ota.OTAClient.for_github("czei", "themeparkwaits", branch="live", current_version=...)` → `manifest.json` + `files/` over raw.githubusercontent (no device token). Reproduce "Installing… do not unplug" via `set_callbacks` + `reboot_device`. Release model (hybrid, Option C): cut a release by creating a `release-MAJOR.MINOR` archive branch; CI/script mirrors its `manifest.json` + `files/` onto `live` (the one branch the device reads). The old private-repo + GitHub-Releases-API + `next/`/`.version` flow is retired.

## Dev commands
- Simulator: `PYTHONPATH="../ScrollKit Library/src:src" python -m src.themeparkwaits --dev`
- Device-speed estimate: prefix `SCROLLKIT_HW_SIM=1` (feel the crawl: `SCROLLKIT_HW_THROTTLE=1`).
- Tests: `pytest tests/` (domain, mocked `HttpClient`) + `scrollkit.dev.run_headless/validate/capabilities`.

## Conventions
- `scrollkit/__init__.py` does no eager imports — import submodules on demand (RAM).
- HTTP (`adafruit_requests`) is synchronous — it pauses the display loop; chunk and show a loading frame.
- Iterate on layout from screenshots: `tools/sim_shot.py` / `run_headless(..., screenshot=...)` (SDL_VIDEODRIVER=dummy).

## Gotchas (learned the hard way — see SCROLLKIT_NOTES.md)
- **`draw_text` `y` is the text BASELINE** (top-down, origin top-left). `y=0` clips the glyph off the top; center a single line in the mid-teens. (Scroll text `y=13`, ride name `y=5`, big number `y=21`.)
- **Don't `import displayio` / `import wifi` bare** on desktop — stray Blinka/`wifi` PyPI packages shadow the platform modules. Import `displayio` from `scrollkit.display.unified`; detect platform via `sys.implementation.name == 'circuitpython'` (NOT the library's `is_dev_mode()`, which the stray `wifi` package fools).
- **Raw `display.set_pixel()`/`fill()` don't render in the simulator** — draw pixels via a `Bitmap`+`TileGrid` appended to `display.main_group` (see `reveal_splash.py`).

- Clean the desktop dev env of the shadowing packages: `pip uninstall wifi displayio`.

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
