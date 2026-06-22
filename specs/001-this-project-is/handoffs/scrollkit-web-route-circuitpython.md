# ScrollKit library handoff — `@route` is broken on CircuitPython (web UI dead on-device)

**For:** the ScrollKit library agent (`../ScrollKit Library`).
**Found:** 2026-06-22, first hardware bring-up of ThemeParkWaits on a Matrix Portal
S3 (CircuitPython 9.1.0). Tracked in this repo as `SCROLLKIT_NOTES.md` #4.
**Severity:** blocker — the config web server cannot start on any CircuitPython
device, so every app using `scrollkit.web` route handlers is web-dead on hardware.
The desktop simulator (CPython) cannot catch this.

## Symptom

On-device boot log:
```
web server unavailable: can't set attribute '_route_info'
Web server not available - install with 'pip install sldk[web]'
```
The app catches it and continues (display still runs), but the web UI never binds —
`curl http://<device>/` is connection-refused.

## Root cause

The `route()` decorator attaches metadata to the **function object**:

`src/scrollkit/web/adapters.py` (~line 464):
```python
def decorator(func):
    func._route_info = {'path': path, 'methods': methods}   # <-- illegal on CircuitPython
    return func
```

**CircuitPython functions/methods have no `__dict__`** and do not support arbitrary
attribute assignment, so `func._route_info = ...` raises
`AttributeError: can't set attribute '_route_info'` at class-construction time. On
CPython this silently works (functions have `__dict__`), which is why it passed in
the simulator and unit tests.

### All affected sites (grep `_route_info` in `src/scrollkit/web/`)
- **Writers:** `adapters.py:464` (decorator) and `server.py:252` (a second `route`
  decorator with the same body). Both must change.
- **Readers (dispatch):** `adapters.py:189-193` and `adapters.py:315-316` — they
  iterate `dir(handler)`, select attrs starting with `route_`, then
  `hasattr(method, '_route_info')` and read `method._route_info`.

Note the dispatch **already** relies on the `route_*` **name-prefix convention**, so
the metadata just needs a CircuitPython-safe home; the discovery mechanism can stay.

## Constraint

The fix must keep working on **both** CPython 3.11+ (desktop simulator) and
CircuitPython 7+/9.x (device). Available on CircuitPython: `func.__name__`,
metaclasses, `__init_subclass__`, class attributes, dicts. Not available:
function `__dict__` / arbitrary function attributes.

## Recommended fix

Move route metadata off the function and into a **class-level registry**, keyed by
method name. A registering decorator + a small metaclass (or `__init_subclass__`) is
the standard CircuitPython-safe pattern:

```python
# decorator: record intent without touching the function object
_PENDING_ROUTES = []   # module-level scratch, drained per class

def route(path, methods=None):
    methods = methods or ['GET']
    def decorator(func):
        _PENDING_ROUTES.append((func.__name__, path, tuple(methods)))
        return func          # function returned UNCHANGED
    return decorator

class _RouteMeta(type):
    def __new__(mcls, name, bases, ns):
        cls = super().__new__(mcls, name, bases, ns)
        routes = dict(getattr(cls, '_routes', {}))     # inherit base routes
        while _PENDING_ROUTES:
            fname, path, methods = _PENDING_ROUTES.pop()
            routes[fname] = {'path': path, 'methods': list(methods)}
        cls._routes = routes
        return cls
```

Then make the handler base class use `metaclass=_RouteMeta`, and change dispatch
(`adapters.py:189-193` and `:315-316`) to read `handler_class._routes` /
`type(handler)._routes` instead of probing `method._route_info`:

```python
for fname, info in type(handler)._routes.items():
    method = getattr(handler, fname)
    for http_method in info['methods']:
        ...
```

(If you prefer to avoid a metaclass, `__init_subclass__` on the handler base draining
`_PENDING_ROUTES` into `cls._routes` works the same way and is also CircuitPython-safe.
Either is fine; key requirement: **never assign an attribute to a function**.)

Keep the public API identical — `@route("/path", methods=[...])` on `route_*`
methods — so no consumer code changes. ThemeParkWaits' `src/web/config_server.py`
uses exactly that and should need no edits.

## Acceptance criteria

1. On CircuitPython, constructing a `@route`-decorated handler class and starting
   `SLDKWebServer` no longer raises `can't set attribute` — the server binds and
   serves the routes.
2. On CPython, existing behavior + tests unchanged (same routes resolve).
3. Inherited routes (subclass adds routes to a base that already has some) still work.
4. Add a regression test that asserts **no route metadata is stored as a function
   attribute** (e.g. `assert not hasattr(SomeHandler.route_index, '_route_info')`),
   so this can't regress on the simulator.

## How to verify on the actual device (ThemeParkWaits)

After the library fix, in `themeparkwaits/`:
```
scripts/deploy.sh                       # redeploys scrollkit (excludes simulator/dev)
# watch serial: screen /dev/cu.usbmodem* 115200  -> expect "Web interface available at: ..."
curl http://<device-ip>/                # should return the config page (was refused)
```
The board's IP prints in the boot log (e.g. `Connected to WiFi. IP address: ...`).

## Related (separate, lower priority) — `SCROLLKIT_NOTES.md` #5

First HTTPS socket after WiFi connect returns `EINPROGRESS`, so `set_system_clock`
burns ~30-60s failing the first host before a working one. Not fatal, but consider
making the first request resilient (adafruit_connection_manager / settle-retry).
Not part of this handoff unless you want to bundle it.
