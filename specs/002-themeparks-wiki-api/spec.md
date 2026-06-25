# Feature Specification: Source Theme-Park Wait Times from themeparks.wiki

**Feature Branch**: `002-themeparks-wiki-api`

**Created**: 2026-06-24

**Status**: Draft

**Input**: User description: "Convert this app to use https://www.themeparks.wiki/api for the source of the theme park wait times, and everything else. Do not use queue-times.com for anything."

## Overview

ThemeParkWaits currently sources every piece of theme-park data — the catalog of
parks the user can choose from, and the live ride wait times shown on the LED
board — from queue-times.com. This feature replaces that data source entirely
with the **themeparks.wiki** API. After this change, **no part of the app reads
from, links to, or credits queue-times.com**. Everything the board does today —
multi-park display, sorting, filtering, grouping, the closed-ride treatment, the
vacation countdown, and the web configuration UI — must continue to work, but
backed by themeparks.wiki data.

This is a data-source re-platforming, not a feature change: the user-visible
behavior of the board should be unchanged except for (a) the catalog of parks now
reflecting themeparks.wiki's coverage and (b) the on-screen attribution now
crediting themeparks.wiki instead of queue-times.com.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Live wait times come from themeparks.wiki (Priority: P1)

A device that already has one or more parks configured shows live ride wait times
on the LED board, with every wait time, open/closed status, and ride name sourced
from themeparks.wiki. The board looks and behaves exactly as it does today — the
ride name scrolls, the wait number is shown at 2× scale, and closed rides show
"Closed" — but the numbers now come from themeparks.wiki.

**Why this priority**: This is the core purpose of the device and the whole point
of the change. If live times don't render correctly from the new source, nothing
else matters. It is the smallest slice that delivers the feature's value.

**Independent Test**: Configure the device with a known park, let it run a refresh
cycle, and confirm the displayed wait times match what themeparks.wiki reports for
that park at that moment — and that no request is made to queue-times.com.

**Acceptance Scenarios**:

1. **Given** a device with a single open park selected, **When** a refresh cycle
   runs, **Then** the board cycles through that park's rides showing each ride's
   name and its current standby wait time from themeparks.wiki.
2. **Given** a ride that themeparks.wiki reports as not operating, **When** that
   ride comes up in the cycle, **Then** the board shows the "Closed" treatment
   instead of a wait number.
3. **Given** a park that themeparks.wiki reports as having no operating rides,
   **When** the cycle reaches that park, **Then** the board shows the park-closed
   message, exactly as it does today.
4. **Given** the device is running, **When** any data fetch occurs, **Then** no
   network request targets queue-times.com.

---

### User Story 2 - Choose parks from the themeparks.wiki catalog (Priority: P2)

A user opens the device's web configuration page, browses the themeparks.wiki
catalog and selects up to four parks, saves, and the board begins showing those
parks. The selection persists across reboots.

**Why this priority**: Without the ability to pick parks from the new catalog,
the device can only ever show whatever was pre-configured. Park selection is how
users make the device theirs. It depends on P1's data layer but is independently
demonstrable.

**Independent Test**: From a clean configuration, open the web UI, pick a park from
the catalog (and up to three more), save, and confirm the board then displays those
parks' wait times on the next cycle.

**Acceptance Scenarios**:

1. **Given** the configuration web page is open, **When** the user opens the park
   selector, **Then** the themeparks.wiki catalog of parks is listed for selection
   by name.
2. **Given** the user has selected up to four parks, **When** they save, **Then**
   the selections persist and the board shows those parks on the next refresh.
3. **Given** the user attempts to select more than four parks, **When** they save,
   **Then** the existing four-park limit is enforced exactly as today.

---

### User Story 3 - All existing board behaviors are preserved (Priority: P3)

Every option the board supports today continues to work against themeparks.wiki
data: alphabetical / longest-wait / shortest-wait sorting, skip-closed and
skip-meet filters, group-by-park vs. combined view, multiple parks (up to four),
the vacation countdown, and a source attribution message in the cycle.

**Why this priority**: These are the differentiating features users already rely
on. A data-source swap that silently drops or breaks any of them would be a
regression. They build on P1 and P2.

**Independent Test**: With multiple parks configured, toggle each setting in turn
(sort mode, skip-closed, skip-meet, group-by-park) and confirm the board's
ordering and contents change exactly as they did with the old source; confirm the
vacation countdown and the attribution message still appear.

**Acceptance Scenarios**:

1. **Given** longest-wait sort is selected, **When** the cycle runs, **Then**
   rides are ordered by descending standby wait, with closed rides weighted last,
   identical to today's behavior.
2. **Given** skip-closed is enabled, **When** the cycle runs, **Then** rides that
   are not operating are omitted.
3. **Given** skip-meet is enabled, **When** the cycle runs, **Then** meet-and-greet
   entries are omitted.
4. **Given** group-by-park is enabled with multiple parks, **When** the cycle runs,
   **Then** each park's rides are shown under that park's heading.
5. **Given** a vacation date is set, **When** the cycle runs, **Then** the
   countdown message appears as it does today.
6. **Given** any park is displayed, **When** the cycle completes, **Then** an
   attribution message crediting themeparks.wiki appears (and never
   queue-times.com).

---

### Edge Cases

- **Existing devices upgrading**: A device already in the field has saved park
  selections expressed as queue-times.com park identifiers, which are not valid
  themeparks.wiki identifiers. **Decision:** on the first run after the update the
  app clears any previously-saved park selections and shows the normal "choose a
  park" prompt; the user re-selects from the themeparks.wiki catalog. The board
  must not crash or hang during this transition.
- **Non-operating ride states**: themeparks.wiki reports `OPERATING`, `DOWN`,
  `CLOSED`, and `REFURBISHMENT`. **Decision:** every non-`OPERATING` state is shown
  with the existing "Closed" treatment.
- **Non-attraction entities**: themeparks.wiki catalogs shows, restaurants, hotels,
  and the park itself alongside rides. **Decision:** the board displays only
  `ATTRACTION` entities; shows, restaurants, and hotels are excluded. The skip-meet
  filter continues to remove meet-and-greet attractions identified by the word
  "Meet" in the name.
- **Rides without a standby wait**: Some operating attractions report only a
  virtual-queue / boarding-group / paid-return time, or no queue at all (e.g.
  splash pads, walk-through experiences). **Decision:** an operating attraction
  with no standby wait is shown as an open ride with a zero/blank number,
  consistent with today's handling of open rides with a zero wait.
- **Source unreachable or partial failure**: When themeparks.wiki is unreachable,
  or some of several selected parks fail to fetch, the device must degrade exactly
  as it does today — retry, then keep showing the last good data / an informational
  message, never a crash or indefinite hang.
- **Empty or malformed responses**: A park that returns no rides, or a malformed
  payload, must be handled without crashing (empty fallback), as today.
- **Non-ASCII names**: Park and ride names containing non-ASCII characters must
  still be rendered cleanly (stripped to displayable characters) as today.
- **Catalog size on device**: The themeparks.wiki catalog is large; fetching and
  holding it for the selection UI must stay within the device's memory limits and
  not regress boot or refresh performance.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST source the catalog of selectable parks exclusively
  from themeparks.wiki.
- **FR-002**: The system MUST source all live ride data — ride name, current
  standby wait time, and operating status — exclusively from themeparks.wiki.
- **FR-003**: The system MUST NOT issue any network request to, link to, or read
  any data from queue-times.com, anywhere in the app.
- **FR-004**: The on-screen attribution message MUST credit themeparks.wiki (e.g.
  "Wait times for {parks} provided by ThemeParks.wiki") and MUST NOT mention
  queue-times.com. No specific wording or link is mandated by themeparks.wiki (the
  backend is MIT-licensed and the API is free); crediting the source preserves the
  app's existing attribution behavior.
- **FR-005**: Users MUST be able to browse the themeparks.wiki park catalog (listed
  by name) and select up to four parks via the existing web configuration UI, with
  selections persisted across reboots.
- **FR-005a**: Where two parks share the same name (e.g. "Disneyland Park" in Paris
  and Anaheim), the selector MUST disambiguate them (e.g. by appending the
  destination/resort name) so the user can tell which park they are choosing.
- **FR-006**: The system MUST preserve the existing four-park maximum selection
  limit.
- **FR-007**: The system MUST preserve all existing sort modes (alphabetical,
  longest wait, shortest wait), including weighting closed rides as zero wait for
  the wait-based sorts.
- **FR-008**: The system MUST preserve the skip-closed filter, omitting rides that
  are not operating (or are operating with no wait, per the existing open-with-wait
  rule).
- **FR-009**: The system MUST preserve the skip-meet filter, omitting
  meet-and-greet entries.
- **FR-010**: The system MUST preserve group-by-park and combined display modes
  for multiple parks.
- **FR-011**: The system MUST preserve the per-ride display treatment: scrolling
  ride name with the wait number at 2× scale for operating rides, and the "Closed"
  treatment for non-operating rides.
- **FR-012**: The system MUST preserve the park-level closed handling, showing the
  park-closed message when a selected park has no operating rides.
- **FR-013**: The system MUST preserve the vacation countdown feature unchanged
  (it is independent of the data source).
- **FR-014**: The system MUST map themeparks.wiki operating states onto the
  board's open/closed model such that the existing open vs. "Closed" display logic
  continues to behave correctly. (See edge cases for non-operating-state handling.)
- **FR-015**: The system MUST continue to strip non-ASCII characters from park and
  ride names for display.
- **FR-016**: The system MUST preserve the existing resilience behavior — bounded
  retries on fetch failure, graceful fallback to an empty/last-known state, and no
  crash or indefinite hang — when themeparks.wiki is slow, unreachable, returns
  empty/malformed data, or when only some of multiple selected parks succeed.
- **FR-017**: The system MUST continue to refresh live data on the existing
  periodic cadence without regressing update latency or display smoothness.
- **FR-018**: The system MUST operate against themeparks.wiki without any API key
  or credential (confirmed: the API requires no authentication). Live data is
  server-cached for ~60 seconds with no documented hard rate limit; the existing
  ~5-minute refresh cadence stays well within fair use.
- **FR-019**: On the first run after updating an existing device, the system MUST
  clear any previously-saved (queue-times) park selections and prompt the user to
  re-select parks from the themeparks.wiki catalog, without crashing or hanging.
- **FR-020**: The system MUST display only ride/attraction entities
  (`entityType == ATTRACTION`) on the board; shows, restaurants, hotels, and the
  park entity itself are excluded.
- **FR-021**: The system MUST handle themeparks.wiki's larger per-park live payload
  (~90 KB per park, ~18× the old source, ~370 KB across four parks) within the
  device's memory limits — e.g. by discarding non-attraction entities during
  parsing — without regressing refresh latency or display smoothness.

### Key Entities *(include if feature involves data)*

- **Destination / Resort**: A themeparks.wiki grouping of one or more parks (e.g. a
  resort containing several parks). New concept introduced by the source; relevant
  to how the catalog is browsed and how parks are addressed.
- **Park**: A selectable venue with a display name, a themeparks.wiki identifier,
  an optional geographic location, and a set of child ride entities. Up to four are
  selected at a time.
- **Ride / Attraction**: A displayable entity with a name, a themeparks.wiki
  identifier, an entity type, an operating status, and a current standby wait time
  in minutes. The unit shown on the board.
- **Selected-Parks Configuration**: The persisted set of up to four chosen park
  identifiers (and any cached display names), stored in device settings.
- **Attribution**: The required source credit shown in the display cycle — now
  themeparks.wiki.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of park-catalog and live wait-time data displayed by the device
  originates from themeparks.wiki, and zero network requests reach queue-times.com
  (verifiable by traffic inspection and a code search finding no queue-times.com
  references).
- **SC-002**: Every board feature available before the change — up-to-four parks,
  the three sort modes, skip-closed, skip-meet, group-by-park, the closed-ride and
  closed-park treatments, and the vacation countdown — produces equivalent results
  with the new source (no regression).
- **SC-003**: A user can browse the new catalog and select their park(s) via the
  web configuration UI in under two minutes.
- **SC-004**: Live wait times refresh on the same periodic cadence as before with
  no regression in refresh duration or display smoothness on the device.
- **SC-005**: An attribution crediting themeparks.wiki appears in every display
  cycle that shows park data, and the string "queue-times" appears nowhere in the
  shipped app or its output.
- **SC-006**: An existing in-field device, after updating, clears its old
  selections and clearly prompts the user to re-select parks from the new catalog —
  and in no case crashes, hangs, or shows a permanently blank board.

## Assumptions

- themeparks.wiki provides, without authentication (confirmed — no API key), both a
  browsable catalog of parks (`/v1/destinations`) and per-park live data
  (`/v1/entity/{id}/live`) including ride names, operating status, and standby wait
  times sufficient to reproduce today's board behavior.
- Existing devices' saved park selections are cleared on upgrade and the user
  re-selects from the themeparks.wiki catalog (no automatic name-based migration).
- Standby wait time is the wait value shown on the board (single-rider, virtual
  queue, and paid-return times are out of scope for this feature unless a later
  clarification adds them).
- The device's existing network, settings, OTA, and display subsystems
  (ScrollKit-based) are reused unchanged; only the theme-park data client, the
  domain models that parse it, the catalog/selection content of the web UI, and the
  attribution text change.
- The vacation countdown, brightness/color/scroll-speed settings, and the reveal
  splash are unaffected by the data source and remain as-is.
- Existing per-park parallel fetching, retry, and empty-fallback patterns remain
  the resilience model; only the endpoints and payload shapes change.
- "Everything else" in the request refers to all theme-park data the app uses
  (the park catalog, locations, and live ride data) — i.e. the complete removal of
  queue-times.com — not to data unrelated to theme parks.
