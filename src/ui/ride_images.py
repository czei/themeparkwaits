"""Per-ride intro-image lookup (manifest -> file path; degrades to None on miss).

Mirrors ``ride_types``: a small JSON manifest maps a themeparks.wiki ride UUID to an
image filename under ``src/images/rides/``. Rides are matched STRICTLY by id — ride
names are not unique across parks ("Space Mountain" exists at several). MANY ids may
map to ONE file, so a single drawing serves the same ride at every park. A missing or
garbled manifest, an unmapped id, or a listed-but-absent file all yield ``None`` (the
ride just shows the normal screen — the intro is purely additive).

CircuitPython-safe: only ``json`` + ``OSError``/``ValueError``; the manifest is read
once and cached. ``_IMAGES_DIR`` is module-level (cwd-relative, like
``ride_types._DATA_DIR`` and ``config_server``'s static dir) so tests can repoint it.

Copyright (c) 2024-2026 Michael Winslow Czeiszperger
"""
import json

# Relative to the app's working directory (same convention as ride_types._DATA_DIR):
# on device and simulator, src/ lives under the cwd.
_IMAGES_DIR = "src/images/rides"
_MANIFEST_NAME = "manifest.json"

_manifest = None        # cached {ride_id: filename} dict (loaded once)


def _load_manifest():
    """The {ride_id: filename} map (empty if no/garbled manifest); cached."""
    global _manifest
    if _manifest is not None:
        return _manifest
    rides = {}
    try:
        with open("%s/%s" % (_IMAGES_DIR, _MANIFEST_NAME)) as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("rides"), dict):
            rides = data["rides"]
    except (OSError, ValueError):
        rides = {}
    _manifest = rides
    return rides


def lookup_intro_image(ride_id):
    """Path to ``ride_id``'s intro image, or ``None``.

    Returns ``None`` when there is no manifest entry for the id, or the mapped file
    does not exist on disk — so a half-finished manifest can never blank a ride.
    """
    if not ride_id:
        return None
    fname = _load_manifest().get(ride_id)
    if not fname:
        return None
    path = "%s/%s" % (_IMAGES_DIR, fname)
    try:                                   # existence check without `os` (CP-safe)
        f = open(path, "rb")
        f.close()
    except OSError:
        return None
    return path
