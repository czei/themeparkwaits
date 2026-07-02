"""Build the per-park roller-coaster map for ThemeParkWaits (desktop dev tool).

Ride type is NOT in the themeparks.wiki feed and ride names have no usable
pattern ("Space Mountain", "Guardians of the Galaxy: Cosmic Rewind", and
"VelociCoaster" are all coasters), so we classify offline with Claude + web
search and ship the result as src/data/coasters/<parkId>.json (a JSON list of
coaster attraction UUIDs). The device loads only the selected parks' small files.

This is a desktop-only dev tool (like tools/sim_shot.py) — it is NEVER bundled to
the board; only the emitted JSON data is. Re-run it to refresh as new coasters open.

Setup:
    pip install anthropic            # the SDK (no extra deps; themeparks via urllib)
    export ANTHROPIC_API_KEY=sk-...

Usage:
    # one or more specific parks (UUIDs from /v1/destinations)
    python tools/classify_rides.py --parks 47f90d2c-...,75ea578a-...
    # every park in the catalog (~139; costs more — uses Claude per park)
    python tools/classify_rides.py --all
    # cheaper model for the bulk pass (default is the most capable, claude-opus-4-8)
    python tools/classify_rides.py --all --model claude-sonnet-4-6

Copyright (c) 2024-2026 Michael Czeiszperger
"""
import argparse
import json
import os
import re
import sys
import urllib.request

API = "https://api.themeparks.wiki/v1"
OUT_DEFAULT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "src", "data", "coasters")

SYSTEM = (
    "You classify theme-park attractions as roller coasters. A ROLLER COASTER is a "
    "gravity- or launch-driven ride on a fixed track with hills, drops, or inversions "
    "— this INCLUDES mine trains, wild-mouse/spinning coasters, bobsleds, launched and "
    "family coasters, indoor/dark coasters (e.g. Space Mountain), and Omnicoasters "
    "(e.g. Guardians of the Galaxy: Cosmic Rewind). It does NOT include powered "
    "slot-car rides (e.g. Test Track), motion simulators (e.g. Soarin', Star Tours, "
    "Mission: SPACE), trackless or omnimover dark rides, log flumes / shoot-the-chutes, "
    "river rapids and other water rides, spinners, carousels, drop towers, or shows. "
    "Use web search to verify any ride you are unsure about before deciding."
)


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "themeparkwaits-classifier"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def all_parks():
    """Flatten /destinations to [(park_id, park_name, destination_name), ...]."""
    data = _get_json("%s/destinations" % API)
    out = []
    for dest in data.get("destinations", []):
        for p in dest.get("parks", []):
            out.append((p["id"], p.get("name", ""), dest.get("name", "")))
    return out


def park_attractions(park_id):
    """[(id, name), ...] of ATTRACTION entities for a park (from /live)."""
    data = _get_json("%s/entity/%s/live" % (API, park_id))
    return [(e["id"], e.get("name", "")) for e in data.get("liveData", [])
            if e.get("entityType") == "ATTRACTION" and e.get("id")]


def _extract_ids(text, valid_ids):
    """Pull the coaster id list from the model's reply, keeping only known ids."""
    m = re.search(r"<coasters>(.*?)</coasters>", text, re.DOTALL)
    blob = m.group(1) if m else text
    arr = re.search(r"\[.*\]", blob, re.DOTALL)
    if not arr:
        return []
    try:
        ids = json.loads(arr.group(0))
    except ValueError:
        return []
    return [i for i in ids if isinstance(i, str) and i in valid_ids]


def classify(client, model, park_name, attractions):
    """Return the subset of attraction ids that are roller coasters."""
    valid = {i for i, _ in attractions}
    listing = "\n".join("%s\t%s" % (i, n) for i, n in attractions)
    user = (
        "Park: %s\nAttractions (id<TAB>name):\n%s\n\n"
        "Return ONLY the ids that are roller coasters, as a JSON array of id strings "
        "wrapped in <coasters>...</coasters>. If none are coasters, return "
        "<coasters>[]</coasters>." % (park_name, listing)
    )
    messages = [{"role": "user", "content": user}]
    text_parts = []
    for _ in range(6):                      # bounded server-tool (pause_turn) loop
        resp = client.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}],
            messages=messages,
        )
        text_parts += [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break
    return _extract_ids("\n".join(text_parts), valid)


def main():
    ap = argparse.ArgumentParser(description="Build src/data/coasters/<parkId>.json via Claude + web search.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--parks", help="comma-separated park UUIDs")
    g.add_argument("--all", action="store_true", help="classify every park in the catalog")
    ap.add_argument("--model", default="claude-opus-4-8",
                    help="Claude model id (default claude-opus-4-8; sonnet/haiku are cheaper for bulk)")
    ap.add_argument("--out", default=OUT_DEFAULT, help="output dir (default src/data/coasters)")
    args = ap.parse_args()

    import anthropic
    client = anthropic.Anthropic()        # reads ANTHROPIC_API_KEY
    os.makedirs(args.out, exist_ok=True)

    catalog = {pid: name for pid, name, _ in all_parks()}
    if args.all:
        park_ids = list(catalog)
    else:
        park_ids = [p.strip() for p in args.parks.split(",") if p.strip()]

    for pid in park_ids:
        name = catalog.get(pid, pid)
        try:
            attractions = park_attractions(pid)
        except Exception as e:
            print("  !! %s (%s): fetch failed: %s" % (name, pid, e))
            continue
        if not attractions:
            print("  -- %s (%s): no attractions" % (name, pid))
            continue
        coasters = classify(client, args.model, name, attractions)
        path = os.path.join(args.out, "%s.json" % pid)
        with open(path, "w") as f:
            json.dump(sorted(coasters), f, indent=2)
        by_id = dict(attractions)
        print("  %s (%s): %d/%d coasters -> %s" % (name, pid, len(coasters), len(attractions), path))
        for cid in coasters:
            print("      coaster: %s" % by_id.get(cid, cid))


if __name__ == "__main__":
    main()
