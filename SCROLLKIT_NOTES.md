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

## 3. OTA release model: `OTAClient` targets a FIXED branch (no branch discovery)
`OTAClient.for_github(owner, repo, branch=...)` fetches one fixed branch's
`manifest.json` and compares the manifest's `version` field. It does **not**
enumerate branches or select the newest `release-*` branch.

- **Impact:** ThemeParkWaits wants a "create a `release-MAJOR.MINOR` branch to
  publish" workflow (single public repo for dev + releases). That needs branch
  discovery (GitHub API `GET /repos/{owner}/{repo}/branches`, filter `release-`,
  pick the highest semver, point the client at it) — currently absent.
- **Resolved by multi-model consensus (2026, gpt-5.3-codex/gemini-3.1-pro/qwen3.7-max):
  DO NOT add on-device branch discovery.** On an ESP32-S3 + CircuitPython it's a trap:
  unauthenticated GitHub REST API is 60 req/hr per IP (a bootloop → `403` → updates
  starve), `json.loads` needs contiguous RAM (the `/branches` array grows → `MemoryError`),
  and the API is slower/un-CDN'd (asyncio stalls). The device must keep using
  `raw.githubusercontent.com` via a FIXED branch.
- **Adopted model: hybrid (Option C).** Device stays on a fixed `branch="live"` (no code
  change). The `release-MAJOR.MINOR` ergonomics + audit/rollback are handled OFF-device
  by automation (a GitHub Action or local `publish.sh`): on a new `release-*` ref it runs
  `make_manifest.py` and publishes `manifest.json` + `files/` to the `live` channel branch;
  the `release-*` branches/tags remain as immutable archives for rollback. (`live` is named
  distinctly from `release-*` to avoid a `releases`/`release-2.1` clash.)
- **For the library:** no discovery feature needed; at most **document that `for_github`
  is fixed-branch + version-in-manifest** so the branch-per-release expectation is set.
- **Doc placement:** the release-cutting workflow is a per-repo concern → `RELEASING.md`
  in this repo, NOT the library.

## 4. `@route` decorator sets a function attribute → fails on CircuitPython (web UI dead)
The web `route` decorator (`scrollkit/web/adapters.py`, `server.py`) does
`func._route_info = {...}`. **CircuitPython functions/methods don't support
arbitrary attribute assignment** (no `__dict__`) → `AttributeError: can't set
attribute '_route_info'` when a `@route`-decorated handler class is built on the
device. The whole config web server fails to start (the app catches it →
"web server unavailable"). CPython allows function attributes, so the **simulator
never caught this** — found only on a Matrix Portal S3 (2026-06-22).

- **Impact:** the config UI is completely unavailable on-device (blocks T038/T039).
- **Repro (device):** build any handler subclass using `@route` → import/construct
  raises `can't set attribute '_route_info'`.
- **Suggested fix:** don't attach metadata to the function object. Register routes
  in a class-level dict/list (decorator appends `(path, methods, func_name)` to a
  class registry, or `__init_subclass__` scans methods by naming convention) —
  anything that avoids `func.attr = ...`.
- **Workaround in this app:** none yet — needs a library change (or an app handler
  that overrides dispatch without `@route`).
- **Handed to the library agent (2026-06-22):** full fix spec + acceptance criteria
  in `specs/001-this-project-is/handoffs/scrollkit-web-route-circuitpython.md`.

## 5. First HTTPS request after WiFi connect fails with EINPROGRESS (slow boot)
On the ESP32-S3 the FIRST socket after WiFi association returns `OSError: [Errno
119] EINPROGRESS` in `adafruit_requests._get_socket`. `HttpClient` retries (3x) but
all attempts to that host fail, so `set_system_clock`'s HTTP-Date cascade burns
~30-40s on the first host (`time.cloudflare.com`) before falling back to the next
(`google.com`), which succeeds. The device **does** boot and run (clock, 141-park
list, ride data, both loops, 1.8 MB free) — but `setup()` blocks ~30-60s on the
splash first. Found on hardware 2026-06-22.

- **Impact:** slow, noisy boot; not fatal. Reordering hosts won't help (any first
  host hits it).
- **Suggested fix:** make the first request resilient — use
  `adafruit_connection_manager` (handles EINPROGRESS), add a short settle/retry on
  the first socket, or a cheap warm-up request. Separately, since synchronous HTTP
  in `setup()` freezes the boot UI, consider starting the display loop *before* the
  blocking clock/fetch so the panel isn't frozen during the retry.

## Not a ScrollKit bug — environment hazard worth noting
A stray Blinka **`displayio`** PyPI package in desktop site-packages shadows the
simulator's `displayio` if app code does a bare `import displayio`. Import the
platform-correct module from `scrollkit.display.unified` instead. (This app's
`reveal_splash.py` was fixed to do so.) Recommend `pip uninstall wifi displayio`
from the desktop dev environment to avoid both shadowing hazards.
