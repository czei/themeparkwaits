# Implementation Plan: Port ThemeParkWaits to the Refactored ScrollKit Library

**Branch**: `001-this-project-is` | **Date**: 2026-06-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-this-project-is/spec.md`

## Summary
Re-platform the ThemeParkWaits LED-box app onto the **current** ScrollKit library so it keeps every feature it has today while every subsystem the library provides runs on the library. The decisive finding (research.md): the app's `SettingsManager`, `WiFiManager`, `HttpClient`, `UnifiedDisplay`, `utils/*`, OTA, and web server are **hand-rolled copies that diverged from the old library** — the refactor extracted clean versions into `scrollkit.*`. So the technical approach is: **delete the app-local subsystem, import the `scrollkit` equivalent, keep only theme-park domain code** (queue-times.com client + models, sort/filter/group rules, the dual-zone ride-screen widget, the config-page content, mDNS, and the OTA release glue). Work is staged: **(1) port to feature parity, (2) optimization pass, (3) dead-code removal** — each independently reviewable.

## Technical Context
**Language/Version**: Python 3.x / CircuitPython (MicroPython-class) for device; CPython 3.11+ for desktop simulation
**Primary Dependencies**: ScrollKit library (`scrollkit.*` — app framework, display/content, effects, network, config, ota, web, utils); Adafruit CircuitPython bundle (`adafruit_matrixportal`, `adafruit_display_text`, `adafruit_bitmap_font`, `adafruit_httpserver`, `adafruit_requests`, `asyncio`, etc., already vendored in `src/lib/`); `adafruit_mdns` (app-owned mDNS gap)
**Storage**: on-device JSON files — `settings.json` (via `scrollkit.config.SettingsManager`), `secrets.py` (WiFi creds); OTA staging dirs
**Testing**: desktop `pytest` for the domain layer (mocked `HttpClient`); library dev harness `scrollkit.dev.run_headless`/`validate`/`capabilities`; hardware-timing sim (`SCROLLKIT_HW_SIM=1`) — advisory
**Target Platform**: Matrix Portal S3 (64×32 RGB LED matrix) on CircuitPython; desktop simulator for development
**Project Type**: single embedded application (Option 1 structure)
**Performance Goals**: no numeric budget — the app has no history of memory/perf issues (spec FR-024). Apply the library's documented efficient techniques; don't regress vs. the Phase-1 port. Library reference points: `bit_depth=4` ≈ 4.5 ms refresh (~220 FPS ceiling), display loop ~20 FPS.
**Constraints**: memory- and CPU-constrained device; HTTP is **synchronous** — `adafruit_requests` blocks the cooperative loop during each request, so a loading frame is **pre-flushed once before** a blocking call (it does not animate during it), and multi-park fetches yield only **between** parks/retries; `scrollkit/__init__.py` does no eager imports (import submodules on demand for RAM)
**Scale/Scope**: one device app; up to 4 parks; ~12 display fields/cycle; ~20 source modules deleted, ~6 reworked, ~3 new (ride-screen content, content builder, mDNS helper)

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution at `.specify/memory/constitution.md` is an **unfilled template** (all placeholders) — there are no ratified project-specific principles to enforce. In their absence, this plan adopts the **spec's own clarified constraints** as the gates:

| Gate (from spec) | Status | Notes |
|---|---|---|
| All library-provided subsystems run on the library | PASS | D1–D9; only documented gaps stay app code |
| App-unique code only where the library lacks capability | PASS | gaps enumerated (ride screen, config HTML, mDNS, domain data, OTA release auth) |
| Port-then-optimize separability | PASS | Phases 1/2 are distinct, independently reviewable milestones |
| No regression / never-crash resilience preserved | PASS | parity scenarios + `ScrollKitApp` graceful degradation |
| Dead-code removal in scope | PASS | Phase 3 with a grep-gated deletion list |

No violations → Complexity Tracking is empty. (Recommend filling the real constitution separately via `/constitution`; not a blocker for this feature.) Note: these PASS marks reflect alignment of the **design direction** with the spec's constraints; they are not a claim that the plan was free of implementation-readiness gaps — the plan-gate review (2026-06-20) surfaced several, now folded into Phase 0/1 and the Boot Lifecycle / Parity Matrix / OTA-release contract below.

## Project Structure

### Documentation (this feature)
```
specs/001-this-project-is/
├── plan.md              # This file
├── spec.md              # Feature spec (clarified 2026-06-20)
├── research.md          # Phase 0 — decisions D1–D12, dead-code inventory, risks
├── data-model.md        # Phase 1 — domain/presentation/library entities
├── contracts/           # Phase 1
│   ├── scrollkit-api-consumption.md   # app↔library API contract (+ "Re-verify before coding")
│   ├── web-config-routes.md           # config UI routes + form fields
│   ├── queue-times-api.md             # external data API + closed/zero-wait table
│   └── ota-release.md                 # OTA release/update + manifest contract (review B3)
├── quickstart.md        # Phase 1 — run + acceptance walkthrough
└── tasks.md             # Phase 2 output (/tasks — NOT created here)
```

### Source Code (repository root) — target shape after the port
```
boot.py, code.py                     # reworked to launch the ScrollKitApp subclass
src/
├── themeparkwaits.py, main.py        # construct + run the new app; sys.path for scrollkit
├── app.py                            # ThemeParkApp(ScrollKitApp): setup/update_data/prepare/create_*
├── models/                           # KEPT (domain): theme_park, theme_park_ride, theme_park_list, vacation
├── api/theme_park_service.py         # KEPT, reworked onto scrollkit.network.HttpClient
├── ui/
│   ├── ride_screen_content.py        # NEW: RideScreenContent/ClosedRideContent (library gap)
│   └── content_builder.py            # NEW: sort/filter/group → ContentQueue (domain logic)
├── net/mdns_helper.py                # NEW (small): mDNS hostname (library gap)
├── ota_glue.py                       # KEPT/minimal: wires OTAClient.for_github(branch="releases")
├── www/, fonts/, images/             # KEPT assets
└── lib/                              # KEPT adafruit .mpy bundle (+ scrollkit/ on device /lib)
# DELETED: src/config/, src/network/* (all), most of src/ui/*, src/utils/* dups,
#          src/ota/* stubs, root dup/dead modules (see research.md inventory)
```
**Structure Decision**: Option 1 (single project). Keep the existing `src/` layout, slimmed to domain + library glue.

## Phase 0: Outline & Research → research.md ✅
Resolved all technical unknowns and recorded decisions D1–D12, the dead-code inventory, the testing approach, and risks (R1 OTA — now resolved; R2 big-number font; R3 mDNS coexistence; R4 `.py` vs `.mpy` RAM). All spec `[NEEDS CLARIFICATION]` markers were closed (Clarifications 2026-06-20). **R1 resolved 2026-06-20**: OTA uses `scrollkit.ota.OTAClient.for_github` against a **public `releases` branch + `manifest.json`**, no device-side auth; the only delta is the release pipeline emitting `manifest.json`. No unresolved **design** decisions remain; the tracked implementation risks **R2 (big-number font), R3 (mDNS/web socket coexistence), R4 (`.py` vs `.mpy` RAM)** carry forward into Milestone A tasks rather than blocking. **Output**: `research.md`.

## Phase 1: Design & Contracts → ✅
- **Entities** → `data-model.md` (domain app-owned; presentation subclasses on library bases; settings/release library-owned).
- **Contracts** → `contracts/` — the app↔library API surface (with a "Re-verify before coding" checklist), the config web routes/fields, the queue-times.com data contract (with the closed/zero-wait decision table), and the OTA release/update contract. (For this embedded app the meaningful "contracts" are these integration surfaces, not REST endpoints.)
- **Test scenarios** → `quickstart.md` acceptance walkthrough maps 1:1 to the spec's 8 scenarios; automated checks use pytest + the library dev harness. Contract "tests" here = the API-consumption checklist (must import/run) + the route/field table + screenshot verification via `run_headless`.
- **Agent context**: produced `CLAUDE.md` at repo root manually (the spec-kit `update-agent-context.sh` requires a local `.specify/templates/agent-file-template.md` this project lacks; created the equivalent directly).

**Post-Design Constitution re-check**: PASS — no new violations; the only design-level escape hatch (app-owned code) is confined to documented library gaps.

## Boot Lifecycle — `setup()` contract  *(resolves review B1/B2)*
`ScrollKitApp.run()` spawns the display/data/web processes **only after `setup()` returns**, so `setup()` runs with no loops active. It is therefore a linear pre-run state machine that draws status **directly** (`clear → draw → show`), not via the content queue, and whose onboarding/OTA branches **terminate in a reboot** (they never fall through into normal run):

1. Initialize display; show splash/reveal + status directly.
2. **If no WiFi credentials** → run the `WiFiManager` AP/captive-portal server **only**; show AP/config info directly; persist credentials; **reboot** (do **not** create the normal config `SLDKWebServer`, do **not** enter `run()`).
3. Station-connect WiFi (retry; on failure show status and continue degraded — never crash).
4. **If a pending OTA is staged** → show install status directly; `apply_update()`; **reboot** (do **not** enter `run()`).
5. NTP clock; fetch park list; fetch wait times (synchronous — pre-flush a loading frame before each blocking call); build the initial content queue.
6. Return → `run()` spawns display/data/web.

**Invariant**: the normal `SLDKWebServer` is never created while AP-onboarding or OTA-install is active (no double web server, no reboot-mid-loop).

## Parity Coverage Matrix  *(resolves review S3 — every parity FR gets an impl + a verification task in `/tasks`)*
| Behavior | FR | Impl home |
|---|---|---|
| Splash + reveal intro | FR-001 | app `setup()` + `RevealEffect` |
| Ride screen: scrolling name + 2× wait number | FR-002 | `RideScreenContent` |
| Closed ride / closed park / open-with-0-wait | FR-003 | display decision table (data-model.md) |
| Sort alpha/max/min + group-by-park | FR-004 | `content_builder` |
| skip-closed / skip-meet | FR-005 | `content_builder` |
| Up to 4 parks (+ legacy `current_park_id`) | FR-006 | `theme_park_list` + `content_builder` |
| 5-min refresh, retries, "updating" msg, attribution | FR-007 | `update_data` + `theme_park_service` |
| Vacation countdown incl. tomorrow/today | FR-008 | `content_builder` + `Vacation` |
| WiFi AP onboarding + credential persistence | FR-009 | `WiFiManager` (setup state 2) |
| Config page: all settings + park select + vacation | FR-010 | web handler + `src/www` |
| Settings persistence + missing-key defaults | FR-011 | `SettingsManager` defaults/bool_keys |
| OTA check/download/install + progress UX | FR-012 | `ota_glue` + ota-release contract |
| Hardware + simulator dual target | FR-013 | `UnifiedDisplay` auto-detect |
| Never-crash resilience + error logging | FR-014 | `ErrorHandler` wraps refresh/web/OTA/parse |
| Brightness / colors / scroll speed | FR-002/010 | `SettingsManager` + display |
| No-parks guidance message | edge | `content_builder` |

## Phase 2: Task Planning Approach
*Describes what `/tasks` will do — not executed here. The "Milestone A/B/C" below are the IMPLEMENTATION stages (the spec's **port → optimize**); they are distinct from the /plan-command "Phase 0/1/2" used above (N2).*

**Strategy** — tasks grouped by milestone, dependency-ordered, `[P]` where files are independent. **Dead-code deletion is interleaved into Milestone A per subsystem** (delete/rename each diverged app module the moment its `scrollkit` replacement lands) to avoid half-migrated state and name collisions (two `SettingsManager`, two `WiFiManager`, two `UnifiedDisplay`); an import-guard check forbids importing the legacy modules. Before coding each subsystem, **re-verify the live `scrollkit` signatures** against `contracts/scrollkit-api-consumption.md` §"Re-verify before coding" (B2/S9).

- **Milestone A — Port to parity (FR-001–018)**
  1. App skeleton + **boot state machine**: `ThemeParkApp(ScrollKitApp)` with `setup/update_data/prepare_display_content/create_display/create_web_server`; implement the `setup()` pre-run state machine (Boot Lifecycle above); rework `main.py`/`themeparkwaits.py`/`code.py`/`boot.py`.
  2. Settings → `scrollkit.config.SettingsManager` (defaults + bool_keys); **decide & document credential storage** (`secrets.py` vs `settings.json`) that `WiFiManager` actually reads; **delete `src/config/settings_manager.py`** `[P]`.
  3. Network → `scrollkit.network.WiFiManager` + `HttpClient`; NTP via `system_utils`; mDNS helper **+ task: mDNS/web-server socket-pool coexistence on device (R3)**; **delete legacy `src/network/*` net modules**.
  4. Domain rework: `theme_park_service` onto `HttpClient`; models unchanged `[P]`.
  5. Display: `RideScreenContent`/`ClosedRideContent` built **strictly on `UnifiedDisplay` primitives** (load font once, no per-frame alloc; **font-asset selection** for the 2× number, R2; **resolve the sync/async `draw_text` vs `render()` boundary first**); the closed/zero-wait decision table; generic messages via `ScrollingText`/`StaticText`; splash via `RevealEffect`; **delete legacy `src/ui/*` display modules**.
  6. Content builder: sort/filter/group/multi-park/vacation/attribution → `ContentQueue`; **delete `src/ui/message_queue.py`**.
  7. Web config: `SLDKWebServer` + `WebHandler` routes + `src/www` via `StaticFileHandler`; `selected_park_ids[]` parsing, absent-checkbox handling, `url_decode`; POST → settings → content rebuild; **delete `src/network/web_server*.py` + dev/unified/core/adapters**.
  8. OTA: wire `OTAClient.for_github(branch="releases")` per the **release/update contract** (`contracts/ota-release.md`); install UX via `set_callbacks`/`reboot_device`; **remove/remap `use_prerelease`**; **delete `src/ota/*` stubs**. Separately: build the release pipeline that emits `manifest.json` (path allowlist excluding `secrets.py`/`settings.json`/logs).
  9. Resilience: wrap data refresh, web handlers, OTA, settings parse, and content rebuild in try/except via `scrollkit.utils.ErrorHandler`; preserve the prior snapshot on failure; surface a status item (FR-014, S6).
  10. Deployment: scrollkit on `sys.path`/device `/lib`; **verify `.py` source fits device RAM/flash — if the data/web processes get memory-gated off, compile `scrollkit` to `.mpy` (this is parity, not optional — R4/S7)**.
  11. **Parity verification — desktop**: pytest domain + `run_headless` screenshots for each Parity-Matrix row.
  12. **Parity verification — hardware (REQUIRED before any OTA release — B4)**: fresh-device AP onboarding; wrong/unavailable WiFi resilience; station connect + NTP; mDNS + raw-IP config page; settings POST rebuild without fetch; multi-park sync-HTTP refresh; OTA success path **and** simulated failure/restore; display+data+web coexistence; record free heap/FPS at checkpoints and **confirm the data/web processes actually spawn** (else memory-gating silently breaks parity).
- **Milestone B — Optimization pass (FR-019–025)**: label reuse / no per-frame alloc / `bitmap.fill`+`blit` / `bit_depth=4` / chunked fetch + pre-flushed loading frame / confirm graceful degradation; re-run the hardware checklist; no regression (HW-timing sim advisory).
- **Milestone C — Final dead-code audit (FR-026–027)**: grep-sweep for any remaining unimported legacy module, delete, re-run quickstart. (Bulk deletion already happened per-subsystem in A; C is the safety net, not the first pass.)

**Ordering**: A → B → C (parity holds before optimizing; per-subsystem deletion happens *within* A). **Estimated output**: ~40–50 tasks — the parity matrix, per-subsystem deletion + import guards, the OTA release pipeline, and the hardware acceptance checklist push this above the original 28–34 (S10).

## Phase 3+: Future Implementation
- **Phase 3**: `/tasks` creates `tasks.md`.
- **Phase 4**: implement Milestones A→B→C.
- **Phase 5**: validate via `quickstart.md` (simulator + hardware), confirm library-only imports, no regression.

## Complexity Tracking
*No constitutional violations to justify (constitution is an unfilled template; spec-derived gates all PASS). Table intentionally empty.*

## Progress Tracking
**Phase Status**:
- [x] Phase 0: Research complete (/plan)
- [x] Phase 1: Design complete (/plan)
- [x] Phase 2: Task planning approach described (/plan)
- [ ] Phase 3: Tasks generated (/tasks)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS (spec-derived gates; constitution is template placeholder)
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved (spec Clarifications 2026-06-20)
- [x] Complexity deviations documented (none)
- [x] Open decision R1 (OTA) resolved 2026-06-20 — public `releases` branch + `manifest.json`, no device auth

---
*Based on the spec's clarified constraints; project constitution at `.specify/memory/constitution.md` is an unfilled template (no ratified principles).*
