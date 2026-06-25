"""Regression: a settings change must not orphan the on-screen content's overlay.

A ride's wait number (Rain/Swarm reveal) is a persistent display LAYER, released
only by the content's ``stop()``. Changing a setting rebuilds the ContentQueue
TWICE in quick succession — the synchronous web handler's immediate rebuild, then
the scheduled data refresh's teardown (which calls ``get_current_content()``,
resurrecting ``_current_content``, then ``clear()`` again). With a single pending
slot the second rebuild clobbered the first's deferred ``stop()``, leaving the
old reveal's pixels (notably a half-finished Swarm) on screen forever.
"""
import asyncio

from scrollkit.display.content import ContentQueue


class _FakeContent:
    """Stands in for a RideScreenContent: stop() is what detaches its overlay."""

    def __init__(self, name):
        self.name = name
        self.started = False
        self.stopped = False
        self.is_complete = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def render(self, display):
        pass


def test_double_rebuild_still_stops_onscreen_content():
    async def scenario():
        q = ContentQueue()
        swarm = _FakeContent("swarm")          # the on-screen ride (mid Swarm reveal)
        q.add(swarm)
        assert await q.get_current() is swarm and swarm.started

        # 1) sync web handler / apply_settings: rebuild with the new color setting
        q.clear()
        q.add(_FakeContent("rain1"))

        # 2) scheduled refresh -> _teardown_active_content: get_current_content()
        #    resurrects _current_content, then clear() runs again (the clobber path)
        q.get_current_content()
        q.clear()
        rain2 = _FakeContent("rain2")
        q.add(rain2)

        # 3) display loop's next frame
        nxt = await q.get_current()
        assert swarm.stopped, "on-screen content never stopped -> overlay orphaned forever"
        assert nxt is rain2 and rain2.started

    asyncio.run(scenario())


def test_single_rebuild_unchanged():
    """The common single-rebuild path still stops exactly the outgoing content."""
    async def scenario():
        q = ContentQueue()
        a = _FakeContent("a")
        q.add(a)
        assert await q.get_current() is a
        q.clear()
        b = _FakeContent("b")
        q.add(b)
        assert await q.get_current() is b
        assert a.stopped and not b.stopped

    asyncio.run(scenario())
