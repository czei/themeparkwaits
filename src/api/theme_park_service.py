"""
Service for fetching and managing theme park data.
Copyright (c) 2024-2026 Michael Czeiszperger
"""
import asyncio
import gc

from src.models.theme_park_list import ThemeParkList
from src.models.vacation import Vacation
from scrollkit.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")


def _close_response(response):
    """Release an HTTP response's socket; safe on any response type or None.

    The ESP32-S3 socket pool holds only ~4 sockets, so a leaked
    ``adafruit_requests`` response quickly exhausts it and pushes the client into
    ``OutOfRetries`` / connection hangs — a prime suspect for the field "frozen /
    black screen" reports. Desktop (urllib/mock) responses already close cleanly;
    this just makes the release explicit and unconditional."""
    if response is not None and hasattr(response, "close"):
        try:
            response.close()
        except Exception:
            pass


def _largest_block():
    """Best-effort size (bytes) of the largest contiguous block we can allocate.

    CircuitPython's GC is non-compacting, so ``gc.mem_free()`` can report over a
    megabyte free while no single ~54 KB span exists (the 2026-07-19 kitchen
    failure: big-park bodies dying at 53,737 B with 1.37 MB free). Probing a
    ladder of sizes tells fragmentation (ample free, small largest block) apart
    from a leak/exhaustion (little free at all) — the owner's gate for the
    streaming refactor. The old ladder topped out at 32 KB, BELOW the observed
    failure sizes, so it could never see the zone that mattered; it now spans
    4 KB–256 KB. Each probe is freed immediately; returns 0 if even 4 KB won't
    allocate. Run sparingly (once per cycle/error) — the probe itself briefly
    perturbs the heap."""
    for size in (262144, 131072, 98304, 65536, 49152, 32768,
                 24576, 16384, 8192, 4096):
        try:
            probe = bytearray(size)
        except MemoryError:
            continue
        else:
            del probe
            return size
    return 0


def _heap_note():
    """One-line heap snapshot for the log, or '' where gc.mem_free is absent (desktop)."""
    try:
        return "%d free, largest block >=%d B" % (gc.mem_free(), _largest_block())
    except Exception:      # gc.mem_free() is device-only; desktop/tests skip the note
        return ""


def _iter_chunks(response, chunk_size=512):
    """Bytes chunks from ANY response shape.

    Native/StreamingResponse expose ``iter_content`` (true streaming); desktop
    mocks and recording stubs carry only ``.text`` — those yield the whole body
    as one chunk, keeping every backend on the SAME parse path (the OTA
    client's proven fallback idiom)."""
    it = getattr(response, "iter_content", None)
    if it is not None:
        return it(chunk_size)
    text = getattr(response, "text", "") or ""
    return iter((text.encode("utf-8"),))


def _extract_destinations(chunks):
    """Incrementally extract the park catalog from a /destinations byte stream.

    Returns the SAME ``{"destinations": [{"name", "parks": [{"id", "name"}]}]}``
    shape ``ThemeParkList`` already consumes, carrying only the three fields it
    reads (destination name + each park's id/name) and dropping slug/externalId
    and every other key. Peak allocation is one chunk + the accumulating park
    list, never the ~41 KB body string or its full dict tree — the last
    whole-body allocation in the app (2026-07-20). Destinations with no usable
    parks are omitted: ``ThemeParkList`` only ever appends parks, so they
    contribute nothing but RAM. Nested transients (each destination's ``parks``
    array) are consumed inline while active, which the parser supports.
    Raises KeyError/ValueError/EOFError on malformed payloads."""
    import adafruit_json_stream as json_stream
    try:
        obj = json_stream.load(chunks)
        dests = []
        for dest in obj["destinations"]:
            dname = None
            parks = []
            for key, value in dest.items():
                if key == "name":
                    dname = value
                elif key == "parks":
                    for entry in value:
                        pid = pname = None
                        for pkey, pval in entry.items():
                            if pkey == "id":
                                pid = pval
                            elif pkey == "name":
                                pname = pval
                        if pid and pname:
                            parks.append({"id": pid, "name": pname})
            if parks:
                dests.append({"name": dname or "", "parks": parks})
        # Finish the ROOT object so a truncated body raises instead of passing
        # as a short-but-valid catalog (same contract as _extract_live_rides).
        if hasattr(obj, "finish"):
            obj.finish()
        return {"destinations": dests}
    except (AttributeError, TypeError, BufferError) as e:
        # Valid JSON, wrong SHAPE -> normalize to the parse-failure class.
        raise ValueError("malformed destinations payload: %s" % e)


def _extract_live_rides(chunks):
    """Incrementally extract ATTRACTION entries from a /live JSON byte stream.

    Returns the SAME ``{"liveData": [...]}`` shape the old whole-tree
    ``json.loads`` produced — each entry a minimal dict of the four fields the
    model layer reads (entityType/name/id/status + queue.STANDBY.waitTime) —
    so ``ThemePark.get_rides_from_json`` is unchanged. Peak allocation is one
    chunk + one small entry, never the ~50-90 KB body string or its full dict
    tree: holding those (twice, with the old eager ``.content`` copy) between
    long-lived UI/model objects is what shattered the non-compacting heap
    (2026-07-19 kitchen failure). Field order within each item doesn't matter:
    keys are consumed in stream order via ``items()``; non-attractions are
    abandoned at ``entityType`` and the stream skips the rest of the item.
    Raises KeyError/ValueError/EOFError on malformed payloads — callers treat
    those as parse failures."""
    import adafruit_json_stream as json_stream
    try:
        obj = json_stream.load(chunks)
        rides = []
        for item in obj["liveData"]:
            etype = name = rid = status = None
            queue = None
            for key, value in item.items():
                if key == "entityType":
                    etype = value
                    if etype != "ATTRACTION":
                        break      # stream auto-skips the rest of this item
                elif key == "name":
                    name = value
                elif key == "id":
                    rid = value
                elif key == "status":
                    status = value
                elif key == "queue":
                    # The queue subtree is tiny (~100 B) — materialize it whole
                    # so STANDBY position within it never matters.
                    queue = value.as_object() if hasattr(value, "as_object") else value
            if etype != "ATTRACTION":
                continue
            entry = {"entityType": etype, "name": name, "id": rid, "status": status}
            if isinstance(queue, dict):
                std = queue.get("STANDBY")
                if isinstance(std, dict):
                    entry["queue"] = {"STANDBY": {"waitTime": std.get("waitTime")}}
            rides.append(entry)
        # Finish the ROOT object: drains trailing keys and demands the closing
        # brace, so a body truncated after a well-formed liveData array raises
        # (EOFError) instead of passing as a silent success (review 2026-07-19).
        if hasattr(obj, "finish"):
            obj.finish()
        return {"liveData": rides}
    except (AttributeError, TypeError, BufferError) as e:
        # Valid JSON, wrong SHAPE (scalar root, non-object liveData entries...):
        # normalize to the parse-failure class so callers retry WITHOUT feeding
        # last_refresh_errors — schema surprises are not reset-curable wedge
        # evidence, and blanket-catching these at the fetch level would hide
        # real implementation bugs elsewhere.
        raise ValueError("malformed live payload: %s" % e)


class ThemeParkService:
    """
    Service for fetching and managing theme park data
    """
    
    def __init__(self, http_client, settings_manager):
        """
        Initialize the theme park service
        
        Args:
            http_client: The HTTP client to use for requests
            settings_manager: The settings manager
        """
        self.http_client = http_client
        self.settings_manager = settings_manager
        self.park_list = None
        self.vacation = Vacation()
        # Optional callable set by the app to pet the hardware watchdog between
        # sequential park fetches (a multi-park refresh blocks the event loop
        # longer than the watchdog timeout). None off-device / when disabled.
        self.watchdog_feed = None
        # Terminal error strings from the most recent update_selected_parks()
        # run (bounded). The app classifies these after each refresh: a park
        # that died with errno 16 (EBUSY, the selective-wedge signature) must
        # count as wedge evidence EVEN IF another park succeeded on a surviving
        # pooled socket — partial success masking the wedge is how the box sat
        # degraded for hours with its failure counter at zero (2026-07-16).
        self.last_refresh_errors = []
        # Per-park visibility (2026-07-19: three big parks failed for hours
        # behind an all-green dashboard). Names that failed the CURRENT run,
        # and per-park last-success stamps for the diagnostics page.
        self.last_failed_parks = []
        self.park_last_updated = {}    # park id -> time.monotonic() of last success
        # Heap telemetry per refresh phase (the leak-vs-fragmentation gate):
        # phase name -> _heap_note() string; rendered on the diagnostics page.
        self.heap_stats = {}

    async def initialize(self):
        """Initialize the service by fetching park list and setting clock"""
        # Track initialization steps for better error reporting
        steps_completed = []

        try:
            # Step 1: Load vacation data from settings
            try:
                self.vacation.load_settings(self.settings_manager)
                steps_completed.append("vacation_loaded")
                logger.info("Vacation data loaded from settings")
            except Exception as vacation_error:
                logger.error(vacation_error, "Error loading vacation data")

            # Step 2: Fetch park list from URL (skipping the check since we need data first)
            # Note: This code was trying to create an empty ThemeParkList without data
            # Let the fetch_park_list code below handle the actual creation

            # Step 3: Fetch the park list
            for attempt in range(3):  # Multiple attempts for park list
                try:
                    logger.info(f"Attempting to fetch park list (attempt {attempt+1}/3)")
                    await self.fetch_park_list()
                    if self.park_list and self.park_list.park_list:
                        steps_completed.append("fetch_park_list")
                        logger.info(f"Successfully fetched {len(self.park_list.park_list)} parks on attempt {attempt+1}")
                        break
                    else:
                        logger.error(None, f"Park list fetch attempt {attempt+1} returned empty list")
                        # Small delay before retrying
                        await asyncio.sleep(3)
                except Exception as list_error:
                    logger.error(list_error, f"Error fetching park list on attempt {attempt+1}/3")
                    await asyncio.sleep(3)
            
            # Create empty park list if all attempts failed
            if "fetch_park_list" not in steps_completed:
                logger.info("Creating empty park list as fallback after failed attempts")
                self.park_list = ThemeParkList([])
            
            # Step 3: Load settings (even for empty park list)
            if self.park_list:
                self.park_list.load_settings(self.settings_manager)
                steps_completed.append("load_park_settings")
                
            # Step 4: Load vacation settings
            self.vacation.load_settings(self.settings_manager)
            steps_completed.append("load_vacation_settings")
            
            # Log initialization success/partial success
            if len(steps_completed) >= 3:  # Clock setting might fail but that's ok
                logger.info(f"Theme park service initialized. Steps completed: {', '.join(steps_completed)}")
            else:
                logger.error(None, f"Theme park service partially initialized. Steps completed: {', '.join(steps_completed)}")
            
        except Exception as e:
            logger.error(e, f"Error initializing theme park service. Steps completed: {', '.join(steps_completed)}")
            
            # Create park list if it doesn't exist yet (failsafe)
            if self.park_list is None:
                self.park_list = ThemeParkList([])
                logger.info("Created empty park list as failsafe after initialization error")
            
    async def fetch_park_list(self):
        """
        Fetch the list of theme parks, STREAMING the body (2026-07-20).

        The ~41 KB /destinations catalog was the last whole-body allocation in
        the app: read as one contiguous string and json.loads'd into a full
        dict tree to keep three fields per park. It runs once at boot on a
        clean heap so it never failed in the field, but it is the same
        fragmentation-driving shape the /live path shed. Now chunked through
        the incremental extractor; the socket is ALWAYS released in ``finally``.

        Returns:
            A ThemeParkList object (empty if every attempt failed)
        """
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            response = None
            try:
                url = "https://api.themeparks.wiki/v1/destinations"
                logger.info(f"Fetching park list from {url} (attempt {retry_count + 1}/{max_retries})")

                gc.collect()  # free heap before the TLS socket
                response = await self.http_client.get(url, stream=True)

                status = getattr(response, "status_code", 200)
                if not response or status != 200:
                    logger.error(None, f"HTTP {status} fetching park list (attempt {retry_count + 1})")
                    retry_count += 1
                    await asyncio.sleep(1)
                    continue

                data = _extract_destinations(_iter_chunks(response))
                gc.collect()   # drop parser transients before building models

                # Create park list
                self.park_list = ThemeParkList(data)

                # Verify park list has parks
                if not self.park_list.park_list:
                    logger.error(None, f"Park list created but no parks were found (attempt {retry_count + 1})")
                    retry_count += 1
                    await asyncio.sleep(1)
                    continue

                logger.info(f"Successfully fetched {len(self.park_list.park_list)} parks")
                return self.park_list

            except (ValueError, KeyError, EOFError) as parse_error:
                # Malformed/truncated catalog: retry. Catalog failures never fed
                # the wedge classifier (boot-only path) — unchanged here.
                logger.error(parse_error, f"JSON decode error for park list (attempt {retry_count + 1})")
                retry_count += 1
                await asyncio.sleep(1)

            except Exception as e:
                note = _heap_note()
                logger.error(e, "Error fetching park list (attempt %d)%s"
                             % (retry_count + 1, (" [heap: " + note + "]") if note else ""))
                retry_count += 1
                await asyncio.sleep(1)

            finally:
                # ALWAYS release the (socket-owning) streaming response.
                _close_response(response)
                response = None

        # All retries failed
        logger.error(None, f"Failed to fetch park list after {max_retries} attempts")

        # Create empty park list as fallback
        self.park_list = ThemeParkList([])
        return self.park_list
            
    async def fetch_park_data(self, park_id):
        """
        Fetch data for a specific park, STREAMING the body (2026-07-19).

        The old path read the ~50-90 KB body as one contiguous string (held
        twice, with the client's eager bytes copy) and json.loads'd the whole
        tree to keep four fields per ride — the prime fragmentation driver on
        the non-compacting CP9 heap. This path consumes the socket in ~512 B
        chunks through an incremental parser and never materializes the body.
        The socket is ALWAYS released in ``finally`` (a leaked socket exhausts
        the ~4-socket pool — the old EBUSY wedge); parse errors retry without
        polluting the wedge-classifier evidence, network/memory errors retry
        AND surface in ``last_refresh_errors``.

        Args:
            park_id: The ID of the park

        Returns:
            ``{"liveData": [minimal ride dicts]}`` (the shape the model layer
            already consumes), or None if every attempt failed
        """
        max_retries = 2
        retry_count = 0

        while retry_count < max_retries:
            response = None
            try:
                # themeparks.wiki live data endpoint for a single park
                url = f"https://api.themeparks.wiki/v1/entity/{park_id}/live"
                logger.info(f"Fetching data for park ID {park_id} from {url} (attempt {retry_count + 1}/{max_retries})")

                # Reclaim heap before the TLS socket. The yield between the two
                # collects lets the display loop run the outgoing content's async
                # stop() — freeing its intro overlay/writable bitmaps — so those
                # aren't still held when adafruit allocates the TLS socket.
                # Verified on hardware (pre-streaming): every-attempt MemoryError
                # -> 11/11 fetches. Still required: the TLS handshake itself
                # needs contiguous room regardless of how we read the body.
                gc.collect()
                await asyncio.sleep(0)
                gc.collect()
                response = await self.http_client.get(url, stream=True)

                status = getattr(response, "status_code", 200)
                if not response or status != 200:
                    logger.error(None, f"HTTP {status} fetching park data (attempt {retry_count + 1})")
                    retry_count += 1
                    if retry_count < max_retries:
                        await asyncio.sleep(0.5)
                    continue

                data = _extract_live_rides(_iter_chunks(response))
                gc.collect()   # drop parser transients before the model rebuild
                logger.info(f"Successfully fetched data for park ID {park_id}")
                return data

            except (ValueError, KeyError, EOFError) as parse_error:
                # Malformed/truncated body: retry, but do NOT feed
                # last_refresh_errors — a bad payload is not reset-curable
                # evidence (wedge classifier reads that list).
                logger.error(parse_error, f"JSON decode error for park data (attempt {retry_count + 1})")
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(0.5)

            except Exception as e:
                note = _heap_note()
                logger.error(e, "Error fetching park data for park ID %s (attempt %d)%s"
                             % (park_id, retry_count + 1,
                                (" [heap: " + note + "]") if note else ""))
                try:  # surface the terminal error for the app's wedge classifier
                    self.last_refresh_errors.append(str(e))
                    del self.last_refresh_errors[:-8]     # bound the evidence list
                except Exception:
                    pass
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(0.5)

            finally:
                # ALWAYS release the (socket-owning) streaming response — on
                # success, parse failure, and network failure alike.
                _close_response(response)
                response = None

        # All retries failed
        logger.error(None, f"Failed to fetch park data for park ID {park_id} after {max_retries} attempts")
        return None
            
    async def update_current_park(self):
        """
        Update the currently selected park with fresh data

        Returns:
            True if successful, False otherwise
        """
        if not self.park_list or not self.park_list.current_park.is_valid():
            logger.debug("No valid current park to update")
            return False

        try:
            park_data = await self.fetch_park_data(self.park_list.current_park.id)
            if park_data:
                self.park_list.current_park.update(park_data)
                return True
            return False

        except Exception as e:
            logger.error(e, "Error updating current park")
            return False
            
    async def update_selected_parks(self):
        """
        Update all selected parks with fresh data

        Returns:
            Number of parks successfully updated
        """
        if not self.park_list or not self.park_list.selected_parks:
            logger.debug("No selected parks to update")
            return 0

        total_parks = len(self.park_list.selected_parks)
        self.last_refresh_errors = []   # fresh evidence set for this run
        self.last_failed_parks = []
        note = _heap_note()             # leak-vs-frag telemetry (device-only)
        if note:
            self.heap_stats["cycle start"] = note
            logger.info("heap @ cycle start: " + note)

        logger.info(f"Starting sequential update of {total_parks} selected parks")

        # Fetch parks one at a time (NOT asyncio.gather). themeparks.wiki's /live
        # payload is ~90 KB/park; fetching all parks concurrently would hold every
        # raw payload in RAM at once (~370 KB for 4 parks). Doing them sequentially
        # and collecting garbage between parks keeps peak memory to a single payload
        # on the constrained device (research D8 / R1). HTTP is synchronous anyway,
        # so this is no slower. _update_single_park swallows its own errors, so a
        # bad park can't abort the batch.
        updated_count = 0
        for park in self.park_list.selected_parks:
            if await self._update_single_park(park):
                updated_count += 1
            gc.collect()
            # Keep the watchdog fed across a long multi-park refresh; a single
            # hung socket is already bounded by the request timeout (< watchdog).
            if self.watchdog_feed is not None:
                self.watchdog_feed()

        note = _heap_note()
        if note:
            self.heap_stats["after parks"] = note
            logger.info("heap @ after parks: " + note)
        logger.info(f"Updated {updated_count}/{total_parks} selected parks")
        return updated_count
    
    async def _update_single_park(self, park):
        """
        Update a single park with error handling
        
        Args:
            park: The park to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.debug(f"Updating park: {park.name} (ID: {park.id})")
            park_data = await self.fetch_park_data(park.id)
            if park_data:
                park.update(park_data)
                try:
                    import time
                    self.park_last_updated[park.id] = time.monotonic()
                except Exception:
                    pass
                logger.debug(f"Successfully updated park: {park.name}")
                return True
            else:
                logger.error(None, f"Failed to fetch data for park: {park.name}")
                self.last_failed_parks.append(park.name)
                return False
        except Exception as e:
            logger.error(e, f"Error updating park: {park.name}")
            try:
                self.last_failed_parks.append(park.name)
            except Exception:
                pass
            return False

