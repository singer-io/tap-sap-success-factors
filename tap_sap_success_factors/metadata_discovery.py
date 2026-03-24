import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

import singer
from singer import metadata

LOGGER = singer.get_logger()

# SAP OData annotation namespace for filterable / sortable attributes.
# The actual SAP SuccessFactors EDMX declares:
#   xmlns:sap="http://www.successfactors.com/edm/sap"
# NOT the commonly-cited http://www.sap.com/Protocols/SAPData URI.
# Step 2 of _get_sap_attrib provides a namespace-agnostic fallback so the
# tap continues to work if SAP ever changes the URI across API versions.
SAP_DATA_NS = "{http://www.successfactors.com/edm/sap}"

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
# Navigation properties that must NEVER be used as automatic $expand targets.
#
# wfRequestNav: SAP documents (KBA 2604638, KBA 2963505) that expanding this
# nav on normal (non-pending) data throws COE0025 —
# "Expand workflow navigation from normal data is NOT supported."
# It only returns data when the parent entity has recordStatus=pending,
# which would yield only unapproved records — not suitable for general
# data extraction.
# ---------------------------------------------------------------------------
BLOCKED_EXPAND_NAV_PROPERTIES = {
    "wfRequestNav",
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


def _get_sap_attrib(
    element: ET.Element, local_attr: str, default: str = "true"
) -> str:
    """Read a SAP annotation attribute by *local name*, namespace-agnostic.

    ElementTree only expands Clark-notation keys ({ns}name) when the namespace
    URI in the document exactly matches.  SAP instances sometimes differ in
    casing or trailing characters, so the exact key lookup can silently miss.
    We therefore first try the canonical key, then scan every attribute for one
    whose local name matches.
    """
    # 1. Exact namespace match (fast path, works when URIs are identical)
    exact_key = f"{SAP_DATA_NS}{local_attr}"
    if exact_key in element.attrib:
        return element.attrib[exact_key]
    # 2. Namespace-agnostic scan: matches any Clark-notation key whose local
    # name equals local_attr regardless of the namespace URI.  Guards against
    # SAP changing the URI across API versions or backend releases.
    suffix = f"}}{local_attr}"
    for key, val in element.attrib.items():
        if key.endswith(suffix):
            return val
    return default


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


def _rescue_type_mismatched_filter_field(
    nav_name: Optional[str],
    par_is_dt: bool,
    dependent_properties: Dict[str, Dict],
) -> Optional[str]:
    """Find a type-compatible child filter field when the inferred one mismatches.

    Called when ``_infer_dependent_field`` picks a child field whose
    JSON-Schema type (date-time or not) differs from the parent key field
    it must be equated to in an OData ``$filter`` clause.

    Strategy
    --------
    Derive a candidate FK field name from the navigation property name
    (e.g. ``countryNav`` → ``country``, ``jobCountryNav`` → ``jobCountry``),
    then verify it exists on the child entity *and* shares the same
    date-time-ness as the parent key field.

    Example
    -------
    TimeZone.countryNav → Country.  Country PK = (code:String,
    effectiveStartDate:DateTime).  ``_infer_dependent_field`` wrongly picks
    ``effectiveStartDate`` (DateTime) because it shares the name with a PK
    component.  This function strips ``Nav`` from ``countryNav`` → ``country``
    and finds ``country`` (String) on TimeZone — type-compatible with
    ``code`` (String) → returns ``'country'``.

    Parameters
    ----------
    nav_name:
        Name of the NavigationProperty that produced the relationship,
        e.g. ``'countryNav'`` or ``'jobCountryNav'``.
    par_is_dt:
        Whether the parent key field has ``format: date-time`` (True) or not.
    dependent_properties:
        JSON-Schema property map of the child entity.

    Returns
    -------
    str | None
        Name of a type-compatible child field, or ``None`` if none found.
    """
    base = nav_name or ""
    # Strip recognised Navigation-property suffixes to get the FK base name.
    for suffix in ("Nav", "nav"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break

    candidates: List[str] = []
    if base:
        candidates.extend([base, f"{base}Id", f"{base}Code"])

    for candidate in candidates:
        if candidate not in dependent_properties:
            continue
        cand_is_dt = (
            dependent_properties[candidate].get("format") == "date-time"
        )
        if cand_is_dt == par_is_dt:
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
            "Authorization": client.get_auth_header(),
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
            prop_elements = _find_children(entity_type, "Property")
            # Detect SAP "computed / expand-only" entities: every property has
            # sap:filterable=false, sap:sortable=false, sap:creatable=false AND
            # the entity has no outbound NavigationProperties.  The SAP API
            # rejects direct queries on these with COE0025 and requires them
            # to be fetched via OData $expand from a parent entity.
            # This covers both all-Edm.Byte permission entities and mixed-type
            # calculated entities (EmpCompensationCalculated, etc.).

            def _all_sap_false(elems, attr):
                return bool(elems) and all(
                    _get_sap_attrib(p, attr, "true").lower() == "false"
                    for p in elems
                )
            is_expand_only = (
                _all_sap_false(prop_elements, "filterable")
                and _all_sap_false(prop_elements, "sortable")
                and _all_sap_false(prop_elements, "creatable")
                and not _find_children(entity_type, "NavigationProperty")
            )
            navigations = []
            for prop in prop_elements:
                prop_name = prop.attrib.get("Name")
                prop_type = prop.attrib.get("Type", "Edm.String")
                if not prop_name:
                    continue

                # Track OData-filterable properties via SAP annotation.
                # Default is filterable=true when the attribute is absent.
                sap_filterable = _get_sap_attrib(prop, "filterable", "true")
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
                "is_expand_only": is_expand_only,
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

    # ------------------------------------------------------------------
    # Build a reverse navigation map: target_entity_type ->
    # (source_entity_type, nav_property_name).  Used to auto-detect
    # the $expand parent+nav for all-Edm.Byte (field-controls) entities.
    # ------------------------------------------------------------------
    reverse_nav: Dict[str, Tuple[str, str]] = {}
    for src_et, navs in entity_navigations.items():
        for nav in navs:
            nav_name = nav.get("name")
            if nav_name in BLOCKED_EXPAND_NAV_PROPERTIES:
                continue
            assoc = associations.get(nav.get("relationship"))
            if not assoc:
                continue
            to_role = nav.get("to_role")
            tgt_type = assoc.get("ends", {}).get(to_role, {}).get("type")
            if tgt_type and tgt_type != src_et:
                reverse_nav.setdefault(tgt_type, (src_et, nav_name))

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

        replication_method = "INCREMENTAL" if replication_keys else "FULL_TABLE"

        parent_stream = None
        parent_filter_field = None
        parent_key_field = None
        relationship_name = None

        relationship_inference = None
        # Name of the NavigationProperty that produced the accepted
        # relationship; used later for type-mismatch rescue.
        matched_nav_name: Optional[str] = None
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
                matched_nav_name = nav.get("name")
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
                    "Dropping parent '%s' for stream '%s': parent is not "
                    "discoverable in this EDMX instance (inferred via %s). "
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

        # ------------------------------------------------------------------
        # Type-compatibility guard: when the inferred parent_filter_field
        # (child-side) and parent_key_field (parent-side) have incompatible
        # JSON Schema types the OData $filter clause would be invalid.
        #
        # Classic false-positive (no ReferentialConstraint):
        #   TimeZone.countryNav → Country  (PK: code:String,
        #                                       effectiveStartDate:DateTime)
        #   _infer_dependent_field finds effectiveStartDate on TimeZone
        #   → parent_filter_field='effectiveStartDate' (DateTime)
        #   → parent_key_field='code' (String)
        #   → $filter: effectiveStartDate eq 'BTN'  ← SAP rejects (HTTP 400)
        #
        # Rescue strategy
        # ---------------
        # Before giving up, attempt to find a *type-compatible* child field
        # by stripping the "Nav" suffix from the nav property name and
        # looking for that base name on the child entity:
        #   countryNav → country (String on TimeZone) ← type-compatible ✓
        #   jobCountryNav → jobCountry (String on PaymentInformationV3) ✓
        # If a compatible field is found it replaces parent_filter_field.
        # Only when no rescue field exists is the relationship dropped.
        # ------------------------------------------------------------------
        if parent_stream and parent_filter_field and parent_key_field:
            child_fld_schema = properties.get(parent_filter_field, {})
            _par_et = stream_to_entity_type.get(parent_stream)
            _par_props = (
                entity_types.get(_par_et, {}).get("properties", {})
            )
            par_fld_schema = _par_props.get(parent_key_field, {})
            child_is_dt = child_fld_schema.get("format") == "date-time"
            par_is_dt = par_fld_schema.get("format") == "date-time"
            if child_is_dt != par_is_dt:
                # ----------------------------------------------------------
                # Two-stage rescue strategy:
                #
                # Stage 1 (Option B) — only when the parent's first PK is
                # DateTime but the child FK is String: scan the remaining
                # parent PKs for a non-DateTime one and use it instead.
                # e.g. PickListValueV2 PK order:
                #   [PickListV2_effectiveStartDate(DateTime),  ← wrong
                #    PickListV2_id(String)]                    ← correct
                # Child FK (e.g. defaultEmployeeClass) is String, so we
                # swap parent_key_field to the first non-DateTime PK.
                #
                # Stage 2 — only when the child FK is DateTime but the
                # parent PK is String: strip the NavigationProperty's Nav
                # suffix to find a String-typed FK on the child entity.
                # e.g. TimeZone.countryNav → 'country' (String) replaces
                # the wrongly-inferred 'effectiveStartDate' (DateTime).
                # ----------------------------------------------------------
                alt_par_key = None
                if par_is_dt and not child_is_dt:
                    # Stage 1: find a non-DateTime alternate parent PK.
                    _par_keys = entity_types.get(_par_et, {}).get("keys", [])
                    alt_par_key = next(
                        (
                            pk for pk in _par_keys
                            if pk != parent_key_field
                            and (
                                _par_props.get(pk, {}).get("format")
                                == "date-time"
                            ) == child_is_dt  # child_is_dt is False here
                        ),
                        None,
                    )

                rescued_filter = None
                if not alt_par_key:
                    # Stage 2: try nav-name rescue on the child side.
                    rescued_filter = _rescue_type_mismatched_filter_field(
                        matched_nav_name,
                        par_is_dt,
                        properties,
                    )

                if alt_par_key:
                    LOGGER.info(
                        "Rescued parent relationship '%s' → '%s': "
                        "replaced type-mismatched parent_key_field '%s' "
                        "(date-time=%s) with alternate PK '%s' "
                        "(type-compatible with parent_filter_field '%s')",
                        stream_name,
                        parent_stream,
                        parent_key_field,
                        par_is_dt,
                        alt_par_key,
                        parent_filter_field,
                    )
                    parent_key_field = alt_par_key
                elif rescued_filter:
                    LOGGER.info(
                        "Rescued parent relationship '%s' → '%s': "
                        "replaced type-mismatched parent_filter_field "
                        "'%s' (date-time=%s) with '%s' "
                        "(type-compatible with parent_key_field '%s')",
                        stream_name,
                        parent_stream,
                        parent_filter_field,
                        child_is_dt,
                        rescued_filter,
                        parent_key_field,
                    )
                    parent_filter_field = rescued_filter
                else:
                    LOGGER.warning(
                        "Dropping parent '%s' for stream '%s': "
                        "type mismatch — parent_filter_field '%s' "
                        "(date-time=%s) vs parent_key_field '%s' "
                        "(date-time=%s) and no rescue field found. "
                        "Stream will be synced as FULL_TABLE.",
                        parent_stream,
                        stream_name,
                        parent_filter_field,
                        child_is_dt,
                        parent_key_field,
                        par_is_dt,
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
        # Group 5: Auto-detect $expand for computed/read-only entities.
        #
        # Signal: ALL properties have sap:filterable=false, sap:sortable=false,
        # sap:creatable=false AND the entity has no outbound NavigationProperty.
        # SAP refuses direct queries on these with COE0025 / COE0018 and
        # requires them to be fetched via OData $expand from a parent entity.
        # The parent entity set and nav property name are resolved from the
        # reverse navigation map built above.
        # ------------------------------------------------------------------
        expand_info: Optional[Dict] = None

        if entity_data.get("is_expand_only", False):
            src_type, nav_name = reverse_nav.get(entity_type, (None, None))
            parent_set_name = (
                entity_type_to_set.get(src_type) if src_type else None
            )
            if parent_set_name and nav_name:
                expand_info = {
                    "expand-nav-property": nav_name,
                    "expand-parent-entity-set": parent_set_name,
                }
            else:
                LOGGER.warning(
                    "Stream '%s' matches expand-only pattern but no reverse "
                    "NavigationProperty found — will attempt direct query.",
                    stream_name,
                )

        if expand_info:
            mdata = metadata.write(
                mdata, (), "expand-nav-property",
                expand_info["expand-nav-property"],
            )
            mdata = metadata.write(
                mdata, (), "expand-parent-entity-set",
                expand_info["expand-parent-entity-set"],
            )
            LOGGER.info(
                "Configured $expand for %s via %s.%s",
                stream_name,
                expand_info["expand-parent-entity-set"],
                expand_info["expand-nav-property"],
            )

        # Only primary-key and replication-key fields are marked automatic.
        # parent_filter_field and parent_id_field are available fields:
        #   - parent_filter_field is a native schema field used as an OData
        #     $filter join key; users can select/deselect it freely.
        #   - parent_id_field (__parent_*) is a synthetic field injected at
        #     sync time; marking it automatic would break test_available_fields
        #     because the Singer spec reserves "automatic" for PKs and rep-keys.
        automatic_fields = list(key_properties + replication_keys)

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
            # JSON schema of the parent_filter_field (e.g. {"type": ["null",
            # "integer"]} or {"type": ["null", "string"], "format":
            # "date-time"}).  Used by stream_probe to build a type-compatible
            # dummy filter value so SAP returns 403 (permission denied)
            # rather than 400 (type validation error) for blocked streams.
            "parent_filter_field_schema": (
                dict(properties.get(parent_filter_field, {}))
                if parent_filter_field else {}
            ),
            "parent_key_field": parent_key_field,
            "relationship": relationship_name,
            "relationship_inference": relationship_inference,
            # Expand-only streams: probing them directly always fails
            # (SAP COE0025/COE0018) because they require $expand context.
            # Stored here so the probe can skip them correctly.
            "expand_parent_entity_set": (
                expand_info["expand-parent-entity-set"]
                if expand_info else None
            ),
        }

    LOGGER.info("Dynamic metadata discovery found %s entity sets", len(stream_defs))
    return schemas, field_metadata, stream_defs
