# Phase 0 Research: Port ThemeParkWaits to the Refactored ScrollKit Library

**Feature**: `001-this-project-is` | **Date**: 2026-06-20

This document resolves the technical unknowns behind the spec and records the per-subsystem migration decisions. The governing constraint (from the spec Clarifications, 2026-06-20): **every subsystem the library provides MUST run on the library; app-unique code survives only where the library genuinely lacks a capability.**

## Key finding that shapes the whole port

The current app does **not** vendor an old copy of ScrollKit. Instead, the subsystems that became the library (`SettingsManager`, `WiFiManager`, `HttpClient`, `UnifiedDisplay`, the `utils/*` helpers, OTA, web server) were **hand-rolled inside the app and then diverged**. The refactor lifted clean versions of exactly these into `scrollkit.*`. So the port is mostly **"delete the app-local subsystem, import the `scrollkit` equivalent, keep only theme-park domain code"** — not a from-scratch rewrite. This is why "ALL subsystems on the library" is both achievable and the natural shape of the work.

What is genuinely **domain-only** (stays in the app): the queue-times.com client + JSON parsing, the `ThemePark` / `ThemeParkRide` / `ThemeParkList` / `Vacation` models, the sort/filter/group/multi-park rules, the **dual-zone ride screen** widget (scrolling name + large wait number + "Closed"), the config-page HTML/routes content, the mDNS hostname, and the product's OTA release contract.

---

## Decisions (Decision / Rationale / Alternatives)

### D1 — App framework: subclass `scrollkit.app.ScrollKitApp`
- **Decision**: Make the app's top-level class extend `ScrollKitApp(enable_web=True, update_interval=300)`. Map the current `ThemeParkApp.initialize_all()` boot sequence into the async `setup()` hook; map the 5-minute data refresh into `update_data()`; build display content via `self.content_queue` and `prepare_display_content()`; override `create_display()` → `UnifiedDisplay`, `create_web_server()` → the app's config server. Use `show_loading()` to **pre-flush a static loading frame before** each synchronous fetch (it cannot animate during the blocking call).
- **Rationale**: `ScrollKitApp.run()` already provides the three cooperative processes (display always; data ≥~30 KB free; web ≥~50 KB free) the app builds by hand with `asyncio.gather`. Reusing it deletes the app's custom loop and gives graceful degradation for free.
- **Lifecycle (review B1)**: the multi-step blocking boot (splash → WiFi/AP onboarding → station connect → OTA install → NTP → fetch → build queue) runs inside `setup()`, which executes **before** `run()` spawns the loops. It is a linear pre-run state machine that draws status **directly** (`clear→draw→show`, not via the queue), and its **AP-onboarding and OTA-install branches each end in a reboot** and never start the normal config server (no double web server, no reboot-mid-loop). Full sequence + invariant in plan.md "Boot Lifecycle".
- **Alternatives**: `MinimalLEDApp` (too small — no web/data processes); keep the app's own loop (violates "all subsystems on the library").

### D2 — Display primitives: `scrollkit.display.UnifiedDisplay` (bit_depth=4)
- **Decision**: Render through the library's `UnifiedDisplay` and content types. Generic scrolling/static messages (config URL, "updating…", attribution, vacation countdown, closed-park, errors) become `ScrollingText` / `StaticText`. Splash branding uses `scrollkit.effects.reveal.RevealEffect`.
- **Rationale**: The library auto-detects hardware vs. simulator, owns the label pool, and bakes in the efficiency rules. The app's `unified_display.py`, `hardware_display.py`, `pyledsimulator_display.py`, `simulator_display.py`, `display_factory.py`, `display_base/impl/interface.py` all collapse into library calls.
- **Alternatives**: keep the app's `UnifiedDisplay` (it is the diverged copy — drop it).

### D3 — Ride screen is a custom `DisplayContent` (a real library gap)
- **Decision**: Implement `RideScreenContent(DisplayContent)` and `ClosedRideContent(DisplayContent)` in the app. `render()` composes two regions via `display.draw_text(...)`: scrolling ride **name** on top, large centered wait **number** on the bottom (or "Closed"). The big number needs 2× scale — use a larger bitmap font (the app already ships `src/fonts/Teeny-Tiny-Pixls-5.bdf` and `tom-thumb.bdf`; `adafruit_bitmap_font` is already vendored) or a `displayio` group at `scale=2`.
- **Rationale**: The library deliberately has **no multi-region layout and no font scaling** (confirmed in the API survey). This widget is product-specific presentation → legitimately app code, but built entirely on library draw primitives.
- **Constraints (review S1/B2)**: `render()` MUST use only `UnifiedDisplay` primitives (no bypassing the display or owning matrix refresh); **load the font once** (no per-frame `Label`/`Bitmap`/`Group` allocation). **First resolve** whether `UnifiedDisplay.draw_text`/`clear`/`show` are sync or async and whether a `DisplayContent.render(display)` may call them directly — the API survey listed `draw_text` as **async** but `render(display)` as a plain override; reconcile against live source before coding (also tracked in `contracts/scrollkit-api-consumption.md` §"Re-verify before coding"). Define `is_complete`/`duration` for the simultaneous scrolling-name + static-number screen, and clarify whether `render()` or the framework owns the per-frame `clear()`/`show()`.
- **Alternatives**: two separate queue items (loses the simultaneous name+number layout — fails FR-002); fork the library to add a layout widget (out of scope).

### D4 — Content ordering stays in the app; the queue mechanism is the library's
- **Decision**: Delete `src/ui/message_queue.py`'s queue machinery; keep its **domain rules** (sort alphabetical/max/min, group-by-park, skip-closed, skip-meet, up-to-4 parks, vacation insertion, attribution) as a "content builder" that emits library content objects into `self.content_queue`. Rebuild the queue on data refresh and on settings change.
- **Rationale**: Sorting/filtering/grouping is theme-park domain logic the library can't own; the FIFO/advance mechanics are exactly `ContentQueue`.
- **Alternatives**: `DisplayQueue` (priority/eviction) — not needed for a simple cycle; `ContentQueue(loop=True)` matches today's "cycle then refresh."

### D5 — Networking: `scrollkit.network.WiFiManager` + `HttpClient`, NTP via `utils.system_utils`
- **Decision**: Use `WiFiManager(settings_manager)` for station connect **and** first-time AP/captive-portal onboarding + `create_http_session()`; use `HttpClient` for all fetches; sync the clock with `scrollkit.utils.system_utils.set_system_clock(http_client, socket_pool, tz_offset=-5)`. Delete `src/network/wifi_manager.py`, `wifimgr.py`, `http_client.py`, `http_client_original.py`, `async_http_request.py`, `src/async_http_request.py`.
- **Rationale**: The library's `WiFiManager` already implements the AP + `/configure` onboarding the app duplicates. NTP+HTTP-date fallback is richer than the app's.
- **Gap kept in app**: **mDNS hostname** (`device.local`) — not in the library; a thin app helper using `adafruit_mdns` stays. **Verify (R3)** it coexists with `SLDKWebServer` on the device (shared socket pool; mDNS start ordering relative to WiFi/web).
- **Credential storage (review S4)**: pin down whether WiFi creds live in `secrets.py`, in `settings.json`, or both — matching what the library `WiFiManager` actually reads — preserve existing creds across the port, and **exclude them from the OTA file set** so updates never overwrite them.

### D6 — Config: `scrollkit.config.SettingsManager`
- **Decision**: Use `SettingsManager(filename="settings.json", defaults={...}, bool_keys=[...])`. Pass the full app default set (domain_name, brightness_scale, colors, scroll_speed, sort_mode, group_by_park, skip_closed, skip_meet, display_mode, use_prerelease, selected_park_ids, next_visit*). Reuse the library's built-in scroll-speed map (Slow 0.06 / Medium 0.04 / Fast 0.02). Delete `src/config/settings_manager.py`.
- **Rationale**: Identical responsibility and file format; the library version handles the CircuitPython bool-as-string quirk via `bool_keys` and missing-key defaults — preserving FR-011.

### D7 — Web config UI: `scrollkit.web.SLDKWebServer` + handlers (HTML stays app content)
- **Decision**: Override `create_web_server()` to return a `SLDKWebServer` whose `WebHandler` subclass defines the themeparkwaits routes (`/`, `/settings`, `/style.css`, `/update`). Keep the `src/www/` assets (served via `StaticFileHandler`) and build the settings form with `FormBuilder`/`HTMLBuilder`. Form POST → `SettingsManager.set/save` → trigger content rebuild (and `/update` → OTA schedule). Delete `web_server.py`, `dev_web_server.py`, `unified_web_server.py`, `web_server_core.py`, `server_adapters.py`, `web_server.py.old.py`.
- **Rationale**: The library owns the server, request loop, and the CircuitPython(adafruit_httpserver)/desktop(aiohttp) adapter split; only the **page content + which settings exist** is product-specific (a genuine gap), so that stays — built on library base classes.

### D8 — OTA: adopt `scrollkit.ota.OTAClient` — **highest-risk item**
- **Decision**: Replace `src/ota/ota_updater.py` with `scrollkit.ota.OTAClient` (use `OTAClient.for_github(owner, repo, branch, current_version=...)` + its `manifest.json`/checksum/backup flow and `set_callbacks` for the "Installing… do not unplug" progress messaging). Drive `check_for_updates()` / `download_update()` / `apply_update()` from `setup()` / a `/update` route.
- **Rationale**: The mandate is "all subsystems on the library," and the library's OTA is safer (checksums + backup/restore).
- **Mechanism change (RESOLVED 2026-06-20)**: today's OTA uses the **GitHub Releases API with an auth token (private `themeparkwaits.release` repo)** + download-to-`next/` + `.version` marker + install-on-reboot. The library's `OTAClient` is **manifest-driven over raw content URLs**. **Decision: move release content to a publicly-readable `releases` branch and add a `manifest.json`** (version + per-file size/checksum); the device uses `OTAClient.for_github(owner, repo, branch="releases", current_version=...)` with **no device-side auth**. This is the cleanest fit and removes the token from the device entirely.
  - **Publishing-process delta (not device code)**: the release pipeline must now emit `manifest.json` alongside the source files on the public `releases` branch. The library handles version compare, SHA-256 verify, and backup/restore on the device.
  - **No private-repo token auth needed** — the previously-considered token adapter is dropped.
  - **Channel branch renamed (supersedes the `releases` name used in this log): the fixed device-read branch is `live`.** `release-MAJOR.MINOR` branches/tags are immutable archives that CI/script mirrors onto `live` (hybrid Option C, multi-model consensus). The repo is also now `czei/themeparkwaits` (renamed from `Czeiszperger/themeparkwaits.release`). `ota_glue.py` uses `branch="live"`.
- The user-facing install UX ("Installing… do not unplug", install-on-reboot) is reproduced via `OTAClient.set_callbacks(...)` + `reboot_device()`.
- **Release/update contract (review B3) → `contracts/ota-release.md`**: specifies the manifest schema + generation command, the path **allowlist that excludes `secrets.py` / `settings.json` / logs**, how `current_version` is read and bumped, whether `scrollkit/` itself is OTA-managed, backup/restore storage headroom, a rollback test, and `/update` semantics (schedule + download, then reboot; call `apply_update()` only in `setup()`). **Public-branch trade-off**: releases become world-readable and SHA-256 gives integrity, not publisher authenticity — accept explicitly. **`use_prerelease` is now orphaned (S8)** (no token/Releases-API channel) → remove it, or remap it to a separate manifest/branch.

### D9 — Simulator/dev: drop PyLEDSimulator, use the library
- **Decision**: Remove the dependency on the external PyLEDSimulator and the app's `--simple-sim`/Pygame fallbacks. Desktop dev uses the library's `SimulatorDisplay` (via `UnifiedDisplay` auto-detect). Validate device behavior with the library's **hardware-timing simulation** (`SCROLLKIT_HW_SIM=1`, and `SCROLLKIT_HW_THROTTLE=1` to feel real device speed).
- **Rationale**: One simulator, owned by the library, calibrated to a real MatrixPortal S3. Advisory per FR-025 (not a blocking gate, since the app has no history of perf problems).

### D10 — Motion idiom: library-native
- **Decision**: Use the library's right-to-left `ScrollingText` and effect timings rather than reproducing the old left-to-right/edge-pause motion pixel-for-pixel (spec Clarification). Same information, library-idiomatic motion.

### D11 — Packaging/deployment
- **Decision**: On device, the library lives at `/lib/scrollkit/` (copy `ScrollKit Library/src/scrollkit/` into the device `lib/`, alongside the existing vendored adafruit `.mpy` bundle in `src/lib/`). For desktop dev, put `"<repo>/../ScrollKit Library/src"` on `sys.path` (or `pip install -e` the library with its `[simulator]` extra). Compiling `scrollkit` to `.mpy` is normally a deploy optimization — **but if the data/web processes get memory-gated off on real hardware, it becomes a parity requirement, not optional** (review S7/R4). The Milestone A deployment task must measure free heap on device and confirm both processes spawn.
- **Rationale**: The library ships as `.py` source with no build step; demos import `scrollkit` from `src/` on `PYTHONPATH`. Mirror that.

### D12 — Phase 2 efficiency techniques (documented by the library)
Apply in the separate optimization pass (FR-019–023): reuse a `Label` and change `.text` only on value change; move `.x` for scrolling instead of rebuilding; never allocate `Label`/`Bitmap`/`Group` per frame; use `bitmap.fill`/`bitmaptools.blit` over per-pixel Python loops; keep `bit_depth=4`; chunk heavy compute and paint a loading frame before the synchronous HTTP fetch; rely on `ScrollKitApp`'s memory-gated graceful degradation. No numeric budget (FR-024) — the app has no history of memory/perf issues; just don't regress vs. the Phase-1 port.

---

## Dead-code inventory (deleted per-subsystem during Milestone A; final grep audit in C — FR-027, review B5)

**Superseded by library imports**: `src/config/settings_manager.py`, `src/network/wifi_manager.py`, `src/network/wifimgr.py`, `src/network/http_client.py`, `src/network/http_client_original.py`, `src/network/async_http_request.py`, `src/async_http_request.py`, `src/network/web_server.py`, `src/network/dev_web_server.py`, `src/network/unified_web_server.py`, `src/network/web_server_core.py`, `src/network/server_adapters.py`, `src/network/web_server.py.old.py`, `src/ui/display_factory.py`, `src/ui/display_base.py`, `src/ui/display_impl.py`, `src/ui/display_interface.py`, `src/ui/unified_display.py`, `src/ui/hardware_display.py`, `src/ui/pyledsimulator_display.py`, `src/ui/simulator_display.py`, `src/ui/message_queue.py`, `src/ui/reveal_animation.py`, `src/utils/*` where a `scrollkit.utils` equivalent exists, `src/color_utils.py`, `src/image_processor.py` (root dup), `src/memory_tracker.py` (if unused), `src/ErrorHandler.py`.

**Already-dead duplicates (delete regardless)**: `src/ota_updater.py` + `src/ota.py` + `src/ota/ota.py` (root/dup stubs importing a non-existent `app.ota_updater`), `src/theme_park_api.py`, `src/theme_park_display.py`, `src/ui/roller_coaster_animation.py`, `src/ui/roller_coaster_animation_cp.py`, `src/webgui.py`, `src/shopify_connect.py` (imports dead `theme_park_api`), `src/pixeldust.py` (if unused).

**Kept (domain)**: `src/models/*`, `src/api/theme_park_service.py` (reworked onto `HttpClient`), the new `RideScreenContent`/content builder, `src/www/*` assets, `src/fonts/*`, `src/images/*`, a small mDNS helper, the OTA glue (per D8). `boot.py` / `code.py` / `src/main.py` / `src/themeparkwaits.py` are reworked to construct the new `ScrollKitApp` subclass.

> **Interleaved deletion (review B5)**: delete each module as its `scrollkit` replacement lands within Milestone A — do **not** defer all deletion to the end — to avoid half-migrated state and name collisions (two `SettingsManager`, two `WiFiManager`, two `UnifiedDisplay`). Add an **import-guard** so the legacy modules can't be re-imported. Verify "not imported" with a grep pass before each deletion; Milestone C is a final grep audit, not the first cleanup pass. (FR-027 is gated on the parity build still running.)

---

## Open risks

- **R1 (OTA) — RESOLVED 2026-06-20**: adopt `scrollkit.ota.OTAClient.for_github` against a **public `releases` branch + `manifest.json`**, no device-side auth (see D8). Release/update details (manifest schema, path allowlist, `/update` semantics, rollback) live in `contracts/ota-release.md`. No longer blocking.
- **R2 (large-number font)** — the 2× wait-time number depends on a bitmap font + scaling approach that renders crisply at 64×32; pick during the ride-screen task and screenshot-verify.
- **R3 (mDNS gap)** — `device.local` resolution remains app code; verify it coexists with the library's web server socket/adapter on device (shared socket pool; start ordering).
- **R4 (memory headroom of `.py` vs `.mpy`)** — shipping `scrollkit` as source may raise RAM/flash use vs. the app's `.mpy` bundle. **If the memory gates skip the data/web processes in normal operation, compiling `scrollkit` to `.mpy` is a parity fix, not optional** (review S7); the deployment task must measure free heap and confirm both processes spawn.

## Testing approach
Desktop: pytest against the domain layer (models, sort/filter/group, vacation math incl. tomorrow/today, closed/zero-wait decisions) with a mocked `HttpClient`; library dev harness `scrollkit.dev.run_headless(app, frames=N, screenshot=...)`, `validate(app)`, and `capabilities()` for display/content checks; `SCROLLKIT_HW_SIM=1` for a device-speed estimate.

**Device — REQUIRED before any OTA release (review B4)**: the most fragile behaviors are device-only and regressions ship via OTA, so the desktop sim alone is insufficient. Walk the hardware acceptance checklist in `quickstart.md`: fresh-device AP onboarding; wrong/unavailable WiFi resilience; station connect + NTP; mDNS **and** raw-IP config page; settings POST rebuild **without** a network fetch; multi-park synchronous-HTTP refresh; OTA success path **and** a simulated failure/restore; web+data+display coexistence. **Record free heap/FPS at checkpoints and confirm the data/web processes actually spawn** — if memory-gating skips them, parity silently fails (ties to R4/S7).

**Output**: all spec [NEEDS CLARIFICATION] markers were resolved (Clarifications 2026-06-20) and the OTA decision (R1) is resolved (public `releases` branch + `manifest.json`). No unresolved **design** decisions remain; the plan-gate review findings (B1–B5, S1–S10, N1–N5) are folded into the Milestone A tasks, the Boot Lifecycle / Parity Matrix in plan.md, and `contracts/ota-release.md`. Tracked implementation risks R2–R4 carry into tasks.

---

## Verified API (T003 — checked against live `../ScrollKit Library/src/scrollkit/` source, 2026-06-20)

**Big picture:** `config/settings_manager.py`, `network/http_client.py`, `network/wifi_manager.py`, and `web/server.py` all carry *"Copyright 2024 3DUPFitters LLC"* / *"Extracted from Theme Park API"* — **they are this app's own subsystems lifted into the library**. The port is a near drop-in: replace the local module with the `scrollkit.*` import. The 7 gate items, verified:

1. **App lifecycle (`app/base.py`)** — `SLDKApp`/`ScrollKitApp(enable_web=True, update_interval=300)`. `run()` calls `await self.setup()` **then** spawns 3 tasks (display always; data if free>30 KB; web if `enable_web` and free>50 KB at startup; data-process also skips an iteration if free<20 KB). Display loop = `clear() → content.render(display) → show()` at 20 FPS. `show()` returning `False` (sim window closed) shuts down. Hooks `setup/update_data/prepare_display_content/cleanup/show_loading` confirmed.
2. **Display sync/async (CORRECTION)** — `interface.py`: `draw_text`/`clear`/`show`/`fill`/`set_pixel`/`set_brightness`/`scroll_text` are **all `async`**; `base.py:141` does `await content.render(self.display)` so **`DisplayContent.render()` is async** and **the framework owns per-frame `clear()`/`show()`**. → `RideScreenContent` = `async def render(self, display)` that only draws (no clear/show), and gives itself a `duration` so the queue advances (T020/T021).
3. **`show_loading()`** — async, default no-op; `base.py` calls it before `update_data()` via `_render_loading()`. Confirmed (B2 design valid).
4. **`SettingsManager` (`config/settings_manager.py`)** — `(filename, defaults=None, bool_keys=None)`; **the scroll-speed map EXISTS** (`self.scroll_speed = {Slow:.06,Medium:.04,Fast:.02}`, `get_scroll_speed()`) → S9(c) resolved, no app helper needed. Auto-defaults `brightness_scale="0.5"`, `scroll_speed="Medium"`. `get/set/save_settings/load_settings/set_defaults/add_bool_keys/get_pretty_name`. **It is the app's own class.**
5. **`HttpClient` (`network/http_client.py`)** — `(session=None, mock_provider=None)`; `async get(url, headers=None, max_retries=3)` with retry+backoff; **never raises** — on total failure returns `MockResponse(status_code=500, text="{}")` (service must check `status_code`). Response: `.json()` (raises `ValueError` on bad JSON / status≥400), `.text/.content/.status_code/.headers/.close()`. Has `get_sync`, `set_use_live_data(False)` + `mock_provider` → **use these for the desktop test fixture (T002)**. Also the app's own class.
6. **`WiFiManager` (`network/wifi_manager.py`)** — `(settings_manager)`; `self.ssid,self.password = load_credentials()` → **credentials live in `secrets.py`** (S4 RESOLVED = secrets.py). `connect(display_callback=None)`, `reset()`; dev-mode (no `wifi` module) simulates connected. AP onboarding methods present. The app's own class.
7. **`OTAClient` (`ota/client.py`)** — `for_github(owner, repo, branch="releases", current_version="0.0.0", update_dir="/updates", backup_dir="/backup")` → base `https://raw.githubusercontent.com/{owner}/{repo}/{branch}`. Manifest at `{base}/manifest.json`; **files at `{base}/files/{path}`**; **manifest `files{}` keys are absolute on-device target paths** (install writes straight to them). `check_for_updates()→(bool, manifest|err)`, `download_update()` (verifies size+SHA256, needs 2× total free space), `apply_update()` (backup→install→restore-on-fail→set version), `set_callbacks(...)`, `reboot_device()`. → **T026 release layout = `manifest.json` (root) + `files/<device-path>/...`**.

**Web (`web/server.py`, item e)** — `SLDKWebServer(app=None, handler_class=None, socket_pool=None, static_dir=None)` → default `CompositeHandler(WebHandler, StaticFileHandler, APIHandler)`. Custom routes either by subclassing `WebHandler` or via `SLDKWebApplication().route(path, methods)` + `add_handler` → `create_server()`. Server is *"Extracted from Theme Park API"* → near drop-in. `start/stop/handle_requests/run_forever/get_server_url/is_running`. (Exact handler-method dispatch signature to confirm from `web/handlers.py` when building T023.)

**Effects** — splash uses `scrollkit.effects.reveal` (confirm `RevealEffect.apply(display, render_func)` shape at T020).

**Downstream task corrections**: T020/T021 (render async, framework owns clear/show, self-scroll); T015 (creds = `secrets.py`, S4 closed); T019 (`HttpClient` returns 500 not raises); T005/T026 (release = `manifest.json` + `files/<device-path>`, manifest keys = device paths). The library duplicate files `web/__init__ 2.py`, `web/handlers 2.py`, `web/templates 2.py` are editor cruft in the *library* — ignore (import the unsuffixed modules).
