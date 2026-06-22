# Tasks: Port ThemeParkWaits to the Refactored ScrollKit Library

**Input**: Design documents in `/Users/czei/Documents/Projects/ScrollKit/themeparkwaits/specs/001-this-project-is/`
**Prerequisites**: plan.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓ (scrollkit-api-consumption, web-config-routes, queue-times-api, ota-release), quickstart.md ✓

> **Revised after the tasks-gate PAL review (2026-06-20)** — TB1 (split the boot machine + add the data-loop task), TB2 (extend the T003 block list), TB3 (OTA decisions task + `use_prerelease` resolved = **removed**), TB4 (scoped import guards), TB5 (mDNS wiring) and the should-fix/nit items are all incorporated; tasks renumbered.

## CURRENT STATUS — Milestone A is simulator-complete (keep this updated)
**Done & verified on the desktop simulator** (26 tests pass; library feasibility ~135 FPS / 1 KB RAM, no warnings):
- T001–T003 (setup + API gate), T012/T014 (app skeleton + entry points), T015/T016/T019 (settings/utils/service on `scrollkit.*`), T017 + T018(partial) (network/mDNS wiring, dev-safe), T020/T021/T022 (ride screen + 2× number, content builder, data loop), the opening **reveal splash** (port of reveal_animation.py — all LEDs on → wink off → THEME PARK WAITS), T023–T025 (web config UI at :8080), T026–T028 (OTA), T029–T031 (resilience + import guard), T032/T033 (integration + green suite), **T044** (efficiency: bit_depth=4, label reuse, `bitmap.fill` — feasibility green), **T046** (dead-code sweep → `src/` = 22 active modules), **T047** (docs), and **P1 text-positioning RESOLVED** (`draw_text` y = baseline; scroll y=13, ride name y=5, big number y=21).

**Repo / OTA facts (changed mid-session):** repo renamed → **`czei/themeparkwaits`** (local `origin` updated); single PUBLIC repo for dev + releases; OTA channel branch = **`live`** (`src/ota_glue.py` `DEFAULT_BRANCH="live"`); `release-MAJOR.MINOR` branches = immutable archives mirrored onto `live` by CI/script (hybrid "Option C", multi-model consensus — NO on-device branch discovery). `src/.version` = 1.95.

**Remaining:**
- **Hardware checklist T035–T043 + T045** — device-only (real WiFi, AP onboarding, OTA install/reboot, mDNS, RAM). USER runs on a Matrix Portal S3; can't be done on the simulator.
- **T013 / T018**: first-boot AP onboarding (no stored creds) is device-only and still TODO; `setup()` reboot-terminating branches not yet formalized.
- **Publish automation (WRITTEN — drafted, NOT enabled):** `RELEASING.md`, `scripts/publish.sh` (shared core), and `.github/workflows/publish-live.yml` (`on: create` for `release-*` → `publish.sh` → force-push `manifest.json`+`files/` onto `live`). Dry-run verified on the sim tree: 34 device-path files, libs flash-frozen, no private leaks, `src/.version` stamped from the ref name (→ how `current_version` bumps after apply). **Still gated on the user:** (a) the workflow only auto-fires once on `main` (default branch); (b) create the public `live` branch. **Confirmed:** `INCLUDE_LIB=0` (OTA ships app source only; `src/lib`/`scrollkit` flash-frozen) — keeps the "do not unplug" install window short so impatient users don't yank power mid-write. Resolves the ota-release.md open items "current_version bump" + "is scrollkit OTA-managed" (no — flash-frozen).
- **ScrollKit library:** a publish-tool prompt was handed to the library agent (add desktop `scrollkit.ota.publish`; explicitly NOT on-device branch discovery). When it lands, retire `scripts/make_manifest.py` and point at it.
- **Visual parity not yet eyeballed on the sim:** closed-park message, vacation countdown, multi-park grouping.

**User action items:** rotate the old hardcoded GitHub token (it's in git history); `pip uninstall wifi displayio` (stray desktop packages caused two bugs this session); ensure a public **`live`** branch exists for OTA.

**Candidate ScrollKit library issues (separate investigation):** see `SCROLLKIT_NOTES.md` — `is_dev_mode()` misfire, `set_pixel()`/`fill()` no-op in the simulator, OTA fixed-branch model.

**Branch:** `001-this-project-is` — ~19 commits, **NOT pushed** to the remote.

---

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
  - **Decision (2026-06-20, user-confirmed): PUBLIC `releases` branch** hosting `manifest.json` + `files/<device-path>/...`, fetched via `OTAClient.for_github(owner, repo, branch="releases")`, **no device-side token**. Owner/repo to confirm at T026/T027 (default: the existing `themeparkwaits.release` repo, made public — user action). Verified release layout from T003: manifest at branch root, payload under `files/`, manifest keys = absolute device paths.

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
- [X] **T012** App skeleton: `src/app.py` — `class ThemeParkApp(ScrollKitApp)`; `create_display()` → `UnifiedDisplay(64,32,bit_depth=4)`; `setup()` queues placeholder splash + scrolling message. *(Done; `enable_web=False` until T023; verified via `run_headless` — renders, ~148 FPS / 1 KB RAM hardware estimate.)*
- [ ] **T013** Boot state machine **scaffolding** (review TB1/B1, part 1): in `src/app.py`, implement `setup()` as the pre-run state-machine **structure** from plan.md "Boot Lifecycle" — direct status-draw helpers (`clear→draw→show`), the ordered branch skeleton, and the reboot-terminating onboarding/OTA branches, with calls into WiFi/OTA/fetch wired in by their later tasks. Enforce the invariant: the normal `SLDKWebServer` is **not** created during onboarding/OTA. (same file as T012 → sequential; after T003)
- [X] **T014** Entry points: `src/main.py` (minimal: parse `--dev`, construct + run `ThemeParkApp`) and `src/themeparkwaits.py` (desktop sys.path for sibling `../ScrollKit Library/src`; device `/src/lib`+`/lib`) reworked. `code.py` already imports `src.themeparkwaits`; `boot.py` is device hardware init — left unchanged. *(Desktop boot verified.)*

### Subsystem replacements
- [X] **T015** [P] Settings → `scrollkit.config.SettingsManager`: `src/settings_schema.py` created (`DEFAULTS` + `BOOL_KEYS=[skip_closed,skip_meet,group_by_park]`, `use_prerelease` removed; `ColorUtils.colors` confirmed has Yellow/Blue/Old Lace; creds = `secrets.py` per T003). **`src/config/` deletion DEFERRED** until its orphan consumers (web_server, theme_park_api, etc.) are removed — per the Deletion protocol "don't delete while references remain". *(Verified: settings_factory + tests green.)*
- [~] **T016** Utils migration: kept domain modules (`models/*`, `api/theme_park_service.py`) repointed to `scrollkit.utils.*` (`ErrorHandler`, `url_utils`); `vacation.py` given a stdlib `datetime` fallback so it's desktop-testable. **Physical DELETE of `src/utils/*` + root dups DEFERRED** until orphan consumers (network/ui/ota) are removed (refs still remain — Deletion protocol). *(Repoint verified: domain imports + tests green.)*
- [X] **T017** [P] mDNS helper: `src/net/mdns_helper.py` (`advertise(hostname)` via `mdns`/`wifi`; no-op on desktop, library gap D5/R3).
- [~] **T018** Networking wiring: `app._init_network()` wires `scrollkit.network.WiFiManager` station connect + `HttpClient` session + `set_system_clock` (NTP) + mDNS, all dev-mode-guarded so desktop is unaffected. **Hardware-unverified** (T037/T038). **TODO:** first-boot AP/captive-portal **onboarding** (no creds) is device-only — the library `WiFiManager` has `start_access_point`/`run_web_server`; finish + verify on hardware. **DELETE of legacy `src/network/*` DEFERRED** to cleanup wave.
- [X] **T019** [P] Domain service rework: `src/api/theme_park_service.py` repointed to `scrollkit.utils` (uses the injected `scrollkit.network.HttpClient`); endpoints/retries/parallel multi-park fetch preserved. *(Verified: `tests/domain/test_service.py` — fetch park list, fetch park data, update_selected_parks all green via the mock HttpClient.)*

### Display, content, and the data loop
- [X] **T020** Ride-screen content: `src/ui/ride_screen_content.py` (`RideScreenContent` + `ClosedRideContent`, async render on display primitives, self-managed name scroll) + `src/ui/tpw_display.py` (`ThemeParkDisplay` adds `draw_text_scaled` with a reuse pool → **large 2× wait number**, terminalio scaled — no extra font needed; R2 resolved). *(Verified on simulator via screenshots: name scroll + big centered number + Closed.)*
- [X] **T021** Content builder: `src/ui/content_builder.py` — sort/group/skip/multi-park/vacation/attribution/no-parks → `ContentQueue` (generic messages via `ScrollingText`/`StaticText`; splash placeholder via `StaticText` — `RevealEffect` polish deferred to T044). *(Verified: 6 builder tests.)* **DELETE of legacy `src/ui/*` display modules DEFERRED** to the cleanup wave (still referenced by un-ported orphans; Deletion protocol).
- [X] **T022** App data loop: `src/app.py` `update_data()` refreshes selected/current parks via `ThemeParkService` then rebuilds the queue via `build_content_queue`; `show_loading()` pre-flushes an "Updating..." frame (B2); `setup()` does splash + `service.initialize()`; `prepare_display_content()` = library default. Never-crash guards (FR-014). *(Verified: T022 app-data-loop test + end-to-end simulator screenshot from real mock data.)*

### Web config (split per review S1)
- [X] **T023** Web server core: `src/web/config_server.py` — `make_handler_class(app)` → `StaticFileHandler` subclass with routes `/`, `/settings`, `/style.css` (from `src/www`), `/update`; `app.create_web_server()` returns `SLDKWebServer`; `enable_web=True`. *(Verified: renders form + live parks.)*
- [X] **T024** Web form parsing/persistence: 4 `park_N` dropdowns → `selected_park_ids` (+legacy `current_park_id`); absent-checkbox→`False`; color `#rrggbb`↔`0xrrggbb`; vacation; POST → `SettingsManager.set/save`. *(Adapter is single-value-per-key, hence 4 dropdowns not a repeat field — S5 noted.)*
- [X] **T025** Rebuild-on-save: POST → `build_content_queue` (no network fetch, FR-004) + `park_list.load_settings` + `update_needed` flag for the next fetch. *(Verified: 3 web tests.)* **NOTE → T038**: CircuitPython adapter `handle_requests()` only sleeps (no `server.poll()`) — on-device handling needs verification/workaround.

### OTA (split; gated on decisions)
- [X] **T026** [P] Release pipeline: `scripts/make_manifest.py` — walks a source tree → `manifest.json` (version + per-file size/SHA-256, keys = device paths) + `files/<device-path>` payload; **allowlist EXCLUDES `secrets.py`/`settings.json`/`error_log`/caches** (B3). Reads version from `src/.version`. *(Verified: excludes private files + correct hashes.)*
- [X] **T027** OTA glue: `src/ota_glue.py` — `OTAGlue` over `OTAClient.for_github("Czeiszperger","themeparkwaits.release",branch="releases")`, no device token; `schedule_update()`+`install_pending()`; `set_callbacks` "Installing…" display; `setup()` installs pending before fetch; `use_prerelease` gone. *(Verified: constructs, has_pending False, reads v1.95.)* **DELETE of old `src/ota*` stubs DEFERRED** (orphans; cleanup wave).
- [X] **T028** `/update` route: `POST /update` in `config_server.py` → `ota.schedule_update()` (check+download) then reboot; apply runs in next `setup()`. *(Wired; live check needs the public release branch to exist — T005 action.)*

### Resilience + guard (resilience split per review S1)
- [X] **T029** Resilience — data path: `update_data()` + `service.initialize` wrapped via `scrollkit.utils.ErrorHandler`; prior snapshot preserved (FR-014).
- [X] **T030** Resilience — web/OTA/settings: web `_apply`, OTA `schedule_update`/`install_pending`, `create_web_server` all guarded; never crash on bad request/update.
- [X] **T031** Import guard: `tests/contract/test_no_legacy_imports.py` — static check that the active boot path imports no legacy subsystem. *(Green. Re-runs after final-audit deletions, T046.)*

---

## Phase 3.4: Integration & desktop validation

- [X] **T032** Wire it together: `ThemeParkApp` boots end-to-end on the simulator (full app: data + web + ota); user ran `python -m src.themeparkwaits --dev` against **live** queue-times data successfully ("bones good, live values"). Full-app headless smoke: no errors.
- [X] **T033** Suite green: `pytest tests/` — **26 pass** in ~1.3s, terminating.
- [~] **T034** Desktop parity walk: scenarios verified via screenshots (splash, ride screen + 2× number, live data, config page renders + applies). **OPEN: P1 text-positioning** (user-confirmed off vs. hardware → fix in T044). Remaining scenarios (closed-park visual, vacation, multi-park grouping on screen) to eyeball.

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

## Known polish items
- [X] **P1 — Text vertical positioning (RESOLVED).** Root cause: `draw_text`'s `y` is the text **baseline** (top-down, origin top-left; `y=0` clips the glyph off the top) — an **app-code** issue (wrong y values), confirmed not a ScrollKit bug via a calibration screenshot. Fixed: scroll text `y=13` (centered), ride name `y=5`, 2× number/"Closed" `y=21`; screenshot-verified. (Original note retained below for history.)
- [ ] **P1 (orig note) — Text vertical positioning.** On the simulator the text y-positions are off vs. the original hardware (user confirmed: live values correct, "bones good," only placement needs tweaking). Likely cause: the `adafruit_display_text` `Label` y-origin / `anchor_point` convention differs between the new library's `Label` (and/or its simulator) and what the old app relied on — the old `unified_display.py` positioned labels at specific y's (ride name y≈7/2, wait y≈22/12) possibly with an `anchor_point` or `y`-as-baseline assumption. Fix in the polish round: calibrate y (and consider setting `label.anchor_point=(0,0)` / `anchored_position`) in `RideScreenContent` + `ThemeParkDisplay.draw_text_scaled` + the splash, screenshot-verifying, and confirm it matches on hardware. Affects `src/ui/ride_screen_content.py`, `src/ui/tpw_display.py`, `src/ui/content_builder.py` splash, `src/app.py` `show_loading`.

## Phase 3.6: Milestone B — Optimization pass (FR-019–025)
- [X] **T044** Efficiency rules applied during the port (verified ~135 FPS / 1 KB RAM, no feasibility warnings): `bit_depth=4`; label reuse via the library pool (ride screen `bitmap_rebuild` only ~0.3 ms/frame); `RevealSplash` uses `bitmap.fill` (not a per-pixel loop); no per-frame `Label`/`Bitmap`/`Group` alloc; `show_loading()` pre-flush before the sync fetch. P1 (text positioning) resolved. **Remaining:** re-confirm on real hardware (part of T045/the hardware checklist).
- [ ] **T045** Re-run Phase 3.5 hardware checklist + quickstart **Scenario 8**; record free heap/FPS; confirm **no regression** vs. the Phase-1 port (no numeric gate, FR-024) and that the optimization is a separable, reviewable diff (FR-026).

---

## Phase 3.7: Milestone C — Final dead-code audit (FR-026–027)
- [X] **T046** Dead-code sweep DONE: reachability-probed the active path (22 modules), then deleted **all** legacy subsystems + the deferred ones from T016/T018/T021 (`src/config`, `src/utils`, `src/network`, `src/ota`, old `src/ui/*` display stack, root dups, stale assets). `src/` now holds only the active path; everything else is on `scrollkit.*`. Re-verified: import guard + 26 tests pass + sim boots (display+data+web). The earlier "DELETE deferred" notes on T015/T016/T018/T019/T021/T022/T027 are now all resolved here.
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
