# Contract: ScrollKit API consumed by ThemeParkWaits

This is the app↔library **integration contract** — the exact public symbols the ported app depends on, per subsystem. If any symbol/signature here is wrong, the port fails to import or run; treat this list as the checklist the port must satisfy (and the surface to re-verify against the library before coding each task). Paths are under `ScrollKit Library/src/scrollkit/`.

## Re-verify before coding  *(review S9/B2 — confirm against live source before each subsystem task)*
The symbols below came from a source survey; these specific points MUST be re-checked against the current library before implementation, because they change the design if wrong:
1. **Display sync/async boundary** — are `UnifiedDisplay.draw_text` / `clear` / `show` sync or async, and may a `DisplayContent.render(display)` call them directly? (Survey listed `draw_text` async but `render(display)` as a plain override — reconcile.) Drives the ride-screen design.
2. **`show_loading()` signature/contract** — exact override shape and whether it must `clear→draw→show` then yield once before the blocking fetch.
3. **`SettingsManager` scroll-speed map** — does the library actually expose the Slow/Medium/Fast→delay map, or must the app keep it? (Listed in data-model but not in the §Config method list below.)
4. **`WiFiManager` credential storage** — `secrets.py` vs `settings.json` (vs both); what `connect()` and the AP `/configure` flow read/write.
5. **`HttpClient.get` retry/backoff + response lifecycle** — actual `max_retries`/backoff behavior and whether responses must be `.close()`d.
6. **Web handler construction** — how a `WebHandler` subclass is registered and how it receives the app/`SettingsManager`/content builder.
7. **OTA manifest path semantics** — how `for_github` maps manifest `files{}` paths to on-device locations; `current_version` source.

## App framework — `scrollkit.app`
- `from scrollkit.app.base import ScrollKitApp`
  - `ScrollKitApp(enable_web=True, update_interval=300)`
  - override async: `setup()`, `update_data()`, `prepare_display_content()`, `cleanup()`, `show_loading()`, `create_display()`, `create_web_server()`
  - attrs: `self.display`, `self.content_queue`, `self.running`; `run()`, `frame_count`, `fps()`, `describe()`, `memory_estimate()`

## Display + content — `scrollkit.display`
- `from scrollkit.display.unified import UnifiedDisplay` → `UnifiedDisplay(width=64, height=32, bit_depth=4)`
  - async: `initialize()`, `clear()`, `show() -> bool`, `draw_text(text, x=0, y=0, color=0xFFFFFF, font=None)`, `scroll_text(...)`, `set_pixel(...)`, `fill(color)`, `set_brightness(0..1)`; props `width`, `height`; `feasibility_report()`
- `from scrollkit.display.content import DisplayContent, StaticText, ScrollingText, ContentQueue`
  - `StaticText(text, x=0, y=0, color=0xFFFFFF, duration=None, priority=2)`
  - `ScrollingText(text, x=None, y=0, color=0xFFFFFF, speed=30, priority=2)`
  - `DisplayContent(duration=None, priority=2)` → override `render(display)`, `start()`, `stop()`, prop `is_complete` (subclass for the ride screen)
  - `ContentQueue(loop=True)` → `add()`, `clear()`, `get_content_count()`, async `get_current()`
- `from scrollkit.display.simulator import SimulatorDisplay` (desktop dev only)

## Effects — `scrollkit.effects`
- `from scrollkit.effects.reveal import RevealEffect` → `RevealEffect(duration=2.0, direction='right', pause_at_end=1.0)`; `await effect.apply(display, render_func)` (splash)
- `from scrollkit.effects.effects import EffectsEngine` (optional color helpers)

## Network — `scrollkit.network`
- `from scrollkit.network.wifi_manager import WiFiManager` → `WiFiManager(settings_manager)`
  - async `connect(display_callback=None) -> bool`, `disconnect()`, `reconnect()`, `reset()`; `create_http_session()`; onboarding: `start_access_point(port=80)`, `register_routes()`, async `run_web_server(termination_func)`; attrs `is_connected`, `ssid`, `password`, `AP_SSID`, `AP_PASSWORD`, `HAS_WIFI`
- `from scrollkit.network.http_client import HttpClient` → `HttpClient(session=None, mock_provider=None)`
  - async `get(url, headers=None, max_retries=3)`, `post(url, data, headers=None)`; `get_sync(...)`; response `.status_code/.text/.content/.headers/.json()/.close()`

## Config — `scrollkit.config`
- `from scrollkit.config.settings_manager import SettingsManager` → `SettingsManager(filename, defaults=None, bool_keys=None)`
  - `get(key, default=None)`, `set(key, value)`, `save_settings()`, `load_settings()`, `set_defaults(d)`, `add_bool_keys(*keys)`, static `get_pretty_name(name)`

## OTA — `scrollkit.ota`  *(public `releases` branch + `manifest.json`, no device auth — resolved 2026-06-20)*
- `from scrollkit.ota.client import OTAClient`
  - `OTAClient.for_github(owner, repo, branch="releases", current_version="0.0.0", update_dir="/updates", backup_dir="/backup")`
  - `check_for_updates() -> (bool, manifest|err)`, `download_update(manifest=None)`, `apply_update(manifest=None)`, `reboot_device()`, `set_callbacks(on_available, on_progress, on_complete, on_error)`
- `from scrollkit.ota.manifest import UpdateManifest`

## Web server — `scrollkit.web`
- `from scrollkit.web import SLDKWebServer` → `SLDKWebServer(app=None, handler_class=None, socket_pool=None, static_dir=None)`
  - async `start(host=None, port=None)`, `stop()`, `handle_requests()`, `run_forever()`; `get_server_url()`; prop `is_running`
- `from scrollkit.web.handlers import WebHandler, StaticFileHandler, APIHandler`
- `from scrollkit.web.forms import FormBuilder`; `from scrollkit.web.templates import HTMLBuilder`
- `from scrollkit.web.adapters import create_server_adapter` (adafruit_httpserver on device / aiohttp on desktop — auto)

## Utils — `scrollkit.utils`
- `from scrollkit.utils.error_handler import ErrorHandler` → `ErrorHandler(file_name, mode=None)`; `error(e, desc)`, `info(msg)`, `debug(msg)`; classmethods `set_mode/get_mode`
- `from scrollkit.utils.color_utils import ColorUtils` → `to_rgb`, `from_rgb`, `scale_color`, `hex_str_to_rgb`, `colors`
- `from scrollkit.utils.system_utils import set_system_clock` → async `set_system_clock(http_client, socket_pool=None, tz_offset=-5, http_date_hosts=None)`
- `from scrollkit.utils.url_utils import url_decode, load_credentials`

## Deployment
- Device: copy `scrollkit/` into `/lib/`. Desktop: `ScrollKit Library/src` on `sys.path` (or `pip install -e ".[simulator]"`). Library ships `.py`; `scrollkit/__init__.py` does no eager imports (RAM).

## Gaps NOT covered by the library (stay app code)
mDNS hostname; the dual-zone ride-screen layout + 2× number font; the config-page HTML/route content + which settings exist; queue-times.com fetch/parse. (OTA is **not** a gap — handled by `OTAClient` against a public `releases` branch + `manifest.json`; the only app-side work is the release pipeline emitting `manifest.json`.)
