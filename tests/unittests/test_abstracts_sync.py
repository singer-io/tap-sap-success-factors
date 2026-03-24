import unittest
from unittest.mock import Mock, patch

from tap_sap_success_factors.streams.abstracts import BaseStream
from tap_sap_success_factors.streams.dynamic import DynamicStream


# ---------------------------------------------------------------------------
# Minimal BaseStream subclass for unit-testing non-abstract methods
# ---------------------------------------------------------------------------

class _ConcreteStream(BaseStream):
    tap_stream_id = "test"
    entity = "Test"
    replication_keys: list = []
    key_properties: list = []
    schema: dict = {}

    def get_records(self):
        return iter([])


# ---------------------------------------------------------------------------
# Catalog fixtures used across multiple tests
# ---------------------------------------------------------------------------

class FakeUserCatalog:
    """Catalog entry for the 'user' stream (parent)."""

    class _Schema:
        @staticmethod
        def to_dict():
            return {
                "type": "object",
                "properties": {
                    "userId": {"type": ["null", "string"]},
                    "lastName": {"type": ["null", "string"]},
                },
            }

    schema = _Schema()
    stream = "user"
    tap_stream_id = "user"
    key_properties = ["userId"]
    metadata = [
        {
            "breadcrumb": [],
            "metadata": {
                "selected": True,
                "entity-set": "User",
                "api-path": "/odata/v2/User",
                "valid-replication-keys": [],
                "forced-replication-method": "FULL_TABLE",
            },
        }
    ]


class FakePhotoCatalog:
    """Catalog entry for the 'photo' stream (child of user)."""

    class _Schema:
        @staticmethod
        def to_dict():
            return {
                "type": "object",
                "properties": {
                    "photoId": {"type": ["null", "integer"]},
                    "userId": {"type": ["null", "string"]},
                    "__parent_user_userId": {"type": ["null", "string"]},
                },
            }

    schema = _Schema()
    stream = "photo"
    tap_stream_id = "photo"
    key_properties = ["photoId"]
    metadata = [
        {
            "breadcrumb": [],
            "metadata": {
                "selected": True,
                "entity-set": "Photo",
                "api-path": "/odata/v2/Photo",
                "parent-tap-stream-id": "user",
                "parent-filter-field": "userId",
                "parent-key-field": "userId",
                "valid-replication-keys": [],
                "forced-replication-method": "FULL_TABLE",
            },
        }
    ]


class FakeCatalog:
    class _Schema:
        @staticmethod
        def to_dict():
            return {
                "type": "object",
                "properties": {
                    "personIdExternal": {"type": ["null", "string"]},
                    "lastModifiedDateTime": {
                        "type": ["null", "string"],
                        "format": "date-time",
                    },
                },
            }

    schema = _Schema()
    stream = "per_person"
    tap_stream_id = "per_person"
    key_properties = ["personIdExternal"]
    metadata = [
        {
            "breadcrumb": [],
            "metadata": {
                "selected": True,
                "valid-replication-keys": ["lastModifiedDateTime"],
                "forced-replication-method": "INCREMENTAL",
                "entity-set": "PerPerson",
                "api-path": "/odata/v2/PerPerson",
            },
        }
    ]


def _client(mock_mode=False):
    client = Mock()
    client.config = {
        "start_date": "2024-01-01T00:00:00Z",
        "lookback_window_days": 0,
        "mock_data_path": "/tmp/mock" if mock_mode else None,
        "mock_record_count": 2,
    }
    client.odata_path = "/odata/v2"
    client.base_url = "https://example.com"
    client.get_access_token.return_value = "abc"
    return client


# ---------------------------------------------------------------------------
# get_records tests
# ---------------------------------------------------------------------------

class TestGetRecords(unittest.TestCase):

    def test_live_pagination_path(self):
        client = _client()
        client.get.return_value = {
            "d": {
                "results": [
                    {
                        "personIdExternal": "1",
                        "lastModifiedDateTime": "2024-01-02T00:00:00.000000Z",
                    }
                ],
                "__next": None,
            }
        }
        stream = DynamicStream(client=client, catalog=FakeCatalog())
        records = list(stream.get_records(state={}))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["personIdExternal"], "1")

    def test_mock_mode_generates_records(self):
        client = _client()
        client.get.return_value = {
            "d": {
                "results": [
                    {
                        "personIdExternal": "mock_1",
                        "lastModifiedDateTime": "2024-01-02T00:00:00.000000Z",
                    },
                    {
                        "personIdExternal": "mock_2",
                        "lastModifiedDateTime": "2024-01-02T00:00:00.000000Z",
                    },
                ],
                "__next": None,
            }
        }
        stream = DynamicStream(client=client, catalog=FakeCatalog())
        records = list(stream.get_records(state={}))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["personIdExternal"], "mock_1")


# ---------------------------------------------------------------------------
# sync tests
# ---------------------------------------------------------------------------

class TestSync(unittest.TestCase):

    def test_writes_records_and_bookmarks(self):
        client = _client()
        client.get.return_value = {
            "d": {
                "results": [
                    {
                        "personIdExternal": "1",
                        "lastModifiedDateTime": "2024-01-02T00:00:00.000000Z",
                    }
                ],
                "__next": None,
            }
        }
        stream = DynamicStream(client=client, catalog=FakeCatalog())
        transformer = Mock()
        transformer.transform.side_effect = lambda rec, schema, mdata: rec

        with patch("tap_sap_success_factors.streams.abstracts.write_record") as write_record_patch:
            with patch("tap_sap_success_factors.streams.abstracts.write_bookmark") as write_bookmark_patch:
                stream.sync(state={}, transformer=transformer)

        write_record_patch.assert_called_once()
        write_bookmark_patch.assert_called_once()

    def test_normalizes_odata_datetime_before_transform(self):
        client = _client()
        client.get.return_value = {
            "d": {
                "results": [
                    {
                        "personIdExternal": "1",
                        "lastModifiedDateTime": "/Date(1704153600000+0000)/",
                    }
                ],
                "__next": None,
            }
        }
        stream = DynamicStream(client=client, catalog=FakeCatalog())
        transformer = Mock()
        observed = {}

        def _capture_transform(rec, _schema, _mdata):
            observed["last_modified"] = rec["lastModifiedDateTime"]
            return rec

        transformer.transform.side_effect = _capture_transform

        with patch("tap_sap_success_factors.streams.abstracts.write_record"):
            with patch("tap_sap_success_factors.streams.abstracts.write_bookmark"):
                stream.sync(state={}, transformer=transformer)

        self.assertEqual(observed["last_modified"], "2024-01-02T00:00:00.000000Z")


# ---------------------------------------------------------------------------
# modify_object unit tests
# ---------------------------------------------------------------------------

class TestModifyObject(unittest.TestCase):

    def test_injects_parent_pk_into_child_record(self):
        """modify_object must add parent FK + synthetic __parent_<parent>_<pk> field."""
        child_stream = DynamicStream(client=_client(), catalog=FakePhotoCatalog())
        child_record = {"photoId": 42, "photoType": 1}
        parent_record = {"userId": "jsmith", "lastName": "Smith"}

        enriched = child_stream.modify_object(child_record, parent_record)

        self.assertEqual(enriched["userId"], "jsmith", "FK field must be back-filled from parent")
        self.assertEqual(enriched["__parent_user_userId"], "jsmith", "Lineage field must be injected")

    def test_does_not_overwrite_existing_fk(self):
        """modify_object must NOT overwrite a FK that already exists in the child record."""
        child_stream = DynamicStream(client=_client(), catalog=FakePhotoCatalog())
        child_record = {"photoId": 42, "userId": "existing_user"}
        parent_record = {"userId": "jsmith"}

        enriched = child_stream.modify_object(child_record, parent_record)

        self.assertEqual(enriched["userId"], "existing_user", "Pre-existing FK must be preserved")
        self.assertEqual(enriched["__parent_user_userId"], "jsmith", "Lineage field always injected")

    def test_is_noop_for_root_streams(self):
        """modify_object must return record unchanged when there is no parent."""
        root_stream = DynamicStream(client=_client(), catalog=FakeCatalog())
        record = {"personIdExternal": "1"}
        self.assertEqual(root_stream.modify_object(record, None), record)
        self.assertEqual(root_stream.modify_object(record, {"someParent": "x"}), record)


# ---------------------------------------------------------------------------
# End-to-end: child records emitted during parent sync carry parent PK
# ---------------------------------------------------------------------------

class TestChildParentSync(unittest.TestCase):

    def test_child_sync_records_contain_parent_key(self):
        """Full parent→child sync: emitted child records must carry __parent_user_userId."""
        parent_client = _client()
        parent_client.get.return_value = {
            "d": {
                "results": [{"userId": "jsmith", "lastName": "Smith"}],
                "__next": None,
            }
        }
        parent_stream = DynamicStream(client=parent_client, catalog=FakeUserCatalog())

        child_client = _client()
        child_client.get.return_value = {
            "d": {
                "results": [{"photoId": 1, "userId": "jsmith", "photoType": 1}],
                "__next": None,
            }
        }
        child_stream = DynamicStream(client=child_client, catalog=FakePhotoCatalog())
        parent_stream.child_to_sync = [child_stream]

        transformer = Mock()
        transformer.transform.side_effect = lambda rec, schema, mdata: rec
        emitted = {}

        def _capture(stream_id, record, **_):
            emitted[stream_id] = record

        with patch("tap_sap_success_factors.streams.abstracts.write_record", side_effect=_capture):
            with patch("tap_sap_success_factors.streams.abstracts.write_bookmark"):
                parent_stream.sync(state={}, transformer=transformer)

        self.assertIn("user", emitted, "Parent record must be emitted")
        self.assertIn("photo", emitted, "Child record must be emitted")

        child_rec = emitted["photo"]
        self.assertEqual(
            child_rec["__parent_user_userId"],
            "jsmith",
            "__parent_user_userId lineage field must be present in child record",
        )
        self.assertEqual(
            child_rec["userId"],
            "jsmith",
            "userId FK field must be present in child record",
        )

    def test_child_sync_sap_error_propagates(self):
        """A SAP API error from a child stream propagates to the caller (fail-fast).

        The try/catch around child sync was intentionally removed so that
        API errors surface immediately rather than being silently swallowed.
        The outer sync.py loop is responsible for logging and handling failures.
        """
        from tap_sap_success_factors.exceptions import SAPSuccessFactorsForbiddenError

        parent_client = _client()
        parent_client.get.return_value = {
            "d": {
                "results": [
                    {"userId": "user1"},
                    {"userId": "user2"},
                ],
                "__next": None,
            }
        }
        parent_stream = DynamicStream(
            client=parent_client, catalog=FakeUserCatalog()
        )

        bad_child = Mock()
        bad_child.tap_stream_id = "attachment"
        bad_child.sync.side_effect = SAPSuccessFactorsForbiddenError(
            "HTTP-error-code: 403"
        )
        parent_stream.child_to_sync = [bad_child]

        transformer = Mock()
        transformer.transform.side_effect = lambda rec, schema, mdata: rec

        with patch("tap_sap_success_factors.streams.abstracts.write_record"):
            with patch(
                "tap_sap_success_factors.streams.abstracts.write_bookmark"
            ):
                # Must raise — child errors now propagate (fail-fast)
                with self.assertRaises(SAPSuccessFactorsForbiddenError):
                    parent_stream.sync(state={}, transformer=transformer)

    def test_child_sync_unexpected_exception_propagates(self):
        """Non-SAP exceptions from a child stream must still propagate."""
        parent_client = _client()
        parent_client.get.return_value = {
            "d": {
                "results": [{"userId": "user1"}],
                "__next": None,
            }
        }
        parent_stream = DynamicStream(
            client=parent_client, catalog=FakeUserCatalog()
        )

        bad_child = Mock()
        bad_child.tap_stream_id = "attachment"
        bad_child.sync.side_effect = RuntimeError("unexpected bug")
        parent_stream.child_to_sync = [bad_child]

        transformer = Mock()
        transformer.transform.side_effect = lambda rec, schema, mdata: rec

        with patch("tap_sap_success_factors.streams.abstracts.write_record"):
            with patch(
                "tap_sap_success_factors.streams.abstracts.write_bookmark"
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    parent_stream.sync(state={}, transformer=transformer)

        self.assertIn("unexpected bug", str(ctx.exception))


# ---------------------------------------------------------------------------
# Catalog fixture for $expand streams
# ---------------------------------------------------------------------------

class FakeExpandCatalog:
    """Catalog for a stream fetched via OData $expand from EmpCompensation."""

    class _Schema:
        @staticmethod
        def to_dict():
            return {
                "type": "object",
                "properties": {
                    "calcId": {"type": ["null", "string"]},
                    "amount": {"type": ["null", "number"]},
                },
            }

    schema = _Schema()
    stream = "emp_compensation_calculated"
    tap_stream_id = "emp_compensation_calculated"
    key_properties = ["calcId"]
    metadata = [
        {
            "breadcrumb": [],
            "metadata": {
                "selected": True,
                "entity-set": "EmpCompensationCalculated",
                "expand-nav-property": "empCompensationCalculatedNav",
                "expand-parent-entity-set": "EmpCompensation",
                "valid-replication-keys": [],
                "forced-replication-method": "FULL_TABLE",
            },
        }
    ]


# ---------------------------------------------------------------------------
# _get_records_via_expand unit tests
# ---------------------------------------------------------------------------

class TestGetRecordsViaExpand(unittest.TestCase):
    """Tests for BaseStream._get_records_via_expand()."""

    def _stream(self):
        client = _client()
        return (
            DynamicStream(client=client, catalog=FakeExpandCatalog()),
            client,
        )

    def test_1_to_many_yields_all_nested_results(self):
        """Nav property returning a results list yields every nested record."""
        stream, client = self._stream()
        client.get.return_value = {
            "d": {
                "results": [
                    {
                        "empId": "e1",
                        "empCompensationCalculatedNav": {
                            "results": [
                                {"calcId": "c1", "amount": 100.0},
                                {"calcId": "c2", "amount": 200.0},
                            ]
                        },
                    }
                ],
                "__next": None,
            }
        }
        records = list(stream.get_records(state={}))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["calcId"], "c1")
        self.assertEqual(records[1]["calcId"], "c2")

    def test_1_to_1_yields_single_dict(self):
        """Nav property returning a plain dict (no results key) yields it."""
        stream, client = self._stream()
        client.get.return_value = {
            "d": {
                "results": [
                    {
                        "empId": "e1",
                        "empCompensationCalculatedNav": {
                            "calcId": "c1",
                            "amount": 50.0,
                        },
                    }
                ],
                "__next": None,
            }
        }
        records = list(stream.get_records(state={}))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["calcId"], "c1")

    def test_deferred_link_is_skipped(self):
        """Nav property containing __deferred must not yield any record."""
        stream, client = self._stream()
        client.get.return_value = {
            "d": {
                "results": [
                    {
                        "empId": "e1",
                        "empCompensationCalculatedNav": {
                            "__deferred": {
                                "uri": "https://example.com/EmpComp/Nav"
                            }
                        },
                    }
                ],
                "__next": None,
            }
        }
        records = list(stream.get_records(state={}))
        self.assertEqual(len(records), 0)

    def test_missing_nav_property_is_skipped(self):
        """Parent record without the nav property key yields nothing."""
        stream, client = self._stream()
        client.get.return_value = {
            "d": {
                "results": [{"empId": "e1"}],
                "__next": None,
            }
        }
        records = list(stream.get_records(state={}))
        self.assertEqual(len(records), 0)

    def test_missing_expand_parent_entity_set_raises_value_error(self):
        """get_records raises ValueError when expand_nav_property is set but
        expand_parent_entity_set is not configured."""
        stream, client = self._stream()
        # Simulate an incompletely configured catalog by clearing the field.
        stream.expand_parent_entity_set = ""
        with self.assertRaises(ValueError):
            list(stream.get_records(state={}))


# ---------------------------------------------------------------------------
# _coerce_odata_datetime — SAP sentinel date handling
# ---------------------------------------------------------------------------

class TestCoerceOdataDatetime(unittest.TestCase):
    """`_coerce_odata_datetime` must handle SAP sentinel dates that fall
    outside the Windows mktime() range (pre-1970 and post-~year-3001).

    SAP OData V2 uses:
      /Date(-2208988800000)/  — 1900-01-01 (sentinel min-date)
      /Date(253402214400000)/ — 9999-12-31 (sentinel max-date)
    Both values caused OSError 22 on Windows when the old implementation
    used datetime.fromtimestamp().  The fix uses timedelta arithmetic from
    the Unix epoch, which is pure-Python and platform-independent.
    """

    def setUp(self):
        # Bypass __init__ — we only need the method under test.
        self.stream = _ConcreteStream.__new__(_ConcreteStream)

    def test_sap_sentinel_min_date_1900(self):
        """Sentinel min-date (1900-01-01) converts without OSError."""
        result = self.stream._coerce_odata_datetime("/Date(-2208988800000)/")
        self.assertIn("1900", result)
        self.assertNotIn("Date(", result)

    def test_sap_sentinel_max_date_9999(self):
        """Sentinel max-date (9999-12-31) converts without OSError."""
        result = self.stream._coerce_odata_datetime("/Date(253402214400000)/")
        self.assertIn("9999", result)
        self.assertNotIn("Date(", result)

    def test_normal_date(self):
        """A typical recent timestamp converts to the correct year."""
        result = self.stream._coerce_odata_datetime("/Date(1704153600000)/")
        self.assertIn("2024", result)
        self.assertNotIn("Date(", result)

    def test_unix_epoch(self):
        """/Date(0)/ must produce a 1970 date string."""
        result = self.stream._coerce_odata_datetime("/Date(0)/")
        self.assertIn("1970", result)

    def test_pre_epoch_negative_millis(self):
        """/Date(-86400000)/ (one day before epoch) must produce 1969."""
        result = self.stream._coerce_odata_datetime("/Date(-86400000)/")
        self.assertIn("1969", result)

    def test_non_date_string_passes_through(self):
        """A string that does not match the OData pattern is returned as-is."""
        result = self.stream._coerce_odata_datetime("not-a-date")
        self.assertEqual(result, "not-a-date")

    def test_non_string_passes_through(self):
        """Non-string values (None, int) are returned unchanged."""
        self.assertIsNone(self.stream._coerce_odata_datetime(None))
        self.assertEqual(self.stream._coerce_odata_datetime(42), 42)
