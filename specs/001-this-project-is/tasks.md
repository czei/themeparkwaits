# Tasks: Port ThemeParkWaits to the Refactored ScrollKit Library

**Input**: Design documents in `/Users/czei/Documents/Projects/ScrollKit/themeparkwaits/specs/001-this-project-is/`
**Prerequisites**: plan.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓ (scrollkit-api-consumption, web-config-routes, queue-times-api, ota-release), quickstart.md ✓

> **Revised after the tasks-gate PAL review (2026-06-20)** — TB1 (split the boot machine + add the data-loop task), TB2 (extend the T003 block list), TB3 (OTA decisions task + `use_prerelease` resolved = **removed**), TB4 (scoped import guards), TB5 (mDNS wiring) and the should-fix/nit items are all incorporated; tasks renumbered.

## Context (read before executing)
This is a **port**, not greenfield: the app's diverged subsystems (`SettingsManager`, `WiFiManager`, `HttpClient`, `UnifiedDisplay`, `utils/*`, OTA, web server) are replaced by `scrollkit.*` imports; only theme-park **domain** code stays. "Tests first" is adapted to the target: automated gates are desktop **domain pytest + API-consumption smoke + headless render**; device-only behaviors (real WiFi, AP onboarding, OTA install/reboot, mDNS, RAM) are verified via the **hardware checklist** (Phase 3.5) — they cannot be unit-tested. Milestones: **A = port to parity → B = optimize → C = final cleanup audit**.

**Deletion protocol (every "DELETE" step):** ordered substeps — (1) replace imports with the `scrollkit` equivalent, (2) `grep -rn` for legacy references under `src/`, (3) run the import/boot smoke (`python -m src.themeparkwaits --dev` + `pytest tests/contract`), (4) delete the legacy file(s), (5) re-run the smoke. **Do not delete while references remain**; if a delete breaks the build, the module wasn't fully replaced — finish the migration rather than reverting blindly.

**Absolute repo root**: `/Users/czei/Documents/Projects/ScrollKit/themeparkwaits/`
**Library (sibling)**: `/Users/czei/Documents/Projects/ScrollKit/ScrollKit Library/`

## Format: `[ID] [P?] Description`
- **[P]** = different files, no dependency → may run in parallel.
- Every task names exact file paths.

---

## Phase 3.1: Setup & pre-coding decisions

- [X] **T001** Set up the desktop dev environment: install the library for simulation — `pip install -e "../ScrollKit Library[simulator]"` (or document `PYTHONPATH="../ScrollKit Library/src:src"`); confirm `python -c "import scrollkit"` works. Update `quickstart.md` if the invocation differs.
- [X] **T002** [P] Create the test tree: `tests/__init__.py`, `tests/domain/`, `tests/contract/`, and `tests/conftest.py` with a `mock_http_client` fixture (canned queue-times JSON) and a `settings_factory` fixture. *(Done; conftest adds `../ScrollKit Library/src` + `src` to sys.path; mock provider + SettingsManager verified working on desktop.)*
- [ ] **T003** ⚠️ **BLOCKING GATE — API re-verification spike** (review S9/B2): verify the 7 items in `contracts/scrollkit-api-consumption.md` §"Re-verify before coding" against live source under `../ScrollKit Library/src/scrollkit/` — esp. (a) whether `UnifiedDisplay.draw_text`/`clear`/`show` are sync or async and whether `DisplayContent.render(display)` may call them; (b) `show_loading()` shape; (c) whether `SettingsManager` exposes the scroll-speed map; (d) `WiFiManager` credential storage location; (e) `WebHandler` construction/app injection; (f) `HttpClient.get` retry/backoff + response lifecycle; (g) OTA manifest path semantics. Append findings as `## Verified API` to `research.md`. **Blocks every subsystem-coding task: T013, T015, T016, T018, T019, T020, T023, T026, T027.**
  - **[X] DONE (2026-06-20)** — all 7 items verified against live source; findings + 4 corrections recorded in `research.md` §"Verified API". Key results: library's settings/http/wifi/web are **this app's own subsystems extracted** (near drop-in); `DisplayContent.render()` is **async** and framework owns `clear()/show()`; `ScrollingText` scrolls 1px/frame; scroll-speed map **exists** in `SettingsManager`; WiFi creds = **`secrets.py`** (S4 closed); OTA files at `{base}/files/{device-path}`, manifest keys = device paths. **Gate cleared.**
- [ ] **T004** [P] Stage the library for the device: copy `../ScrollKit Library/src/scrollkit/` into the device deployment `lib/` (document the exact path in `CLAUDE.md`); the `.py`-vs-`.mpy` decision is made later under the device memory check (**T043**, R4/S7).
- [ ] **T005** OTA release decisions (review TB3/B3): in `contracts/ota-release.md`, pin the concrete values the impl needs — `owner`/`repo`, the `releases` branch policy, where `current_version` is read from and how it is bumped after apply, whether `scrollkit/` itself is OTA-managed (and thus in the file set/RAM budget), the **public-branch security sign-off** (world-readable; SHA-256 = integrity not authenticity), and the backup/restore **storage-headroom** budget. **Resolution carried into tasks: `use_prerelease` is REMOVED** (no token/Releases-API prerelease channel under the public-branch model — S8). **Blocks T026, T027.**

---

## Phase 3.2: Tests first (desktop, domain + contract) ⚠️ write and see them FAIL before 3.3
**These exercise the kept models and the to-be-built content builder / decision table. Models exist today, so model tests pass immediately; builder/decision/render tests must fail until 3.3 — this is expected and noted.** [all P — distinct files]

- [ ] **T006** [P] Domain test — models: `tests/domain/test_models.py`. `ThemePark.remove_non_ascii`/`get_url()`; `ThemeParkRide.is_open()` ⇔ `open_flag and wait_time>0` (incl. `open_flag=True, wait_time=0` → not-open); `ThemeParkList` selected (≤4) + legacy `current_park_id` fallback.
- [ ] **T007** [P] Domain test — content ordering/filtering: `tests/domain/test_content_builder.py`. sort `alphabetical|max_wait|min_wait`, `group_by_park`, `skip_closed`, `skip_meet`, multi-park (≤4), attribution + no-parks message. (Targets `src/ui/content_builder.py` from **T021**.)
- [ ] **T008** [P] Domain test — vacation math: `tests/domain/test_vacation.py`. `is_set()`; `get_days_until()`; `>1 day` / `1`→"tomorrow" / `0`→"TODAY".
- [ ] **T009** [P] Domain test — display decision table: `tests/domain/test_display_decisions.py`. For each data-model row (park-closed / ride `open_flag=False` / open-with-0-wait / open>0) assert content type + sort/filter outcome. (Targets decision logic in **T020/T021**.)
- [ ] **T010** [P] Contract smoke test — ScrollKit API: `tests/contract/test_scrollkit_api.py`. Import every symbol in `contracts/scrollkit-api-consumption.md`, assert callable/constructor shape.
- [ ] **T011** [P] Headless render test: `tests/contract/test_render_headless.py`. `scrollkit.dev.run_headless(...)` + `validate(app)` render splash, a scrolling message, and a `RideScreenContent`; assert non-empty frames, no exceptions. (Targets **T012/T020/T021/T022**.)

---

## Phase 3.3: Core implementation — Milestone A (port to parity, FR-001–018)
*Per-subsystem: replace with `scrollkit.*`, then DELETE the diverged module via the Deletion protocol (interleaved, B5).*

### App lifecycle
- [ ] **T012** App skeleton: `src/app.py` — `class ThemeParkApp(ScrollKitApp)` (`enable_web=True, update_interval=300`); `create_display()` → `UnifiedDisplay(bit_depth=4)`; `create_web_server()` → the config server (from T023); stub `setup/update_data/prepare_display_content/cleanup/show_loading`.
- [ ] **T013** Boot state machine **scaffolding** (review TB1/B1, part 1): in `src/app.py`, implement `setup()` as the pre-run state-machine **structure** from plan.md "Boot Lifecycle" — direct status-draw helpers (`clear→draw→show`), the ordered branch skeleton, and the reboot-terminating onboarding/OTA branches, with calls into WiFi/OTA/fetch wired in by their later tasks. Enforce the invariant: the normal `SLDKWebServer` is **not** created during onboarding/OTA. (same file as T012 → sequential; after T003)
- [ ] **T014** Entry points: rework `boot.py`, `code.py`, `src/themeparkwaits.py`, `src/main.py` to set `sys.path` for `scrollkit` and `asyncio.run(ThemeParkApp().run())`. (after T012)

### Subsystem replacements
- [ ] **T015** [P] Settings → `scrollkit.config.SettingsManager`: create `src/settings_schema.py` with `defaults={...}` + `bool_keys=[skip_closed, skip_meet, group_by_park]` (**`use_prerelease` removed**, T005/S8) and boundary normalization (brightness→float, colors→one rep; verify `ColorUtils` accepts `Yellow`/`Blue`/`Old Lace`, N3); decide+document credential storage location (`secrets.py` vs `settings.json`, S4). **DELETE** `src/config/settings_manager.py` (+ `src/config/` if empty). (after T003; independent file → [P])
- [ ] **T016** Utils migration: replace app utility usages with `scrollkit.utils` (`ErrorHandler`, `ColorUtils`, `Timer`, `system_utils`, `url_utils`). **DELETE** `src/utils/color_utils.py`, `src/utils/error_handler.py`, `src/utils/image_processor.py`, `src/utils/system_utils.py`, `src/utils/timer.py`, `src/utils/url_utils.py` (those with a `scrollkit.utils` equivalent), plus root duplicates `src/color_utils.py`, `src/image_processor.py`, `src/ErrorHandler.py`, and `src/memory_tracker.py` (if unimported). (after T003)
- [ ] **T017** [P] mDNS helper (creation only): `src/net/__init__.py` + `src/net/mdns_helper.py` — `device.local` advertising via `adafruit_mdns` (library gap, D5/R3). Wiring + coexistence happen in T018/T038.
- [ ] **T018** Networking wiring: in `setup()` (T013) wire `scrollkit.network.WiFiManager(settings)` (station connect **and** AP/captive-portal onboarding) + `HttpClient` + clock via `scrollkit.utils.system_utils.set_system_clock(...)`; **start the T017 mDNS helper after station connect**, passing `domain_name` and the same socket pool used by `SLDKWebServer` (review TB5/B5). **DELETE** `src/network/wifi_manager.py`, `src/network/wifimgr.py`, `src/network/http_client.py`, `src/network/http_client_original.py`, `src/network/async_http_request.py`, `src/async_http_request.py`. (after T003, T013, T017)
- [ ] **T019** [P] Domain service rework: `src/api/theme_park_service.py` onto `scrollkit.network.HttpClient` per `contracts/queue-times-api.md` — endpoints, `max_retries=3`, chunked multi-park fetch with `await asyncio.sleep(0)` between requests/retries, keep-prior-snapshot-on-failure, "updating"/attribution status. Models in `src/models/*` unchanged. (after T003; own file → [P])

### Display, content, and the data loop
- [ ] **T020** Ride-screen content: `src/ui/ride_screen_content.py` — `RideScreenContent` (scrolling name + 2× centered wait number) and `ClosedRideContent`, built **strictly on `UnifiedDisplay` primitives**, font loaded once / no per-frame alloc; implement the decision-table branches; select + wire the 2× bitmap font from `src/fonts/` (R2). (after T003; makes T009/T011 pass)
- [ ] **T021** Content builder: `src/ui/content_builder.py` — consumes `WaitTimeSnapshot`+settings → ordered `ContentQueue`: sort/group/skip/multi-park/vacation/attribution/no-parks; generic messages via `ScrollingText`/`StaticText`; splash via `scrollkit.effects.reveal.RevealEffect`. **DELETE** `src/ui/message_queue.py`, `src/ui/unified_display.py`, `src/ui/hardware_display.py`, `src/ui/pyledsimulator_display.py`, `src/ui/simulator_display.py`, `src/ui/display_factory.py`, `src/ui/display_base.py`, `src/ui/display_impl.py`, `src/ui/display_interface.py`, `src/ui/reveal_animation.py`. (after T019, T020; makes T007 pass)
- [ ] **T022** App data loop (review TB1/B1 part 2, B2): in `src/app.py` implement `update_data()` (5-min refresh via `ThemeParkService`; **pre-flush a loading frame** before each blocking fetch; keep prior snapshot on failure) and `prepare_display_content()` (serve from the `ContentBuilder`-populated `content_queue`); complete the `setup()` initial fetch→build-queue section. (after T013, T019, T021)

### Web config (split per review S1)
- [ ] **T023** Web server core: `src/web/__init__.py` + `src/web/config_server.py` — `create_web_server()` → `scrollkit.web.SLDKWebServer` + a `WebHandler` subclass; serve `src/www/` via `StaticFileHandler`; register routes `/`, `/settings`, `/style.css`. (after T003, T013)
- [ ] **T024** Web form parsing/persistence: in `src/web/config_server.py`, parse `selected_park_ids[]` (repeat field → ≤4 + legacy `current_park_id`), absent-checkbox→`False`, `url_decode`; POST → `SettingsManager.set/save` (per `contracts/web-config-routes.md`, S5). (after T023, T015)
- [ ] **T025** Rebuild-on-save: POST to `/settings` triggers a content-queue rebuild via the `ContentBuilder` **without** a network fetch (FR-004). (after T024, T022)

### OTA (split; gated on decisions)
- [ ] **T026** [P] Release pipeline: `scripts/make_manifest.py` — enumerate the release file set, compute size + SHA-256, stamp `version`, emit `manifest.json`; enforce the **path allowlist excluding `secrets.py`/`settings.json`/logs** and the credential file from T015 (per `contracts/ota-release.md`). (after T003, T005; independent file → [P])
- [ ] **T027** OTA glue: `src/ota_glue.py` — wire `scrollkit.ota.OTAClient.for_github(owner, repo, branch="releases", current_version=...)` using the T005 values; `check_for_updates`/`download_update`/`apply_update`; `set_callbacks` for "Installing… do not unplug"; `apply_update()` invoked from `setup()` (T013 OTA branch); **confirm `use_prerelease` is gone** from code/settings. **DELETE** `src/ota/ota_updater.py`, `src/ota/ota.py`, `src/ota_updater.py`, `src/ota.py`, and the `src/ota/` package stubs. (after T003, T005, T013)
- [ ] **T028** `/update` route: in `src/web/config_server.py`, `POST /update` → schedule + download via `ota_glue`, then reboot; apply happens in the next `setup()` (not inline). (after T023, T027)

### Resilience + guard (resilience split per review S1)
- [ ] **T029** Resilience — data path: wrap `update_data()` + content rebuild (`src/app.py`, `src/api/theme_park_service.py`) in try/except via `scrollkit.utils.ErrorHandler`; preserve prior snapshot; surface an error/status content item (FR-014, S6). (after T022)
- [ ] **T030** Resilience — web/OTA/settings: wrap web handlers (`src/web/config_server.py`), OTA (`src/ota_glue.py`), and settings parse in try/except + logging; never crash on a bad request/update/parse. (after T024, T027, T028)
- [ ] **T031** Import guard (scoped to deletions done so far): `tests/contract/test_no_legacy_imports.py` asserting none of the modules deleted through T015–T030 (settings/utils/network/display/web/OTA) are importable or referenced under `src/`. (Final-audit guard re-runs in T046.) (after T016, T018, T021, T024, T027)

---

## Phase 3.4: Integration & desktop validation

- [ ] **T032** Wire it together: `ThemeParkApp` boots end-to-end on the simulator (`PYTHONPATH="../ScrollKit Library/src:src" python -m src.themeparkwaits --dev`); fix import/wiring gaps. (after T012–T031)
- [ ] **T033** Suite green: `pytest tests/` — T006–T011 + T031 all pass. (after T032)
- [ ] **T034** Desktop parity walk: quickstart Acceptance scenarios **1–4 and 7** on the simulator (Scenario 8 is post-optimization → moved to T045); capture `run_headless` screenshots for each **Parity Coverage Matrix** row (plan.md) and eyeball vs. pre-port behavior. (after T033)

---

## Phase 3.5: Hardware acceptance — REQUIRED before any OTA release (review B4)
*Device-only; cannot be simulated. Real Matrix Portal S3. Not [P] — one shared device.*

- [ ] **T035** Fresh device / no credentials → AP + captive portal appears; entering WiFi persists creds (location from T015) and reboots into normal run (Scenario 5).
- [ ] **T036** Wrong / unavailable WiFi → status shown, retries, continues degraded, never crashes (FR-014).
- [ ] **T037** Station connect + NTP set; park list + wait times fetched; ride cycle renders with configured colors/brightness/scroll speed.
- [ ] **T038** Config page reachable at `http://<domain_name>.local/` **and** by raw IP — confirms the T017/T018 mDNS helper coexists with `SLDKWebServer` (shared socket pool / start ordering, R3).
- [ ] **T039** Settings POST rebuilds the display **without** a network fetch (FR-004); booleans persist with missing-key defaults (FR-011).
- [ ] **T040** Multi-park (≤4) synchronous-HTTP refresh: loading frame pre-flushes before each blocking fetch; display resumes between fetches; closed ride / closed park / open-with-0-wait each render + sort per the decision table.
- [ ] **T041** OTA success path: publish a newer `manifest.json` to the public `releases` branch → device detects newer version, downloads, applies, reboots into it with progress UX.
- [ ] **T042** OTA failure/restore path: corrupt/incomplete update → backup-restore yields a bootable device, prior version intact; **credentials + `settings.json` survive** (exclusion list works).
- [ ] **T043** Memory/coexistence (R4/S7): record free heap + FPS at boot, after fetch, with the web server active; **confirm the data and web processes actually spawn**. If memory-gated off → compile `scrollkit` to `.mpy`, re-flash (this is the T004 deferred decision), re-check. **Gate: parity is not met until both processes run in normal operation.**

---

## Phase 3.6: Milestone B — Optimization pass (FR-019–025)
- [ ] **T044** Apply the library's efficiency rules in `src/ui/ride_screen_content.py`, `src/ui/content_builder.py`, and per-frame paths: reuse `Label`/change `.text` only on value change; move `.x` for scrolling; no per-frame `Label`/`Bitmap`/`Group` alloc; `bitmap.fill`/`bitmaptools.blit` over per-pixel loops; keep `bit_depth=4`; chunk heavy compute + pre-flush loading frame.
- [ ] **T045** Re-run Phase 3.5 hardware checklist + quickstart **Scenario 8**; record free heap/FPS; confirm **no regression** vs. the Phase-1 port (no numeric gate, FR-024) and that the optimization is a separable, reviewable diff (FR-026).

---

## Phase 3.7: Milestone C — Final dead-code audit (FR-026–027)
- [ ] **T046** Grep sweep for remaining unimported legacy modules (research.md inventory not yet deleted: `src/theme_park_api.py`, `src/theme_park_display.py`, `src/ui/roller_coaster_animation.py`, `src/ui/roller_coaster_animation_cp.py`, `src/webgui.py`, `src/shopify_connect.py`, `src/pixeldust.py`); confirm unreferenced, delete, then **re-run the import guard (T031) + `pytest tests/` + simulator boot**.
- [ ] **T047** [P] Docs sync: update `CLAUDE.md` + `quickstart.md` to the final module layout, bundling steps, and the manifest/release process. (after T046, so docs reflect final deletions)

---

## Dependencies
- **T003 is a hard gate** → blocks all subsystem-coding tasks: **T013, T015, T016, T018, T019, T020, T023, T026, T027** (review TB2/B2: now includes settings/utils/network/service/manifest, not just display/web/OTA).
- **T005 (OTA decisions)** blocks **T026, T027**.
- Setup (T001–T005) before everything.
- Tests (T006–T011) authored before/with 3.3; suite green gate at T033.
- App lifecycle: **T012 → T013 → T014** (all touch `src/app.py`/entry; sequential). T013 before T018/T022/T027 (they fill `setup()` branches).
- **T017 → T018** (helper created before wiring). T015/T016/T017/T019/T026 are own-file `[P]` **but each is gated on its listed prerequisite** (T003, and T026 on T005).
- **T019 + T020 → T021** (builder consumes ride content + service data) → **T022** (data loop) → **T025** (rebuild-on-save).
- **T023 → T024 → T025**; **T027 → T028** (`/update` needs OTA glue).
- T029 after T022; T030 after T024/T027/T028; **T031 (scoped guard)** after T016/T018/T021/T024/T027.
- 3.3 complete → **T032 → T033 → T034** → **3.5 hardware (T035–T043)** → **B (T044–T045)** → **C (T046–T047)**.
- T041/T042 depend on T026 (manifest) + T027 (OTA glue) + T028 (`/update`).

## Parallel execution examples
```
# After T003 (+ T002), author all tests together (distinct files):
Task: "T006 models test in tests/domain/test_models.py"
Task: "T007 content-ordering test in tests/domain/test_content_builder.py"
Task: "T008 vacation test in tests/domain/test_vacation.py"
Task: "T009 decision-table test in tests/domain/test_display_decisions.py"
Task: "T010 scrollkit API smoke in tests/contract/test_scrollkit_api.py"
Task: "T011 headless render in tests/contract/test_render_headless.py"

# Own-file subsystem work, each gated on T003 (and T026 on T005) — overlap once gated:
Task: "T015 settings schema in src/settings_schema.py (+delete src/config/)"
Task: "T017 mDNS helper in src/net/mdns_helper.py (+ src/net/__init__.py)"
Task: "T019 theme_park_service onto HttpClient in src/api/theme_park_service.py"
Task: "T026 manifest generator in scripts/make_manifest.py"   # also needs T005
```

## Notes
- `[P]` = different files, no dependency. Tasks touching `src/app.py` (T012/T013/T014/T022/T029) and `src/web/config_server.py` (T023/T024/T025/T028/T030) are **sequential within their file**.
- This is a port: prefer importing `scrollkit.*` over re-implementing; the only NEW app code is the documented gaps (ride screen, content builder, web handler content, mDNS helper, OTA glue, manifest script).
- Follow the **Deletion protocol** for every DELETE; commit after each task.
- Device behaviors (3.5) are non-negotiable before shipping an OTA — desktop green ≠ ship-ready.

## Validation checklist
- [x] Every contract has tasks: scrollkit-api-consumption → T003/T010/T031; queue-times-api → T019; web-config-routes → T023/T024/T025/T028; ota-release → T005/T026/T027/T041/T042.
- [x] Every entity has a task: ThemePark/Ride/List/Vacation → T006/T019 (kept); WaitTimeSnapshot → T019/T022; RideScreenContent/ClosedRideContent → T020; ContentBuilder → T021; DeviceSettings → T015; Release/Manifest → T026/T027.
- [x] Every Parity-Matrix FR (FR-001–014) maps to an impl + verification task (3.3 + 3.4/3.5).
- [x] Lifecycle hooks fully tasked: `setup()` scaffold T013, `update_data()`/`prepare_display_content()` T022 (review TB1 fix).
- [x] T003 blocks all subsystem-coding tasks (review TB2 fix); T005 blocks OTA impl (TB3 fix).
- [x] `use_prerelease` resolved once = removed (T005/T015/T027 — TB3/S8 fix); no contradiction.
- [x] Import guard scoped to completed deletions (T031) + re-run after final audit (T046) — no premature failure (TB4 fix).
- [x] mDNS has create (T017) + wire (T018) + verify (T038) — review TB5 fix.
- [x] Tests precede implementation; suite green gate at T033.
- [x] `[P]` tasks touch distinct files; same-file work sequential; coarse tasks (web, resilience, boot) split.
- [x] Each task names exact file paths; Deletion protocol replaces "revert if it breaks".
