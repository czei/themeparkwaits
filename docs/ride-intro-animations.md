# Ride Intro Animations — Authoring Guide

How to design, validate, and land an intro animation for a ride icon. Written so an
agent (human or AI) with no prior context can do the whole loop autonomously and use
every capability the ScrollKit engine offers. For drawing the icon itself, see
`docs/ride-intro-images.md`; this doc starts where that one ends. The ENGINE has its
own documentation in the library repo (`docs/guide/effects.md`, with an animated GIF
of every animator, plus runnable demos) — this doc covers the APP side: picking the
right motion for a ride, the `_SPECS` registry, the owner's art rules, and validation.

**The system in one paragraph.** Every ride icon is a 64x32 indexed BMP in
`src/images/rides/` (sky = palette index 0). During the intro HOLD (~5 s at ~20 fps)
the icon may animate; which icon gets which animation is `_SPECS` in
`src/ui/ride_animations.py` — **one data line per image**, `"file.bmp": (kind, kwargs)`
or `("combo", ((kind, kwargs), ...))`. The engine (13 generic per-frame primitives)
lives in the library: `scrollkit/effects/image_animators.py`. Any animator failure at
start or step degrades to the still image, never a blank panel (`ANIM-START-FAIL` /
`ANIM-STEP-FAIL` on serial).

**The invariant (since ccdc89a):** every shipped icon has an animation. A new icon
lands with its spec line in the same change.

## Where things live

| What | Where |
|---|---|
| Spec registry (`_SPECS`) + bespoke animators | `src/ui/ride_animations.py` |
| Engine (13 primitives + Combo) | `../ScrollKit Library/src/scrollkit/effects/image_animators.py` |
| **Engine guide with a GIF of every animator** (lifecycle, substrates, feasibility) | library `docs/guide/effects.md` ("Image animators") + `docs/guide/visual-reference.md` |
| Runnable engine demos (intro contract; the cel-walk ostrich) | library `demos/medium/image_intro.py`, `demos/medium/walking_ostrich.py` |
| Icons + walk sheets + manifest | `src/images/rides/` |
| Intro host (HOLD/fade phases, fallback) | `src/ui/ride_screen_content.py` |
| Headless verifier (contact sheet + motion metric) | `tools/anim_verify.py` |
| Interactive / GIF-gallery preview | `tools/intro_preview.py` (also `anim_demo.py`) |
| Registry safety net (parametrized over every spec) | `tests/domain/test_ride_animations.py` |

Headless runs need: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy` and
`PYTHONPATH="../ScrollKit Library/src:."`, cwd = this repo.

## The authoring loop

1. **Look at the art.** Upscale the BMP x10 nearest-neighbor with Pillow and read the
   pixel grid (indices + palette RGB). Identify features with exact coordinates. Every
   box/pivot/color in a spec must be pixel-true; never guess coordinates.
2. **Pick an archetype** from the table below. Prefer the primitive that matches the
   subject's real physics; read 2-3 comparable shipped specs first — they are the
   authority on kwarg value formats. (Conventions throughout: boxes are inclusive
   `(x0, y0, x1, y1)`; colors are packed RGB888 ints like `0x44DD55`, never palette
   indices; `blink` repaints EVERY non-sky pixel in its box with `color`, so keep eye
   boxes off adjacent features.)
3. **Write the spec line** (alphabetical position in `_SPECS`, double-quoted filename
   key, trailing comma). Comment only what the code can't say (pivot/exclude reasoning,
   clamp direction) — see the goat, dinosaur, and plant entries for the idiom.
4. **Validate a PROPOSAL without editing the registry** (for review/iteration): copy
   `tools/anim_verify.py` to a scratch dir, fix its repo-root `sys.path` insert to this
   repo's absolute path, and inject in-memory right after its imports:

   ```python
   import src.ui.ride_animations as ra
   ra._SPECS["name.bmp"] = ("region_rotate", dict(box=..., pivot=..., amp_deg=9, period=64))
   ```

   (Same idiom the test suite uses: `monkeypatch.setitem(ra._SPECS, ...)`.) Then run it
   with cwd = this repo (the verifier's image dir is cwd-relative) and the env prefix
   from "Where things live":
   `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy PYTHONPATH="../ScrollKit Library/src:." python3 <scratch>/verify_name.py name.bmp <outdir>`
5. **Check the gates.** `animator=` must be your class (not `None` — `None` means the
   spec didn't resolve or a budget guard raised at start and the host fell back);
   `motion=` must be > 0; then **look at the contact sheet**: does the motion read at
   64x32, is the art intact (no holes, smears, or seams), does it settle for the fade?
   Iterate kwargs until all three pass. (The motion metric counts SIMULATOR SURFACE
   pixels — each LED renders as a multi-pixel disc — so magnitudes look big: a subtle
   two-eye blink ≈ 300, a traverse or rotate in the thousands, a static icon exactly
   0.0. Judge legibility on the sheet, not the number.) The later pytest and gallery
   gates exercise the shipped registry, so they apply at landing (step 6), not to an
   in-memory proposal.
6. **Land it**: edit `_SPECS` for real, then
   `pytest tests/domain/test_ride_animations.py -q` (parametrized over every entry, so
   your line is exercised against the real BMP automatically) and re-run `anim_verify`
   from the registry. Regenerate the review gallery for the owner:
   `python3 tools/intro_preview.py --gif <names...>` →
   `media-raw/intro-preview/index.html`.
7. **Owner review.** Animations are art-directed; ship after sign-off, with a one-line
   alternative concept in your pocket for anything rejected.

## Choosing an archetype

Match the SUBJECT, not the effect you feel like using:

| Your subject | Archetype | Spec shape | Shipped examples |
|---|---|---|---|
| Vehicle/creature on empty sky that should cross the panel | whole-tile traverse | `("motion", dict(path='traverse_lr'\|'traverse_rl', bob_amp=0-2))` | airplane, shark, witch, carousel_horse |
| Character idling in place | bob / jiggle | `("motion", dict(path='bob'\|'jiggle', amp=1-2))` | child, minion, yoshi |
| Rocket / launch | rise | `("motion", dict(path='rise', delay=20-40))` + exhaust emitter | rocket, xwing |
| Vehicle drawn INSIDE a scene (water, rails, jungle) | **lift** (scene division) | `("lift", dict(boxes=(...), exclude_colors=(scene colors), tol=28, path, slope, loop))` | jungle_cruise, coaster_car, riverboat, hang_glider |
| Winged flyer that must beat its wings | traverse + 2 wing shifts | combo: motion + two `region_shift` (`wave='hinge'`, mirrored `hinge=`/`phase`) | bat, bird, fairy |
| **Walking animal or human** | **cel_walk + sprite sheet** | `("cel_walk", dict(period=4-8, bob=0-1))` + `<name>_walk.bmp` — see below | ostrich |
| Head / neck / limb / leaf at a joint | region_rotate | `("region_rotate", dict(box, pivot, amp_deg=6-13, period=40-84, exclude, half))` | big_thunder_goat, dinosaur, giraffe, plant |
| Small feature that translates (tail, ghost, jaw, door) | region_shift | `("region_shift", dict(box, axis, amp=1-2, period, wave, half))` | slinky_dog, monkey, haunted_mansion, jellyfish |
| Face looking at the viewer | blink | `("blink", dict(box=<eye>, color=<local fur color>, period, duty, delay))` | bear, panda, tiger (two parts, per-side fur) |
| Lit windows / neon / glow | palette_pulse | `("palette_pulse", dict(match=(exclusive colors), tol, lo, hi, period))` | tower_of_terror, light_bulb, pagoda |
| Stars / gems / glinting water | twinkle | `("twinkle", dict(colors=(dark,mid,bright), count, box))` | spaceship_earth, gems, tree, river |
| Steam / fire / bubbles / spray / snow | emitter | `("emitter", dict(box=<orifice>, vx, vy, rate, life, colors=young→old, max_live, jitter))` | tea_cup, volcano, submarine, everest |
| Tiny creature circling a landmark | orbiter | `("orbiter", dict(cx, cy, rx, ry, period, sprite=((dx,dy,color),...), wobble))` | barn, honey_pot, pyramid |
| A gag with a beat (pop-out, bite, slide) | reveal one-shots | `region_shift` `hide_before+delay` / `wave='ramp'` / `cover` / `vanish`, staged in a combo | jack_in_box, door, dragon, donut |
| Large cloth/water that must ripple whole | frames (pre-baked cels) | `("frames", dict(box, nframes=4-6, amp=2, wavelength=10-16, period=3))` | flag |
| Nothing above fits | bespoke class (last resort) | subclass `IntroAnimator` in ride_animations.py, register in `_CLASSES` | turtle (swim), rock_roller (sheen) |

Emitter velocity encodes the physics: steam/bubbles rise (`vy` -0.4), spray bursts
(`vy` -1), falls/lava drop (`vy` 0.5-0.8), wind-blown snow drifts (`vx` 0.7,
`vy` -0.15), laser bolts shoot flat and fast (`vx` 3, `jitter` 0). Colors always ramp
young→old (fire: white→orange→red→ember).

## Walkers: cel-walk sprite sheets

The one archetype that needs new ART, not just a spec line. The engine
(`CelWalkAnimator`) blanks the still, plays a sibling sprite-sheet strip as a
tile-indexed TileGrid, and strides it across the panel (HOLD_FRAMES=104, one full
off-screen-to-off-screen crossing). O(1) per frame; a missing/bad sheet raises BEFORE
the still is blanked, so the fallback is safe. A runnable reference lives in the
library: `demos/medium/walking_ostrich.py`.

**Sheet contract:** `<stem>_walk.bmp` beside `<stem>.bmp` (the `_walk` suffix is how
the animator finds it — the sheet is never in the manifest). One horizontal strip of N
panel-sized cels: width 64*N, height 32, ONE shared palette, sky at index 0, global
top-left pixel sky. Keep colors few and 4-bit-clean (ostrich sheet: 4 cels, 5 colors).

**Authoring (the ostrich template, `tools/gen_ride_designs.py`):**
1. Split the drawing: `_<stem>_body(g)` (pixel-identical in every cel — a changing
   body shimmers) and `_<stem>_legs(g, lf, rf)` (each leg a `thick_line` width 2 from
   FIXED hip constants down to the foot points; contrasting toe pixels so steps read).
2. Walk cycle = a list of (left, right) foot positions, minimum 4 cels for a biped:
   double-support → leg A lifts (~2 px, y=31→29; more reads as hopping) and swings
   forward while B's planted foot drags BACKWARD ~3 px → mirrored double-support →
   leg B lifts. Legs 180° out of phase. **Anti-moonwalk rule:** planted feet must
   translate backward relative to the body so they read as fixed to the ground while
   the sprite travels.
3. `write_sheet("<stem>_walk", grids)` composes the cels into the strip BMP; add a
   dispatch so `python tools/gen_ride_designs.py <stem>_walk` regenerates it.
4. Spec: `"<stem>.bmp": ("cel_walk", dict(period=6, bob=0))`. `period` is display
   frames per pose; `path='traverse_rl'` walks right-to-left; `bob=1` adds vertical
   bounce.

**Humans vs animals:** same engine, different art. A human gait reads better with 6-8
cels (contact/down/pass/up per side) and needs counter-swinging ARMS drawn per cel
(left arm forward with right leg — that's what sells it) plus `bob=1`; the ostrich
ships 4 cels, frozen wings, `bob=0`. Quadrupeds: move diagonal leg pairs together
(4 cels), or 8 cels for a lateral-sequence walk. Always draw walkers in profile —
front-facing gaits can't show leg phase at this resolution.

## Art direction (owner-approved rules — follow them, cite them in review)

- **One clear physical idea per icon.** Subtle beats flashy; this is a wait-time
  display, not a demo reel. Amplitudes are 1-2 px, angles 6-13 degrees.
- **Scene division: water, track, and scenery NEVER move.** Only the vehicle does
  (that's what `lift` is for). Transport intros show the scene first, then the vehicle
  crosses. Whole-image `lift` with no scene is a misuse (on-device it stalls, then
  vanishes and re-enters).
- **Vehicles lead nose/bow-first**, matching which way the art faces. Fix the art's
  facing rather than traversing backwards.
- **Joints rotate, they don't shear.** Heads/necks/leaves get `region_rotate` with the
  pivot at the anatomical joint and `exclude` on the attached body ("never holed").
  Clamp one-sided motion with `half` (the T-rex rears up, never pecks).
- **Foliage sways or rotates; it does not bob vertically** (owner, 2026-07-10: "leaves
  should wave, not bop up and down").
- **No moonwalking** (walkers above); ostriches walk without bobbing.
- **Blinks cover the eye with the fur color local to that eye** (two-part blink when
  the face is shaded per side, like the tiger).
- **`palette_pulse` match colors must be exclusive to the glowing feature** — every
  palette entry within `tol` pulses wherever it appears.
- Gags land ONCE, mid-hold (cue frames 12-55 of ~96).
- The registry line is data; if you're writing loops in a spec, you want a combo or a
  bespoke class.

## Validation gates (all mandatory before landing)

1. `anim_verify.py`: `animator=` is your class, `motion=` > 0, and the CONTACT SHEET
   looks right to an actual pair of eyes (art intact, motion legible, clean settle).
2. `pytest tests/domain/test_ride_animations.py -q` — green.
3. `intro_preview.py --gif` gallery regenerated for owner review.
4. On-device sanity after deploy for pixel-heavy animators (see below): watch serial
   for `ANIM-START-FAIL` / `ANIM-STEP-FAIL` via `tools/dev_serial_capture.py`.

## Device vs simulator (sim-green is not device-green)

- The simulator presents finished frames: start()-time stalls are INVISIBLE in sim.
  SpriteLift's row-inpaint once cost 1.6 s at start on device.
- On-device `OnDiskBitmap` is not subscriptable; pixel-reading animators get a
  writable copy via `read_indexed_bmp` (a 2048-iteration Python loop, one-time).
- Measured on-device step costs: 0.1-5.3 ms/frame across all kinds; the display loop
  budget is 50 ms at ~20 fps. HOLD is frame-counted, not wall-clock.
- CircuitPython quirks the engine already handles: no `random.shuffle`, no
  `math.hypot`, no attributes on functions, `hasattr` unreliable on native types.

## Budgets (raise at start = automatic fallback to still)

| Animator | Guard |
|---|---|
| region_shift | ≤ 320 lit px (sine/ramp), ≤ 240 (ripple/hinge); 0 lit px raises |
| region_rotate | ≤ 320 lit px AND ≤ 1600 scan cells (box grown by arc margin) |
| emitter | max 8 live particles (silent cap — asking for 20 gets 8) |
| blink | no cap — a huge box is a silent perf cost, keep eyes eye-sized |
| frames | RAM: nframes × ~1 KB bitmaps, unenforced — budget it yourself |
| cel_walk | raises if the sheet is missing/narrower than one tile |
| lift / frames | raise on empty capture |

`HOLD_FRAMES`: 96 default (~5 s); traverse/lift/cel_walk/swim 104; rise 84; sheen 108.
Combo = max of its parts; parts step in PARALLEL on one clock — sequence with per-part
`delay` / `until` / `hide_before`, not by ordering.

## Known kwarg traps

- `motion` `delay` is read ONLY by `path='rise'` (a delayed traverse doesn't exist;
  the fairy spec's `delay=40` is silently ignored).
- `frames` `exclude_colors`/`tol` are DEAD kwargs (stored, never read).
- `region_shift` box rule is unenforced: box expanded by the travel along axis must
  contain only that feature plus sky, or you smear/erase neighboring art (watch
  features adjacent to stems, masts, bodies — clamp with `half` to sway AWAY from
  them).
- `for_image()` swallows construction errors only; budget guards raise from start()
  and the HOST catches them — either way you get a still icon and `animator=None` in
  anim_verify, so check that line.

## Capabilities nothing uses yet (reach for these when they fit)

- `emitter follow_tile=True` — exhaust puffing from a MOVING vehicle's own stack
  (composes with `motion`/`swim` tile movement; does NOT track a `lift` subject, whose
  motion lives on the lift's private overlay).
- `cel_walk` generality: `sheet_suffix`, `path='traverse_rl'`, sub-panel `tile_w/h`,
  `bob` — all implemented, only defaults ship.
- `frames` beyond the flag: any large cloth/water over the ripple cap (sails, banners,
  a full-width sea).
- `region_rotate` `phase`/`delay`/`half='neg'`/multi-box `exclude` — all supported,
  unused.
- `cover` with `dx≠0` (hold a lever in its "before" pose) or `blank=False` (ghost
  double); `orbiter clockwise=False`; nested combos (`_build` recurses).

## Bespoke animators (the escape hatch)

When no primitive combo expresses the signature motion, subclass `IntroAnimator` in
`ride_animations.py` (NOT the library), register in `_CLASSES`, one spec line. The two
shipped examples show both substrates: `SwimAnimator` (turtle: tile motion + in-place
flipper restamp, constants tuned to turtle.bmp) and `SheenAnimator` (rock_roller:
overlay-only specular sweep via `_make_overlay`/`_drop_overlay`). Both are "approved
as-is, do not generalize." Prefer a combo first; going bespoke is an owner decision.
