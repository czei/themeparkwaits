"""Configuration web UI for ThemeParkWaits (T023–T025).

The library (`scrollkit.web`) provides the server, request loop, and platform
adapter (adafruit_httpserver on device / http.server on desktop) but no default
config UI — that page + routes are product-specific (a documented gap). This
builds a `WebHandler` subclass bound to the running app: it renders the settings
form (pre-filled, with the live park list) and applies POSTed changes to the
`SettingsManager`, then rebuilds the display content queue (no network fetch —
FR-004).

Routes (per contracts/web-config-routes.md): GET `/` + GET/POST `/settings`,
GET `/style.css` (served from `src/www`), POST `/update` (schedule OTA — T027).

Note: the adapter exposes one value per form key, so multi-park selection uses
four distinct `park_1..park_4` dropdowns rather than a repeated field.

Copyright 2024 3DUPFitters LLC
"""
from __future__ import annotations

from scrollkit.web.handlers import StaticFileHandler
from scrollkit.web.adapters import route

from src.ui.content_builder import build_content_queue

SORT_MODES = ("alphabetical", "max_wait", "min_wait")
SCROLL_SPEEDS = ("Slow", "Medium", "Fast")
MAX_PARKS = 4


def _hex_to_html(color) -> str:
    """'0x0000ff' / 0x0000ff -> '#0000ff' for an <input type=color>."""
    try:
        val = int(color, 16) if isinstance(color, str) else int(color)
    except (TypeError, ValueError):
        return "#ffffff"
    return "#%06x" % (val & 0xFFFFFF)


def _html_to_hex(value) -> str:
    """'#0000ff' -> '0x0000ff' for storage (matches the app's color format)."""
    if isinstance(value, str) and value.startswith("#") and len(value) == 7:
        return "0x" + value[1:].lower()
    return value


def _esc(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def make_handler_class(app):
    """Return a WebHandler subclass bound to ``app`` (settings + content rebuild)."""

    class ThemeParkConfigHandler(StaticFileHandler):
        # bound app (the adapter only passes itself to __init__)
        _app = app

        # ---- routes ----
        @route("/")
        def route_index(self, request):
            return self.create_response(self._render_page())

        @route("/settings", methods=["GET", "POST"])
        def route_settings(self, request):
            params = request.form_data or request.query_params or {}
            if params:
                self._apply(params)
                return self.create_redirect_response(
                    "Settings saved", status="success", redirect_url="/")
            return self.create_response(self._render_page())

        @route("/update", methods=["POST"])
        def route_update(self, request):
            # OTA wiring lands in T027; acknowledge the request for now.
            scheduled = False
            ota = getattr(self._app, "ota", None)
            if ota is not None and hasattr(ota, "schedule_update"):
                try:
                    scheduled = bool(ota.schedule_update())
                except Exception:
                    scheduled = False
            msg = ("Update scheduled — rebooting to install."
                   if scheduled else "Update check is not available yet.")
            return self.create_redirect_response(
                msg, status="info" if scheduled else "warning", redirect_url="/")

        # ---- apply settings ----
        def _apply(self, params):
            sm = self._app.settings
            svc = self._app.service

            # Park selection (park_1..park_4 -> selected_park_ids).
            ids = []
            for i in range(1, MAX_PARKS + 1):
                raw = params.get("park_%d" % i, "").strip()
                if raw:
                    try:
                        pid = int(raw)
                    except ValueError:
                        continue
                    if pid > 0 and pid not in ids:
                        ids.append(pid)
            if ids:
                sm.set("selected_park_ids", ids)
                sm.set("current_park_id", ids[0])

            # Scalars.
            for key in ("sort_mode", "scroll_speed", "domain_name"):
                if key in params and params[key]:
                    sm.set(key, params[key])
            if "brightness_scale" in params:
                sm.set("brightness_scale", params["brightness_scale"])
            for key in ("default_color", "ride_name_color", "ride_wait_time_color"):
                if key in params:
                    sm.set(key, _html_to_hex(params[key]))

            # Booleans: an unchecked box is simply absent from the form.
            for key in ("group_by_park", "skip_closed", "skip_meet"):
                sm.set(key, key in params)

            # Vacation.
            if "next_visit" in params:
                sm.set("next_visit", params.get("next_visit", ""))
                for k in ("next_visit_year", "next_visit_month", "next_visit_day"):
                    try:
                        sm.set(k, int(params.get(k, 0)))
                    except (TypeError, ValueError):
                        pass

            sm.save_settings()

            # Reflect changes immediately (no network fetch — FR-004).
            try:
                if svc and svc.park_list is not None:
                    svc.park_list.load_settings(sm)
                    svc.update_needed = True  # next update_data() fetches new park rides
                if svc:
                    svc.vacation.load_settings(sm)
                build_content_queue(self._app.content_queue, svc.park_list if svc else None,
                                    sm, svc.vacation if svc else None)
            except Exception as e:
                print("apply settings rebuild failed:", e)

        # ---- page ----
        def _render_page(self):
            sm = self._app.settings
            svc = getattr(self._app, "service", None)
            parks = sorted(getattr(getattr(svc, "park_list", None), "park_list", []) or [],
                           key=lambda p: p.name)
            selected = list(sm.get("selected_park_ids", []) or [])

            def park_select(i):
                cur = selected[i - 1] if i - 1 < len(selected) else None
                opts = ['<option value="">(none)</option>']
                for p in parks:
                    sel = " selected" if cur == p.id else ""
                    opts.append('<option value="%d"%s>%s</option>' % (p.id, sel, _esc(p.name)))
                return ('<div class="form-group"><label>Park %d</label>'
                        '<select class="form-control" name="park_%d">%s</select></div>'
                        % (i, i, "".join(opts)))

            def select(name, options, current):
                opts = []
                for o in options:
                    sel = " selected" if o == current else ""
                    opts.append('<option%s>%s</option>' % (sel, _esc(o)))
                return ('<div class="form-group"><label>%s</label>'
                        '<select class="form-control" name="%s">%s</select></div>'
                        % (_esc(SettingsLabel(name)), name, "".join(opts)))

            def checkbox(name):
                chk = " checked" if sm.get(name, False) else ""
                return ('<div class="form-group"><label>'
                        '<input type="checkbox" name="%s"%s> %s</label></div>'
                        % (name, chk, _esc(SettingsLabel(name))))

            def color(name):
                return ('<div class="form-group"><label>%s</label>'
                        '<input class="form-control" type="color" name="%s" value="%s"></div>'
                        % (_esc(SettingsLabel(name)), name, _hex_to_html(sm.get(name, "0xffffff"))))

            park_html = "".join(park_select(i) for i in range(1, MAX_PARKS + 1))
            try:
                brightness = float(sm.get("brightness_scale", "0.5"))
            except (TypeError, ValueError):
                brightness = 0.5

            return PAGE_TEMPLATE.format(
                park_selectors=park_html,
                sort=select("sort_mode", SORT_MODES, sm.get("sort_mode", "alphabetical")),
                scroll=select("scroll_speed", SCROLL_SPEEDS, sm.get("scroll_speed", "Medium")),
                brightness=brightness,
                group=checkbox("group_by_park"),
                skip_closed=checkbox("skip_closed"),
                skip_meet=checkbox("skip_meet"),
                default_color=color("default_color"),
                name_color=color("ride_name_color"),
                wait_color=color("ride_wait_time_color"),
                domain=_esc(sm.get("domain_name", "themeparkwaits")),
                vac_name=_esc(sm.get("next_visit", "") or ""),
                vac_year=_esc(sm.get("next_visit_year", "") or ""),
                vac_month=_esc(sm.get("next_visit_month", "") or ""),
                vac_day=_esc(sm.get("next_visit_day", "") or ""),
            )

    return ThemeParkConfigHandler


def SettingsLabel(key):
    """Pretty label for a settings key ('sort_mode' -> 'Sort Mode')."""
    return " ".join(w[:1].upper() + w[1:] for w in str(key).replace("_", " ").split())


PAGE_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ThemeParkWaits</title><link rel="stylesheet" href="/style.css"></head>
<body><div class="container">
<div class="header"><h1>ThemeParkWaits</h1></div>
<div class="content">
<form method="POST" action="/settings">
<h3>Parks (up to 4)</h3>
{park_selectors}
<h3>Display</h3>
{sort}
{scroll}
<div class="form-group"><label>Brightness</label>
<input class="form-control" type="range" name="brightness_scale" min="0" max="1" step="0.05" value="{brightness}"></div>
{group}
{skip_closed}
{skip_meet}
{default_color}
{name_color}
{wait_color}
<h3>Network</h3>
<div class="form-group"><label>Domain Name (.local)</label>
<input class="form-control" type="text" name="domain_name" value="{domain}"></div>
<h3>Vacation Countdown</h3>
<div class="form-group"><label>Park Name</label>
<input class="form-control" type="text" name="next_visit" value="{vac_name}"></div>
<div class="form-group"><label>Year</label>
<input class="form-control" type="number" name="next_visit_year" value="{vac_year}"></div>
<div class="form-group"><label>Month</label>
<input class="form-control" type="number" name="next_visit_month" value="{vac_month}"></div>
<div class="form-group"><label>Day</label>
<input class="form-control" type="number" name="next_visit_day" value="{vac_day}"></div>
<button class="btn" type="submit">Save</button>
</form>
<form method="POST" action="/update" style="margin-top:20px">
<button class="btn" type="submit">Check for Update</button>
</form>
</div></div></body></html>
"""
