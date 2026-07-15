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

## 2026-07-15: the evidence session (USB-attached, live falsification)

The wedged box was probed BEFORE power-cycling — the direct observation the
ledger lacked. Findings, in the order they overturned assumptions:

1. **The wedge was never OTA-specific — and never socket-table exhaustion.**
   With the box wedged (~26 h uptime): every outbound connect failed
   `OSError: 16` at `_get_connected_socket` — park API and GitHub alike —
   while INBOUND kept working (the config page answered). At the REPL the
   socket table had **7/8 slots free** and `idf_free` jumped 211 KB → 2.2 MB
   once the app halted: nothing was leaked. The wedge lived in the WiFi/lwIP
   session itself.
2. **A radio reconnect alone cures the wedge.** With every wedged app object
   still in RAM, `wifi.radio.connect()` at the REPL restored outbound TCP
   *and* a full TLS handshake to raw.githubusercontent.com. No reboot needed.
   Nothing in the recovery ladder ever tried this rung: the link looked up
   (IP present, inbound fine), so `reconnect()`-style guards were blind.
3. **Attempt #4 is falsified as the complete story.** A FRESH boot — healthy
   network, 4/4 parks fetched — fails its first-ever check with `-16256`.
   No rebuilds had happened; no orphans existed. Eviction+retry both failed;
   heap probe at check time: `idf_free=211760 idf_largest=147456` — identical
   to the wedge-time numbers, i.e. that is the app's NORMAL runtime steady
   state (the espidf numbers cannot see the internal-SRAM region at all).
4. **The deterministic culprit is the cert chain.** raw.githubusercontent.com
   now serves an **RSA-2048** chain (`CN=*.github.io`, via a Let's Encrypt
   intermediate — a rotation from earlier DigiCert observations);
   api.themeparks.wiki and themeparkwaits.com are **ECDSA P-256** end-to-end.
   mbedtls RSA verification needs multi-KB bignum buffers from internal SRAM;
   ECDSA needs a fraction. That is why park fetches never fail a handshake,
   why the bare REPL (max headroom) completes the same GitHub handshake, and
   why the running app never can. Checks passed 7/7 on 3.5.5 (07-09) —
   a knife-edge margin that GitHub's rotation and/or app growth flipped.

| # | Fix (where, when) | Hypothesis | Outcome | Post-mortem |
|---|---|---|---|---|
| 5 | Check via themeparkwaits.com + boot-time staging + radio-bounce rung (lib `check_url`/`WiFiManager.bounce`, app glue/ladder, publish.sh → `/ota/version.txt`, 2026-07-15) | Two diseases: (a) the CHECK dies deterministically on GitHub's RSA-2048 chain (internal-SRAM PK_ALLOC) — so check against a ~6-byte version.txt on an ECDSA host we control, and defer the RSA manifest/file fetches to EARLY BOOT where the same handshake provably succeeds; (b) the long-uptime lwIP wedge needs a radio-bounce escalation rung (proven cure) + the auto-reboot watchdog actually fed and enabled | **UNVERIFIED** — ships in 3.5.11 | First attempt grounded in a direct observation of the failing allocation's host-side cause (cert chain), not in heap archaeology. The check now shares its TLS profile with the park fetches that have never failed. |

**Verification standard for #5** (unchanged in spirit from #4):
1. USB-deploy 3.5.11 (its own fix cannot arrive OTA — the old check path is the
   thing that's broken), publish the release + `/ota/version.txt`.
2. Button check must return a definitive answer on a RUNNING app, fresh boot
   AND hot heap.
3. Full install path exercised once for real: lower `src/.version` on-device,
   check → install → boot-time stage (RSA fetch at early boot) → apply →
   correct version after reboot.
4. Multi-day soak via the (now mDNS-addressed) hourly monitor: no STALE, every
   check definitive. The radio-bounce rung is expected to make the ~26 h wedge
   self-heal invisibly; a wedge that survives a bounce escalates to the
   watchdog reboot at 12 consecutive failures.
