from singer import metadata

from tap_sap_success_factors.streams.abstracts import BaseStream


class DynamicStream(BaseStream):
    """Runtime stream for entity sets discovered from OData metadata."""

    def __init__(self, client=None, catalog=None, child_map=None) -> None:
        super().__init__(client=client, catalog=catalog)
        child_map = child_map or {}

        root_metadata = metadata.to_map(catalog.metadata).get((), {})

        self.tap_stream_id = catalog.tap_stream_id
        self.key_properties = catalog.key_properties or []
        self.replication_keys = root_metadata.get("valid-replication-keys", [])
        self.replication_method = (
            root_metadata.get("forced-replication-method")
            or root_metadata.get("replication-method")
            or "FULL_TABLE"
        )
        self.entity = root_metadata.get("entity-set") or catalog.stream
        self.path = f"{client.odata_path}/{self.entity}"
        self.parent = (
            root_metadata.get("parent-tap-stream-id")
            or root_metadata.get("parent-stream")
            or ""
        )
        self.parent_filter_field = root_metadata.get("parent-filter-field") or ""
        self.parent_key_field = root_metadata.get("parent-key-field") or ""
        self.children = child_map.get(self.tap_stream_id, [])
