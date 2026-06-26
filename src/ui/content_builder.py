"""Builds the display ContentQueue from theme-park data + settings.

Domain ordering (sort / group-by-park / skip filters / multi-park / vacation /
attribution) is unchanged, and so is the RIDE LAYOUT: the dual-zone ride screen
(scrolling NAME on top + large 2x wait NUMBER on the bottom, or "Closed").

What is chosen at RUNTIME from the live ScrollKit catalog (``src.ui.effect_catalog``)
and RANDOMIZED per item — never a hardcoded list:
  * the ride NAME gets a random SCROLLING-category effect (KineticMarquee/WaveRider),
    rendered in the top zone by an embedded effect instance;
  * the wait NUMBER gets a random STATIC-category reveal (Rain/Swarm) — it still
    assembles in place at the same size/position (the layout never changes);
  * every screen gets a transition (rides carry overlay layers, so they use the
    overlay-safe Horizontal Wipe; message scrollers get a random catalog transition).
Info messages are single scrolling lines presented by a random scroller/palette.

Copyright 2024 3DUPFitters LLC
"""
from __future__ import annotations

import random

from scrollkit.display.content import ScrollingText
from scrollkit.effects.scrolling import KineticMarquee
from scrollkit.display.bitmap_text import BitmapText, RainbowChase
from src.ui.effect_catalog import scrolling_catalog
from src.ui.reveal_splash import SplashContent
from src.ui.ride_screen_content import (
    RideScreenContent, ClosedRideContent, _to_int_color, _NAME_Y, NUMBER_STYLES,
)

REQUIRED_MESSAGE = "ThemeParks.wiki"

# draw_text's y is the text BASELINE (top-down origin; y=0 clips off the top).
_SCROLL_Y = 13          # message scroller baseline (centers one line)
_PALETTE_Y = 12         # top of the 5x7 bitmap glyphs (palette message, full panel)
_NAME_PALETTE_Y = 2     # top of the 5x7 glyphs for a palette NAME — kept in the top
                        # zone, clear of the wait-number band (so the layout holds)

# Rides carry overlay layers (the wait-number reveal), which only composite cleanly
# under the overlay-safe wipe; message scrollers (content_group) get a random one.
_TX_SCROLL = "Horizontal Wipe"
_TX_RIDE = _TX_SCROLL

# The wait NUMBER's effect is randomized per ride across BOTH the assembly reveals
# ("Rain" drips the digits down, "Swarm" flies a flock in) and the held colour
# animations (sheen/pulse). ALL render the digits in their green->red SEVERITY
# colour, in place at 2x size — the layout never changes.
_NUMBER_EFFECTS = ("Rain", "Swarm") + tuple(NUMBER_STYLES)

# Wait severity coloring (wait_color_mode="severity"): minutes -> color, green
# (short) through red (long). 4-bit-clean channels so they survive bit_depth=4.
_SEVERITY_BANDS = ((20, 0x00FF00), (45, 0xFFC000), (75, 0xFF8000))
_SEVERITY_MAX = 0xFF0000   # 76+ minutes


def _severity_color(minutes):
    """Color for a wait of ``minutes`` under severity coloring (green -> red)."""
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        return _SEVERITY_BANDS[0][1]   # unknown wait reads as low, not alarming
    for threshold, color in _SEVERITY_BANDS:
        if m <= threshold:
            return color
    return _SEVERITY_MAX


def _sort_rides(rides, sort_mode):
    """Sort a list of ThemeParkRide by the given mode (closed rides weigh 0)."""
    if sort_mode == "max_wait":
        return sorted(rides, key=lambda r: r.wait_time if r.open_flag else 0, reverse=True)
    if sort_mode == "min_wait":
        return sorted(rides, key=lambda r: r.wait_time if r.open_flag else 0)
    return sorted(rides, key=lambda r: r.name.lower())   # alphabetical (default)


def _sort_pairs(pairs, sort_mode):
    """Sort (park_id, ride) tuples like _sort_rides sorts rides (combined mode)."""
    if sort_mode == "max_wait":
        return sorted(pairs, key=lambda t: t[1].wait_time if t[1].open_flag else 0, reverse=True)
    if sort_mode == "min_wait":
        return sorted(pairs, key=lambda t: t[1].wait_time if t[1].open_flag else 0)
    return sorted(pairs, key=lambda t: t[1].name.lower())


def _filter_rides(rides, skip_meet, skip_closed):
    out = []
    for ride in rides:
        if skip_meet and "Meet" in ride.name:
            continue
        if skip_closed and ride.is_open() is False:
            continue
        out.append(ride)
    return out


def _scroll_speed(settings):
    """Scroll speed in px/sec from the Scroll Speed setting (1/delay); falls back
    to the library default (30) if unavailable."""
    try:
        delay = settings.get_scroll_speed()
        if delay and delay > 0:
            return max(1, int(round(1.0 / delay)))
    except Exception:
        pass
    return 30


class _PaletteMessage(BitmapText):
    """BitmapText (palette-animated) made queue-safe for INFO MESSAGES. The library's
    BitmapText is a persistent banner — ``is_complete`` is always False (would freeze
    the cycle) and it doesn't rebuild after ``stop()`` detaches its layer. Here it
    completes after ~one scroll pass and rebuilds each time it is shown."""

    def __init__(self, text, *, palette_effect, scroll_speed, priority=2, y=_PALETTE_Y):
        speed = max(1, int(scroll_speed))
        super().__init__(text, y=y, palette_effect=palette_effect,
                         scroll_speed=speed,
                         max_width_px=max(64, len(text) * 6 + 6), priority=priority)
        self._show_for = (len(text) * 6 + 64) / speed + 0.5

    async def start(self):
        await super().start()
        self._built = False        # rebuild (re-add the layer) each time shown

    @property
    def is_complete(self):
        return self._is_complete or self.elapsed >= self._show_for


def _instantiate_scroller(name, text, color, speed, y):
    """A scrolling DisplayContent of the catalog class ``name`` (by name -> class)."""
    from scrollkit.effects import scrolling as _sc
    cls = getattr(_sc, name, None) or KineticMarquee
    try:
        return cls(text, y=y, color=color, speed=speed)
    except TypeError:        # unknown signature for a newly added scroller
        return KineticMarquee(text, y=y, color=color, speed=speed)


def _instantiate_palette(name, text, speed, y=_PALETTE_Y):
    """Palette-animated bitmap text using the catalog palette effect ``name``."""
    from scrollkit.display import bitmap_text as _bt
    eff_cls = getattr(_bt, name, None) or RainbowChase
    try:
        eff = eff_cls()
    except Exception:                       # new/changed palette class -> safe default
        eff = RainbowChase()
    return _PaletteMessage(text, palette_effect=eff, scroll_speed=speed, y=y)


def _plain_message(text, color, speed):
    """A message with NO text effect: a plain constant-speed ScrollingText. Use this
    (instead of _random_content) for any message that should never be animated. It
    still gets the scroll-safe wipe between screens; drop the ``_tpw_transition`` line
    if you want no screen transition into it either."""
    item = ScrollingText(text, y=_SCROLL_Y, color=color, speed=speed)
    item._tpw_transition = _TX_SCROLL
    item._tpw_effect = "plain"
    return item


def _random_content(text, color, speed, cat, rng):
    """One INFO MESSAGE line, effect + transition chosen at random from the live
    catalog. Scrollers (content_group) get a random transition; palette content
    (overlay) gets the overlay-safe wipe."""
    pool = cat.content_pool
    if not pool:
        item = KineticMarquee(text, y=_SCROLL_Y, color=color, speed=speed)
        item._tpw_transition = _TX_SCROLL
        item._tpw_effect = "KineticMarquee"
        return item
    kind, name = rng.choice(pool)
    if kind == "scroller":
        item = _instantiate_scroller(name, text, color, speed, _SCROLL_Y)
        item._tpw_transition = rng.choice(cat.transitions) if cat.transitions else _TX_SCROLL
    else:
        item = _instantiate_palette(name, text, speed)
        item._tpw_transition = _TX_SCROLL
    item._tpw_effect = name
    return item


def _name_scroller(ride_name, color, speed, cat, rng):
    """A random SCROLLING-category effect to render the ride NAME in the top zone —
    drawn from the FULL scrolling-tagged set (motion scrollers AND palette colour
    effects), so names get visibly varied effects, not just subtle motion. Returns
    (content, effect_name); (None, "plain") falls back to the built-in scroll."""
    pool = cat.content_pool
    if not pool:
        return None, "plain"
    kind, name = rng.choice(pool)
    if kind == "scroller":
        item = _instantiate_scroller(name, ride_name, color, speed, _NAME_Y)
    else:                              # palette colour effect, kept in the top zone
        item = _instantiate_palette(name, ride_name, speed, y=_NAME_PALETTE_Y)
    return item, name


def _add_ride(queue, ride, name_color, wait_color, wait_color_mode, speed, cat, rng,
              name_effect_on=True):
    """Add the dual-zone ride screen (layout unchanged): the NAME alternates between
    a random scrolling effect (``name_effect_on``) and a plain scroll so the board
    isn't busy; the large wait NUMBER always keeps its green->red severity colour and
    animates it (a random Rain/Swarm/sheen/pulse) below."""
    if name_effect_on:
        name_c, name_eff = _name_scroller(ride.name, _to_int_color(name_color), speed, cat, rng)
    else:
        name_c, name_eff = None, "plain"     # plain scroll — the built-in name renderer
    if ride.open_flag is True:
        wc = (_severity_color(ride.wait_time) if wait_color_mode == "severity"
              else _to_int_color(wait_color))
        num = rng.choice(_NUMBER_EFFECTS)        # Rain/Swarm reveal OR sheen/pulse colour
        if num in NUMBER_STYLES:
            content = RideScreenContent(ride.name, ride.wait_time, name_color=name_color,
                                        wait_color=wc, number_style=num, name_content=name_c)
        else:
            content = RideScreenContent(ride.name, ride.wait_time, name_color=name_color,
                                        wait_color=wc, effect=num, name_content=name_c)
        content._tpw_wait = ride.wait_time
        content._tpw_color = wc
        content._tpw_number_effect = num
    else:
        content = ClosedRideContent(ride.name, name_color=name_color, name_content=name_c)
        content._tpw_wait = None
        content._tpw_color = _to_int_color(wait_color)
        content._tpw_number_effect = None
    content._tpw_ride = ride.name
    content._tpw_name_effect = name_eff
    content._tpw_transition = _TX_RIDE
    queue.add(content)


def build_content_queue(queue, park_list, settings, vacation, *, include_splash=True, rng=None):
    """Populate ``queue`` (a ContentQueue) from the data + settings. Clears first.

    Effects + transitions are picked at random from the live ScrollKit catalog. Pass
    ``rng`` (e.g. ``random.Random(seed)``) for deterministic tests; defaults to the
    module ``random``.
    """
    queue.clear()
    if rng is None:
        rng = random
    cat = scrolling_catalog()

    default_color = _to_int_color(settings.get("default_color", "0xffff00"))
    name_color = settings.get("ride_name_color", "0x0000ff")
    wait_color = settings.get("ride_wait_time_color", "0xfdf5e6")
    domain = settings.get("domain_name", "themeparkwaits")
    speed = _scroll_speed(settings)

    # The opening reveal splash is played once at boot; include_splash kept for API
    # compatibility. Which parks to display (multi-park, else legacy single park).
    parks = list(getattr(park_list, "selected_parks", None) or [])
    if not parks and park_list and park_list.current_park.is_valid():
        parks = [park_list.current_park]

    if not parks:
        queue.add(_random_content("Choose theme park at http://%s.local" % domain,
                                  default_color, speed, cat, rng))
        return

    # "Configure at <domain>.local" is a plain message (no effect) so the setup URL
    # stays maximally legible. Swap _plain_message <-> _random_content per message to
    # turn effects off/on for any individual line.
    queue.add(_plain_message("Configure at http://%s.local" % domain,
                             default_color, speed))

    sort_mode = settings.get("sort_mode", "alphabetical")
    group_by_park = settings.get("group_by_park", False)
    skip_meet = settings.get("skip_meet", False)
    skip_closed = settings.get("skip_closed", False)
    wait_color_mode = settings.get("wait_color_mode", "severity")  # severity|fixed

    # The ride NAME effect alternates on/off across rides (every other ride scrolls
    # plain) so the board isn't busy; ride_i counts rides across all parks/groups.
    ride_i = 0
    if group_by_park:
        for park in parks:
            if park.is_open is False:
                queue.add(_random_content(park.name + " is closed",
                                          default_color, speed, cat, rng))
                continue
            queue.add(_random_content(park.name + " wait times...",
                                      default_color, speed, cat, rng))
            rides = _sort_rides(_filter_rides(park.rides, skip_meet, skip_closed), sort_mode)
            for ride in rides:
                _add_ride(queue, ride, name_color, wait_color, wait_color_mode, speed, cat, rng,
                          name_effect_on=(ride_i % 2 == 0))
                ride_i += 1
    else:
        combined = []
        for park in parks:
            if park.is_open:
                for ride in _filter_rides(park.rides, skip_meet, skip_closed):
                    combined.append((park.id, ride))
        for _park_id, ride in _sort_pairs(combined, sort_mode):
            _add_ride(queue, ride, name_color, wait_color, wait_color_mode, speed, cat, rng,
                      name_effect_on=(ride_i % 2 == 0))
            ride_i += 1

    # Vacation countdown.
    if vacation is not None and vacation.is_set():
        days = vacation.get_days_until()
        if days > 1:
            queue.add(_random_content("Vacation to %s in: %d days" % (vacation.name, days),
                                      default_color, speed, cat, rng))
        elif days == 1:
            queue.add(_random_content("Your vacation to %s is tomorrow!!!" % vacation.name,
                                      default_color, speed, cat, rng))
        elif days == 0:
            queue.add(_random_content("Your vacation to %s is TODAY!!!!!!!!!!!!!" % vacation.name,
                                      default_color, speed, cat, rng))

    # Attribution (required).
    park_names = ", ".join(p.name for p in parks)
    queue.add(_random_content("Wait times for %s provided by %s" % (park_names, REQUIRED_MESSAGE),
                              default_color, speed, cat, rng))

    # The swarm splash caps each full cycle, then the queue loops back to the start.
    queue.add(SplashContent())
