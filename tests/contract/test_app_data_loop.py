# Copyright (c) 2024-2026 Michael Czeiszperger
"""T022 — the wired app: setup() + update_data() populate the queue with rides."""
import os

from src.app import ThemeParkApp
from tests.conftest import MAGIC_KINGDOM_ID


async def test_app_boots_and_builds_ride_queue(mock_http_client, settings_factory):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from scrollkit.dev.harness import run_headless_async

    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)

    # warmup_data=True runs setup() (fetch park list) then one update_data() (fetch waits + build).
    res = await run_headless_async(app, frames=5, hardware=False, warmup_data=True)
    assert not res.errors, res.errors

    # Rides are scrolling content tagged with their ride name (any random effect).
    rides = [c for c in app.content_queue if getattr(c, "_tpw_ride", None)]
    names = {c._tpw_ride for c in rides}
    assert "Space Mountain" in names
    assert app.content_queue.get_content_count() > 0


async def test_refresh_preserves_rotation_position(mock_http_client, settings_factory):
    """A data refresh must NOT restart the rotation at the top.

    Rebuilding the queue calls ContentQueue.clear() (which resets _current_index to
    0). For a board whose full cycle outlasts update_interval — a big park, or a
    max_wait sort that parks every closed ride at the tail — that meant the tail was
    never reached before the next refresh restarted at the top, so the "Closed" rides
    never displayed. _fetch_and_build() must carry the rotation position across the
    rebuild instead. (Regression: closed rides invisible under max_wait sort.)
    """
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from scrollkit.dev.harness import run_headless_async
    from src.ui.ride_screen_content import ClosedRideContent

    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID],
                          skip_closed=False, sort_mode="max_wait")
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)
    res = await run_headless_async(app, frames=5, hardware=False, warmup_data=True)
    assert not res.errors, res.errors

    q = app.content_queue
    # The mock live data includes DOWN/CLOSED/REFURBISHMENT attractions, so closed
    # screens must be present in the queue (they were always built — the bug was that
    # the rotation never reached them).
    assert any(isinstance(c, ClosedRideContent) for c in q), "no closed rides in queue"

    # Simulate the rotation having advanced deep into the board (where the closed
    # rides live under max_wait), then refresh.
    deep = q.get_content_count() - 2
    assert deep > 0
    q._current_index = deep
    ok = await app._fetch_and_build()
    assert ok

    # The refresh must resume near where the rotation was, NOT snap back to 0.
    assert q._current_index == min(deep, q.get_content_count() - 1)
    assert q._current_index > 0, "refresh reset the rotation to the top (tail never shows)"
