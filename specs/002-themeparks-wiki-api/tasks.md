---
description: "Task list for feature 002 — source theme-park data from themeparks.wiki"
---

# Tasks: Source Theme-Park Wait Times from themeparks.wiki

**Input**: Design documents from `/specs/002-themeparks-wiki-api/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — the spec defines acceptance scenarios and the plan/quickstart
mandate pytest + a grep gate + headless screenshots. Write tests first; ensure they
FAIL before implementing.

**Scope reality**: This is a domain-layer re-platforming, not greenfield. The data
layer (`src/models/*`, `src/api/theme_park_service.py`) is shared by US1 and US2, so
it lives in **Foundational**; the per-story phases then add the story-specific
behavior on top. No new modules, no ScrollKit changes.

## Format: `[ID] [P?] [Story] Description`
- **[P]**: can run in parallel (different files, no dependency)
- **[Story]**: US1 / US2 / US3 (or FND/SETUP/POLISH for shared work)
- Exact file paths are absolute from repo root `/Users/czei/Documents/Projects/ScrollKit/themeparkwaits/`

---

## Phase 1: Setup — fixtures & mock harness

**Purpose**: Replace the canned queue-times test data with themeparks.wiki fixtures so
every later test runs offline against the new payload shapes.

- [x] **T001** [P] [SETUP] Capture themeparks.wiki fixtures into `tests/fixtures/`:
  - `tests/fixtures/themeparks_destinations.json` — trimmed `/v1/destinations` body
    containing at minimum: Walt Disney World (parks "Magic Kingdom Park", "EPCOT")
    **and** two destinations that each contain a park named **"Disneyland Park"**
    (Disneyland Paris + Disneyland Resort) to exercise FR-005a disambiguation.
  - `tests/fixtures/themeparks_mk_live.json` — trimmed `/v1/entity/{id}/live` body
    whose `liveData` covers every branch: an `ATTRACTION` `OPERATING` with
    `queue.STANDBY.waitTime`; an `ATTRACTION` `OPERATING` with **no STANDBY**
    (waitTime absent **and** one present-but-`null`); one each `DOWN`,
    `REFURBISHMENT`, `CLOSED` attraction; a meet-and-greet `ATTRACTION` whose name
    contains "Meet"; a `SHOW`; a `RESTAURANT`; and the `PARK` entity.
  - Source command (for reference): `curl https://api.themeparks.wiki/v1/destinations`
    and `curl https://api.themeparks.wiki/v1/entity/75ea578a-adc8-4116-a54d-dccb60765ef9/live`.

- [x] **T002** [SETUP] Rewrite the canned provider in `tests/conftest.py`:
  - Replace `PARKS_JSON` → `DESTINATIONS_JSON` (load `themeparks_destinations.json`)
    and `QUEUE_TIMES_JSON` → `LIVE_JSON` (load `themeparks_mk_live.json`).
  - Rewrite `_canned_provider(url)` routing: `url.endswith("/destinations")` →
    destinations fixture; `"/live" in url` (i.e. `/entity/{id}/live`) → live fixture;
    else 404. Keep the `MockResponse` / `HttpClient(mock_provider=...)` wiring and the
    `settings_factory` fixture unchanged.
  - (Depends on T001; same file as nothing else in this phase.)

**Checkpoint**: `pytest` import-collects; the mock serves tpwiki shapes.

---

## Phase 2: Foundational — shared data layer (BLOCKS US1 & US2)

**⚠️ CRITICAL**: US1 and US2 both depend on these. Parse + fetch must work before
story behavior is testable.

- [x] **T003** [P] [FND] `src/models/theme_park_ride.py`: allow a **string** `id`
  (UUID) — update the docstring/typing; no behavioral change. `is_open()`
  (`open_flag and wait_time > 0`) stays as-is.

- [x] **T004** [FND] `src/models/theme_park.py` — rewrite ride parsing for `/live`:
  - Replace `get_rides_from_json` / `_process_ride` to iterate `json_data["liveData"]`,
    keep only items where `entityType == "ATTRACTION"`, and build `ThemeParkRide(name,
    id, wait_time, open_flag)` with: `name = remove_non_ascii(item["name"])`;
    `open_flag = (item.get("status") == "OPERATING")`; `wait_time = w` where
    `w = item.get("queue",{}).get("STANDBY",{}).get("waitTime")` coerced
    `int(w) if w is not None else 0`. Set `self.is_open = True` if any attraction is
    `open_flag`.
  - `is_valid()` → `bool(self.id)` (non-empty string) instead of `id > 0`.
  - **Remove** `get_url()` (queue-times URL). Keep `remove_non_ascii`, `update()`,
    counter/iteration helpers. Defensive `.get` throughout (FR-016).
  - (data-model.md "Ride"/"Park"; contracts/themeparks-wiki-api.md §2.)

- [x] **T005** [FND] `src/models/theme_park_list.py` — parse `/destinations`:
  - Rewrite `__init__` to read `json_response["destinations"]`, flatten
    `destination["parks"]`, and build `ThemePark` per park with string `id` and
    ASCII-stripped `name`. **Carry the destination name** (e.g. store
    `park.destination_name`) for FR-005a. Drop latitude/longitude. Keep the
    alphabetical sort.
  - `get_park_by_id` compares ids as strings; `parse()` (query `park-id-N=`) stops
    `int()`-casting (use the raw string, accept non-empty).
  - **Remove** `get_park_url_from_id` / `get_park_url_from_name` / queue-times URLs.
  - Keep `load_settings` / `store_settings` (the migration is added in T014).
  - (data-model.md; contracts/themeparks-wiki-api.md §1.)

- [x] **T006** [FND] `src/api/theme_park_service.py` — endpoints + memory-safe fetch:
  - `fetch_park_list`: URL → `https://api.themeparks.wiki/v1/destinations`; pass the
    parsed body straight to `ThemeParkList(...)`. Keep the retry/empty-fallback loop.
  - `fetch_park_data` / `get_rides_for_park_async`: URL →
    `https://api.themeparks.wiki/v1/entity/%s/live` (string id). Keep retries.
  - `update_selected_parks`: replace the `asyncio.gather` of all parks with a
    **sequential** loop (`for park in selected_parks: await _update_single_park(park)`)
    and `import gc; gc.collect()` after each park, so peak RAM holds one ~90 KB
    payload (research D8 / R1). Keep per-park error isolation + count.
  - `get_available_parks`: return `{id, name}` (+ optional `destination`); drop
    latitude/longitude.
  - (contracts/themeparks-wiki-api.md §3; research D8.)

**Checkpoint**: the data layer fetches + parses tpwiki catalog and live data offline.

---

## Phase 3: User Story 1 — Live wait times from themeparks.wiki (P1) 🎯 MVP

**Goal**: A configured park renders live standby waits + closed treatment, sourced
from themeparks.wiki, with attribution to ThemeParks.wiki.

**Independent Test**: feed the mock `/live`, build the content queue, assert ride
screens / "Closed" / closed-park / attribution.

### Tests (write first, must FAIL)
- [x] **T007** [P] [US1] `tests/domain/test_models.py`: status→display mapping for all
  four enum values (OPERATING→open; DOWN/REFURBISHMENT/CLOSED→closed); STANDBY
  present / absent / `null` → wait 0; ATTRACTION-only filter (SHOW/RESTAURANT/PARK
  excluded); non-ASCII name stripped; `is_valid()` on a UUID. Use the T001 fixtures.
- [x] **T008** [P] [US1] `tests/domain/test_content_builder.py`: an OPERATING ride →
  `RideScreenContent`; a non-OPERATING ride → `ClosedRideContent`; a park with no
  open ride → "{park} is closed"; the cycle ends with an attribution containing
  "ThemeParks.wiki" and **never** "queue-times".

### Implementation
- [x] **T009** [US1] `src/ui/content_builder.py`: set
  `REQUIRED_MESSAGE = "ThemeParks.wiki"` (attribution string becomes "Wait times for
  {parks} provided by ThemeParks.wiki"). No change to filter/sort/group logic.
- [x] **T010** [US1] Visual parity via `scrollkit.dev.run_headless` / `tools/sim_shot.py`:
  capture open-ride, closed-ride, and closed-park screenshots from tpwiki data and
  eyeball against current behavior (quickstart US1 rows).

**Checkpoint**: with a park configured, the board shows tpwiki live times + closed
treatment + ThemeParks.wiki attribution.

---

## Phase 4: User Story 2 — Choose parks from the catalog (P2)

**Goal**: Browse the tpwiki catalog (UUIDs), select up to 4 (disambiguated names),
persist across reboot; legacy integer selections are cleared on upgrade.

**Independent Test**: feed the mock `/destinations`, render the config page, apply a
selection, assert persisted UUIDs; seed legacy int ids → assert cleared.

### Tests (write first, must FAIL)
- [x] **T011** [P] [US2] `tests/domain/test_models.py` (catalog section): `/destinations`
  flattening yields parks with string ids; the two "Disneyland Park" entries each
  carry their destination name; `get_park_by_id("<uuid>")` works.
- [x] **T012** [P] [US2] `tests/domain/test_models.py` (migration section):
  `ThemeParkList.load_settings` with `selected_park_ids=[6,5]` (legacy ints) clears
  `selected_park_ids`/`selected_park_names`/`current_park_id`/`current_park_name`;
  with valid UUIDs it keeps them (FR-019, SC-006).
- [x] **T013** [P] [US2] `tests/contract/test_web_config.py`: POST `/settings` with
  `park_1=<uuid>` stores a string in `selected_park_ids` and round-trips; the
  rendered page emits `<option value="<uuid>">` and pre-selects it; the two
  "Disneyland Park" options render distinct "Park — Destination" labels.

### Implementation
- [x] **T014** [US2] `src/models/theme_park_list.py` `load_settings`: add the one-time
  **clear-on-upgrade migration** — if any `selected_park_ids` entry is an `int`, an
  all-digit string, or not UUID-shaped (no `-`), clear all four selection keys and
  persist. (Same file as T005 → sequential, after T005.) (contracts/config-and-migration.md.)
- [x] **T015** [US2] `src/web/config_server.py` park selection for UUIDs:
  - `apply_settings`: drop `int(raw)`/`pid > 0`; accept non-empty `raw`, dedupe by
    string, store `selected_park_ids` (str) + `current_park_id` (str).
  - `render_page` `park_select`: option value `%s` (not `%d`); `cur == p.id` string
    compare; **label = "{name} — {destination_name}"** when the park name is
    duplicated in the catalog (FR-005a) — otherwise just the name.
  - `theme_park_list.parse` already de-int'd in T005; verify the `/settings` path.

**Checkpoint**: park selection persists UUIDs + survives reboot; legacy devices boot
to the choose-a-park prompt (no crash).

---

## Phase 5: User Story 3 — Preserve all board behaviors (P3)

**Goal**: sort modes, skip-closed, skip-meet, group-by-park, multi-park, and the
vacation countdown behave identically on tpwiki data.

**Independent Test**: toggle each setting over the mock data; assert ordering/contents.

### Tests (write first, must FAIL where data changed)
- [x] **T016** [P] [US3] `tests/domain/test_content_builder.py`: max_wait / min_wait
  ordering with closed rides weighted 0; `skip_closed` omits non-operating (and
  open-with-0) rides; `skip_meet` omits the "Meet" attraction; `group_by_park` with
  two parks emits per-park headings.
- [x] **T017** [P] [US3] `tests/domain/test_vacation.py`: vacation countdown messages
  unchanged (data-source-independent) — confirm still green against the new fixtures.

### Implementation
- [x] **T018** [US3] No new logic expected — `src/ui/content_builder.py` filter/sort/
  group paths are unchanged. Fix any breakage the new field types surface (e.g. ride
  `id` type in comparisons); confirm `_filter_rides`/`_sort_rides`/group branches pass.

**Checkpoint**: all preserved behaviors green on tpwiki data.

---

## Phase 6: Polish & cross-cutting

- [x] **T019** [POLISH] **Grep gate (FR-003)**: remove every remaining
  `queue-times` / `queue_times` / `parks.json` reference across `src/` and `tests/`
  (URL helpers, comments, fixtures). Add an assertion to `tests/contract/` (e.g.
  extend `test_no_legacy_imports.py`) that greps `src/` and fails on any hit.
  Command check: `grep -rniE 'queue-?times|parks\.json' src/ tests/` → no output.
- [x] **T020** [P] [POLISH] `src/settings_schema.py`: update the comment/docs noting
  `selected_park_ids` is now a list of UUID strings; default `[]` unchanged.
- [x] **T021** [POLISH] Desktop validation per `quickstart.md`: `pytest tests/` green;
  grep gate clean; `run_headless` parity screenshots (open/closed/closed-park/
  multi-park/vacation).
- [ ] **T022** [POLISH] **Hardware verification (REQUIRED before release — R1)**: on
  the Matrix Portal S3, configure 1 then 4 parks; record `gc.mem_free()` before/after
  a 4-park refresh **with the ~139-park catalog resident**; confirm the data + web
  processes still spawn (not memory-gated); confirm UUID park selection persists +
  triggers a prompt refresh; pull WiFi mid-refresh → no crash.
- [x] **T023** [P] [POLISH] Update `CLAUDE.md` (and any `docs/active`) to record the
  themeparks.wiki source (endpoints, no-auth, attribution, the sequential-fetch RAM
  note); drop queue-times references.

---

## Dependencies & Execution Order

- **Setup (T001–T002)** → first. T002 depends on T001.
- **Foundational (T003–T006)** depends on Setup. T003 `[P]`; T004 `[P]` (theme_park.py)
  and T005 `[P]` (theme_park_list.py) are different files; **T006 depends on T004+T005**
  (service constructs both). BLOCKS US1 + US2.
- **US1 (T007–T010)**: tests after Foundational; T009 (content_builder) before T010.
- **US2 (T011–T015)**: tests after Foundational; **T014 depends on T005** (same file);
  T015 (config_server) independent of T014's file but logically after T005.
- **US3 (T016–T018)**: after Foundational + T009 (content_builder attribution landed).
- **Polish (T019–T023)**: after all code changes. T021 before T022. T019 after every
  source edit.

### Within each story
- Write tests first (they must FAIL), then implement. Models before service before web.

### Parallel opportunities
- T001 ∥ (nothing — T002 waits on it).
- **Foundational**: T003 ∥ T004 ∥ T005 (then T006).
- **US1 tests**: T007 ∥ T008. **US2 tests**: T011 ∥ T012 ∥ T013. **US3 tests**: T016 ∥ T017.
- **Polish**: T020 ∥ T023.

---

## Parallel Example: Foundational models

```bash
# After Setup, launch the independent model edits together:
Task: "T003 string id in src/models/theme_park_ride.py"
Task: "T004 parse /live -> ATTRACTION rides in src/models/theme_park.py"
Task: "T005 parse /destinations + string ids in src/models/theme_park_list.py"
# then, once T004 & T005 land:
Task: "T006 endpoints + sequential fetch in src/api/theme_park_service.py"
```

## Parallel Example: User Story 2 tests

```bash
Task: "T011 catalog-parse test in tests/domain/test_models.py"
Task: "T012 migration clear test in tests/domain/test_models.py"   # same file → run sequentially if edited together
Task: "T013 web UUID round-trip test in tests/contract/test_web_config.py"
```

---

## Implementation Strategy

### MVP first (US1)
1. Setup (T001–T002) → Foundational (T003–T006).
2. US1 (T007–T010). **STOP & validate**: a configured park shows tpwiki live times +
   attribution. This is the demonstrable MVP.

### Incremental delivery
- + US2 (T011–T015): catalog selection + migration → test → demo.
- + US3 (T016–T018): parity verification → test → demo.
- Polish (T019–T023): grep gate, docs, desktop + **hardware** validation (R1).

## Notes
- `[P]` = different files, no dependency; same-file tasks run sequentially.
- Verify each test FAILS before implementing.
- Keep all parsing defensive (`.get`, null-safe) to preserve never-crash resilience.
- R1 (per-park ~90 KB payload) is verified on hardware in T022 — do not skip.
- Estimated: 23 tasks (matches plan's ~18–24 for a domain-layer-only change).
