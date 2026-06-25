"""T031 — import guard: the active boot path must not import legacy app subsystems.

The diverged modules (src/config, src/utils, src/network, the old src/ui display
stack, src/ota stubs) still exist on disk (physical deletion deferred to the
cleanup wave per the Deletion protocol), but no *active* module may import them —
they were replaced by scrollkit.* imports. Static check so it doesn't depend on a
shared sys.modules.
"""
import os

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ACTIVE = [
    "src/app.py", "src/main.py", "src/themeparkwaits.py", "src/settings_schema.py",
    "src/ota_glue.py", "src/api/theme_park_service.py",
    "src/ui/content_builder.py", "src/ui/ride_screen_content.py",
    "src/web/config_server.py", "src/web/__init__.py",
    "src/models/theme_park.py", "src/models/theme_park_ride.py",
    "src/models/theme_park_list.py", "src/models/vacation.py",
]

FORBIDDEN = [
    "src.config", "src.utils", "src.network",
    "src.ui.message_queue", "src.ui.unified_display", "src.ui.hardware_display",
    "src.ui.display_factory", "src.ui.display_base", "src.ui.display_impl",
    "src.ui.display_interface", "src.ui.simulator_display", "src.ui.pyledsimulator_display",
    "src.ui.reveal_animation", "src.ota.ota_updater", "src.ota_updater",
    "src.theme_park_api", "src.theme_park_display",
]


def test_active_modules_do_not_import_legacy():
    offenders = []
    for rel in ACTIVE:
        path = os.path.join(_REPO, rel)
        with open(path) as f:
            text = f.read()
        for bad in FORBIDDEN:
            if ("from %s" % bad) in text or ("import %s" % bad) in text:
                offenders.append("%s imports %s" % (rel, bad))
    assert not offenders, offenders


def test_no_queue_times_references_in_shipped_code():
    """FR-003 / SC-001 / SC-005: the data source is themeparks.wiki only — the
    string 'queue-times' / 'queue_times' / 'parks.json' must appear nowhere in the
    shipped app under src/ (URLs, attribution, comments, or runtime output)."""
    import re
    src_root = os.path.join(_REPO, "src")
    pattern = re.compile(r"queue-?times|queue_times|parks\.json", re.IGNORECASE)
    offenders = []
    for dirpath, _dirs, files in os.walk(src_root):
        if "__pycache__" in dirpath or os.sep + "lib" in dirpath:
            continue  # skip caches and the vendored adafruit/scrollkit bundle
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    if pattern.search(line):
                        offenders.append("%s:%d: %s" % (os.path.relpath(path, _REPO), i, line.strip()))
    assert not offenders, "queue-times references remain:\n" + "\n".join(offenders)
