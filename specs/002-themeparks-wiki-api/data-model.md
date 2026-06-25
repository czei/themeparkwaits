# Phase 1 Data Model — themeparks.wiki port

Domain entities and the field/behavior mapping from queue-times.com to
themeparks.wiki. Library-owned entities (`SettingsManager`, display content) are
unchanged and not repeated here.

## Entities

### Destination (new, transient)
A themeparks.wiki grouping of one or more parks (resort). Used only while flattening
the catalog; not persisted.
- `id` (uuid str), `name` (str), `parks` (list of Park)
- Source: `/v1/destinations` → `destinations[]`.

### Park (`ThemePark`)
A selectable venue and its rides.
| Field | Type | Source | Change vs. queue-times |
|---|---|---|---|
| `id` | **str (uuid)** | `destinations[].parks[].id` | **was int** |
| `name` | str | `destinations[].parks[].name` | ASCII-stripped (unchanged) |
| `latitude` / `longitude` | — | n/a | **removed** (not provided, never used) |
| `rides` | list[Ride] | `/entity/{id}/live` → `liveData[]` | parsed from `liveData`, not `lands`/`rides` |
| `is_open` | bool | derived: any ride `open_flag` True | unchanged rule |

- `is_valid()` → `id` is a non-empty uuid string (was `id > 0`).
- `get_url()` / queue-times URL helpers → **removed** (the service owns endpoints).

### Ride (`ThemeParkRide`)
A single attraction shown on the board.
| Field | Type | Source | Notes |
|---|---|---|---|
| `name` | str | `liveData[].name` | ASCII-stripped |
| `id` | **str (uuid)** | `liveData[].id` | was int (unused downstream) |
| `wait_time` | int | `liveData[].queue.STANDBY.waitTime` | `int(w) if w is not None else 0` — STANDBY/waitTime may be absent **or null** |
| `open_flag` | bool | `liveData[].status == "OPERATING"` | non-OPERATING → False |

- `is_open()` = `open_flag and wait_time > 0` — **unchanged**; drives skip-closed
  filter + wait-based sort weight.

Only `liveData[]` items with `entityType == "ATTRACTION"` become Rides. SHOW,
RESTAURANT, HOTEL, and the PARK entity are skipped.

### Selected-Parks configuration (persisted, `settings.json`)
| Key | Type | Change |
|---|---|---|
| `selected_park_ids` | **str[] (uuid)** | was int[] |
| `selected_park_names` | str[] | unchanged (cached display names) |
| `current_park_id` | **str (uuid)** | was int (legacy back-compat field) |
| `current_park_name` | str | unchanged |

## Status → display decision table

`status` enum: `OPERATING | DOWN | CLOSED | REFURBISHMENT`.

| `status` | `open_flag` | STANDBY wait | Board shows |
|---|---|---|---|
| OPERATING | True | n (>0) | ride name + **n** (2× number) |
| OPERATING | True | 0 / absent | ride name + **0** (open-with-zero, e.g. splash pad) |
| DOWN | False | — | **"Closed"** |
| REFURBISHMENT | False | — | **"Closed"** |
| CLOSED | False | — | **"Closed"** |
| (unknown/missing) | False | — | **"Closed"** (defensive — R4) |

Filter/sort interactions (unchanged from feature 001, re-keyed onto new fields):
- **skip-closed**: drop rides where `is_open()` is False (closed, or open-with-0).
- **skip-meet**: drop rides whose `name` contains "Meet".
- **sort max_wait / min_wait**: closed rides weigh `0`.
- **closed park**: a selected park with no `open_flag` ride → "{park} is closed".

## Upgrade migration (clear-and-reprompt)

Run once in `ThemeParkList.load_settings`:
1. Read `selected_park_ids`.
2. An id is **legacy** if it is an `int`, an all-digits string, or otherwise not a
   UUID-shaped string (no hyphen). 
3. If **any** id is legacy → clear `selected_park_ids`, `selected_park_names`,
   `current_park_id`, `current_park_name` and persist.
4. Result: `selected_parks` is empty → `content_builder` emits the existing
   "Choose theme park at http://{domain}.local" prompt. No crash, no blank board
   (SC-006).

## Validation rules
- Park `id` non-empty string; rides require a `name`.
- Defensive parsing throughout (`dict.get`, ignore unknown `entityType`/`status`),
  preserving the never-crash resilience (FR-016).
- Names ASCII-stripped before display (FR-015) — payloads contain smart quotes /
  en-dashes.
