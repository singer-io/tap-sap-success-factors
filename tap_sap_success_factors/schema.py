from singer import metadata

from tap_sap_success_factors.streams.dynamic import DynamicStream


def _build_child_map(catalog):
    child_map = {}
    for stream in catalog.streams:
        root_mdata = metadata.to_map(stream.metadata).get((), {})
        parent_stream = (
            root_mdata.get("parent-tap-stream-id") or root_mdata.get("parent-stream")
        )
        if not parent_stream:
            continue
        child_map.setdefault(parent_stream, []).append(stream.tap_stream_id)
    return child_map


def write_schema(stream, client, streams_to_sync, catalog, visited=None, child_map=None) -> None:
    """Emit schema message for selected stream.

    Dynamic discovery workflow does not recursively construct static child streams.
    """
    visited = visited or set()
    if stream.tap_stream_id in visited:
        return
    visited.add(stream.tap_stream_id)

    child_map = child_map or _build_child_map(catalog)

    if stream.is_selected():
        stream.write_schema()

    for child_stream_name in child_map.get(stream.tap_stream_id, []):
        child_catalog = catalog.get_stream(child_stream_name)
        child_stream = DynamicStream(client, child_catalog, child_map=child_map)

        write_schema(
            child_stream,
            client,
            streams_to_sync,
            catalog,
            visited=visited,
            child_map=child_map,
        )

        if child_stream_name in streams_to_sync:
            stream.child_to_sync.append(child_stream)
