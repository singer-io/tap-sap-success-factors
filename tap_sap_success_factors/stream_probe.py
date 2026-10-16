"""stream_probe.py — Discovery-time probing to exclude unsupported streams.

Each entity set is probed with a minimal ``$top=1`` request immediately after
EDMX metadata discovery. Unreadable streams are removed from the catalog;
rejected optional navigation expansions disable only their flattened fields
when the base entity remains readable.

Design decisions
----------------
* Uses ``requests.get`` directly (not the shared tap client session) so that:
  - Probes are thread-safe — each worker creates its own connection.
  - No backoff/retry decorators delay threads on expected 400s.
  - Raw HTTP status codes are visible without ``raise_for_error`` masking.
* Direct base-query 4xx/5xx responses and child 403/5xx or known-unqueryable
    400 responses exclude the stream. Network errors and timeouts are logged as
    warnings but the stream is kept in the catalog.
* If a request with optional navigation expansions fails, the base query and
    each navigation are probed separately. A readable base stream is retained;
    rejected navigation fields are marked unsupported before catalog emission.
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
    HTTP 403/5xx and known-unqueryable 400 responses are excluded; other 400s
    are treated as possible filter-value false positives.
* **INCREMENTAL streams** (have ``replication_keys``) — probed with
  ``$filter=<rep_key> ge datetime'<start_date>'`` mirroring the sync filter.
* **Expand-only streams** (have ``expand_parent_entity_set``) — skipped.
  They are fetched via OData ``$expand`` on a parent entity set, not by
  direct query, so a direct probe would always fail (COE0025/COE0018).
* All other streams — probed with bare ``$top=1`` (FULL_TABLE, no filter).

"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Set

import backoff
import requests
import singer

LOGGER = singer.get_logger()

# Per-probe request timeout in seconds.  Short because each probe is $top=1.
PROBE_TIMEOUT = 20

# Maximum number of concurrent probe threads.
PROBE_MAX_WORKERS = 20

# Total attempts per probe (1 initial + 2 retries) on Timeout.
PROBE_MAX_TRIES = 3


# ---------------------------------------------------------------------------
# Single-stream probe
# ---------------------------------------------------------------------------

@backoff.on_exception(
    backoff.expo,
    requests.exceptions.Timeout,
    max_tries=PROBE_MAX_TRIES,
    factor=2,
    logger=LOGGER,
)
def _request_with_retry(url, headers, params):
    """Make a single GET request, retrying on Timeout via backoff.

    Lets ``requests.exceptions.Timeout`` propagate so the backoff decorator
    can intercept and schedule retries with exponential back-off.  After all
    ``PROBE_MAX_TRIES`` attempts are exhausted the exception is re-raised and
    must be caught by the caller (:func:`probe_stream`).
    """
    return requests.get(
        url, headers=headers, params=params, timeout=PROBE_TIMEOUT
    )


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
        response = _request_with_retry(url, headers, params)
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
        body = json.loads(error_text)
        return body.get("error", {}).get("code", "")
    except Exception:  # pylint: disable=broad-except
        return ""


def _probe_result_excludes_stream(result: Dict, is_child: bool) -> bool:
    status = result["status"]
    if is_child and status == 400:
        return _extract_odata_error_code(
            result.get("error") or ""
        ) in _CHILD_GENUINE_400_CODES
    return status is not None and 400 <= status <= 599


def probe_all_streams(
    client,
    stream_defs: Dict,
    max_workers: int = PROBE_MAX_WORKERS,
) -> Set[str]:
    """Probe every stream in *stream_defs* in parallel; return excluded names.

    Each stream is probed via :func:`probe_stream`. Unreadable base endpoints
    are returned in ``excluded``. If optional navigation expansions fail but
    the base request succeeds, the stream is retained and its
    ``stream_def`` is updated with supported and rejected navigation lists.
    Network errors and timeouts do **not** result in exclusion.

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
        Snake-case stream names whose base endpoint is not queryable and should
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
    #                     403/5xx and known-unqueryable 400s are excluded.
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
    futures: Dict = {}
    initial_results: Dict[str, Dict] = {}

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
            base_params = dict(extra_params or {})
            flatten_navs = stream_def.get("flatten_nav_properties") or []
            request_params = dict(base_params)
            if flatten_navs:
                request_params["$expand"] = ",".join(flatten_navs)
            future = executor.submit(
                probe_stream,
                auth_header,
                base_url,
                stream_name,
                stream_def["path"],
                request_params or None,
            )
            futures[future] = (stream_name, False, flatten_navs, base_params)

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
            base_params = {"$filter": f"{pff} {filter_clause}"}
            flatten_navs = stream_def.get("flatten_nav_properties") or []
            child_filter = dict(base_params)
            if flatten_navs:
                child_filter["$expand"] = ",".join(flatten_navs)
            future = executor.submit(
                probe_stream,
                auth_header,
                base_url,
                stream_name,
                stream_def["path"],
                child_filter,
            )
            futures[future] = (stream_name, True, flatten_navs, base_params)

        done_count = 0
        for future in as_completed(futures):
            result = future.result()
            stream_name, is_child, flatten_navs, base_params = futures[future]
            initial_results[stream_name] = {
                "result": result,
                "is_child": is_child,
                "flatten_navs": flatten_navs,
                "base_params": base_params,
            }
            done_count += 1
            if done_count % 50 == 0 or done_count == total:
                LOGGER.info(
                    "[Probe] Progress: %d/%d probes completed "
                    "(%d excluded so far)",
                    done_count,
                    total,
                    len(excluded),
                )

        control_futures: Dict = {}
        final_results: Dict[str, Dict] = {}
        for stream_name, probe_data in initial_results.items():
            result = probe_data["result"]
            status = result["status"]
            flatten_navs = probe_data["flatten_navs"]
            if flatten_navs and status is not None and 400 <= status <= 599:
                control_future = executor.submit(
                    probe_stream,
                    auth_header,
                    base_url,
                    stream_name,
                    stream_defs[stream_name]["path"],
                    probe_data["base_params"] or None,
                )
                control_futures[control_future] = (stream_name, probe_data)
            else:
                final_results[stream_name] = {
                    "result": result,
                    "is_child": probe_data["is_child"],
                }

        isolation_futures: Dict = {}
        isolation_data: Dict[str, Dict] = {}
        for future in as_completed(control_futures):
            control_result = future.result()
            stream_name, probe_data = control_futures[future]
            final_results[stream_name] = {
                "result": control_result,
                "is_child": probe_data["is_child"],
            }
            if not (
                control_result["status"] is not None
                and 200 <= control_result["status"] < 300
            ):
                continue

            flatten_navs = probe_data["flatten_navs"]
            if len(flatten_navs) == 1:
                rejected_navs = flatten_navs
                stream_def = stream_defs[stream_name]
                stream_def["rejected_flatten_nav_properties"] = rejected_navs
                stream_def["flatten_nav_properties"] = []
                LOGGER.warning(
                    "[Probe] Keeping stream '%s' but disabling rejected "
                    "navigation expansion '%s'.",
                    stream_name,
                    rejected_navs[0],
                )
                continue

            isolation_data[stream_name] = probe_data
            for nav_name in flatten_navs:
                nav_params = dict(probe_data["base_params"])
                nav_params["$expand"] = nav_name
                nav_future = executor.submit(
                    probe_stream,
                    auth_header,
                    base_url,
                    stream_name,
                    stream_defs[stream_name]["path"],
                    nav_params,
                )
                isolation_futures[nav_future] = (stream_name, nav_name)

        isolated_navs: Dict[str, List[str]] = {
            stream_name: [] for stream_name in isolation_data
        }
        for future in as_completed(isolation_futures):
            result = future.result()
            stream_name, nav_name = isolation_futures[future]
            status = result["status"]
            if status is None or not 400 <= status <= 599:
                isolated_navs[stream_name].append(nav_name)

        combined_futures: Dict = {}
        for stream_name, probe_data in isolation_data.items():
            supported_navs = [
                nav for nav in probe_data["flatten_navs"]
                if nav in isolated_navs[stream_name]
            ]
            if len(supported_navs) <= 1:
                rejected_navs = [
                    nav for nav in probe_data["flatten_navs"]
                    if nav not in supported_navs
                ]
                stream_def = stream_defs[stream_name]
                stream_def["rejected_flatten_nav_properties"] = rejected_navs
                stream_def["flatten_nav_properties"] = supported_navs
                continue

            combined_params = dict(probe_data["base_params"])
            combined_params["$expand"] = ",".join(supported_navs)
            combined_future = executor.submit(
                probe_stream,
                auth_header,
                base_url,
                stream_name,
                stream_defs[stream_name]["path"],
                combined_params,
            )
            combined_futures[combined_future] = (
                stream_name,
                probe_data,
                supported_navs,
            )

        for future in as_completed(combined_futures):
            result = future.result()
            stream_name, probe_data, supported_navs = combined_futures[future]
            combined_status = result["status"]
            combined_rejected = (
                combined_status is not None
                and 400 <= combined_status <= 599
            )
            rejected_navs = (
                probe_data["flatten_navs"]
                if combined_rejected
                else [
                    nav for nav in probe_data["flatten_navs"]
                    if nav not in supported_navs
                ]
            )
            stream_def = stream_defs[stream_name]
            stream_def["rejected_flatten_nav_properties"] = rejected_navs
            stream_def["flatten_nav_properties"] = (
                [] if combined_rejected else supported_navs
            )

    for stream_name, probe_data in final_results.items():
        result = probe_data["result"]
        if _probe_result_excludes_stream(result, probe_data["is_child"]):
            LOGGER.warning(
                "[Probe] Excluding%s stream '%s' — HTTP %s: %s",
                " child" if probe_data["is_child"] else "",
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

    LOGGER.info(
        "Discovery probe complete: %d/%d streams excluded "
        "(direct: HTTP 4xx/5xx; "
        "child: 403/5xx or 400 COE0003/COE0025)",
        len(excluded),
        total,
    )

    # ------------------------------------------------------------------
    # Propagate exclusions to expand-only children.
    # A second cascade (below) handles regular child streams whose parent
    # was excluded — they cannot be synced without parent keys.
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

    # ------------------------------------------------------------------
    # Cascade exclusions to child streams whose parent was excluded.
    #
    # A child stream is synced by first fetching parent keys and then
    # querying the child with $filter=<parent_filter_field> eq '<key>'.
    # If the parent stream was excluded (HTTP 4xx/5xx during probe), no
    # parent keys will ever be available, so the child is also unsyncable
    # and must be excluded to avoid a dangling parent-tap-stream-id reference
    # in the catalog.
    #
    # The loop repeats until no new exclusions are found so that multi-level
    # chains (grandparent → child → grandchild) are fully propagated:
    #   Round 1: grandparent excluded → child cascade-excluded
    #   Round 2: child now excluded  → grandchild cascade-excluded
    #
    # Example (single-level):
    #   mdf_enum_value    → HTTP 400 (excluded by probe)
    #   external_allowance has parent_stream='mdf_enum_value'
    #   → sync would find no parent keys → must also be excluded.
    # ------------------------------------------------------------------
    child_cascade_excluded: Set[str] = set()
    changed = True
    while changed:
        changed = False
        for stream_name, stream_def in stream_defs.items():
            parent_stream = stream_def.get("parent_stream")
            if not parent_stream:
                continue
            if parent_stream in excluded and stream_name not in excluded:
                LOGGER.warning(
                    "[Probe] Excluding child stream '%s' — its parent stream "
                    "'%s' was excluded (HTTP 4xx/5xx), no parent keys available.",
                    stream_name,
                    parent_stream,
                )
                child_cascade_excluded.add(stream_name)
                excluded.add(stream_name)
                changed = True

    if child_cascade_excluded:
        LOGGER.info(
            "[Probe] Cascade-excluded %d child streams "
            "whose parent stream was excluded (HTTP 4xx/5xx).",
            len(child_cascade_excluded),
        )

    return excluded
