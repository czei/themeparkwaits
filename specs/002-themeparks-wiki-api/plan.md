# Implementation Plan: Source Theme-Park Wait Times from themeparks.wiki

**Branch**: `002-themeparks-wiki-api` | **Date**: 2026-06-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-themeparks-wiki-api/spec.md`

## Summary

Replace the app's theme-park data source — both the park catalog and the live ride
wait times — from queue-times.com to **themeparks.wiki**, with no queue-times.com
left anywhere. The board's behavior is unchanged (multi-park, sort/filter/group,
closed treatment, vacation countdown, web config); only the data client, the
domain models that parse the new payloads, the park-selection field types, and the
attribution text change. The whole change is confined to the theme-park **domain
layer** — `src/api/theme_park_service.py`, `src/models/*`, `src/ui/content_builder.py`
(attribution), and the park-selection bits of `src/web/config_server.py`. Every
ScrollKit subsystem (display, network `HttpClient`, settings, OTA, web framework)
is reused untouched.

Two facts from Phase 0 shape the approach: (1) themeparks.wiki needs exactly **two
endpoints** — `GET /v1/destinations` (catalog) and `GET /v1/entity/{parkId}/live`
(wait times) — mirroring today's two-call shape; (2) the `/live` payload is **~18×
larger** than queue-times (~90 KB/park vs ~5 KB) because it returns shows,
restaurants, and rich queue objects with **no server-side filter**. So the one real
engineering task beyond a mechanical swap is **bounding peak RAM**: fetch selected
parks **sequentially**, parse each response down to a compact attraction list, and
release the raw payload (with `gc.collect()`) before the next park — so the device
holds at most one large payload at a time, not four.

Identifiers change from integers to **UUID strings**, which (a) ripples through
park-selection code that currently `int()`-casts IDs, and (b) means existing
devices' saved selections are invalid — per the clarified decision they are
**cleared on upgrade** and the user re-selects.

## Technical Context

**Language/Version**: CircuitPython (MicroPython-class) on device; CPython 3.11+ for desktop simulation
**Primary Dependencies**: ScrollKit library (`scrollkit.network.HttpClient`, `scrollkit.config.SettingsManager`, `scrollkit.display.UnifiedDisplay`/`ContentQueue`, `scrollkit.utils.ErrorHandler`/`url_decode`) — all reused unchanged; `adafruit_requests` (synchronous HTTP) + `json` for parsing
**External API**: themeparks.wiki — base `https://api.themeparks.wiki/v1`, **no auth / no API key**; `GET /destinations`, `GET /entity/{parkId}/live`; `/live` `cache-control: max-age=60`
**Storage**: `settings.json` via `SettingsManager` — `selected_park_ids` changes from `int[]` to `str[]` (UUIDs); a one-time migration clears legacy integer IDs
**Testing**: desktop `pytest` with a mocked `HttpClient` fed canned themeparks.wiki JSON fixtures (destinations + a park `/live`); `scrollkit.dev.run_headless` screenshots for visual parity; `SCROLLKIT_HW_SIM=1` for advisory device timing; on-device free-heap check for the payload-size risk
**Target Platform**: Matrix Portal S3 (64×32 RGB LED matrix) on CircuitPython; desktop simulator for development
**Project Type**: single embedded application (Option 1 structure) — domain-layer change only
**Performance Goals**: no regression vs. the current build. Refresh stays on the ~5-minute cadence; display loop ~20 FPS; `bit_depth=4`. New constraint: per-park `/live` ≈ 90 KB must parse within device RAM without gating the data/web processes off
**Constraints**: memory-constrained device; HTTP is **synchronous** (blocks the cooperative loop — pre-flush a loading frame before each fetch, yield only between parks); `scrollkit/__init__.py` does no eager imports; the larger payload must be parsed one-park-at-a-time with intermediate `gc.collect()`
**Scale/Scope**: one device app; up to 4 parks; catalog = 106 destinations / **139 parks** (comparable to queue-times' 141); ~4 domain modules reworked, 0 new modules, 0 ScrollKit changes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution at `.specify/memory/constitution.md` is an **unfilled
template** (all placeholders) — there are no ratified project-specific principles to
enforce. As in feature 001, this plan adopts the **spec's clarified constraints**
plus the project's standing CLAUDE.md conventions as the gates:

| Gate | Status | Notes |
|---|---|---|
| Complete removal of queue-times.com (FR-003) | PASS | grep-gated; no URL, attribution, or ID assumption remains |
| All data from themeparks.wiki (FR-001/002) | PASS | two endpoints; catalog + live |
| No feature regression (parity FRs) | PASS | change confined to domain layer; display/web/settings logic untouched |
| Stay on ScrollKit subsystems (no app-local re-implementation) | PASS | reuses `HttpClient`/`SettingsManager`/`UnifiedDisplay`/web as-is |
| Efficiency / never-regress RAM & FPS (FR-017/021, CLAUDE.md) | PASS (with risk R1) | sequential fetch + parse-and-discard + `gc.collect()`; verify free heap on hardware |
| Never-crash resilience preserved (FR-016) | PASS | existing retry/empty-fallback patterns kept, only payload shape changes |

No violations → Complexity Tracking is empty. These PASS marks reflect the design
direction's alignment with the constraints; the one carried-forward implementation
risk is **R1 (per-park payload RAM on device)**, addressed in Phase 0 and verified
in the hardware task, not a design blocker.

## Project Structure

### Documentation (this feature)

```text
specs/002-themeparks-wiki-api/
├── plan.md              # This file
├── spec.md              # Feature spec (clarifications resolved 2026-06-24)
├── api-research.md      # Raw API probe notes (pre-plan research)
├── research.md          # Phase 0 — decisions D1–D10, payload strategy, risks
├── data-model.md        # Phase 1 — domain entities + status/closed decision tables + migration
├── contracts/           # Phase 1
│   ├── themeparks-wiki-api.md       # external data API consumption contract
│   └── config-and-migration.md      # park-selection field changes (UUID) + upgrade migration
├── quickstart.md        # Phase 1 — run + acceptance walkthrough (maps to spec scenarios)
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root) — files touched by this feature

```text
src/
├── api/theme_park_service.py     # REWORK: endpoints → /destinations + /entity/{id}/live;
│                                 #         sequential per-park fetch + gc; drop queue-times URLs
├── models/
│   ├── theme_park.py             # REWORK: get_rides_from_json parses liveData (ATTRACTION,
│   │                             #         status, queue.STANDBY.waitTime); drop get_url (queue-times)
│   ├── theme_park_list.py        # REWORK: parse /destinations; IDs are str UUIDs (no int cast);
│   │                             #         get_park_by_id str compare; drop queue-times URL helpers;
│   │                             #         clear-on-upgrade migration in load_settings
│   └── theme_park_ride.py        # MINOR: id may be str; open_flag from status=="OPERATING"
├── ui/content_builder.py         # MINOR: REQUIRED_MESSAGE → "ThemeParks.wiki" (attribution)
└── web/config_server.py          # REWORK (park selection only): UUID string IDs — stop int()-cast,
                                   #   %d → %s, pid>0 → non-empty; duplicate-name disambiguation (FR-005a)
tests/                            # REWORK: fixtures → themeparks.wiki JSON; add status/migration/grep tests
```

**Structure Decision**: Option 1 (single project). No new modules, no new
directories, no ScrollKit changes — this is a domain-layer re-platforming within the
existing `src/` layout established by feature 001.

## Phase 0: Outline & Research → research.md ✅

All technical unknowns were resolved by probing the live API and its OpenAPI spec
(captured in `api-research.md`, distilled into `research.md` as decisions D1–D10).
No `[NEEDS CLARIFICATION]` markers remain in the spec (resolved 2026-06-24). Key
decisions: two endpoints (D1); UUID string identity (D3); ATTRACTION-only + status
mapping where any non-`OPERATING` → "Closed" (D5); attribution "ThemeParks.wiki"
(D6); clear-on-upgrade migration (D7); **sequential fetch + parse-and-discard +
`gc.collect()`** for the payload-size risk (D8). The single carried-forward risk is
**R1 (per-park `/live` ≈ 90 KB RAM on device)** → hardware free-heap verification.
**Output**: `research.md`.

## Phase 1: Design & Contracts → ✅

- **Entities** → `data-model.md`: `Destination`→`Park`→`Ride` with the new
  themeparks.wiki field mapping; the **status → open/closed decision table**
  (OPERATING=open; DOWN/REFURBISHMENT/CLOSED="Closed"); the **wait/closed/zero
  display table** (carried from 001, now keyed on the new fields); the
  `selected_park_ids` int→str type change and the clear-on-upgrade migration rule.
- **Contracts** → `contracts/`: the themeparks.wiki API-consumption contract
  (endpoints, request/response shapes, field paths, status enum, error/empty
  handling, payload-size note) and the config-and-migration contract (park-selection
  field changes for UUIDs + the upgrade clear behavior). For this embedded app the
  meaningful "contracts" are these integration surfaces, not REST endpoints we own.
- **Test scenarios** → `quickstart.md` maps 1:1 to the spec's acceptance scenarios;
  automated checks = pytest (mocked `HttpClient` + canned fixtures) plus a grep gate
  asserting no "queue-times" string survives, and `run_headless` screenshots for
  visual parity.

**Post-Design Constitution re-check**: PASS — no new violations; the change stays in
the domain layer and reuses every ScrollKit subsystem unchanged.

## Phase 2: Task Planning Approach

*Describes what `/speckit.tasks` will do — not executed here.*

**Strategy** — tasks dependency-ordered, `[P]` where files are independent, grouped
to keep the build green at each step:

1. **Test fixtures + harness first**: capture trimmed themeparks.wiki fixtures
   (`destinations.json`, one park `/live`), swap the mocked-`HttpClient` test data,
   and write failing parity tests (catalog parse, ATTRACTION filter, status mapping,
   standby extraction, no-standby→0, skip-meet, sort weights, migration clear,
   attribution string, grep-no-queue-times).
2. **Models**: `theme_park_list` (parse `/destinations`, str IDs, `get_park_by_id`
   str compare, drop queue-times URL helpers, clear-on-upgrade migration);
   `theme_park` (parse `liveData` → ATTRACTION rides, status→open_flag,
   `queue.STANDBY.waitTime`→wait, drop `get_url`); `theme_park_ride` (str id). `[P]`
   across the two model files where independent.
3. **Service**: `theme_park_service` endpoints → `/destinations` + `/entity/{id}/live`;
   **sequential** `update_selected_parks` with `gc.collect()` between parks; keep
   retry/empty-fallback; pre-flush loading frame (already in `app.update_data`).
4. **Attribution**: `content_builder.REQUIRED_MESSAGE` → "ThemeParks.wiki".
5. **Web config**: park-selection UUID handling (no `int()`, `%s`, non-empty test);
   duplicate-name disambiguation — render the label as "Park — Destination" so the
   two "Disneyland Park" entries are distinguishable (FR-005a).
6. **Cleanup gate**: grep sweep for `queue-times`/`queue_times`/`parks.json` across
   `src/` + fixtures; remove dead URL helpers.
7. **Verification — desktop**: pytest green + `run_headless` parity screenshots for
   open/closed/multi-park/vacation.
8. **Verification — hardware (REQUIRED)**: live fetch of a real park; **record free
   heap before/after a 4-park refresh** (R1); confirm the data + web processes still
   spawn (memory not gated); web UI park selection with UUIDs persists and refreshes.

**Ordering**: fixtures/tests → models → service → attribution → web → cleanup →
verify. **Estimated output**: ~18–24 tasks (smaller than 001 — domain-layer only, no
new subsystems).

## Phase 3+: Future Implementation

- **Phase 3**: `/speckit.tasks` creates `tasks.md`.
- **Phase 4**: implement per the task ordering above.
- **Phase 5**: validate via `quickstart.md` (simulator + hardware), confirm
  themeparks.wiki-only data, no regression, R1 free-heap acceptable.

## Complexity Tracking

*No constitutional violations to justify (constitution is an unfilled template;
spec-derived gates all PASS). Table intentionally empty.*

## Progress Tracking

**Phase Status**:
- [x] Phase 0: Research complete (/plan) — `research.md` (+ `api-research.md`)
- [x] Phase 1: Design complete (/plan) — `data-model.md`, `contracts/`, `quickstart.md`
- [x] Phase 2: Task planning approach described (/plan)
- [x] Phase 3: Tasks generated (/speckit.tasks) — `tasks.md` (23 tasks)
- [x] Phase 4: Implementation complete (/speckit.implement) — 22/23 tasks; T022 hardware verification pending a device
- [~] Phase 5: Validation passed — desktop: 45 pytest green, grep gate clean, live-API end-to-end (139 parks, MK 35 attractions); hardware free-heap (R1) pending

**Gate Status**:
- [x] Initial Constitution Check: PASS (spec-derived gates; constitution is template placeholder)
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved (spec, 2026-06-24)
- [x] Complexity deviations documented (none)
- [~] Open risk R1 (per-park payload RAM) — design mitigation chosen (sequential + gc); hardware verification deferred to Phase 4

---
*Based on the spec's clarified constraints; project constitution at `.specify/memory/constitution.md` is an unfilled template (no ratified principles).*
