# Research: themeparks.wiki API (feature 002)

Captured 2026-06-24 from live API probing + the OpenAPI spec
(`https://api.themeparks.wiki/docs/v1.yaml`). Feeds `/speckit.plan`.

## Base & endpoints

Base URL: `https://api.themeparks.wiki/v1`

| Endpoint | Returns | Used for |
|---|---|---|
| `GET /destinations` | `{destinations:[{id,name,slug,externalId,parks:[{id,name}]}]}` | The park catalog (selection UI). 106 destinations, **38 KB**. |
| `GET /entity/{id}` | entity metadata (name, entityType, location, timezone, parents) | Optional metadata; not needed for parity. |
| `GET /entity/{id}/children` | child entities (rides) **without** live data | Not needed — `/live` already carries names. |
| `GET /entity/{id}/live` | `{id,name,entityType,timezone,liveData:[{id,name,entityType,status,queue,...}]}` | **Live wait times** per park. |
| `GET /entity/{id}/schedule[/{year}/{month}]` | operating calendar | Not needed for parity. |

So the app needs exactly **two** endpoints: `/destinations` (catalog) and
`/entity/{parkId}/live` (wait times). This mirrors the old two-call shape
(`parks.json` + `parks/{id}/queue_times.json`).

## Identifiers

- All IDs are **UUID strings** (e.g. `75ea578a-adc8-4116-a54d-dccb60765ef9` =
  Magic Kingdom), **not integers** like queue-times. This breaks existing saved
  `selected_park_ids` (which are queue-times integers).
- Helpful: the app already persists `selected_park_names` alongside the IDs
  (`theme_park_list.store_settings`), so name-based migration is feasible.

## Enums (from OpenAPI spec)

- **entityType**: `DESTINATION, PARK, ATTRACTION, RESTAURANT, HOTEL, SHOW`
- **status** (`LiveStatusType`): `OPERATING, DOWN, CLOSED, REFURBISHMENT`
- **queue** (`LiveQueue`) keys: `STANDBY.waitTime`, `SINGLE_RIDER.waitTime`,
  `RETURN_TIME` (virtual queue), `PAID_RETURN_TIME` (Lightning Lane),
  `BOARDING_GROUP`, `PAID_STANDBY`. The board's wait number = `queue.STANDBY.waitTime`.

## Auth, caching, rate limits, license

- **No authentication / no API key.** The OpenAPI spec defines no security scheme;
  anonymous requests return 200. Matches the app's no-token model.
- **Caching**: `/live` returns `cache-control: public, max-age=60` — data is
  cached 60 s. Polling faster than once/min just re-serves cache. The app's
  ~5-minute refresh is well within bounds.
- **Rate limit**: no documented hard limit; clients may see `429` if they hammer
  the API (the official Python SDK has a `RateLimitError` w/ `retry_after`). Not a
  concern at 5-min cadence.
- **License**: backend library is **MIT** (© Jamie Holding – ThemeParks.wiki). API
  is free, sponsor-supported. **No mandatory attribution string** is documented;
  crediting/linking themeparks.wiki is the community norm. (Note: queue-times.com
  is itself listed as a *sponsor* of themeparks.wiki — irrelevant to us; our app
  will contact only themeparks.wiki.)

## Payload size — the key device risk

| Park data call | queue-times | themeparks.wiki `/live` |
|---|---|---|
| Magic Kingdom | **5.1 KB** | **92 KB** (~18×) |

`/live` returns *all* entity types (35 attractions + 19 shows + 8 restaurants +
park) with rich queue/showtime objects, and there is **no server-side filter** to
request only attractions or only standby. So the device must download + parse the
full payload. With up to 4 parks that is ~**370 KB** of JSON per refresh — the
single biggest concern for the memory-constrained Matrix Portal S3 (and the most
important thing for `/speckit.plan` to solve: incremental/streaming parse, parse-
and-discard non-attractions, PSRAM use, and not regressing refresh latency).

## Mapping to the current app

- **Catalog**: `/destinations` → flatten `destinations[].parks[]` to `{id,name}`.
  No lat/long in this payload — fine, because the app stores lat/long but never
  functionally uses it (the clock uses NTP, not park location).
- **Park open/closed**: derive from "any ATTRACTION OPERATING" (matches current
  `ThemePark.is_open`), or read the `PARK` entity's status in `liveData`.
- **Rides**: keep `liveData` items where `entityType == ATTRACTION`; map
  `status == OPERATING` → open, `STANDBY.waitTime` → wait minutes.
- **Non-ASCII**: still required — names contain smart quotes / en-dashes
  (e.g. "Disney’s Celebrate America! – …").

## Recommended resolutions for the spec's open questions

| # | Spec question | Recommendation |
|---|---|---|
| 1 | Upgrade migration (int IDs → UUID) | **Auto-migrate by matching saved `selected_park_names` to the catalog**; anything unmatched is dropped, and if none match, fall back to the existing "choose a park" prompt. No crash either way. |
| 2 | Attribution wording | No mandate found. Reuse the existing attribution line, crediting **ThemeParks.wiki** (e.g. "Wait times for {parks} provided by ThemeParks.wiki"). |
| 3 | Non-operating states (DOWN/REFURBISHMENT/CLOSED) | **Collapse all non-`OPERATING` to the existing "Closed" treatment** for parity. (A distinct "Down"/"Refurb" label is a possible later nicety.) |
| 4 | Which entity types to display | **Attractions only** (`entityType == ATTRACTION`); exclude SHOW/RESTAURANT/HOTEL/PARK. `skip_meet` continues to match "Meet" in the name. |
| 5 | Operating rides with no STANDBY (e.g. splash pads, virtual-queue-only) | Treat as an open ride with no number (same as today's open-with-0). ~2 of 31 operating MK attractions. Optionally skip empty-`queue` attractions. |

## Decisions confirmed (2026-06-24)

1. **Migration → clear and re-prompt** (user chose this over auto-migrate): on the
   first run after update, clear saved selections and have the user re-select.
2. **Attribution → credit ThemeParks.wiki** (no mandated string).
3. **Non-`OPERATING` states → "Closed"** treatment.
4. **Entity scope → attractions only** (`entityType == ATTRACTION`); no shows.
5. **Operating rides w/o standby → open with zero/blank number.**

See `spec.md` (FR-004/018/019/020/021, edge cases, SC-006) — all
`[NEEDS CLARIFICATION]` markers are now resolved.
