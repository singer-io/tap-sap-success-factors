from unittest.mock import Mock

from tap_sap_success_factors.streams.dynamic import DynamicStream


class FakeCatalog:
    class _Schema:
        @staticmethod
        def to_dict():
            return {
                "type": "object",
                "properties": {
                    "personIdExternal": {"type": ["null", "string"]},
                    "lastModifiedDateTime": {"type": ["null", "string"]},
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


def test_base_stream_build_params_incremental():
    client = Mock()
    client.config = {"start_date": "2024-01-01T00:00:00Z", "lookback_window_days": 0}

    stream = DynamicStream(client=client, catalog=FakeCatalog())
    params = stream.build_params(state={})

    assert "$filter" in params
    assert "lastModifiedDateTime" in params["$filter"]


def test_parse_odata_records_and_next_link():
    stream = DynamicStream(
        client=Mock(config={"start_date": "2024-01-01T00:00:00Z"}),
        catalog=FakeCatalog(),
    )

    payload = {"d": {"results": [{"personIdExternal": "1"}], "__next": "https://next"}}
    assert list(stream.parse_odata_records(payload))[0]["personIdExternal"] == "1"
    assert stream.get_next_link(payload) == "https://next"


class ChildCatalog:
    class _Schema:
        @staticmethod
        def to_dict():
            return {
                "type": "object",
                "properties": {
                    "userId": {"type": ["null", "string"]},
                },
            }

    schema = _Schema()
    stream = "user_permissions"
    tap_stream_id = "user_permissions"
    key_properties = ["userId"]
    metadata = [
        {
            "breadcrumb": [],
            "metadata": {
                "selected": True,
                "entity-set": "UserPermissions",
                "api-path": "/odata/v2/UserPermissions",
                "parent-tap-stream-id": "user",
                "parent-filter-field": "userId",
                "parent-key-field": "userId",
            },
        }
    ]


def test_modify_object_adds_parent_primary_key_to_child_record():
    stream = DynamicStream(
        client=Mock(config={"start_date": "2024-01-01T00:00:00Z"}),
        catalog=ChildCatalog(),
    )

    record = {"permission": "READ"}
    parent_record = {"userId": "U-100"}

    updated = stream.modify_object(record, parent_record)

    assert updated["userId"] == "U-100"
    assert updated["__parent_user_userId"] == "U-100"
