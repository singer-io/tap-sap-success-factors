import unittest
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


class TestBaseStreamBuildParams(unittest.TestCase):

    def test_incremental_filter_added(self):
        client = Mock()
        client.config = {"start_date": "2024-01-01T00:00:00Z", "lookback_window_days": 0}
        stream = DynamicStream(client=client, catalog=FakeCatalog())
        params = stream.build_params(state={})
        self.assertIn("$filter", params)
        self.assertIn("lastModifiedDateTime", params["$filter"])


class TestParseOdataRecords(unittest.TestCase):

    def test_returns_records_and_next_link(self):
        stream = DynamicStream(
            client=Mock(config={"start_date": "2024-01-01T00:00:00Z"}),
            catalog=FakeCatalog(),
        )
        payload = {"d": {"results": [{"personIdExternal": "1"}], "__next": "https://next"}}
        self.assertEqual(list(stream.parse_odata_records(payload))[0]["personIdExternal"], "1")
        self.assertEqual(stream.get_next_link(payload), "https://next")


class TestModifyObject(unittest.TestCase):

    def test_adds_parent_primary_key_to_child_record(self):
        stream = DynamicStream(
            client=Mock(config={"start_date": "2024-01-01T00:00:00Z"}),
            catalog=ChildCatalog(),
        )
        record = {"permission": "READ"}
        parent_record = {"userId": "U-100"}
        updated = stream.modify_object(record, parent_record)
        self.assertEqual(updated["userId"], "U-100")
        self.assertEqual(updated["__parent_user_userId"], "U-100")
