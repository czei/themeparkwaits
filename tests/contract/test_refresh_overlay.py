"""Regression: a data refresh must not leave the previous ride's wait-number
overlay ghosting on top of the "Updating / Times" status frame.

The large wait number is a persistent display *layer* (DripReveal/SwarmReveal in
the display's layer group), which the per-frame ``display.clear()`` deliberately
leaves untouched so an effect can span frames. ``update_data()`` paints the
"Updating / Times" status frame and then makes a *blocking* fetch (the display
loop is frozen for its duration). If the refresh doesn't tear the previous ride's
overlay down first, the old wait number stays lit on top of "Updating / Times"
for the whole fetch — the reported bug.
"""
import os

from src.app import ThemeParkApp
from src.ui.ride_screen_content import RideScreenContent
from tests.conftest import MAGIC_KINGDOM_ID


async def test_refresh_status_clears_previous_wait_number_overlay(
        mock_http_client, settings_factory):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)

    await app._initialize_display()
    await app.setup()           # fetch park list (and play/clean up the splash)
    await app.update_data()     # initial refresh: fetch waits + build queue
    display = app.display

    # Persistent layers unrelated to a ride (e.g. a paint canvas) may exist; take
    # a baseline and assert against it so the test isolates the ride overlay.
    baseline = len(display._layer_group)

    # Put a ride on screen and render it once so its wait-number reveal overlay
    # attaches to the display's layer group (this is the state at refresh time).
    app.content_queue.clear()
    app.content_queue.add(RideScreenContent("Space Mountain", 35))
    content = await app.prepare_display_content()
    await display.clear()
    await content.render(display)
    await display.show()
    assert isinstance(content, RideScreenContent)
    assert len(display._layer_group) > baseline, (
        "ride wait-number overlay should be attached after rendering it")

    # A subsequent refresh paints "Updating / Times" before its blocking fetch.
    # The previous ride's overlay must be gone by the time that frame is up.
    await app.update_data()

    assert len(display._layer_group) == baseline, (
        "stale wait-number overlay still attached during the refresh status "
        "frame — it would ghost over 'Updating / Times' through the fetch")
