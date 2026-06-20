"""ThemeParkWaits application — built on the refactored ScrollKit library.

Port milestone A (in progress). This is the walking skeleton: a
``ScrollKitApp`` subclass that boots and renders a splash + placeholder message
on the simulator (and, on device, the LED matrix). Subsystems (settings, WiFi,
HTTP, theme-park data, the ride screen, the web config server, OTA) are layered
in by their respective tasks — see specs/001-this-project-is/tasks.md.

Copyright 2024 3DUPFitters LLC
"""
from __future__ import annotations

from scrollkit.app.base import ScrollKitApp
from scrollkit.display.content import StaticText, ScrollingText


class ThemeParkApp(ScrollKitApp):
    """Theme-park wait-time display application.

    The library's ``run()`` calls ``setup()`` once and then spawns the
    display / data-update / web processes (the latter two are memory-gated).
    See the "Boot Lifecycle" section of plan.md for how the pre-run state
    machine in ``setup()`` is being filled in across Milestone A.
    """

    # Display geometry / color depth for the Matrix Portal S3. bit_depth=4 is the
    # library's recommended (~3x-faster refresh) setting — keep it (FR-022).
    WIDTH = 64
    HEIGHT = 32
    BIT_DEPTH = 4

    def __init__(self, *, enable_web: bool = False, update_interval: int = 300) -> None:
        # enable_web defaults False until the config server lands (T023). The
        # 5-minute (300s) refresh cadence matches the pre-port behavior.
        super().__init__(enable_web=enable_web, update_interval=update_interval)

    async def create_display(self):
        """Return the library's unified display (auto-detects sim vs hardware)."""
        from scrollkit.display.unified import UnifiedDisplay
        return UnifiedDisplay(width=self.WIDTH, height=self.HEIGHT, bit_depth=self.BIT_DEPTH)

    async def setup(self) -> None:
        """Pre-run setup. Skeleton: title the sim window and queue placeholder content.

        Milestone A fills this in as the boot state machine (splash/reveal →
        WiFi/onboarding → OTA → NTP → fetch → build queue).
        """
        # Name the simulator window when running on desktop.
        if hasattr(self.display, "create_window"):
            try:
                await self.display.create_window("ThemeParkWaits (port skeleton)")
            except Exception:
                pass

        # Placeholder content so the loop has something to render. The real
        # splash uses scrollkit.effects.reveal.RevealEffect (T020/T021).
        self.content_queue.add(StaticText("THEME PARK", x=2, y=4, color=0xFFAA00, duration=2.0))
        self.content_queue.add(StaticText("WAITS", x=14, y=18, color=0xFFAA00, duration=2.0))
        self.content_queue.add(
            ScrollingText("Porting to ScrollKit...", y=12, color=0x00AAFF)
        )

    async def update_data(self) -> None:
        """Periodic data refresh — wired to ThemeParkService + ContentBuilder in T019/T021/T022."""
        # No-op until the data path lands.
        return None
