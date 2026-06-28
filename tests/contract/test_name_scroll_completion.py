# Copyright (c) 2024-2026 Michael Winslow Czeiszperger
"""Regression: a palette-effect ride NAME completes when the text has scrolled fully
across (one FRAME-based pass), not on a wall-clock timer.

The bug: ``_PaletteMessage`` used to complete on ``elapsed >= _show_for`` (wall-clock).
The scroll itself is frame-based, so when a heavy concurrent effect — the swarm
wait-number, ~34 ms/frame — drops the frame rate, the wall-clock timer fired while the
name was only half-scrolled, advancing the ride and cutting the name off mid-scroll.
Completion is now keyed on the scroll position (one full pass), which is fps-independent.
"""
import os

from scrollkit.display.bitmap_text import MonoChase
from src.ui.content_builder import _PaletteMessage


async def test_palette_name_completes_on_scroll_not_wallclock():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from scrollkit.display.simulator import SimulatorDisplay

    async def frames_to_complete(starve_clock):
        disp = SimulatorDisplay(64, 32)
        await disp.initialize()
        msg = _PaletteMessage("SPACE MOUNTAIN", palette_effect=MonoChase(0x00AAFF),
                              scroll_speed=30)
        await msg.start()
        for f in range(600):
            if starve_clock:
                # Pretend a huge amount of wall-clock time has elapsed (what a slow
                # frame rate accumulates). A wall-clock completion would fire at once.
                msg._start_time -= 9999
            await disp.clear()
            await msg.render(disp)
            await disp.show()
            if msg.is_complete:
                return f
        return None

    normal = await frames_to_complete(starve_clock=False)
    starved = await frames_to_complete(starve_clock=True)

    assert normal is not None, "name never completed"
    assert normal > 30, "name completed before it could have scrolled across"
    # Wall-clock has NO bearing on completion: starving the clock doesn't end it early.
    assert normal == starved, "completion depends on wall-clock (the cut-off regression)"
