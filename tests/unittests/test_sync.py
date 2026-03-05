from importlib import import_module
from unittest.mock import Mock, patch

from singer.catalog import Catalog, CatalogEntry, Schema

from tap_sap_success_factors.sync import sync


def _catalog_for_stream(*stream_names: str, selected: str = None):
    """Build a Catalog with one CatalogEntry per stream name.

    Only the stream matching ``selected`` (or the first stream if not given)
    will have ``selected=True``.  All other entries are present in the catalog
    but not selected, which is enough to satisfy catalog.get_stream() guards.
    """
    selected = selected or stream_names[0]
    entries = [
        CatalogEntry(
            stream=name,
            tap_stream_id=name,
            key_properties=["personIdExternal"],
            schema=Schema.from_dict(
                {
                    "type": "object",
                    "properties": {
                        "personIdExternal": {"type": ["null", "string"]}
                    },
                }
            ),
            metadata=[{"breadcrumb": [], "metadata": {"selected": name == selected}}],
        )
        for name in stream_names
    ]
    return Catalog(streams=entries)


def test_sync_invokes_stream_sync():
    sync_module = import_module("tap_sap_success_factors.sync")
    fake_client = Mock()
    catalog = _catalog_for_stream("per_person")

    with patch.object(sync_module, "write_schema") as write_schema_patch:
        with patch.object(sync_module, "DynamicStream") as dynamic_stream_cls:
            stream_instance = Mock()
            stream_instance.parent = ""
            stream_instance.sync.return_value = 1
            dynamic_stream_cls.return_value = stream_instance

            sync(fake_client, {}, catalog, {})

            write_schema_patch.assert_called_once()
            stream_instance.sync.assert_called_once()


def test_sync_adds_parent_when_child_selected():
    sync_module = import_module("tap_sap_success_factors.sync")
    fake_client = Mock()
    # per_email is selected; per_person (parent) is present in catalog but not selected.
    # sync() should auto-add per_person to the sync queue so it drives the child loop.
    catalog = _catalog_for_stream("per_email", "per_person", selected="per_email")

    with patch.object(sync_module, "DynamicStream") as dynamic_stream_cls:
        child_stream_instance = Mock()
        child_stream_instance.parent = "per_person"
        child_stream_instance.tap_stream_id = "per_email"

        parent_stream_instance = Mock()
        parent_stream_instance.parent = ""
        parent_stream_instance.tap_stream_id = "per_person"
        parent_stream_instance.sync.return_value = 1

        dynamic_stream_cls.side_effect = [
            child_stream_instance,
            parent_stream_instance,
        ]

        sync(fake_client, {}, catalog, {})
        child_stream_instance.sync.assert_not_called()
        parent_stream_instance.sync.assert_called_once()
