from singer import metadata

from tap_sap_success_factors.metadata_discovery import MDATA_NS
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
        self.entity = (
            root_metadata.get(f"{MDATA_NS}.entity-set") or catalog.stream
        )
        self.path = f"{client.odata_path}/{self.entity}"
        self.parent = (
            root_metadata.get("parent-tap-stream-id")
            or root_metadata.get("parent-stream")
            or ""
        )
        self.parent_filter_field = (
            root_metadata.get(f"{MDATA_NS}.parent-filter-field") or ""
        )
        self.parent_key_field = (
            root_metadata.get(f"{MDATA_NS}.parent-key-field") or ""
        )
        # Optional secondary filter for multi-field parent expressions.
        self.parent_secondary_filter_field = (
            root_metadata.get(
                f"{MDATA_NS}.parent-secondary-filter-field"
            ) or ""
        )
        self.parent_secondary_key_field = (
            root_metadata.get(
                f"{MDATA_NS}.parent-secondary-key-field"
            ) or ""
        )
        # OData $expand support: fetch via navigation from a parent entity set.
        self.expand_nav_property = (
            root_metadata.get(f"{MDATA_NS}.expand-nav-property") or ""
        )
        self.expand_parent_entity_set = (
            root_metadata.get(
                f"{MDATA_NS}.expand-parent-entity-set"
            ) or ""
        )
        if self.expand_nav_property and self.expand_parent_entity_set:
            # Override path to point at the parent entity set (not this stream's
            # own entity set) so that _get_records_via_expand queries correctly.
            self.path = f"{client.odata_path}/{self.expand_parent_entity_set}"
        self.children = child_map.get(self.tap_stream_id, [])
