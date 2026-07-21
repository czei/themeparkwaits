"""Per-park roller-coaster lookup (precomputed map; built by tools/classify_rides.py).

Ride type is NOT in the themeparks.wiki feed, and ride names have no usable pattern
("Space Mountain" and "Guardians of the Galaxy: Cosmic Rewind" are both coasters),
so coasters are classified offline and shipped as ``src/data/coasters/<parkId>.json``
— a JSON list of attraction UUIDs. At runtime only the selected parks' files are
loaded, so device RAM holds a few small sets, never the whole catalog.

CircuitPython-safe: only ``json`` + ``OSError``/``ValueError``. A missing or garbled
file yields an empty set (every ride name scrolls plain) rather than raising.

Copyright (c) 2024-2026 Michael Czeiszperger
"""
import json

# Relative to the app's working directory (same convention as config_server's
# static_dir="src/www"): on device and simulator, src/ lives under the cwd.
_DATA_DIR = "src/data/coasters"

_cache = {}


def coaster_ids(park_id):
    """The set of coaster attraction UUIDs for ``park_id`` (empty if none/unknown)."""
    if not park_id:
        return frozenset()
    cached = _cache.get(park_id)
    if cached is not None:
        return cached
    ids = frozenset()
    try:
        with open("%s/%s.json" % (_DATA_DIR, park_id)) as f:
            data = json.load(f)
        if isinstance(data, list):
            ids = frozenset(str(x) for x in data)
    except (OSError, ValueError):
        ids = frozenset()
    _cache[park_id] = ids
    return ids


def is_coaster(ride_id, park_id):
    """True if attraction ``ride_id`` is a roller coaster in ``park_id``."""
    return bool(ride_id) and ride_id in coaster_ids(park_id)
