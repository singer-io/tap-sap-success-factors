import singer
from singer.catalog import Catalog, CatalogEntry, Schema

from tap_sap_success_factors.metadata_discovery import discover_dynamic_streams

LOGGER = singer.get_logger()


def discover(client=None) -> Catalog:
    """Run metadata-driven discover mode and return catalog."""
    if client is None:
        raise ValueError("Client is required for dynamic discovery")

    schemas, field_metadata, _stream_defs = discover_dynamic_streams(client)
    catalog = Catalog([])

    for stream_name, schema_dict in schemas.items():
        schema = Schema.from_dict(schema_dict)
        mdata = field_metadata[stream_name]
        key_properties = (
            singer.metadata.to_map(mdata).get((), {}).get("table-key-properties")
        )

        catalog.streams.append(
            CatalogEntry(
                stream=stream_name,
                tap_stream_id=stream_name,
                key_properties=key_properties,
                schema=schema,
                metadata=mdata,
            )
        )

    return catalog
