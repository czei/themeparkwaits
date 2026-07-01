---
name: ride-icon
description: Create or edit a 64×32 LED "intro image" for a ThemeParkWaits ride, and map it to rides by UUID. Use when adding icons for a park (or a single ride), drawing a new silhouette, re-shading one, or wiring ride UUIDs to an existing icon in the manifest. Covers the draw→flat→rich→manifest→verify pipeline and the hard-won 64×32 gotchas.
---

# ThemeParkWaits Ride Icons

Each ride can play a 64×32 silhouette before its wait-time screen (HOLD → FADE+scroll →
NORMAL). Icons are **matched strictly by themeparks.wiki ride UUID** via
`src/images/rides/manifest.json`; a missing/mismatched entry just renders the normal
screen (icons are purely additive — they can never break a ride). Many UUIDs → one file
is the norm (one drawing serves that ride at every park).

## When you only need to reuse an existing icon
No code, no art. Add `"​<uuid>": "<existing_file>.bmp"` lines to
`src/images/rides/manifest.json` under `"rides"`. Done. List the 71+ existing subjects
with `ls src/images/rides/*.bmp`. Find a park's rides + UUIDs with
`python tools/list_park_rides.py --park <parkUUID>` (`--list-parks` for park UUIDs).

## Drawing a NEW icon — the pipeline

1. **Draw** a function in `tools/gen_ride_designs.py` (append a labeled batch, register it
   in the `if __name__ == "__main__":` dispatch). Use the primitive DSL: `grid`, `put`,
   `hline`/`vline`, `rect`, `line`, `thick_line`, `ring`, `ellipse(…, half="top"|"bottom")`,
   `fill_tri`, then `write("<name>", g)`. Colors are single chars from
   `make_ride_image.PALETTE` (e.g. `#`=white, `r`=red, `g`/`G`=green, `s`/`S`=grey,
   `K`=near-black, `o`=gold, `y`=yellow, `p`=pink, `O`=orange, `~`=cyan, `T`=sandstone).
   Add a new char to
   that PALETTE if you need a colour — keep every channel a multiple of `0x11` (4-bit clean).
   Run `python tools/gen_ride_designs.py`.
2. **Flatten** to the pre-shade "original":
   `python tools/make_ride_image.py designs/<name>.txt --name <name> --out-dir designs/originals`
3. **Re-shade** to the shipped BMP:
   `PYTHONPATH="tools" python tools/gen_rich_icons.py <name>`
   With no hero entry this uses `generic()` (auto-ramp per region colour — usually fine).
   For polish add a hero function + register it in the `HEROES` dict of
   `tools/gen_rich_icons.py` (bespoke ramps, `extras()` for glints/glows). Reuse shared
   ramps `_RED/_GOLD/_WOOD/_STEEL/_WATER/_GREEN/_WHITE/_INK/…`.
4. **Review the preview** — `designs/<name>.rich.preview.png` is an LED-dot render. Look at
   it (montage several with PIL). Iterate the design until it reads at LED scale. The human
   approves every image — don't over-iterate blind; get a solid first pass and show it.
5. **Map** the ride UUID(s) → `<name>.bmp` in `src/images/rides/manifest.json`.
6. **Render-test** — add one sample `(name, uuid)` to `RIDES_WITH_INTRO` in
   `tools/intro_shots.py`, then
   `PYTHONPATH="../ScrollKit Library/src:." SDL_VIDEODRIVER=dummy python3 tools/intro_shots.py /tmp/x "<name>"`
   asserts the intro phases through the REAL `UnifiedDisplay` (exercises the on-disk BMP +
   palette path). Also run `pytest tests/` (manifest loader).

## Format invariants (enforced; violating them fails the build or the panel)
- **64×32 indexed BMP** (Pillow "P" mode), ≤256 palette entries.
- **Palette index 0 = sky AND the top-left pixel must be sky.** The device reads the BMP
  palette (sky=0); the sim rebuilds it by top-left-first scan. Both make `make_transparent(0)`
  mean "sky" only if this holds. Keep row 0 / corners empty (' ').
- **4-bit-clean** colours (channels = multiples of `0x11`) so sim == device (`bit_depth=4`).

## Hard-won gotchas
- **Black vanishes.** Sky = LEDs off = black, so a pure-black fill (`K`=`111111`) is
  invisible on the panel. For black subjects/parts (panda ears, tyres, outlines) either draw
  them in a **visible dark grey** (`S`) or add a hero ramp mapping `111111` up to grey — see
  `_INK = ramp((0x22,0x22,0x22),(0x66,0x66,0x66),4)` and the panda/minion heroes.
- **Don't outline the silhouette in black.** A black outer contour against sky vanishes and
  leaves GAPS — the clownfish tail detached from its body this way. Build the subject as ONE
  connected fill (draw fins/limbs overlapping the body so they merge) and let the fill colour
  be the edge. Reserve `K`/dark only for INTERNAL detail lines (between two visible colours).
- **Sanity-check the aspect ratio.** Match the subject's real proportions to its bbox — the
  cassette first came out too wide (~2.4:1) and had to be narrowed to ~1.5:1. Compare the
  preview to how the real object actually looks.
- **Paint detail onto an existing fill** so stripes/bands/patches follow a curved body:
  recolour only pixels currently the body colour (`if g[y][x]=="O": g[y][x]="#"`), and the
  marking auto-conforms to the silhouette (clownfish bands).
- **64×32 is tiny — keep the composition simple.** A motorcycle *with sidecar* crowded out
  the front wheel and read as a blob; the clean two-wheeler read instantly. Prefer one bold,
  legible subject over a busy accurate one. Wheels read best as **hollow spoked rings** in
  grey (ring + spokes + hub), not filled discs.
- **`generic()` is a good default**; only write a hero when a part needs a specific colour
  lift, a glow, or an accent the auto-ramp washes out.
- **`hasattr` can't feature-detect dunders on CircuitPython native types** — the intro's
  palette probe is functional (`len(pal); pal[0]` in try/except). Sim-green ≠ device-correct.

## Mapping a whole park efficiently
Universal repeats franchises across parks, so a few new franchise silhouettes unlock most
mappings and the rest reuse existing icons. A **keyword-rule mapper** (first substring in the
lowercased ride name wins, ordered specific→general, plus a SKIP list for shows/kiddie
attractions) is the fast, auditable way to map ~140 rides — dry-run it and check for any
UNMATCHED before writing the manifest. (See `docs/ride-intro-images.md` and the
`docs/ride-icons.md` checklist generator `tools/gen_ride_checklist.py`.)

## Deploy
`scripts/deploy.sh` ships **committed HEAD** (`git archive HEAD`) — commit first. The FAT
rsync is slow: run it **backgrounded** (the 120 s foreground timeout kills it mid-write) and
check its exit code from a log, never pipe it through `grep`. It seeds `secrets.py`/
`settings.json` only if absent. Board must be Mac-writable (`boot.py`: hold DOWN + tap RESET;
`boot_out.txt` shows "Drive mount logic is: True"); tap RESET with no buttons to run normally.

## Key files
`tools/gen_ride_designs.py` (shapes) · `tools/make_ride_image.py` (flat BMP + PALETTE) ·
`tools/gen_rich_icons.py` (re-shader + HEROES) · `tools/list_park_rides.py` (ride UUIDs) ·
`src/images/rides/manifest.json` (UUID→file) · `src/ui/ride_images.py` (lookup) ·
`src/ui/ride_screen_content.py` (intro state machine) · `tools/intro_shots.py` (sim e2e) ·
`docs/ride-intro-images.md` (full guide).
