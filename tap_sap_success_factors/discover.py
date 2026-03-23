import singer
from singer.catalog import Catalog, CatalogEntry, Schema

from tap_sap_success_factors.metadata_discovery import discover_dynamic_streams
from tap_sap_success_factors.stream_probe import probe_all_streams

LOGGER = singer.get_logger()


def discover(client=None) -> Catalog:
    """Run metadata-driven discover mode and return a validated catalog.

    Discovery runs in two phases:

    Phase 1 — EDMX metadata discovery
        Parse the OData ``$metadata`` document to build schemas, Singer
        metadata, and stream definitions for every entity set.

    Phase 2 — Discovery-time probe validation
        Send a ``$top=1`` GET to every entity set endpoint.  Streams whose
        endpoint unconditionally returns HTTP 400 are removed from the catalog
        before it is emitted.  This prevents downstream sync runs from wasting
        time retrying endpoints that SAP will never serve (e.g. navigation-only
        entities that require ``COE0018`` composite-key filters, or
        ``COE0025`` query-unsupported entities).
    """
    if client is None:
        raise ValueError("Client is required for dynamic discovery")

    # Phase 1: parse EDMX
    schemas, field_metadata, stream_defs = discover_dynamic_streams(client)

    # Phase 2: probe each stream; collect those that return HTTP 400
    excluded_streams = probe_all_streams(client, stream_defs)

    catalog = Catalog([])

    for stream_name, schema_dict in schemas.items():
        if stream_name in excluded_streams:
            LOGGER.info(
                "Omitting stream '%s' from catalog "
                "\u2014 excluded by discovery probe (HTTP 4xx/5xx)",
                stream_name,
            )
            continue

        schema = Schema.from_dict(schema_dict)
        mdata = field_metadata[stream_name]
        mdata_map = singer.metadata.to_map(mdata)
        key_properties = mdata_map.get((), {}).get("table-key-properties")

        catalog.streams.append(
            CatalogEntry(
                stream=stream_name,
                tap_stream_id=stream_name,
                key_properties=key_properties,
                schema=schema,
                metadata=mdata,
            )
        )

    LOGGER.info(
        "Discover complete: %d streams in catalog (%d excluded by probe)",
        len(catalog.streams),
        len(excluded_streams),
    )
    return catalog
