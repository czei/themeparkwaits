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
import random

from src.app import ThemeParkApp
from src.ui.ride_screen_content import RideScreenContent
from tests.conftest import MAGIC_KINGDOM_ID


async def test_refresh_status_clears_previous_wait_number_overlay(
        mock_http_client, settings_factory):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    random.seed(0)              # effects are randomized; make the rebuild deterministic

    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)

    await app._initialize_display()
    await app.setup()           # fetch park list (and play/clean up the splash)
    await app.update_data()     # initial refresh: fetch waits + build queue
    display = app.display

    # Put a ride on screen and render it so its wait-number reveal overlay attaches.
    # clear() schedules any prior content's deferred stop; prepare_display_content()
    # (get_current) flushes that and starts the ride, so the ride's own reveal is the
    # overlay we then expect a refresh to release.
    app.content_queue.clear()
    app.content_queue.add(RideScreenContent("Space Mountain", 35))
    content = await app.prepare_display_content()
    await display.clear()
    await content.render(display)
    await display.show()
    assert isinstance(content, RideScreenContent)
    assert content._reveal is not None, "ride should build its wait-number overlay"
    with_ride = len(display._layer_group)

    # A subsequent refresh paints "Updating / Times" before its blocking fetch. The
    # previous ride's overlay must be torn down first (else it ghosts over the frame).
    await app.update_data()

    assert len(display._layer_group) < with_ride, (
        "stale wait-number overlay still attached during the refresh status "
        "frame — it would ghost over 'Updating / Times' through the fetch")
