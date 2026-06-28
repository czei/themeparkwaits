# Copyright (c) 2024-2026 Michael Winslow Czeiszperger
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
