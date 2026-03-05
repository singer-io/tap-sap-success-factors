from unittest.mock import Mock

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


def _client():
    response = Mock()
    response.text = METADATA_XML

    client = Mock()
    client.base_url = "https://example.successfactors.com"
    client.odata_path = "/odata/v2"
    client.get_access_token.return_value = "token"
    client.request_raw.return_value = response
    return client


def test_dynamic_discovery_builds_schemas_and_metadata():
    schemas, field_metadata, stream_defs = discover_dynamic_streams(_client())
    assert "calibration_template" in schemas
    assert "calibration_template" in field_metadata
    assert stream_defs["calibration_template"]["replication_method"] == "INCREMENTAL"
    assert schemas["calibration_template"]["type"] == "object"


def test_discover_returns_catalog_entries():
    client = _client()
    catalog = discover(client)
    stream_names = {stream.stream for stream in catalog.streams}
    assert "calibration_template" in stream_names


def test_association_without_referential_constraint_infers_relationship():
    metadata_xml = """<?xml version="1.0" encoding="utf-8"?>
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

    response = Mock()
    response.text = metadata_xml

    client = Mock()
    client.base_url = "https://example.successfactors.com"
    client.odata_path = "/odata/v2"
    client.get_access_token.return_value = "token"
    client.request_raw.return_value = response

    _schemas, _metadata, stream_defs = discover_dynamic_streams(client)
    wf_request = stream_defs["wf_request"]

    assert wf_request["parent_stream"] == "employee_profile_sub_section_config"
    assert wf_request["relationship_inference"] == "multiplicity_heuristic"


def test_child_schema_contains_parent_identifier_fields():
    metadata_xml = """<?xml version="1.0" encoding="utf-8"?>
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

    response = Mock()
    response.text = metadata_xml

    client = Mock()
    client.base_url = "https://example.successfactors.com"
    client.odata_path = "/odata/v2"
    client.get_access_token.return_value = "token"
    client.request_raw.return_value = response

    schemas, _metadata, stream_defs = discover_dynamic_streams(client)

    child = schemas["child_entity"]["properties"]
    assert stream_defs["child_entity"]["parent_stream"] == "parent_entity"
    assert stream_defs["child_entity"]["parent_filter_field"] == "ParentEntityNavId"
    assert "ParentEntityNavId" in child
    assert "__parent_parent_entity_parentId" in child
