# Feature Specification: Port ThemeParkWaits App to the Refactored ScrollKit Library

**Feature Branch**: `001-this-project-is`
**Created**: 2026-06-20
**Status**: Draft
**Input**: User description: "This project is an app that gets theme park wait times and displays the information on a scrolling LED display. The current source code was written for a previous version of ../ScrollKit Library. That library has been heavily refactored to work better as a library. This app needs to be refactored to match. Some ways of doing things may have been merged or replaced. The library also has information on which calls are more efficient than others. Try to use the more efficient techniques even if the code becomes longer. Best practice would be to first port the existing code, then do a separate optimization pass."

---

## Overview

ThemeParkWaits is a CircuitPython application that runs on a Matrix Portal S3 powering a 64×32 RGB LED matrix ("ThemeParkWaits LED box"). It fetches live theme-park ride wait times from an online service and presents them as scrolling text and large numeric readouts, and it lets the owner configure the device through WiFi setup and a web page.

The current code was written against an **older version** of the ScrollKit display library. That library has since been heavily refactored into a clean, reusable package: capabilities have been consolidated, some classes and call paths have been **renamed, merged, or removed**, and the library now documents which calls are cheaper to run on the memory- and CPU-constrained device.

This feature re-platforms the app onto the **current** ScrollKit library so that, from the device owner's point of view, the product keeps doing everything it does today, while the codebase tracks the supported library and runs more efficiently. The work is deliberately staged: **first a faithful port to restore feature parity on the new library, then a separate optimization pass** that adopts the library's documented efficient techniques even where that makes the code longer.

Beyond compatibility, this app is intended as a **flagship demonstration of the ScrollKit library** — a sophisticated, real-world application that exercises the library's full feature set. **Every subsystem the library can provide MUST run on the library** (graphics/display, content/queue, effects/animations, WiFi and HTTP networking, settings persistence, OTA updates, and the configuration web server). Code remains unique to this app **only** where the library genuinely lacks the capability — i.e., the theme-park domain logic, the queue-times.com data model, and product-specific screen layouts. The app has historically had **no memory or performance problems**, so efficiency work is about idiomatic, recommended library usage rather than meeting a hard performance budget. Dead and superseded code is removed as part of the work.

## Clarifications

### Session 2026-06-20
- **Q: Which subsystems switch to the library vs. stay app-owned?** → **A: ALL of them.** Every subsystem the library provides (display/graphics, content/queue, effects/animations, WiFi + HTTP networking, settings persistence, OTA, and the config web server) MUST use the library. App-unique code is allowed only where the library lacks the capability (theme-park domain logic, the queue-times.com data model, product-specific layouts). The project's purpose is to be a sophisticated showcase of the library's full feature set.
- **Q: What is the performance/free-RAM acceptance target?** → **A: No hard numeric gate.** Past versions had no memory or performance issues. The optimization pass applies the library's documented efficient techniques and must not regress, but there is no required FPS/RAM threshold to hit.
- **Q: Is removing now-dead duplicate modules in scope?** → **A: Yes.** Clean up dead code (e.g., `*.old.py`, `*_original.py`, parallel display/web-server implementations the library now supplies).
- **Q: Must on-screen motion match the old app pixel-for-pixel?** → **A: No.** Because the app is a library showcase, the port should adopt the library's native scrolling/animation idioms as long as the same information is conveyed.
- **Q: Is the library's hardware-timing simulation a required acceptance gate?** → **A: Advisory.** Given no historical performance concerns, it is a recommended check, not a blocking gate.

## User Scenarios & Testing *(mandatory)*

### Primary User Story
A theme-park visitor owns a ThemeParkWaits LED box. After this change is delivered (over the air, like every release), the device powers on and behaves exactly as it did before: it shows the startup branding, connects to WiFi, retrieves current wait times for the parks the owner selected, and continuously displays each ride's name and current wait — closed rides and closed parks are handled the same way, the same sort and filter options apply, and the same web page is reachable for configuration. The owner notices no loss of features. Internally, the app is now built on the supported ScrollKit library and uses the library's more efficient display techniques, so the display stays smooth and the device stays within its memory budget.

### Acceptance Scenarios

1. **Given** a configured device with one or more selected parks, **When** it boots after the update, **Then** it shows the startup splash, connects to WiFi, fetches wait times, and cycles through ride displays with no loss of any feature that existed before the port.

2. **Given** a ride that is operating, **When** its turn comes up in the display cycle, **Then** the ride name scrolls and the current wait time is shown as a large centered number, using the owner's configured colors and brightness.

3. **Given** a ride that is closed (or a park that is closed), **When** it is displayed, **Then** the device shows the same "Closed" / "[Park] is closed" treatment it did before the port.

4. **Given** the owner opens the device's configuration web page, **When** they change a setting (park selection, brightness, sort order, group-by-park, skip-closed, skip-meet, scroll speed, colors, or vacation date), **Then** the setting is saved and the display reflects it on the next cycle — identical to pre-port behavior.

5. **Given** a device with no saved WiFi credentials, **When** it boots, **Then** it starts its setup access point with a captive portal for entering WiFi details, exactly as before.

6. **Given** a newer release is published, **When** the device performs its over-the-air update check, **Then** it downloads and installs the update on reboot, with the same progress messaging as before.

7. **Given** the app source after Phase 1 (port), **When** a developer runs it on the desktop simulator and on hardware, **Then** every previously supported behavior works and the app imports only **current** ScrollKit public API — no removed or renamed legacy library symbols remain.

8. **Given** the app source after Phase 2 (optimization), **When** the display loop runs, **Then** it follows the library's documented efficiency rules (reuse text labels rather than rebuilding them per frame, no per-frame object allocation, bulk/C draw calls instead of per-pixel Python loops, the device's lower color-depth refresh setting, and graceful degradation under low memory), and the measured display performance and free-memory headroom are no worse than — and ideally better than — the Phase 1 port.

### Edge Cases

- **Scrolling direction / motion idiom.** The current app scrolls some text left-to-right and pauses at the edges; the refactored library's scrolling content has its own scroll-direction and auto-complete behavior. Resolved (see Clarifications): the port adopts the library's native scrolling/animation idioms as long as the same information is conveyed — pixel-for-pixel reproduction of the old motion is not required.
- **Closed mid-day rides.** A ride may report "operating" with a 0-minute wait, or "closed." The displayed result and its sort position must match current behavior.
- **No parks selected / empty data.** The device must still show its "configure at http://[hostname].local" guidance and not crash.
- **WiFi unavailable or data fetch fails.** The device must degrade gracefully (retry, show a status/error message, keep running) exactly as it does today; failures must never crash the device.
- **Low memory on the device.** Under tight RAM, the library may skip the data-refresh and web-config functions while the display keeps running (its graceful-degradation model). Resolved (see Clarifications): the app has historically had no memory problems, so this safety behavior is acceptable and is not expected to trigger in normal operation.
- **Library capability gaps.** If a behavior the app relies on was removed in the refactor with no direct replacement, the port must reproduce that behavior on top of the new library rather than silently drop it.

## Requirements *(mandatory)*

### Functional Requirements — Feature Parity (the port must preserve all of these)

- **FR-001**: The device MUST display a startup splash/branding sequence equivalent to the current one, including the existing reveal-style intro.
- **FR-002**: The device MUST display each selected park's rides as a scrolling ride name plus a large, centered current-wait-time number, using the owner's configured colors and brightness.
- **FR-003**: The device MUST display closed rides and closed parks using the same treatment as today (e.g., a "Closed" indicator and a "[Park] is closed" message).
- **FR-004**: The device MUST support the same ride ordering options — alphabetical, longest-wait-first, shortest-wait-first — and the same grouping behavior (per-park headers vs. all parks combined).
- **FR-005**: The device MUST support the same content filters — hide closed rides and hide meet-&-greet attractions — controlled by owner settings.
- **FR-006**: The device MUST support selecting and displaying multiple parks (up to the current limit of four) simultaneously.
- **FR-007**: The device MUST retrieve live wait-time data from the same external source the app uses today and on the same default refresh cadence (5 minutes), with the same retry behavior, the same "updating…" status messaging, and the same data-source attribution message.
- **FR-008**: The device MUST display the vacation countdown feature (days-until messages, plus the special "tomorrow" and "today" messages) when a vacation date is configured.
- **FR-009**: The device MUST provide the same WiFi onboarding: when no credentials are stored it starts a setup access point with a captive portal for entering WiFi details, and it persists credentials for future boots.
- **FR-010**: The device MUST host the same configuration web page, reachable at the configured mDNS hostname (and by IP), exposing the same settings: park selection, brightness, sort mode, group-by-park, skip-closed, skip-meet, scroll speed, text colors, and vacation date.
- **FR-011**: Settings MUST be persisted across reboots and MUST tolerate missing keys by applying defaults, exactly as today (no crash on absent or legacy settings).
- **FR-012**: The device MUST retain its over-the-air update capability: check for a newer published release, download it, and install it on reboot with the existing "installing / do not unplug" progress messaging and version handling.
- **FR-013**: The application MUST continue to run on both targets it supports today — real Matrix Portal S3 hardware and the desktop development simulator — selecting the correct target automatically.
- **FR-014**: The application MUST preserve its current resilience guarantees: recoverable errors are logged and the device keeps running; no single failure (network, data, web, OTA) crashes the device.

### Functional Requirements — Library Adoption

- **FR-015**: The application MUST be built against the **current** public API of the refactored ScrollKit library (its app framework, unified display, content/queue model, effects, networking, configuration, OTA, and utility packages) instead of the app's older vendored or hand-rolled equivalents. As the library's flagship demonstration, the app MUST exercise the library's feature set idiomatically rather than adopting it minimally.
- **FR-016**: The application MUST NOT reference any library class, function, or call path that was **renamed, merged, or removed** in the refactor; each such usage MUST be mapped to its current replacement.
- **FR-017**: **ALL** app subsystems that the library provides MUST be built on the library's equivalents — graphics/display, the content/message queue, effects/animations, WiFi management, the HTTP client, settings/configuration persistence, OTA updates, and the configuration web server. The app MUST NOT retain a parallel duplicate of any capability the library offers.
- **FR-017a**: App-specific code is permitted **only** for functionality the library genuinely lacks — specifically the theme-park domain logic, the queue-times.com data model and parsing, and product-specific screen layouts. Before keeping any subsystem as app code, the port MUST confirm the library has no equivalent capability.
- **FR-018**: The port MUST be verifiable as a distinct first milestone: feature parity restored on the new library, with no behavior change introduced solely for optimization.

### Functional Requirements — Efficiency (Phase 2 optimization pass)

- **FR-019**: The display loop MUST follow the library's documented "reuse, don't rebuild" rule: a text element's content is changed only when its value actually changes, and motion (e.g., scrolling) moves an existing element rather than rebuilding it each frame.
- **FR-020**: The app MUST NOT allocate new display objects every frame; display objects are created once and mutated, per the library's guidance.
- **FR-021**: Bulk/efficient draw operations MUST be used in place of per-pixel Python loops wherever the library offers them.
- **FR-022**: The app MUST use the device's lower color-depth refresh configuration that the library recommends for this hardware, unless a specific feature demonstrably requires higher depth.
- **FR-023**: Long or heavy computation MUST be chunked so it does not stall the display loop, consistent with the library's cooperative-multitasking and synchronous-fetch guidance.
- **FR-024**: There is no hard numeric performance budget (the app has historically run without memory or performance issues). The optimization pass MUST still apply the library's documented efficient techniques and MUST NOT regress display smoothness or free-memory headroom relative to the Phase 1 port.
- **FR-025**: The team SHOULD validate efficiency using the library's hardware-timing simulation before flashing to physical hardware so device-speed regressions surface earlier. This is advisory (recommended), not a required acceptance gate.

### Functional Requirements — Process & Cleanup

- **FR-026**: The work MUST be delivered in two clearly separable stages — (1) port for parity, (2) optimize — each independently reviewable, so a parity regression can be told apart from an optimization regression.
- **FR-027**: Dead-code cleanup is **in scope**. Obsolete duplicate and superseded source artifacts that the port renders dead (e.g., legacy `*.old.py` / `*_original.py` files and the parallel display/web-server implementations the library now supplies) MUST be removed so the codebase reflects a single supported path.

### Key Entities *(include if feature involves data)*

- **Park**: A theme park the owner can select (identity, name, open/closed status, location). The device tracks up to four selected parks at once.
- **Ride / Attraction**: A single attraction within a park, with a display name, a current wait time in minutes, and an operating/closed status. Meet-&-greet attractions are a filterable category.
- **Wait-Time Snapshot**: The set of current ride waits fetched from the external service per park, refreshed on a fixed cadence and used to build what is shown.
- **Display Content Item**: A unit of what appears on the matrix — a scrolling message, a static message, or a ride readout — sequenced for presentation. (The refactored library models these as content objects in a queue; the app consumes that model.)
- **Device Settings**: The owner's persisted configuration — selected parks, brightness, sort mode, grouping, filters, scroll speed, colors, hostname, and vacation date — survived across reboots.
- **Vacation**: An optional upcoming trip (park + date) that drives countdown messaging.
- **Release / Update**: A published version the device can fetch and install over the air.

## Out of Scope

- Adding new end-user features, new data sources, or new display modes beyond what the app does today (the placeholder display-mode field stays a placeholder).
- Changing the external wait-time data provider or its refresh contract.
- Redesigning the configuration web page's layout or settings set (it must match today's).
- Any change to the LED hardware or enclosure.

## Review & Acceptance Checklist
*GATE: Automated checks run during main() execution*

### Content Quality
- [ ] Focused on user value and preserved behavior, not implementation specifics
- [ ] Written so a stakeholder can confirm "nothing the device does today is lost"
- [ ] All mandatory sections completed

### Requirement Completeness
- [x] Open [NEEDS CLARIFICATION] markers resolved (see Clarifications, Session 2026-06-20)
- [x] Requirements are testable (parity behaviors are observable; efficiency rules are checkable)
- [x] Success criteria for the optimization pass are defined (apply documented techniques, no regression; no numeric gate by decision)
- [x] Scope (port-then-optimize, all-subsystems-on-library) is clearly bounded
- [x] Dependencies (the refactored ScrollKit library and its documented API/efficiency guidance) and assumptions identified

---

## Execution Status
*Updated by main() during processing*

- [x] User description parsed
- [x] Key concepts extracted (actors: device owner, maintainer; actions: port, optimize; data: parks/rides/waits/settings; constraints: feature parity, new library API, documented efficient calls, staged delivery)
- [x] Ambiguities marked
- [x] User scenarios defined
- [x] Requirements generated
- [x] Entities identified
- [x] Review checklist passed (all clarifications resolved 2026-06-20)

---
