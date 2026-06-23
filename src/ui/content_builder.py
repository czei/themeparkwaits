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
from src.ui.ride_screen_content import RideScreenContent, ClosedRideContent, _to_int_color

REQUIRED_MESSAGE = "queue-times.com"

# draw_text's y is the text BASELINE (top-down origin; y=0 clips the glyph off the
# top). Mid-teens vertically centers a single line on the 32px panel.
_SCROLL_Y = 13


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


def _add_ride(queue, ride, name_color, wait_color, scroll_step=1.0):
    if ride.open_flag is True:
        queue.add(RideScreenContent(ride.name, ride.wait_time,
                                    name_color=name_color, wait_color=wait_color,
                                    scroll_step=scroll_step))
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

    # The opening reveal splash is played once at boot (app.setup → show_reveal_splash),
    # so it is intentionally not part of the repeating content cycle. include_splash
    # is kept for API compatibility.

    # Which parks to display (multi-park, else legacy single current_park).
    parks = list(getattr(park_list, "selected_parks", None) or [])
    if not parks and park_list and park_list.current_park.is_valid():
        parks = [park_list.current_park]

    if not parks:
        queue.add(ScrollingText("Choose theme park at http://%s.local" % domain,
                                y=_SCROLL_Y, color=default_color))
        return

    queue.add(ScrollingText("Configure at http://%s.local" % domain, y=_SCROLL_Y, color=default_color))

    sort_mode = settings.get("sort_mode", "alphabetical")
    group_by_park = settings.get("group_by_park", False)
    skip_meet = settings.get("skip_meet", False)
    skip_closed = settings.get("skip_closed", False)
    step = _scroll_step(settings)   # ride-name scroll px/frame from Scroll Speed

    if group_by_park:
        for park in parks:
            if park.is_open is False:
                queue.add(ScrollingText(park.name + " is closed", y=_SCROLL_Y, color=default_color))
                continue
            queue.add(ScrollingText(park.name + " wait times...", y=_SCROLL_Y, color=default_color))
            rides = _sort_rides(_filter_rides(park.rides, skip_meet, skip_closed), sort_mode)
            for ride in rides:
                _add_ride(queue, ride, name_color, wait_color, step)
    else:
        combined = []
        for park in parks:
            if park.is_open:
                combined.extend(_filter_rides(park.rides, skip_meet, skip_closed))
        for ride in _sort_rides(combined, sort_mode):
            _add_ride(queue, ride, name_color, wait_color)

    # Vacation countdown.
    if vacation is not None and vacation.is_set():
        days = vacation.get_days_until()
        if days > 1:
            queue.add(ScrollingText("Vacation to %s in: %d days" % (vacation.name, days),
                                    y=_SCROLL_Y, color=default_color))
        elif days == 1:
            queue.add(ScrollingText("Your vacation to %s is tomorrow!!!" % vacation.name,
                                    y=_SCROLL_Y, color=default_color))
        elif days == 0:
            queue.add(ScrollingText("Your vacation to %s is TODAY!!!!!!!!!!!!!" % vacation.name,
                                    y=_SCROLL_Y, color=default_color))

    # Attribution (required).
    park_names = ", ".join(p.name for p in parks)
    queue.add(ScrollingText("Wait times for %s provided by %s" % (park_names, REQUIRED_MESSAGE),
                            y=_SCROLL_Y, color=default_color))
