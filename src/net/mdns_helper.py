"""mDNS hostname advertising (library gap — T017).

ScrollKit has no mDNS support, so advertising ``<domain_name>.local`` for the
config page stays app code. CircuitPython only; a no-op on desktop (and harmless
if the ``mdns`` module is unavailable). Verify on-device coexistence with the web
server's socket pool (R3 / hardware checklist T038).

Copyright 2024 3DUPFitters LLC
"""
from __future__ import annotations


def advertise(hostname, *, port=80):
    """Advertise ``<hostname>.local`` over mDNS and an HTTP service. Returns the
    mdns.Server on success, else None (dev/desktop or no radio)."""
    try:
        import wifi
        import mdns
    except ImportError:
        return None  # desktop / no CircuitPython mdns
    try:
        server = mdns.Server(wifi.radio)
        server.hostname = hostname
        server.advertise_service(service_type="_http", protocol="_tcp", port=port)
        print("mDNS advertising %s.local" % hostname)
        return server
    except Exception as e:  # never block boot on mDNS
        print("mDNS setup failed:", e)
        return None
