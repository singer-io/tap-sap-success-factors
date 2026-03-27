"""stream_probe.py — Discovery-time probing to exclude unsupported streams.

Each entity set is probed with a minimal ``$top=1`` request immediately after
EDMX metadata discovery.  Streams that return any 4xx or 5xx HTTP status are
logged and removed from the catalog before it is emitted so downstream
connectors never attempt to sync data from endpoints that SAP rejects.

Design decisions
----------------
* Uses ``requests.get`` directly (not the shared tap client session) so that:
  - Probes are thread-safe — each worker creates its own connection.
  - No backoff/retry decorators delay threads on expected 400s.
  - Raw HTTP status codes are visible without ``raise_for_error`` masking.
* Any 4xx or 5xx response is treated as a permanent exclusion.
  Network errors and timeouts are logged as warnings but the stream is kept
  in the catalog (conservative / non-destructive default).
* Parallelism via ``concurrent.futures.ThreadPoolExecutor``; default 20 workers
  probes 466 streams in roughly 30 s wall-clock time on typical SAP instances.

Filter replication
------------------
The probe replicates the same request shape that sync uses so that streams
are not falsely excluded because they require a mandatory filter:

* **Child streams** (have ``parent_filter_field``) — probed with
  ``$filter=<parent_filter_field> eq '<config_username>'``.  Using the
  configured username as a real (if minimal) filter value allows SAP to
  evaluate the full permission chain, so HTTP 403 (permission / feature
  block) is returned instead of HTTP 400 ("field cannot be null").
  All 4xx/5xx responses are excluded, same as direct streams.
* **INCREMENTAL streams** (have ``replication_keys``) — probed with
  ``$filter=<rep_key> ge datetime'<start_date>'`` mirroring the sync filter.
* **Expand-only streams** (have ``expand_parent_entity_set``) — skipped.
  They are fetched via OData ``$expand`` on a parent entity set, not by
  direct query, so a direct probe would always fail (COE0025/COE0018).
* All other streams — probed with bare ``$top=1`` (FULL_TABLE, no filter).

"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional, Set

import requests
import singer

LOGGER = singer.get_logger()

# Per-probe request timeout in seconds.  Short because each probe is $top=1.
PROBE_TIMEOUT = 20

# Maximum number of concurrent probe threads.
PROBE_MAX_WORKERS = 20


# ---------------------------------------------------------------------------
# Single-stream probe
# ---------------------------------------------------------------------------

def probe_stream(
    auth_header: str,
    base_url: str,
    stream_name: str,
    path: str,
    extra_params: Optional[Dict] = None,
) -> Dict:
    """Send a ``$top=1`` GET to one entity set and return a status descriptor.

    Parameters
    ----------
    auth_header:
        Full ``Authorization`` header value (``Basic …`` or ``Bearer …``).
    base_url:
        Tap client base URL, e.g. ``https://api.successfactors.eu``.
    stream_name:
        Singer tap_stream_id, used as a label in the returned dict.
    path:
        OData entity set path relative to *base_url*, e.g.
        ``/odata/v2/Currency``.
    extra_params:
        Additional OData query parameters merged into the probe request,
        e.g. ``{"$filter": "lastModifiedDateTime ge datetime'2000-01-01T00:00:00Z'"}``.
        Used to replicate the filter shape that sync would apply so that
        streams requiring mandatory filters are not falsely excluded.

    Returns
    -------
    dict with keys:
        ``stream``  – tap_stream_id label.
        ``status``  – HTTP status code (int) or ``None`` on network error.
        ``error``   – First 300 chars of response body for 4xx/5xx responses,
                      exception message for network errors, else ``None``.
    """
    url = f"{base_url}{path}"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
    }
    params: Dict = {
        "$top": "1",
        "$format": "json",
    }
    if extra_params:
        params.update(extra_params)

    try:
        response = requests.get(
            url, headers=headers, params=params, timeout=PROBE_TIMEOUT
        )
        error_snippet = None
        if 400 <= response.status_code <= 599:
            error_snippet = (response.text[:300] if response.text else "(no body)")
        return {
            "stream": stream_name,
            "status": response.status_code,
            "error": error_snippet,
        }
    except requests.exceptions.Timeout:
        LOGGER.warning("Probe timed out for stream '%s' (%s)", stream_name, url)
        return {"stream": stream_name, "status": None, "error": "timeout"}
    except requests.exceptions.RequestException as exc:
        LOGGER.warning(
            "Probe network error for stream '%s': %s", stream_name, exc
        )
        return {"stream": stream_name, "status": None, "error": str(exc)}


# ---------------------------------------------------------------------------
# Parallel probe orchestrator
# ---------------------------------------------------------------------------

def _probe_filter_value(field_schema, username):
    """Return a type-appropriate OData RHS clause for a child probe filter.

    Builds the ``<op> <value>`` portion of
    ``$filter=<parent_filter_field> <op> <value>`` so that SAP can evaluate
    the expression without a type-validation error (HTTP 400), while still
    triggering any permission checks that surface as HTTP 403.

    * ``integer`` / ``number`` fields  → ``eq 0``
    * ``date-time`` fields → ``ge datetime'2000-01-01T00:00:00'``
    * ``string`` / unknown → ``eq '<username>'``
    """
    types = field_schema.get("type", [])
    if isinstance(types, str):
        types = [types]
    if "integer" in types or "number" in types:
        return "eq 0"
    if field_schema.get("format") == "date-time":
        return "ge datetime'2000-01-01T00:00:00'"
    return f"eq '{username}'"


# OData error codes that indicate a child stream genuinely cannot be queried
# via $filter even at sync time.  All other 400s are type-mismatch / value-not-
# found false positives that will succeed with real parent key values.
_CHILD_GENUINE_400_CODES = frozenset({
    "COE_BAD_PROPERTY_EXPRESSION",  # COE0003: field not filterable
    "COE_UNSUPPORTED_FEATURE",       # COE0025: stream not directly queryable
})


def _extract_odata_error_code(error_text):
    """Extract the SAP OData error code from a probe response snippet."""
    try:
        import json as _json  # local import to avoid circular at module level
        body = _json.loads(error_text)
        return body.get("error", {}).get("code", "")
    except Exception:  # pylint: disable=broad-except
        return ""


def probe_all_streams(
    client,
    stream_defs: Dict,
    max_workers: int = PROBE_MAX_WORKERS,
) -> Set[str]:
    """Probe every stream in *stream_defs* in parallel; return excluded names.

    Each stream is probed via :func:`probe_stream`.  Streams whose endpoint
    returns any 4xx or 5xx HTTP status are added to the returned ``excluded``
    set.  Network errors and timeouts are logged but do **not** result in
    exclusion — the stream stays in the catalog.

    Parameters
    ----------
    client:
        Initialised :class:`~tap_sap_success_factors.client.SAPSuccessFactorsClient`.
        Used only to obtain ``base_url`` and the current auth header.
    stream_defs:
        Mapping of ``{stream_name: stream_def_dict}`` as returned by
        :func:`~tap_sap_success_factors.metadata_discovery.discover_dynamic_streams`.
        Each ``stream_def_dict`` must contain a ``"path"`` key.
    max_workers:
        Maximum number of concurrent probe threads (default: 20).

    Returns
    -------
    set[str]
        Snake-case stream names that returned any 4xx or 5xx status and should
        be excluded from the emitted catalog.
    """
    auth_header = client.get_auth_header()
    base_url = client.base_url
    start_date = client.config.get("start_date", "2000-01-01T00:00:00Z")
    username = client.config.get("user_id", "__probe_user__")

    # Classify streams into three buckets:
    #   probeable       — direct query streams (all non-child, non-expand).
    #   child_probeable — child streams probed with a config-username filter
    #                     so SAP evaluates the full permission chain.
    #                     All 4xx/5xx excluded (same rule as direct streams).
    #   skipped_expand  — expand-only streams; direct queries always fail.
    probeable: Dict[str, Dict] = {}
    child_probeable: Dict[str, Dict] = {}
    skipped_expand = 0
    for stream_name, stream_def in stream_defs.items():
        if stream_def.get("expand_parent_entity_set"):
            # Expand-only stream — probing the entity set directly would
            # always fail with COE0025/COE0018; skip probe.
            skipped_expand += 1
            continue
        if stream_def.get("parent_filter_field"):
            # Child stream — probe with config-username filter.
            child_probeable[stream_name] = stream_def
            continue
        probeable[stream_name] = stream_def

    total = len(probeable) + len(child_probeable)
    LOGGER.info(
        "Starting discovery probe for %d streams "
        "(%d direct, %d child streams probed with filter, "
        "%d expand-only streams skipped). "
        "max_workers=%d, timeout=%ds per probe.",
        total,
        len(probeable),
        len(child_probeable),
        skipped_expand,
        max_workers,
        PROBE_TIMEOUT,
    )

    excluded: Set[str] = set()
    # futures maps future → (stream_name, is_child)
    futures: Dict = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for stream_name, stream_def in probeable.items():
            # For INCREMENTAL streams replicate the $filter sync would use.
            # Without it SAP rejects the request with HTTP 400 for streams
            # that mandate a date filter (e.g. ExternalLearner).
            extra_params: Optional[Dict] = None
            rep_keys = stream_def.get("replication_keys") or []
            if rep_keys:
                rep_key = rep_keys[0]
                extra_params = {
                    "$filter": (
                        f"{rep_key} ge datetime'{start_date}'"
                    )
                }
            future = executor.submit(
                probe_stream,
                auth_header,
                base_url,
                stream_name,
                stream_def["path"],
                extra_params,
            )
            futures[future] = (stream_name, False)

        for stream_name, stream_def in child_probeable.items():
            # Probe with a type-appropriate filter value so SAP evaluates
            # the full permission chain without a type-validation 400:
            #   string field  → eq '<user_id from config>'
            #   integer field → eq 0
            #   datetime field → ge datetime'2000-01-01T00:00:00'
            # This means only genuine permission/feature 403s (or other
            # non-type-error 4xx/5xx) trigger exclusion.
            pff = stream_def["parent_filter_field"]
            pff_schema = stream_def.get("parent_filter_field_schema", {})
            filter_clause = _probe_filter_value(pff_schema, username)
            child_filter = {"$filter": f"{pff} {filter_clause}"}
            future = executor.submit(
                probe_stream,
                auth_header,
                base_url,
                stream_name,
                stream_def["path"],
                child_filter,
            )
            futures[future] = (stream_name, True)

        done_count = 0
        for future in as_completed(futures):
            result = future.result()
            stream_name, is_child = futures[future]
            done_count += 1

            status = result["status"]
            # Direct streams: exclude all 4xx/5xx.
            # Child streams: exclude 403/5xx unconditionally; exclude 400
            # only for COE0003 (field not filterable) and COE0025 (stream
            # not queryable) — these will always fail at sync time too.
            # All other child 400s are false positives (type-precision
            # mismatches, value-not-found) that work with real parent keys.
            if is_child and status == 400:
                error_code = _extract_odata_error_code(
                    result.get("error") or ""
                )
                is_excluded = error_code in _CHILD_GENUINE_400_CODES
            else:
                is_excluded = (
                    status is not None and 400 <= status <= 599
                )
            if is_excluded:
                LOGGER.warning(
                    "[Probe] Excluding%s stream '%s' — HTTP %s: %s",
                    " child" if is_child else "",
                    result["stream"],
                    result["status"],
                    result["error"],
                )
                excluded.add(result["stream"])
            elif result["status"] is None:
                LOGGER.warning(
                    "[Probe] Stream '%s' probe failed (network/timeout) — "
                    "keeping in catalog. Error: %s",
                    result["stream"],
                    result["error"],
                )
            else:
                LOGGER.debug(
                    "[Probe] Stream '%s' → HTTP %s",
                    result["stream"],
                    result["status"],
                )

            if done_count % 50 == 0 or done_count == total:
                LOGGER.info(
                    "[Probe] Progress: %d/%d probes completed "
                    "(%d excluded so far)",
                    done_count,
                    total,
                    len(excluded),
                )

    LOGGER.info(
        "Discovery probe complete: %d/%d streams excluded "
        "(direct: HTTP 4xx/5xx; "
        "child: 403/5xx or 400 COE0003/COE0025)",
        len(excluded),
        total,
    )

    # ------------------------------------------------------------------
    # Propagate exclusions to expand-only children.
    #
    # An expand-only stream is synced by querying its expand_parent_entity_set
    # via OData $expand.  If the parent entity set's probe returned HTTP 400
    # (i.e. its stream is in ``excluded``), the expand-only child is also
    # unsyncable and must be excluded too.
    #
    # Example:
    #   form_custom_element       → HTTP 400 (excluded by probe)
    #   form_custom_element_list_value  expand_parent=FormCustomElement
    #   → sync hits FormCustomElement → also 400 → must be excluded.
    #
    # Build entity-set → stream-name reverse map for the lookup.
    # ------------------------------------------------------------------
    entity_set_to_stream = {
        sd["entity_set"]: sname
        for sname, sd in stream_defs.items()
        if sd.get("entity_set")
    }
    cascade_excluded: Set[str] = set()
    for stream_name, stream_def in stream_defs.items():
        parent_es = stream_def.get("expand_parent_entity_set")
        if not parent_es:
            continue
        parent_stream = entity_set_to_stream.get(parent_es)
        if parent_stream and parent_stream in excluded:
            LOGGER.warning(
                "[Probe] Excluding expand-only stream '%s' — its expand "
                "parent '%s' (entity set '%s') was excluded (HTTP 4xx/5xx).",
                stream_name,
                parent_stream,
                parent_es,
            )
            cascade_excluded.add(stream_name)

    if cascade_excluded:
        LOGGER.info(
            "[Probe] Cascade-excluded %d expand-only streams "
            "whose expand parent returned HTTP 4xx/5xx.",
            len(cascade_excluded),
        )
        excluded |= cascade_excluded

    return excluded
