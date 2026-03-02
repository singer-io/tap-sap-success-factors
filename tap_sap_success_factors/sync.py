from typing import Dict

import singer
from singer import metadata

from tap_sap_success_factors.schema import write_schema
from tap_sap_success_factors.streams.dynamic import DynamicStream

LOGGER = singer.get_logger()


def update_currently_syncing(state: Dict, stream_name: str) -> None:
    """Update `currently_syncing` marker in state."""
    if not stream_name and singer.get_currently_syncing(state):
        del state["currently_syncing"]
    else:
        singer.set_currently_syncing(state, stream_name)
    singer.write_state(state)


def sync(client, config: Dict, catalog: singer.Catalog, state: Dict) -> None:
    """Sync selected streams from catalog."""
    del config

    streams_to_sync = [stream.stream for stream in catalog.get_selected_streams(state)]
    child_map = {}
    for stream in catalog.streams:
        root_mdata = metadata.to_map(stream.metadata).get((), {})
        parent_stream = root_mdata.get("parent-tap-stream-id")
        if parent_stream:
            child_map.setdefault(parent_stream, []).append(stream.stream)

    LOGGER.info("selected_streams: %s", streams_to_sync)

    last_stream = singer.get_currently_syncing(state)
    LOGGER.info("last/currently syncing stream: %s", last_stream)
    failed_streams = []

    with singer.Transformer() as transformer:
        for stream_name in streams_to_sync:
            catalog_stream = catalog.get_stream(stream_name)
            stream = DynamicStream(client, catalog_stream, child_map=child_map)

            if stream.parent:
                if stream.parent not in streams_to_sync:
                    streams_to_sync.append(stream.parent)
                continue

            try:
                write_schema(stream, client, streams_to_sync, catalog)
                LOGGER.info("START Syncing: %s", stream_name)
                update_currently_syncing(state, stream_name)
                total_records = stream.sync(state=state, transformer=transformer)

                update_currently_syncing(state, None)
                LOGGER.info(
                    "FINISHED Syncing: %s, total_records: %s",
                    stream_name,
                    total_records,
                )
            except Exception as err:  # pragma: no cover
                failed_streams.append(stream_name)
                update_currently_syncing(state, None)
                LOGGER.warning("FAILED Syncing: %s, error: %s", stream_name, err)

    if failed_streams:
        LOGGER.warning("Streams failed due permissions/availability: %s", failed_streams)
