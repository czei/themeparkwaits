# ScrollKit library — candidate issues found while porting ThemeParkWaits

Two items surfaced during the port that look like **ScrollKit-side issues worth
investigating separately** (not themeparkwaits bugs). Both have desktop
workarounds in this app; flagging for the library maintainer.

## 1. `is_dev_mode()` misfires when a stray `wifi` package is importable
`scrollkit.network.wifi_manager.is_dev_mode()` decides "am I on desktop?" by
trying `import wifi` and treating success as "real hardware". On a desktop with a
PyPI **`wifi`** package installed (common), that import succeeds, so `is_dev_mode()`
returns **False** on desktop → code takes the hardware path (real WiFi/NTP) and
blocks on failing network calls.

- **Impact here:** the app hung in `setup()` on `set_system_clock()` (NTP) → the
  simulator window never appeared.
- **Repro:** `pip install wifi` on desktop, then call `is_dev_mode()` → False.
- **Suggested fix:** gate on the real platform —
  `sys.implementation.name == 'circuitpython'` — rather than `import wifi` success.
  (HttpClient's own dev detection has the same shape.)
- **Workaround in this app:** `app._init_network()` gates on
  `sys.implementation.name == 'circuitpython'`.

## 2. `UnifiedDisplay.set_pixel()` / `fill()` render nothing in the simulator
`set_pixel()` and `fill()` write to the matrix, but `_update_simulator()` calls
`display.refresh()`, which repaints the surface **from the displayio group only** —
so direct matrix writes are overwritten and never show. `draw_text` (Labels) and a
`Bitmap`+`TileGrid` added to `main_group` render correctly; `set_pixel`/`fill` do
not, even though they are public `DisplayInterface` methods (and `clear()`'s
docstring implies `set_pixel` is supported: *"Clear any pixel data drawn outside
the displayio group (e.g. set_pixel)"*).

- **Repro (desktop sim):** `await d.set_pixel(10,10,0xFFFFFF); await d.show()` → blank;
  `await d.fill(0xFFFF00); await d.show()` → blank; a filled `TileGrid` in
  `main_group` → renders.
- **Likely also true on hardware** (displayio `refresh()` owns the framebuffer).
- **Suggested fix:** either document that pixel-level drawing must go through a
  `Bitmap`/`TileGrid` in `main_group`, or back `set_pixel`/`fill` with a bitmap that
  is part of the rendered group.
- **Workaround in this app:** the reveal splash draws via a `Bitmap`+`TileGrid` in
  `main_group` (not `set_pixel`).

## Not a ScrollKit bug — environment hazard worth noting
A stray Blinka **`displayio`** PyPI package in desktop site-packages shadows the
simulator's `displayio` if app code does a bare `import displayio`. Import the
platform-correct module from `scrollkit.display.unified` instead. (This app's
`reveal_splash.py` was fixed to do so.) Recommend `pip uninstall wifi displayio`
from the desktop dev environment to avoid both shadowing hazards.
