# Quickstart: Running & validating the ported ThemeParkWaits

**Feature**: `001-this-project-is`

This is both the dev run guide and the acceptance walkthrough. Two targets: the desktop **simulator** (fast iteration) and real **Matrix Portal S3** hardware.

## Prerequisites
- The refactored library at `../ScrollKit Library` (sibling of this repo).
- Desktop: Python 3.11+, the library installed for simulation: `pip install -e "../ScrollKit Library[simulator]"` (or put `../ScrollKit Library/src` on `PYTHONPATH`).
- Hardware: a Matrix Portal S3 flashed with CircuitPython, with the adafruit `.mpy` bundle in `src/lib/` **and** `scrollkit/` copied into the device `/lib/`.

## Run on the desktop simulator
```bash
# from the repo root
PYTHONPATH="../ScrollKit Library/src:src" python -m src.themeparkwaits --dev
```
- A 64×32 simulator window opens.
- To estimate real device speed: prefix `SCROLLKIT_HW_SIM=1`. To feel the real crawl: `SCROLLKIT_HW_THROTTLE=1` (advisory, FR-025).

## Run on hardware
1. Copy the app to the device (`code.py`, `boot.py`, `src/`).
2. Ensure `/lib/scrollkit/` and the adafruit bundle are present.
3. Provide `secrets.py` (or use first-boot AP onboarding).
4. Reset the board; it boots `code.py` → `src/themeparkwaits` → the `ScrollKitApp` subclass.

## Acceptance walkthrough (maps to spec scenarios)
1. **Boot/parity (Scenario 1)** — power on with ≥1 selected park → splash (reveal) → WiFi connect → wait-times fetched → ride cycle shows, no missing features.
2. **Open ride (Scenario 2)** — a ride shows scrolling name + large centered number in configured colors/brightness.
3. **Closed (Scenario 3)** — a closed ride shows "Closed"; a closed park shows "<Park> is closed".
4. **Config (Scenario 4)** — open `http://<domain_name>.local/`, change park/brightness/sort/group/skip/scroll/colors/vacation → saved, reflected next cycle.
5. **Onboarding (Scenario 5)** — wipe credentials → device starts AP + captive portal; entering WiFi connects and reboots.
6. **OTA (Scenario 6)** — publish a newer release to the public `releases` branch with a `manifest.json` → `OTAClient.for_github` downloads & installs on reboot with "Installing… do not unplug".
7. **Library-only imports (Scenario 7)** — `grep -rn "from scrollkit" src/` shows subsystems on the library; `grep -rn "import" src/` shows no references to deleted app subsystems or removed legacy library symbols. App imports run on both targets.
8. **Efficiency (Scenario 8)** — after Phase 2, display loop reuses labels, no per-frame allocation, `bit_depth=4`; smoothness/free-RAM ≥ Phase-1 port (no numeric gate, FR-024).

## Automated checks (desktop)
```bash
pytest tests/                     # domain: models, sort/filter/group, vacation math (mocked HttpClient)
python -c "from scrollkit.dev import run_headless, validate, capabilities"   # library dev harness
# run_headless(app, frames=120, screenshot='out.png'); validate(app); capabilities()
```

## Hardware acceptance checklist — REQUIRED before any OTA release (review B4)
The desktop simulator cannot exercise the app's most fragile, device-only behaviors, and regressions ship to fielded boxes via OTA. Before publishing a release, run on a real Matrix Portal S3 and check each:
- [ ] **Fresh device / no credentials** → AP + captive portal appears; entering WiFi persists creds and reboots into normal run.
- [ ] **Wrong / unavailable WiFi** → device shows status, retries, and continues degraded (never crashes).
- [ ] **Station connect + NTP clock** set.
- [ ] **Config page reachable** at `http://<domain_name>.local/` **and** by raw IP (mDNS + web-server coexist).
- [ ] **Settings POST** rebuilds the display **without** a network fetch.
- [ ] **Multi-park refresh** (up to 4) over synchronous HTTP; loading frame pre-flushes; display resumes between fetches.
- [ ] **OTA success path** (publish newer `manifest.json` → download → apply → reboot into new version).
- [ ] **OTA failure/restore path** (corrupt/failed update → backup-restore yields a bootable device; creds + settings intact).
- [ ] **Coexistence** — display + data + web processes all run together.
- [ ] **Memory** — record free heap/FPS at boot, after fetch, with web active; **confirm the data and web processes actually spawn** (if memory-gated off, parity fails → compile `scrollkit` to `.mpy`, R4/S7).
- [ ] **Decision table** — closed ride, closed park, and open-with-0-wait ride each render + sort correctly (data-model.md).

## Definition of done
- **Milestone A (port)**: all acceptance scenarios pass on simulator **and** the hardware checklist passes; only `scrollkit.*` + domain code imported; legacy modules deleted per-subsystem (no half-migrated state).
- **Milestone B (optimize)**: efficiency rules applied; hardware checklist re-run; no regression.
- **Milestone C (cleanup audit)**: grep sweep finds no remaining unimported legacy module; app still runs.
