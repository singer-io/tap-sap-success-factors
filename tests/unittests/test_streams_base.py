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
                "tap-sap-success-factors.entity-set": "PerPerson",
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
                "tap-sap-success-factors.entity-set": "UserPermissions",
                "api-path": "/odata/v2/UserPermissions",
                "parent-tap-stream-id": "user",
                "tap-sap-success-factors.parent-filter-field": "userId",
                "tap-sap-success-factors.parent-key-field": "userId",
            },
        }
    ]


class TestBaseStreamBuildParams(unittest.TestCase):

    def test_primary_key_ordering_added(self):
        client = Mock()
        client.config = {"start_date": "2024-01-01T00:00:00Z"}
        stream = DynamicStream(client=client, catalog=FakeCatalog())
        stream.sortable_key_properties = ["personIdExternal"]

        params = stream.build_params(state={})

        self.assertEqual(params["$orderby"], "personIdExternal")

    def test_composite_primary_key_ordering_added(self):
        client = Mock()
        client.config = {"start_date": "2024-01-01T00:00:00Z"}
        stream = DynamicStream(client=client, catalog=FakeCatalog())
        stream.key_properties = ["roleId", "permissionId"]
        stream.sortable_key_properties = ["roleId", "permissionId"]

        params = stream.build_params(state={})

        self.assertEqual(params["$orderby"], "roleId,permissionId")

    def test_primary_key_ordering_not_added_for_expand_stream(self):
        client = Mock()
        client.config = {"start_date": "2024-01-01T00:00:00Z"}
        stream = DynamicStream(client=client, catalog=FakeCatalog())
        stream.expand_nav_property = "permissionsNav"
        stream.sortable_key_properties = ["personIdExternal"]

        params = stream.build_params(state={})

        self.assertNotIn("$orderby", params)

    def test_primary_key_ordering_not_added_for_unsortable_key(self):
        client = Mock()
        client.config = {"start_date": "2024-01-01T00:00:00Z"}
        stream = DynamicStream(client=client, catalog=FakeCatalog())

        params = stream.build_params(state={})

        self.assertNotIn("$orderby", params)

    def test_incremental_filter_added(self):
        client = Mock()
        client.config = {"start_date": "2024-01-01T00:00:00Z", "lookback_window_days": 0}
        stream = DynamicStream(client=client, catalog=FakeCatalog())
        params = stream.build_params(state={})
        self.assertIn("$filter", params)
        self.assertIn("lastModifiedDateTime", params["$filter"])

    def test_expand_added_for_flatten_nav_properties(self):
        client = Mock()
        client.config = {"start_date": "2024-01-01T00:00:00Z"}
        stream = DynamicStream(client=client, catalog=FakeCatalog())
        stream.flatten_nav_properties = ["emailTypeNav"]

        params = stream.build_params(state={})

        self.assertEqual(params["$expand"], "emailTypeNav")

    def test_expand_not_added_when_already_expand_nav_stream(self):
        """A stream fetched via the separate expand_nav_property path (Group
        5) must not also get a flatten-$expand — it queries a different
        parent entity set entirely."""
        client = Mock()
        client.config = {"start_date": "2024-01-01T00:00:00Z"}
        stream = DynamicStream(client=client, catalog=FakeCatalog())
        stream.expand_nav_property = "permissionsNav"
        stream.flatten_nav_properties = ["emailTypeNav"]

        params = stream.build_params(state={})

        self.assertNotIn("$expand", params)


class TestFlattenNavData(unittest.TestCase):

    def test_flattens_expanded_nav_into_prefixed_fields(self):
        client = Mock(config={"start_date": "2024-01-01T00:00:00Z"})
        stream = DynamicStream(client=client, catalog=FakeCatalog())
        stream.flatten_nav_properties = ["emailTypeNav"]

        record = {
            "emailType": "home",
            "emailTypeNav": {
                "externalCode": "HOME",
                "id": 7,
                "childPicklistOptions": {
                    "__deferred": {
                        "uri": "https://sf/odata/v2/PicklistOption(7)/childPicklistOptions"
                    }
                },
            },
        }

        result = stream.flatten_nav_data(record)

        self.assertNotIn("emailTypeNav", result)
        self.assertEqual(result["emailTypeNav_externalCode"], "HOME")
        self.assertEqual(result["emailTypeNav_id"], 7)
        self.assertEqual(
            result["emailTypeNav_childPicklistOptions_deferred_uri"],
            "https://sf/odata/v2/PicklistOption(7)/childPicklistOptions",
        )

    def test_leaves_unexpanded_deferred_nav_untouched(self):
        """If $expand silently fails to apply (e.g. SAP ignores an unknown
        nav), the raw __deferred link must be left as-is rather than
        crashing or emitting half-flattened fields."""
        client = Mock(config={"start_date": "2024-01-01T00:00:00Z"})
        stream = DynamicStream(client=client, catalog=FakeCatalog())
        stream.flatten_nav_properties = ["emailTypeNav"]

        record = {
            "emailType": "home",
            "emailTypeNav": {"__deferred": {"uri": "https://sf/.../emailTypeNav"}},
        }

        result = stream.flatten_nav_data(record)

        self.assertEqual(
            result["emailTypeNav"], {"__deferred": {"uri": "https://sf/.../emailTypeNav"}}
        )

    def test_noop_when_no_flatten_nav_properties_configured(self):
        client = Mock(config={"start_date": "2024-01-01T00:00:00Z"})
        stream = DynamicStream(client=client, catalog=FakeCatalog())

        record = {"personIdExternal": "1"}
        result = stream.flatten_nav_data(record)

        self.assertEqual(result, {"personIdExternal": "1"})


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
