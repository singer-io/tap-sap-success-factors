import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

import singer
from singer import metadata

LOGGER = singer.get_logger()

# SAP OData annotation namespace for filterable / sortable attributes
SAP_DATA_NS = "{http://www.sap.com/Protocols/SAPData}"

# ---------------------------------------------------------------------------
# Group 4: Known parent-child relationships that EDMX inference misses.
# Keyed by snake_case stream name.
# ---------------------------------------------------------------------------
KNOWN_PARENT_OVERRIDES: Dict[str, Dict] = {
    # WorkflowAllowedActionList requires wfRequestId filter in every request.
    "workflow_allowed_action_list": {
        "parent-tap-stream-id": "wf_request",
        "parent-filter-field": "wfRequestId",
        "parent-key-field": "wfRequestId",
    },
    # GoalPlanState has userId as a filterable key; fetch per-user.
    "goal_plan_state": {
        "parent-tap-stream-id": "user",
        "parent-filter-field": "userId",
        "parent-key-field": "userId",
    },
    # ONB2ActivityNudgeDetails requires BOTH activityId AND activityObjectType.
    "onb2_activity_nudge_details": {
        "parent-tap-stream-id": "onb2_activity",
        "parent-filter-field": "activityId",
        "parent-key-field": "activityId",
        "parent-secondary-filter-field": "activityObjectType",
        "parent-secondary-key-field": "activityObjectType",
    },
}

# ---------------------------------------------------------------------------
# Group 5: Streams only accessible via OData $expand from a parent entity.
# Keyed by snake_case stream name.  The expand-parent-entity-set is the SAP
# entity set name (not a catalog stream name).
# ---------------------------------------------------------------------------
KNOWN_EXPAND_OVERRIDES: Dict[str, Dict] = {
    "emp_compensation_calculated": {
        "expand-nav-property": "empCompensationCalculatedNav",
        "expand-parent-entity-set": "EmpCompensation",
    },
    "emp_compensation_group_sum_calculated": {
        "expand-nav-property": "empCompensationGroupSumCalculatedNav",
        "expand-parent-entity-set": "EmpCompensation",
    },
    # SuccessStoreContentBlob is linked 1-to-1 from SuccessStoreContent via
    # the "contentData" navigation property (confirmed from entity service log).
    "success_store_content_blob": {
        "expand-nav-property": "contentData",
        "expand-parent-entity-set": "SuccessStoreContent",
    },
}

# ---------------------------------------------------------------------------
# Group 3 (runtime override): Streams whose lastModified* field is marked
# sap:filterable="true" in EDMX but rejected at runtime by the API with
# COE_BAD_PROPERTY_EXPRESSION.  Force FULL_TABLE so no $filter is added.
# ---------------------------------------------------------------------------
FORCED_FULL_TABLE_STREAMS = {
    "theme_info",
    "user_permissions",
}

EDM_TO_JSON_TYPE = {
    "Edm.String": ["null", "string"],
    "Edm.Guid": ["null", "string"],
    "Edm.Boolean": ["null", "boolean"],
    "Edm.Byte": ["null", "integer"],
    "Edm.Int16": ["null", "integer"],
    "Edm.Int32": ["null", "integer"],
    "Edm.Int64": ["null", "integer", "string"],
    "Edm.Decimal": ["null", "number", "string"],
    "Edm.Double": ["null", "number"],
    "Edm.Single": ["null", "number"],
    "Edm.DateTime": ["null", "string"],
    "Edm.DateTimeOffset": ["null", "string"],
    "Edm.Time": ["null", "string"],
    "Edm.Binary": ["null", "string"],
}

DATE_TIME_TYPES = {"Edm.DateTime", "Edm.DateTimeOffset"}


def to_snake_case(name: str) -> str:
    """Convert CamelCase/OData names to snake_case stream names."""
    name = name.replace("-", "_")
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _find_child(element: ET.Element, local_name: str):
    for child in list(element):
        if child.tag.endswith(local_name):
            return child
    return None


def _find_children(element: ET.Element, local_name: str) -> List[ET.Element]:
    return [child for child in list(element) if child.tag.endswith(local_name)]


def _build_association_map(schema_nodes: List[ET.Element]) -> Dict[str, Dict]:
    """Parse association metadata to infer parent-child candidates."""
    associations: Dict[str, Dict] = {}

    for schema_node in schema_nodes:
        namespace = schema_node.attrib.get("Namespace", "")
        for association in _find_children(schema_node, "Association"):
            name = association.attrib.get("Name")
            if not name:
                continue

            assoc_name = f"{namespace}.{name}" if namespace else name
            ends = {}
            for end in _find_children(association, "End"):
                role = end.attrib.get("Role")
                if not role:
                    continue
                ends[role] = {
                    "type": end.attrib.get("Type"),
                    "multiplicity": end.attrib.get("Multiplicity"),
                }

            principal_role: Optional[str] = None
            dependent_role: Optional[str] = None
            principal_keys: List[str] = []
            dependent_keys: List[str] = []

            ref = _find_child(association, "ReferentialConstraint")
            if ref is not None:
                principal = _find_child(ref, "Principal")
                dependent = _find_child(ref, "Dependent")

                if principal is not None:
                    principal_role = principal.attrib.get("Role")
                    principal_keys = [
                        p.attrib.get("Name")
                        for p in _find_children(principal, "PropertyRef")
                        if p.attrib.get("Name")
                    ]

                if dependent is not None:
                    dependent_role = dependent.attrib.get("Role")
                    dependent_keys = [
                        p.attrib.get("Name")
                        for p in _find_children(dependent, "PropertyRef")
                        if p.attrib.get("Name")
                    ]

            associations[assoc_name] = {
                "ends": ends,
                "principal_role": principal_role,
                "dependent_role": dependent_role,
                "principal_keys": principal_keys,
                "dependent_keys": dependent_keys,
            }

    return associations


def _infer_dependent_field(
    dependent_properties: Dict[str, Dict], principal_keys: List[str], nav_name: Optional[str]
) -> Optional[str]:
    """Infer foreign-key field in dependent entity when constraint is absent."""
    if not principal_keys:
        return None

    dep_fields = set(dependent_properties.keys())

    # Best case: principal key name exists directly on dependent entity
    for key in principal_keys:
        if key in dep_fields:
            return key

    # Common conventions: <navName><Key>, <navName>Id
    nav_base = nav_name or ""
    if nav_base:
        for key in principal_keys:
            candidates = [
                f"{nav_base}{key[:1].upper()}{key[1:]}",
                f"{nav_base}Id",
                f"{nav_base}_id",
            ]
            for candidate in candidates:
                if candidate in dep_fields:
                    return candidate

    return None


def _infer_parent_relationship(
    entity_type: str,
    nav: Dict,
    assoc: Dict,
    entity_type_to_set: Dict[str, str],
    entity_types: Dict[str, Dict],
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Infer parent relationship details for current entity.

    Returns: (parent_stream, parent_filter_field, parent_key_field, relationship_name, inference_mode)
    """
    ends = assoc.get("ends", {})
    dependent_role = assoc.get("dependent_role")
    principal_role = assoc.get("principal_role")

    # Path 1: Referential constraint available (authoritative)
    if dependent_role and principal_role:
        dependent_end = ends.get(dependent_role, {})
        principal_end = ends.get(principal_role, {})

        if dependent_end.get("type") != entity_type:
            return None, None, None, None, None

        principal_type = principal_end.get("type")
        principal_set = entity_type_to_set.get(principal_type)
        if not principal_set:
            return None, None, None, None, None

        dependent_keys = assoc.get("dependent_keys") or []
        principal_keys = assoc.get("principal_keys") or []
        if not dependent_keys or not principal_keys:
            return None, None, None, None, None

        return (
            to_snake_case(principal_set),
            dependent_keys[0],
            principal_keys[0],
            nav.get("relationship"),
            "referential_constraint",
        )

    # Path 2: No referential constraint, infer from multiplicity and nav roles
    from_role = nav.get("from_role")
    to_role = nav.get("to_role")

    if from_role in ends and to_role in ends:
        current_end = ends[from_role]
        target_end = ends[to_role]
    else:
        # Fallback match by type (if roles are not present)
        current_end = None
        target_end = None
        for end_data in ends.values():
            if end_data.get("type") == entity_type:
                current_end = end_data
            else:
                target_end = end_data
        if current_end is None or target_end is None:
            return None, None, None, None, None

    current_mult = current_end.get("multiplicity")
    target_mult = target_end.get("multiplicity")
    target_type = target_end.get("type")

    # Current entity is child when current is many and target is one/optional one
    if not (current_mult == "*" and target_mult in {"1", "0..1"}):
        return None, None, None, None, None

    parent_set = entity_type_to_set.get(target_type)
    if not parent_set:
        return None, None, None, None, None

    parent_entity_data = entity_types.get(target_type, {})
    principal_keys = parent_entity_data.get("keys", [])
    if not principal_keys:
        return None, None, None, None, None

    dependent_properties = entity_types.get(entity_type, {}).get("properties", {})
    dependent_field = _infer_dependent_field(
        dependent_properties,
        principal_keys,
        nav_name=nav.get("name"),
    )
    if not dependent_field:
        return None, None, None, None, None

    return (
        to_snake_case(parent_set),
        dependent_field,
        principal_keys[0],
        nav.get("relationship"),
        "multiplicity_heuristic",
    )


def discover_dynamic_streams(client) -> Tuple[Dict, Dict, Dict]:
    """Build schemas + Singer metadata for all entity sets from OData metadata."""
    endpoint = f"{client.base_url}{client.odata_path}/$metadata"
    LOGGER.info("Fetching OData metadata from %s", endpoint)
    response = client.request_raw(
        "GET",
        endpoint,
        headers={
            "Authorization": f"Bearer {client.get_access_token()}",
            "Accept": "application/xml",
        },
    )

    root = ET.fromstring(response.text)

    schema_nodes = []
    for data_services in _find_children(root, "DataServices"):
        schema_nodes.extend(_find_children(data_services, "Schema"))

    entity_types: Dict[str, Dict] = {}
    entity_sets: Dict[str, str] = {}
    entity_navigations: Dict[str, List[Dict]] = {}
    associations = _build_association_map(schema_nodes)

    for schema_node in schema_nodes:
        namespace = schema_node.attrib.get("Namespace", "")

        for entity_type in _find_children(schema_node, "EntityType"):
            entity_type_name = entity_type.attrib.get("Name")
            if not entity_type_name:
                continue

            fq_name = f"{namespace}.{entity_type_name}" if namespace else entity_type_name

            key_names = []
            key_node = _find_child(entity_type, "Key")
            if key_node is not None:
                for key_ref in _find_children(key_node, "PropertyRef"):
                    ref_name = key_ref.attrib.get("Name")
                    if ref_name:
                        key_names.append(ref_name)

            properties = {}
            filterable_props: set = set()
            navigations = []
            for prop in _find_children(entity_type, "Property"):
                prop_name = prop.attrib.get("Name")
                prop_type = prop.attrib.get("Type", "Edm.String")
                if not prop_name:
                    continue

                # Track OData-filterable properties via SAP annotation.
                # Default is filterable=true when the attribute is absent.
                sap_filterable = prop.attrib.get(f"{SAP_DATA_NS}filterable", "true")
                if sap_filterable.lower() != "false":
                    filterable_props.add(prop_name)

                json_prop = {"type": EDM_TO_JSON_TYPE.get(prop_type, ["null", "string"])}
                if prop_type in DATE_TIME_TYPES:
                    json_prop["format"] = "date-time"
                properties[prop_name] = json_prop

            for nav in _find_children(entity_type, "NavigationProperty"):
                relationship = nav.attrib.get("Relationship")
                if relationship:
                    navigations.append(
                        {
                            "name": nav.attrib.get("Name"),
                            "relationship": relationship,
                            "from_role": nav.attrib.get("FromRole"),
                            "to_role": nav.attrib.get("ToRole"),
                        }
                    )

            entity_types[fq_name] = {
                "keys": key_names,
                "properties": properties,
                "filterable_props": filterable_props,
            }
            entity_navigations[fq_name] = navigations

        for container in _find_children(schema_node, "EntityContainer"):
            for entity_set in _find_children(container, "EntitySet"):
                set_name = entity_set.attrib.get("Name")
                set_entity_type = entity_set.attrib.get("EntityType")
                if set_name and set_entity_type:
                    entity_sets[set_name] = set_entity_type

    schemas = {}
    field_metadata = {}
    stream_defs = {}

    entity_type_to_set = {
        entity_type: set_name for set_name, entity_type in entity_sets.items()
    }
    stream_to_entity_type = {
        to_snake_case(set_name): entity_type
        for set_name, entity_type in entity_sets.items()
    }
    # Pre-compute the full set of snake_case stream names that will be
    # discoverable from this EDMX.  Used to validate parent overrides below.
    discovered_stream_names = {to_snake_case(s) for s in entity_sets}

    for set_name, entity_type in entity_sets.items():
        entity_data = entity_types.get(entity_type)
        if not entity_data:
            continue

        stream_name = to_snake_case(set_name)
        properties = {
            prop_name: dict(prop_schema)
            for prop_name, prop_schema in entity_data["properties"].items()
        }
        key_properties = entity_data["keys"]

        replication_keys = []
        # Only use a replication key candidate if it exists in the schema AND
        # is OData-filterable.  When EDMX has no SAP filterable annotations the
        # filterable_props set defaults to all properties (fully permissive).
        entity_filterable = entity_data.get("filterable_props", set(properties.keys()))
        for candidate in ["lastModifiedDateTime", "lastModifiedOn", "lastModifiedDate"]:
            if candidate in properties and candidate in entity_filterable:
                replication_keys = [candidate]
                break

        # Runtime override: EDMX annotation is misleading for these streams.
        # The API rejects the lastModified* field as non-filterable at runtime.
        if stream_name in FORCED_FULL_TABLE_STREAMS:
            replication_keys = []
            LOGGER.info(
                "Forced FULL_TABLE for %s (EDMX filterable annotation is inaccurate at runtime)",
                stream_name,
            )

        replication_method = "INCREMENTAL" if replication_keys else "FULL_TABLE"

        parent_stream = None
        parent_filter_field = None
        parent_key_field = None
        relationship_name = None

        relationship_inference = None
        for nav in entity_navigations.get(entity_type, []):
            assoc = associations.get(nav.get("relationship"))
            if not assoc:
                continue

            (
                parent_stream,
                parent_filter_field,
                parent_key_field,
                relationship_name,
                relationship_inference,
            ) = _infer_parent_relationship(
                entity_type,
                nav,
                assoc,
                entity_type_to_set,
                entity_types,
            )
            if parent_stream == stream_name:
                parent_stream = None
                parent_filter_field = None
                parent_key_field = None
                relationship_name = None
                relationship_inference = None
            if parent_stream:
                break

        # ------------------------------------------------------------------
        # Group 4: Apply hardcoded parent overrides when EDMX inference could
        # not detect the relationship (e.g. no navigation property on child).
        # Guard: only apply the override when the declared parent is actually
        # present in the EDMX for this instance — otherwise the child stream
        # would be permanently orphaned and silently never sync.
        # ------------------------------------------------------------------
        parent_secondary_filter_field = None
        parent_secondary_key_field = None
        if not parent_stream and stream_name in KNOWN_PARENT_OVERRIDES:
            override = KNOWN_PARENT_OVERRIDES[stream_name]
            declared_parent = override["parent-tap-stream-id"]
            if declared_parent not in discovered_stream_names:
                LOGGER.warning(
                    "Skipping parent override for %s: declared parent '%s' was not "
                    "discovered in this EDMX instance. Stream will be attempted as "
                    "FULL_TABLE direct query.",
                    stream_name,
                    declared_parent,
                )
            else:
                parent_stream = declared_parent
                parent_filter_field = override["parent-filter-field"]
                parent_key_field = override["parent-key-field"]
                parent_secondary_filter_field = override.get("parent-secondary-filter-field")
                parent_secondary_key_field = override.get("parent-secondary-key-field")
                relationship_name = None
                relationship_inference = "manual_override"
                LOGGER.info(
                    "Applied parent override for %s -> parent=%s",
                    stream_name,
                    parent_stream,
                )

        parent_id_field = None
        if parent_stream and parent_key_field:
            # ------------------------------------------------------------------
            # Final validation: ensure the resolved parent (whether inferred
            # from EDMX associations or from KNOWN_PARENT_OVERRIDES) actually
            # exists as a discoverable entity set in this EDMX instance.
            # Without this, a child stream would reference a phantom parent,
            # causing it to be silently orphaned and never synced.
            # ------------------------------------------------------------------
            if parent_stream not in discovered_stream_names:
                LOGGER.warning(
                    "Dropping parent '%s' for stream '%s': parent is not discoverable "
                    "in this EDMX instance (inferred via %s). "
                    "Stream will be synced as FULL_TABLE direct query.",
                    parent_stream,
                    stream_name,
                    relationship_inference or "unknown",
                )
                parent_stream = None
                parent_filter_field = None
                parent_key_field = None
                parent_secondary_filter_field = None
                parent_secondary_key_field = None
                relationship_name = None
                relationship_inference = None

        if parent_stream and parent_key_field:
            parent_entity_type = stream_to_entity_type.get(parent_stream)
            parent_properties = entity_types.get(parent_entity_type, {}).get(
                "properties", {}
            )
            parent_pk_schema = dict(
                parent_properties.get(parent_key_field, {"type": ["null", "string"]})
            )

            if parent_filter_field and parent_filter_field not in properties:
                properties[parent_filter_field] = dict(parent_pk_schema)

            parent_id_field = f"__parent_{parent_stream}_{parent_key_field}"
            properties[parent_id_field] = dict(parent_pk_schema)

        schemas[stream_name] = {
            "type": "object",
            "additionalProperties": True,
            "properties": properties,
        }

        mdata = metadata.new()
        mdata = metadata.get_standard_metadata(
            schema=schemas[stream_name],
            key_properties=key_properties,
            valid_replication_keys=replication_keys,
            replication_method=replication_method,
        )
        mdata = metadata.to_map(mdata)
        mdata = metadata.write(mdata, (), "entity-set", set_name)
        if parent_stream:
            mdata = metadata.write(
                mdata,
                (),
                "parent-tap-stream-id",
                parent_stream,
            )
            mdata = metadata.write(mdata, (), "parent-filter-field", parent_filter_field)
            mdata = metadata.write(mdata, (), "parent-key-field", parent_key_field)
            if parent_secondary_filter_field:
                mdata = metadata.write(
                    mdata, (), "parent-secondary-filter-field", parent_secondary_filter_field
                )
            if parent_secondary_key_field:
                mdata = metadata.write(
                    mdata, (), "parent-secondary-key-field", parent_secondary_key_field
                )

        # ------------------------------------------------------------------
        # Group 5: Write $expand metadata for streams that can only be
        # fetched via OData navigation from a parent entity set.
        # ------------------------------------------------------------------
        if stream_name in KNOWN_EXPAND_OVERRIDES:
            expand_info = KNOWN_EXPAND_OVERRIDES[stream_name]
            mdata = metadata.write(
                mdata, (), "expand-nav-property", expand_info["expand-nav-property"]
            )
            mdata = metadata.write(
                mdata,
                (),
                "expand-parent-entity-set",
                expand_info["expand-parent-entity-set"],
            )
            LOGGER.info(
                "Configured $expand for %s via %s.%s",
                stream_name,
                expand_info["expand-parent-entity-set"],
                expand_info["expand-nav-property"],
            )

        automatic_fields = list(key_properties + replication_keys)
        if parent_filter_field:
            automatic_fields.append(parent_filter_field)
        if parent_id_field:
            automatic_fields.append(parent_id_field)

        for automatic_field in automatic_fields:
            if automatic_field in properties:
                mdata = metadata.write(
                    mdata,
                    ("properties", automatic_field),
                    "inclusion",
                    "automatic",
                )

        field_metadata[stream_name] = metadata.to_list(mdata)

        stream_defs[stream_name] = {
            "entity_set": set_name,
            "path": f"{client.odata_path}/{set_name}",
            "key_properties": key_properties,
            "replication_keys": replication_keys,
            "replication_method": replication_method,
            "parent_stream": parent_stream,
            "parent_filter_field": parent_filter_field,
            "parent_key_field": parent_key_field,
            "relationship": relationship_name,
            "relationship_inference": relationship_inference,
        }

    LOGGER.info("Dynamic metadata discovery found %s entity sets", len(stream_defs))
    return schemas, field_metadata, stream_defs
