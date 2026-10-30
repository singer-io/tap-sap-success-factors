"""Composition-only parent inference: a parent key must live in the child key."""
import unittest
from unittest.mock import Mock

from tap_sap_success_factors.metadata_discovery import discover_dynamic_streams

STR = "Edm.String"
DT = "Edm.DateTime"
STR_NOT_FILTERABLE = "Edm.String;nofilter"


def _property_xml(name, edm_type):
    edm_type, _, flag = edm_type.partition(";")
    sap = ' sap:filterable="false"' if flag == "nofilter" else ""
    return f'<Property Name="{name}" Type="{edm_type}"{sap}/>'


def _client(metadata_xml):
    response = Mock()
    response.text = metadata_xml
    client = Mock()
    client.base_url = "https://example.successfactors.com"
    client.odata_path = "/odata/v2"
    client.request_raw.return_value = response
    return client


def _edmx(entities, associations=""):
    """Build an EDMX document.

    ``entities`` is a list of (name, keys, props, navs); props maps a property
    name to its EDM type and navs is a list of (nav_name, association, to_role).
    """
    parts = []
    sets = []
    for name, keys, props, navs in entities:
        key_xml = "".join(f'<PropertyRef Name="{k}"/>' for k in keys)
        prop_xml = "".join(_property_xml(p, t) for p, t in props.items())
        nav_xml = "".join(
            f'<NavigationProperty Name="{n}" Relationship="SFOData.{a}" '
            f'FromRole="{name}" ToRole="{r}"/>'
            for n, a, r in navs
        )
        parts.append(
            f'<EntityType Name="{name}"><Key>{key_xml}</Key>'
            f"{prop_xml}{nav_xml}</EntityType>"
        )
        sets.append(f'<EntitySet Name="{name}" EntityType="SFOData.{name}"/>')
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">'
        "<edmx:DataServices>"
        '<Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm" '
        'Namespace="SFOData" xmlns:sap="http://www.successfactors.com/edm/sap">'
        + "".join(parts)
        + associations
        + '<EntityContainer Name="C" m:IsDefaultEntityContainer="true" '
        'xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">'
        + "".join(sets)
        + "</EntityContainer></Schema></edmx:DataServices></edmx:Edmx>"
    )


def _assoc(name, child, parent, parent_mult="1", constraint=""):
    return (
        f'<Association Name="{name}">'
        f'<End Type="SFOData.{child}" Multiplicity="*" Role="{child}"/>'
        f'<End Type="SFOData.{parent}" Multiplicity="{parent_mult}" '
        f'Role="{parent}"/>{constraint}</Association>'
    )


def _constraint(principal_key, dependent_key):
    return (
        "<ReferentialConstraint>"
        f'<Principal Role="Parent"><PropertyRef Name="{principal_key}"/></Principal>'
        f'<Dependent Role="Child"><PropertyRef Name="{dependent_key}"/></Dependent>'
        "</ReferentialConstraint>"
    )


def _discover(entities, associations=""):
    return discover_dynamic_streams(_client(_edmx(entities, associations)))


class TestCompositionParentInference(unittest.TestCase):

    def test_same_name_non_generic_key_links(self):
        _, _, defs = _discover(
            [
                ("Employment", ["userId"], {"userId": STR}, []),
                (
                    "Job",
                    ["userId", "seqNumber"],
                    {"userId": STR, "seqNumber": STR},
                    [("employmentNav", "Employment_Job", "Employment")],
                ),
            ],
            _assoc("Employment_Job", "Job", "Employment"),
        )
        job = defs["job"]
        self.assertEqual(job["parent_stream"], "employment")
        self.assertEqual(job["parent_filter_field"], "userId")
        self.assertEqual(job["parent_key_field"], "userId")
        self.assertEqual(job["relationship_inference"], "key_composition")

    def test_prefixed_key_links_for_generic_parent_key(self):
        _, _, defs = _discover(
            [
                ("DayModel", ["externalCode"], {"externalCode": STR}, []),
                (
                    "Assignment",
                    ["DayModel_externalCode", "externalCode"],
                    {"DayModel_externalCode": STR, "externalCode": STR},
                    [("dayModelNav", "DayModel_Assignment", "DayModel")],
                ),
            ],
            _assoc("DayModel_Assignment", "Assignment", "DayModel"),
        )
        assignment = defs["assignment"]
        self.assertEqual(assignment["parent_stream"], "day_model")
        self.assertEqual(assignment["parent_filter_field"], "DayModel_externalCode")
        self.assertEqual(assignment["parent_key_field"], "externalCode")

    def test_generic_key_name_alone_does_not_link(self):
        _, _, defs = _discover(
            [
                ("Parent", ["externalCode"], {"externalCode": STR}, []),
                (
                    "Child",
                    ["externalCode", "seq"],
                    {"externalCode": STR, "seq": STR},
                    [("parentNav", "Parent_Child", "Parent")],
                ),
            ],
            _assoc("Parent_Child", "Child", "Parent"),
        )
        self.assertIsNone(defs["child"]["parent_stream"])

    def test_non_key_field_does_not_link(self):
        _, _, defs = _discover(
            [
                ("Parent", ["parentId"], {"parentId": STR}, []),
                (
                    "Child",
                    ["childId"],
                    {"childId": STR, "parentId": STR},
                    [("parentNav", "Parent_Child", "Parent")],
                ),
            ],
            _assoc("Parent_Child", "Child", "Parent"),
        )
        self.assertIsNone(defs["child"]["parent_stream"])

    def test_lone_key_sharing_parent_key_name_is_excluded(self):
        _, _, defs = _discover(
            [
                ("Parent", ["userId"], {"userId": STR}, []),
                (
                    "Child",
                    ["userId"],
                    {"userId": STR},
                    [("parentNav", "Parent_Child", "Parent")],
                ),
            ],
            _assoc("Parent_Child", "Child", "Parent"),
        )
        self.assertIsNone(defs["child"]["parent_stream"])

    def test_parent_with_date_time_key_is_never_linked(self):
        _, _, defs = _discover(
            [
                ("Parent", ["effDate"], {"effDate": DT}, []),
                (
                    "Child",
                    ["effDate", "seq"],
                    {"effDate": DT, "seq": STR},
                    [("parentNav", "Parent_Child", "Parent")],
                ),
            ],
            _assoc("Parent_Child", "Child", "Parent"),
        )
        self.assertIsNone(defs["child"]["parent_stream"])

    def test_parent_with_composite_key_is_never_linked(self):
        _, _, defs = _discover(
            [
                (
                    "Parent",
                    ["effDate", "parentCode"],
                    {"effDate": DT, "parentCode": STR},
                    [],
                ),
                (
                    "Child",
                    ["effDate", "parentCode", "seq"],
                    {"effDate": DT, "parentCode": STR, "seq": STR},
                    [("parentNav", "Parent_Child", "Parent")],
                ),
            ],
            _assoc("Parent_Child", "Child", "Parent"),
        )
        self.assertIsNone(defs["child"]["parent_stream"])

    def test_non_filterable_child_key_is_never_linked(self):
        _, _, defs = _discover(
            [
                ("Parent", ["userId"], {"userId": STR}, []),
                (
                    "Child",
                    ["userId", "seq"],
                    {"userId": STR_NOT_FILTERABLE, "seq": STR},
                    [("parentNav", "Parent_Child", "Parent")],
                ),
            ],
            _assoc("Parent_Child", "Child", "Parent"),
        )
        self.assertIsNone(defs["child"]["parent_stream"])

    def test_non_filterable_constraint_field_is_never_linked(self):
        _, _, defs = _discover(
            [
                ("Parent", ["parentId"], {"parentId": STR}, []),
                (
                    "Child",
                    ["childId"],
                    {"childId": STR, "ownerRef": STR_NOT_FILTERABLE},
                    [("parentNav", "Parent_Child", "Parent")],
                ),
            ],
            _assoc(
                "Parent_Child", "Child", "Parent",
                constraint=_constraint("parentId", "ownerRef"),
            ),
        )
        self.assertIsNone(defs["child"]["parent_stream"])

    def test_multi_key_constraint_is_never_linked(self):
        constraint = (
            "<ReferentialConstraint>"
            '<Principal Role="Parent"><PropertyRef Name="a"/>'
            '<PropertyRef Name="b"/></Principal>'
            '<Dependent Role="Child"><PropertyRef Name="ra"/>'
            '<PropertyRef Name="rb"/></Dependent>'
            "</ReferentialConstraint>"
        )
        _, _, defs = _discover(
            [
                ("Parent", ["a", "b"], {"a": STR, "b": STR}, []),
                (
                    "Child",
                    ["childId"],
                    {"childId": STR, "ra": STR, "rb": STR},
                    [("parentNav", "Parent_Child", "Parent")],
                ),
            ],
            _assoc("Parent_Child", "Child", "Parent", constraint=constraint),
        )
        self.assertIsNone(defs["child"]["parent_stream"])

    def test_constraint_to_date_time_parent_key_is_never_linked(self):
        _, _, defs = _discover(
            [
                ("Parent", ["stamp"], {"stamp": DT}, []),
                (
                    "Child",
                    ["childId"],
                    {"childId": STR, "ownerStamp": DT},
                    [("parentNav", "Parent_Child", "Parent")],
                ),
            ],
            _assoc(
                "Parent_Child", "Child", "Parent",
                constraint=_constraint("stamp", "ownerStamp"),
            ),
        )
        self.assertIsNone(defs["child"]["parent_stream"])

    def test_one_to_many_navigation_is_not_a_candidate(self):
        _, _, defs = _discover(
            [
                ("Parent", ["userId"], {"userId": STR}, []),
                (
                    "Child",
                    ["userId", "seq"],
                    {"userId": STR, "seq": STR},
                    [("parentNav", "Parent_Child", "Parent")],
                ),
            ],
            _assoc("Parent_Child", "Child", "Parent", parent_mult="*"),
        )
        self.assertIsNone(defs["child"]["parent_stream"])

    def test_exactly_one_target_beats_optional_target(self):
        _, _, defs = _discover(
            [
                ("Optional", ["aId"], {"aId": STR}, []),
                ("Mandatory", ["bId"], {"bId": STR}, []),
                (
                    "Child",
                    ["aId", "bId"],
                    {"aId": STR, "bId": STR},
                    [
                        ("optionalNav", "Optional_Child", "Optional"),
                        ("mandatoryNav", "Mandatory_Child", "Mandatory"),
                    ],
                ),
            ],
            _assoc("Optional_Child", "Child", "Optional", parent_mult="0..1")
            + _assoc("Mandatory_Child", "Child", "Mandatory"),
        )
        self.assertEqual(defs["child"]["parent_stream"], "mandatory")

    def test_tie_keeps_first_navigation(self):
        _, _, defs = _discover(
            [
                ("First", ["aId"], {"aId": STR}, []),
                ("Second", ["bId"], {"bId": STR}, []),
                (
                    "Child",
                    ["aId", "bId"],
                    {"aId": STR, "bId": STR},
                    [
                        ("firstNav", "First_Child", "First"),
                        ("secondNav", "Second_Child", "Second"),
                    ],
                ),
            ],
            _assoc("First_Child", "Child", "First")
            + _assoc("Second_Child", "Child", "Second"),
        )
        self.assertEqual(defs["child"]["parent_stream"], "first")

    def test_referential_constraint_wins(self):
        _, _, defs = _discover(
            [
                ("Parent", ["parentId"], {"parentId": STR}, []),
                (
                    "Child",
                    ["childId"],
                    {"childId": STR, "ownerRef": STR},
                    [("parentNav", "Parent_Child", "Parent")],
                ),
            ],
            _assoc(
                "Parent_Child", "Child", "Parent",
                constraint=_constraint("parentId", "ownerRef"),
            ),
        )
        child = defs["child"]
        self.assertEqual(child["parent_stream"], "parent")
        self.assertEqual(child["parent_filter_field"], "ownerRef")
        self.assertEqual(child["relationship_inference"], "referential_constraint")

    def test_entity_without_navigation_is_root(self):
        _, _, defs = _discover([("Solo", ["id"], {"id": STR}, [])])
        self.assertIsNone(defs["solo"]["parent_stream"])

    def test_child_schema_contains_parent_fields(self):
        schemas, _, defs = _discover(
            [
                ("Employment", ["userId"], {"userId": STR}, []),
                (
                    "Job",
                    ["userId", "seqNumber"],
                    {"userId": STR, "seqNumber": STR},
                    [("employmentNav", "Employment_Job", "Employment")],
                ),
            ],
            _assoc("Employment_Job", "Job", "Employment"),
        )
        self.assertEqual(defs["job"]["parent_stream"], "employment")
        self.assertIn("__parent_employment_userId", schemas["job"]["properties"])

    def test_date_time_filter_against_string_key_is_dropped(self):
        _, _, defs = _discover(
            [
                ("Parent", ["code"], {"code": STR}, []),
                (
                    "Child",
                    ["childId"],
                    {"childId": STR, "stamp": DT},
                    [("parentNav", "Parent_Child", "Parent")],
                ),
            ],
            _assoc(
                "Parent_Child", "Child", "Parent",
                constraint=_constraint("code", "stamp"),
            ),
        )
        self.assertIsNone(defs["child"]["parent_stream"])


LMD = "lastModifiedDateTime"
SYNTHETIC_FLAG = "tap-sap-success-factors.synthetic-replication-key"


def _root_metadata(field_metadata, stream):
    return next(m["metadata"] for m in field_metadata[stream] if not m["breadcrumb"])


class TestSyntheticReplicationKey(unittest.TestCase):

    def test_full_table_child_of_incremental_parent_becomes_incremental(self):
        schemas, field_metadata, defs = _discover(
            [
                ("Employment", ["userId"], {"userId": STR, LMD: DT}, []),
                (
                    "Job",
                    ["userId", "seq"],
                    {"userId": STR, "seq": STR},
                    [("employmentNav", "Employment_Job", "Employment")],
                ),
            ],
            _assoc("Employment_Job", "Job", "Employment"),
        )
        key = f"__parent_employment_{LMD}"
        self.assertEqual(defs["job"]["replication_method"], "INCREMENTAL")
        self.assertEqual(defs["job"]["replication_keys"], [key])
        self.assertEqual(
            schemas["job"]["properties"][key],
            {"type": ["null", "string"], "format": "date-time"},
        )
        root = _root_metadata(field_metadata, "job")
        self.assertEqual(root["forced-replication-method"], "INCREMENTAL")
        self.assertEqual(root["valid-replication-keys"], [key])
        self.assertTrue(root[SYNTHETIC_FLAG])
        field = next(
            m["metadata"] for m in field_metadata["job"]
            if tuple(m["breadcrumb"]) == ("properties", key)
        )
        self.assertEqual(field["inclusion"], "automatic")

    def test_child_with_own_replication_key_is_untouched(self):
        schemas, field_metadata, defs = _discover(
            [
                ("Employment", ["userId"], {"userId": STR, LMD: DT}, []),
                (
                    "Job",
                    ["userId", "seq"],
                    {"userId": STR, "seq": STR, LMD: DT},
                    [("employmentNav", "Employment_Job", "Employment")],
                ),
            ],
            _assoc("Employment_Job", "Job", "Employment"),
        )
        self.assertEqual(defs["job"]["replication_keys"], [LMD])
        self.assertNotIn(f"__parent_employment_{LMD}", schemas["job"]["properties"])
        self.assertNotIn(SYNTHETIC_FLAG, _root_metadata(field_metadata, "job"))

    def test_full_table_child_of_full_table_parent_stays_full_table(self):
        schemas, field_metadata, defs = _discover(
            [
                ("Employment", ["userId"], {"userId": STR}, []),
                (
                    "Job",
                    ["userId", "seq"],
                    {"userId": STR, "seq": STR},
                    [("employmentNav", "Employment_Job", "Employment")],
                ),
            ],
            _assoc("Employment_Job", "Job", "Employment"),
        )
        self.assertEqual(defs["job"]["replication_method"], "FULL_TABLE")
        self.assertEqual(defs["job"]["replication_keys"], [])
        self.assertNotIn(SYNTHETIC_FLAG, _root_metadata(field_metadata, "job"))
        self.assertNotIn("synthetic_replication_key", defs["job"])
        self.assertNotIn(f"__parent_employment_{LMD}", schemas["job"]["properties"])

    def test_grandchild_chains_through_the_synthetic_key_of_its_parent(self):
        schemas, _, defs = _discover(
            [
                ("Employment", ["userId"], {"userId": STR, LMD: DT}, []),
                (
                    "Job",
                    ["Employment_userId"],
                    {"Employment_userId": STR},
                    [("employmentNav", "Employment_Job", "Employment")],
                ),
                (
                    "Detail",
                    ["Job_Employment_userId", "line"],
                    {"Job_Employment_userId": STR, "line": STR},
                    [("jobNav", "Job_Detail", "Job")],
                ),
            ],
            _assoc("Employment_Job", "Job", "Employment")
            + _assoc("Job_Detail", "Detail", "Job"),
        )
        key = f"__parent_employment_{LMD}"
        self.assertEqual(defs["detail"]["parent_stream"], "job")
        self.assertEqual(defs["job"]["replication_keys"], [key])
        self.assertEqual(
            defs["detail"]["replication_keys"], [f"__parent_job_{key}"]
        )
        self.assertIn(f"__parent_job_{key}", schemas["detail"]["properties"])
