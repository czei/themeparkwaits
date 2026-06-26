"""Per-park coaster lookup: reads the map, caches, degrades to empty on miss."""
import json
import os

import src.ui.ride_types as ride_types


def _point_at(tmp_path, monkeypatch):
    monkeypatch.setattr(ride_types, "_DATA_DIR", str(tmp_path))
    ride_types._cache.clear()


def test_reads_coaster_ids(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch)
    pid = "park-1"
    with open(os.path.join(str(tmp_path), pid + ".json"), "w") as f:
        json.dump(["uuid-a", "uuid-b"], f)
    ids = ride_types.coaster_ids(pid)
    assert ids == {"uuid-a", "uuid-b"}
    assert ride_types.is_coaster("uuid-a", pid)
    assert not ride_types.is_coaster("uuid-z", pid)


def test_missing_or_bad_file_is_empty(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch)
    assert ride_types.coaster_ids("no-such-park") == frozenset()
    # garbled JSON -> empty, never raises
    bad = os.path.join(str(tmp_path), "park-bad.json")
    with open(bad, "w") as f:
        f.write("{not json")
    assert ride_types.coaster_ids("park-bad") == frozenset()
    assert not ride_types.is_coaster("anything", "park-bad")


def test_empty_inputs(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch)
    assert ride_types.coaster_ids("") == frozenset()
    assert not ride_types.is_coaster("", "park-1")
    assert not ride_types.is_coaster("uuid-a", "")
