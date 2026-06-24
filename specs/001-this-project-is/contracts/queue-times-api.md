# Contract: queue-times.com data API (external, app-owned)

The wait-time data source. The library has no theme-park concepts, so the fetch + parse stays app code (`src/api/theme_park_service.py`, reworked onto `scrollkit.network.HttpClient`). The provider and refresh contract MUST NOT change (spec Out of Scope).

## Endpoints
| Method | URL | Returns |
|---|---|---|
| GET | `https://queue-times.com/parks.json` | All parks, grouped by company; each park has `id`, `name`, `latitude`, `longitude`. |
| GET | `https://queue-times.com/parks/{park_id}/queue_times.json` | Current wait times for one park: ride `lands[].rides[]` and `rides[]` with `name`, `wait_time`, `is_open`. |

## Parsing rules (preserved)
- Park `name` is ASCII-normalized (`ThemePark.remove_non_ascii`).
- Ride → `ThemeParkRide(name, id, wait_time, open_flag=is_open)`.
- `ride.is_open()` ⇔ `open_flag and wait_time > 0` (closed parks report rides as open/0). See the **display decision table** in `data-model.md` for how closed / zero-wait / closed-park map to screens, filtering, and sort position.
- Up to 4 selected parks fetched per refresh.

## Fetch policy (preserved — FR-007)
- **Cadence**: every 300 s (`update_interval`), now driven by `ScrollKitApp.update_data()`.
- **Retries**: 3 attempts per request (`HttpClient.get(..., max_retries=3)`), with backoff.
- **Status UX (review B2)**: `adafruit_requests` is **synchronous** — it blocks the cooperative loop during each request, so the display does **not** render mid-fetch. **Pre-flush a static** "Updating <park> wait times from queue-times.com…" frame (via `show_loading()` / direct `clear→draw→show`) **before** each blocking request; it will not animate during the call. Show the "Wait Times Powered By queue-times.com" attribution.
- **Failure**: keep the previous snapshot, surface a status/error message, never crash (FR-014). Chunk multi-park fetches with `await asyncio.sleep(0)` **between** requests/retries so the display renders *between* (not during) the blocking calls.

## Request shape
- Plain HTTPS GET, JSON response via `response.json()`. No auth. Standard headers.
