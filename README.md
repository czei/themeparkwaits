# ThemeParkWaits

Live theme-park ride wait times on a 64×32 LED matrix that sits on your desk or shelf. It joins your WiFi, pulls current standby times for the parks you pick, and scrolls each ride's name with its wait in big two-tone digits — green when the line is short, red when it isn't. Closed rides say so. Every ride can carry a tiny hand-drawn LED icon. No app, no account: you configure it from a web page the sign hosts itself, and it updates itself over the air.

*Built by [Michael Czeiszperger](http://czei.org)*

<p align="center">
  <video src="https://github.com/czei/themeparkwaits/raw/main/docs/media/themeparkwaits-gradient.mp4"
         width="640" controls muted playsinline>
    <!-- Fallback for renderers that don't play inline video -->
    <a href="https://github.com/czei/themeparkwaits/raw/main/docs/media/themeparkwaits-gradient.mp4">▶ Watch the ThemeParkWaits demo</a>
  </video>
</p>

## What it does

- **Live wait times** for 100+ theme parks worldwide (Disney, Universal, and many more) from the free [themeparks.wiki](https://themeparks.wiki) API — no API key, no login.
- **Readable across the room.** Each screen scrolls the ride name on top and shows the standby wait as a large 2× number below. Colors run green→red by how long the line is; closed / down / refurbishment rides are labeled instead of shown as a number.
- **Per-ride LED art.** Rides can display a small custom 64×32 intro icon (a boat for Jungle Cruise, a ghost for Haunted Mansion, and so on).
- **Pick your parks from a browser.** The sign runs its own configuration web page — choose up to four parks, set brightness and colors, sort/group, and hide closed rides or character meets. Nothing to install.
- **Set up WiFi with no cables.** First boot with no credentials opens a phone-friendly setup portal; you join its network, enter your WiFi, and it saves the credentials itself. No editing files on the device.
- **Updates itself over the air.** New releases install from a public GitHub channel with an on-device "Installing… do not unplug" screen, then reboot.
- **Built to run in the field, unattended.** Fault-tolerant data refresh, reboot-loop safe mode, and self-healing WiFi reconnection so it recovers from a power blip on its own.

## Hardware

- **[Adafruit Matrix Portal S3](https://www.adafruit.com/product/5778)** (ESP32-S3) running CircuitPython.
- A **64×32 RGB LED matrix panel** (HUB75), e.g. Adafruit's 64×32 panels.
- USB-C power.

The same code also runs on a desktop **simulator**, so you can develop and preview screens without any hardware (see below).

## Installing the app on the board

The easy install is the ready-made zip on the website: every file the board needs, already laid out. Flash [CircuitPython 10.2.1](https://themeparkwaits.com/downloads/circuitpython-matrixportal-s3-10.2.1.uf2), then copy the [zip's](https://themeparkwaits.com/downloads/themeparkwaits-usb-install.zip) contents onto the `CIRCUITPY` drive. The full walkthrough, including what to do when the drive shows up read-only, is at [Flash & Set Up](https://themeparkwaits.com/products/setup.html).

Installing by hand from the repos instead? The on-device layout is:

```
/code.py            this repo
/boot.py            this repo
/src/               this repo (src/lib is the Adafruit driver bundle; it stays inside src)
/lib/scrollkit/     the ScrollKit repo's src/scrollkit folder
```

Two things trip people up:

- **This repo has no top-level `lib` folder.** The board's `/lib/scrollkit` comes from the separate [ScrollKit repo](https://github.com/czei/scrollkit): copy its `src/scrollkit` folder onto the drive as `lib/scrollkit`, skipping `scrollkit/simulator` and `scrollkit/dev` (desktop-only, and they waste flash).
- **`src/lib` is not that `lib`.** It's the Adafruit driver bundle, and it stays where it is, inside `src`.

## First-time setup

1. **Flash and power on.** The sign shows an opening reveal splash, then looks for WiFi.
2. **Join the setup portal.** With no saved credentials it holds a setup portal open — connect your phone or laptop to it and enter your home WiFi. Credentials are saved to the device; it reconnects and reboots on its own if the power ever drops.
3. **Open the config page.** Once online it advertises itself on your network as **`themeparkwaits.local`** (served on port 80). Open that in a browser.
4. **Choose your parks and style.** Pick up to four parks, set brightness, colors, sort order, and whether to skip closed rides. Save, and the display rebuilds with your picks.

Wait times refresh every few minutes. Because each park's live feed is ~90 KB and the board has little RAM, selected parks are fetched one at a time with a garbage-collect between them, and a loading frame is painted before each blocking fetch so the sign never looks hung.

## Development (desktop simulator)

ThemeParkWaits is a domain app on top of the **[ScrollKit](https://github.com/czei/scrollkit)** LED-matrix library, which runs the same code on the Matrix Portal S3 and a desktop pygame simulator. Clone this repo next to a checkout of ScrollKit, then:

```bash
# Run the app in the desktop simulator (opens a live 64×32 preview window)
PYTHONPATH="../ScrollKit Library/src:src" python -m src.themeparkwaits --dev

# Feel the on-device frame rate on your desktop
SCROLLKIT_HW_SIM=1 PYTHONPATH="../ScrollKit Library/src:src" python -m src.themeparkwaits --dev

# Run the test suite (domain logic against a mocked HTTP client)
pytest tests/
```

The simulator talks to the real themeparks.wiki API, renders the real screens, and is how the layouts and ride icons are iterated. `tools/sim_shot.py` grabs headless screenshots for layout work.

### Previewing the ride animations

Each ride's icon plays a short intro animation before its wait time (twinkle, a vehicle crossing, a creature walking, …). `tools/intro_preview.py` drives the **real** intro pipeline (the same `RideScreenContent` + animators that run on the device) so you can look at all of them without booting the app:

```bash
# Page through EVERY animated ride in a live window
PYTHONPATH="../ScrollKit Library/src:." python3 tools/intro_preview.py
#   Right / Space = next   Left = previous   R = replay   Esc / Q = quit

# Or render them all to a GIF gallery you can open in a browser
PYTHONPATH="../ScrollKit Library/src:." SDL_VIDEODRIVER=dummy python3 tools/intro_preview.py --gif
#   -> writes media-raw/intro-preview/*.gif + index.html (open that index.html)
```

With no filter it shows every image that has a registered animation. Append case-insensitive filename substrings to narrow it, e.g. `... intro_preview.py ostrich tron pirates`. Which ride gets which animation is the `_SPECS` table in `src/ui/ride_animations.py`.

## How it's put together

Everything the library provides — the display abstraction, WiFi, HTTP, settings, the config web server, OTA, effects, and the desktop simulator — lives in `scrollkit.*`. This repo keeps only the theme-park domain:

```
boot.py, code.py, src/themeparkwaits.py, src/main.py   # entry / bootstrap
src/app.py                      # ThemeParkApp(ScrollKitApp): boot sequence + 5-min refresh
src/api/theme_park_service.py   # themeparks.wiki fetch/parse over ScrollKit's HttpClient
src/models/*                    # ThemePark / Ride / List / Vacation domain models
src/ui/content_builder.py       # sort / group / filter / attribution → the display queue
src/ui/ride_screen_content.py   # the dual-zone ride screen (scrolling name + 2× wait number)
src/ui/reveal_splash.py         # the opening reveal
src/web/config_server.py        # the browser configuration form
src/ota_glue.py                 # the GitHub OTA channel config
src/images/                     # per-ride LED intro icons
```

The scrolling effects, in-place number reveals, and screen transitions are chosen at runtime from ScrollKit's live effect catalog and randomized per screen, so the motion varies instead of looping the same animation.

## Data & attribution

Live wait-time and park data come from the **[themeparks.wiki](https://themeparks.wiki)** API (no authentication). As that project asks, the sign displays a **"ThemeParks.wiki"** attribution message in its rotation. The data is not part of this software and is subject to themeparks.wiki's terms.

## Acknowledgements

- **[ScrollKit](https://github.com/czei/scrollkit)** — the LED-matrix library this app is built on (over-the-air updates, effects, the web config server, and the desktop simulator). Same author, separately MIT-licensed.
- **[themeparks.wiki](https://themeparks.wiki)** — the wait-time and park catalog API.
- **[Adafruit](https://www.adafruit.com/)** — the Matrix Portal S3, the LED panels, and the CircuitPython libraries vendored in `src/lib/`.

## License

MIT — see [LICENSE](LICENSE). ThemeParkWaits vendors the Adafruit CircuitPython libraries (`src/lib/`), which retain their own MIT license; that notice is in the LICENSE file.
