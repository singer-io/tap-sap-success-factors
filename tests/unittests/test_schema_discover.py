import unittest
from unittest.mock import Mock, patch

from tap_sap_success_factors.discover import discover
from tap_sap_success_factors.metadata_discovery import discover_dynamic_streams

METADATA_XML = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
    <edmx:DataServices>
        <Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm" Namespace="SFOData">
            <EntityType Name="CalibrationTemplate">
                <Key>
                    <PropertyRef Name="templateId"/>
                </Key>
                <Property Name="templateId" Type="Edm.String" Nullable="false"/>
                <Property Name="templateName" Type="Edm.String"/>
                <Property Name="lastModifiedDateTime" Type="Edm.DateTime"/>
            </EntityType>
            <EntityContainer
                Name="Container"
                m:IsDefaultEntityContainer="true"
                xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
            >
                <EntitySet Name="CalibrationTemplate" EntityType="SFOData.CalibrationTemplate"/>
            </EntityContainer>
        </Schema>
    </edmx:DataServices>
</edmx:Edmx>
"""


def _client(metadata_xml=None):
    response = Mock()
    response.text = metadata_xml if metadata_xml is not None else METADATA_XML

    client = Mock()
    client.base_url = "https://example.successfactors.com"
    client.odata_path = "/odata/v2"
    client.get_access_token.return_value = "token"
    client.request_raw.return_value = response
    return client


class TestDynamicDiscovery(unittest.TestCase):

    def test_builds_schemas_and_metadata(self):
        schemas, field_metadata, stream_defs = discover_dynamic_streams(_client())
        self.assertIn("calibration_template", schemas)
        self.assertIn("calibration_template", field_metadata)
        self.assertEqual(stream_defs["calibration_template"]["replication_method"], "INCREMENTAL")
        self.assertEqual(schemas["calibration_template"]["type"], "object")

    def test_discover_returns_catalog_entries(self):
        with patch(
            "tap_sap_success_factors.discover.probe_all_streams",
            return_value=set(),
        ):
            catalog = discover(_client())
        stream_names = {stream.stream for stream in catalog.streams}
        self.assertIn("calibration_template", stream_names)

    def test_emits_only_sortable_primary_keys(self):
        metadata_xml = METADATA_XML.replace(
            '<Property Name="templateId" Type="Edm.String" Nullable="false"/>',
            '<Property Name="templateId" Type="Edm.String" Nullable="false" '
            'xmlns:sap="http://www.successfactors.com/edm/sap" '
            'sap:sortable="false"/>',
        )

        _, field_metadata, _ = discover_dynamic_streams(_client(metadata_xml))
        root_metadata = next(
            item["metadata"]
            for item in field_metadata["calibration_template"]
            if item["breadcrumb"] == ()
        )

        self.assertEqual(
            root_metadata["tap-sap-success-factors.sortable-key-properties"],
            [],
        )


class TestAssociationInference(unittest.TestCase):

    ASSOCIATION_XML = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
    <edmx:DataServices>
        <Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm" Namespace="SFOData">
            <EntityType Name="EmployeeProfileSubSectionConfig">
                <Key><PropertyRef Name="id"/></Key>
                <Property Name="id" Type="Edm.String" Nullable="false"/>
            </EntityType>
            <EntityType Name="WfRequest">
                <Key><PropertyRef Name="wfRequestId"/></Key>
                <Property Name="wfRequestId" Type="Edm.String" Nullable="false"/>
                <Property Name="id" Type="Edm.String"/>
                <NavigationProperty
                    Name="EmployeeProfileSubSectionConfigNav"
                    Relationship="SFOData.EmployeeProfileSubSectionConfig_WfRequest"
                    FromRole="WfRequest"
                    ToRole="EmployeeProfileSubSectionConfig"
                />
            </EntityType>
            <Association Name="EmployeeProfileSubSectionConfig_WfRequest">
                <End
                    Type="SFOData.EmployeeProfileSubSectionConfig"
                    Multiplicity="1"
                    Role="EmployeeProfileSubSectionConfig"
                />
                <End Type="SFOData.WfRequest" Multiplicity="*" Role="WfRequest"/>
            </Association>
            <EntityContainer
                Name="Container"
                m:IsDefaultEntityContainer="true"
                xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
            >
                <EntitySet
                    Name="EmployeeProfileSubSectionConfig"
                    EntityType="SFOData.EmployeeProfileSubSectionConfig"
                />
                <EntitySet Name="WfRequest" EntityType="SFOData.WfRequest"/>
            </EntityContainer>
        </Schema>
    </edmx:DataServices>
</edmx:Edmx>
"""

    def test_generic_name_without_key_composition_is_not_a_parent(self):
        # WfRequest only shares the generic, non-key column ``id`` with the
        # target, which is not evidence of a parent link.
        _schemas, _metadata, stream_defs = discover_dynamic_streams(_client(self.ASSOCIATION_XML))
        wf_request = stream_defs["wf_request"]
        self.assertIsNone(wf_request["parent_stream"])
        self.assertIsNone(wf_request["relationship_inference"])


class TestChildSchemaParentFields(unittest.TestCase):

    CHILD_PARENT_XML = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
    <edmx:DataServices>
        <Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm" Namespace="SFOData">
            <EntityType Name="ParentEntity">
                <Key><PropertyRef Name="parentId"/></Key>
                <Property Name="parentId" Type="Edm.String" Nullable="false"/>
            </EntityType>
            <EntityType Name="ChildEntity">
                <Key>
                    <PropertyRef Name="parentId"/>
                    <PropertyRef Name="childId"/>
                </Key>
                <Property Name="parentId" Type="Edm.String" Nullable="false"/>
                <Property Name="childId" Type="Edm.String" Nullable="false"/>
                <NavigationProperty
                    Name="ParentEntityNav"
                    Relationship="SFOData.ParentEntity_ChildEntity"
                    FromRole="ChildEntity"
                    ToRole="ParentEntity"
                />
            </EntityType>
            <Association Name="ParentEntity_ChildEntity">
                <End Type="SFOData.ParentEntity" Multiplicity="1" Role="ParentEntity"/>
                <End Type="SFOData.ChildEntity" Multiplicity="*" Role="ChildEntity"/>
            </Association>
            <EntityContainer
                Name="Container"
                m:IsDefaultEntityContainer="true"
                xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
            >
                <EntitySet Name="ParentEntity" EntityType="SFOData.ParentEntity"/>
                <EntitySet Name="ChildEntity" EntityType="SFOData.ChildEntity"/>
            </EntityContainer>
        </Schema>
    </edmx:DataServices>
</edmx:Edmx>
"""

    def test_child_schema_contains_parent_identifier_fields(self):
        schemas, _metadata, stream_defs = discover_dynamic_streams(_client(self.CHILD_PARENT_XML))
        child = schemas["child_entity"]["properties"]
        self.assertEqual(stream_defs["child_entity"]["parent_stream"], "parent_entity")
        self.assertEqual(stream_defs["child_entity"]["parent_filter_field"], "parentId")
        self.assertIn("parentId", child)
        self.assertIn("__parent_parent_entity_parentId", child)


# ---------------------------------------------------------------------------
# SAP sap:filterable annotation tests
# ---------------------------------------------------------------------------

class TestSAPFilterableAnnotation(unittest.TestCase):
    """sap:filterable='false' prevents a field from being used as a rep-key."""

    # A stream with lastModifiedDateTime annotated as non-filterable at the
    # SAP level.  Discovery must fall back to FULL_TABLE.
    FILTERABLE_FALSE_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
    <edmx:DataServices>
        <Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm"
                xmlns:sap="http://www.sap.com/Protocols/SAPData"
                Namespace="SFOData">
            <EntityType Name="SomeEntity">
                <Key><PropertyRef Name="id"/></Key>
                <Property Name="id" Type="Edm.String" Nullable="false"/>
                <Property Name="lastModifiedDateTime" Type="Edm.DateTime"
                          sap:filterable="false"/>
            </EntityType>
            <EntityContainer Name="Container"
                m:IsDefaultEntityContainer="true"
                xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
            >
                <EntitySet Name="SomeEntity"
                           EntityType="SFOData.SomeEntity"/>
            </EntityContainer>
        </Schema>
    </edmx:DataServices>
</edmx:Edmx>
"""

    def test_non_filterable_replication_key_yields_full_table(self):
        """A lastModifiedDateTime with sap:filterable='false' must not become a
        replication key — the stream should be FULL_TABLE."""
        _, _, stream_defs = discover_dynamic_streams(
            _client(self.FILTERABLE_FALSE_XML)
        )
        self.assertEqual(
            stream_defs["some_entity"]["replication_method"],
            "FULL_TABLE",
        )
        self.assertEqual(
            stream_defs["some_entity"]["replication_keys"],
            [],
        )

    # Same entity without sap:filterable annotation — should be INCREMENTAL.
    FILTERABLE_DEFAULT_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
    <edmx:DataServices>
        <Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm"
                Namespace="SFOData">
            <EntityType Name="SomeEntity">
                <Key><PropertyRef Name="id"/></Key>
                <Property Name="id" Type="Edm.String" Nullable="false"/>
                <Property Name="lastModifiedDateTime" Type="Edm.DateTime"/>
            </EntityType>
            <EntityContainer Name="Container"
                m:IsDefaultEntityContainer="true"
                xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
            >
                <EntitySet Name="SomeEntity"
                           EntityType="SFOData.SomeEntity"/>
            </EntityContainer>
        </Schema>
    </edmx:DataServices>
</edmx:Edmx>
"""

    def test_filterable_by_default_when_annotation_absent(self):
        """When sap:filterable is absent the property is filterable by default
        and lastModifiedDateTime should be selected as a replication key."""
        _, _, stream_defs = discover_dynamic_streams(
            _client(self.FILTERABLE_DEFAULT_XML)
        )
        self.assertEqual(
            stream_defs["some_entity"]["replication_method"],
            "INCREMENTAL",
        )
        self.assertEqual(
            stream_defs["some_entity"]["replication_keys"],
            ["lastModifiedDateTime"],
        )


# ---------------------------------------------------------------------------
# FORCED_FULL_TABLE_STREAMS override tests
# ---------------------------------------------------------------------------

class TestSAPFilterableFullTable(unittest.TestCase):
    """A stream whose only replication-key candidate has sap:filterable=false
    must resolve to FULL_TABLE with no replication keys.

    This is the actual mechanism that keeps theme_info and user_permissions
    as FULL_TABLE — the EDMX itself marks their lastModified* properties as
    non-filterable, so no separate runtime override constant is needed.
    """

    # lastModifiedDateTime is present but marked sap:filterable=false —
    # so it must NOT be selected as a replication key.
    THEME_INFO_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
    <edmx:DataServices>
        <Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm"
                xmlns:sap="http://www.successfactors.com/edm/sap"
                Namespace="SFOData">
            <EntityType Name="ThemeInfo">
                <Key><PropertyRef Name="themeId"/></Key>
                <Property Name="themeId" Type="Edm.String" Nullable="false"/>
                <Property Name="lastModifiedDateTime" Type="Edm.DateTime"
                          sap:filterable="false"/>
            </EntityType>
            <EntityContainer Name="Container"
                m:IsDefaultEntityContainer="true"
                xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
            >
                <EntitySet Name="ThemeInfo"
                           EntityType="SFOData.ThemeInfo"/>
            </EntityContainer>
        </Schema>
    </edmx:DataServices>
</edmx:Edmx>
"""

    def test_non_filterable_replication_key_yields_full_table(self):
        """theme_info is FULL_TABLE because lastModifiedDateTime has
        sap:filterable=false — no separate override constant required."""
        _, _, stream_defs = discover_dynamic_streams(
            _client(self.THEME_INFO_XML)
        )
        self.assertEqual(
            stream_defs["theme_info"]["replication_method"],
            "FULL_TABLE",
        )
        self.assertEqual(
            stream_defs["theme_info"]["replication_keys"],
            [],
        )


class TestBlockedExpandNavProperties(unittest.TestCase):
    """wfRequestNav must never be selected as an expand-nav-property.

    SAP documents (KBA 2604638, KBA 2963505) that expanding wfRequestNav on
    normal (non-pending) data raises COE0025.  Even if an entity looks
    expand-only and the only reverse-nav path goes through wfRequestNav, the
    tap must not use it.
    """

    # WfPendingAction looks expand-only (all props sap:filterable/sortable/
    # creatable=false, no NavigationProperty) and the ONLY nav that points to
    # it is wfRequestNav on WfRequest.  The tap must NOT set expand metadata.
    EDMX = """\
<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices>
    <Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm"
            xmlns:sap="http://www.sap.com/Protocols/SAPData"
            Namespace="SFOData">

      <EntityType Name="WfPendingAction">
        <Key><PropertyRef Name="actionId"/></Key>
        <Property Name="actionId" Type="Edm.String"
                  sap:filterable="false" sap:sortable="false"
                  sap:creatable="false"/>
        <Property Name="label" Type="Edm.String"
                  sap:filterable="false" sap:sortable="false"
                  sap:creatable="false"/>
      </EntityType>

      <EntityType Name="WfRequest">
        <Key><PropertyRef Name="wfRequestId"/></Key>
        <Property Name="wfRequestId" Type="Edm.Int64"/>
        <NavigationProperty Name="wfRequestNav"
          Relationship="SFOData.WfRequest_WfPendingAction"
          FromRole="WfRequest" ToRole="WfPendingAction"/>
      </EntityType>

      <Association Name="WfRequest_WfPendingAction">
        <End Type="SFOData.WfRequest"
             Multiplicity="1" Role="WfRequest"/>
        <End Type="SFOData.WfPendingAction"
             Multiplicity="*" Role="WfPendingAction"/>
      </Association>

      <EntityContainer Name="C"
          m:IsDefaultEntityContainer="true"
          xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
        <EntitySet Name="WfRequest"
                   EntityType="SFOData.WfRequest"/>
        <EntitySet Name="WfPendingAction"
                   EntityType="SFOData.WfPendingAction"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
"""

    def test_wf_request_nav_never_used_as_expand_target(self):
        """wf_pending_action must NOT receive expand-nav-property metadata
        even though it is expand-only and reachable only via wfRequestNav."""
        _, field_mdata, _ = discover_dynamic_streams(_client(self.EDMX))
        root_mdata = {
            entry["breadcrumb"]: entry["metadata"]
            for entry in field_mdata.get("wf_pending_action", [])
        }
        stream_root = root_mdata.get(())
        self.assertIsNotNone(
            stream_root, "wf_pending_action must be discovered"
        )
        self.assertNotIn(
            "tap-sap-success-factors.expand-nav-property",
            stream_root,
            "wfRequestNav must not be selected as expand-nav-property",
        )

