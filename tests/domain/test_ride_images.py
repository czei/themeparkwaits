# Copyright (c) 2024-2026 Michael Czeiszperger
"""Per-ride intro-image lookup: reads the manifest, matches by id, degrades to None."""
import json
import os

import src.ui.ride_images as ride_images


def _point_at(tmp_path, monkeypatch):
    monkeypatch.setattr(ride_images, "_IMAGES_DIR", str(tmp_path))
    ride_images._manifest = None        # reset the module cache


def _write_manifest(tmp_path, rides):
    with open(os.path.join(str(tmp_path), "manifest.json"), "w") as f:
        json.dump({"version": 1, "rides": rides}, f)


def _touch(tmp_path, name):
    with open(os.path.join(str(tmp_path), name), "wb") as f:
        f.write(b"BM")                   # contents irrelevant; only existence is checked


def test_matches_by_uuid(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch)
    _write_manifest(tmp_path, {"uuid-mk": "space_mountain.bmp"})
    _touch(tmp_path, "space_mountain.bmp")
    assert ride_images.lookup_intro_image("uuid-mk") == "%s/space_mountain.bmp" % str(tmp_path)
    assert ride_images.lookup_intro_image("uuid-unknown") is None


def test_many_uuids_one_file(tmp_path, monkeypatch):
    # one drawing serves the same ride at multiple parks
    _point_at(tmp_path, monkeypatch)
    _write_manifest(tmp_path, {"mk": "space_mountain.bmp", "dlr": "space_mountain.bmp"})
    _touch(tmp_path, "space_mountain.bmp")
    a = ride_images.lookup_intro_image("mk")
    b = ride_images.lookup_intro_image("dlr")
    assert a == b == "%s/space_mountain.bmp" % str(tmp_path)


def test_listed_but_missing_file_is_none(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch)
    _write_manifest(tmp_path, {"mk": "space_mountain.bmp"})   # no file on disk
    assert ride_images.lookup_intro_image("mk") is None


def test_missing_or_garbled_manifest_is_none(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch)
    # no manifest at all
    assert ride_images.lookup_intro_image("mk") is None
    # garbled JSON -> None, never raises
    ride_images._manifest = None
    with open(os.path.join(str(tmp_path), "manifest.json"), "w") as f:
        f.write("{not json")
    assert ride_images.lookup_intro_image("mk") is None


def test_empty_id_is_none(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch)
    _write_manifest(tmp_path, {"mk": "space_mountain.bmp"})
    _touch(tmp_path, "space_mountain.bmp")
    assert ride_images.lookup_intro_image("") is None
    assert ride_images.lookup_intro_image(None) is None
