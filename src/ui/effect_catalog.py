# Copyright (c) 2024-2026 Michael Czeiszperger
"""Runtime discovery of ScrollKit visual effects — never a hardcoded list.

ScrollKit tags every effect class with ``PAIRS_WITH`` ("static"/"scrolling"/
"fullscreen") and publishes a live catalog via ``scrollkit.dev.capabilities()``.
ThemeParkWaits content SCROLLS, so we query the catalog at runtime and keep only
the SCROLLING-tagged scrollers + palette effects (plus every full-screen
transition). When the library gains a new effect or changes a tag, the app picks
it up with zero code changes — exactly the point of querying instead of listing.

Three categories, kept separate (each is applied a different way):
  * transitions  -> full-screen swaps between screens (set as a transition name)
  * scrollers    -> scrolling DisplayContent classes (added to the content queue)
  * palettes     -> colour animations applied via ``BitmapText(palette_effect=)``

``capabilities()`` is desktop-oriented; if it can't be imported (e.g. on-device)
we read ``PAIRS_WITH`` straight off the effect classes — still dynamic, still no
hardcoded list.
"""
from __future__ import annotations


class EffectCatalog:
    """The scrolling-relevant slice of the live catalog (effect *names*)."""

    def __init__(self, transitions, scrollers, palettes, static_palettes=None):
        self.transitions = list(transitions)
        self.scrollers = list(scrollers)
        self.palettes = list(palettes)                 # palette effects tagged "scrolling"
        # Palette effects tagged "static" — the color animations for the (non-scrolling)
        # wait NUMBER. They're tagged both ways, so this usually equals ``palettes``,
        # but query the tag explicitly so name (scrolling) vs number (static) stay
        # category-correct if the catalog ever diversifies.
        self.static_palettes = list(static_palettes if static_palettes is not None
                                    else palettes)

    @property
    def content_pool(self):
        """``[("scroller", name) | ("palette", name)]`` — the ways to present one
        line of SCROLLING content (the ride name / a message), to pick at random."""
        return ([("scroller", n) for n in self.scrollers]
                + [("palette", n) for n in self.palettes])

    def __repr__(self):
        return ("EffectCatalog(transitions=%d, scrollers=%r, palettes=%r, static_palettes=%r)"
                % (len(self.transitions), self.scrollers, self.palettes, self.static_palettes))


def scrolling_catalog():
    """Return an :class:`EffectCatalog` for scrolling content, queried live."""
    cat = _from_capabilities()
    if cat is not None and (cat.scrollers or cat.palettes):
        return cat
    return _from_introspection()


def _from_capabilities():
    """Primary path: the published catalog (``scrollkit.dev.capabilities``)."""
    try:
        from scrollkit.dev import capabilities
        c = capabilities()
    except Exception:
        return None
    try:
        transitions = [t["name"] for t in c.get("transitions", []) if t.get("name")]
        scrollers = [e["name"] for e in c.get("scrolling", [])
                     if "scrolling" in (e.get("pairs_with") or ())]
        palettes = [e["name"] for e in c.get("palette_effects", [])
                    if "scrolling" in (e.get("pairs_with") or ())]
        static_palettes = [e["name"] for e in c.get("palette_effects", [])
                           if "static" in (e.get("pairs_with") or ())]
        return EffectCatalog(transitions, scrollers, palettes, static_palettes)
    except Exception:
        return None


def _from_introspection():
    """Device-safe fallback: read ``PAIRS_WITH`` off the live effect classes."""
    transitions, scrollers, palettes, static_palettes = [], [], [], []
    try:
        from scrollkit.effects.transitions import supported_names
        transitions = list(supported_names())
    except Exception:
        pass
    try:
        from scrollkit.effects import scrolling as _sc
        for nm in dir(_sc):
            cls = getattr(_sc, nm, None)
            if isinstance(cls, type) and "scrolling" in getattr(cls, "PAIRS_WITH", ()):
                scrollers.append(nm)
    except Exception:
        pass
    try:
        from scrollkit.display import bitmap_text as _bt
        for nm in dir(_bt):
            cls = getattr(_bt, nm, None)
            if not isinstance(cls, type):
                continue
            pw = getattr(cls, "PAIRS_WITH", ())
            if "scrolling" in pw:
                palettes.append(nm)
            if "static" in pw:
                static_palettes.append(nm)
    except Exception:
        pass
    return EffectCatalog(transitions, scrollers, palettes, static_palettes)
