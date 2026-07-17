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

## 2026-07-15 evening: attempt #5 verified end-to-end; the warm-radio law

**Shipped and hardware-verified (3.5.11 → 3.5.12):**
- The ECDSA-host check answers definitively on a healthy boot ("You're up to
  date", "Update available") — first definitive answers from a running app in
  this ledger's history.
- Boot-time staging works: ~100 sequential RSA GETs from
  raw.githubusercontent at early boot, download → apply → reboot, TWICE
  (drill 3.5.9→3.5.11, then a fully-OTA self-update 3.5.11→3.5.12).

**New law (3-for-3 both ways, then reproduced again post-apply):** a
``microcontroller.reset()`` issued while the station is associated carries
warm radio state into the next session; that session then degrades until
every NEW outbound TCP connect fails ``OSError: 16`` while pooled keep-alive
flows (the park fetches) keep working — which is why the box always "looked
fine" while checks failed. A cold-radio boot (radio disabled before reset, or
full power cycle) is healthy. 3.5.12 therefore cold-resets on every
deliberate reboot (OTA apply, watchdog, web install, crash handler).

**Open item (rung 3):** the in-handler synchronous radio bounce fired live
(ESP-IDF scan visible on serial — note: the site WiFi is a multi-node mesh,
two APs same SSID at -43/-58 dBm) but did NOT cure an already-degraded warm
boot, unlike the REPL-sequence cure (which had longer settle + separate
reconnect). Suspect the 1 s settle is too short or the mesh reassociation
lands on a different node mid-handler. The state it guards against should now
be rare (cold resets remove the known trigger); the soak will tell. If it
recurs, try: longer settle, connect retry loop, or escalate rung 3 to a
cold_reset instead of a bounce.

**Residue:** one transient boot crash was recorded during the 3.5.12 apply
window (``themeparkwaits.py:33 AttributeError: 'module' object has no
attribute 'run'``) — self-recovered (streak 0, status OK). Likely the reload
racing the half-applied /src; worth an eye during the soak.

## 2026-07-16: overnight verdict, the 3.5.13 split-brain, and the review roadmap

**Overnight (the "bricked morning"):** telemetry shows the ladder WORKED — ~4
cycles of wedge → 12 failures (~12 min) → cold auto-reboot → healthy; the
device answered its config page and checks at 07:00/08:00. The bounces at
3/6/9 reassociated but did not cure (the app kept its pre-bounce
SocketPool/Session — fixed in 3.5.13/3.5.14 by completing every bounce with
a full session rebuild + re-pointing the OTA client's session). The morning
"brick" sighting is best explained by the OR-fed hardware watchdog: display
loop OR fetch path feed it, so a frozen panel with a live backend never
starves it (3-model consensus). AND-watchdog is the fix — not yet built.

**3.5.13 split-brain regression:** pushing a release-* branch triggers
publish-live.yml, which bundles scrollkit from that repo's GITHUB MASTER.
The attempt-#5 library changes were uncommitted, so CI's force-push shipped
app-3.5.13 + lib-without-check_url; fielded as "OTA unavailable: unexpected
keyword argument 'check_url'" (OTA constructor-dead; no self-heal — needed a
REPL hand-rescue of client.mpy). RULE: the library must be committed+pushed
BEFORE any release branch. Fixed in 3.5.14; scrollkit master now carries all
attempt-#5 changes. Bonus finds: /lib accumulated interleaved stale .py
(USB-deploy era) + .mpy (OTA era) — installing X.mpy now removes X.py.

**First-ever post-apply check success:** after 3.5.14's cold-reset-on-apply,
the first check after the OTA apply returned "You're up to date (3.5.14)" —
previously that check always failed on the warm-radio state.

**3-model review roadmap (gpt-5.2/5.4/5.5, consolidated):** (A) cold_reset as
the single unavoidable primitive incl. breadcrumbs — DONE except breadcrumbs;
WiFiManager.reset() footgun fixed 14059f4. (B) bounce = full network-stack
lifecycle event: 3-5 s/state-based settle; evaluate config-server + mDNS
rebind; bounce_sync is_connected fixed. (C) global network-operation lock;
web-triggered recovery should ACK-then-recover async (bounce inside a sync
handler can kill the very HTTP response). (D) failure CLASSIFICATION (EBUSY
vs PK_ALLOC vs DNS vs 5xx) — escalate only on local-stack classes; reboot
BUDGET with degraded safe mode. (E) mode-aware AND-watchdog (per-task
heartbeats; UPDATING/RECOVERY modes exempt). (F) instrumentation:
/status.json (frame counter!), pre-reset breadcrumb capsule, corner-pixel
panel heartbeat, numeric-IP-vs-hostname probe during a wedge, mDNS-off A/B
soak, BSSID/channel/RSSI at every rung. (G) hygiene: connect() discards a
Session; _prep_session comment/policy mismatch; _is_transient too broad.

**Open questions:** roam theory unconfirmed (BSSID logging shipped, awaiting
data); exact errno-16 mechanism (upstream CircuitPython/ESP-IDF reproducer
worth building once instrumented); the panel-dark-vs-loop-dead distinction
needs the frame-counter instrumentation.

## 2026-07-16 (later): the blank-box guarantee (3.5.15)

Why the watchdog never fired on the frozen morning — two mechanisms, both
now closed:
1. **It may never have been armed.** Arming skipped whenever a host held the
   CDC serial port open (`supervisor.runtime.serial_connected`) — a browser
   Web-Serial tab or any attached computer silently disabled the watchdog
   for the whole boot. Now: arms UNCONDITIONALLY on hardware; interactive
   debugging opts out explicitly via a `/no_watchdog` marker file (create it
   BEFORE rebooting into a debug session — RESET-mode watchdogs can't always
   be stopped from the REPL). Armed/disarmed state shows on the diagnostics
   page.
2. **Even armed, it couldn't see a dead panel.** The display loop caught
   render errors and RE-FED the watchdog (and if the loop itself had died,
   an armed watchdog WOULD have fired — the fetch-path feeds can't bridge an
   8 s timeout across a 300 s cycle; so the frozen panel means the loop ran
   while its output didn't). Now: 10 consecutive render errors stop the
   feeding and the box hardware-resets within seconds. The below-Python
   case (RGBMatrix DMA death with a happily-rendering loop) is still only
   DETECTABLE (frames-rendered counter on the diagnostics page: advancing
   number + dark panel = output layer dead), not self-healing — the
   mode-aware AND-watchdog with a rendered-frame heartbeat remains the
   roadmap item for that.

## 2026-07-16 (later still): 3.5.15's own reset loop, fixed in 3.5.16

Shipping always-arm put the box into a hardware-watchdog reset loop
(ResetReason.WATCHDOG, no traceback; box reset every ~2-4 min shortly after
arming). The 8 s library-default timeout NEVER fit this app: synchronous
update checks block the event loop 10-19 s (the soak log itself recorded
18.2 s and 19.4 s checks) and a slow 90 KB park fetch can breach 8 s. The
old serial-connected arming guard had masked the misfit for months — the
desk box's port was always held, so this app has effectively never run
armed until 3.5.15. Debug path for an armed reset-looping box: break into
the REPL DURING the boot print phase (arming happens after setup()), create
/no_watchdog, reboot — then investigate at leisure. 3.5.16 sets
watchdog_timeout=60 (still a sub-minute self-heal for a frozen box; the 8 s
figure was precision the workload never supported) with a test guard
(>= 30 s). Verified on hardware: armed 60 s, survives checks and fetch
cycles, boot count static.

Lesson for the ledger's method: "the watchdog worked for 26 h during the
soak" was FALSE HISTORY — it was disarmed the whole time and nobody could
tell. The diagnostics page now shows the armed/disarmed state precisely so
an assumption like that can never go unexamined again.

## 2026-07-16 (evening): the selective wedge outlasts rung 3 — two design gaps

Episode: soak shows checks failing 14:00-16:00+ with `status=OK` — the
SELECTIVE wedge (new connects dead, pooled park socket fine) persisting for
HOURS on 3.5.16. Owner-visible symptom: "the web server isn't responding" —
the UI was alive but starved (each hourly check ran the full rung ladder,
~40-45 s INSIDE the synchronous handler). A live-specimen REPL probe landed
mid-bounce (radio unassociated, ap_info None), so the numeric-IP-vs-hostname
discriminator REMAINS unanswered — future probes must check ap_info first.
Cold reset cured it, as always.

Findings:
1. **rung-3 bounce+rebuild does NOT reliably cure the selective wedge** —
   hourly soak checks kept failing with it firing every time. The full
   session rebuild was necessary but is evidently not sufficient.
2. **Design gap: only FETCH failures escalate.** In selective-wedge mode the
   park fetches ride their pooled socket, the failure counter stays at 0,
   and the auto-reboot never fires — the box can sit degraded indefinitely.
   Check failures need to feed an escalation counter (a few consecutive
   definitive-check failures while fetches succeed = the selective
   signature; escalate to cold reset).
3. **Field-validated (gpt-5.4's review concern): in-handler recovery makes
   the box feel dead.** The check should answer fast (return the failure,
   schedule recovery async) — ACK-then-recover — or drop rung 3 from the
   handler entirely and leave bounce+rebuild to background escalation.

Next fix set (proposed, not yet shipped): check-failure escalation counter →
cold reset; move rung 3 out of the handler; then the roam correlation +
upstream reproducer work continues under the soak.

## 2026-07-16 (night): the consensus tear-down — 3.5.17 deletes the recovery layer

A 3-model adversarial review (gpt-5.6-sol, gemini-3.1-pro, claude-opus-4.5;
two rounds + synthesis) of the whole 07-12→07-16 change set, prompted by the
owner's verdict ("unshippable — worse with every release"), converged
unanimously on a sharper diagnosis than any single entry above:

1. **The check was destroying the data path.** `_prep_session()` evicted the
   data session's pooled sockets before EVERY check. In the selective wedge
   (new connects dead, POOLED park socket alive) the hourly check therefore
   killed the one connection still working — "I fixed the check and now all
   ride updates fail" was literally the mechanism. The ECDSA check_url had
   already made the eviction pointless (the check's handshake costs what a
   park fetch costs; the RSA fetches live at early boot).
2. **The in-handler ladder was the hang.** Rungs 2-3 (evict → bounce_sync +
   rebuild) ran synchronously inside the web handler: 40-45 s with the single
   event loop frozen (display dead, web dead, watchdog margin ~15 s of 60) —
   and the evening episode above had already shown the ladder never cured the
   wedge. All damage, no benefit.
3. **Three uncoordinated recovery actors** (HttpClient auto-rebuild at 2
   failures, app bounce-every-3, the check ladder) shared one radio and one
   session with no lock, no cooldown, no shared state.

**3.5.17 (net-negative diff):** check is ONE attempt and read-only (no
eviction, no bounce, no rebuild — `_evict_data_sockets`/`_is_transient`/the
ladder deleted); app-level radio bounce deleted (fetch failures ride the
12-strike budget straight to the base cold reset); HttpClient auto-rebuild
effectively disabled (threshold 1e6) — cold reset is the ONLY automatic
recovery primitive. NEW: check failures finally escalate — `note_check_result`
counts consecutive non-definitive checks (park success cannot clear it; the
pooled-socket success is blind to the wedge), 4 strikes → ONE cold reset
scheduled AFTER the response flushes (ACK-then-recover), with a persisted
3-reset budget so a check-host/DNS outage can't reboot-loop the box (any
definitive answer re-arms it). publish.sh: a missing server key now FAILS the
release (the exit-0 skip was a fleet-wide silent "up to date" split-brain
waiting to happen), and the endpoint is read back post-publish and must match
exactly. KEPT (hardware-verified): ECDSA check_url, boot-time staging +
persisted install flag, cold_reset on deliberate reboots, always-arm watchdog
@60 s, diagnostics visibility, .mpy/.py cleanup.

**Verification standard (unchanged in spirit):** 211-test suite green
(rewritten ladder tests now assert the INVERSE: single-attempt read-only
check, zero in-band bounces/rebuilds, ledger escalation + budget + reboot
persistence). Shippable only after a ≥72 h hardware soak: hourly checks, ride
data stays fresh through failed checks, frames_rendered keeps advancing, any
wedge self-heals via one budgeted cold reset, zero manual power-cycles.

## 2026-07-17: the flapping falsification — 3.5.17's counters were blind (3.5.18)

The owner's hand-reinstall of 3.5.17 "still broken" report led to the richest
evidence night yet (pal debug + live specimen, all read-only):

1. **3.5.17 was correctly installed and its check code never ran.** OTA:
   ready, page serving (on port 80 — :8080 is desktop-only; a probe mistake
   briefly claimed inbound death), zero completed-check log lines.
2. **The wedge developed IN-SESSION from a POWER_ON (cold) boot in <1 h** —
   falsifying warm-reset poisoning as the only path in. Live serial: every
   new outbound connect EBUSY, heap healthy, park API included.
3. **The wedge FLAPS.** A settings save mid-episode fetched new parks
   successfully (new connections!) with no reboot in between (boot count
   static), then a later cycle failed again. Sick ↔ healthy, minutes-scale.
4. **Therefore every consecutive counter was structurally blind:** brief
   healthy phases — or ONE park succeeding on a surviving pooled socket
   (`update_selected_parks() > 0` counted as success) — reset both the
   12-strike fetch budget and the 4-strike check counter forever. One
   "consecutive=1" line all night; no escalation ever fired.

**3.5.18 (built, 216 tests green):** the wedge ledger — WINDOWED, CLASSIFIED
strikes (errno-16 only; -16256/DNS/5xx never reboot) from refreshes AND
checks; strikes expire by TIME only (success re-arms the reset budget but
never erases evidence); 6 strikes/30 min → one budgeted cold reset. Partial
success with wedge evidence keeps content but stays on the 60 s retry and
strikes. **Sockets are closed until needed** (owner's design rule): every
refresh and check drains the pool afterward — the box idles with zero open
outbound sockets, so each burst honestly probes new-connect health and no
surviving socket can mask the wedge. Warm-boot normalization in the
bootstrap: RESET_PIN/WATCHDOG reset reasons get ONE marker-guarded cold
reset before the first join (a hardware button press can never run radio-off
first; skipped when the FS is read-only, i.e. USB-deploy sessions). WiFi
modem power-save disabled (PowerManagement.NONE) as the A/B discriminator —
if wedges stop recurring, the doze/wake path was the trigger all along.
Cadence: 600 s (product intent). Instrumentation: boot banner (version/
reason/boot#) anchors the log; strikes log t=<monotonic>+bssid; POST /update
logs a handler-entry breadcrumb. Install instructions must end with FULL
POWER REMOVAL, never the RESET button (pending: README/upgrade/setup pages).
