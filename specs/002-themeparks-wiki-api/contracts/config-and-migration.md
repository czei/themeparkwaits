# Contract — config web UI park selection + upgrade migration

The web routes are **unchanged** (`GET /`, `GET|POST /settings`, `POST /update`,
static files — see feature 001's `web-config-routes.md`). This feature changes only
how **park identifiers** flow through park selection (int → UUID string) and adds a
one-time upgrade migration.

## Park-selection field changes (`src/web/config_server.py`)

The four park dropdowns (`park_1..park_4`) now carry **UUID string** values.

| Location | Before (queue-times int) | After (themeparks.wiki uuid) |
|---|---|---|
| `apply_settings` parse | `pid = int(raw); if pid > 0` | use `raw` as-is; `if raw` (non-empty) |
| dedupe | `pid not in ids` | `raw not in ids` |
| store | `selected_park_ids = ids` (int) | `selected_park_ids = ids` (str) |
| `render_page` option value | `'<option value="%d">' % p.id` | `'<option value="%s">' % p.id` |
| selected match | `cur == p.id` (int) | `cur == p.id` (str) |
| `current_park_id` | `int(...)` | str |

`theme_park_list.parse` (query-string path, `park-id-N=`) likewise stops
`int()`-casting and compares park ids as strings; `get_park_by_id` does a string
compare.

**Duplicate-name disambiguation (FR-005a, in scope)**: only "Disneyland Park" is
duplicated (Paris vs. Anaheim). The dropdown label MUST be rendered as
`"{park.name} — {destination.name}"` so the two entries are distinguishable. This
requires carrying the destination name alongside the park during catalog
flattening. (Selection by unique UUID is correct either way; this fixes the *label*
ambiguity.)

## Behavior preserved
- Up-to-4 limit (`MAX_PARKS = 4`).
- Unchecked checkbox = absent (skip_closed / skip_meet / group_by_park).
- POST applies settings + rebuilds the content queue with **no** network fetch, then
  303-redirects; a fire-and-forget `_schedule_refresh` fetches a newly-selected
  park's live data within seconds.
- URL-decoding of form values (`url_decode`).

## Upgrade migration (clear-and-reprompt) — `theme_park_list.load_settings`

Runs once when settings are loaded:
1. Read `selected_park_ids`.
2. Mark an id **legacy** if it is an `int`, an all-digit string, or any string that
   is not UUID-shaped (no `-`).
3. If **any** id is legacy → clear and persist:
   `selected_park_ids = []`, `selected_park_names = []`, and drop
   `current_park_id` / `current_park_name`.
4. Outcome: no selected parks → the board shows the existing
   "Choose theme park at http://{domain}.local" prompt; the user re-selects from the
   themeparks.wiki catalog. No crash, no permanently blank board (FR-019, SC-006).

## Acceptance
- Selecting parks via the web UI persists UUID ids across reboot and the board shows
  those parks on the next refresh.
- A `settings.json` carrying old integer `selected_park_ids` boots to the
  choose-a-park prompt (not a crash), and re-selection then works.
