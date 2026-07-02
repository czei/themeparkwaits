# Copyright (c) 2024-2026 Michael Winslow Czeiszperger
"""Boot-time WiFi onboarding policy (_connect_wifi / _run_wifi_onboarding).

The library owns the setup portal (AP + phone page + settings.json write); the
app only decides WHEN to run it. These tests pin that decision with a mock
WiFiManager — no real radio, no real server, no reboot:

* a successful join never touches the portal;
* a failed join with NO credentials (first boot) opens the portal indefinitely,
  with the app's display object;
* a failed join with KNOWN credentials retries as a station first (the
  power-outage self-heal), then falls back to the portal, and reboots on a
  portal timeout so a slow-to-return router reconnects next boot.
"""
from src.app import ThemeParkApp


class _FakeWiFi:
    """Stand-in for scrollkit.network.WiFiManager (only what onboarding calls)."""

    def __init__(self, *, ssid="", connect_results=(False,), portal_saved=False):
        self.ssid = ssid
        self._connect_results = list(connect_results)
        self.portal_saved = portal_saved
        self.connect_calls = 0
        self.portal_calls = []   # each entry: {"display":..., "timeout_s":...}
        self.reset_calls = 0

    async def connect(self, display_callback=None):
        self.connect_calls += 1
        return self._connect_results.pop(0) if self._connect_results else False

    async def run_setup_portal(self, display=None, *, port=80, reboot=True,
                               timeout_s=None):
        self.portal_calls.append({"display": display, "timeout_s": timeout_s})
        return self.portal_saved

    async def reset(self):
        self.reset_calls += 1


def _app(settings_factory, mock_http_client):
    """A ThemeParkApp with a sentinel display and status draws stubbed out.

    _status is defensive display drawing we don't want in these logic tests, and
    a plain sentinel display lets us assert the exact object handed to the portal.
    """
    app = ThemeParkApp(http_client=mock_http_client, settings=settings_factory())
    app.display = object()                       # sentinel identity for the assert

    async def _noop_status(*a, **k):
        return None
    app._status = _noop_status
    return app


async def test_successful_connect_skips_onboarding(settings_factory, mock_http_client):
    """A join that succeeds must never open the setup portal or reboot."""
    app = _app(settings_factory, mock_http_client)
    wm = _FakeWiFi(connect_results=[True])

    connected = await app._connect_wifi(wm)

    assert connected is True
    assert wm.connect_calls == 1
    assert wm.portal_calls == [], "portal must not run when the join succeeds"
    assert wm.reset_calls == 0


async def test_first_boot_no_creds_holds_portal_indefinitely(settings_factory, mock_http_client):
    """No credentials (first boot): open the portal once, with the app's display,
    and with NO timeout (wait for the user); do not reboot."""
    app = _app(settings_factory, mock_http_client)
    wm = _FakeWiFi(ssid="", connect_results=[False])

    connected = await app._connect_wifi(wm)

    assert connected is False
    assert len(wm.portal_calls) == 1, "portal should run exactly once"
    call = wm.portal_calls[0]
    assert call["display"] is app.display, "portal must get the app's display"
    assert call["timeout_s"] is None, "first boot waits indefinitely for setup"
    assert wm.reset_calls == 0, "nothing to reboot for with no credentials"


async def test_known_creds_self_heal_on_retry_no_portal(settings_factory, mock_http_client):
    """Known creds + a transient outage: a station retry that reconnects (a router
    coming back after a power blip) must NOT open the portal or reboot."""
    app = _app(settings_factory, mock_http_client)
    app.WIFI_RECONNECT_BACKOFF_S = (0, 0, 0)     # no real sleeping in tests
    # First connect (in _connect_wifi) fails; the first retry round succeeds.
    wm = _FakeWiFi(ssid="HomeNet", connect_results=[False, True])

    connected = await app._connect_wifi(wm)

    assert connected is True
    assert wm.connect_calls == 2, "one initial join + one successful retry"
    assert wm.portal_calls == [], "a recovered router needs no portal"
    assert wm.reset_calls == 0, "and no reboot"


async def test_known_creds_all_retries_fail_portal_then_reboot(settings_factory, mock_http_client):
    """Known creds that never reconnect: after the retries, open the portal with a
    bounded timeout; on a timeout (nobody saved) reboot so a slow router recovers."""
    app = _app(settings_factory, mock_http_client)
    app.WIFI_RECONNECT_BACKOFF_S = (0, 0)        # two quick retry rounds
    wm = _FakeWiFi(ssid="HomeNet", connect_results=[False], portal_saved=False)

    connected = await app._connect_wifi(wm)

    assert connected is False
    assert wm.connect_calls == 1 + 2, "initial join + two retry rounds"
    assert len(wm.portal_calls) == 1
    assert wm.portal_calls[0]["display"] is app.display
    assert wm.portal_calls[0]["timeout_s"] == app.WIFI_PORTAL_TIMEOUT_S
    assert wm.reset_calls == 1, "portal timed out with no save -> reboot to retry"


async def test_known_creds_portal_save_does_not_double_reboot(settings_factory, mock_http_client):
    """When the portal SAVES, the library reboots itself — onboarding must not also
    call reset() (a double reboot)."""
    app = _app(settings_factory, mock_http_client)
    app.WIFI_RECONNECT_BACKOFF_S = ()            # skip straight to the portal
    wm = _FakeWiFi(ssid="HomeNet", connect_results=[False], portal_saved=True)

    connected = await app._connect_wifi(wm)

    assert connected is False
    assert len(wm.portal_calls) == 1
    assert wm.reset_calls == 0, "library reboots on save; don't reboot twice"


async def test_init_network_is_noop_off_device(settings_factory, mock_http_client):
    """Desktop safety: _init_network must return before ever constructing a
    WiFiManager, so the setup portal can never fire during a desktop/sim run."""
    app = ThemeParkApp(http_client=mock_http_client, settings=settings_factory())
    await app._init_network()
    assert getattr(app, "wifi", None) is None, \
        "off-device boot must not bring up WiFi (portal must never trigger)"
