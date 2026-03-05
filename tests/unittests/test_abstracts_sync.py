from unittest.mock import Mock, call, patch

from tap_sap_success_factors.streams.dynamic import DynamicStream


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


def test_get_records_live_pagination_path():
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

    assert len(records) == 1
    assert records[0]["personIdExternal"] == "1"


def test_get_records_mock_mode_generates_records():
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

    assert len(records) == 2
    assert records[0]["personIdExternal"] == "mock_1"


def test_sync_writes_records_and_bookmarks():
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


def test_sync_normalizes_odata_datetime_before_transform():
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

    assert observed["last_modified"] == "2024-01-02T00:00:00.000000Z"


# ---------------------------------------------------------------------------
# modify_object unit tests
# ---------------------------------------------------------------------------

def test_modify_object_injects_parent_pk_into_child_record():
    """modify_object must add parent FK + synthetic __parent_<parent>_<pk> field."""
    child_stream = DynamicStream(client=_client(), catalog=FakePhotoCatalog())

    child_record = {"photoId": 42, "photoType": 1}
    parent_record = {"userId": "jsmith", "lastName": "Smith"}

    enriched = child_stream.modify_object(child_record, parent_record)

    assert enriched["userId"] == "jsmith", "FK field must be back-filled from parent"
    assert enriched["__parent_user_userId"] == "jsmith", "Lineage field must be injected"


def test_modify_object_does_not_overwrite_existing_fk():
    """modify_object must NOT overwrite a FK that already exists in the child record."""
    child_stream = DynamicStream(client=_client(), catalog=FakePhotoCatalog())

    child_record = {"photoId": 42, "userId": "existing_user"}
    parent_record = {"userId": "jsmith"}

    enriched = child_stream.modify_object(child_record, parent_record)

    assert enriched["userId"] == "existing_user", "Pre-existing FK must be preserved"
    assert enriched["__parent_user_userId"] == "jsmith", "Lineage field always injected"


def test_modify_object_is_noop_for_root_streams():
    """modify_object must return record unchanged when there is no parent."""
    # FakeCatalog is a root stream (no parent-tap-stream-id)
    root_stream = DynamicStream(client=_client(), catalog=FakeCatalog())
    record = {"personIdExternal": "1"}
    assert root_stream.modify_object(record, None) == record
    assert root_stream.modify_object(record, {"someParent": "x"}) == record


# ---------------------------------------------------------------------------
# End-to-end: child records emitted during parent sync carry parent PK
# ---------------------------------------------------------------------------

def test_child_sync_records_contain_parent_key():
    """Full parent→child sync: emitted child records must carry __parent_user_userId."""
    # --- parent stream setup ---
    parent_client = _client()
    parent_client.get.return_value = {
        "d": {
            "results": [{"userId": "jsmith", "lastName": "Smith"}],
            "__next": None,
        }
    }
    parent_stream = DynamicStream(client=parent_client, catalog=FakeUserCatalog())

    # --- child stream setup ---
    child_client = _client()
    child_client.get.return_value = {
        "d": {
            "results": [{"photoId": 1, "userId": "jsmith", "photoType": 1}],
            "__next": None,
        }
    }
    child_stream = DynamicStream(client=child_client, catalog=FakePhotoCatalog())

    # Wire child onto parent (normally done by schema.write_schema)
    parent_stream.child_to_sync = [child_stream]

    transformer = Mock()
    transformer.transform.side_effect = lambda rec, schema, mdata: rec

    emitted = {}

    def _capture(stream_id, record, **_):
        emitted[stream_id] = record

    with patch("tap_sap_success_factors.streams.abstracts.write_record", side_effect=_capture):
        with patch("tap_sap_success_factors.streams.abstracts.write_bookmark"):
            parent_stream.sync(state={}, transformer=transformer)

    assert "user" in emitted, "Parent record must be emitted"
    assert "photo" in emitted, "Child record must be emitted"

    child_rec = emitted["photo"]
    assert child_rec["__parent_user_userId"] == "jsmith", (
        "__parent_user_userId lineage field must be present in child record"
    )
    assert child_rec["userId"] == "jsmith", (
        "userId FK field must be present in child record"
    )


def test_child_sync_exception_does_not_fail_parent():
    """A child stream 403 must log a warning but must NOT abort the parent sync."""
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
    parent_stream = DynamicStream(client=parent_client, catalog=FakeUserCatalog())

    # Child that always raises
    bad_child = Mock()
    bad_child.tap_stream_id = "attachment"
    bad_child.sync.side_effect = Exception("HTTP-error-code: 403")

    parent_stream.child_to_sync = [bad_child]

    transformer = Mock()
    transformer.transform.side_effect = lambda rec, schema, mdata: rec

    parent_records = []

    def _capture(stream_id, record, **_):
        if stream_id == "user":
            parent_records.append(record)

    with patch("tap_sap_success_factors.streams.abstracts.write_record", side_effect=_capture):
        with patch("tap_sap_success_factors.streams.abstracts.write_bookmark"):
            # Must NOT raise despite child raising every iteration
            parent_stream.sync(state={}, transformer=transformer)

    assert len(parent_records) == 2, "Both parent records must be emitted despite child errors"
    assert bad_child.sync.call_count == 2, "Child sync was called once per parent record"
