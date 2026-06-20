# Phase 1 Data Model: ThemeParkWaits (post-port)

**Feature**: `001-this-project-is` | **Date**: 2026-06-20

Entities below are the app's **domain + presentation state**. Domain entities stay app-owned (the library has no theme-park concepts); presentation entities are app subclasses built on library base classes; settings/release entities are owned by the library and merely configured by the app.

## Domain entities (app-owned)

### ThemePark
- **Fields**: `id: int`, `name: str` (ASCII-normalized), `latitude: float`, `longitude: float`, `is_open: bool`, `rides: list[ThemeParkRide]`.
- **Rules**: `name` strips non-ASCII (international parks); `is_open` is true if any ride is open; `get_url()` → `https://queue-times.com/parks/{id}/queue_times.json`.
- **Source**: `src/models/theme_park.py` (kept).

### ThemeParkRide
- **Fields**: `id: int`, `name: str`, `wait_time: int` (minutes), `open_flag: bool`.
- **Rules**: `is_open()` ⇔ `open_flag and wait_time > 0` (API reports closed parks' rides as open/0). Meet-&-greet detected by name (for `skip_meet`). Closed rides sort as wait `0`.
- **Source**: `src/models/theme_park_ride.py` (kept).

### ThemeParkList
- **Fields**: `park_list: list[ThemePark]` (all parks), `selected_parks: list[ThemePark]` (≤ 4), `current_park` (legacy single-park back-compat), `skip_meet: bool`, `skip_closed: bool`.
- **Rules**: `load_settings()` reads `selected_park_ids` (falls back to legacy `current_park_id`); `get_park_by_id()`.
- **Source**: `src/models/theme_park_list.py` (kept).

### Vacation
- **Fields**: `name: str`, `year: int`, `month: int`, `day: int`.
- **Rules**: `is_set()` ⇔ name set ∧ year ≥ 2000 ∧ valid month/day; `get_days_until()` (via `adafruit_datetime`). Drives countdown: `>1 day` → "in N days"; `1` → "tomorrow"; `0` → "TODAY".
- **Source**: `src/models/vacation.py` (kept).

### WaitTimeSnapshot (in-memory, transient)
- **Represents**: the current set of rides per selected park after a refresh. Not persisted; rebuilt every `update_interval` (300 s) and used to (re)build display content.
- **Validation**: a failed/empty fetch leaves the prior snapshot in place and surfaces a status message (never crashes — FR-014).

## Presentation entities (app subclasses on library base classes)

### RideScreenContent  *(extends `scrollkit.display.content.DisplayContent`)*
- **Fields**: `ride_name: str`, `wait_minutes: int`, plus colors/brightness from settings.
- **render()**: scrolling ride name (top region) + large 2×-scale centered wait number (bottom region). Library gap → custom composition via `display.draw_text(...)` + a scaled bitmap font (see research D3, R2).
- **Constraints (review S1/B2)**: render strictly through `UnifiedDisplay` primitives (no bypassing the display / owning matrix refresh); **load the font once**, no per-frame `Label`/`Bitmap`/`Group` allocation; **first resolve** whether `draw_text`/`clear`/`show` are sync/async and whether `render()` may call them directly (API survey listed `draw_text` async but `render(display)` as a plain override — reconcile against source). Define `is_complete`/`duration` for the simultaneous scrolling-name + static-number screen; state whether `render()` or the framework owns per-frame `clear()`/`show()`.

### ClosedRideContent / message content
- `ClosedRideContent`: renders the closed treatment per the decision table below.
- Generic messages (config URL, "updating…", attribution, vacation countdown, closed-park, errors) use library `ScrollingText` / `StaticText` directly — no subclass.

### Display decision table — closed / zero-wait / closed park  *(review S2)*
| Condition | Treatment | Sort/filter |
|---|---|---|
| Park has no open rides (`ThemePark.is_open == False`) | one "<Park> is closed" message (not per-ride screens) | n/a |
| Ride `open_flag == False` | `ClosedRideContent` ("Closed") | sorts as wait `0`; hidden if `skip_closed` |
| Ride `open_flag == True` **and** `wait_time == 0` | preserve current behavior explicitly — treat as "not open" per `ThemeParkRide.is_open()`, i.e. closed treatment | sorts as wait `0`; hidden if `skip_closed` |
| Ride `open_flag == True` **and** `wait_time > 0` | `RideScreenContent` (name + number) | sorts by `wait_time` |
> This resolves the prior inconsistency where `ClosedRideContent` was described as `open_flag == False` only while the domain rule (`is_open ⇔ open_flag and wait_time > 0`) also makes a zero-wait "open" ride non-open.

### ContentBuilder (app logic, not an entity)
- Consumes the `WaitTimeSnapshot` + `DeviceSettings` and produces an ordered list of the above content objects into `self.content_queue` (`scrollkit.display.content.ContentQueue`). Encodes sort (`alphabetical` | `max_wait` | `min_wait`), `group_by_park`, `skip_closed`, `skip_meet`, multi-park, vacation insertion, attribution. Rebuilt on refresh and on settings change.

## Library-owned entities (app configures, does not define)

### DeviceSettings  → `scrollkit.config.SettingsManager`
- **File**: `settings.json`. **Keys / defaults** (passed by the app):
  `domain_name="themeparkwaits"`, `brightness_scale="0.5"`, `default_color=Yellow`, `ride_name_color=Blue`, `ride_wait_time_color=Old Lace`, `scroll_speed="Medium"`, `sort_mode="alphabetical"`, `group_by_park=false`, `skip_closed=false`, `skip_meet=false`, `display_mode="all_rides"`, `use_prerelease=false`, `selected_park_ids=[]` (legacy `current_park_id`), `next_visit`, `next_visit_year/month/day`, legacy `subscription_status`/`email`.
- **bool_keys**: `skip_closed`, `skip_meet`, `group_by_park`, `use_prerelease`.
- **Rules**: missing keys fall back to defaults (FR-011); booleans tolerate string storage; scroll-speed map (Slow .06 / Medium .04 / Fast .02) **verify the library actually provides this map** (S9) — else keep a small app helper. Normalize at the settings boundary: `brightness_scale`→float, colors→one representation (verify `ColorUtils` accepts the named colors `Yellow`/`Blue`/`Old Lace`) (N3).
- **Credentials (review S4)**: WiFi SSID/password are **not** a DeviceSettings key here — confirm whether the library `WiFiManager` reads them from `secrets.py`, `settings.json`, or both, document the chosen location, and **exclude that file from the OTA file set** so updates never wipe credentials.
- **`use_prerelease` (review S8)**: orphaned under the public-branch OTA model (no token/Releases-API channel) → remove from defaults/bool_keys, or remap to a separate manifest/branch in `contracts/ota-release.md`.

### Release / UpdateManifest  → `scrollkit.ota.OTAClient` (+ `manifest.json`)
- **Fields** (manifest): `version`, `files{path:{size,checksum}}`, optional pre/post scripts.
- **Rules**: semantic-version compare; SHA-256 verify (integrity, **not** publisher authenticity — public branch is world-readable); backup/restore on failure; progress via callbacks ("Installing… do not unplug"). **Resolved (2026-06-20)**: device uses `OTAClient.for_github(owner, repo, branch="releases", current_version=...)` against a **public `releases` branch + `manifest.json`**, no device-side auth.
- **Full release/update contract → `contracts/ota-release.md`** (review B3): manifest schema + generation command, path allowlist **excluding `secrets.py`/`settings.json`/logs**, `current_version` read/bump, whether `scrollkit/` is OTA-managed, backup/restore storage headroom, rollback test, and `/update` route semantics.

## Relationships
```
ThemeParkList 1──* ThemePark 1──* ThemeParkRide
DeviceSettings ──drives── ContentBuilder ──reads── WaitTimeSnapshot(per selected ThemePark)
ContentBuilder ──emits──> ContentQueue ──holds──> {RideScreenContent | ClosedRideContent | ScrollingText | StaticText}
Vacation ──(if set)──> countdown content item in the queue
WiFiManager ──reads/writes──> credentials (secrets.py or settings.json — confirm; excluded from OTA)
OTAClient ──(use_prerelease orphaned under public-branch model — remove/remap)
```

## State transitions (device lifecycle)
`setup()` is a pre-run state machine (runs **before** `run()` spawns the loops); status is drawn **directly**; onboarding/OTA branches **reboot** and never enter `run()` (review B1, plan.md "Boot Lifecycle"):
```
BOOT → setup():
   splash(reveal, drawn directly)
   → if NO creds: WiFiManager AP/captive-portal ONLY → persist creds → REBOOT (no normal web server)
   → station connect (retry; on fail show status, continue degraded — never crash)
   → if pending OTA: show status → apply_update() → REBOOT
   → NTP clock → fetch park list → fetch wait times (sync; pre-flush loading frame) → build content queue
   → return
RUN  → display loop (always) ∥ data update every 300 s ∥ web config server (created ONLY now)
       settings change (web) → save → rebuild content queue (no fetch)
       data refresh → new WaitTimeSnapshot → rebuild content queue
LOW-MEM → data/web processes auto-skip; display keeps running (library degradation;
          verify on real hardware that normal operation does NOT trip this — else parity fails)
UPDATE → POST /update → schedule + download → reboot → apply_update() in next setup()
```
