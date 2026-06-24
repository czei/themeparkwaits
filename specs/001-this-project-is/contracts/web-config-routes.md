# Contract: Configuration web UI routes (user-facing)

The device hosts a config page reachable at `http://<domain_name>.local/` (and by IP). This contract must be preserved by the port (FR-010); only the *serving mechanism* changes (now `scrollkit.web.SLDKWebServer` + a `WebHandler` subclass + `StaticFileHandler` for `src/www/` assets). Port = adafruit_httpserver on device / aiohttp on desktop (library adapters).

## Routes
| Method | Path | Behavior |
|---|---|---|
| GET | `/` | Render the configuration page (HTML form pre-filled from current settings). |
| GET/POST | `/settings` | Same form; POST applies submitted settings, saves, and rebuilds the display content queue. |
| GET | `/style.css` | Serve stylesheet from `src/www/style.css`. |
| POST | `/update` | Schedule + download an OTA update, then reboot; `apply_update()` runs in the next `setup()` (not inline in the handler). Progress via `OTAClient.set_callbacks`. Full semantics in `ota-release.md`. |

> Today's app also accepts settings via query params on `/`; the port may consolidate on `/settings` POST as long as the same fields are accepted and the page behaves identically.

## Form fields (must all be accepted and persisted)
| Field | Type | Maps to setting |
|---|---|---|
| `selected_park_ids[]` | up to 4 park IDs | `selected_park_ids` |
| `brightness_scale` | 0.0–1.0 | `brightness_scale` |
| `default_color` | hex | `default_color` |
| `ride_name_color` | hex | `ride_name_color` |
| `ride_wait_time_color` | hex | `ride_wait_time_color` |
| `scroll_speed` | Slow/Medium/Fast | `scroll_speed` |
| `sort_mode` | alphabetical/max_wait/min_wait | `sort_mode` |
| `group_by_park` | checkbox | `group_by_park` (bool) |
| `skip_closed` | checkbox | `skip_closed` (bool) |
| `skip_meet` | checkbox | `skip_meet` (bool) |
| `domain_name` | string | `domain_name` (mDNS hostname) |
| `next_visit`, `next_visit_year`, `next_visit_month`, `next_visit_day` | vacation | `next_visit*` |

## Behavioral guarantees
- Saving a setting persists to `settings.json` and is reflected on the **next display cycle** without a network fetch (FR-004).
- Park-selection or sort/group/filter changes rebuild the content queue immediately.
- URL-decoding of form values uses `scrollkit.utils.url_utils.url_decode` (CircuitPython-safe).
- The page is reachable at the mDNS hostname (app-owned mDNS helper) and by raw IP. **Verify (R3)** the mDNS helper and `SLDKWebServer` coexist on the device (shared socket pool; mDNS start ordering relative to WiFi/web).

## Form-parsing rules (review S5 — make explicit before coding)
- `selected_park_ids[]` is a **repeated** field → parse into a list of ≤4 IDs; preserve legacy single `current_park_id`.
- An **absent** checkbox (`group_by_park` / `skip_closed` / `skip_meet`) means **false** — handle the missing key explicitly, not only the `"on"` case.
- If GET query-param settings on `/` are retained for back-compat, they must map to the same fields/handlers as the `/settings` POST.
- Confirm how `WebHandler` is constructed and how it accesses the app (`SettingsManager` + content builder) — see `scrollkit-api-consumption.md` §"Re-verify before coding".

## First-time WiFi onboarding (separate, library-owned)
Before normal operation, with no stored credentials the device runs `WiFiManager.start_access_point()` + `register_routes()` (`/configure`) + `run_web_server(...)` — a standalone AP/captive-portal flow that captures SSID/password, persists them, and reboots. This is distinct from the config server above.
