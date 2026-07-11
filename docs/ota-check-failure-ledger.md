# The Check-for-Update failure — complete attempt ledger

Every fix attempted for the recurring update-check failure on the MatrixPortal
S3 ("MemoryError" / "Out of sockets" / "OSError: -16256"), what each one
assumed, and what actually happened. Kept because retrying variations of dead
hypotheses cost days; a written kill-list prevents circular debugging.

## The symptom family (one disease, three faces)

All three errors are the same underlying starvation — the ESP32-S3's ~320 KB
**internal SRAM**, where mbedtls TLS contexts must live (hardware crypto cannot
use the 2 MB PSRAM). Which error appears depends on which allocation dies
first:

- `MemoryError` — a Python-visible allocation fails during `session.get()`
- `RuntimeError: Out of sockets` — the global lwip socket table is exhausted
- `OSError: -16256` — mbedtls `-0x3F80 PK_ALLOC_FAILED`: the TLS handshake
  itself can't allocate its context

## The ledger

| # | Fix (where, when) | Hypothesis | Outcome | Post-mortem |
|---|---|---|---|---|
| 0 | Free the intro bitmap before the manifest GET (`6d42c12`, pre-2026-07-08) | Display bitmap pressure on the GC heap starves the GET | **FAILED** — check kept failing intermittently | Freed Python-side RAM; the starvation is native. First of several GC-heap-shaped answers to a native-heap problem. |
| 0b | Rebuild the session before every OTA GET (`_prep_session`, EBUSY era) | Wedged sockets/TLS from the old leak block the handshake | "Worked", then **became the disease** | Each rebuild orphaned the old pool's native socket + TLS context. The defense outlived the leak it guarded (fixed at the source 2026-06-30) and turned into the primary leak engine. |
| 1 | Stream manifest/file bodies to flash instead of `response.json()` / `.content` (library `bc2a082`, 2026-07-09) | The ~31 KB body needs one contiguous GC-heap block | **FAILED** for the button | Real improvement (kills a genuine contiguous-RAM cliff, keeps large manifests viable) — but the error text always said the failure was inside `_http_get`, *before* any body read. Fixed the wrong allocation; declared victory after verifying deployment, not the failure mode. |
| 2 | Sacrificial 48 KB arena, released pre-GET (`ota_glue`, 2026-07-09) | GC-heap fragmentation blocks the handshake allocation | **FAILED** — falsified by a single click | Wrong heap entirely. A guaranteed contiguous GC-heap hole changed nothing because mbedtls allocates from internal SRAM. Removed same day. |
| 3 | Remove the OTA-side rebuild + evict-and-retry + heap telemetry (app 3.5.5, 2026-07-09) | Rebuild-per-check orphans native contexts; reuse one session | **PARTIAL** — 7/7 same-day hot-heap; **FAILED at ~30 h uptime** | Correct mechanism, incomplete coverage: it fixed the per-*click* leak (the cascade stopped, proven) but missed the identical rebuild in the *data path*. Eviction frees only the current session's context — it cannot reclaim contexts orphaned by prior rebuilds. Also: the retry path never fired during verification, so it shipped effectively untested. |
| 4 | Data-path rebuild hygiene: `close_pooled_sockets()` before every `HttpClient._rebuild_session` (library, 2026-07-11) | `session_rebuild_threshold=2` means any two consecutive fetch blips (one WiFi hiccup) orphan another ~40 KB native context; over days this is the death spiral — evidenced by the device reaching "STALE (network issues)" with BOTH the data path and the check dead | **UNVERIFIED** — ships in 3.5.6 | First hypothesis that explains the whole picture: the failure was never OTA-specific (the data path on the same box is failing too), and it reapplies the mechanism already *proven* for the OTA copy of the same pattern. |

## Why attempt #4 is differently grounded (and still not a promise)

- It explains the new evidence (#1–#3 never addressed why the *park fetches*
  would also die: "STALE (network issues)" on the 30 h box).
- Its mechanism is not a guess: removing the same rebuild pattern from the OTA
  path measurably ended the per-click cascade (attempt #3's verified half).
- It fits every falsification: fresh boot works (no orphans yet), bare REPL
  works (no app, no rebuilds), pooled park fetches survive while new
  handshakes die (existing contexts keep working; new allocations fail),
  same-day soak passed (too little uptime to accumulate orphans).

**Known unknowns:** no direct heap capture of the wedged state exists (USB was
detached); other internal-SRAM consumers (httpserver TIME_WAIT lwip PCBs, mDNS)
could contribute and are NOT addressed by #4.

## The verification standard this bug has earned

Same-day tests cannot validate a fix for a failure that takes ~30 hours to
develop. Attempt #4 is **unproven until a multi-day soak passes**:

1. Ship as 3.5.6; power-cycle the device (only cure for the current wedged
   native heap) and install.
2. External monitor polls the device hourly for ≥3 days: config-page status
   (must stay OK, never STALE) and `POST /update` (must return a definitive
   answer every time).
3. If USB-attached, each check's serial heap probe provides the trend line.
4. Only a clean multi-day soak closes this ledger. A same-day pass closes
   nothing.

*(Evidence opportunity, optional: before power-cycling the wedged device,
attach USB and click Check once — the heap-probe print of the exhausted state
is the one direct observation this whole ledger lacks.)*
