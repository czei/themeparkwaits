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

## 2026-07-17 (evening): THE FIRMWARE EXPERIMENT — 3.5.19 on CircuitPython 9.1.0

The 2.x-vs-3.x network-design investigation (10-agent workflow; full result in
the session archive) refuted every app-level design change as the origin of
the 2.x→3.x connection-reliability regression — connect frequency at onset
matched 2.x (temporal inversion), the lost 5x retry loop can't mask a
persistent wedge, the 6 s timeout is per-operation not per-request (10-19 s
transfers complete fine), and the lwIP slot-poisoning theory died on our own
hardware facts (reassociation alone cured once; the warm-radio law carries the
disease ACROSS a chip reset, i.e. the state lives in the RADIO DRIVER layer,
not lwIP's structures). What survives: the regression boarded with commit
08c8da5 (2026-06-24), which changed the CircuitPython firmware generation
(9.x → 10.2.1 = new ESP-IDF/WiFi-driver) AND the requests stack in one step —
the 2.x app shape ran ~2 years on CP 9.x without this failure mode.

**The deciding experiment (started tonight):** desk box flashed to
CP 9.1.0 (2024-07-10 build) with UNMODIFIED 3.5.19 — filesystem survived the
downgrade; power_management API absent on 9.1 so power-save runs at the
2.x-era default ON (logged at boot); same room, same mesh, same parks; .mpy
bundle loads fine (format stable across 9/10). First boot: 140-park catalog +
4/4 parks on first attempts. Baseline to beat: on CP 10.2.1 the wedge struck
MULTIPLE times per day with 20-40 min session onsets (strike ledger logs every
one with t=/bssid). Verdicts: 24 h with zero strikes on 9.1.0 = firmware
generation convicted (fix = track/bisect CP releases + upstream reproducer);
wedge recurs on 9.1.0 = firmware exonerated, driver-state hunt continues.
Discord/community search for the fingerprint (errno 16, new-connects-only,
power-cycle-not-reset cures): no hits as of tonight.

**Same night, first status: THE INSTRUMENT BROKE — resource misfit, not the
wedge.** On 9.1.0 the check button dies "RuntimeError: pystack exhausted"
(the deep handler→OTA→requests-4.x call chain overflows the 2024 firmware's
default Python call-stack BEFORE any network I/O — button clicks probe
nothing), and park refreshes died MemoryError (16x) until the GENERIC
12-strike backstop auto-rebooted — NOT the 6-strike errno-16 wedge ledger,
which correctly refused to classify pystack/MemoryError as wedge evidence
(zero false strikes; classifier integrity proven in the field). Sessions
therefore never reach the 20-40 min onset window: "no wedge on 9.1.0" is
UNFALSIFIABLE until the instrument is repaired. The 2026 app does not fit
2024 firmware defaults (consistent with the much-smaller 2.x app fitting 9.x
comfortably). Repair options, owner to choose ("fix one thing at a time"):
(a) CIRCUITPY_PYSTACK_SIZE bump in /settings.toml (one line, REPL-writable
— mind the 60 s armed watchdog at the REPL), retest, see if MemoryError
persists; (b) if the full app won't fit: a MINIMAL REPRODUCER script
(always-on listener + timed fresh HTTPS connects, few KB) run identically on
9.1.0 and 10.2.1 — cleaner science and the upstream-issue artifact anyway.
CP 9.2.x is the fallback old-generation testbed. Full investigation record:
docs/network-design-2x-vs-3x.md.

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

## 2026-07-17 (late): WHEN instrumentation — timestamps on the diagnostics page

**Owner's re-anchor:** the experiment's ONLY question is whether the errno-16
wedge reproduces on CP 9.x (clean 9.x → firmware regression; wedged 9.x → our
bug). Auto-reboot recovery working is triage, not success — the goal is a box
where network errors are RARE. And the diagnostics page could not answer his
basic question: "Last error" had no time on it, so 'booted, fetched once,
failing ever since' was indistinguishable from 'one blip yesterday'.

**Built (working trees only — NOT yet deployed, so the running soak is
undisturbed):**
- `scrollkit.utils.diagnostics` NVM record **v2**: every `record_crash` now
  stamps wall-clock epoch (0 = clock never set), uptime-at-error, and the boot
  number; the last SUCCESSFUL fetch epoch is persisted too (throttled to one
  NVM write per 30 min while healthy; flushed EXACT the moment a failure or
  crash happens, so post-mortems never read a stale value). Version bump means
  the fielded record resets ONCE on first boot with v2 (boot count restarts).
- Config page: new rows **Device time (up N)**, **Last fetch OK** (exact this
  session via `seconds_since_last_refresh_success()`, NVM epoch across
  reboots), and **Last error when** ("2026-07-17 14:32:10, 22m after
  power-up, boot #130 (a previous boot)"; falls back to uptime+boot# when the
  clock wasn't set; all-zero stamps render as 'recorded before timestamps
  existed', never a bogus 'boot #0').
- Gap closed: the wedge-escalation cold reset never wrote WHY to NVM (only
  base's `_auto_reboot` did) — after a wedge reset the page showed some OLDER
  error. `note_wedge_strike` now records "wedge cold reset (source): reason"
  before returning True, covering both the refresh and check paths.

Diagnostics-only change — no network-path behavior touched, safe to ship onto
the A/B box without contaminating the experiment.

## 2026-07-17 (evening): instrumentation live on-device; two follow-up fixes queued

Deployed via targeted copy (app parked at a watchdog-fed REPL; deploy.sh
deliberately not used — it ships committed HEAD and would clobber the CP 9-era
src/lib): src/app.py, src/web/config_server.py, lib/scrollkit/utils/diagnostics.py
(source; stale .mpy deleted). Verified live after the owner's power-cycle: page
shows Device time / Last fetch OK / Last error when; NVM v2 one-time reset
confirmed (boot #1, POWER_ON, clean error record).

**"Last fetch OK (never)" while the panel showed data** — the boot-time fetch in
setup() never fed the fetch accounting (only periodic update_data does), so every
boot read "(never)" for its first ~10 min. Watched it self-correct live: first
periodic refresh at ~11m35s uptime stamped "16:32:36 (33s ago)". FIXED in the
working tree: the healthy-boot branch now calls note_refresh_result(True) +
diagnostics.note_fetch_result(True, 0) instead of bare note_clean_run()
(note_fetch_result's ok-path subsumes it). Pinned by
test_boot_fetch_counts_as_fetch_success; resilience file 25/25.

**Device clock exactly 1 h behind wall time** (device 16:32 vs Mac 17:33):
scrollkit set_system_clock hardcodes tz_offset=-5 (EST) — no DST. FIXED in the
library working tree: tz_offset=None now means "US Eastern, DST-aware"
(us_eastern_offset: 2nd Sun Mar 07:00 UTC → 1st Sun Nov 06:00 UTC = -4, else -5);
NTP path now fetches UTC then shifts (offset can't be decided before the date is
known); explicit tz_offset callers unchanged. Boundary tests added (2026: Mar 8 /
Nov 1). NOTE: 3 pre-existing test_system_utils failures on the dev Mac are the
stray pip adafruit_datetime breaking the desktop rtc shim (same class as the
stray-storage issue) — not from this change; verify in a clean venv.

**Both fixes await the next deploy-mode window** (box is back in run mode; files
to ship: src/app.py + lib/scrollkit/utils/system_utils.py). Until then: page
wall-times read 1 h early; relative times ("Xs ago", uptime) are correct.

**CP 9 soak status:** the post-deploy boot is the cleanest instrumented session
yet — Status OK, 0 failures, fetch timestamps ticking. Wedge question still
open; needs hours.

## 2026-07-17 (night): pystack repair + a wrong reboot plan, corrected

CIRCUITPY_PYSTACK_SIZE = 4096 written to /settings.toml over the serial REPL
(device-writable in run mode; verified via os.getenv re-parse → 4096). Rationale:
CP 9's 1536-byte default pystack can't hold the OTA check's TLS+requests call
chain (dies pre-network, "pystack exhausted"); CP 10's default is larger — the
bump also removes a resource asymmetry from the firmware A/B.

**Two wrong assumptions, caught live:** (1) "the armed 60 s watchdog will reboot
the box from the REPL" — FALSE: CircuitPython does not run the app watchdog at
the REPL; the box just idled black (radio off) at a live prompt until the owner
noticed. (2) Even if it HAD expired, a WDT-expiry reset boots CircuitPython into
its OWN safe mode (code.py doesn't run) — the same class of trap as the fielded
8 s-watchdog safe-mode incident. RULE: never plan a reboot via watchdog expiry;
deliberate reboots are cold_reset() or owner power removal, nothing else.
Recovery: owner power-cycles; pystack applies on the hard boot.

**VERIFIED (18:38, boot #4):** after the owner's power cycle, POST /update over
HTTP returned "You're up to date (3.5.19)" — the check's full chain (fresh HTTPS
connect to themeparkwaits.com, TLS, version.txt fetch, compare) completed on
CP 9.1.0 with pystack 4096. The check-path instrument is repaired; the wedge
ledger now gets honest check-path probes on CP 9 as well. Boot #4 also confirms
the boot-fetch stamp (Last fetch OK at +78 s) and the DST clock live.

## 2026-07-17 (night): the weekend-verdict framework (3-agent adversarial assessment)

**Owner's question:** chances the wedge was our bug; is a clean CP 9 weekend
definitive proof of a CP 10.2.1 bug?

**Probability allocation (evidence-based):** "our code alone is defective" ≈ 5%
or less — three converging lines: the 10-agent refutations of every app-level
mechanism; the warm-radio law (the diseased state survives microcontroller.reset,
which wipes all Python AND lwIP state, and clears only on radio power-down — no
Python code CAN store the fault); the identical app bytes running clean on CP 9.
The real residual (~30-50%): our traffic shape (always-on listener + zero-idle
drain + fresh TLS bursts + two-AP mesh roams) is a NECESSARY TRIGGER of a latent
firmware bug — the best explanation for the verified fact that NOBODY else has
reported this fingerprint ("EBUSY" returns zero issues in the entire
adafruit/circuitpython history; esp-idf/esp-lwip/forums also empty). App-triggered
is still not app-caused: upstream classifies that as a firmware bug.

**A clean weekend is strong, not definitive:** at the logged CP 10 rate, 60 clean
hours is between ~1800:1 (hostile 3/day assumption) and astronomical odds against
"same rate" — call it ~90-95% for a firmware-generation regression. What it can
NOT do: (a) name 10.2.1 — the 9.1.0→10.2.1 span covers FOUR ESP-IDF driver drops
(5.2→5.3→5.4→5.5.3, incl. Espressif's closed WiFi blob and an lwIP-config regime
change at 5.4.1); (b) exclude the co-trigger hypothesis (the app is the constant,
so it doesn't need to). **What makes it near-definitive: the REVERSE ARM (A/B/A)
— reflash CP 10.2.1 on the same box, same settings.toml/instrumentation, and
watch the wedge return.** One flash + about a day; closes environmental drift,
weekend-RF, reflash-itself-cured-it, and app-version-baseline confounds in one
stroke.

**Weekend exposure rules (or the hours don't count):** clean-clock starts at the
2026-07-17 18:38 boot #4 (pystack repaired); boot count must stay near-static
(MemoryError reboot churn would reset the radio before every onset window —
zero strikes would then be an artifact); Last fetch OK advancing throughout;
judge on failures of EVERY class, not errno-16 alone (the disease could wear a
different errno on 2024 firmware). Each 600 s drained-pool burst = one honest
fresh-connect probe → ~6/h, 360+ over the weekend. The second fielded device
(still CP 10.2.1) is a free concurrent control — read it out too.

**Then the upstream path (verified precedent):** CP issue #10892 (ESP32-C6 WiFi
regression at the IDF 5.5.1 bump) was accepted on exactly this per-version A/B
evidence and root-caused by the maintainers — same triagers (tannewt/dhalbert).
Requirements learned from it: reproducer must use CORE MODULES ONLY (wifi,
socketpool, ssl — any adafruit_requests frame gets deflected to library repos);
include the warm-reset demonstration (tells a port engineer WHERE to look:
esp_wifi deinit/init path); report mesh topology (they ask). Bisect ladder:
9.2.8 (IDF 5.3.2 — kills "9.1.0 is just old") → 10.0.3 (IDF 5.4.1 — splits the
two suspect boundaries; #10892 reporters found it good) → 10.1.4 (IDF 5.5.1) if
needed → 10.3.0-alpha (IDF 6.0.1) as the "already fixed?" probe. Verified from
release bodies: NO shipped 10.x stable contains any relevant WiFi/socket fix —
upgrading within 10.x cannot cure this today.

## 2026-07-18 ~12:10: first CP 9 soak failure — MemoryError fragmentation, NOT the wedge

At 17h48m uptime (boot #4, ~106 clean fresh-connect probes), refreshes began
failing MemoryError: a ~57 KB contiguous alloc for DHS's response body fails with
1.36 MB free ("largest block >=32768") — same class as the first CP 9 day, with
the fragmentation threshold down from ~80 KB (fresh heap) to ~57 KB after 17.8 h.
Serial capture confirms: ZERO errno-16; classifier counting nothing; "Updated
0/4 parks" once fragmentation blocked all daytime payloads; bssid at failure
26:de:4b:9c:fb:c7 (the OTHER mesh node vs the CP10 wedge-era 3e:de:4b:9d:03:8d —
a roam happened at some point; irrelevant to a RAM failure). Expected next: the
12-strike backstop cold-reboots (radio-off), boot #5, fresh heap, soak continues.

**Weekend-math consequence:** CP 9 sessions self-truncate at ~18 h via heap
fragmentation, so the soak will be a chain of ~18 h sessions separated by
documented MemoryError cold reboots — each session still ~25x the longest CP 10
survival, so the exposure arithmetic holds; the "boot count near-static" criterion
becomes "every reboot must be a documented MemoryError backstop, never a wedge."
Fragmentation is a REAL CP 9 liability for product use (slow largest-block decay
under 90 KB payload cycling) — a point for the eventual firmware decision matrix
(CP 9.2.8 may differ; CP 10's allocator handled it), separate from the wedge
question.

**Outcome (12:31): self-healed IN PLACE, no reboot.** A 60 s stale-retry
succeeded at 12:31:54 — boot #4 unbroken at 17h58m, Status OK, failures reset.
The fragmentation episode flapped for ~21 min (repeated gc across retry cycles
eventually yielded a big-enough contiguous block) rather than riding to the
12-strike backstop. Notable: CP 9's MemoryError episodes are transient and
self-curing in-session; the CP 10 wedge never was. Session-truncation math from
the previous entry is therefore pessimistic — sessions may run far past 18 h with
occasional stale windows.

**Boot #4 session complete (2026-07-18 15:20): 20h46m, zero wedge markers.**
Three MemoryError fragmentation flaps in the final ~3 h (12:10 self-healed 21 min,
13:05 self-healed ~25 min, 14:50 rode to the 12-strike backstop) → documented
cold reboot at 15:20:56 with full WHEN provenance on the page (the instrumentation
working exactly as designed — no serial cable needed to read the whole story).
Boot #5 fetching OK 44 s after power-up (boot-fetch stamp working). Soak
continues. Running weekend total: one ~21 h session, ~120 clean fresh-connect
probes, errno-16 count: ZERO.

## 2026-07-18 16:38–16:50: kitchen-move forensics — no new failure; boots #9–#10 are bench REPL log dumps

The box was moved to the kitchen this afternoon and came back to the bench at
~16:40 ("check the error logs to see what happened"). Full dump of `/error_log`
(2.5 KB) AND `/error_log.old` (16.8 KB) over the raw REPL (bench-attached, so
the headless watchdog is unarmed; each dump ended with a deliberate soft reboot
back into the app).

**Verdict: the kitchen broke nothing.** The 16 KB rotation split boot #4's final
flap mid-cycle — MK park-attempt 1 (3× MemoryError 88896 B) ends `.old`,
park-attempt 2 opens the current file, joining seamlessly — so ALL failure
content in both files belongs to the already-documented 14:50→15:20 flap
(EPCOT 84509 B and MK 88896 B allocs failing with ~1.27 MB free). Every
post-15:20 boot logged nothing but its boot banner: no join failures, no portal
entries, no fetch errors, no wedge strikes. errno-16 count: still ZERO.

**Boot accounting since #4:** #5 = 15:20:56 backstop recovery (banner present,
fetched OK 44 s in). #6–#7 = kitchen power cycles; #8 = bench plug-in ~16:40.
Fewer banners than NVM boot counts here — at least one boot reset before the
app reached its `__init__` banner write (consistent with a quick unplug, or a
marginal kitchen power source browning out during the WiFi/PSRAM spike; no
positive evidence either way — depends on what the panel actually showed in the
kitchen). **#9 (16:43) and #10 (16:49) are documented bench interventions** —
Ctrl-C + raw-REPL log dumps, each followed by a soft reboot; both resumed
cleanly, monitor shows fetching OK. For the weekend criterion these two are
deliberate, not backstops. The monitor's 16:38 "unreachable" window was just
the box unplugged in transit; the .119 lease survived and it re-found the box
at 16:41. **#11 (~17:03) = another hard power event** — the power-up clock
restarted and the NVM error record is unchanged from 15:20:56, and no
escalation fits a 13-min healthy window on the 600 s cadence, so this was a
manual unplug/replug (box relocated again). Fetched OK 71 s after power-up;
soak continues.

## 2026-07-18 evening: the wedge probe — 9.1.0 negative control PASSES; a CP 9 USB-CDC trap en route

The CP-version bisection begins (goal: which firmware to ship; 10.2.1 wedges
almost immediately in the field — first fetch OK, everything after fails).
Soak monitor stopped; `tools/wedge_probe.py` replaces code.py on the desk box:
standalone, app-faithful fetch loop (same Session construction, power-save
setting, UA header, 6 s timeout, `.text` read, drain-after-burst close), the
app's own errno-16 classifier, 15 fetches at 60 s, self-identifying lines
(`os.uname().version`), VERDICT + 30 s idle heartbeat. v1.1 fix: /src/lib on
sys.path (the vendored bundle's home — standalone code.py doesn't get the
app bootstrap's path setup; the v1.0 boot died ImportError on
adafruit_requests, silently, at a "Done" console).

**The observability trap (cost ~90 min, three power cycles):** three runs in
a row went serial-silent after 1, 5, and 13 minutes — console output dead,
Ctrl-C dead, ping alive. Misread first as an ESP32-S3 core lockup. v1.2
added an append-only `/probe_log.txt` on the device flash (begin line before
each fetch, result after — the phase discriminator). The flash log's verdict:
**the device never locked up.** Run 3 completed 15/15 + VERDICT + 18 idle
heartbeats invisibly; only CP 9.1.0's USB CDC had died (in+out) under a
persistent host reader. Rule for all remaining bisection runs: serial is
untrusted convenience; the flash log is the record — run with nothing
attached, read `/probe_log.txt` over the REPL afterward.

**Result: CP 9.1.0 = NO-WEDGE, 15/15 fetches OK** (steady ~63 s cadence,
heap flat ~1.88 MB free, largest block ≥96 KB every pass — no fragmentation
inside a 15-min window). The probe and pattern are validated as the
bisection detector. Ladder staged in ~/Downloads (UF2s verified): 9.2.9,
10.0.3, 10.1.4, 10.2.0, 10.3.0-alpha.3; next step = flash 10.2.1 (the
site-hosted UF2) for the positive control — expect WEDGE by i=02-03, then
a MODE="raw" run to mint the upstream artifact.

**Positive control REFUSED to reproduce: 10.2.1 = NO-WEDGE 26/26.** Four
10.2.1 boots (extra ones were USB-debug power cycles): one full 15/15 run +
partials of 1, 2, and 8 fetches — every single-park 60 s fetch clean, zero
errno-16, RSSI -38..-46, no roams. The v1.x probe passes BOTH poles → not a
valid detector; bisection on hold. Owner clarification pins the delta: the
field failure was THIS box, THIS bench, THIS cable, running the FULL APP —
first refresh of 4 parks OK, all subsequent refreshes fail. Environment
exonerated; the missing ingredient is the app's refresh shape (4-park
burst, drain per REFRESH not per fetch — a v1.2 fidelity bug — and the
600 s idle gap the failure boundary sits on) and/or its co-resident socket
pools (web server, NTP, mDNS).

**New instrument hazard: CP 10.2.1 never enumerates USB on this box** — all
four boots, two cables, two Mac ports; meanwhile double-tap → TinyUF2
enumerates instantly (hardware exonerated) and reflashing 9.1.0 restores
USB on the first boot. Unexplained (box ran 10.2.1 with working USB for
weeks pre-downgrade; settings.toml pystack line added 07-17 is a candidate).
Practical consequence: 10.x verdicts are read from /probe_log.txt after
flashing BACK to 9.x, and the probe's status NeoPixel is the only live view.

**v2.0 (pushed):** replays the app's refresh verbatim — boot catalog GET,
the box's real selected_park_ids per burst, gc sandwich per park, ONE pool
drain per burst, 600 s idles, 4 bursts, early-exit on 3 consecutive
errno-16 after any success (field timing predicts a burst-2 verdict,
~12 min). NeoPixel: green/red/amber per fetch, dim blue idle, steady
green/red = final verdict — readable with USB dead.

**v2.0 result: 10.2.1 STILL refuses to wedge — VERDICT NO-WEDGE ok=16/16**
(catalog + 4×4-park bursts across three 600 s idles), plus power-cycle-cut
reruns of 4/4, 12/12, 8/8. Tonight's total on the known-bad firmware:
**66/66 fetches, zero errno-16, two probe shapes.** The app's fetch pattern
— even burst+idle+catalog verbatim — is exonerated. The wedge needs the
app's co-resident machinery (web server pool/listener, mDNS, NTP, the OTA
check's second TLS host, asyncio interleaving) or bench-absent conditions
(mesh roam; longer horizons). The 10.x investigation is PARKED with that
suspect list; tools/wedge_probe.py stays for its resumption. (Reading these
verdicts surfaced a second trap for the toolbox: the Mac's mounted view of
CIRCUITPY is frozen at mount time — a mid-run TextEdit read of
probe_log.txt showed only the first two lines of a 4 KB section. Stale-FAT
applies to ALL device files, not just error_log.)

## 2026-07-18 ~21:30: STRATEGIC PIVOT — the real fleet is 50+ boxes on CP 9.2.8; ship 3.0 on the 9.x line

Owner reveal: 50+ customer boxes run CP **9.2.8** (factory image
MatrixPortalBoot/adafruit-circuitpython-adafruit_matrixportal_s3-en_US-9.2.8.bin)
on TPW 2.x — the site's hosted 10.2.1 UF2 does not match the installed
base. Decision: ship ThemeParkWaits 3.0 on the 9.x line (no fleet firmware
change), investigate 10.x later. Gate: **a weekend soak of 3.5.19 on 9.2.8
exactly** — never yet run (the 21 h wedge-free soak was 9.1.0 = IDF 5.2.2;
9.2.8 = IDF 5.3.2 + the 9.2.2 mbedtls-in-PSRAM TLS change; the fleet's
stability record was earned by the 2.x stack). Named ship conditions:
(1) CP9 fragmentation liability rides along — soak decides if 9.2.8 shares
9.1.0's ~18 h MemoryError flaps; (2) CIRCUITPY_PYSTACK_SIZE=4096 must reach
every upgraded box (3.x OTA chain exhausts CP9's 1536 B default);
(3) flip the site's customer UF2 10.2.1 → 9.2.8; (4) 2.x boxes upgrade via
the USB zip path (retired 2.x OTA can't receive 3.x). Desk box flashed
9.2.8 21:28 (USB deterministic again — first boot), probe's first-ever
3.x-on-9.2.8 data came back clean (catalog + 4/4 burst), app restored as
code.py; soak starts on the owner's next power pull.

## 2026-07-19 morning: night one of the 9.2.8 soak — WDT bite → CP safe mode → dark panel til morning

Owner found the panel BLANK at ~07:54. Console: "Running in safe mode! ...
Internal watchdog timer expired"; microcontroller.cpu.reset_reason =
WATCHDOG. In CP safe mode code.py never runs: no display, no web server,
radio off (the .119 lease went to another device — arp shows 48:e1:e9:7a:39:c0).

**Timeline from the raw NVM ledger** (read over the safe-mode REPL —
diagnostics.open() hands back the inert stub in that context, another face
of the reason=UNKNOWN/boot#0 instrument breakage; raw bytes decoded against
the layout): boot_count=15 (the 21:34 POWER_ON soak boot, never incremented
again), **last_ok_time = 2026-07-19 03:52:00** — the box fetched
successfully for 6+ hours before dying (persist throttle ≤30 min slack).
ERR_* slots still hold July-18 15:20:56 (no new escalation), persisted
consec_fails=0, no wedge-strike/escalation lines in error_log. So the death
was SUDDEN: healthy operation → >60 s watchdog starvation somewhere in
03:52–07:00, with no ladder engagement and nothing logged.

**9.2.8 inherits the CP9 fragmentation liability** (expected): overnight
error_log shows partial refreshes — 83–88 KB payloads (EPCOT/MK) failing
MemoryError with ~1.27 MB free while the 35–55 KB parks pass. Logged,
handled, non-fatal — NOT the direct killer.

**Two systemic findings, both ship-gates for 3.0-on-9.2.8:**
1. **The CP-safe-mode trap is the real product killer:** any >60 s stall +
   WatchDogMode.RESET = a customer box dark until a human power-cycles.
   There is no /safemode.py on the device. CP 9 supports one; a guarded
   reset-after-delay (NVM loop-guard so a hard fault can't fast-loop)
   converts "dark forever" into "self-heals in ~a minute" fleet-wide.
2. **Monitoring went blind twice:** the box left .119 around ~21:40 (DHCP —
   the July-13 blindness repeating; poll by mDNS name, not hard IP) AND the
   re-armed monitor was a background shell capped at 10 min. Net: a 6-hour
   healthy stretch and the actual death window went unobserved.

**Open question:** what starves the watchdog for >60 s between 03:52 and
07:00 on 9.2.8 while 9.1.0 ran 21 h clean? Candidates: a TLS/DNS hard block
uncovered by the 6 s HTTP timeout (9.2.2 moved mbedtls data to PSRAM), a
stall in a non-feeding path, or a fragmentation-era failure mode in a loop
that owns the feed. Next: audit the feed points, then an instrumented soak
with working monitoring. Box is fully harvested and safe to power-cycle.

**Instrument note:** the error_log boot banner prints `reason=UNKNOWN boot#0`
on CP 9.1.0 (the known pystack/MemoryError-era breakage — NVM ledger/status
page unaffected; the monitor reads boot numbers fine). The banner ambiguity is
exactly what made this forensics pass slow — another vote for the pending
repair.

## 2026-07-19 afternoon: the fault-tolerance redesign — nothing ever parks

The owner's verdict on the 07-19 morning brick generalized: the design's
fatal flaw isn't any one bug, it's that serious problems END somewhere —
safe modes that park, budgets that exhaust, stalls with no backstop. A
3-model PAL review (GPT-5.6-Sol / Gemini 3.1 Pro / Qwen 3.7-Max) confirmed
the diagnosis unanimously: **every escalation mechanism defined health as
"a fetch succeeded", so ordinary network trouble escalated exactly like a
crash loop** — and three of the five mechanisms terminated in a state only
a human could exit. Design invariant now in force: *from any state the
device returns to a normal-operation attempt within bounded time, forever.*
Reboot (radio-off cold reset) is the recovery primitive; it is rate-limited
and never accumulates into a parking lot.

**The terminal states that existed, and what replaced them:**
1. *The outage-to-brick walk* (12-failure reboot every ~13 min → each boot
   +1 rapid_boots, cleared only by a fetch success → 5th boot = safe mode
   with update_data() disabled = never notices the WAN return): DEAD. A
   stable-uptime task (10 min alive = clean run, app.py
   _note_stable_runtime) clears rapid_boots + the safemode streak with no
   network at all; only boots that die YOUNG still trip the breaker.
2. *App safe mode* is now RECOVERY MODE: catalog + web UI as before, plus a
   guarded probation fetch every 30 min (success → prove health → cold
   reset to a normal boot) and a 60-min full re-test reboot. Settings-save
   stays the instant manual exit.
3. */safemode.py* never parks: the park-at-5 became an escalating ladder
   (10 s ×5, 60 s ×5, then 15 min forever), counter saturates at 255, NVM
   bounds-checked, radio forced off before the reset (warm-radio law), USER
   safe mode still respected. OTA-deliverable now (allowlist + publish.sh
   SHIP_SAFEMODE two-stage gate; deploy.sh ships it like boot.py).
4. *Wedge budget exhaustion* ("not resetting", forever) is a rate limit:
   after 6 h uptime one more cooled-down reset is allowed, each further one
   needing another 6 h.
5. *Failure-reboot churn*: first 12-failure reboot fires as before, but a
   new NVM epoch flag (set at each failure reboot, cleared ONLY by a real
   fetch success) rate-limits subsequent ones to ~1/hour.

**The silent-stall gaps, closed (library):** boot now runs under the
watchdog (armed BEFORE setup() at 120 s, tightened to 60 s after; fed at
status frames, per-park fetches, OTA download chunks, and the setup-portal
poll loop — the first-boot portal legitimately waits forever and feeds
while doing so). A data-progress deadman rides the display loop: a dead
data task, an attempt that never returns (>10 min), or a data loop that
stops iterating gets a *recorded* cold reset — deliberately better than
starving the watchdog, whose bite transits CP safe mode and records
nothing. Progress = attempts COMPLETING, success or failure alike (PAL
consensus: an offline box actively retrying is healthy — a success-based
deadman would have rebuilt the original sin). The data task is now ALWAYS
created (a transient low-memory reading at startup used to omit it
permanently), and cold_reset failures fall through a hard_reset ladder
(raw reset → supervisor.reload) instead of silently not resetting.

Diagnostics page grew the machinery state (failure-reboot epoch, wedge
budget incl. cooldown, safemode auto-reset count); partial-wedge refreshes
now read STALE, not OK. NVM bytes 240–241 are a documented reserved range
(diagnostics SAFEMODE_RESERVED_START; layout pinned by tests in both
repos). Also fixed while proving the suite: the desktop rtc mock in
system_utils eagerly constructed adafruit_datetime.datetime() (TypeError)
— every desktop RTC write had been failing silently inside the except.

Tests: app contract suite grew the keep-going section (stable-uptime clean
run, 100-outage-cycle never-safe-mode composition, recovery-mode
probation/throttle/timed-reboot, budget trickle, safemode.py exec'd under
stubbed CircuitPython — ladder/USER/radio-off/no-NVM, layout pins);
library grew rate-limit, supervision, always-data-task, and epoch-flag
coverage. Still device-only: WDT timeout retighten on 9.2.8 (falls back to
a single 120 s window if the port refuses), a forced WDT bite through
safemode.py, and the headless soak. The 03:52–07:00 starvation root cause
remains OPEN — this work makes it survivable, not explained.

**2026-07-19 bench-deploy discovery — OTA checksums cannot run on this CP
9.2.8 build:** the built-in `hashlib` exposes only `new()`, and
`hashlib.new("sha256")` raises `ValueError: Unsupported hash algorithm`
(verified at the REPL on the desk box; no `adafruit_hashlib` in the vendored
bundle either). The OTA client's `_sha256()` helper — and therefore every
manifest/file verification — would fail on 9.2.8, so 3.x OTA is currently
10.x-only in practice. A new ship-gate for 3.0-on-9.2.8: either vendor
`adafruit_hashlib` into /src/lib, add a CRC32 fallback to the OTA client
(`binascii.crc32` IS present and native on 9.2.8), or confirm a CP build
option restores sha256. Found while deploying the fault-tolerance redesign
over WiFi (the Mac's MSC view of CIRCUITPY never attached media this
session — `CircuitPython Mass Storage` interface enumerated but no IOMedia,
so USB deploy was impossible without hands; the working trees were pulled by
the device itself from a LAN manifest server, crc32-verified, .mpy siblings
removed as .py landed).

**2026-07-19 midday: the redesign is ON the desk box (ship layout) + three
hardware verdicts.** Deploy path: the WiFi pull got the logic running first
(.py); once the owner restored the Mac's CIRCUITPY mount, `WORKTREE=1 MPY=1
scripts/deploy.sh` shipped the tracked working trees properly — new deploy.sh
modes: WORKTREE=1 stages tracked files with their CURRENT contents, and adds
rsync --checksum (fresh staging mtimes otherwise recopy the whole tree over
full-speed USB MSC; the first attempt burned >10 min recopying bit-identical
images). Library on device: 54 .mpy, zero .py. Verified post-boot page:
Status OK, last fetch OK seconds after boot (the new boot-fetch accounting),
watchdog "armed: 120s (RESET)", all three recovery-state rows present.
Verdicts: (1) **retightening a running watchdog fails on CP 9.2.8**
(EINVAL; read-back ambiguous) — the library now arms ONE 120 s window for
boot+runtime, no retighten; (2) **the armed watchdog does not fire in REPL
context on 9.2.8** — sat unfed at a REPL for ~7 min, no bite (matches the
earlier REPL rule; also means a forced-bite test CANNOT be staged from the
REPL — it needs a code-injection boot, or a natural 03:52-style stall during
the soak, which safemode.py will now catch and count in NVM 241);
(3) hashlib-sha256 absence (see the bench-deploy discovery above) makes CRC32
the working integrity primitive on 9.x. Headless soak of the fault-tolerance
redesign starts with this boot; success criteria: fetches keep succeeding,
and if the >60 s stall recurs, the morning page shows "Safe-mode
auto-resets" > 0 with the panel ALIVE rather than dark.

## 2026-07-19 night: the streaming-parse refactor (the fragmentation fix)

Owner's call after the kitchen partial-failure incident: stream the /live
parse. Implemented + 3-model PAL-reviewed (GPT-5.6-Sol / Gemini 3.1 Pro /
Qwen 3.7-Max) same evening. The shape of the fix:
- **HttpClient `get(stream=True)`** → socket-OWNING context-managed
  `StreamingResponse` (`iter_content` chunks; text-only fallback keeps mocks
  and the desktop on the same path; close in `__exit__`; pre-handoff
  exceptions close the native response). The old detach's **eager
  `.content = text.encode()` double copy is gone** (lazy property) — that
  alone had every park body resident TWICE (~180 KB contiguous per 90 KB).
- **`adafruit_json_stream` vendored** into src/lib with two LOCAL patches
  (re-apply on re-vendor): empty-chunk skip in `read()` (native iter_content
  can yield b"" → upstream IndexError), and per-byte set-literal membership
  replaced with int comparisons (hot-path allocation hygiene).
- **`fetch_park_data` streams**: ~512 B chunks → incremental extraction of
  entityType/name/id/status/queue.STANDBY.waitTime per ATTRACTION, same
  `{"liveData": [...]}` shape to the models; ROOT object finished (truncated
  bodies raise instead of passing); malformed SHAPES normalized to
  ValueError so schema surprises never pollute the errno-16 wedge evidence;
  socket always closed in `finally`. Parity-tested at 17 B chunks.
- **Partial ≠ healthy, everywhere**: `note_fetch_result(..., rearm=)` — a
  partial stamps "Last fetch OK" but does NOT clean-run / end the
  failure-reboot epoch (review caught partials still riding the full-health
  re-arms); Status shows `PARTIAL (n/m; failing: ...)`; per-park
  last-updated ages + heap-by-phase on the page; hot 60 s cadence on
  partial; a continuous degraded HOUR → one rate-limited reboot cure.
- **Leak-vs-frag instrumentation** (the owner's gate): `_largest_block`
  ladder now spans 4 KB–256 KB (the old 32 KB cap sat BELOW the observed
  53,737 B failures); heap notes at cycle-start / after-parks / after-build.
  Soak verdict rule: free decaying = leak (hunt it); free flat with
  largest-block healthy = fragmentation fixed, nothing masked.
- Bonus review catch outside the diff: OTA `download_update` serialized the
  whole staged manifest as one string (`manifest.to_json()`) — now
  `json.dump` streams it to flash.
Suites green both repos after fixes. NOT yet deployed — needs a deploy-mode
replug; soak criteria: zero MemoryError, all 4 parks updating, heap free
flat, largest block never below ~64 KB.

**2026-07-20: catalog fetch streams too — the last whole-body allocation is
gone.** `fetch_park_list` (/destinations, ~41 KB) now runs through
`_extract_destinations` + `_iter_chunks`, keeping only the three fields
`ThemeParkList` reads (destination name, park id, park name) and dropping
slug/externalId/etc. Exercises NESTED transients (each destination's `parks`
array consumed inline while active). Root object finished so truncation
raises; malformed shapes normalize to ValueError; socket closed in `finally`;
catalog failures still do NOT feed the wedge classifier (boot-only path,
unchanged). The now-unused `json` import is deleted from the service — NEITHER
fetch path materializes a body or a full dict tree anymore. Verified against
the LIVE API: 140 parks parsed, identical to the whole-body count; parity
tests at 13 B chunks; non-ASCII handling (the ® in "Walt Disney World®
Resort") still stripped identically by the model layer.

**Context for the memory question (2026-07-20):** the box is NOT
memory-constrained — overnight, 49 samples showed 1.2–1.5 MB free with the
largest contiguous block pinned at the probe's 256 KB ceiling in EVERY sample.
The original failure was contiguous-block starvation at 1.37 MB free, i.e.
fragmentation, not capacity. Hence: removing ride animations (largest icon
8 KB, transient, freed on stop) or compiling the app to .mpy (saves flash +
the boot-time compile spike, not steady-state RAM) would NOT have fixed it and
are not needed now. Recorded so the next memory scare starts from the right
question: contiguous or total?

**2026-07-20: OTA unblocked on CP 9.x — dual-checksum manifests.** Owner
cleared modifying OTA (not yet rolled out to customers), so the sha256 gap is
fixed rather than worked around. `scrollkit.ota.client._new_digest()` returns
`(digest, manifest_key)` for the strongest checksum the RUNTIME can compute:
sha256 where present, native `binascii.crc32` on CP 9.2.x where
`hashlib.new("sha256")` raises. Applied at all four verification sites
(download, post-install verify, live-file checksum, and the delta comparison —
which must compare like with like). `make_manifest.py` now emits BOTH
`checksum` (sha256) and `crc32` per file; the device-side validator accepts it
unchanged (extra keys tolerated by design), so old clients keep working.
Rejected the alternative — vendoring pure-python `adafruit_hashlib` — because
hashing a library-sized update in interpreted Python would add minutes of
boot-time CPU; CRC32 is instant and native. This does NOT weaken the trust
model: payloads are unsigned on both paths, so authenticity rests on TLS to
GitHub either way, and the checksum's real job is detecting corrupt/truncated
downloads. Verification is NEVER skipped: a manifest carrying no digest the
runtime can compute raises a named OTAError (`_expected`), pinned by tests.
Library suite 945 green (9 new).
