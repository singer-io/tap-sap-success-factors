from typing import Dict, Optional

import singer
from singer import metadata

from tap_sap_success_factors.schema import write_schema
from tap_sap_success_factors.streams.dynamic import DynamicStream

LOGGER = singer.get_logger()


def update_currently_syncing(state: Dict, stream_name: Optional[str]) -> None:
    """Update `currently_syncing` marker in state."""
    if not stream_name:
        state.pop("currently_syncing", None)
    else:
        singer.set_currently_syncing(state, stream_name)
    singer.write_state(state)


def sync(client, config: Dict, catalog: singer.Catalog, state: Dict) -> None:
    """Sync selected streams from catalog."""
    # config is deleted immediately after discovery.
    # Sync should rely on config values only via the client
    del config

    streams_to_sync = [
        stream.tap_stream_id for stream in catalog.get_selected_streams(state)
    ]
    child_map = {}
    for stream in catalog.streams:
        root_mdata = metadata.to_map(stream.metadata).get((), {})
        parent_stream = root_mdata.get("parent-tap-stream-id") or root_mdata.get("parent-stream")
        if parent_stream:
            child_map.setdefault(parent_stream, []).append(stream.tap_stream_id)

    LOGGER.info("selected_streams: %s", streams_to_sync)

    last_stream = singer.get_currently_syncing(state)
    LOGGER.info("last/currently syncing stream: %s", last_stream)

    with singer.Transformer() as transformer:
        for stream_name in streams_to_sync:
            catalog_stream = catalog.get_stream(stream_name)
            if catalog_stream is None:
                LOGGER.warning(
                    "Stream '%s' not found in catalog, skipping.", stream_name
                )
                continue
            if catalog_stream.schema is None:
                LOGGER.warning(
                    "Stream '%s' has no schema in catalog, skipping.", stream_name
                )
                continue

            stream = DynamicStream(client, catalog_stream, child_map=child_map)

            if stream.parent:
                if stream.parent not in streams_to_sync:
                    # Only append the parent if it exists in the catalog.
                    # Discovery-time validation ensures this for freshly generated
                    # catalogs; this guard handles externally-modified catalogs.
                    if catalog.get_stream(stream.parent) is not None:
                        streams_to_sync.append(stream.parent)
                    else:
                        LOGGER.warning(
                            "Stream '%s' declares parent '%s' which is not in the "
                            "catalog. Stream will be skipped.",
                            stream_name,
                            stream.parent,
                        )
                continue

            write_schema(stream, client, streams_to_sync, catalog, child_map=child_map)
            LOGGER.info("START Syncing: %s", stream_name)
            update_currently_syncing(state, stream_name)
            total_records = stream.sync(state=state, transformer=transformer)

            update_currently_syncing(state, None)
            LOGGER.info(
                "FINISHED Syncing: %s, total_records: %s",
                stream_name,
                total_records,
            )
