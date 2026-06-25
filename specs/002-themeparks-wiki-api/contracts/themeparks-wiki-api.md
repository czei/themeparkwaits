# Contract — themeparks.wiki API consumption

The external data API the app consumes. Base URL: `https://api.themeparks.wiki/v1`.
**No authentication.** All requests are anonymous GETs over HTTPS. Verified against
the live API + OpenAPI spec (`https://api.themeparks.wiki/docs/v1.yaml`) on
2026-06-24.

## 1. Catalog — `GET /v1/destinations`

Called once at boot (replaces `parks.json`). ~38 KB.

Response:
```json
{
  "destinations": [
    {
      "id": "e957da41-3552-4cf6-b636-5babc5cbc4e5",
      "name": "Walt Disney World® Resort",
      "slug": "waltdisneyworldresort",
      "externalId": "...",
      "parks": [
        { "id": "75ea578a-adc8-4116-a54d-dccb60765ef9", "name": "Magic Kingdom Park" }
      ]
    }
  ]
}
```
App use: flatten `destinations[].parks[]` → park list `{id, name}` (ASCII-strip
name), sort alphabetically by name. Ignore `slug` / `externalId` / lat-long
(absent). 106 destinations / 139 parks.

## 2. Live data — `GET /v1/entity/{parkId}/live`

Called per selected park on each refresh (replaces `parks/{id}/queue_times.json`).
**~90 KB per park.** `cache-control: public, max-age=60`.

Response (trimmed):
```json
{
  "id": "75ea578a-...",
  "name": "Magic Kingdom Park",
  "entityType": "PARK",
  "timezone": "America/New_York",
  "liveData": [
    {
      "id": "2551a77d-...",
      "name": "Haunted Mansion",
      "entityType": "ATTRACTION",
      "status": "OPERATING",
      "queue": { "STANDBY": { "waitTime": 15 } }
    }
  ]
}
```

Field paths the app reads:
| Need | Path | Notes |
|---|---|---|
| ride list | `liveData[]` where `entityType == "ATTRACTION"` | skip SHOW/RESTAURANT/HOTEL/PARK |
| ride name | `liveData[].name` | ASCII-strip |
| ride id | `liveData[].id` | uuid str |
| operating? | `liveData[].status == "OPERATING"` | else closed |
| standby wait | `liveData[].queue.STANDBY.waitTime` | `int(w) if w is not None else 0` — `queue`, `STANDBY`, or `waitTime` may be absent **or present-but-null** |

Enums:
- `entityType`: `DESTINATION | PARK | ATTRACTION | RESTAURANT | HOTEL | SHOW`
- `status` (`LiveStatusType`): `OPERATING | DOWN | CLOSED | REFURBISHMENT`
- `queue` keys (only `STANDBY` is used): `STANDBY.waitTime`, `SINGLE_RIDER.waitTime`,
  `RETURN_TIME`, `PAID_RETURN_TIME`, `BOARDING_GROUP`, `PAID_STANDBY`

## 3. Fetch behavior contract

- **Sequential** per-park fetch (no `asyncio.gather` of 4 at once); parse each
  response to compact rides, release the raw payload, `gc.collect()` before the next
  park (bounds peak RAM — see plan D8 / R1).
- Pre-flush a loading frame before each blocking GET (HTTP is synchronous).
- **Retries / failure**: keep the existing bounded-retry + empty-fallback pattern.
  On a park's fetch/parse failure, retain that park's last-known rides; never crash
  (FR-016). A malformed/empty `liveData` → that park has no rides → closed-park
  handling.
- **Defensive parsing**: use `dict.get`; ignore unknown `entityType`/`status`/queue
  keys (unknown status ≠ OPERATING ⇒ treated closed — R4).

## 4. Prohibited (FR-003)
No request to, URL for, or attribution of queue-times.com. Enforced by a grep gate
over `src/` for `queue-times` / `queue_times` / `parks.json`.
