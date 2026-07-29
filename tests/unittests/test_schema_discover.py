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

    def test_without_referential_constraint_infers_relationship(self):
        _schemas, _metadata, stream_defs = discover_dynamic_streams(_client(self.ASSOCIATION_XML))
        wf_request = stream_defs["wf_request"]
        self.assertEqual(wf_request["parent_stream"], "employee_profile_sub_section_config")
        self.assertEqual(wf_request["relationship_inference"], "multiplicity_heuristic")


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
                <Key><PropertyRef Name="childId"/></Key>
                <Property Name="childId" Type="Edm.String" Nullable="false"/>
                <Property Name="parentEntityId" Type="Edm.String"/>
                <Property Name="ParentEntityNavId" Type="Edm.String"/>
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
        self.assertEqual(stream_defs["child_entity"]["parent_filter_field"], "ParentEntityNavId")
        self.assertIn("ParentEntityNavId", child)
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


# ---------------------------------------------------------------------------
# Type-mismatch guard: DateTime child field vs String parent key
# ---------------------------------------------------------------------------

class TestParentRelationshipTypeMismatch(unittest.TestCase):
    """When parent_filter_field (child) and parent_key_field (parent) have
    incompatible types, the tap must attempt a *rescue* before giving up.

    Rescue strategy: strip the ``Nav`` suffix from the NavigationProperty
    name to obtain a candidate FK field on the child, then verify it is
    type-compatible with the parent key field.

    Real-world example
    ------------------
    TimeZone.countryNav \u2192 Country.
      Country PK = (code:String, effectiveStartDate:DateTime).
      _infer_dependent_field finds effectiveStartDate (DateTime) on TimeZone.
      \u2192 parent_filter_field='effectiveStartDate' (DateTime) vs
        parent_key_field='code' (String)  \u2190 type mismatch.
      Rescue: countryNav \u2192 country \u2192 exists on TimeZone as String \u2713
      \u2192 parent_filter_field replaced with 'country'.
    """

    # TimeZone has 'country' (String) — rescue should find it and replace
    # the mismatched 'effectiveStartDate' FK.
    MISMATCH_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices>
    <Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm" Namespace="SFOData">

      <!-- Parent: composite PK (code:String, effectiveStartDate:DateTime) -->
      <EntityType Name="Country">
        <Key>
          <PropertyRef Name="code"/>
          <PropertyRef Name="effectiveStartDate"/>
        </Key>
        <Property Name="code" Type="Edm.String" Nullable="false"/>
        <Property Name="effectiveStartDate" Type="Edm.DateTime"/>
        <Property Name="lastModifiedDateTime" Type="Edm.DateTime"/>
      </EntityType>

      <!-- Child: has effectiveStartDate (DateTime) AND country (String).
           _infer_dependent_field picks effectiveStartDate first (name match
           from parent PK list), producing a type mismatch.  The rescue
           function should replace it with 'country' (nav base, String). -->
      <EntityType Name="TimeZone">
        <Key>
          <PropertyRef Name="effectiveStartDate"/>
          <PropertyRef Name="externalCode"/>
        </Key>
        <Property Name="externalCode" Type="Edm.String" Nullable="false"/>
        <Property Name="effectiveStartDate" Type="Edm.DateTime"/>
        <Property Name="country" Type="Edm.String"/>
        <Property Name="lastModifiedDateTime" Type="Edm.DateTime"/>
        <NavigationProperty Name="countryNav"
          Relationship="SFOData.countryNav_of_TimeZone"
          FromRole="TimeZone" ToRole="countryNav"/>
      </EntityType>

      <Association Name="countryNav_of_TimeZone">
        <End Type="SFOData.TimeZone" Multiplicity="*" Role="TimeZone"/>
        <End Type="SFOData.Country" Multiplicity="0..1" Role="countryNav"/>
      </Association>

      <EntityContainer Name="C"
          m:IsDefaultEntityContainer="true"
          xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
        <EntitySet Name="Country" EntityType="SFOData.Country"/>
        <EntitySet Name="TimeZone" EntityType="SFOData.TimeZone"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
"""

    # No type-compatible rescue field exists — relationship must be dropped.
    MISMATCH_NO_RESCUE_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices>
    <Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm" Namespace="SFOData">
      <EntityType Name="Parent">
        <Key>
          <PropertyRef Name="code"/>
          <PropertyRef Name="effectiveStartDate"/>
        </Key>
        <Property Name="code" Type="Edm.String" Nullable="false"/>
        <Property Name="effectiveStartDate" Type="Edm.DateTime"/>
      </EntityType>
      <!-- Child: has effectiveStartDate but NO string field matching
           the nav base name 'fooNav' -> 'foo' — rescue must fail. -->
      <EntityType Name="Child">
        <Key><PropertyRef Name="id"/></Key>
        <Property Name="id" Type="Edm.String" Nullable="false"/>
        <Property Name="effectiveStartDate" Type="Edm.DateTime"/>
        <NavigationProperty Name="fooNav"
          Relationship="SFOData.fooNav_of_Child"
          FromRole="Child" ToRole="fooNav"/>
      </EntityType>
      <Association Name="fooNav_of_Child">
        <End Type="SFOData.Child" Multiplicity="*" Role="Child"/>
        <End Type="SFOData.Parent" Multiplicity="0..1" Role="fooNav"/>
      </Association>
      <EntityContainer Name="C"
          m:IsDefaultEntityContainer="true"
          xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
        <EntitySet Name="Parent" EntityType="SFOData.Parent"/>
        <EntitySet Name="Child" EntityType="SFOData.Child"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
"""

    def test_type_mismatch_rescues_with_nav_base_field(self):
        """When effectiveStartDate (DateTime) is wrongly picked as FK to
        Country.code (String), the rescue must replace parent_filter_field
        with 'country' (the nav base name field, which IS String-typed)."""
        _, _, stream_defs = discover_dynamic_streams(
            _client(self.MISMATCH_XML)
        )
        tz = stream_defs["time_zone"]
        # Relationship must be KEPT (not dropped)
        self.assertEqual(tz["parent_stream"], "country")
        # parent_key_field stays unchanged (it was always correct)
        self.assertEqual(tz["parent_key_field"], "code")
        # parent_filter_field must be the rescued String field
        self.assertEqual(
            tz["parent_filter_field"],
            "country",
            "Rescue must replace the mismatched DateTime field with the "
            "type-compatible 'country' field derived from 'countryNav'",
        )

    def test_type_mismatch_drops_when_rescue_fails(self):
        """When no type-compatible rescue field exists the relationship
        must be dropped (parent_stream set to None)."""
        _, _, stream_defs = discover_dynamic_streams(
            _client(self.MISMATCH_NO_RESCUE_XML)
        )
        self.assertIsNone(
            stream_defs["child"]["parent_stream"],
            "Relationship must be dropped when rescue finds no compatible field",
        )

    # Mirrors the PickListValueV2 scenario: parent composite PK has
    # effectiveStartDate (DateTime) first, then a String-typed id.  The child
    # FK is String → Stage 1 (Option B) should swap parent_key_field to the
    # String-typed alternate PK instead of dropping the relationship.
    ALTERNATE_PK_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices>
    <Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm" Namespace="SFOData">

      <!-- Parent: PK = [effectiveStartDate(DateTime), picklistId(String),
           externalCode(String)].  First PK is DateTime. -->
      <EntityType Name="Picklist">
        <Key>
          <PropertyRef Name="effectiveStartDate"/>
          <PropertyRef Name="picklistId"/>
          <PropertyRef Name="externalCode"/>
        </Key>
        <Property Name="effectiveStartDate" Type="Edm.DateTime"/>
        <Property Name="picklistId" Type="Edm.String"/>
        <Property Name="externalCode" Type="Edm.String"/>
      </EntityType>

      <!-- Child: has 'externalCode' (String) which matches the third
           parent PK name.  _infer_dependent_field returns 'externalCode'.
           parent_key_field defaults to first PK 'effectiveStartDate'
           (DateTime) → type mismatch.  Stage 1 should replace
           parent_key_field with 'picklistId' (String). -->
      <EntityType Name="JobCode">
        <Key>
          <PropertyRef Name="externalCode"/>
          <PropertyRef Name="startDate"/>
        </Key>
        <Property Name="externalCode" Type="Edm.String"/>
        <Property Name="startDate" Type="Edm.DateTime"/>
        <Property Name="employeeClass" Type="Edm.String"/>
        <NavigationProperty Name="employeeClassNav"
          Relationship="SFOData.employeeClassNav_of_JobCode"
          FromRole="JobCode" ToRole="employeeClassNav"/>
      </EntityType>

      <Association Name="employeeClassNav_of_JobCode">
        <End Type="SFOData.JobCode" Multiplicity="*" Role="JobCode"/>
        <End Type="SFOData.Picklist" Multiplicity="0..1" Role="employeeClassNav"/>
      </Association>

      <EntityContainer Name="C"
          m:IsDefaultEntityContainer="true"
          xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
        <EntitySet Name="Picklist" EntityType="SFOData.Picklist"/>
        <EntitySet Name="JobCode" EntityType="SFOData.JobCode"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
"""

    def test_type_mismatch_rescued_by_alternate_parent_pk(self):
        """Stage 1 (Option B): when parent first PK is DateTime but child FK
        is String, swap parent_key_field to the first String-typed parent PK.

        Mirrors the real FOJobCode/CurrencyExchangeRate → PickListValueV2
        scenario where PickListValueV2 PKs are:
          [PickListV2_effectiveStartDate(DateTime), PickListV2_id(String), ...].
        The child FK (e.g. externalCode/defaultEmployeeClass) is String
        → type mismatch with the first DateTime PK
        → Stage 1 rescues by swapping to PickListV2_id (String)."""
        _, _, stream_defs = discover_dynamic_streams(
            _client(self.ALTERNATE_PK_XML)
        )
        job = stream_defs["job_code"]
        # Relationship must be KEPT
        self.assertEqual(job["parent_stream"], "picklist")
        # parent_filter_field stays as-is (externalCode on child, String)
        self.assertEqual(job["parent_filter_field"], "externalCode")
        # parent_key_field must be rescued to the String-typed alternate PK
        self.assertEqual(
            job["parent_key_field"],
            "picklistId",
            "Stage 1 must replace the mismatched DateTime parent_key_field "
            "with the first String-typed alternate PK 'picklistId'",
        )

    def test_same_type_string_relationship_not_affected(self):
        """When parent_key and parent_filter are both String, no rescue is
        needed and the relationship must be preserved as-is."""
        xml = """\
<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices>
    <Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm" Namespace="SFOData">
      <EntityType Name="ParentE">
        <Key><PropertyRef Name="parentId"/></Key>
        <Property Name="parentId" Type="Edm.String" Nullable="false"/>
      </EntityType>
      <EntityType Name="ChildE">
        <Key><PropertyRef Name="childId"/></Key>
        <Property Name="childId" Type="Edm.String" Nullable="false"/>
        <Property Name="parentId" Type="Edm.String"/>
        <NavigationProperty Name="parentNav"
          Relationship="SFOData.parentNav_of_ChildE"
          FromRole="ChildE" ToRole="parentNav"/>
      </EntityType>
      <Association Name="parentNav_of_ChildE">
        <End Type="SFOData.ChildE" Multiplicity="*" Role="ChildE"/>
        <End Type="SFOData.ParentE" Multiplicity="0..1" Role="parentNav"/>
      </Association>
      <EntityContainer Name="C"
          m:IsDefaultEntityContainer="true"
          xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
        <EntitySet Name="ParentE" EntityType="SFOData.ParentE"/>
        <EntitySet Name="ChildE" EntityType="SFOData.ChildE"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
"""
        _, _, stream_defs = discover_dynamic_streams(_client(xml))
        child = stream_defs["child_e"]
        self.assertEqual(
            child["parent_stream"],
            "parent_e",
            "String-String relationship must NOT be dropped or altered",
        )
        self.assertEqual(child["parent_filter_field"], "parentId")
