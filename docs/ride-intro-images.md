# Ride Intro Images — Project Guide

**Goal:** create a 64×32 LED "intro image" (a recognizable silhouette) for as many
rides as possible (US Disney, Universal, and other parks). Each plays before that
ride's wait-time screen on the Matrix Portal S3.

**Status (2026-06-29):** framework DONE + verified on hardware. **All 49 ride icons are
drawn + registered** — every filled-in representation in `docs/ride-icons.md` now maps to a
BMP (79 ride UUIDs → 49 images in `manifest.json`), sim-verified through the real
`UnifiedDisplay`. Designs are reproducible via `tools/gen_ride_designs.py`
(+ `tools/trace_ref_outline.py` for reference-traced ones, e.g. the glass slipper).
Adding more rides still needs **no code changes** — just a design + a manifest line.

---

## How it works (runtime)

1. `content_builder._add_ride()` calls `lookup_intro_image(ride.id)` for every ride.
2. `src/ui/ride_images.py` reads `src/images/rides/manifest.json` (a `uuid → filename`
   map, cached) and returns the BMP path, or `None` if the ride has no image / the file
   is missing. **Matched strictly by themeparks.wiki ride UUID** (names aren't unique
   across parks). Many UUIDs may map to ONE file (one drawing serves a ride at every park).
3. If an image is present, `RideScreenContent` (and `ClosedRideContent`) play an intro
   via the shared base `_ScrollingNameContent`:
   **HOLD** (~1.6 s, image still) → **FADE** (~1.3 s, image fades while the name scrolls
   in from the right) → **NORMAL** (image detached; the existing wait-number reveal runs).
   Rides without an image render exactly as before. Fails safe to the normal screen if the
   image can't load.

Tuning constants: `_INTRO_HOLD_FRAMES = 32`, `_INTRO_FADE_FRAMES = 26` in
`src/ui/ride_screen_content.py` (frame-counted at ~20 fps).

---

## Files

| Path | Role |
|------|------|
| `src/ui/ride_images.py` | `lookup_intro_image(ride_id) -> path|None` (mirrors `ride_types.py`) |
| `src/ui/ride_screen_content.py` | intro state machine in `_ScrollingNameContent` (`_intro_step`/`_load_intro`/`_fade_intro`/`_detach_intro`) |
| `src/ui/content_builder.py` | `_add_ride()` wires the lookup into all ride content |
| `src/images/rides/manifest.json` | `{"version":1,"rides":{"<uuid>":"<file>.bmp"}}` |
| `src/images/rides/*.bmp` | the images (indexed 64×32, sky = palette index 0) |
| `designs/*.txt` | editable ASCII-art source for each image |
| `tools/make_ride_image.py` | ASCII/PNG → device BMP + preview + manifest line |
| `tools/list_park_rides.py` | list a park's `uuid<TAB>name` (and `--list-parks`) |
| `tools/intro_shots.py` | sim e2e: render the real intro flow to a GIF + assert phases |
| `tools/dev_serial_capture.py` | capture the device serial console (reconnects across resets) |
| `tools/dev_repl_exec.py` | run a diagnostic code block on-device via the raw REPL |
| `tests/domain/test_ride_images.py` | unit tests for the loader |

---

## Add a new ride (the repeatable loop)

```bash
# 1. Find the ride's UUID(s) (network). Park UUIDs are in the table below.
python tools/list_park_rides.py --park 75ea578a-adc8-4116-a54d-dccb60765ef9 --grep "haunted"
# (all parks: python tools/list_park_rides.py --list-parks)

# 2. Draw designs/<name>.txt — 32 lines × 64 chars, one char per LED:
#      ' ' = sky (MUST be the top-left / row 0 so palette index 0 = sky)
#      '#' = white   ':' = blue rib/shade   '+' = dim star   (full map in make_ride_image.PALETTE)
#    Keep it <= 16 colors. Iterate by eye with step 3's preview.

# 3. Convert -> indexed BMP + preview PNG + prints the manifest line(s):
python tools/make_ride_image.py designs/<name>.txt --name <name> \
    --uuid <uuid>[,<uuid2>,...]

# 4. Paste the printed line(s) into src/images/rides/manifest.json under "rides".

# 5. Verify in the simulator (edit the UUID in the script, or generalize it):
PYTHONPATH="../ScrollKit Library/src:." SDL_VIDEODRIVER=dummy python3 tools/intro_shots.py /tmp/x

# 6. Commit, then deploy to the device (see below) and watch.
```

**Image format spec:** 64×32, indexed BMP (Pillow `P` mode), ≤16 colors (panel is
`bit_depth=4`). Palette **index 0 = sky**, and the **top-left pixel must be sky** — the
device reads the BMP's indexed palette (sky=0) and the simulator rebuilds the palette by
top-left-first scan, so both make `make_transparent(0)` mean "sky".

---

## US Disney park UUIDs (for `--park`)

| Park | UUID |
|------|------|
| Magic Kingdom | `75ea578a-adc8-4116-a54d-dccb60765ef9` |
| EPCOT | `47f90d2c-e191-4239-a466-5892ef59a88b` |
| Hollywood Studios | `288747d1-8b4f-4a64-867e-ea7c9b27bad8` |
| Animal Kingdom | `1c84a229-8862-4648-9c71-378ddd2c7693` |
| Disneyland Park | `7340550b-c14d-4def-80bb-acdb51d49a66` |
| Disney California Adventure | `832fcd51-ea19-4e77-85c7-75d5843b127c` |

**Scope:** theme parks only — the water parks (Blizzard Beach, Typhoon Lagoon,
Volcano Bay) are intentionally excluded; no intro images for them.

## Universal park UUIDs (for `--park`)

| Park | UUID |
|------|------|
| Universal Studios Florida | `eb3f4560-2383-4a36-9152-6b3e5ed6bc57` |
| Universal Islands of Adventure | `267615cc-8943-4c2a-ae2c-5da728ca591f` |
| Universal Epic Universe | `12dbb85b-265f-44e6-bccf-f1faa17211fc` |
| Universal Studios Hollywood | `bc4005c5-8c7e-41d7-b349-cdddf1796427` |
| Universal Studios Japan | `47f61fac-7586-41ac-ae80-61c9257cf33e` |
| Universal Studios Singapore | `f95d7f76-2024-4510-b799-26e122d0e448` |
| Universal Studios Beijing | `68e1d8f0-ed42-4351-af25-160421e37ce0` |

Universal added 2026-07-01: **8 new icons** (`minion`, `dinosaur`, `transformers`,
`mummy`, `panda`, `donut`, `shark`, `yoshi`) + 124 UUID→file mappings across the 7
non-water parks (most reuse existing silhouettes). Shows/interactive/kiddie
attractions with no good silhouette are left unmapped (they render the normal screen).

Shipped so far: **Space Mountain** → `space_mountain.bmp`
(MK `b2260923-9315-40fd-9c6b-44dd811dbe64`, DLR `9167db1d-e5e7-46da-a07f-ae30a87bc4c4`).
Good next candidates (same drawing can serve multiple parks): Big Thunder Mountain,
Haunted Mansion, Tower of Terror, Tron/Tron-style, Tree of Life, Spaceship Earth.

---

## Hardware / device

- **Board:** Adafruit MatrixPortal S3, **CircuitPython 10.2.1**. Firmware UF2 +
  esptool bins are in `../MatrixPortalBoot/`. The 10.x Adafruit `.mpy` bundle is in
  `../adafruit-circuitpython-bundle-10.x-mpy-20260620/`; the app already vendors the
  matching libs at `src/lib/` (committed, 10.x ABI).
- **Deploy:** `scripts/deploy.sh` — ships the **committed HEAD** (`code.py`, `boot.py`,
  `src/`, and scrollkit → `/lib/scrollkit`). Images under `src/images/rides/` ship
  automatically (tracked) via both USB deploy and OTA — **no script changes per ride.**
  ⚠️ deploy.sh uses `git archive HEAD`, so **commit before deploying** (a working-tree
  overlay variant is in scratchpad `deploy_worktree.sh` if ever needed).
- **Write-protect (boot.py):** the drive is read-only to the Mac during normal runs.
  To deploy/edit files from the Mac: **hold `DOWN` + tap `RESET`** (boots Mac-writable;
  `boot_out.txt` shows "Drive mount logic is: True"). To run normally: **tap `RESET`
  with no buttons** (device-writable, Mac read-only).
- **Serial:** `/dev/cu.usbmodem<BOARD_UID>` @ 115200 (this board:
  `/dev/cu.usbmodem84722EB3564F1`; `ls /dev/cu.usbmodem*` to confirm — the PORT is
  hard-coded in the two `tools/dev_*` scripts, update if it changes).
  - Watch a boot: `python tools/dev_serial_capture.py 90` then tap RESET.
  - On-device diagnostics: edit the `CODE` block in `tools/dev_repl_exec.py` and run it.
- **Pick the test park:** `settings.json` `selected_park_ids` (edit in Mac-writable mode)
  or the web UI at `http://testbox1.local/` / device IP `:80`. Currently set to Magic
  Kingdom with `skip_closed: false`. The original device settings backup is in this
  session's scratchpad (`device_backup/settings.json.predeploy.bak`).

---

## Gotchas (learned the hard way)

- **`hasattr` can't feature-detect dunders on CircuitPython native types.**
  `displayio.Palette` does `len()`/`pal[i]`/`pal[i]=` via C type-slots, so
  `hasattr(pal,"__len__"/"__setitem__")` is `False` on-device even though they work — and
  `True` in the pure-Python simulator. This made the intro work in the sim but silently
  no-op on hardware. Probe **functionally** (`len(pal); pal[0]` in a try/except). See the
  comment in `_load_intro`.
- **Sim vs device color/transparency:** the sim's `OnDiskBitmap` rebuilds the palette by
  top-left-first scan and stores RGB565 (`pal[i]` returns 565; use `get_rgb888()` when
  present); on-device `pal[i]` is RGB888. The "top-left = sky" rule keeps index 0 = sky on
  both. `tests/sim green ≠ device correct` — always verify on hardware.
- **deploy.sh ships committed HEAD only** — uncommitted work won't reach the device.

---

## References

- Approved plan: `~/.claude/plans/how-are-you-going-snug-eagle.md`
- Memory: `circuitpython-hasattr-native-slots`, `scrollkit-vendoring-deploy`
- Feature commit: `da36781`
- App overview: `CLAUDE.md` (and its Gotchas section / `SCROLLKIT_NOTES.md`)
