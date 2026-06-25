"""Builds the display ContentQueue from theme-park data + settings (T021).

This is the domain ordering logic ported from the old ``MessageQueue`` — sort /
group-by-park / skip filters / multi-park / vacation countdown / attribution —
but instead of calling ``display.show_*`` methods it emits library content
objects (``RideScreenContent`` / ``ClosedRideContent`` / ``ScrollingText`` /
``StaticText``) into a ``scrollkit.display.content.ContentQueue``.

Parity note (matches the old app): the wait-vs-"Closed" *display* choice is keyed
on ``ride.open_flag`` (an open ride with a 0 wait still shows "0"); the
``is_open()`` rule (open_flag AND wait>0) governs the skip-closed *filter* and the
wait-time *sort* weight.

Copyright 2024 3DUPFitters LLC
"""
from __future__ import annotations

from scrollkit.display.content import ScrollingText
from src.ui.reveal_splash import SplashContent
from src.ui.ride_screen_content import RideScreenContent, ClosedRideContent, _to_int_color

REQUIRED_MESSAGE = "ThemeParks.wiki"

# draw_text's y is the text BASELINE (top-down origin; y=0 clips the glyph off the
# top). Mid-teens vertically centers a single line on the 32px panel.
_SCROLL_Y = 13

# Wait-number severity coloring (wait_color_mode="severity"): minutes -> color,
# green (short) through red (long). Channels stick to 4-bit-clean values
# (0x00/0x80/0xc0/0xff) so they survive the bit_depth=4 panel. Thresholds are
# inclusive upper bounds.
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
    # alphabetical (default)
    return sorted(rides, key=lambda r: r.name.lower())


def _filter_rides(rides, skip_meet, skip_closed):
    out = []
    for ride in rides:
        if skip_meet and "Meet" in ride.name:
            continue
        if skip_closed and ride.is_open() is False:
            continue
        out.append(ride)
    return out


def _scroll_step(settings):
    """Ride-name scroll speed in pixels/frame from the Scroll Speed setting.

    The library maps Slow/Medium/Fast to a per-step DELAY in seconds
    ({Slow:0.06, Medium:0.04, Fast:0.02}); convert to px/frame against the display
    loop's ~20 FPS so the setting actually changes on-screen speed (Slow≈0.83,
    Medium≈1.25, Fast≈2.5 px/frame). Falls back to 1.0 if unavailable.
    """
    try:
        from scrollkit.display.content import LOOP_FPS
        delay = settings.get_scroll_speed()
        if delay and delay > 0:
            return (1.0 / LOOP_FPS) / delay
    except Exception:
        pass
    return 1.0


def _scroll_speed(settings):
    """Info-message scroll speed in px/sec from the Scroll Speed setting.

    ScrollingText now honors ``speed`` (px/sec); ``1/delay`` matches the ride-name
    pace (``_scroll_step`` px/frame * LOOP_FPS), so all scrolling moves together.
    Falls back to the library default (30) if the setting is unavailable.
    """
    try:
        delay = settings.get_scroll_speed()
        if delay and delay > 0:
            return max(1, int(round(1.0 / delay)))
    except Exception:
        pass
    return 30


def _add_ride(queue, ride, name_color, wait_color, scroll_step=1.0, wait_effect="Rain",
              wait_color_mode="severity"):
    if ride.open_flag is True:
        wc = _severity_color(ride.wait_time) if wait_color_mode == "severity" else wait_color
        queue.add(RideScreenContent(ride.name, ride.wait_time,
                                    name_color=name_color, wait_color=wc,
                                    scroll_step=scroll_step, effect=wait_effect))
    else:
        queue.add(ClosedRideContent(ride.name, name_color=name_color,
                                    scroll_step=scroll_step))


def build_content_queue(queue, park_list, settings, vacation, *, include_splash=True):
    """Populate ``queue`` (a ContentQueue) from the data + settings. Clears first."""
    queue.clear()

    default_color = _to_int_color(settings.get("default_color", "0xffff00"))
    name_color = settings.get("ride_name_color", "0x0000ff")
    wait_color = settings.get("ride_wait_time_color", "0xfdf5e6")
    domain = settings.get("domain_name", "themeparkwaits")
    msg_speed = _scroll_speed(settings)   # info-message scroll px/sec (Scroll Speed)

    # The opening reveal splash is played once at boot (app.setup → show_reveal_splash),
    # so it is intentionally not part of the repeating content cycle. include_splash
    # is kept for API compatibility.

    # Which parks to display (multi-park, else legacy single current_park).
    parks = list(getattr(park_list, "selected_parks", None) or [])
    if not parks and park_list and park_list.current_park.is_valid():
        parks = [park_list.current_park]

    if not parks:
        queue.add(ScrollingText("Choose theme park at http://%s.local" % domain,
                                y=_SCROLL_Y, color=default_color, speed=msg_speed))
        return

    queue.add(ScrollingText("Configure at http://%s.local" % domain,
                            y=_SCROLL_Y, color=default_color, speed=msg_speed))

    sort_mode = settings.get("sort_mode", "alphabetical")
    group_by_park = settings.get("group_by_park", False)
    skip_meet = settings.get("skip_meet", False)
    skip_closed = settings.get("skip_closed", False)
    step = _scroll_step(settings)   # ride-name scroll px/frame from Scroll Speed
    wait_effect = settings.get("wait_time_effect", "Rain")  # wait-number reveal style
    wait_color_mode = settings.get("wait_color_mode", "severity")  # severity|fixed

    if group_by_park:
        for park in parks:
            if park.is_open is False:
                queue.add(ScrollingText(park.name + " is closed",
                                        y=_SCROLL_Y, color=default_color, speed=msg_speed))
                continue
            queue.add(ScrollingText(park.name + " wait times...",
                                    y=_SCROLL_Y, color=default_color, speed=msg_speed))
            rides = _sort_rides(_filter_rides(park.rides, skip_meet, skip_closed), sort_mode)
            for ride in rides:
                _add_ride(queue, ride, name_color, wait_color, step, wait_effect, wait_color_mode)
    else:
        combined = []
        for park in parks:
            if park.is_open:
                combined.extend(_filter_rides(park.rides, skip_meet, skip_closed))
        for ride in _sort_rides(combined, sort_mode):
            _add_ride(queue, ride, name_color, wait_color, step, wait_effect, wait_color_mode)

    # Vacation countdown.
    if vacation is not None and vacation.is_set():
        days = vacation.get_days_until()
        if days > 1:
            queue.add(ScrollingText("Vacation to %s in: %d days" % (vacation.name, days),
                                    y=_SCROLL_Y, color=default_color, speed=msg_speed))
        elif days == 1:
            queue.add(ScrollingText("Your vacation to %s is tomorrow!!!" % vacation.name,
                                    y=_SCROLL_Y, color=default_color, speed=msg_speed))
        elif days == 0:
            queue.add(ScrollingText("Your vacation to %s is TODAY!!!!!!!!!!!!!" % vacation.name,
                                    y=_SCROLL_Y, color=default_color, speed=msg_speed))

    # Attribution (required).
    park_names = ", ".join(p.name for p in parks)
    queue.add(ScrollingText("Wait times for %s provided by %s" % (park_names, REQUIRED_MESSAGE),
                            y=_SCROLL_Y, color=default_color, speed=msg_speed))

    # The swarm splash CAPS each full cycle: it plays after all wait times (and the
    # attribution) have shown, then the queue loops back to the start. Same look as
    # the boot splash (reveal_splash).
    queue.add(SplashContent())
