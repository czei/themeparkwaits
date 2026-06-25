# Phase 0 Research — themeparks.wiki data-source port

Distilled from live API probing + the OpenAPI spec (full notes in
`api-research.md`). Every decision below is anchored to the spec's requirements and
the project's CLAUDE.md efficiency rules. No `[NEEDS CLARIFICATION]` markers remain.

## Decisions

### D1 — Two endpoints (mirror the current two-call shape)
- **Catalog**: `GET https://api.themeparks.wiki/v1/destinations`
- **Live wait times**: `GET https://api.themeparks.wiki/v1/entity/{parkId}/live`
- Rationale: these two cover everything the app needs; `/entity/{id}`,
  `/entity/{id}/children`, and `/entity/{id}/schedule` add nothing for parity.
  Maps cleanly onto the old `parks.json` + `parks/{id}/queue_times.json` pair.

### D2 — No authentication
- The OpenAPI spec defines no security scheme; anonymous requests return 200.
- No API key, no `secrets.py` change. Matches the app's existing no-token posture
  (FR-018).

### D3 — Park identity is a UUID string
- themeparks.wiki IDs are UUIDs (e.g. `75ea578a-…` = Magic Kingdom), not integers.
- `selected_park_ids` becomes `str[]`. All `int()`-casting of park IDs is removed
  (`theme_park_list.parse`, `config_server.apply_settings`); `get_park_by_id` and
  option rendering compare/emit strings (`%d` → `%s`).

### D4 — Catalog parsing
- `/destinations` → `{destinations:[{id,name,slug,externalId,parks:[{id,name}]}]}`.
  Flatten `destinations[].parks[]` into the app's park list as `{id:uuid, name}`.
- **Drop latitude/longitude** — they are not in this payload, and the app never
  functionally uses them (the clock uses NTP, not park location; the lat/long
  fields and `get_park_location_from_id` are vestigial).
- Catalog is **139 parks across 106 destinations** — *comparable* to queue-times'
  **141** parks, so the on-device config-page dropdowns (~556 `<option>` across 4
  selects, ~32 KB) are **not** a regression.
- Only **one** duplicate park name exists ("Disneyland Park" — Paris vs. Anaheim).
  Selection is unambiguous because IDs are unique, but the *label* is ambiguous for
  that one case, so the dropdown label is rendered as "Park — Destination" to
  disambiguate (FR-005a). This requires carrying the destination name through catalog
  flattening.

### D5 — Live parsing + status mapping
From `/entity/{parkId}/live` → `{liveData:[{id,name,entityType,status,queue}]}`:
- Keep only items where `entityType == "ATTRACTION"` (exclude SHOW, RESTAURANT,
  HOTEL, and the PARK entity) — FR-020.
- `wait_time = queue.STANDBY.waitTime`, coerced to int. `waitTime` may be **absent
  or present-but-null** (the schema marks several queue waits `nullable`), so the
  rule is `int(w) if w is not None else 0` — not merely a key-presence check.
- `open_flag = (status == "OPERATING")`. Status enum is
  `OPERATING | DOWN | CLOSED | REFURBISHMENT`; **every non-`OPERATING` value maps to
  the existing "Closed" treatment** (FR-014, edge case).
- Park open/closed: `park.is_open = any attraction with open_flag True` (preserves
  today's behavior). themeparks.wiki *also* returns an authoritative `PARK` entity
  `status` in `liveData` — not used for parity, but it is the signal to switch to if
  the any-ride heuristic ever misbehaves at the edges (e.g. early entry, or park
  OPERATING while all rides are still pre-opening). See R5.
- `ThemeParkRide.is_open()` (`open_flag and wait_time > 0`) is unchanged and still
  governs the skip-closed *filter* and the wait-based *sort weight*; `open_flag`
  alone still governs the wait-vs-"Closed" *display* choice (an OPERATING ride with
  no/zero standby still shows "0"). This is the same closed/zero-wait contract as
  feature 001, re-keyed onto the new fields.

### D6 — Attribution
- `content_builder.REQUIRED_MESSAGE = "ThemeParks.wiki"`; message becomes
  "Wait times for {parks} provided by ThemeParks.wiki".
- No specific wording/link is mandated (backend is MIT-licensed, API is free);
  crediting the source preserves the app's existing attribution behavior (FR-004).

### D7 — Upgrade migration: clear and re-prompt
- Old saved `selected_park_ids` are queue-times integers — invalid as UUIDs.
- **Decision (user-chosen): clear them on first run after update** and let the user
  re-select from the catalog (FR-019, SC-006). No name-based auto-migration.
- Detection rule (in `theme_park_list.load_settings`, run once): a saved id is
  *legacy* if it is an `int` or an all-digits string (or otherwise not a UUID-shaped
  string with hyphens). If any selected id is legacy, clear
  `selected_park_ids` / `selected_park_names` / `current_park_id` /
  `current_park_name`. The board then shows the existing "Choose theme park…"
  prompt — never a crash or blank board.

### D8 — Payload-size strategy (the one real engineering decision)
- `/live` is **~90 KB per park** (Magic Kingdom 92 KB) vs queue-times' ~5 KB
  (~18×), because it bundles shows/restaurants and rich queue/showtime objects, and
  there is **no server-side filter**. Four parks ≈ 370 KB of JSON per refresh.
- **Mitigation**: fetch selected parks **sequentially** (replace the current
  `asyncio.gather` of four simultaneous fetches), parse each response immediately to
  the compact attraction list, drop the raw text + parsed dict, and `gc.collect()`
  before the next park — so peak RAM holds **one** large payload, not four. The
  retained per-park data (≈35 rides × name/wait/status) is small.
- Keep the pre-flushed loading frame before each blocking fetch (already in
  `app.update_data` / `_status("Times")`); HTTP remains synchronous so yields happen
  only *between* parks.
- This satisfies FR-021 and the CLAUDE.md "don't regress RAM/FPS" rule by design;
  the absolute headroom is verified on hardware (R1).

### D9 — Testing approach
- Unit/parity: `pytest` with a mocked `HttpClient` returning **canned
  themeparks.wiki fixtures** — a trimmed `/destinations` and one park `/live`
  (captured from the real API). Replace the queue-times fixtures.
- Assertions: catalog flattening; ATTRACTION-only filter; status→open/closed for all
  four enum values; `STANDBY.waitTime` extraction and no-standby→0; skip-meet;
  sort-weight of closed rides; migration clears legacy integer IDs; attribution
  string; and a **grep gate** that "queue-times"/"queue_times"/"parks.json" appears
  nowhere under `src/`.
- Visual parity: `scrollkit.dev.run_headless` screenshots (open ride, closed ride,
  closed park, multi-park, vacation). `SCROLLKIT_HW_SIM=1` advisory timing.
- Hardware (required, Phase 4): live fetch of a real park; **free-heap before/after a
  4-park refresh (R1)**; confirm data + web processes still spawn (not memory-gated);
  UUID park selection persists + refreshes via the web UI.

### D10 — Complete queue-times removal
- Remove queue-times URLs and helpers: `ThemePark.get_url`,
  `ThemeParkList.get_park_url_from_id` / `get_park_url_from_name` (or delete — unused
  after the swap), the `parks.json` / `queue_times.json` URLs in
  `theme_park_service`, and `REQUIRED_MESSAGE`.
- Enforced by the D9 grep gate (FR-003, SC-001/SC-005).

## Risks

| ID | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | Per-park `/live` ≈ 90 KB; 4 parks ≈ 370 KB transient — peak RAM could gate the data/web processes off on the S3. Note the **38 KB `/destinations` catalog (~139 park objects) is resident for the app's lifetime** (the web dropdowns read it), so the worst case is the resident catalog *plus* one `/live` transient. | **High** | D8 sequential fetch + parse-and-discard + `gc.collect()`; measure free heap on hardware **with the catalog resident** (Phase 4 / quickstart hardware step) |
| R2 | One duplicate park name ("Disneyland Park") is ambiguous in the dropdown | Low | "Park — Destination" label (FR-005a) — now in scope; selection is correct regardless (unique UUID) |
| R3 | themeparks.wiki occasionally returns a park `/live` with no STANDBY for some operating rides (e.g. splash pads) | Low | Treat as open-with-0 (D5) — consistent with today's open-with-0 handling |
| R4 | API shape drift (statuses/queue keys added later) | Low | Parse defensively (`.get`), ignore unknown entity types/statuses (unknown status ≠ OPERATING → "Closed") |
| R5 | Park open/closed via the "any ride OPERATING" heuristic could differ from the authoritative `PARK` status at the edges (early entry, pre-opening) | Low | Parity default; switch to the `PARK` entity `status` in `liveData` if observed behavior is wrong (D5) |

## Open decisions
None. All spec clarifications resolved 2026-06-24; R1 is an implementation
verification item, not a design decision.
