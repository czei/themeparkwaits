# Quickstart — themeparks.wiki port (feature 002)

How to run, test, and acceptance-verify the data-source swap. Assumes the feature
001 environment (ScrollKit on `sys.path`, vendored Adafruit bundle, clean desktop
env per CLAUDE.md "Gotchas").

## Run

Simulator (desktop):
```bash
PYTHONPATH="../ScrollKit Library/src:src" python -m src.themeparkwaits --dev
```
Config web UI: <http://localhost:8080> (pick parks; they now come from
themeparks.wiki).

Device-speed estimate / crawl:
```bash
SCROLLKIT_HW_SIM=1 PYTHONPATH="../ScrollKit Library/src:src" python -m src.themeparkwaits --dev
# SCROLLKIT_HW_THROTTLE=1 to feel the per-frame cost
```

## Tests

```bash
pytest tests/                 # domain + parse + migration + attribution, mocked HttpClient
```
Plus the grep gate (must print nothing):
```bash
grep -rniE 'queue-?times|parks\.json' src/ tests/ && echo "FAIL: queue-times reference found" || echo "OK: clean"
```
Visual parity (screenshots via the headless harness):
```bash
PYTHONPATH="../ScrollKit Library/src:src" python tools/sim_shot.py   # or run_headless(..., screenshot=...)
```

## Acceptance walkthrough (maps to spec scenarios)

| Spec scenario | How to verify |
|---|---|
| US1.1 open park wait times | Configure one open park (e.g. Magic Kingdom); confirm the board cycles rides with live standby numbers matching `/v1/entity/{id}/live`. |
| US1.2 closed ride | Find a ride with `status != OPERATING`; confirm "Closed" treatment, no number. |
| US1.3 closed park | Configure a park that is closed (outside hours); confirm "{park} is closed". |
| US1.4 no queue-times traffic | Run with network logging; confirm only `api.themeparks.wiki` is contacted. The grep gate confirms no source references. |
| US2.1 search catalog | Open the web UI; the park dropdowns list themeparks.wiki parks (139). |
| US2.2 select + persist | Select up to 4 parks, Save; reboot; confirm selections persist (UUIDs) and the board shows them. |
| US2.3 four-park limit | Confirm only 4 dropdowns; a 5th selection isn't possible. |
| US2 / FR-005a duplicate name | Confirm the two "Disneyland Park" entries render as "Disneyland Park — Disneyland Paris" / "… — Disneyland Resort" (distinguishable). |
| US3.1 sort longest-wait | Set sort = max_wait; confirm descending standby order, closed rides last. |
| US3.2 skip-closed | Enable skip-closed; confirm non-operating rides omitted. |
| US3.3 skip-meet | Enable skip-meet; confirm meet-and-greet entries omitted. |
| US3.4 group-by-park | Two+ parks, group-by-park on; confirm per-park headings. |
| US3.5 vacation countdown | Set a vacation date; confirm the countdown message. |
| US3.6 attribution | Confirm the cycle ends with "…provided by ThemeParks.wiki" and never queue-times.com. |
| Edge — upgrade migration | Seed `settings.json` with integer `selected_park_ids`; boot; confirm the choose-a-park prompt (no crash), then re-select works. |
| Edge — no-standby ride | A splash-pad/virtual-queue attraction that is OPERATING with no STANDBY shows as open-with-0. |

## Hardware verification (REQUIRED before release — R1)

On the Matrix Portal S3:
1. Configure 1 then 4 parks; confirm live times render.
2. **Record free heap before/after a 4-park refresh** (`gc.mem_free()`) **with the
   ~139-park catalog resident** (worst case = resident catalog + one `/live`
   transient), confirming the sequential fetch + `gc.collect()` keeps headroom and
   the **data + web processes still spawn** (memory not gated off).
3. Web UI park selection over UUIDs persists and triggers a prompt refresh.
4. Pull WiFi mid-refresh → board keeps last data, retries, never crashes.

## Done when
- pytest green; grep gate clean (no queue-times).
- All acceptance rows pass on the simulator.
- Hardware free-heap acceptable with 4 parks; no process gated off.
- No regression in display smoothness / refresh cadence.
