# Copyright (c) 2024-2026 Michael Czeiszperger
"""Generate docs/ride-icons.md — a per-park ride checklist to fill in with a SIMPLE
visual representation for each ride (e.g. Jungle Cruise = a small boat; Haunted
Mansion = a ghost), which then drives drawing the intro images.

Idempotent: re-running MERGES the existing 'Representation' column (keyed by UUID), so
you never lose notes when Disney adds/renames rides. The 'Image' column auto-fills from
src/images/rides/manifest.json so progress is visible.

Desktop-only dev tool (network: themeparks.wiki). Usage:
    python tools/gen_ride_checklist.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classify_rides import park_attractions  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "docs", "ride-icons.md")
MANIFEST = os.path.join(REPO, "src", "images", "rides", "manifest.json")

# THEME parks only (water parks intentionally excluded).
PARKS = [
    ("Magic Kingdom", "75ea578a-adc8-4116-a54d-dccb60765ef9"),
    ("EPCOT", "47f90d2c-e191-4239-a466-5892ef59a88b"),
    ("Hollywood Studios", "288747d1-8b4f-4a64-867e-ea7c9b27bad8"),
    ("Animal Kingdom", "1c84a229-8862-4648-9c71-378ddd2c7693"),
    ("Disneyland Park", "7340550b-c14d-4def-80bb-acdb51d49a66"),
    ("Disney California Adventure", "832fcd51-ea19-4e77-85c7-75d5843b127c"),
    # Universal (non-water parks)
    ("Universal Studios Florida", "eb3f4560-2383-4a36-9152-6b3e5ed6bc57"),
    ("Universal Islands of Adventure", "267615cc-8943-4c2a-ae2c-5da728ca591f"),
    ("Universal Epic Universe", "12dbb85b-265f-44e6-bccf-f1faa17211fc"),
    ("Universal Studios Hollywood", "bc4005c5-8c7e-41d7-b349-cdddf1796427"),
    ("Universal Studios Japan", "47f61fac-7586-41ac-ae80-61c9257cf33e"),
    ("Universal Studios Singapore", "f95d7f76-2024-4510-b799-26e122d0e448"),
    ("Universal Studios Beijing", "68e1d8f0-ed42-4351-af25-160421e37ce0"),
]

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def load_manifest():
    try:
        with open(MANIFEST) as f:
            return json.load(f).get("rides", {})
    except (OSError, ValueError):
        return {}


def load_existing_reps(path):
    """uuid -> Representation text from a prior run (so re-gen preserves notes)."""
    reps = {}
    if not os.path.exists(path):
        return reps
    with open(path) as f:
        for line in f:
            parts = line.split("|")
            if len(parts) != 6:
                continue
            uuid = parts[4].strip().strip("`")
            if _UUID.match(uuid):
                reps[uuid] = parts[2].strip()
    return reps


def main():
    manifest = load_manifest()
    reps = load_existing_reps(OUT)

    body = []
    total = done = filled = 0
    for pname, pid in PARKS:
        body.append("\n## %s\n" % pname)
        try:
            rides = sorted(park_attractions(pid), key=lambda t: t[1].lower())
        except Exception as e:
            body.append("_fetch failed: %s_\n" % e)
            continue
        body.append("| Ride | Representation | Image | UUID |")
        body.append("|------|----------------|-------|------|")
        for uuid, name in rides:
            total += 1
            img = manifest.get(uuid, "")
            done += 1 if img else 0
            rep = reps.get(uuid, "")
            filled += 1 if rep else 0
            body.append("| %s | %s | %s | `%s` |" % (name.replace("|", "/"), rep, img, uuid))

    head = (
        "# Ride Icon Ideas\n\n"
        "_%d rides across %d theme parks · %d with images · %d representations filled in._\n\n"
        "Fill in **Representation** with a SIMPLE visual for each ride (e.g. Jungle Cruise "
        "= a small boat; Haunted Mansion = a ghost; Space Mountain = the spired cone). Then "
        "draw it and ship the BMP — see `docs/ride-intro-images.md`. The **Image** column "
        "auto-fills from the manifest. Avoid `|` in your notes (it breaks the table merge).\n\n"
        "Re-generate (preserves your notes, adds new rides): `python tools/gen_ride_checklist.py`\n"
        % (total, len(PARKS), done, filled)
    )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(head + "\n".join(body) + "\n")
    print("wrote %s  (%d rides, %d with images, %d notes preserved)" % (OUT, total, done, filled))


if __name__ == "__main__":
    main()
