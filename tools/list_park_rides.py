"""List a park's attractions as ``uuid<TAB>name`` (desktop dev tool).

Use this to pick which rides to draw intro images for and to grab the exact
themeparks.wiki UUID(s) to map in ``src/images/rides/manifest.json``. Reuses
``classify_rides.park_attractions`` (GET /v1/entity/{parkId}/live).

Usage:
    python tools/list_park_rides.py --park <parkUUID>
    python tools/list_park_rides.py --park <parkUUID> --grep "space"
    python tools/list_park_rides.py --list-parks            # dump all park UUIDs + names

Copyright (c) 2024-2026 Michael Winslow Czeiszperger
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classify_rides import park_attractions, all_parks  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="List a park's attractions (uuid<TAB>name).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--park", help="park UUID (from --list-parks or /v1/destinations)")
    g.add_argument("--list-parks", action="store_true", help="list every park UUID + name")
    ap.add_argument("--grep", default="", help="case-insensitive name filter")
    args = ap.parse_args()

    if args.list_parks:
        for pid, name, dest in sorted(all_parks(), key=lambda t: (t[2], t[1])):
            print("%s\t%s (%s)" % (pid, name, dest))
        return

    needle = args.grep.lower()
    rows = park_attractions(args.park)
    for rid, name in sorted(rows, key=lambda t: t[1].lower()):
        if needle and needle not in name.lower():
            continue
        print("%s\t%s" % (rid, name))


if __name__ == "__main__":
    main()
