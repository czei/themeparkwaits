"""SplashContent: assemble -> hold -> complete, frame-cap, and overlay cleanup.

Drives the content with a fake SwarmReveal (patched in) so the completion/hold/
cap logic is tested without a real display or the slow flocking animation.
"""
import asyncio

from src.ui.reveal_splash import SplashContent


class _FakeSwarm:
    """Records lifecycle; completes after ``done_at`` steps (or never if None)."""
    last = None

    def __init__(self, pixels, **kw):
        self.pixels = pixels
        self.kw = kw
        self.started = False
        self.detached = False
        self.steps = 0
        self._complete = False
        self.done_at = 3
        _FakeSwarm.last = self

    def start(self, display):
        self.started = True

    @property
    def is_complete(self):
        return self._complete

    def step(self):
        self.steps += 1
        if self.done_at is not None and self.steps >= self.done_at:
            self._complete = True
        return self._complete

    def detach(self):
        self.detached = True


def _patch(monkeypatch):
    import scrollkit.effects.swarm_reveal as sr
    monkeypatch.setattr(sr, "SwarmReveal", _FakeSwarm)


def test_assembles_then_holds_then_completes(monkeypatch):
    _patch(monkeypatch)

    async def scenario():
        s = SplashContent(pixels=[(1, 1)], hold_seconds=0.1)   # hold_frames = 2
        await s.start()
        assert not s.is_complete
        for _ in range(50):
            await s.render(display=object())
            if s.is_complete:
                break
        assert s.is_complete
        assert _FakeSwarm.last.started
        assert _FakeSwarm.last.steps >= 3        # stepped through assembly
        await s.stop()
        assert _FakeSwarm.last.detached          # overlay released
        await s.start()                          # queue re-starts it next cycle
        assert not s.is_complete                 # reset, ready to play again

    asyncio.run(scenario())


def test_frame_cap_prevents_forever_hang(monkeypatch):
    _patch(monkeypatch)

    async def scenario():
        s = SplashContent(pixels=[(1, 1)], hold_seconds=0.0)
        s._max_frames = 5                         # never-completing swarm must still end
        await s.start()
        _FakeSwarm.last_done = None
        for _ in range(50):
            await s.render(display=object())
            # force the fake to never assemble
            if _FakeSwarm.last is not None:
                _FakeSwarm.last.done_at = None
            if s.is_complete:
                break
        assert s.is_complete                      # capped, not stuck

    asyncio.run(scenario())


def test_bad_reveal_completes_instead_of_wedging(monkeypatch):
    import scrollkit.effects.swarm_reveal as sr

    def _boom(*a, **k):
        raise RuntimeError("swarm unavailable")
    monkeypatch.setattr(sr, "SwarmReveal", _boom)

    async def scenario():
        s = SplashContent(pixels=[(1, 1)])
        await s.start()
        await s.render(display=object())
        assert s.is_complete                      # failed start -> advance, don't hang

    asyncio.run(scenario())
