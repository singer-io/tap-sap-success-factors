import copy
import re
from abc import ABC
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional

from singer import (Transformer, get_bookmark, get_logger, metadata, metrics,
                    write_bookmark, write_record, write_schema)
from singer.utils import strftime, strptime_with_tz

LOGGER = get_logger()
ODATA_DATE_RE = re.compile(r"^/Date\((?P<millis>-?\d+)(?P<offset>[+-]\d{4})?\)/$")
# Reference point for /Date(ms)/ → datetime arithmetic.
# Using timedelta from this epoch avoids os.mktime() which on Windows
# only handles timestamps within 1970-01-01..~year 3001.
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _odata_filter_value(value, field_schema: dict) -> str:
    """Return a type-appropriate OData ``eq`` filter RHS for *value*.

    OData requires integer/number literals to be unquoted and boolean literals
    to be the bare keywords ``true``/``false``.  Wrapping them in single quotes
    causes SAP to reject the request with HTTP 400 (type mismatch).

    * ``integer`` / ``number`` → ``eq 12345``  (unquoted)
    * ``boolean``              → ``eq true``    (bare keyword)
    * ``string`` / unknown     → ``eq '...'``   (single-quoted)
    """
    types = field_schema.get("type", [])
    if isinstance(types, str):
        types = [types]
    if "integer" in types or "number" in types:
        return f"eq {value}"
    if "boolean" in types:
        return f"eq {str(value).lower()}"
    # string / unknown — wrap in single quotes
    return f"eq '{value}'"


class BaseStream(ABC):
    """Base stream class following tap-harvest style."""

    tap_stream_id = ""
    key_properties = []
    sortable_key_properties = []
    replication_method = "FULL_TABLE"
    replication_keys = []
    entity = ""
    parent = ""
    children = []
    data_key = "results"
    date_fields = []
    parent_filter_field = ""
    parent_key_field = "personIdExternal"
    # Optional secondary filter for multi-field parent filter expressions.
    parent_secondary_filter_field = ""
    parent_secondary_key_field = ""
    # OData $expand support: fetch this stream by expanding a nav property on
    # expand_parent_entity_set instead of querying the entity set directly.
    expand_nav_property = ""
    expand_parent_entity_set = ""
    path = ""

    def __init__(self, client=None, catalog=None) -> None:
        if catalog is None:
            raise ValueError(
                "catalog entry must not be None — ensure the stream exists in the catalog "
                "before constructing a stream instance."
            )
        if catalog.schema is None:
            raise ValueError(
                f"catalog entry '{catalog.tap_stream_id}' has no schema — the catalog may be "
                "malformed or the stream was not discovered correctly."
            )
        self.client = client
        self.catalog = catalog
        self.schema = catalog.schema.to_dict()
        self.metadata = metadata.to_map(catalog.metadata)
        self.child_to_sync = []
        self.effective_bookmark = None

    def is_selected(self):
        """Return whether stream is selected in catalog metadata."""
        return metadata.get(self.metadata, (), "selected")

    def build_params(self, state: Dict, parent_obj: Dict = None) -> Dict:
        """Build OData query params for stream fetch."""
        params: Dict[str, Any] = {}

        if (
            self.key_properties
            and self.sortable_key_properties == self.key_properties
            and not self.expand_nav_property
        ):
            params["$orderby"] = ",".join(self.key_properties)

        # Why this guard is needed (data loss on support case 00481070):
        # - per_email is a CHILD stream (fetched per-parent via
        #   `personIdExternal eq '<id>'`) AND INCREMENTAL (own
        #   lastModifiedDateTime replication key).
        # - Child records (e.g. an email address) are rarely modified again
        #   after creation, so their lastModifiedDateTime is often OLDER than
        #   start_date/bookmark even though the record is still valid.
        # - Example: person "123" was created in 2015 and never touched since.
        #   Combining both filters produces:
        #     $filter=lastModifiedDateTime ge datetime'2024-01-01...'
        #             and personIdExternal eq '123'
        #   SAP returns 0 rows for that person — multiply by ~2,183 people
        #   and only ~6 ever had a recent-enough timestamp to pass.
        # - Fix: skip the date filter entirely for parent-scoped fetches;
        #   completeness is governed by the PARENT's bookmark instead (it
        #   decides whether to resync this parent, and therefore its
        #   children, at all).
        is_parent_scoped_fetch = bool(parent_obj and self.parent_filter_field)

        if (
            self.replication_method == "INCREMENTAL"
            and self.replication_keys
            and not is_parent_scoped_fetch
        ):
            key = self.replication_keys[0]
            bookmark = self.effective_bookmark or self.get_bookmark(
                state,
                self.tap_stream_id,
                key,
            )

            lookback_days = int(self.client.config.get("lookback_window_days", 0))
            bookmark_dt = strptime_with_tz(bookmark)
            effective_dt = bookmark_dt - timedelta(days=lookback_days)
            bookmark_value = strftime(effective_dt)

            params["$filter"] = f"{key} ge datetime'{bookmark_value}'"

        if parent_obj and self.parent_filter_field:
            parent_val = parent_obj[self.parent_key_field]
            props = self.schema.get("properties", {})
            pff_schema = props.get(self.parent_filter_field, {})
            clause = (
                f"{self.parent_filter_field} "
                f"{_odata_filter_value(parent_val, pff_schema)}"
            )
            # Append optional secondary filter field (e.g. activityObjectType).
            if self.parent_secondary_filter_field and self.parent_secondary_key_field:
                sec_val = parent_obj.get(self.parent_secondary_key_field, "")
                if sec_val is not None and sec_val != "":
                    sec_schema = props.get(self.parent_secondary_filter_field, {})
                    clause += (
                        f" and {self.parent_secondary_filter_field} "
                        f"{_odata_filter_value(sec_val, sec_schema)}"
                    )
            params["$filter"] = (
                f"{params['$filter']} and {clause}" if "$filter" in params else clause
            )

        return params

    def get_bookmark(self, state: Dict, stream: str, key: str = None):
        """Wrapper around singer.get_bookmark following tap-harvest style."""
        return get_bookmark(
            state,
            stream,
            key or (self.replication_keys[0] if self.replication_keys else None),
            self.client.config["start_date"],
        )

    def write_bookmark(self, state: Dict, stream: str, key: str = None, value=None):
        """Wrapper around singer.write_bookmark following tap-harvest style."""
        bookmark_key = key or (self.replication_keys[0] if self.replication_keys else None)
        if not bookmark_key:
            return

        current = self.get_bookmark(state, stream, bookmark_key)
        write_bookmark(state, stream, bookmark_key, max(current, value))

    def parse_odata_records(self, payload: Dict) -> Iterable[Dict]:
        """Parse OData V2 payload records."""
        data = payload.get("d", {})
        return data.get("results", [])

    def get_next_link(self, payload: Dict) -> Optional[str]:
        """Get OData __next absolute URL."""
        return payload.get("d", {}).get("__next")

    def append_times_to_dates(self, record: Dict):
        """Normalize date fields to Singer-compatible timestamps."""
        for date_field in self.date_fields:
            if record.get(date_field):
                try:
                    record[date_field] = strftime(strptime_with_tz(record[date_field]))
                except (TypeError, ValueError):  # pragma: no cover
                    pass

    def _coerce_odata_datetime(self, value: Any) -> Any:
        """Convert SAP OData V2 /Date(ms±offset)/ values to RFC 3339.

        datetime.fromtimestamp() delegates to the OS mktime() which on
        Windows only accepts timestamps in 1970-01-01..~3001.  SAP uses
        /Date(-2208988800000)/ (1900-01-01) as a sentinel min-date and
        /Date(253402214400000)/ (9999-12-31) as a sentinel max-date — both
        are outside that range and cause OSError 22 on Windows.

        Using timedelta arithmetic from the Unix epoch bypasses mktime
        entirely and works for the full Python datetime range (years 1-9999)
        on every platform.
        """
        if not isinstance(value, str):
            return value

        match = ODATA_DATE_RE.match(value.strip())
        if not match:
            return value

        try:
            millis = int(match.group("millis"))
            dt_val = _UNIX_EPOCH + timedelta(milliseconds=millis)
            return strftime(dt_val)
        except (OverflowError, OSError, TypeError, ValueError):
            return value

    def _normalize_datetimes_with_schema(self, value: Any, schema: Dict) -> Any:
        """Recursively coerce date-time fields based on JSON schema format."""
        if value is None or not isinstance(schema, dict):
            return value

        if schema.get("format") == "date-time":
            return self._coerce_odata_datetime(value)

        if isinstance(value, dict):
            properties = schema.get("properties", {})
            for key, current in list(value.items()):
                if key in properties:
                    value[key] = self._normalize_datetimes_with_schema(current, properties[key])
            return value

        if isinstance(value, list):
            item_schema = schema.get("items", {})
            return [self._normalize_datetimes_with_schema(item, item_schema) for item in value]

        return value

    def normalize_record_datetimes(self, record: Dict) -> Dict:
        """Normalize all date-time fields in a record before Singer transformation."""
        return self._normalize_datetimes_with_schema(record, self.schema)

    def modify_object(self, record: Dict, _parent_record: Dict = None) -> Dict:
        """Allow child streams to enrich records."""
        if not _parent_record or not self.parent:
            return record

        parent_pk_field = self.parent_key_field
        if not parent_pk_field or parent_pk_field not in _parent_record:
            return record

        parent_pk_value = _parent_record[parent_pk_field]

        if self.parent_filter_field and self.parent_filter_field not in record:
            record[self.parent_filter_field] = parent_pk_value

        parent_id_field = (
            f"__parent_{self.parent}_{parent_pk_field}"
        )
        record[parent_id_field] = parent_pk_value

        return record

    def get_records(self, state: Dict, parent_obj: Dict = None):
        """Iterate records with OData next-link pagination."""
        if self.expand_nav_property:
            if not self.expand_parent_entity_set:
                raise ValueError(
                    f"Stream '{self.tap_stream_id}' has "
                    f"expand_nav_property='{self.expand_nav_property}' but "
                    "expand_parent_entity_set is not configured."
                )
            yield from self._get_records_via_expand(state, parent_obj)
            return

        path = self.path or f"{self.client.odata_path}/{self.entity}"
        params = self.build_params(state, parent_obj)
        payload = self.client.get(path, params=params)

        while True:
            yield from self.parse_odata_records(payload)

            next_link = self.get_next_link(payload)
            if not next_link:
                break

            response = self.client.request_raw(
                "GET",
                next_link,
                headers={"Authorization": self.client.get_auth_header()},
            )
            payload = response.json()

    def _get_records_via_expand(self, state: Dict, parent_obj: Dict = None):
        """Fetch records via OData $expand from a parent entity set.

        Queries ``expand_parent_entity_set`` with ``$expand=<nav_property>``
        and extracts the nested records from the navigation property of every
        parent record.  Handles both 1-to-many (results list) and 1-to-1
        (single object) navigation properties.
        """
        path = self.path  # already set to parent entity set path in __init__
        params = self.build_params(state, parent_obj)
        params["$expand"] = self.expand_nav_property
        payload = self.client.get(path, params=params)

        while True:
            for parent_record in self.parse_odata_records(payload):
                nav_data = parent_record.get(self.expand_nav_property)
                if not nav_data or not isinstance(nav_data, dict):
                    continue
                # Skip OData deferred links (navigation not yet expanded).
                if "__deferred" in nav_data:
                    continue
                results = nav_data.get("results")
                if results is not None:
                    # 1-to-many: {"results": [...]}
                    yield from results
                else:
                    # 1-to-1: nav_data is the record itself.
                    yield nav_data

            next_link = self.get_next_link(payload)
            if not next_link:
                break

            response = self.client.request_raw(
                "GET",
                next_link,
                headers={"Authorization": self.client.get_auth_header()},
            )
            payload = response.json()

    def write_schema(self):
        """Write schema message for stream."""
        write_schema(self.tap_stream_id, self.schema, self.key_properties)

    def sync(self, state: Dict, transformer: Transformer, parent_obj: Dict = None) -> int:
        """Sync stream records and children streams."""
        # Why this guard is ALSO needed here (mirrors build_params() above):
        # - build_params() stops the SERVER from filtering by date, but this
        #   method has its OWN client-side bookmark comparison further down
        #   (`if bookmark_key and bookmark: record_passes_bookmark = ...`).
        # - Example: without this, the 2015 per_email record from the
        #   build_params() example would come back from SAP (now unfiltered)
        #   but still get silently dropped right here, before write_record()
        #   runs — same data loss, just moved one layer down the call stack.
        # - Fix: `is_parent_scoped_fetch` also forces `bookmark = None` below,
        #   so every record returned by a parent-scoped fetch gets written.
        is_parent_scoped_fetch = bool(parent_obj and self.parent_filter_field)

        bookmark_key = self.replication_keys[0] if self.replication_keys else None
        # Why NOT cache `bookmark` across calls (reviewer question):
        # - This instance is reused per parent record (e.g. per_email.sync()
        #   runs once per per_person record — ~2,183 times/tenant), so
        #   caching looks tempting here.
        # - Not needed: when is_parent_scoped_fetch is True this ternary
        #   already short-circuits to None WITHOUT calling get_bookmark() or
        #   touching `state` — there is nothing expensive to cache.
        # - A naive `if self.effective_bookmark: reuse else: compute` cache
        #   would also be fragile: None is both the valid "no filter applies"
        #   result AND the "not computed yet" sentinel, so it would silently
        #   recompute every call anyway today, but could serve a stale value
        #   if this method's invariants ever change.
        # - See test_parent_scoped_fetch_bookmark_recomputed_fresh_each_call.
        #
        # Why `and self.is_selected()` was added (see min() comment below for
        # the regression this prevents):
        # - An unselected pass-through parent (e.g. per_person, added to
        #   streams_to_sync only to reach a selected per_email) never writes
        #   its own bookmark, so get_bookmark() for it would always default
        #   to start_date — a misleadingly "fresh" value that must not be
        #   treated as real progress.
        bookmark = (
            self.get_bookmark(state, self.tap_stream_id)
            if bookmark_key and not is_parent_scoped_fetch and self.is_selected()
            else None
        )

        # Why `bookmark` must stay None here when unselected (PR review fix):
        # - When this stream is unselected and only running to reach a
        #   selected child (see is_selected() guard on the bookmark write
        #   further below), its own bookmark is deliberately never
        #   persisted — so get_bookmark() for it always reads back as
        #   start_date, never the stream's real progress.
        # - Example: per_person is unselected, per_email is selected.
        #   per_email's saved checkpoint correctly advances each run (e.g. to
        #   2026-06-01). If per_person's frozen start_date (2024-01-01) were
        #   fed into `min(own_bookmark, child_bookmark)` below, the OLDER
        #   value always wins: min(2024-01-01, 2026-06-01) = 2024-01-01 —
        #   forever. per_person would then re-query EVERY historical record,
        #   and re-emit EVERY child, on every single run.
        # - Fix: leave `bookmark` as None here when unselected, so the loop
        #   below seeds it from the child's real, advancing checkpoint alone.
        if bookmark_key and self.child_to_sync and not is_parent_scoped_fetch:
            parent_bookmark_key = f"{self.tap_stream_id}_{bookmark_key}"
            for child in self.child_to_sync:
                child_bookmark = self.get_bookmark(
                    state,
                    child.tap_stream_id,
                    key=parent_bookmark_key,
                )
                bookmark = min(bookmark, child_bookmark) if bookmark else child_bookmark

        self.effective_bookmark = bookmark
        # Only advance from real records — do NOT pre-seed with start_date so
        # that 0-record syncs never write a spurious bookmark.
        current_max_bookmark = None

        with metrics.record_counter(self.tap_stream_id) as counter:
            for record in self.get_records(state=state, parent_obj=parent_obj):
                record = self.modify_object(record, parent_obj)
                record = self.normalize_record_datetimes(copy.deepcopy(record))
                transformed_record = transformer.transform(
                    record, self.schema, self.metadata
                )
                self.append_times_to_dates(transformed_record)

                record_passes_bookmark = True
                record_value = (
                    transformed_record.get(bookmark_key)
                    if bookmark_key
                    else None
                )

                if bookmark_key and bookmark:
                    record_passes_bookmark = bool(
                        record_value and record_value >= bookmark
                    )

                if record_passes_bookmark:
                    if self.is_selected():
                        write_record(self.tap_stream_id, transformed_record)
                        counter.increment()

                    if record_value:
                        current_max_bookmark = (
                            max(current_max_bookmark, record_value)
                            if current_max_bookmark
                            else record_value
                        )

                    for child in self.child_to_sync:
                        child.sync(
                            state=state,
                            transformer=transformer,
                            parent_obj=record,
                        )

            if bookmark_key and current_max_bookmark:
                # Why this write is gated on is_selected():
                # - sync.py adds an unselected parent to streams_to_sync purely
                #   so a selected child can be reached (e.g. only per_email is
                #   selected; per_person is synced solely as a pass-through).
                # - Example: without this guard, per_person would still
                #   advance its own bookmark to "now" despite never writing a
                #   single record. If the user later selects per_person
                #   directly, the tap would think it's already caught up and
                #   skip every historical record — even though none were ever
                #   actually extracted.
                # - Fix: only persist a stream's own bookmark when it is
                #   actually selected.
                if self.is_selected():
                    self.write_bookmark(
                        state, self.tap_stream_id, value=current_max_bookmark
                    )

                if self.child_to_sync:
                    parent_bookmark_key = (
                        f"{self.tap_stream_id}_{bookmark_key}"
                    )
                    for child in self.child_to_sync:
                        self.write_bookmark(
                            state,
                            child.tap_stream_id,
                            key=parent_bookmark_key,
                            value=current_max_bookmark,
                        )

            self.effective_bookmark = None

            return counter.value
