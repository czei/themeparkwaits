"""T022 — the wired app: setup() + update_data() populate the queue with rides."""
import os

from src.app import ThemeParkApp
from src.ui.ride_screen_content import RideScreenContent


async def test_app_boots_and_builds_ride_queue(mock_http_client, settings_factory):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from scrollkit.dev.harness import run_headless_async

    sm = settings_factory(selected_park_ids=[6])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)

    # warmup_data=True runs setup() (fetch park list) then one update_data() (fetch waits + build).
    res = await run_headless_async(app, frames=5, hardware=False, warmup_data=True)
    assert not res.errors, res.errors

    rides = [c for c in app.content_queue if isinstance(c, RideScreenContent)]
    names = {c.ride_name for c in rides}
    assert "Space Mountain" in names
    assert app.content_queue.get_content_count() > 0
