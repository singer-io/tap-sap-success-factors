import singer
from singer.catalog import Catalog, CatalogEntry, Schema

from tap_sap_success_factors.metadata_discovery import (
    MDATA_NS,
    discover_dynamic_streams,
)
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
        base query is not readable are removed from the catalog before it is
        emitted. If an optional navigation expansion is rejected while the
        base entity remains readable, only that navigation's fields are marked
        unsupported.
    """
    if client is None:
        raise ValueError("Client is required for dynamic discovery")

    # Phase 1: parse EDMX
    schemas, field_metadata, stream_defs = discover_dynamic_streams(client)

    # Phase 2: probe each stream; collect those that return HTTP 4xx/5xx
    excluded_streams = probe_all_streams(client, stream_defs)

    # A failed optional $expand should disable only its flattened fields,
    # not remove an otherwise-readable stream from the catalog.
    for stream_name, stream_def in stream_defs.items():
        rejected_navs = stream_def.get("rejected_flatten_nav_properties") or []
        if not rejected_navs:
            continue

        mdata = singer.metadata.to_map(field_metadata[stream_name])
        properties = schemas[stream_name]["properties"]
        for nav_name in rejected_navs:
            prefix = f"{nav_name}_"
            for field_name in properties:
                if field_name.startswith(prefix):
                    mdata = singer.metadata.write(
                        mdata,
                        ("properties", field_name),
                        "inclusion",
                        "unsupported",
                    )
        mdata = singer.metadata.write(
            mdata,
            (),
            f"{MDATA_NS}.flatten-nav-properties",
            stream_def.get("flatten_nav_properties", []),
        )
        field_metadata[stream_name] = singer.metadata.to_list(mdata)

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
